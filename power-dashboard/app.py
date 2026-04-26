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
# タブ
# ------------------------------------------------------------------ #
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["リアルタイム", "日次", "月次", "料金単価", "料金計算", "インサイト"])

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
            color_discrete_sequence=px.colors.qualitative.Set2,
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
# タブ4：料金単価
# ------------------------------------------------------------------ #
with tab4:
    df_t = load_tariff()
    if df_t.empty:
        st.info("単価データがありません。")
    else:
        display_cols = [c for c in ALL_COL_LABELS if c in df_t.columns]
        display_df = df_t[["年月"] + display_cols].rename(columns=ALL_COL_LABELS)
        st.subheader("月次単価一覧")
        st.dataframe(display_df, use_container_width=True, hide_index=True)

        fig_t = px.line(
            df_t.melt(id_vars=["date", "年月"], value_vars=[c for c in CHART_COLS if c in df_t.columns],
                      var_name="項目", value_name="単価"),
            x="date",
            y="単価",
            color="項目",
            markers=True,
            labels={"date": "年月", "単価": "単価 (円)", "項目": "項目"},
            color_discrete_sequence=px.colors.qualitative.Set2,
        )
        fig_t.update_layout(
            height=500,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
            xaxis=dict(tickformat="%Y年%m月"),
        )
        st.plotly_chart(fig_t, use_container_width=True, config=PLOTLY_CONFIG)

