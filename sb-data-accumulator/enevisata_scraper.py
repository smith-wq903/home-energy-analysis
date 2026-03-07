"""
Enevisata スクレイパー
毎日23:45 JSTに実行し、以下を収集：
- 30分データ（当日分、00:00〜20:30 JST程度）
- 日次データ（当月分）
- 月次データ（当年・前年）
"""

import os
import re
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright
from supabase import create_client

load_dotenv()

JST = timezone(timedelta(hours=9))
BASE_URL = "https://www.enability.jp/EneVista/jsp"
LOGIN_URL = f"{BASE_URL}/to-login.action?firstLoginFlg=0&brand=NP"
URL_30MIN = f"{BASE_URL}/condition-time-show.action"
URL_DAILY = f"{BASE_URL}/condition-day-show.action"
URL_MONTHLY = f"{BASE_URL}/condition-month-show.action"


def login(page, login_id: str, password: str) -> None:
    page.goto(LOGIN_URL)
    page.wait_for_load_state("domcontentloaded")
    page.fill('[name="loginId"]', login_id)
    page.fill('input[type="password"]', password)
    page.click("#login")
    page.wait_for_load_state("domcontentloaded")
    print(f"ログイン完了: {page.url}")


def extract_tables(page) -> list[list[list[str]]]:
    """ページ内の全テーブルのセルテキストを取得"""
    return page.evaluate("""
        () => Array.from(document.querySelectorAll('table')).map(table =>
            Array.from(table.querySelectorAll('tr'))
                .map(row => Array.from(row.querySelectorAll('td, th'))
                    .map(cell => cell.textContent.trim()))
                .filter(cells => cells.length > 0)
        ).filter(rows => rows.length > 0)
    """)


def scrape_30min(page, today) -> list[dict]:
    """
    30分データを取得
    テーブル構造: 6つの別テーブル（各4時間分）× 2列（時間範囲・使用量）× 8行
    時間フォーマット: "00:00-00:30"
    """
    page.goto(URL_30MIN)
    page.wait_for_load_state("domcontentloaded")

    tables = extract_tables(page)
    records = []

    for table in tables:
        for row in table:
            if len(row) != 2:
                continue
            time_range, usage_str = row[0].strip(), row[1].strip()

            # "HH:MM-HH:MM" 形式の開始時刻を抽出
            m = re.match(r'^(\d{2}:\d{2})-\d{2}:\d{2}$', time_range)
            if not m:
                continue

            try:
                hour, minute = map(int, m.group(1).split(':'))
                recorded_at = datetime(
                    today.year, today.month, today.day,
                    hour, minute, tzinfo=JST
                )
                usage = None
                if usage_str and usage_str not in ['-', '－', '—', '']:
                    usage = float(usage_str.replace(',', ''))

                records.append({
                    'recorded_at': recorded_at.isoformat(),
                    'usage_kwh': usage,
                })
            except (ValueError, TypeError):
                continue

    print(f"30分データ: {len(records)} 件取得")
    return records


def scrape_daily(page, now: datetime) -> list[dict]:
    """
    日次データを取得（当月分）
    テーブル構造: 15列（5グループ × 月日・合計・累計の3列）× 7行
    """
    page.goto(URL_DAILY)
    page.wait_for_load_state("domcontentloaded")

    # 月選択ドロップダウン（"YYYY年M月" または "YYYY年MM月" 形式を試みる）
    month_labels = [
        f"{now.year}年{now.month}月",
        f"{now.year}年{now.month:02d}月",
    ]
    for label in month_labels:
        try:
            page.select_option("select", label=label)
            break
        except Exception:
            continue

    # 「実績を見る」ボタンをクリック
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
            # データ行は3列: ['2/9(月)', '14.8', '14.8']
            if len(row) != 3:
                continue
            date_str, total_str, cumul_str = row[0].strip(), row[1].strip(), row[2].strip()

            # "M/D(曜)" 形式から月日を抽出
            m = re.match(r'^(\d{1,2})/(\d{1,2})', date_str)
            if not m:
                continue

            key = date_str
            if key in seen:
                continue

            try:
                month, day = int(m.group(1)), int(m.group(2))
                # 月が現在月より大きければ前年
                year = now.year if month <= now.month else now.year - 1
                recorded_date = datetime(year, month, day).date()
                total = float(total_str.replace(',', '')) if total_str not in ['-', '－', ''] else None
                cumul = float(cumul_str.replace(',', '')) if cumul_str not in ['-', '－', ''] else None

                records.append({
                    'recorded_date': recorded_date.isoformat(),
                    'usage_kwh': total,
                    'cumulative_kwh': cumul,
                })
                seen.add(key)
            except (ValueError, TypeError):
                continue

    print(f"日次データ: {len(records)} 件取得")
    return records


def scrape_monthly(page, now: datetime) -> list[dict]:
    """
    月次データを取得（当年・前年）
    テーブル構造: 3列（月・当年・前年）× 12行
    """
    page.goto(URL_MONTHLY)
    page.wait_for_load_state("domcontentloaded")

    current_year = str(now.year)
    prev_year = str(now.year - 1)

    selects = page.query_selector_all("select")
    if len(selects) >= 2:
        selects[0].select_option(current_year)
        selects[1].select_option(prev_year)

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
                key = (int(current_year), month)
                if key in seen:
                    continue

                if year1_str not in ['-', '－', '']:
                    records.append({
                        'year': int(current_year),
                        'month': month,
                        'usage_kwh': float(year1_str.replace(',', '')),
                    })
                if year2_str not in ['-', '－', '']:
                    records.append({
                        'year': int(prev_year),
                        'month': month,
                        'usage_kwh': float(year2_str.replace(',', '')),
                    })
                seen.add(key)
            except (ValueError, TypeError):
                continue

    print(f"月次データ: {len(records)} 件取得")
    return records


def main() -> None:
    supabase = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_ANON_KEY"])
    login_id = os.environ["ENEVISATA_LOGIN_ID"]
    password = os.environ["ENEVISATA_PASSWORD"]

    now = datetime.now(JST)
    today = now.date()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        try:
            login(page, login_id, password)

            records_30min = scrape_30min(page, today)
            if records_30min:
                supabase.table("enevisata_30min").upsert(
                    records_30min, on_conflict="recorded_at"
                ).execute()
                print(f"30分データ保存: {len(records_30min)} 件")

            records_daily = scrape_daily(page, now)
            if records_daily:
                supabase.table("enevisata_daily").upsert(
                    records_daily, on_conflict="recorded_date"
                ).execute()
                print(f"日次データ保存: {len(records_daily)} 件")

        finally:
            browser.close()


if __name__ == "__main__":
    main()
