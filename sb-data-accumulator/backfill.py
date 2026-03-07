"""
device_power テーブルの全履歴データを30分平均に集約して
device_power_30min テーブルに一括保存するスクリプト（一回限り実行）

GitHub Actions の workflow_dispatch から手動実行する。
データを1日単位で処理し、upsert するため重複実行しても安全。
"""

import os
from datetime import datetime, timedelta, timezone

import pandas as pd
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

JST = timezone(timedelta(hours=9))


def fetch_day(supabase, start: datetime, end: datetime) -> pd.DataFrame:
    result = (
        supabase
        .table("device_power")
        .select("device_name, recorded_at, power_w, voltage_v, current_a")
        .gte("recorded_at", start.isoformat())
        .lt("recorded_at", end.isoformat())
        .order("recorded_at")
        .limit(100000)
        .execute()
    )
    return pd.DataFrame(result.data)


def aggregate_day(df: pd.DataFrame) -> list[dict]:
    for col in ["power_w", "voltage_v", "current_a"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    rows = []
    for device_name, group in df.groupby("device_name"):
        group = group.set_index("recorded_at").sort_index()
        resampled = group[["power_w", "voltage_v", "current_a"]].resample("30min").mean()

        for ts, row_data in resampled.iterrows():
            if pd.isna(row_data["power_w"]):
                continue
            rows.append({
                "device_name": device_name,
                "recorded_at": ts.isoformat(),
                "power_w": round(float(row_data["power_w"]), 2),
                "voltage_v": round(float(row_data["voltage_v"]), 2) if pd.notna(row_data["voltage_v"]) else None,
                "current_a": round(float(row_data["current_a"]), 2) if pd.notna(row_data["current_a"]) else None,
            })
    return rows


def main() -> None:
    supabase = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_ANON_KEY"])

    # 最古のレコードを取得して開始日を決定
    oldest = (
        supabase
        .table("device_power")
        .select("recorded_at")
        .order("recorded_at")
        .limit(1)
        .execute()
    )
    if not oldest.data:
        print("device_power にデータがありません")
        return

    first_dt = pd.to_datetime(oldest.data[0]["recorded_at"]).tz_convert(JST)
    # 日単位で切り捨て
    current = first_dt.replace(hour=0, minute=0, second=0, microsecond=0)
    # 昨日の終わりまで処理（今日のデータは aggregator.py に任せる）
    today = datetime.now(JST).replace(hour=0, minute=0, second=0, microsecond=0)

    print(f"バックフィル範囲: {current.date()} 〜 {(today - timedelta(days=1)).date()}")

    total = 0
    while current < today:
        day_end = current + timedelta(days=1)
        df = fetch_day(supabase, current, day_end)

        if not df.empty:
            df["recorded_at"] = pd.to_datetime(df["recorded_at"], utc=True)
            rows = aggregate_day(df)
            if rows:
                supabase.table("device_power_30min").upsert(rows, on_conflict="device_name,recorded_at").execute()
                total += len(rows)
                print(f"  {current.date()}: {len(rows)} 件")
            else:
                print(f"  {current.date()}: 集約データなし")
        else:
            print(f"  {current.date()}: データなし")

        current = day_end

    print(f"完了: 合計 {total} 件")


if __name__ == "__main__":
    main()
