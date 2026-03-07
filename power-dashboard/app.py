"""
家庭電力ダッシュボード（Streamlit）
- 直近24時間: device_power（5分粒度の生データ）
- それ以前:   device_power_30min（30分粒度の集約データ）
を結合して可視化する
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


@st.cache_data(ttl=300)  # 5分キャッシュ
def load_recent(hours: int) -> pd.DataFrame:
    """直近 hours 時間分の生データ（最大24時間）を取得"""
    fetch_hours = min(hours, 24)
    since = (datetime.now(timezone.utc) - timedelta(hours=fetch_hours)).isoformat()
    result = (
        get_supabase()
        .table("device_power")
        .select("device_name, recorded_at, power_w, voltage_v, current_a")
        .gte("recorded_at", since)
        .order("recorded_at")
        .limit(10000)
        .execute()
    )
    return pd.DataFrame(result.data)


@st.cache_data(ttl=3600)  # 1時間キャッシュ（1日1回更新のため）
def load_aggregated(hours: int) -> pd.DataFrame:
    """24時間より古い集約データ（30分粒度）を取得"""
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    until = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    result = (
        get_supabase()
        .table("device_power_30min")
        .select("device_name, recorded_at, power_w, voltage_v, current_a")
        .gte("recorded_at", since)
        .lt("recorded_at", until)
        .order("recorded_at")
        .limit(200000)
        .execute()
    )
    return pd.DataFrame(result.data)


def load_data(hours: int) -> pd.DataFrame:
    df_recent = load_recent(hours)
    frames = [df_recent]

    if hours > 24:
        df_agg = load_aggregated(hours)
        if not df_agg.empty:
            frames.append(df_agg)

    df = pd.concat(frames, ignore_index=True)
    if not df.empty:
        df["recorded_at"] = pd.to_datetime(df["recorded_at"]).dt.tz_convert("Asia/Tokyo")
        df = df.sort_values("recorded_at")
    return df


# ------------------------------------------------------------------ #
# サイドバー
# ------------------------------------------------------------------ #
hours = st.sidebar.selectbox(
    "表示期間",
    options=[24, 72, 168, 720, 8760],
    format_func=lambda x: {
        24: "直近 24時間",
        72: "直近 3日",
        168: "直近 1週間",
        720: "直近 1ヶ月",
        8760: "直近 1年",
    }[x],
    index=0,
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
fig.update_layout(
    legend_title_text="機器名",
    xaxis=dict(
        rangeslider=dict(visible=True),
        rangeselector=dict(
            buttons=[
                dict(count=6,  label="6時間", step="hour",  stepmode="backward"),
                dict(count=1,  label="1日",   step="day",   stepmode="backward"),
                dict(count=7,  label="1週間", step="day",   stepmode="backward"),
                dict(count=1,  label="1ヶ月", step="month", stepmode="backward"),
                dict(step="all", label="全期間"),
            ]
        ),
    ),
)
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
