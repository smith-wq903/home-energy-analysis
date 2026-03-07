"""
Enevisata 月次データ収集スクリプト
毎月1日 01:00 JST に実行し、当年・前年の月次データを取得する
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
URL_MONTHLY = "https://www.enability.jp/EneVista/jsp/condition-month-show.action"


def scrape_monthly(page, now: datetime) -> list[dict]:
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

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        try:
            login(page, login_id, password)

            records = scrape_monthly(page, now)
            if records:
                supabase.table("enevisata_monthly").upsert(
                    records, on_conflict="year,month"
                ).execute()
                print(f"月次データ保存: {len(records)} 件")
        finally:
            browser.close()


if __name__ == "__main__":
    main()
