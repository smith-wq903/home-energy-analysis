"""
日次データのバックフィルスクリプト。
指定した年月リストのデータをEnevistaからスクレイプしてSupabaseに保存する。

使用例:
  python backfill_daily.py 2026 4        # 2026年4月のみ
  python backfill_daily.py 2026 3 4      # 2026年3月〜4月
"""

import os
import sys
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright
from supabase import create_client

from enevisata_scraper import BASE_URL, URL_DAILY, login, extract_tables, select_month

load_dotenv()

JST = timezone(timedelta(hours=9))


def scrape_daily_for_month(page, year: int, month: int) -> list[dict]:
    page.goto(URL_DAILY)
    page.wait_for_load_state("networkidle")

    selected = select_month(page, year, month)
    if not selected:
        print(f"  {year}年{month}月: 月選択失敗、スキップ")
        return []

    try:
        page.click('input[value="実績を見る"]')
    except Exception:
        page.click('button:has-text("実績を見る")')
    page.wait_for_load_state("networkidle")

    tables = extract_tables(page)
    records = []
    seen = set()
    now = datetime(year, month, 1, tzinfo=JST)

    import re
    for table in tables:
        for row in table:
            if len(row) != 3:
                continue
            date_str, total_str, cumul_str = row[0].strip(), row[1].strip(), row[2].strip()

            m = re.match(r'^(\d{1,2})/(\d{1,2})', date_str)
            if not m:
                continue

            key = date_str
            if key in seen:
                continue

            try:
                mon, day = int(m.group(1)), int(m.group(2))
                yr = now.year if mon <= now.month else now.year - 1
                recorded_date = datetime(yr, mon, day).date()
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

    print(f"  {year}年{month}月: {len(records)} 件取得")
    return records


def main():
    args = sys.argv[1:]
    if len(args) < 2:
        print("使用法: python backfill_daily.py <year> <month> [month2] ...")
        sys.exit(1)

    year = int(args[0])
    months = [int(m) for m in args[1:]]

    supabase = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])
    login_id = os.environ["ENEVISATA_LOGIN_ID"]
    password = os.environ["ENEVISATA_PASSWORD"]

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        try:
            login(page, login_id, password)

            for month in months:
                records = scrape_daily_for_month(page, year, month)
                if records:
                    supabase.table("enevisata_daily").upsert(
                        records, on_conflict="recorded_date"
                    ).execute()
                    print(f"  保存完了: {len(records)} 件")
        finally:
            browser.close()


if __name__ == "__main__":
    main()
