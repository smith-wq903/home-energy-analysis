"""
SwitchBot API v1.1 → Supabase データ収集スクリプト

GitHub Actions から5分毎に1回実行される（ループなし）。
sb_monitor.py のデバイス定義・変数名を踏襲しつつ、
API v1.1 (HMAC-SHA256) + Supabase 保存に対応。
"""

import base64
import hashlib
import hmac
import os
import time
import uuid
from datetime import datetime, timezone

import httpx
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

SWITCHBOT_API_BASE = "https://api.switch-bot.com/v1.1"

# ------------------------------------------------------------------ #
# デバイスIDと名前のマッピング（sb_monitor.py の方式を踏襲）
# .env の DEVICE_IDS / DEVICE_NAMES をカンマ区切りで定義する
#
# 例）
#   DEVICE_IDS=abc123,def456,...
#   DEVICE_NAMES=ペンペン,デスクライト,冷蔵庫,トイレ,ベッド,玄関充電,デスクチャージャー,テレビ他,洗濯機,ドライヤー
# ------------------------------------------------------------------ #
_device_ids = [d.strip() for d in os.environ["DEVICE_IDS"].split(",")]
_device_names = [n.strip() for n in os.environ["DEVICE_NAMES"].split(",")]
DEVICE_MAP: dict[str, str] = dict(zip(_device_ids, _device_names))


# ------------------------------------------------------------------ #
# SwitchBot API v1.1 認証ヘッダー（HMAC-SHA256）
# ------------------------------------------------------------------ #
def _auth_headers() -> dict:
    token = os.environ["SB_API_TOKEN"]
    secret = os.environ["SB_API_SECRET"]
    nonce = str(uuid.uuid4())
    t = str(int(time.time() * 1000))
    string_to_sign = f"{token}{t}{nonce}"
    sign = base64.b64encode(
        hmac.new(secret.encode(), string_to_sign.encode(), hashlib.sha256).digest()
    ).decode()
    return {
        "Authorization": token,
        "sign": sign,
        "nonce": nonce,
        "t": t,
        "Content-Type": "application/json",
    }


# ------------------------------------------------------------------ #
# API 呼び出し
# ------------------------------------------------------------------ #
def _get_device_status(client: httpx.Client, device_id: str) -> dict:
    resp = client.get(
        f"{SWITCHBOT_API_BASE}/devices/{device_id}/status",
        headers=_auth_headers(),
    )
    resp.raise_for_status()
    body = resp.json()
    if body.get("statusCode") != 100:
        raise RuntimeError(f"SwitchBot API error: {body}")
    return body["body"]


# ------------------------------------------------------------------ #
# メイン処理（GitHub Actions から1回だけ呼ばれる）
# ------------------------------------------------------------------ #
def main() -> None:
    supabase = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])
    now = datetime.now(timezone.utc)
    timestamp_str = now.strftime("%Y-%m-%d %H:%M:%S")  # sb_monitor.py と同形式

    rows: list[dict] = []
    with httpx.Client(timeout=30) as client:
        for device_id, device_name in DEVICE_MAP.items():
            try:
                status = _get_device_status(client, device_id)
                power = status.get("weight")      # 消費電力 (W)
                voltage = status.get("voltage")   # 電圧 (V)
                current = status.get("electricCurrent")  # 電流 (A)
                rows.append({
                    "device_id": device_id,
                    "device_name": device_name,
                    "recorded_at": now.isoformat(),
                    "power_w": power,
                    "voltage_v": voltage,
                    "current_a": current,
                })
                print(f"{timestamp_str} - {device_name}: {power}")
            except Exception as exc:
                print(f"Error for {device_name}: {exc}")
            time.sleep(1)  # レート制限対策：デバイスごとに1秒待機

    if rows:
        supabase.table("device_power").insert(rows).execute()
        print(f"✅ データ保存完了: {len(rows)} 件 ({timestamp_str})")
    else:
        print("保存するデータがありませんでした。")


if __name__ == "__main__":
    main()
