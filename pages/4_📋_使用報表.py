import io
from datetime import timedelta

import altair as alt
import pandas as pd
import streamlit as st

from database import get_db
from queries import (
    get_all_users,
    get_first_job_date,
    get_last_job_date,
    get_user_resource_usage_summary,
)

st.set_page_config(page_title="日常使用報表", layout="wide")

st.title("📋 日常 CPU / GPU 使用報表")

if not st.session_state.get("username"):
    st.warning("請先從首頁登入後再檢視此報表。")
    st.stop()

db_session = next(get_db())
username = st.session_state["username"]
user_role = st.session_state.get("user_role") or "user"

st.sidebar.header("報表條件")

initial_start = get_first_job_date(db_session)
initial_end = get_last_job_date(db_session)
if (initial_end - initial_start).days > 180:
    default_start = max(initial_start, initial_end - timedelta(days=90))
else:
    default_start = initial_start

start_date = st.sidebar.date_input("開始日期", default_start)
end_date = st.sidebar.date_input("結束日期", initial_end)

time_granularity = st.sidebar.selectbox(
    "時間粒度",
    ["daily", "weekly", "monthly"],
    format_func=lambda x: {"daily": "每日", "weekly": "每週", "monthly": "每月"}[x],
)

subject_user_name = None
if user_role == "admin":
    job_users = get_all_users(db_session)
    options = ["(全體)"] + sorted(job_users)
    choice = st.sidebar.selectbox("報表對象（僅管理員）", options)
    subject_user_name = None if choice == "(全體)" else choice
else:
    st.sidebar.caption(f"目前帳號：**{username}**（僅顯示本人用量）")

days_in_period = (end_date - start_date).days + 1
if time_granularity == "daily" and days_in_period > 45:
    st.info(
        "目前為「每日」且區間較長：後端需掃描區間內所有任務再聚合，載入可能較久。"
        " 若只要看走勢，可改選「每月」或縮短日期。"
    )

with st.spinner("正在載入使用摘要…"):
    rows = get_user_resource_usage_summary(
        db_session,
        start_date,
        end_date,
        user_role,
        username,
        subject_user_name=subject_user_name,
        time_granularity=time_granularity,
    )

df = pd.DataFrame(rows)
if df.empty:
    st.info("此區間內沒有符合條件的作業紀錄。")
    st.stop()

chart_interactive = not (time_granularity == "daily" and days_in_period > 90)
df_chart = df.melt(
    id_vars=["period"],
    value_vars=["cpu_node_hours", "gpu_core_hours"],
    var_name="指標",
    value_name="小時數",
)
df_chart["指標"] = df_chart["指標"].map(
    {"cpu_node_hours": "CPU 節點小時", "gpu_core_hours": "GPU 核心小時"}
)

chart = (
    alt.Chart(df_chart)
    .mark_line(point=True)
    .encode(
        x=alt.X("period:N", title="期間", sort=None),
        y=alt.Y("小時數:Q", title="小時"),
        color=alt.Color("指標:N", title=""),
        tooltip=[
            alt.Tooltip("period:N", title="期間"),
            alt.Tooltip("指標:N", title="指標"),
            alt.Tooltip("小時數:Q", format=",.4f", title="小時數"),
        ],
    )
    .properties(height=360)
)
if chart_interactive:
    chart = chart.interactive()

st.subheader("用量趨勢")
if time_granularity == "daily" and days_in_period > 90:
    st.caption("目前為「每日」且區間較長：趨勢圖已關閉互動縮放以提升顯示速度；可改選「每月」或縮短日期範圍。")
st.altair_chart(chart, use_container_width=True)

st.subheader("明細表")
st.dataframe(
    df.rename(
        columns={
            "period": "期間",
            "cpu_node_hours": "CPU 節點小時",
            "gpu_core_hours": "GPU 核心小時",
            "job_count": "作業數",
        }
    ),
    use_container_width=True,
)

csv_buf = io.StringIO()
df.to_csv(csv_buf, index=False)
st.download_button(
    label="下載 CSV",
    data=csv_buf.getvalue().encode("utf-8-sig"),
    file_name="resource_usage_summary.csv",
    mime="text/csv",
)