# ------------------------------------------------------------------ #
# タブ5：料金計算
# ------------------------------------------------------------------ #
with tab5:
    df_daily = load_enevisata_daily()
    df_tariff = load_tariff()

    if df_daily.empty:
        st.info("Enevisata 日次データがありません。")
    elif df_tariff.empty:
        st.info("単価データがありません。")
    else:
        # 日次→月次集計（検針期間は前月9日〜当月8日のため、8日を前月に割り当て）
        df_daily = df_daily.copy()
        df_daily["bill_month"] = df_daily["recorded_date"].apply(
            lambda d: d.replace(day=1) if d.day >= 9 else (d.replace(day=1) - pd.offsets.MonthBegin(1))
        )
        df_usage = (
            df_daily.groupby("bill_month")["usage_kwh"]
            .sum()
            .reset_index()
            .rename(columns={"bill_month": "date"})
        )
        df_usage["year"] = df_usage["date"].dt.year
        df_usage["month"] = df_usage["date"].dt.month

        df_bill = df_usage.merge(df_tariff[
            ["year", "month", "基本料金", "第1段階単価", "第2段階単価", "第3段階単価",
             "燃料費調整単価", "再エネ賦課金単価", "負担軽減支援単価", "一括受電割引率"]
        ], on=["year", "month"], how="inner")

        def calc_bill(row):
            u = int(row["usage_kwh"])  # 請求は小数切り捨て整数kWh
            t1 = min(u, 120) * row["第1段階単価"]
            t2 = min(max(u - 120, 0), 180) * row["第2段階単価"]
            t3 = max(u - 300, 0) * row["第3段階単価"]
            base = row["基本料金"] + t1 + t2 + t3 + u * row["燃料費調整単価"]
            discount = base * row["一括受電割引率"]
            reene = u * row["再エネ賦課金単価"]
            support = u * row["負担軽減支援単価"]
            return pd.Series({
                "使用量 (kWh)": round(u, 1),
                "電力量料金": round(t1 + t2 + t3),
                "燃料費調整額": round(u * row["燃料費調整単価"]),
                "一括受電割引": round(-discount),
                "再エネ賦課金": round(reene),
                "負担軽減支援": round(u * row["負担軽減支援単価"]),
                "推定料金 (円)": round(base - discount + reene + support),
            })

        df_result = pd.concat([df_bill[["date", "year", "month"]], df_bill.apply(calc_bill, axis=1)], axis=1)
        df_result["年月"] = df_result["date"].dt.strftime("%Y年%m月")

        st.subheader("月次推定料金")
        st.caption("※ 検針日（毎月9日）を基準に集計。実際の明細と若干異なる場合があります。")

        fig_bill = px.bar(
            df_result,
            x="date",
            y="推定料金 (円)",
            labels={"date": "年月", "推定料金 (円)": "推定料金 (円)"},
            color_discrete_sequence=["#4C78A8"],
        )
        fig_bill.update_layout(
            height=400,
            yaxis=dict(fixedrange=False),
            xaxis=dict(tickformat="%Y年%m月"),
        )
        st.plotly_chart(fig_bill, use_container_width=True, config=PLOTLY_CONFIG)

        st.subheader("内訳")
        st.dataframe(
            df_result[["年月", "使用量 (kWh)", "電力量料金", "燃料費調整額",
                        "一括受電割引", "再エネ賦課金", "負担軽減支援", "推定料金 (円)"]],
            use_container_width=True,
            hide_index=True,
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
# タブ6：インサイト
# ------------------------------------------------------------------ #
with tab6:
    _df_t = load_tariff()
    _df_d = load_enevisata_daily()
    _df_30 = load_enevisata_30min(hours)
    _df_sw = load_switchbot(hours)

    # ---------------------------------------------------------------- #
    # ① 段階別使用量 + 節約シミュレーター
    # ---------------------------------------------------------------- #
    st.subheader("① 段階別使用量と節約シミュレーター")

    if not _df_d.empty and not _df_t.empty:
        _usage = _aggregate_to_billing_months(_df_d)
        _billed = _usage.merge(
            _df_t[["year", "month", "基本料金", "第1段階単価", "第2段階単価", "第3段階単価",
                   "燃料費調整単価", "再エネ賦課金単価", "負担軽減支援単価", "一括受電割引率"]],
            on=["year", "month"], how="inner"
        )

        def _tiers(row):
            u = int(row["usage_kwh"])
            return pd.Series({
                "第1段階": min(u, 120),
                "第2段階": min(max(u - 120, 0), 180),
                "第3段階": max(u - 300, 0),
            })

        _tier_df = pd.concat([_billed[["date"]], _billed.apply(_tiers, axis=1)], axis=1)

        fig_tier = px.bar(
            _tier_df.melt(id_vars=["date"], var_name="段階", value_name="kWh"),
            x="date", y="kWh", color="段階",
            labels={"date": "年月", "kWh": "使用量 (kWh)"},
            color_discrete_map={"第1段階": "#2ecc71", "第2段階": "#f39c12", "第3段階": "#e74c3c"},
        )
        fig_tier.update_layout(height=350, xaxis=dict(tickformat="%Y年%m月"))
        st.plotly_chart(fig_tier, use_container_width=True, config=PLOTLY_CONFIG)

        _latest = _billed.iloc[-1]
        _latest_u = int(_latest["usage_kwh"])
        _latest_ym = _latest["date"].strftime("%Y年%m月")
        if _latest_u > 120:
            st.markdown(f"**節約シミュレーター（{_latest_ym}・{_latest_u}kWh）**")
            _max_reduce = _latest_u - 120
            _reduce = st.slider("削減量 (kWh)", 0, _max_reduce, min(10, _max_reduce), key="reduce_slider")
            _saving = _calc_bill_from_kwh(_latest_u, _latest) - _calc_bill_from_kwh(_latest_u - _reduce, _latest)
            _co2_save = _reduce * CO2_KG_PER_KWH
            _c1, _c2 = st.columns(2)
            _c1.metric(f"{_reduce}kWh削減すると", f"月 {_saving:,} 円節約",
                       f"{_latest_u} → {_latest_u - _reduce} kWh")
            _c2.metric("CO2削減量", f"{_co2_save:.1f} kg-CO2/月")
            st.caption(
                f"参考（一人当たり月間平均）: "
                f"家庭用電力 {CO2_PERCAPITA_ELEC_KG_YEAR/12:.0f} kg-CO2　"
                f"／　日本全部門 {CO2_PERCAPITA_TOTAL_KG_YEAR/12:.0f} kg-CO2"
            )
        else:
            st.success(f"{_latest_ym}は第1段階内（{_latest_u}kWh）に収まっています。")
    else:
        st.info("データが不足しています。")

    st.divider()

    # ---------------------------------------------------------------- #
    # ② デバイス別年間コスト推定
    # ---------------------------------------------------------------- #
    st.subheader("② デバイス別推定年間コスト")

    if not _df_sw.empty and not _df_t.empty:
        _r = _df_t.iloc[-1]
        _marginal = (
            (_r["第2段階単価"] + _r["燃料費調整単価"]) * (1 - _r["一括受電割引率"])
            + _r["再エネ賦課金単価"] + _r["負担軽減支援単価"]
        )
        _avg_w = (
            _df_sw.groupby("device_name")["power_w"]
            .mean()
            .reset_index()
            .rename(columns={"device_name": "機器名", "power_w": "平均消費電力 (W)"})
        )
        _avg_w["年間推定コスト (円)"] = (
            _avg_w["平均消費電力 (W)"] / 1000 * 24 * 365 * _marginal
        ).round(0).astype(int)
        _avg_w["年間CO2排出量 (kg)"] = (
            _avg_w["平均消費電力 (W)"] / 1000 * 24 * 365 * CO2_KG_PER_KWH
        ).round(1)
        _avg_w = _avg_w.sort_values("年間推定コスト (円)", ascending=False)

        _dev_tab1, _dev_tab2 = st.tabs(["年間推定コスト", "年間CO2排出量"])
        with _dev_tab1:
            fig_dev = px.bar(
                _avg_w, x="年間推定コスト (円)", y="機器名", orientation="h",
                labels={"機器名": ""},
                color_discrete_sequence=["#4C78A8"],
            )
            fig_dev.update_layout(height=max(300, len(_avg_w) * 35), yaxis=dict(categoryorder="total ascending"))
            st.plotly_chart(fig_dev, use_container_width=True, config=PLOTLY_CONFIG)
        with _dev_tab2:
            fig_co2 = px.bar(
                _avg_w.sort_values("年間CO2排出量 (kg)", ascending=False),
                x="年間CO2排出量 (kg)", y="機器名", orientation="h",
                labels={"機器名": ""},
                color_discrete_sequence=["#54A24B"],
            )
            fig_co2.update_layout(height=max(300, len(_avg_w) * 35), yaxis=dict(categoryorder="total ascending"))
            st.plotly_chart(fig_co2, use_container_width=True, config=PLOTLY_CONFIG)
        st.caption(
            f"※ 直近1ヶ月の平均消費電力から試算。実効限界単価: {_marginal:.1f}円/kWh（第2段階ベース）　"
            f"排出係数: {CO2_KG_PER_KWH} kg-CO2/kWh（東電EP 2022年度）　"
            f"参考（一人当たり年間平均）: 家庭用電力 {CO2_PERCAPITA_ELEC_KG_YEAR:,} kg-CO2　"
            f"／　日本全部門 {CO2_PERCAPITA_TOTAL_KG_YEAR:,} kg-CO2"
        )
        st.dataframe(
            _avg_w[["機器名", "平均消費電力 (W)", "年間推定コスト (円)", "年間CO2排出量 (kg)"]].reset_index(drop=True),
            use_container_width=True, hide_index=True,
        )
    else:
        st.info("データが不足しています。")

    st.divider()

    # ---------------------------------------------------------------- #
    # ③ 今月の電気代予測
    # ---------------------------------------------------------------- #
    st.subheader("③ 今月の電気代予測")

    if not _df_d.empty and not _df_t.empty:
        _now_ts = pd.Timestamp.now(tz="Asia/Tokyo")
        _today = _now_ts.date()

        # 検針日（9日）基準の当月開始・終了日
        if _today.day >= 9:
            _bill_start_date = _today.replace(day=9)
            _cur_key = (_now_ts.year, _now_ts.month)
        else:
            _prev_m = (_today.replace(day=1) - timedelta(days=1))
            _bill_start_date = _prev_m.replace(day=9)
            _cur_key = (_prev_m.year, _prev_m.month)
        if _bill_start_date.month == 12:
            _bill_end_date = _bill_start_date.replace(year=_bill_start_date.year + 1, month=1, day=8)
        else:
            _bill_end_date = _bill_start_date.replace(month=_bill_start_date.month + 1, day=8)
        _bill_days = (_bill_end_date - _bill_start_date).days + 1
        _days_elapsed = (_today - _bill_start_date).days + 1
        _days_remaining = _bill_days - _days_elapsed

        # 当月使用量: 検針開始日以降の最新 cumulative_kwh を使用（丸め誤差を避けるため）
        _cur_period = _df_d[
            (_df_d["recorded_date"] >= pd.Timestamp(_bill_start_date)) &
            (_df_d["cumulative_kwh"].notna())
        ]
        _cur_kwh = float(_cur_period["cumulative_kwh"].iloc[-1]) if not _cur_period.empty else 0.0
        _proj_kwh = _cur_kwh + (_cur_kwh / max(_days_elapsed, 1)) * _days_remaining

        _trow_df = _df_t[(_df_t["year"] == _cur_key[0]) & (_df_t["month"] == _cur_key[1])]
        _trow = _trow_df.iloc[0] if not _trow_df.empty else _df_t.iloc[-1]

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("現在の使用量", f"{_cur_kwh:.1f} kWh", f"経過 {_days_elapsed} 日")
        col2.metric("月末予測使用量", f"{int(_proj_kwh)} kWh", f"残 {_days_remaining} 日")
        col3.metric("月末予測料金", f"{_calc_bill_from_kwh(_proj_kwh, _trow):,} 円")
        col4.metric("月末予測CO2", f"{_proj_kwh * CO2_KG_PER_KWH:.1f} kg-CO2")
        st.caption(
            f"参考（一人当たり月間平均）: "
            f"家庭用電力 {CO2_PERCAPITA_ELEC_KG_YEAR/12:.0f} kg-CO2　"
            f"／　日本全部門 {CO2_PERCAPITA_TOTAL_KG_YEAR/12:.0f} kg-CO2"
        )

        if _proj_kwh > 300:
            st.warning(f"このペースだと第3段階（301kWh超）に入る見込みです。予測超過: {_proj_kwh - 300:.0f}kWh")
        elif _proj_kwh > 120:
            _save = _calc_bill_from_kwh(_proj_kwh, _trow) - _calc_bill_from_kwh(120, _trow)
            st.warning(f"第2段階に入る見込みです。120kWh以内に抑えると約 {_save:,} 円節約できます。")
        else:
            st.success("第1段階内に収まる見込みです。")
    else:
        st.info("データが不足しています。")

    st.divider()

    # ---------------------------------------------------------------- #
    # ④ 時間帯別使用パターン
    # ---------------------------------------------------------------- #
    st.subheader("④ 時間帯別使用パターン")

    if not _df_30.empty:
        _h = _df_30.copy()
        _h["hour"] = _h["recorded_at"].dt.hour
        _h["曜日種別"] = _h["recorded_at"].dt.weekday.apply(lambda x: "平日" if x < 5 else "休日")
        _hourly = (
            _h.groupby(["hour", "曜日種別"])["usage_kwh"]
            .mean()
            .reset_index()
        )
        _hourly["平均消費電力 (W)"] = (_hourly["usage_kwh"] * 2000).round(1)

        fig_hour = px.line(
            _hourly, x="hour", y="平均消費電力 (W)", color="曜日種別",
            markers=True,
            labels={"hour": "時刻 (時)", "平均消費電力 (W)": "平均消費電力 (W)"},
            color_discrete_map={"平日": "#4C78A8", "休日": "#F58518"},
        )
        fig_hour.update_layout(
            height=380,
            xaxis=dict(tickmode="linear", dtick=2, range=[-0.5, 23.5]),
        )
        st.plotly_chart(fig_hour, use_container_width=True, config=PLOTLY_CONFIG)
        st.caption("※ 直近1ヶ月の30分データの平均。スマートライフプランでは23〜7時が割安になります。")
    else:
        st.info("30分データがありません。")

    st.divider()

    # ---------------------------------------------------------------- #
    # ⑤ 削減提案
    # ---------------------------------------------------------------- #
    st.subheader("⑤ 削減提案")

    if not _df_sw.empty and not _df_t.empty:
        _r = _df_t.iloc[-1]
        _marginal_rate = (
            (_r["第2段階単価"] + _r["燃料費調整単価"]) * (1 - _r["一括受電割引率"])
            + _r["再エネ賦課金単価"] + _r["負担軽減支援単価"]
        )
        _avg_w_dev = _df_sw.groupby("device_name")["power_w"].mean()

        # データ期間（時間）を算出
        _period_hours = float(
            (_df_sw["recorded_at"].max() - _df_sw["recorded_at"].min()).total_seconds() / 3600
        )
        # 全体kWhはEnevisata日次データをSwitchBotと同期間でフィルタして使用
        # （30分データは当日分しか蓄積されないため日次を使用）
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

        # (tip, ベンチマーク年間kWh, ベンチマーク根拠)
        _DEVICE_INFO: dict[str, tuple[str, float, str]] = {
            "冷蔵庫":             (
                "設定温度を1段階上げる（強→中）・扉の開閉を減らす・詰め込みすぎない",
                250, "省エネトップランナー基準・400Lクラス"),
            "トイレ":             (
                "便座ヒーターを「弱」または節電タイマーを設定する",
                60, "省エネ型温水洗浄便座の目安"),
            "テレビ他":           (
                "画面輝度を下げる・視聴後は主電源をオフ・省エネモードを有効にする",
                65, "43型4K液晶・1日4時間視聴の目安"),
            "ドライヤー":         (
                "タオルで十分に水気を取ってから使う・弱モードや温冷交互を活用する",
                80, "毎日10分使用の目安"),
            "洗濯機":             (
                "乾燥は「低温」または「送風」コースを活用する・まとめ洗いで回数を削減する・乾燥まで使わない日を設ける",
                250, "乾燥機能付きドラム式洗濯機の標準値"),
            "デスクライト":       (
                "ディスプレイ輝度を下げる・PCスリープを短く設定する・スタンドライトをLED化する",
                120, "27インチ省エネディスプレイ＋LEDスタンドライトの目安"),
            "ベッド":             (
                "充電完了後はコンセントを抜く・充電タイマーやスマートプラグで自動オフを設定する",
                5, "スマートフォン充電器（充電完了後すぐ抜く場合）の目安"),
            "玄関充電":           (
                "充電完了後はコンセントを抜く・スマートプラグで自動オフを設定する",
                10, "スマートフォン充電器（待機電力含む）の目安"),
            "デスクチャージャー": (
                "充電完了後はコンセントを抜く・スマートプラグで自動オフを設定する",
                10, "USB充電器（待機電力含む）の目安"),
            "ペンペン":           (
                "清掃頻度・スケジュールを見直す・使わない時間帯は充電台の電源をオフにする",
                20, "ロボット掃除機の標準的な年間消費量"),
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

        # 未監視機器（エアコン・照明）をEnevisata - SwitchBot合計で推定
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

            # 照明推定: 夜間(18〜22時) - 日中(10〜17時)のギャップ × 夜間スロット数でkWh計算
            _day_base_w = float(_gap_df[_gap_df["hour"].between(10, 17)]["unmonitored_w"].mean())
            _evening_w  = float(_gap_df[_gap_df["hour"].between(18, 22)]["unmonitored_w"].mean())
            _lighting_w = max(_evening_w - _day_base_w, 0)
            _evening_slots = len(_gap_df[_gap_df["hour"].between(18, 22)])
            _lighting_kwh = _lighting_w * _evening_slots * 0.5 / 1000  # 各スロット30分
            if _lighting_w > 20:
                _lighting_kwh_year = _lighting_w * 24 * 365 / 1000
                _proposals.append({
                    "機器": "照明",
                    "avg_w": _lighting_w,
                    "kwh": _lighting_kwh,
                    "kwh_year": _lighting_kwh_year,
                    "bm_year": 200,
                    "bm_label": "一般家庭の照明合計の目安",
                    "excess_kwh": _lighting_kwh_year - 200,
                    "tip": f"夜間(18〜23時)の未監視電力から照明が平均 {_lighting_w:.0f} W と推定されます。"
                           "LED未交換の照明があれば交換で50〜80%削減可能です。使わない部屋の照明をこまめに消すことも有効です。",
                    "yen": _excess_saving_yen(_lighting_kwh_year - 200),
                })

        # エアコン推定: 全体kWh - SwitchBot合計 - 照明
        if _total_kwh:
            _monitored_kwh = sum(p["kwh"] for p in _proposals)
            _ac_kwh = max(_total_kwh - _monitored_kwh, 0)
            if _ac_kwh > 0:
                _ac_avg_w = _ac_kwh / _period_hours * 1000
                _ac_kwh_year = _ac_avg_w * 24 * 365 / 1000
                _ac_bm = 800 * 3  # 3台分
                _proposals.append({
                    "機器": "エアコン（3台）",
                    "avg_w": _ac_avg_w,
                    "kwh": _ac_kwh,
                    "kwh_year": _ac_kwh_year,
                    "bm_year": _ac_bm,
                    "bm_label": "エアコン3台・冷暖房合計の標準値",
                    "excess_kwh": _ac_kwh_year - _ac_bm,
                    "tip": f"全体から個別機器を差し引いた残余電力（{_ac_kwh:.1f} kWh）をエアコン3台等の未監視大型機器と推定します。"
                           "設定温度を1℃緩める（冷房: 26→27℃、暖房: 20→19℃）と約10%削減できます。"
                           "フィルター清掃（月1回）も効率維持に重要です。",
                    "yen": _excess_saving_yen(_ac_kwh_year - _ac_bm),
                })

        # ベンチマーク超過量順にソート（超過量がない機器は末尾）
        _proposals.sort(key=lambda x: x.get("excess_kwh", float("-inf")), reverse=True)

        if _proposals:
            st.caption(
                "※ 直近1ヶ月の実績データをもとにした推定です。"
                + (f"　集計期間の合計使用量: {_total_kwh:.1f} kWh　（{_co2_kg(_total_kwh):.0f} kg-CO2）" if _total_kwh else "")
                + f"　排出係数: {CO2_KG_PER_KWH} kg-CO2/kWh（東電EP 2022年度）　"
                + f"参考（一人当たり年間平均）: 家庭用電力 {CO2_PERCAPITA_ELEC_KG_YEAR:,} kg-CO2　"
                + f"／　日本全部門 {CO2_PERCAPITA_TOTAL_KG_YEAR:,} kg-CO2"
            )

            # ベンチマーク比較チャート
            _bm_rows = [
                p for p in _proposals if p.get("bm_year") and p.get("kwh_year")
            ]
            if _bm_rows:
                _bm_df = pd.DataFrame([
                    {"機器": p["機器"], "種別": "実測", "年間kWh": round(p["kwh_year"], 1)}
                    for p in _bm_rows
                ] + [
                    {"機器": p["機器"], "種別": "ベンチマーク", "年間kWh": p["bm_year"]}
                    for p in _bm_rows
                ])
                fig_bm = px.bar(
                    _bm_df, x="機器", y="年間kWh", color="種別", barmode="group",
                    color_discrete_map={"実測": "#E45756", "ベンチマーク": "#4C78A8"},
                    labels={"年間kWh": "年間消費量 (kWh)", "機器": ""},
                )
                fig_bm.update_layout(height=380, legend=dict(orientation="h", y=1.02, x=0))
                st.plotly_chart(fig_bm, use_container_width=True, config=PLOTLY_CONFIG)

            for _p in _proposals:
                _kwh_str = f"{_p['kwh']:.1f} kWh"
                _pct_str = _pct_of_total(_p["kwh"])
                _excess = _p.get("excess_kwh")
                _excess_str = (
                    f"ベンチマーク比 **+{_excess:.0f} kWh/年** 超過 ⚠️" if _excess and _excess > 0
                    else "ベンチマーク以内 ✅" if _excess is not None
                    else ""
                )
                _yen_str = f"{_p['yen']:,} 円/年" if _p["yen"] > 0 else "―"
                _co2_period = _co2_kg(_p["kwh"])
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
