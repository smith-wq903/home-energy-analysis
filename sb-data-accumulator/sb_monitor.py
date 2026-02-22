import requests
import json
import time
from datetime import datetime
import pandas as pd
import os
from dotenv import load_dotenv

# 環境変数の読み込み
load_dotenv()

# SwitchBot API設定
API_TOKEN = os.getenv('SB_API_TOKEN')

# デバイスIDと名前のマッピング
device_ids = os.getenv('DEVICE_ID').split(',')
device_names = ["ペンペン", "デスクライト", "冷蔵庫", "トイレ", "ベッド", 
               "玄関充電", "デスクチャージャー", "テレビ他", "洗濯機", "ドライヤー"]
DEVICE_IDS = dict(zip(device_ids, device_names))

def get_power_consumption(device_id, device_name):
    """APIからデータを取得する関数"""
    url = f"https://api.switch-bot.com/v1.0/devices/{device_id}/status"
    headers = {
        "Authorization": API_TOKEN
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        data = response.json()
        power = data.get("body", {}).get("weight", 0)
        return power
    else:
        print(f"Error {response.status_code} for {device_name}")
        return None

def save_to_csv(data, file_name):
    """データをCSVファイルに保存"""
    # フォルダ"SB_Data"の作成
    output_dir = os.path.join(os.getcwd(), "SB_Data")
    os.makedirs(output_dir, exist_ok=True)

    # 保存ファイルパスの生成
    filename = f"SB_power_data_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
    filepath = os.path.join(output_dir, filename)

    # DataFrameの作成とCSVファイル保存
    df = pd.DataFrame(data, columns=["Timestamp", "Device", "Power"])
    df.to_csv(filepath, index=False)
    print(f"✅ データ保存完了: {filepath}")

def main():
    # 保存したCSVファイル名を保持
    file_names = [f for f in os.listdir('.') if f.startswith('power_readings_') and f.endswith('.csv')]
    file_count = len(file_names)
    total_duration = 60*24-6  # 合計収集時間（分）
    log_freq = 5            # ログ収集頻度（分）
    interval_min = 60  # CSVファイル作成間隔（分）
    interval = int(interval_min/log_freq)

    try:
        for i in range(file_count, file_count + total_duration // interval):
            collected_data = []  # データを保存するリスト

            for j in range(interval):  # interval_min分間隔でデータ収集,ファイル作成
                timestamp = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
                for device_id, device_name in DEVICE_IDS.items():
                    power_reading = get_power_consumption(device_id, device_name)
                    collected_data.append([timestamp, device_name, power_reading])
                    print(f"{timestamp} - {device_name}: {power_reading}")
                time.sleep(60*log_freq)  # 5分待機

            # CSVファイルに保存
            file_name = f"power_readings_{i+1}.csv"
            save_to_csv(collected_data, file_name)

    except KeyboardInterrupt:
        print("\nプログラムが中断されました。")
        # 最後のデータを保存
        if collected_data:
            file_name = f"power_readings_final.csv"
            save_to_csv(collected_data, file_name)
            print("最後のデータを保存しました。")

if __name__ == "__main__":
    main() 