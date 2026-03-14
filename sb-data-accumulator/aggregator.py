"""
device_power テーブルの5分データを30分平均に集約して
device_power_30min テーブルに保存するスクリプト

毎日01:00 JST（16:00 UTC）に実行。
処理対象: 実行時刻の6時間前（前日19:00 JST）から24時間分

- 30分窓内に5分データが1件以上あれば平均値を保存
- 30分窓内に5分データが1件もない場合はスキップ（データなし扱い）
"""

import os
from datetime import datetime, timedelta, timezone

import pandas as pd
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

JST = timezone(timedelta(hours=9))


def main() -> None:
    supabase = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])

    now = datetime.now(JST)
    end = now - timedelta(hours=6)    # 前日 19:00 JST
    start = end - timedelta(hours=24) # 前々日 19:00 JST

    print(f"集約対象期間: {start.isoformat()} 〜 {end.isoformat()}")

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

    if not result.data:
        print("対象データなし")
        return

    df = pd.DataFrame(result.data)
    df["recorded_at"] = pd.to_datetime(df["recorded_at"], utc=True)
    for col in ["power_w", "voltage_v", "current_a"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    rows = []
    for device_name, group in df.groupby("device_name"):
        group = group.set_index("recorded_at").sort_index()

        # 30分平均に集約（窓内にデータが1件もない場合は NaN → スキップ）
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

    if not rows:
        print("集約データなし")
        return

    supabase.table("device_power_30min").upsert(rows, on_conflict="device_name,recorded_at").execute()
    print(f"集約完了: {len(rows)} 件")


if __name__ == "__main__":
    main()
