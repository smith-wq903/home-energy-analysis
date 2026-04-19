"""
毎月の料金単価データを収集して power-dashboard/tariff_data.csv に追記する。

実行タイミング: 毎月15日（GitHub Actions）
対象: 当月の明細（前月9日〜当月8日）に適用される単価

■ 燃料費調整単価の計算式
  TEPCOの公表値（支援込み）から前月の政府支援額を戻した値を使う。
  NP燃料費調整 = TEPCO公表値 + 前月の政府支援単価
  NP支援額     = 前月の政府支援単価（マイナス表示）

  ※ Next Powerの「N月分」明細（期間: N-1/9〜N/8）は
     TEPCOのN月レートに前月(N-1)の支援を組み合わせるため。
"""

import csv
import re
import sys
from datetime import date
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

CSV_PATH = Path(__file__).parent.parent / "power-dashboard" / "tariff_data.csv"

TEPCO_FUELCOST_URL = "https://www.tepco.co.jp/ep/private/fuelcost2/newlist/index-j.html"

# 再エネ賦課金単価（年度 → 単価）
# 年度の4月〜翌年3月に適用。2026年度以降は判明次第追記。
RENEWABLE_RATES: dict[int, float] = {
    2023: 1.40,
    2024: 3.49,
    2025: 3.98,
    2026: 4.18,
}

# 電気料金負担軽減支援（使用月 → 低圧単価 円/kWh）
# 政府発表を踏まえて都度更新。未定の月はキーなし（0円扱い）。
SUPPORT_BY_USE_MONTH: dict[tuple[int, int], float] = {
    (2026, 1): 4.50,
    (2026, 2): 4.50,
    (2026, 3): 1.50,
}

# 固定料金（スタンダードS・40A契約）
# 料金改定時にここを更新するか、CSVの直近行を参照して自動継承する。
DEFAULT_BASIC_FEE = 1247.00
DEFAULT_TIER1 = 29.80
DEFAULT_TIER2 = 36.40
DEFAULT_TIER3 = 40.49


def fiscal_year(year: int, month: int) -> int:
    """4月始まりの年度を返す。"""
    return year if month >= 4 else year - 1


def renewable_rate(year: int, month: int) -> float:
    fy = fiscal_year(year, month)
    if fy not in RENEWABLE_RATES:
        raise ValueError(f"再エネ賦課金単価が未定義です: {fy}年度")
    return RENEWABLE_RATES[fy]


def support_rate(year: int, month: int) -> float:
    """指定した使用月の政府支援単価を返す（未定義なら0）。"""
    return SUPPORT_BY_USE_MONTH.get((year, month), 0.0)


def scrape_tepco_rate(year: int, month: int) -> float:
    """TEPCOの燃料費調整単価一覧ページから指定月の低圧単価を取得する。"""
    resp = httpx.get(TEPCO_URL, timeout=30, follow_redirects=True)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    target = f"{year}年{month}月分"

    for row in soup.find_all("tr"):
        cells = [td.get_text(strip=True) for td in row.find_all(["td", "th"])]
        row_text = "".join(cells)
        if target in row_text:
            for cell in cells:
                cell = cell.replace("▲", "-").replace(",", "")
                try:
                    return float(cell)
                except ValueError:
                    continue

    raise ValueError(f"TEPCO燃料費調整単価が見つかりません: {target}")


def load_csv() -> list[dict]:
    if not CSV_PATH.exists():
        return []
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def already_exists(rows: list[dict], year: int, month: int) -> bool:
    return any(int(r["year"]) == year and int(r["month"]) == month for r in rows)


def latest_fixed_rates(rows: list[dict]) -> tuple[float, float, float, float]:
    """直近行から固定料金を継承する（空欄なら DEFAULT を使用）。"""
    for row in reversed(rows):
        try:
            return (
                float(row["基本料金"]),
                float(row["第1段階単価"]),
                float(row["第2段階単価"]),
                float(row["第3段階単価"]),
            )
        except (KeyError, ValueError):
            continue
    return DEFAULT_BASIC_FEE, DEFAULT_TIER1, DEFAULT_TIER2, DEFAULT_TIER3


def write_csv(rows: list[dict]) -> None:
    fieldnames = [
        "year", "month",
        "基本料金", "第1段階単価", "第2段階単価", "第3段階単価",
        "燃料費調整単価", "再エネ賦課金単価", "負担軽減支援単価", "一括受電割引額",
    ]
    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    today = date.today()
    year, month = today.year, today.month

    rows = load_csv()
    if already_exists(rows, year, month):
        print(f"{year}年{month}月のデータは既に存在します。スキップします。")
        return

    print(f"{year}年{month}月の単価を収集します...")

    # 前月（明細の使用期間の主たる月）
    prev_year, prev_month = (year, month - 1) if month > 1 else (year - 1, 12)

    tepco_rate = scrape_tepco_rate(year, month)
    print(f"  TEPCO公表値（{year}年{month}月分）: {tepco_rate:.2f}円/kWh")

    prev_support = support_rate(prev_year, prev_month)
    np_fuel = round(tepco_rate + prev_support, 2)
    np_support = -prev_support if prev_support else 0.0
    reene = renewable_rate(year, month)
    basic, t1, t2, t3 = latest_fixed_rates(rows)

    new_row: dict = {
        "year": year,
        "month": month,
        "基本料金": basic,
        "第1段階単価": t1,
        "第2段階単価": t2,
        "第3段階単価": t3,
        "燃料費調整単価": np_fuel,
        "再エネ賦課金単価": reene,
        "負担軽減支援単価": np_support if np_support != 0.0 else 0.00,
        "一括受電割引額": "",
    }
    print(f"  NP燃料費調整: {np_fuel:.2f}  再エネ: {reene:.2f}  支援: {np_support:.2f}")

    rows.append(new_row)
    rows.sort(key=lambda r: (int(r["year"]), int(r["month"])))
    write_csv(rows)
    print(f"CSV更新完了: {CSV_PATH}")


TEPCO_URL = TEPCO_FUELCOST_URL

if __name__ == "__main__":
    main()
