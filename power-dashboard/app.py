"""
家庭電力ダッシュボード（Streamlit）
Supabase から device_power テーブルを読み取って可視化する
"""

import os
from datetime import datetime, timedelta, timezone

import pandas as pd
import plotly.express as px
import streamlit as st
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

st.set_page_config(page_title="家庭電力ダッシュボード", layout="wide")
st.title("家庭電力ダッシュボード")


@st.cache_resource
def get_supabase():
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_ANON_KEY"])


@st.cache_data(ttl=300)  # 5分キャッシュ（収集間隔と合わせる）
def load_data(hours: int) -> pd.DataFrame:
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    result = (
        get_supabase()
        .table("device_power")
        .select("device_name, recorded_at, power_w, voltage_v, current_a")
        .gte("recorded_at", since)
        .order("recorded_at")
        .execute()
    )
    df = pd.DataFrame(result.data)
    if not df.empty:
        df["recorded_at"] = pd.to_datetime(df["recorded_at"]).dt.tz_convert("Asia/Tokyo")
    return df


# ------------------------------------------------------------------ #
# サイドバー
# ------------------------------------------------------------------ #
hours = st.sidebar.selectbox(
    "表示期間",
    options=[6, 24, 72, 168],
    format_func=lambda x: f"過去 {x} 時間",
    index=1,
)

if st.sidebar.button("データ更新"):
    st.cache_data.clear()

# ------------------------------------------------------------------ #
# データ取得
# ------------------------------------------------------------------ #
df = load_data(hours)

if df.empty:
    st.warning("データがありません。コレクターの設定・動作を確認してください。")
    st.stop()

# ------------------------------------------------------------------ #
# KPI（現在の合計電力）
# ------------------------------------------------------------------ #
latest = df.groupby("device_name").last().reset_index()
total_w = latest["power_w"].sum()
st.metric("現在の合計消費電力", f"{total_w:.1f} W")

# ------------------------------------------------------------------ #
# 機器別電力推移グラフ
# ------------------------------------------------------------------ #
st.subheader("機器別 消費電力 (W)")
fig = px.line(
    df,
    x="recorded_at",
    y="power_w",
    color="device_name",
    labels={"recorded_at": "時刻", "power_w": "消費電力 (W)", "device_name": "機器名"},
)
fig.update_layout(legend_title_text="機器名")
st.plotly_chart(fig, use_container_width=True)

# ------------------------------------------------------------------ #
# 現在の機器状態テーブル
# ------------------------------------------------------------------ #
st.subheader("現在の機器状態")
st.dataframe(
    latest[["device_name", "power_w", "voltage_v", "current_a", "recorded_at"]].rename(
        columns={
            "device_name": "機器名",
            "power_w": "消費電力 (W)",
            "voltage_v": "電圧 (V)",
            "current_a": "電流 (A)",
            "recorded_at": "最終取得時刻",
        }
    ),
    use_container_width=True,
    hide_index=True,
)
