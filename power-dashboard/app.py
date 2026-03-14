"""
家庭電力ダッシュボード（Streamlit）
- SwitchBot: 機器別消費電力（W）
- Enevisata: 家全体の電力使用量（kWh）
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


# ------------------------------------------------------------------ #
# SwitchBot データ取得
# ------------------------------------------------------------------ #
@st.cache_data(ttl=300)
def load_recent(hours: int) -> pd.DataFrame:
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


@st.cache_data(ttl=3600)
def load_aggregated(hours: int) -> pd.DataFrame:
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


def load_switchbot(hours: int) -> pd.DataFrame:
    df_recent = load_recent(hours)
    frames = [df_recent]
    if hours > 24:
        df_agg = load_aggregated(hours)
        if not df_agg.empty:
            frames.append(df_agg)
    df = pd.concat(frames, ignore_index=True)
    if not df.empty:
        df["recorded_at"] = pd.to_datetime(df["recorded_at"], utc=True, format="mixed").dt.tz_convert("Asia/Tokyo")
        df = df.sort_values("recorded_at")
    return df


# ------------------------------------------------------------------ #
# Enevisata データ取得
# ------------------------------------------------------------------ #
@st.cache_data(ttl=3600)
def load_enevisata_30min(hours: int) -> pd.DataFrame:
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    result = (
        get_supabase()
        .table("enevisata_30min")
        .select("recorded_at, usage_kwh")
        .gte("recorded_at", since)
        .order("recorded_at")
        .limit(10000)
        .execute()
    )
    df = pd.DataFrame(result.data)
    if not df.empty:
        df["recorded_at"] = pd.to_datetime(df["recorded_at"], utc=True, format="mixed").dt.tz_convert("Asia/Tokyo")
        df["usage_kwh"] = pd.to_numeric(df["usage_kwh"], errors="coerce")
    return df


@st.cache_data(ttl=3600)
def load_enevisata_daily() -> pd.DataFrame:
    result = (
        get_supabase()
        .table("enevisata_daily")
        .select("recorded_date, usage_kwh, cumulative_kwh")
        .order("recorded_date")
        .limit(10000)
        .execute()
    )
    df = pd.DataFrame(result.data)
    if not df.empty:
        df["recorded_date"] = pd.to_datetime(df["recorded_date"])
        df["usage_kwh"] = pd.to_numeric(df["usage_kwh"], errors="coerce")
    return df


@st.cache_data(ttl=86400)
def load_enevisata_monthly() -> pd.DataFrame:
    result = (
        get_supabase()
        .table("enevisata_monthly")
        .select("year, month, usage_kwh")
        .order("year")
        .order("month")
        .execute()
    )
    df = pd.DataFrame(result.data)
    if not df.empty:
        df["usage_kwh"] = pd.to_numeric(df["usage_kwh"], errors="coerce")
        df["date"] = pd.to_datetime(df[["year", "month"]].assign(day=1))
        df["年月"] = df["date"].dt.strftime("%Y年%m月")
        df["年"] = df["year"].astype(str)
    return df


hours = 720  # 直近1ヶ月固定

# ------------------------------------------------------------------ #
# タブ
# ------------------------------------------------------------------ #
tab1, tab2, tab3 = st.tabs(["リアルタイム", "日次", "月次"])

# ------------------------------------------------------------------ #
# タブ1：リアルタイム（SwitchBot + Enevisata 30分）
# ------------------------------------------------------------------ #
with tab1:
    df_sb = load_switchbot(hours)

if df_sb.empty:
        st.warning("SwitchBot データがありません。")
    else:
        latest = df_sb.groupby("device_name").last().reset_index()
        total_w = latest["power_w"].sum()
        st.metric("現在の合計消費電力", f"{total_w:.1f} W")

        # Enevisata 30分データをWに換算してSwitchBotデータと統合
        # kWh（30分） × 2 = kW × 1000 = W
        df_e30 = load_enevisata_30min(hours)
        if not df_e30.empty:
            df_e30_w = df_e30[["recorded_at", "usage_kwh"]].copy()
            df_e30_w["power_w"] = df_e30_w["usage_kwh"] * 2000
            df_e30_w = df_e30_w.dropna(subset=["power_w"])
            df_e30_w["device_name"] = "家全体 (Enevisata)"
            df_combined = pd.concat(
                [df_sb[["recorded_at", "power_w", "device_name"]], df_e30_w[["recorded_at", "power_w", "device_name"]]],
                ignore_index=True,
            ).sort_values("recorded_at")
        else:
            df_combined = df_sb[["recorded_at", "power_w", "device_name"]]

        st.subheader("機器別 消費電力 (W)")
        fig = px.line(
            df_combined,
            x="recorded_at",
            y="power_w",
            color="device_name",
            labels={"recorded_at": "時刻", "power_w": "消費電力 (W)", "device_name": "機器名"},
        )
        fig.update_layout(
            height=550,
            margin=dict(t=120),
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.12,
                xanchor="left",
                x=0,
                title_text="機器名",
            ),
            xaxis=dict(
                rangeslider=dict(visible=True),
                rangeselector=dict(
                    buttons=[
                        dict(count=1,  label="1日",   step="day",   stepmode="backward"),
                        dict(count=7,  label="1週間", step="day",   stepmode="backward"),
                        dict(count=1,  label="1ヶ月", step="month", stepmode="backward"),
                        dict(step="all", label="全期間"),
                    ]
                ),
            ),
        )
        st.plotly_chart(fig, use_container_width=True)

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

# ------------------------------------------------------------------ #
# タブ2：日次
# ------------------------------------------------------------------ #
with tab2:
    df_ed = load_enevisata_daily()
    if df_ed.empty:
        st.info("Enevisata 日次データがありません。")
    else:
        st.subheader("日次電力使用量 (kWh)")
        fig_ed = px.bar(
            df_ed,
            x="recorded_date",
            y="usage_kwh",
            labels={"recorded_date": "日付", "usage_kwh": "使用量 (kWh)"},
        )
        fig_ed.update_layout(
            height=550,
            xaxis=dict(
                rangeslider=dict(visible=True),
                rangeselector=dict(
                    buttons=[
                        dict(count=1,  label="1ヶ月", step="month", stepmode="backward"),
                        dict(count=3,  label="3ヶ月", step="month", stepmode="backward"),
                        dict(count=6,  label="6ヶ月", step="month", stepmode="backward"),
                        dict(step="all", label="全期間"),
                    ]
                ),
            ),
        )
        st.plotly_chart(fig_ed, use_container_width=True)

# ------------------------------------------------------------------ #
# タブ3：月次
# ------------------------------------------------------------------ #
with tab3:
    df_em = load_enevisata_monthly()
    if df_em.empty:
        st.info("Enevisata 月次データがありません。")
    else:
        st.subheader("月次電力使用量 (kWh)")
        fig_em = px.bar(
            df_em,
            x="date",
            y="usage_kwh",
            color="年",
            labels={"date": "年月", "usage_kwh": "使用量 (kWh)", "年": "年"},
            color_discrete_sequence=px.colors.qualitative.Set2,
        )
        fig_em.update_layout(
            height=550,
            legend_title_text="年",
            xaxis=dict(
                range=[df_em["date"].min(), df_em["date"].max()],
                rangeslider=dict(visible=True, range=[df_em["date"].min(), df_em["date"].max()]),
                rangeselector=dict(
                    buttons=[
                        dict(count=6,  label="6ヶ月", step="month", stepmode="backward"),
                        dict(count=1,  label="1年",   step="year",  stepmode="backward"),
                        dict(step="all", label="全期間"),
                    ]
                ),
            ),
        )
        st.plotly_chart(fig_em, use_container_width=True)
