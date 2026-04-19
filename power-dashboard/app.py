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

PLOTLY_CONFIG = {"scrollZoom": True}

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
            lambda d: d.replace(day=1) if d.day >= 9 else (d - pd.offsets.MonthBegin(1))
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
        lambda d: d.replace(day=1) if d.day >= 9 else (d - pd.offsets.MonthBegin(1))
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
            st.metric(f"{_reduce}kWh削減すると", f"月 {_saving:,} 円節約",
                      f"{_latest_u} → {_latest_u - _reduce} kWh")
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
        _avg_w = _avg_w.sort_values("年間推定コスト (円)", ascending=False)

        fig_dev = px.bar(
            _avg_w, x="年間推定コスト (円)", y="機器名", orientation="h",
            labels={"機器名": ""},
            color_discrete_sequence=["#4C78A8"],
        )
        fig_dev.update_layout(height=max(300, len(_avg_w) * 35), yaxis=dict(categoryorder="total ascending"))
        st.plotly_chart(fig_dev, use_container_width=True, config=PLOTLY_CONFIG)
        st.caption(f"※ 直近1ヶ月の平均消費電力から試算。実効限界単価: {_marginal:.1f}円/kWh（第2段階ベース）")
        st.dataframe(
            _avg_w[["機器名", "平均消費電力 (W)", "年間推定コスト (円)"]].reset_index(drop=True),
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
        _today = pd.Timestamp.now(tz="Asia/Tokyo").date()
        if _today.day >= 9:
            _bill_start_date = _today.replace(day=9)
        else:
            _prev = (_today.replace(day=1) - timedelta(days=1))
            _bill_start_date = _prev.replace(day=9)
        if _bill_start_date.month == 12:
            _bill_end_date = _bill_start_date.replace(year=_bill_start_date.year + 1, month=1, day=8)
        else:
            _bill_end_date = _bill_start_date.replace(month=_bill_start_date.month + 1, day=8)
        _bill_days = (_bill_end_date - _bill_start_date).days + 1
        _days_elapsed = (_today - _bill_start_date).days + 1
        _days_remaining = _bill_days - _days_elapsed

        _rec_dates = _df_d["recorded_date"].dt.date
        _this_month = _df_d[(_rec_dates >= _bill_start_date) & (_rec_dates <= _today)]
        _cur_kwh = _this_month["usage_kwh"].sum()
        _proj_kwh = _cur_kwh + (_cur_kwh / max(_days_elapsed, 1)) * _days_remaining

        _ty, _tm = _bill_end_date.year, _bill_end_date.month
        _trow_df = _df_t[(_df_t["year"] == _ty) & (_df_t["month"] == _tm)]
        _trow = _trow_df.iloc[0] if not _trow_df.empty else _df_t.iloc[-1]

        col1, col2, col3 = st.columns(3)
        col1.metric("現在の使用量", f"{_cur_kwh:.1f} kWh", f"経過 {_days_elapsed} 日")
        col2.metric("月末予測使用量", f"{int(_proj_kwh)} kWh", f"残 {_days_remaining} 日")
        col3.metric("月末予測料金", f"{_calc_bill_from_kwh(_proj_kwh, _trow):,} 円")

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
