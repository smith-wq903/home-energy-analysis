"""
Enevisata 過去データ一括取得スクリプト（一回限り実行）

- 日次データ: ドロップダウンの全月を順に取得
- 月次データ: ドロップダウンの全年の組み合わせを取得
"""

import os
import re
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright
from supabase import create_client

from enevisata_scraper import login, extract_tables

load_dotenv()

JST = timezone(timedelta(hours=9))
URL_DAILY = "https://www.enability.jp/EneVista/jsp/condition-day-show.action"
URL_MONTHLY = "https://www.enability.jp/EneVista/jsp/condition-month-show.action"


def backfill_daily(page, supabase) -> None:
    """日次ページのドロップダウンにある全月を取得"""
    page.goto(URL_DAILY)
    page.wait_for_load_state("domcontentloaded")

    # ドロップダウンの全オプションを取得（"YYYY年M月" 形式を想定）
    options = page.evaluate("""
        () => Array.from(document.querySelectorAll('select option'))
            .map(o => ({value: o.value, label: o.textContent.trim()}))
            .filter(o => o.label.includes('年') && o.label.includes('月'))
    """)
    print(f"取得可能な月数: {len(options)}")

    total = 0
    for opt in options:
        label = opt['label']  # 例: "2025年2月"
        m = re.match(r'(\d{4})年(\d{1,2})月', label)
        if not m:
            continue
        sel_year, sel_month = int(m.group(1)), int(m.group(2))

        page.goto(URL_DAILY)
        page.wait_for_load_state("domcontentloaded")

        try:
            page.select_option("select", value=opt['value'])
        except Exception:
            page.select_option("select", label=label)

        try:
            page.click('input[value="実績を見る"]')
        except Exception:
            page.click('button:has-text("実績を見る")')
        page.wait_for_load_state("domcontentloaded")

        tables = extract_tables(page)
        records = []
        seen = set()

        for table in tables:
            for row in table:
                if len(row) != 3:
                    continue
                date_str, total_str, cumul_str = row[0].strip(), row[1].strip(), row[2].strip()

                dm = re.match(r'^(\d{1,2})/(\d{1,2})', date_str)
                if not dm or date_str in seen:
                    continue

                try:
                    row_month, day = int(dm.group(1)), int(dm.group(2))
                    # 月をまたぐ場合（例: 2月ページに1月末が含まれる）
                    if row_month == sel_month:
                        year = sel_year
                    elif row_month < sel_month:
                        year = sel_year
                    else:
                        year = sel_year - 1

                    recorded_date = datetime(year, row_month, day).date()
                    total_val = float(total_str.replace(',', '')) if total_str not in ['-', '－', ''] else None
                    cumul_val = float(cumul_str.replace(',', '')) if cumul_str not in ['-', '－', ''] else None

                    records.append({
                        'recorded_date': recorded_date.isoformat(),
                        'usage_kwh': total_val,
                        'cumulative_kwh': cumul_val,
                    })
                    seen.add(date_str)
                except (ValueError, TypeError):
                    continue

        if records:
            supabase.table("enevisata_daily").upsert(
                records, on_conflict="recorded_date"
            ).execute()
            total += len(records)
            print(f"  {label}: {len(records)} 件保存")
        else:
            print(f"  {label}: データなし")

    print(f"日次データ 合計: {total} 件")


def backfill_monthly(page, supabase) -> None:
    """月次ページのドロップダウンにある全年の組み合わせを取得"""
    page.goto(URL_MONTHLY)
    page.wait_for_load_state("domcontentloaded")

    selects = page.query_selector_all("select")
    if not selects:
        print("月次ページのドロップダウンが見つかりません")
        return

    # 利用可能な年を取得
    years = page.evaluate("""
        () => Array.from(document.querySelectorAll('select')[0].options)
            .map(o => o.value.trim())
            .filter(v => /^\d{4}$/.test(v))
    """)
    years = sorted(set(years), reverse=True)
    print(f"取得可能な年: {years}")

    total = 0
    seen_pairs = set()

    for i, year1 in enumerate(years):
        for year2 in years[i + 1:i + 2]:  # 隣接する年ペアのみ
            pair = (year1, year2)
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)

            page.goto(URL_MONTHLY)
            page.wait_for_load_state("domcontentloaded")

            selects = page.query_selector_all("select")
            if len(selects) >= 2:
                selects[0].select_option(year1)
                selects[1].select_option(year2)

            try:
                page.click('input[value="実績を比較する"]')
            except Exception:
                page.click('button:has-text("実績を比較する")')
            page.wait_for_load_state("domcontentloaded")

            tables = extract_tables(page)
            records = []
            seen = set()

            for table in tables:
                for row in table:
                    if len(row) < 3:
                        continue
                    month_str = row[0].strip()
                    year1_str = row[1].strip()
                    year2_str = row[2].strip()

                    if not re.match(r'^\d{1,2}月$', month_str):
                        continue

                    try:
                        month = int(month_str.replace('月', ''))
                        key = (int(year1), month)
                        if key in seen:
                            continue

                        if year1_str not in ['-', '－', '']:
                            records.append({
                                'year': int(year1),
                                'month': month,
                                'usage_kwh': float(year1_str.replace(',', '')),
                            })
                        if year2_str not in ['-', '－', '']:
                            records.append({
                                'year': int(year2),
                                'month': month,
                                'usage_kwh': float(year2_str.replace(',', '')),
                            })
                        seen.add(key)
                    except (ValueError, TypeError):
                        continue

            if records:
                supabase.table("enevisata_monthly").upsert(
                    records, on_conflict="year,month"
                ).execute()
                total += len(records)
                print(f"  {year1}年/{year2}年: {len(records)} 件保存")

    print(f"月次データ 合計: {total} 件")


def main() -> None:
    supabase = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_ANON_KEY"])
    login_id = os.environ["ENEVISATA_LOGIN_ID"]
    password = os.environ["ENEVISATA_PASSWORD"]

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        try:
            login(page, login_id, password)
            backfill_daily(page, supabase)
            backfill_monthly(page, supabase)
        finally:
            browser.close()


if __name__ == "__main__":
    main()
