import io
import numpy as np
import pandas as pd
import streamlit as st

st.set_page_config(page_title="持仓分析", layout="wide")

# ── 密码保护 ──────────────────────────────────────────────────────────────────
def check_password():
    if st.session_state.get("authenticated"):
        return True
    st.title("持仓历史分析")
    pwd = st.text_input("請輸入密碼", type="password", key="pwd_input")
    if st.button("登入"):
        if pwd == st.secrets["APP_PASSWORD"]:
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("密碼錯誤")
    return False

if not check_password():
    st.stop()

# ── 主界面 ────────────────────────────────────────────────────────────────────
st.title("持仓历史分析")
st.caption("上传 Positions History CSV，自动生成客户统计报表")

uploaded = st.file_uploader("上传文件（MT5 导出 CSV）", type=["csv", "txt"])

if uploaded:
    file_mb = len(uploaded.getvalue()) / 1024 / 1024
    st.info(f"文件已接收：{uploaded.name}（{file_mb:.1f} MB），開始處理...")

    progress = st.progress(0, text="讀取文件中...")
    raw = uploaded.read()

    progress.progress(15, text="解析數據中...")
    df = pd.read_csv(io.BytesIO(raw), encoding="utf-16", sep="\t", low_memory=False)

    progress.progress(30, text="清洗數據中...")
    df = df[pd.to_numeric(df["Login"], errors="coerce").notna()].copy()
    df["Login"] = df["Login"].astype(int)
    df["Volume"] = pd.to_numeric(df["Volume"], errors="coerce")

    progress.progress(45, text="轉換時間欄位...")
    df["Time"] = pd.to_datetime(df["Time"], format="%Y.%m.%d %H:%M:%S.%f")
    df["Close Time"] = pd.to_datetime(df["Close Time"], format="%Y.%m.%d %H:%M:%S.%f")

    progress.progress(55, text="換算幣種（USC → USD）...")
    usc = df["Currency"] == "USC"
    df.loc[usc, "Profit"] = df.loc[usc, "Profit"] / 100
    df.loc[usc, "Volume"] = df.loc[usc, "Volume"] / 100

    progress.progress(65, text="計算持倉時長...")
    df["duration_min"] = (df["Close Time"] - df["Time"]).dt.total_seconds() / 60
    df["open_date"] = df["Time"].dt.date
    df["close_date"] = df["Close Time"].dt.date
    df["is_social"] = df["Comment"].fillna("").str.contains("Social", case=False)

    progress.progress(75, text="按賬戶彙總中（數據量大，稍候）...")

    def agg_login(g):
        dur = g["duration_min"]
        total = len(g)
        wins = int((g["Profit"] > 0).sum())
        within_15 = (dur <= 15).sum()
        same_day = (g["open_date"] == g["close_date"]).sum()
        return pd.Series({
            "客戶名字":     g["Name"].iloc[0],
            "幣種":         g["Currency"].iloc[0],
            "當天盈虧":     round(g["Profit"].sum(), 2),
            "交易總額":     round(g["Volume"].sum(), 4),
            "交易次數":     total,
            "獲利次數":     wins,
            "0 - 1 分鐘":  int((dur <= 1).sum()),
            "1 - 5 分鐘":  int(((dur > 1) & (dur <= 5)).sum()),
            "5 - 15 分鐘": int(((dur > 5) & (dur <= 15)).sum()),
            "專業下單":     round(within_15 / total, 4) if total else np.nan,
            "勝算比率":     round(wins / total, 4) if total else np.nan,
            "同日平倉占比": round(same_day / total, 4) if total else np.nan,
            "公司跟單":     int(g["is_social"].any()),
        })

    result = (
        df.groupby("Login")
        .apply(agg_login, include_groups=False)
        .reset_index()
        .rename(columns={"Login": "賬戶號碼"})
        .sort_values("當天盈虧", ascending=False)
    )

    progress.progress(100, text="完成！")
    st.success(f"完成！共 {len(result)} 個賬戶")
    st.dataframe(result, use_container_width=True, hide_index=True)

    csv_out = result.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
    st.download_button(
        label="⬇️ 下載結果 CSV",
        data=csv_out,
        file_name="持仓分析结果.csv",
        mime="text/csv",
    )
