"""
家庭電力ダッシュボード（Streamlit）
- SwitchBot: 機器別消費電力（W）
- Enevisata: 家全体の電力使用量（kWh）
"""

import os
from datetime import datetime, timedelta, timezone

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio

pio.templates["cockpit"] = go.layout.Template(
    layout=go.Layout(
        font=dict(family="'Courier New', 'Hiragino Sans', monospace", size=12, color="#c8e0f0"),
        paper_bgcolor="#040810",
        plot_bgcolor="#060c18",
        colorway=["#00d4ff", "#ffb300", "#00e676", "#ff4444", "#7c4dff", "#ff6d00"],
        xaxis=dict(gridcolor="#0a2040", zerolinecolor="#0a2040", linecolor="#0a2040", tickcolor="#4a8fa8"),
        yaxis=dict(gridcolor="#0a2040", zerolinecolor="#0a2040", linecolor="#0a2040", tickcolor="#4a8fa8"),
        legend=dict(bgcolor="rgba(4,8,16,0.8)", bordercolor="rgba(0,212,255,0.2)", borderwidth=1),
        margin=dict(l=10, r=10, t=40, b=10),
    )
)
pio.templates.default = "cockpit"
import streamlit as st
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

st.set_page_config(
    page_title="家庭電力ダッシュボード",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Share+Tech+Mono&display=swap');

/* ── ベース背景 ── */
.stApp, [data-testid="stAppViewContainer"] {
    background-color: #040810 !important;
    background-image:
        linear-gradient(rgba(0,212,255,0.025) 1px, transparent 1px),
        linear-gradient(90deg, rgba(0,212,255,0.025) 1px, transparent 1px);
    background-size: 48px 48px;
}
[data-testid="stHeader"] { background: rgba(4,8,16,0.95) !important; border-bottom: 1px solid #00d4ff22; }
[data-testid="block-container"] { padding-top: 1rem !important; }

/* ── タイトルヘッダー ── */
.hud-header {
    font-family: 'Share Tech Mono', 'Courier New', monospace;
    font-size: 1.5rem;
    font-weight: 400;
    color: #00d4ff;
    letter-spacing: 0.15em;
    text-transform: uppercase;
    text-shadow: 0 0 20px rgba(0,212,255,0.6);
    border-bottom: 1px solid #00d4ff33;
    padding-bottom: 0.6rem;
    margin-bottom: 1rem;
}
.hud-header span { color: #4a8fa8; font-size: 0.85rem; margin-left: 1rem; letter-spacing: 0.08em; }

/* ── メトリクスカード ── */
[data-testid="metric-container"] {
    background: linear-gradient(135deg, #060e20 0%, #0a1628 100%) !important;
    border: 1px solid #00d4ff33 !important;
    border-radius: 6px !important;
    padding: 0.8rem 1rem !important;
    box-shadow: 0 0 16px rgba(0,212,255,0.08), inset 0 1px 0 rgba(0,212,255,0.08);
    position: relative;
}
[data-testid="metric-container"]::before {
    content: '';
    position: absolute;
    top: 0; left: 0;
    width: 3px; height: 100%;
    background: linear-gradient(180deg, #00d4ff, transparent);
    border-radius: 6px 0 0 6px;
}
[data-testid="stMetricValue"] {
    font-family: 'Share Tech Mono', 'Courier New', monospace !important;
    font-size: 1.55rem !important;
    font-weight: 400 !important;
    color: #00d4ff !important;
    text-shadow: 0 0 12px rgba(0,212,255,0.5) !important;
    letter-spacing: 0.05em;
}
[data-testid="stMetricLabel"] {
    font-size: 0.68rem !important;
    letter-spacing: 0.12em !important;
    text-transform: uppercase !important;
    color: #4a8fa8 !important;
}
[data-testid="stMetricDelta"] { font-size: 0.78rem !important; }

/* ── セクション見出し ── */
h2 {
    font-family: 'Share Tech Mono', 'Courier New', monospace !important;
    font-size: 1rem !important;
    letter-spacing: 0.12em !important;
    text-transform: uppercase !important;
    color: #00d4ff !important;
    text-shadow: 0 0 8px rgba(0,212,255,0.4);
    border-left: 3px solid #00d4ff !important;
    border-bottom: 1px solid #00d4ff22 !important;
    padding: 0.3rem 0 0.4rem 0.7rem !important;
    margin-top: 1.4rem !important;
    margin-bottom: 0.8rem !important;
}

/* ── タブ ── */
.stTabs [data-baseweb="tab-list"] {
    gap: 2px !important;
    background: #060c18 !important;
    border-bottom: 1px solid #00d4ff33 !important;
    padding: 0 4px !important;
}
.stTabs [data-baseweb="tab"] {
    border-radius: 4px 4px 0 0 !important;
    padding: 6px 14px !important;
    font-size: 0.82rem !important;
    font-family: 'Share Tech Mono', monospace !important;
    letter-spacing: 0.05em !important;
    color: #4a8fa8 !important;
    border: 1px solid transparent !important;
    border-bottom: none !important;
}
.stTabs [aria-selected="true"] {
    background: #0a1628 !important;
    color: #00d4ff !important;
    border-color: #00d4ff33 !important;
    border-bottom: 2px solid #00d4ff !important;
}

/* ── expander ── */
[data-testid="stExpander"] {
    background: #060e20 !important;
    border: 1px solid #00d4ff22 !important;
    border-radius: 6px !important;
    margin-bottom: 4px !important;
}
[data-testid="stExpander"]:hover { border-color: #00d4ff55 !important; }

/* ── divider ── */
hr { border-color: #00d4ff22 !important; margin: 1.2rem 0 !important; }

/* ── dataframe ── */
[data-testid="stDataFrame"] { border: 1px solid #00d4ff22; border-radius: 6px; overflow: hidden; }

/* ── caption ── */
[data-testid="stCaptionContainer"] p { color: #4a8fa8 !important; font-size: 0.72rem !important; }

/* ── success / warning / info ── */
[data-testid="stAlert"] { border-radius: 6px !important; border-left-width: 3px !important; }
</style>
""", unsafe_allow_html=True)

_now_str = datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d  %H:%M JST")
st.markdown(
    f'<div class="hud-header">⚡ HOME ENERGY MONITOR<span>[ {_now_str} ]</span></div>',
    unsafe_allow_html=True,
)


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


@st.cache_data(ttl=300)
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


@st.cache_data(ttl=3600)
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
        df["year"] = pd.to_numeric(df["year"], errors="coerce").astype("Int64")
        df["month"] = pd.to_numeric(df["month"], errors="coerce").astype("Int64")
        df["usage_kwh"] = pd.to_numeric(df["usage_kwh"], errors="coerce")
        df = df.dropna(subset=["year", "month"]).drop_duplicates(subset=["year", "month"])
        df["year"] = df["year"].astype(int)
        df["month"] = df["month"].astype(int)
        df["date"] = pd.to_datetime(df[["year", "month"]].assign(day=1))
        df["年月"] = df["date"].dt.strftime("%Y年%m月")
        df["年"] = df["year"].astype(str)
    return df


@st.cache_data(ttl=3600)
def load_enevisata_30min_all() -> pd.DataFrame:
    result = (
        get_supabase()
        .table("enevisata_30min")
        .select("recorded_at, usage_kwh")
        .order("recorded_at")
        .limit(50000)
        .execute()
    )
    df = pd.DataFrame(result.data)
    if not df.empty:
        df["recorded_at"] = pd.to_datetime(df["recorded_at"], utc=True, format="mixed").dt.tz_convert("Asia/Tokyo")
        df["usage_kwh"] = pd.to_numeric(df["usage_kwh"], errors="coerce")
        df["_date"] = df["recorded_at"].dt.date
    return df


hours = 720  # 直近1ヶ月固定

PLOTLY_CONFIG = {"scrollZoom": True}
CO2_KG_PER_KWH = 0.441          # 東京電力EP 調整後排出係数 2022年度実績 (kg-CO2/kWh)
CO2_PERCAPITA_ELEC_KG_YEAR = 863   # 家庭用電力 一人当たり年間: 世帯平均4,500kWh÷2.3人×0.441 (資源エネルギー庁・総務省)
CO2_PERCAPITA_TOTAL_KG_YEAR = 9040  # 日本全部門 一人当たり年間: 11.3億tCO2÷1.254億人 (環境省 2022年度)

TARIFF_CSV = os.path.join(os.path.dirname(__file__), "tariff_data.csv")

ALL_COL_LABELS = {
    "基本料金": "基本料金 (円/月)",
    "第1段階単価": "第1段階 〜120kWh (円/kWh)",
    "第2段階単価": "第2段階 121〜300kWh (円/kWh)",
    "第3段階単価": "第3段階 301kWh〜 (円/kWh)",
    "燃料費調整単価": "燃料費調整 (円/kWh)",
    "再エネ賦課金単価": "再エネ賦課金 (円/kWh)",
    "負担軽減支援単価": "電気料金負担軽減支援 (円/kWh)",
    "一括受電割引率": "一括受電割引率",
}

# グラフに表示する列（割引率・基本料金は除外）
CHART_COLS = ["燃料費調整単価", "再エネ賦課金単価", "負担軽減支援単価"]


@st.cache_data(ttl=300)
def load_tariff() -> pd.DataFrame:
    df = pd.read_csv(TARIFF_CSV)
    df["date"] = pd.to_datetime(df[["year", "month"]].assign(day=1))
    df["年月"] = df["date"].dt.strftime("%Y年%m月")
    return df


def _get_billing_usage(df_daily: pd.DataFrame, df_monthly: pd.DataFrame) -> pd.DataFrame:
    """日次データを検針期間別に集計し、日次がない期間は月次データで補完して返す。"""
    df_result = pd.DataFrame()
    if not df_daily.empty:
        df = df_daily.copy()
        df["bill_month"] = df["recorded_date"].apply(
            lambda d: d.replace(day=1) if d.day >= 9 else (d.replace(day=1) - pd.offsets.MonthBegin(1))
        )
        df_result = (
            df.groupby("bill_month")["usage_kwh"]
            .sum()
            .reset_index()
            .rename(columns={"bill_month": "date"})
            .assign(year=lambda x: x["date"].dt.year, month=lambda x: x["date"].dt.month)
        )
    if df_monthly.empty:
        return df_result
    df_mon = df_monthly[["date", "year", "month", "usage_kwh"]].copy()
    df_mon["year"] = df_mon["year"].astype(int)
    df_mon["month"] = df_mon["month"].astype(int)
    if df_result.empty:
        return df_mon
    df_result["year"] = df_result["year"].astype(int)
    df_result["month"] = df_result["month"].astype(int)
    min_daily = df_result["date"].min()
    df_mon_old = df_mon[df_mon["date"] < min_daily].drop_duplicates(subset=["year", "month"])
    return (
        pd.concat([df_mon_old, df_result], ignore_index=True)
        .drop_duplicates(subset=["year", "month"])
        .sort_values("date")
        .reset_index(drop=True)
    )


def insert_gaps(df: pd.DataFrame, time_col: str, group_col: str, max_gap_minutes: int) -> pd.DataFrame:
    """時間ギャップが閾値を超える箇所に NaN 行を挿入して折れ線を途切れさせる。"""
    parts = []
    for name, grp in df.groupby(group_col, sort=False):
        grp = grp.sort_values(time_col).reset_index(drop=True)
        big_gaps = grp[time_col].diff() > pd.Timedelta(minutes=max_gap_minutes)
        if big_gaps.any():
            nan_rows = grp.loc[big_gaps].copy()
            nan_rows[time_col] = nan_rows[time_col] - pd.Timedelta(seconds=1)
            for col in grp.columns:
                if col not in (time_col, group_col):
                    nan_rows[col] = float("nan")
            grp = pd.concat([grp, nan_rows]).sort_values(time_col).reset_index(drop=True)
        parts.append(grp)
    return pd.concat(parts, ignore_index=True)

# ------------------------------------------------------------------ #
# 競合プランデータ（関東・40A契約前提）
# ------------------------------------------------------------------ #
COMPETITOR_PLANS = [
    {"id": "cde",        "name": "CDエナジー",         "type": "tier",
     "base": 1107.60, "b1": 120, "b2": 300,
     "t1": 29.90, "t2": 35.59, "t3": 36.50,
     "fuel_adj": True,  "renewable": False, "note": "CDエナジーダイレクト ベーシックでんき"},
    {"id": "terasel",    "name": "TERASEL",            "type": "tier",
     "base": 1247.00, "b1": 120, "b2": 300,
     "t1": 29.80, "t2": 34.26, "t3": 35.64,
     "fuel_adj": True,  "renewable": False, "note": "超TERASELプラン"},
    {"id": "eneos",      "name": "ENEOSでんき",         "type": "tier",
     "base": 1247.00, "b1": 120, "b2": 300,
     "t1": 29.80, "t2": 34.85, "t3": 36.90,
     "fuel_adj": True,  "renewable": False, "note": "Vプラン"},
    {"id": "oct_green",  "name": "🌱オクトパスグリーン", "type": "tier",
     "base": 1180.00, "b1": 120, "b2": 300,
     "t1": 20.62, "t2": 25.29, "t3": 27.44,
     "fuel_adj": False, "renewable": True,  "note": "実質再エネ100%・燃調なし"},
    {"id": "oct_simple", "name": "🌱オクトパスシンプル", "type": "flat",
     "base": 0.0,     "flat_rate": 30.35,
     "fuel_adj": False, "renewable": True,  "note": "初年度12ヶ月限定・燃調なし"},
    {"id": "looop",      "name": "🌱Looop",             "type": "market",
     "base": 1148.36,
     "fuel_adj": False, "renewable": True,  "note": "市場連動型（2025年実績推計・all-in単価）"},
    {"id": "syn_day",    "name": "シン・エナジー昼型",   "type": "tod",
     "base": 753.60,  "day_rate": 20.05, "life_rate": 32.65, "night_rate": 22.98,
     "fuel_adj": True,  "renewable": False, "note": "生活フィットプラン昼型・30分データ使用"},
    {"id": "syn_night",  "name": "シン・エナジー夜型",   "type": "tod",
     "base": 753.60,  "day_rate": 26.25, "life_rate": 32.65, "night_rate": 18.88,
     "fuel_adj": True,  "renewable": False, "note": "生活フィットプラン夜型・30分データ使用"},
]

# Looop スマートタイムONE 2025年月別実績推計（all-in単価 円/kWh）
LOOOP_MONTHLY_RATES = {
    (2025, 4): 28.00, (2025, 5): 25.62, (2025, 6): 26.98,
    (2025, 7): 31.93, (2025, 8): 32.11, (2025, 9): 31.43,
    (2025, 10): 31.74, (2025, 11): 29.02, (2025, 12): 29.52,
}


def _calc_comp_plan_row(plan: dict, row: pd.Series, df_30min: pd.DataFrame):
    u = float(row["usage_kwh"])
    fuel = float(row["燃料費調整単価"]) if plan["fuel_adj"] else 0.0
    renene = float(row["再エネ賦課金単価"]) + float(row["負担軽減支援単価"])
    adj = fuel + renene

    if plan["type"] == "tier":
        t1 = min(u, plan["b1"]) * plan["t1"]
        t2 = min(max(u - plan["b1"], 0), plan["b2"] - plan["b1"]) * plan["t2"]
        t3 = max(u - plan["b2"], 0) * plan["t3"]
        return round(plan["base"] + t1 + t2 + t3 + u * adj)

    elif plan["type"] == "flat":
        return round(plan["base"] + u * (plan["flat_rate"] + adj))

    elif plan["type"] == "market":
        rate = LOOOP_MONTHLY_RATES.get((int(row["year"]), int(row["month"])))
        if rate is None:
            return None
        return round(plan["base"] + u * rate)

    elif plan["type"] == "tod":
        if df_30min.empty:
            return None
        bill_date = row["date"]
        bill_start = (bill_date - pd.DateOffset(months=1)).replace(day=9).date()
        bill_end = bill_date.replace(day=8).date()
        df_p = df_30min[
            (df_30min["_date"] >= bill_start) & (df_30min["_date"] <= bill_end)
        ].dropna(subset=["usage_kwh"])
        if df_p.empty:
            return None
        h = df_p["recorded_at"].dt.hour
        wd = df_p["recorded_at"].dt.dayofweek < 5
        day_mask  = (wd & (h >= 9) & (h < 16)) | (~wd & (h >= 8) & (h < 22))
        night_mask = (wd & ((h >= 23) | (h < 6))) | (~wd & ((h >= 22) | (h < 8)))
        life_mask  = ~day_mask & ~night_mask
        day_kwh   = df_p.loc[day_mask,   "usage_kwh"].sum()
        life_kwh  = df_p.loc[life_mask,  "usage_kwh"].sum()
        night_kwh = df_p.loc[night_mask, "usage_kwh"].sum()
        total_kwh = day_kwh + life_kwh + night_kwh
        usage_charge = (day_kwh * plan["day_rate"] + life_kwh * plan["life_rate"]
                        + night_kwh * plan["night_rate"])
        return round(plan["base"] + usage_charge + total_kwh * adj)

    return None


# ------------------------------------------------------------------ #
# 料金データ鮮度チェック（タブ描画前）
# ------------------------------------------------------------------ #
_tariff_check = load_tariff()
if not _tariff_check.empty:
    _last_tariff_ym = _tariff_check[["year", "month"]].tail(1).iloc[0]
    _last_tariff_date = pd.Timestamp(int(_last_tariff_ym["year"]), int(_last_tariff_ym["month"]), 1)
    _today_ts = pd.Timestamp.now(tz="Asia/Tokyo").tz_localize(None)
    # 現在の検針月（9日以降は当月、8日以前は前月）
    _cm = _today_ts.replace(day=1) if _today_ts.day >= 9 else (
        _today_ts.replace(day=1) - pd.offsets.MonthBegin(1))
    # データ残り2ヶ月を切ったら警告
    if (_last_tariff_date - _cm).days < 60:
        st.warning(
            "⚠️ **料金データの更新が必要です。** "
            f"tariff_data.csv の最終行は {int(_last_tariff_ym['year'])}年{int(_last_tariff_ym['month'])}月です。 "
            "新しい年度の **再エネ賦課金単価** および燃料費調整単価を設定してください。"
        )

# ------------------------------------------------------------------ #
# タブ
# ------------------------------------------------------------------ #
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["🔴 リアルタイム", "📅 日次", "📆 月次", "💴 料金", "💡 インサイト", "⚡ 会社比較"])

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

        # ギャップ箇所で線を途切れさせる（デバイスごとに独立処理）
        sb_part = df_combined[df_combined["device_name"] != "家全体 (Enevisata)"].copy()
        ene_part = df_combined[df_combined["device_name"] == "家全体 (Enevisata)"].copy()
        sb_part = insert_gaps(sb_part, "recorded_at", "device_name", max_gap_minutes=60)
        if not ene_part.empty:
            ene_part = insert_gaps(ene_part, "recorded_at", "device_name", max_gap_minutes=60)
        df_combined = pd.concat([sb_part, ene_part]).sort_values("recorded_at").reset_index(drop=True)

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
            yaxis=dict(fixedrange=False),
            xaxis=dict(
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
        st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)

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
            yaxis=dict(fixedrange=False),
            xaxis=dict(
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
        st.plotly_chart(fig_ed, use_container_width=True, config=PLOTLY_CONFIG)

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
            color_discrete_sequence=["#00d4ff","#ffb300","#00e676","#ff4444","#7c4dff","#ff6d00","#00bfa5"],
        )
        fig_em.update_layout(
            height=550,
            legend_title_text="年",
            yaxis=dict(fixedrange=False),
            xaxis=dict(
                range=[df_em["date"].min(), df_em["date"].max()],
                rangeselector=dict(
                    buttons=[
                        dict(count=6,  label="6ヶ月", step="month", stepmode="backward"),
                        dict(count=1,  label="1年",   step="year",  stepmode="backward"),
                        dict(step="all", label="全期間"),
                    ]
                ),
            ),
        )
        st.plotly_chart(fig_em, use_container_width=True, config=PLOTLY_CONFIG)

# ------------------------------------------------------------------ #
# タブ4：料金（単価 + 計算 統合）
# ------------------------------------------------------------------ #
with tab4:
    _t4_t = load_tariff()
    _t4_daily = load_enevisata_daily()
    _t4_usage = _get_billing_usage(_t4_daily, load_enevisata_monthly())

    # 料金計算（使用量×単価）
    _t4_res = None
    _t4_ym = []
    if not _t4_usage.empty and not _t4_t.empty:
        _t4_raw = _t4_usage.merge(_t4_t[
            ["year", "month", "基本料金", "第1段階単価", "第2段階単価", "第3段階単価",
             "燃料費調整単価", "再エネ賦課金単価", "負担軽減支援単価", "一括受電割引率"]
        ], on=["year", "month"], how="inner")

        if _t4_raw.empty:
            st.warning("使用量データと単価データを照合できませんでした。")
            st.caption(f"使用量データ年月範囲: {_t4_usage['year'].min()}/{_t4_usage['month'].min()} 〜 {_t4_usage['year'].max()}/{_t4_usage['month'].max()}")
        else:
            def _calc_comp(row):
                u = int(row["usage_kwh"])
                t1 = min(u, 120) * row["第1段階単価"]
                t2 = min(max(u - 120, 0), 180) * row["第2段階単価"]
                t3 = max(u - 300, 0) * row["第3段階単価"]
                base = row["基本料金"] + t1 + t2 + t3 + u * row["燃料費調整単価"]
                discount = base * row["一括受電割引率"]
                reene = u * row["再エネ賦課金単価"]
                support = u * row["負担軽減支援単価"]
                return pd.Series({
                    "使用量 (kWh)": round(u, 1),
                    "基本料金": round(row["基本料金"]),
                    "電力量料金": round(t1 + t2 + t3),
                    "燃料費調整額": round(u * row["燃料費調整単価"]),
                    "一括受電割引": round(-discount),
                    "再エネ賦課金": round(reene),
                    "負担軽減支援": round(u * row["負担軽減支援単価"]),
                    "推定料金 (円)": round(base - discount + reene + support),
                })

            _t4_res = pd.concat([_t4_raw[["date", "year", "month"]], _t4_raw.apply(_calc_comp, axis=1)], axis=1)
            _t4_res = _t4_res.drop_duplicates(subset=["year", "month"]).sort_values("date").reset_index(drop=True)
            _t4_res["年月"] = _t4_res["date"].dt.strftime("%Y年%m月")
            _t4_ym = _t4_res["年月"].tolist()

    # ── グラフ①：積み上げ面グラフ（料金構成） ──
    if _t4_res is not None:
        st.subheader("月次推定料金（料金構成）")
        st.caption("※ 検針日（毎月9日）を基準に集計。実際の明細と若干異なる場合があります。")

        _POS = [("基本料金", "rgba(29,78,216,0.72)"), ("電力量料金", "rgba(59,130,246,0.72)"), ("再エネ賦課金", "rgba(147,197,253,0.68)")]
        _NEG = [("燃料費調整額", "rgba(180,83,9,0.68)"), ("一括受電割引", "rgba(245,158,11,0.65)"), ("負担軽減支援", "rgba(253,230,138,0.62)")]

        _fig_area = go.Figure()
        for _n, _c in _POS:
            _fig_area.add_trace(go.Scatter(
                x=_t4_ym, y=_t4_res[_n].tolist(),
                name=_n, stackgroup="pos", mode="none", fillcolor=_c,
                hovertemplate="%{y:,.0f} 円<extra>" + _n + "</extra>",
            ))
        for _n, _c in _NEG:
            if _t4_res[_n].abs().sum() > 0:
                _fig_area.add_trace(go.Scatter(
                    x=_t4_ym, y=_t4_res[_n].tolist(),
                    name=_n, stackgroup="neg", mode="none", fillcolor=_c,
                    hovertemplate="%{y:,.0f} 円<extra>" + _n + "</extra>",
                ))
        _fig_area.add_trace(go.Scatter(
            x=_t4_ym, y=_t4_res["推定料金 (円)"].tolist(),
            name="推定料金合計", mode="lines+markers",
            line=dict(color="rgba(226,232,240,0.92)", width=2, dash="dot"),
            marker=dict(size=4, color="rgba(226,232,240,0.92)"),
            hovertemplate="合計: %{y:,.0f} 円<extra>推定料金合計</extra>",
        ))
        _fig_area.update_layout(
            height=450,
            hovermode="x unified",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
            xaxis=dict(tickangle=-45, categoryorder="array", categoryarray=_t4_ym),
            yaxis=dict(fixedrange=False, title="推定料金 (円)"),
        )
        st.plotly_chart(_fig_area, use_container_width=True, config=PLOTLY_CONFIG)

    # ── グラフ②：折れ線グラフ（料金単価推移） ──
    if not _t4_t.empty:
        st.subheader("月次単価推移")
        _t4_ts = _t4_t.sort_values("date")
        _t4_ymt = _t4_ts["年月"].tolist()
        _fig_t4 = px.line(
            _t4_ts.melt(id_vars=["date", "年月"], value_vars=[c for c in CHART_COLS if c in _t4_t.columns],
                        var_name="項目", value_name="単価"),
            x="年月", y="単価", color="項目", markers=True,
            labels={"年月": "年月", "単価": "単価 (円/kWh)", "項目": "項目"},
            category_orders={"年月": _t4_ymt},
            color_discrete_sequence=["#3b82f6", "#f59e0b", "#93c5fd"],
        )
        _fig_t4.update_layout(
            height=380,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
            xaxis=dict(tickangle=-45),
        )
        st.plotly_chart(_fig_t4, use_container_width=True, config=PLOTLY_CONFIG)

    # ── テーブル（下部） ──
    if _t4_res is not None:
        st.subheader("料金内訳")
        st.dataframe(
            _t4_res[["年月", "使用量 (kWh)", "基本料金", "電力量料金", "燃料費調整額",
                      "一括受電割引", "再エネ賦課金", "負担軽減支援", "推定料金 (円)"]],
            use_container_width=True, hide_index=True,
        )

    if not _t4_t.empty:
        st.subheader("月次単価一覧")
        _t4_disp_cols = [c for c in ALL_COL_LABELS if c in _t4_t.columns]
        st.dataframe(
            _t4_t.sort_values("date")[["年月"] + _t4_disp_cols].rename(columns=ALL_COL_LABELS),
            use_container_width=True, hide_index=True,
        )

# ------------------------------------------------------------------ #
# ユーティリティ：料金計算（インサイトタブでも使用）
# ------------------------------------------------------------------ #
def _calc_bill_from_kwh(u_float: float, row: pd.Series) -> int:
    u = int(u_float)
    t1 = min(u, 120) * row["第1段階単価"]
    t2 = min(max(u - 120, 0), 180) * row["第2段階単価"]
    t3 = max(u - 300, 0) * row["第3段階単価"]
    base = row["基本料金"] + t1 + t2 + t3 + u * row["燃料費調整単価"]
    discount = base * row["一括受電割引率"]
    reene = u * row["再エネ賦課金単価"]
    support = u * row["負担軽減支援単価"]
    return round(base - discount + reene + support)


def _aggregate_to_billing_months(df_daily: pd.DataFrame) -> pd.DataFrame:
    df = df_daily.copy()
    df["bill_month"] = df["recorded_date"].apply(
        lambda d: d.replace(day=1) if d.day >= 9 else (d.replace(day=1) - pd.offsets.MonthBegin(1))
    )
    return (
        df.groupby("bill_month")["usage_kwh"]
        .sum()
        .reset_index()
        .rename(columns={"bill_month": "date"})
        .assign(year=lambda x: x["date"].dt.year, month=lambda x: x["date"].dt.month)
    )


# ------------------------------------------------------------------ #
# タブ5：インサイト
# ------------------------------------------------------------------ #
with tab5:
    _df_t = load_tariff()
    _df_d = load_enevisata_daily()
    _df_em = load_enevisata_monthly()
    _df_30 = load_enevisata_30min(hours)
    _df_sw = load_switchbot(hours)

    # 現在の検針期間を事前計算（上段全体で共用）
    _now_ts = pd.Timestamp.now(tz="Asia/Tokyo")
    _today = _now_ts.date()
    if _today.day >= 9:
        _bill_start_date = _today.replace(day=9)
        _cur_key = (_now_ts.year, _now_ts.month)
    else:
        _prev_m_d = (_today.replace(day=1) - timedelta(days=1))
        _bill_start_date = _prev_m_d.replace(day=9)
        _cur_key = (_prev_m_d.year, _prev_m_d.month)
    if _bill_start_date.month == 12:
        _bill_end_date = _bill_start_date.replace(year=_bill_start_date.year + 1, month=1, day=8)
    else:
        _bill_end_date = _bill_start_date.replace(month=_bill_start_date.month + 1, day=8)
    _bill_days = (_bill_end_date - _bill_start_date).days + 1
    _days_elapsed = (_today - _bill_start_date).days + 1
    _days_remaining = _bill_days - _days_elapsed
    _period_str = f"{_bill_start_date.month}/{_bill_start_date.day}〜{_bill_end_date.month}/{_bill_end_date.day}"
    _prev_end_date = _bill_start_date - timedelta(days=1)
    _prev_start_month = 12 if _bill_start_date.month == 1 else _bill_start_date.month - 1
    _prev_period_str = f"{_prev_start_month}/9〜{_prev_end_date.month}/{_prev_end_date.day}"
    _cur_bill_month_ts = pd.Timestamp(_bill_start_date.replace(day=1))

    # ================================================================ #
    # 上段: 左＝①　右＝②
    # ================================================================ #
    _top_left, _top_right = st.columns([1, 1])

    with _top_left:
        # ① 月別使用量と今月予測
        st.subheader("① 月別使用量と今月予測")
        if not _df_d.empty and not _df_t.empty:
            _usage = _get_billing_usage(_df_d, _df_em)
            _billed = _usage.merge(
                _df_t[["year", "month", "基本料金", "第1段階単価", "第2段階単価", "第3段階単価",
                       "燃料費調整単価", "再エネ賦課金単価", "負担軽減支援単価", "一括受電割引率"]],
                on=["year", "month"], how="inner"
            ).drop_duplicates(subset=["year", "month"]).sort_values("date")

            def _tiers(row):
                u = int(row["usage_kwh"])
                return pd.Series({
                    "第1段階": min(u, 120),
                    "第2段階": min(max(u - 120, 0), 180),
                    "第3段階": max(u - 300, 0),
                })

            _tier_df = pd.concat([_billed[["date"]], _billed.apply(_tiers, axis=1)], axis=1)
            _tier_df["年月"] = _tier_df["date"].dt.strftime("%Y年%m月")
            _tier_df = _tier_df.drop_duplicates(subset=["年月"])
            _ym_order = _tier_df["年月"].tolist()
            _ym_vals = _tier_df["年月"].tolist()
            _y1 = _tier_df["第1段階"].tolist()
            _y2 = (_tier_df["第1段階"] + _tier_df["第2段階"]).tolist()
            _y3 = (_tier_df["第1段階"] + _tier_df["第2段階"] + _tier_df["第3段階"]).tolist()
            import numpy as np
            _cd = np.column_stack([
                _tier_df["第3段階"].values,
                _tier_df["第2段階"].values,
                _tier_df["第1段階"].values,
                (_tier_df["第1段階"] + _tier_df["第2段階"] + _tier_df["第3段階"]).values,
            ])
            fig_tier = go.Figure()
            # 視覚トレース: 累積値 + fill で積み上げ表示
            fig_tier.add_trace(go.Scatter(
                x=_ym_vals, y=_y1, name="第1段階", mode="none",
                fill="tozeroy", fillcolor="#004e64", line=dict(width=0),
                hoverinfo="skip",
            ))
            fig_tier.add_trace(go.Scatter(
                x=_ym_vals, y=_y2, name="第2段階", mode="none",
                fill="tonexty", fillcolor="#0096c7", line=dict(width=0),
                hoverinfo="skip",
            ))
            fig_tier.add_trace(go.Scatter(
                x=_ym_vals, y=_y3, name="第3段階", mode="none",
                fill="tonexty", fillcolor="#00d4ff", line=dict(width=0),
                hoverinfo="skip",
            ))
            # 単一ホバートレース: customdata で第3→第2→第1→合計の順に表示
            fig_tier.add_trace(go.Scatter(
                x=_ym_vals, y=_y3,
                mode="markers", marker=dict(color="rgba(0,0,0,0)", size=8),
                customdata=_cd,
                hovertemplate=(
                    "第3段階: %{customdata[0]:.0f} kWh<br>"
                    "第2段階: %{customdata[1]:.0f} kWh<br>"
                    "第1段階: %{customdata[2]:.0f} kWh<br>"
                    "<b>合計: %{customdata[3]:.0f} kWh</b>"
                    "<extra></extra>"
                ),
                showlegend=False,
            ))
            _total_line = _tier_df[["年月"]].copy()
            _total_line["合計"] = _tier_df[["第1段階", "第2段階", "第3段階"]].sum(axis=1)
            fig_tier.update_layout(
                height=300,
                margin=dict(t=55, b=10),
                legend=dict(orientation="h", y=1.0, x=0, yanchor="bottom"),
                xaxis=dict(tickangle=-45, categoryorder="array", categoryarray=_ym_order),
                hovermode="x unified",
            )
            st.plotly_chart(fig_tier, use_container_width=True, config=PLOTLY_CONFIG)

            # 今月の現在値・予測値
            _cur_period = _df_d[
                (_df_d["recorded_date"] >= pd.Timestamp(_bill_start_date)) &
                (_df_d["cumulative_kwh"].notna())
            ]
            _cur_kwh = float(_cur_period["cumulative_kwh"].iloc[-1]) if not _cur_period.empty else 0.0
            _proj_kwh = _cur_kwh + (_cur_kwh / max(_days_elapsed, 1)) * _days_remaining
            _trow_df = _df_t[(_df_t["year"] == _cur_key[0]) & (_df_t["month"] == _cur_key[1])]
            _trow = _trow_df.iloc[0] if not _trow_df.empty else _df_t.iloc[-1]

            # 前回の完了済み検針期間
            _billed_done = _billed[_billed["date"] < _cur_bill_month_ts]
            _latest = _billed_done.iloc[-1] if not _billed_done.empty else _billed.iloc[-1]
            _latest_u = int(_latest["usage_kwh"])

            # 今月のメトリクス（2×2）
            _r1c1, _r1c2 = st.columns(2)
            _r2c1, _r2c2 = st.columns(2)
            _r1c1.metric("現在の使用量", f"{_cur_kwh:.1f} kWh", f"経過 {_days_elapsed} 日")
            _r1c2.metric("月末予測使用量", f"{int(_proj_kwh)} kWh", f"残 {_days_remaining} 日")
            _r2c1.metric("月末予測料金", f"{_calc_bill_from_kwh(_proj_kwh, _trow):,} 円")
            _r2c2.metric("月末予測CO2", f"{_proj_kwh * CO2_KG_PER_KWH:.1f} kg-CO2")
            st.caption(
                f"参考（一人当たり月間平均）: "
                f"家庭用電力 {CO2_PERCAPITA_ELEC_KG_YEAR/12:.0f} kg-CO2　"
                f"／　日本全部門 {CO2_PERCAPITA_TOTAL_KG_YEAR/12:.0f} kg-CO2"
            )

            # ステータス（今回の着地予測 + 前回比較）
            _prev_stage = 3 if _latest_u > 300 else 2 if _latest_u > 120 else 1
            _proj_stage = 3 if _proj_kwh > 300 else 2 if _proj_kwh > 120 else 1
            _stage_range = {1: "〜120 kWh", 2: "121〜300 kWh", 3: "301 kWh〜"}
            _status_msg = (
                f"今回の検針期間（{_period_str}）は **{int(_proj_kwh)} kWh** の見込みで、"
                f"**第{_proj_stage}段階**（{_stage_range[_proj_stage]}）に着地しそうです。"
                f"　前回（{_prev_period_str}）は {_latest_u} kWh・第{_prev_stage}段階でした。"
            )
            if _proj_stage == 1:
                st.success(_status_msg)
            else:
                st.info(_status_msg)

            # 削減シミュレーション（予測値ベース）
            st.markdown(f"**削減シミュレーション**（{_period_str} 予測 {int(_proj_kwh)} kWh ベース）")
            _max_reduce = max(int(_proj_kwh - _cur_kwh), 0)
            _delta = st.slider(
                "月末予測からの変化 (kWh)　　増加 ← 0 → 削減",
                -20, _max_reduce, 0, key="delta_slider",
            )
            _sim_kwh = max(_proj_kwh - _delta, 0)
            _proj_cost = _calc_bill_from_kwh(_proj_kwh, _trow)
            _sim_cost = _calc_bill_from_kwh(_sim_kwh, _trow)
            _cost_diff = _sim_cost - _proj_cost
            _co2_diff = (_sim_kwh - _proj_kwh) * CO2_KG_PER_KWH
            _s1, _s2, _s3 = st.columns(3)
            _s1.metric("調整後の使用量", f"{int(_sim_kwh)} kWh",
                       delta=f"{-_delta:+d} kWh", delta_color="inverse")
            _s2.metric("推定料金の変化", f"{_sim_cost:,} 円",
                       delta=f"{_cost_diff:+,} 円", delta_color="inverse")
            _s3.metric("CO2の変化", f"{_sim_kwh * CO2_KG_PER_KWH:.1f} kg-CO2",
                       delta=f"{_co2_diff:+.1f} kg-CO2", delta_color="inverse")
        else:
            st.info("データが不足しています。")

    with _top_right:
        # ② 時間帯別使用パターン
        st.subheader("② 時間帯別使用パターン")
        if not _df_30.empty:
            _h = _df_30.copy()
            _h["hour"] = _h["recorded_at"].dt.hour
            _h["曜日種別"] = _h["recorded_at"].dt.weekday.apply(lambda x: "平日" if x < 5 else "休日")
            _ene_agg = (
                _h.groupby(["hour", "曜日種別"])["usage_kwh"]
                .agg(["mean", "count"])
                .reset_index()
            )
            _ene_agg["平均消費電力 (W)"] = (_ene_agg["mean"] * 2000).round(1)
            _ene_ok = _ene_agg[_ene_agg["count"] >= 5].copy()
            _ene_covered = set(_ene_ok["hour"].unique())

            _sw_hourly = None
            if not _df_sw.empty:
                _sw_tot = _df_sw.groupby("recorded_at")["power_w"].sum().reset_index()
                _sw_tot["hour"] = _sw_tot["recorded_at"].dt.hour
                _sw_tot["曜日種別"] = _sw_tot["recorded_at"].dt.weekday.apply(
                    lambda x: "平日" if x < 5 else "休日"
                )
                _sw_hourly = (
                    _sw_tot.groupby(["hour", "曜日種別"])["power_w"]
                    .mean().reset_index()
                    .rename(columns={"power_w": "平均消費電力 (W)"})
                )
                _sw_ov = _sw_hourly[_sw_hourly["hour"].isin(_ene_covered)]
                _merge_ov = _sw_ov.merge(
                    _ene_ok[["hour", "曜日種別", "平均消費電力 (W)"]].rename(
                        columns={"平均消費電力 (W)": "ene_w"}),
                    on=["hour", "曜日種別"], how="inner"
                )
                if not _merge_ov.empty:
                    _sw_mean = _merge_ov["平均消費電力 (W)"].mean()
                    _ene_mean = _merge_ov["ene_w"].mean()
                    _scale = _ene_mean / _sw_mean if _sw_mean > 0 else 1.0
                else:
                    _scale = 1.0
                _sw_hourly["平均消費電力 (W)"] = (_sw_hourly["平均消費電力 (W)"] * _scale).round(1)

            fig_hour = go.Figure()
            _day_colors = {"平日": "#00d4ff", "休日": "#ffb300"}
            for _dt in ["平日", "休日"]:
                _col = _day_colors[_dt]
                _ene_d = _ene_ok[_ene_ok["曜日種別"] == _dt].sort_values("hour")
                if _ene_d.empty:
                    continue
                fig_hour.add_trace(go.Scatter(
                    x=_ene_d["hour"], y=_ene_d["平均消費電力 (W)"],
                    mode="lines+markers", name=_dt,
                    line=dict(color=_col, dash="solid", width=2),
                    marker=dict(size=5),
                    legendgroup=_dt,
                    hovertemplate="%{y:.0f} W（Enevisata）<extra>" + _dt + "</extra>",
                ))
                if _sw_hourly is not None:
                    _last_h = int(_ene_d["hour"].max())
                    _sw_d = _sw_hourly[
                        (_sw_hourly["曜日種別"] == _dt) & (_sw_hourly["hour"] > _last_h)
                    ].sort_values("hour")
                    if not _sw_d.empty:
                        _conn = pd.concat([
                            _ene_d[_ene_d["hour"] == _last_h][["hour", "平均消費電力 (W)"]],
                            _sw_d[["hour", "平均消費電力 (W)"]],
                        ]).sort_values("hour")
                        fig_hour.add_trace(go.Scatter(
                            x=_conn["hour"], y=_conn["平均消費電力 (W)"],
                            mode="lines+markers", name=f"{_dt}（推算）",
                            line=dict(color=_col, dash="dot", width=1.5),
                            marker=dict(size=4, symbol="circle-open"),
                            legendgroup=_dt,
                            hovertemplate="%{y:.0f} W（SwitchBot推算）<extra>" + _dt + "</extra>",
                        ))
            fig_hour.update_layout(
                height=420,
                xaxis=dict(title="時刻 (時)", tickmode="linear", dtick=2, range=[-0.5, 23.5]),
                yaxis=dict(title="平均消費電力 (W)"),
                legend=dict(orientation="h", y=1.02, x=0),
            )
            st.plotly_chart(fig_hour, use_container_width=True, config=PLOTLY_CONFIG)
            st.caption("実線: Enevisata 30分データ。点線: SwitchBot合計をEnevisataにスケーリングした推算値。スマートライフプランでは23〜7時が割安。")
        else:
            st.info("30分データがありません。")

    st.divider()

    # ================================================================ #
    # 下段: 左＝③　右＝④
    # ================================================================ #
    _bot_left, _bot_right = st.columns([1, 1])

    with _bot_left:
        # ③ デバイス別推定年間コスト
        st.subheader("③ デバイス別推定年間コスト")
        if not _df_sw.empty and not _df_t.empty:
            _r = _df_t.iloc[-1]
            _marginal = (
                (_r["第2段階単価"] + _r["燃料費調整単価"]) * (1 - _r["一括受電割引率"])
                + _r["再エネ賦課金単価"] + _r["負担軽減支援単価"]
            )
            _avg_w = (
                _df_sw.groupby("device_name")["power_w"]
                .mean().reset_index()
                .rename(columns={"device_name": "機器名", "power_w": "平均消費電力 (W)"})
            )
            _avg_w["年間kWh"] = (_avg_w["平均消費電力 (W)"] / 1000 * 24 * 365).round(1)
            _avg_w["年間推定コスト (円)"] = (_avg_w["年間kWh"] * _marginal).round(0).astype(int)
            _avg_w["年間CO2排出量 (kg)"] = (_avg_w["年間kWh"] * CO2_KG_PER_KWH).round(1)

            fig_tm = px.treemap(
                _avg_w, path=["機器名"], values="年間kWh",
                color="年間kWh",
                color_continuous_scale=[[0, "#003a4a"], [0.5, "#007a9a"], [1, "#00d4ff"]],
                custom_data=["年間推定コスト (円)", "年間CO2排出量 (kg)"],
            )
            fig_tm.update_traces(
                texttemplate="<b>%{label}</b><br>%{value:.0f} kWh<br>¥%{customdata[0]:,.0f}<br>%{customdata[1]:.0f} kg-CO2",
                hovertemplate="%{label}<br>%{value:.1f} kWh<br>¥%{customdata[0]:,.0f}<br>%{customdata[1]:.1f} kg-CO2<extra></extra>",
                textfont=dict(size=11),
            )
            fig_tm.update_layout(
                height=420, coloraxis_showscale=False,
                margin=dict(t=10, l=0, r=0, b=0),
            )
            st.plotly_chart(fig_tm, use_container_width=True, config=PLOTLY_CONFIG)
            st.caption(
                f"※ 直近1ヶ月の平均消費電力から試算。実効限界単価: {_marginal:.1f}円/kWh（第2段階ベース）　"
                f"排出係数: {CO2_KG_PER_KWH} kg-CO2/kWh（東電EP 2022年度）　"
                f"参考（一人当たり年間平均）: 家庭用電力 {CO2_PERCAPITA_ELEC_KG_YEAR:,} kg-CO2　"
                f"／　日本全部門 {CO2_PERCAPITA_TOTAL_KG_YEAR:,} kg-CO2"
            )
        else:
            st.info("データが不足しています。")

    with _bot_right:
        # ④ 削減提案
        st.subheader("④ 削減提案")
        if not _df_sw.empty and not _df_t.empty:
            _r = _df_t.iloc[-1]
            _marginal_rate = (
                (_r["第2段階単価"] + _r["燃料費調整単価"]) * (1 - _r["一括受電割引率"])
                + _r["再エネ賦課金単価"] + _r["負担軽減支援単価"]
            )
            _avg_w_dev = _df_sw.groupby("device_name")["power_w"].mean()
            _period_hours = float(
                (_df_sw["recorded_at"].max() - _df_sw["recorded_at"].min()).total_seconds() / 3600
            )
            _sw_start_date = _df_sw["recorded_at"].min().date()
            _sw_end_date   = _df_sw["recorded_at"].max().date()
            if not _df_d.empty:
                _ed_period = _df_d[
                    (_df_d["recorded_date"].dt.date >= _sw_start_date) &
                    (_df_d["recorded_date"].dt.date <= _sw_end_date)
                ]
                _total_kwh = float(_ed_period["usage_kwh"].dropna().sum()) if not _ed_period.empty else None
            else:
                _total_kwh = None

            def _excess_saving_yen(excess_kwh: float) -> int:
                return int(max(excess_kwh, 0) * _marginal_rate)

            def _co2_kg(kwh: float) -> float:
                return round(kwh * CO2_KG_PER_KWH, 1)

            def _pct_of_total(kwh: float) -> str:
                if _total_kwh and _total_kwh > 0:
                    return f"{kwh / _total_kwh * 100:.1f}%"
                return "―"

            _DEVICE_INFO: dict[str, tuple[str, float, str]] = {
                "冷蔵庫":             ("設定温度を1段階上げる（強→中）・扉の開閉を減らす・詰め込みすぎない", 250, "省エネトップランナー基準・400Lクラス"),
                "トイレ":             ("便座ヒーターを「弱」または節電タイマーを設定する", 60, "省エネ型温水洗浄便座の目安"),
                "テレビ他":           ("画面輝度を下げる・視聴後は主電源をオフ・省エネモードを有効にする", 65, "43型4K液晶・1日4時間視聴の目安"),
                "ドライヤー":         ("タオルで十分に水気を取ってから使う・弱モードや温冷交互を活用する", 80, "毎日10分使用の目安"),
                "洗濯機":             ("乾燥は「低温」または「送風」コースを活用する・まとめ洗いで回数を削減する・乾燥まで使わない日を設ける", 250, "乾燥機能付きドラム式洗濯機の標準値"),
                "デスクライト":       ("ディスプレイ輝度を下げる・PCスリープを短く設定する・スタンドライトをLED化する", 120, "27インチ省エネディスプレイ＋LEDスタンドライトの目安"),
                "ベッド":             ("充電完了後はコンセントを抜く・充電タイマーやスマートプラグで自動オフを設定する", 5, "スマートフォン充電器（充電完了後すぐ抜く場合）の目安"),
                "玄関充電":           ("充電完了後はコンセントを抜く・スマートプラグで自動オフを設定する", 10, "スマートフォン充電器（待機電力含む）の目安"),
                "デスクチャージャー": ("充電完了後はコンセントを抜く・スマートプラグで自動オフを設定する", 10, "USB充電器（待機電力含む）の目安"),
                "ペンペン":           ("清掃頻度・スケジュールを見直す・使わない時間帯は充電台の電源をオフにする", 20, "ロボット掃除機の標準的な年間消費量"),
            }

            _proposals = []
            for _dev, (_tip, _bm_year, _bm_label) in _DEVICE_INFO.items():
                if _dev in _avg_w_dev.index:
                    _w = float(_avg_w_dev[_dev])
                    _kwh = _w * _period_hours / 1000
                    _kwh_year = _w * 24 * 365 / 1000
                    _excess_kwh = _kwh_year - _bm_year
                    _yen = _excess_saving_yen(_excess_kwh)
                    _proposals.append({
                        "機器": _dev, "avg_w": _w, "kwh": _kwh,
                        "kwh_year": _kwh_year, "bm_year": _bm_year,
                        "bm_label": _bm_label, "excess_kwh": _excess_kwh,
                        "tip": _tip, "yen": _yen,
                    })

            if not _df_30.empty:
                _sw_30 = (
                    _df_sw[["recorded_at", "device_name", "power_w"]]
                    .assign(ts30=lambda d: d["recorded_at"].dt.floor("30min"))
                    .groupby(["ts30", "device_name"])["power_w"].mean()
                    .reset_index()
                    .groupby("ts30")["power_w"].sum()
                    .reset_index()
                    .rename(columns={"ts30": "recorded_at", "power_w": "sb_total_w"})
                )
                _e30_copy = _df_30[["recorded_at", "usage_kwh"]].dropna().copy()
                _e30_copy["ene_w"] = _e30_copy["usage_kwh"] * 2000
                _gap_df = _e30_copy.merge(_sw_30, on="recorded_at", how="inner")
                _gap_df["unmonitored_w"] = (_gap_df["ene_w"] - _gap_df["sb_total_w"]).clip(lower=0)
                _gap_df["hour"] = _gap_df["recorded_at"].dt.hour
                _day_base_w = float(_gap_df[_gap_df["hour"].between(10, 17)]["unmonitored_w"].mean())
                _evening_w  = float(_gap_df[_gap_df["hour"].between(18, 22)]["unmonitored_w"].mean())
                _lighting_w = max(_evening_w - _day_base_w, 0)
                _evening_slots = len(_gap_df[_gap_df["hour"].between(18, 22)])
                _lighting_kwh = _lighting_w * _evening_slots * 0.5 / 1000
                if _lighting_w > 20:
                    _lighting_kwh_year = _lighting_w * 24 * 365 / 1000
                    _proposals.append({
                        "機器": "照明", "avg_w": _lighting_w, "kwh": _lighting_kwh,
                        "kwh_year": _lighting_kwh_year, "bm_year": 200,
                        "bm_label": "一般家庭の照明合計の目安",
                        "excess_kwh": _lighting_kwh_year - 200,
                        "tip": f"夜間(18〜23時)の未監視電力から照明が平均 {_lighting_w:.0f} W と推定されます。LED未交換の照明があれば交換で50〜80%削減可能です。使わない部屋の照明をこまめに消すことも有効です。",
                        "yen": _excess_saving_yen(_lighting_kwh_year - 200),
                    })

            if _total_kwh:
                _monitored_kwh = sum(p["kwh"] for p in _proposals)
                _ac_kwh = max(_total_kwh - _monitored_kwh, 0)
                if _ac_kwh > 0:
                    _ac_avg_w = _ac_kwh / _period_hours * 1000
                    _ac_kwh_year = _ac_avg_w * 24 * 365 / 1000
                    _ac_bm = 800 * 3
                    _proposals.append({
                        "機器": "エアコン（3台）", "avg_w": _ac_avg_w, "kwh": _ac_kwh,
                        "kwh_year": _ac_kwh_year, "bm_year": _ac_bm,
                        "bm_label": "エアコン3台・冷暖房合計の標準値",
                        "excess_kwh": _ac_kwh_year - _ac_bm,
                        "tip": f"全体から個別機器を差し引いた残余電力（{_ac_kwh:.1f} kWh）をエアコン3台等の未監視大型機器と推定します。設定温度を1℃緩める（冷房: 26→27℃、暖房: 20→19℃）と約10%削減できます。フィルター清掃（月1回）も効率維持に重要です。",
                        "yen": _excess_saving_yen(_ac_kwh_year - _ac_bm),
                    })

            _proposals.sort(key=lambda x: x.get("excess_kwh", float("-inf")), reverse=True)

            if _proposals:
                st.caption(
                    "※ 直近1ヶ月の実績データをもとにした推定です。"
                    + (f"　集計期間の合計使用量: {_total_kwh:.1f} kWh　（{_co2_kg(_total_kwh):.0f} kg-CO2）" if _total_kwh else "")
                    + f"　排出係数: {CO2_KG_PER_KWH} kg-CO2/kWh（東電EP 2022年度）　"
                    + f"参考（一人当たり年間平均）: 家庭用電力 {CO2_PERCAPITA_ELEC_KG_YEAR:,} kg-CO2　"
                    + f"／　日本全部門 {CO2_PERCAPITA_TOTAL_KG_YEAR:,} kg-CO2"
                )
                _bm_rows = [p for p in _proposals if p.get("bm_year") and p.get("kwh_year")]
                if _bm_rows:
                    _sc_df = pd.DataFrame({
                        "機器":        [p["機器"] for p in _bm_rows],
                        "ベンチマーク": [p["bm_year"] for p in _bm_rows],
                        "実測":        [round(p["kwh_year"], 1) for p in _bm_rows],
                        "超過":        [max(p["excess_kwh"], 0) for p in _bm_rows],
                    })

                    def _make_scatter(df, axis_max, title):
                        fig = go.Figure()
                        fig.add_trace(go.Scatter(
                            x=[0, axis_max], y=[0, axis_max],
                            mode="lines",
                            line=dict(color="rgba(0,212,255,0.25)", width=1, dash="dot"),
                            showlegend=False, hoverinfo="skip",
                        ))
                        fig.add_trace(go.Scatter(
                            x=df["ベンチマーク"], y=df["実測"],
                            mode="markers+text",
                            marker=dict(
                                size=14,
                                color=df["超過"],
                                colorscale=[[0, "#003a5a"], [1, "#00d4ff"]],
                                line=dict(color="#040810", width=1),
                                showscale=False,
                            ),
                            text=df["機器"],
                            textposition="top center",
                            textfont=dict(size=10, color="#c8e0f0"),
                            customdata=df[["実測", "ベンチマーク", "超過"]].values,
                            hovertemplate=(
                                "<b>%{text}</b><br>"
                                "実測: %{customdata[0]:.0f} kWh/年<br>"
                                "ベンチマーク: %{customdata[1]:.0f} kWh/年<br>"
                                "超過: %{customdata[2]:.0f} kWh/年<extra></extra>"
                            ),
                            showlegend=False,
                        ))
                        fig.update_layout(
                            height=300,
                            xaxis=dict(title="ベンチマーク (kWh/年)", range=[0, axis_max]),
                            yaxis=dict(title="実測 (kWh/年)", range=[0, axis_max]),
                            margin=dict(t=30, l=50, r=10, b=40),
                            title=dict(text=title, font=dict(size=12, color="#4a8fa8"), x=0),
                        )
                        return fig

                    _ax_max_full = _sc_df[["ベンチマーク", "実測"]].max().max() * 1.15
                    st.plotly_chart(
                        _make_scatter(_sc_df, _ax_max_full, "全機器"),
                        use_container_width=True, config=PLOTLY_CONFIG,
                    )
                    _ZOOM = 500
                    _sc_zoom = _sc_df[
                        (_sc_df["ベンチマーク"] <= _ZOOM) & (_sc_df["実測"] <= _ZOOM)
                    ]
                    if not _sc_zoom.empty:
                        st.plotly_chart(
                            _make_scatter(_sc_zoom, _ZOOM, f"拡大（〜{_ZOOM} kWh）"),
                            use_container_width=True, config=PLOTLY_CONFIG,
                        )
                    st.caption("点が対角線より上＝ベンチマーク超過。色が濃いほど超過量が大きい。")

                for _p in _proposals:
                    _kwh_str = f"{_p['kwh']:.1f} kWh"
                    _pct_str = _pct_of_total(_p["kwh"])
                    _excess = _p.get("excess_kwh")
                    _excess_str = (
                        f"ベンチマーク比 **+{_excess:.0f} kWh/年** 超過 ⚠️" if _excess and _excess > 0
                        else "ベンチマーク以内 ✅" if _excess is not None else ""
                    )
                    _yen_str = f"{_p['yen']:,} 円/年" if _p["yen"] > 0 else "―"
                    _co2_excess_str = (
                        f"{_co2_kg(_excess):.1f} kg-CO2/年" if _excess and _excess > 0 else "―"
                    )
                    with st.expander(
                        f"**{_p['機器']}** — {_kwh_str}（全体の {_pct_str}）　ベンチマーク超過分節約 {_yen_str}"
                    ):
                        c1, c2, c3, c4 = st.columns(4)
                        c1.metric("集計期間の使用量", _kwh_str)
                        c2.metric("全体に占める割合", _pct_str)
                        c3.metric("ベンチマーク超過分節約", _yen_str)
                        c4.metric("削減可能CO2", _co2_excess_str)
                        if _p.get("bm_year"):
                            st.markdown(
                                f"**年間換算**: {_p['kwh_year']:.0f} kWh　（{_co2_kg(_p['kwh_year']):.0f} kg-CO2）　／　"
                                f"**ベンチマーク**: {_p['bm_year']} kWh（{_p['bm_label']}）　{_excess_str}"
                            )
                        st.write(_p["tip"])
            else:
                st.info("削減提案を生成するためのデータが不足しています。")
        else:
            st.info("削減提案を生成するためのデータが不足しています。")

# ------------------------------------------------------------------ #
# タブ6：会社比較
# ------------------------------------------------------------------ #
with tab6:
    _t6_d  = load_enevisata_daily()
    _t6_em = load_enevisata_monthly()
    _t6_t  = load_tariff()
    _t6_30 = load_enevisata_30min_all()

    _t6_usage = _get_billing_usage(_t6_d, _t6_em)

    if _t6_usage.empty or _t6_t.empty:
        st.info("使用量・料金データが不足しています。")
    else:
        _t6_billed = (
            _t6_usage
            .merge(
                _t6_t[["year", "month", "基本料金", "第1段階単価", "第2段階単価", "第3段階単価",
                        "燃料費調整単価", "再エネ賦課金単価", "負担軽減支援単価", "一括受電割引率"]],
                on=["year", "month"], how="inner",
            )
            .drop_duplicates(subset=["year", "month"])
            .sort_values("date")
            .reset_index(drop=True)
        )

        if _t6_billed.empty:
            st.info("料金データとの突合ができません。")
        else:
            # 現在のTEPCO料金
            _t6_billed["現在(TEPCO)"] = _t6_billed.apply(
                lambda r: _calc_bill_from_kwh(r["usage_kwh"], r), axis=1
            )
            # 競合プラン料金
            for _cp in COMPETITOR_PLANS:
                _t6_billed[_cp["name"]] = _t6_billed.apply(
                    lambda r, p=_cp: _calc_comp_plan_row(p, r, _t6_30), axis=1
                )

            _t6_billed["年月"] = _t6_billed["date"].dt.strftime("%Y年%m月")
            _ym6 = _t6_billed["年月"].tolist()
            _all_plans = ["現在(TEPCO)"] + [p["name"] for p in COMPETITOR_PLANS]

            # ── グラフ：月別推定料金比較 ──
            st.subheader("月別推定料金比較")
            _t6_long = (
                _t6_billed
                .melt(id_vars=["年月"], value_vars=_all_plans,
                      var_name="プラン", value_name="推定料金(円)")
                .dropna(subset=["推定料金(円)"])
            )
            _PLAN_COLORS = {
                "現在(TEPCO)":          "#00d4ff",
                "CDエナジー":           "#3b82f6",
                "TERASEL":              "#818cf8",
                "ENEOSでんき":          "#60a5fa",
                "🌱オクトパスグリーン": "#34d399",
                "🌱オクトパスシンプル": "#6ee7b7",
                "🌱Looop":              "#a3e635",
                "シン・エナジー昼型":   "#fbbf24",
                "シン・エナジー夜型":   "#f97316",
            }
            _fig6 = px.line(
                _t6_long, x="年月", y="推定料金(円)", color="プラン",
                markers=True,
                color_discrete_map=_PLAN_COLORS,
                category_orders={"年月": _ym6},
                labels={"推定料金(円)": "推定料金 (円)"},
            )
            _fig6.update_traces(selector=dict(name="現在(TEPCO)"),
                                line=dict(width=3), marker=dict(size=6))
            _fig6.update_layout(
                height=480,
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
                xaxis=dict(tickangle=-45),
                yaxis=dict(title="推定料金 (円)"),
            )
            st.plotly_chart(_fig6, use_container_width=True, config=PLOTLY_CONFIG)

            # ── 節約ポテンシャル表 ──
            st.subheader("節約ポテンシャル（データのある全月合計）")
            _tepco_total = int(_t6_billed["現在(TEPCO)"].sum())
            _n_months = len(_t6_billed)
            _rows6 = []
            for _cp in COMPETITOR_PLANS:
                _col = _cp["name"]
                _valid = _t6_billed[_col].dropna()
                if _valid.empty:
                    continue
                _comp_total = int(_valid.sum())
                _n_valid = len(_valid)
                _tepco_same = int(_t6_billed.loc[_valid.index, "現在(TEPCO)"].sum())
                _saving = _tepco_same - _comp_total
                _rows6.append({
                    "プラン":           _col,
                    "再エネ":           "🌱" if _cp["renewable"] else "",
                    "対象月数":         _n_valid,
                    "TEPCO合計(円)":    f"{_tepco_same:,}",
                    "他社合計(円)":     f"{_comp_total:,}",
                    "節約額(円)":       f"{_saving:+,}",
                    "備考":             _cp["note"],
                })
            st.dataframe(
                pd.DataFrame(_rows6),
                use_container_width=True, hide_index=True,
            )

            st.caption(
                "※ 競合他社の燃料費調整額はTEPCOの実績値で近似。"
                "Looopは2025年実績推計値（対象外月はN/A）。"
                "シン・エナジーは30分データのある月のみ計算。"
                "現在(TEPCO)には一括受電割引（8%）を含む。他社には適用なし。"
            )
