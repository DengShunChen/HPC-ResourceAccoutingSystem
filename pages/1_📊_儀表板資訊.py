import streamlit as st
from datetime import timedelta
import pandas as pd
import altair as alt
import configparser

from database import get_db
from queries import (
    get_kpi_data,
    get_usage_over_time,
    get_filtered_jobs,
    get_all_users,
    get_all_groups,
    get_all_queues,
    get_all_wallets,
    get_first_job_date,
    get_last_job_date,
)

# --- Load Config ---
config = configparser.ConfigParser()
config.read("config.ini")
total_cpu_nodes = config.getint("cluster", "total_cpu_nodes", fallback=1)
total_gpu_cores = config.getint("cluster", "total_gpu_cores", fallback=1)

st.set_page_config(page_title="使用者儀表板", layout="wide")


def create_donut_chart(df, theta_col, color_col, title, color_range, tooltip_override=None):
    """Creates a generic Altair donut chart with a modern color scheme."""
    color_scale = alt.Scale(domain=["已使用", "未使用"], range=color_range)

    tooltip = tooltip_override if tooltip_override else [color_col, theta_col]
    chart = (
        alt.Chart(df)
        .mark_arc(outerRadius=110, innerRadius=60)
        .encode(
            theta=alt.Theta(field=theta_col, type="quantitative"),
            color=alt.Color(field=color_col, type="nominal", title="圖例", scale=color_scale),
            order=alt.Order(field=color_col, sort="descending"),
            tooltip=tooltip,
        )
        .properties(title=title)
        .configure_title(fontSize=24, anchor="middle", dy=25)
        .configure_legend(titleFontSize=14, labelFontSize=12, orient="bottom", direction="horizontal")
    )
    return chart


st.title(f"📊 {config.get('cluster', 'cluster_name', fallback='HPC')} 使用者儀表板")

# --- Database Session ---
db_session = next(get_db())

# --- Sidebar Filters ---
st.sidebar.header("篩選條件")

initial_start_date = get_first_job_date(db_session)
initial_end_date = get_last_job_date(db_session)
# 資料跨度 > 180 天時，預設開始日改為結束日前 90 天，減少初次聚合負擔
if (initial_end_date - initial_start_date).days > 180:
    default_start = max(initial_start_date, initial_end_date - timedelta(days=90))
else:
    default_start = initial_start_date

start_date = st.sidebar.date_input("開始日期", default_start)
end_date = st.sidebar.date_input("結束日期", initial_end_date)

all_users = ["(全部)"] + get_all_users(db_session)
all_queues = ["(全部)"] + get_all_queues(db_session)
all_wallets = ["(全部)"] + [w["name"] for w in get_all_wallets(db_session)]
all_groups = ["(全部)"] + get_all_groups(db_session)

user_name = st.sidebar.selectbox("使用者名稱", all_users)
user_group = st.sidebar.selectbox("使用者群組", all_groups)
wallet_name = st.sidebar.selectbox("錢包", all_wallets)
queue = st.sidebar.selectbox("佇列", all_queues)

time_granularity = st.sidebar.selectbox(
    "時間粒度",
    ["daily", "monthly", "quarterly", "yearly"],
    format_func=lambda x: {"daily": "每日", "monthly": "每月", "quarterly": "每季", "yearly": "每年"}[x],
)

effective_wallet_name = wallet_name if wallet_name != "(全部)" else None

# 使用 radio 取代 tabs：僅在選「CPU / GPU」時才查 get_filtered_jobs，避免每 rerun 撈 2000 筆
view = st.radio(
    "檢視",
    ["📈 總覽", "💻 CPU 帳務詳情", "🎮 GPU 帳務詳情"],
    horizontal=True,
    label_visibility="collapsed",
)

days_in_period = (end_date - start_date).days + 1
# 長區間 + 每日粒度：關閉 Vega 互動以降低瀏覽器端負擔
chart_interactive = not (time_granularity == "daily" and days_in_period > 90)


def _quarter_strings_to_datetime(series: pd.Series) -> pd.Series:
    """將 '2025-Q1' 形式轉成該季首月 1 日（向量化）。"""
    s = series.astype(str)
    m = s.str.extract(r"^(?P<y>\d{4})-Q(?P<q>[1-4])$", expand=True)
    y = pd.to_numeric(m["y"], errors="coerce")
    q = pd.to_numeric(m["q"], errors="coerce")
    month = (q - 1) * 3 + 1
    return pd.to_datetime(dict(year=y, month=month, day=1))


if view == "📈 總覽":
    if time_granularity == "daily" and days_in_period > 45:
        st.info(
            "目前為「每日」且區間較長：後端需掃描區間內所有任務再聚合，首次載入可能需數秒至數十秒。"
            " 若只要看整體走勢，建議改選「每月」或縮短日期。"
        )

    with st.spinner("正在載入 KPI 與使用趨勢…"):
        kpi_data = get_kpi_data(db_session, start_date, end_date, user_name, user_group, queue, effective_wallet_name)
        usage_data = get_usage_over_time(
            db_session, start_date, end_date, user_name, user_group, queue, effective_wallet_name, time_granularity
        )

    with st.container(border=True):
        st.subheader("期間資源使用率", divider="rainbow")

        hours_in_period = days_in_period * 24
        available_cpu_node_hours = total_cpu_nodes * hours_in_period
        available_gpu_core_hours = total_gpu_cores * hours_in_period

        used_cpu_node_hours = kpi_data["CPU"]["total_node_hours"]
        used_gpu_core_hours = kpi_data["GPU"]["total_core_hours"]

        free_cpu_node_hours = max(0, available_cpu_node_hours - used_cpu_node_hours)
        cpu_data = pd.DataFrame({"狀態": ["已使用", "未使用"], "節點小時數": [used_cpu_node_hours, free_cpu_node_hours]})
        cpu_chart_title = "CPU 節點小時使用情況"
        cpu_chart = create_donut_chart(
            cpu_data,
            "節點小時數",
            "狀態",
            cpu_chart_title,
            color_range=["#4CAF50", "#e5e7eb"],
            tooltip_override=["狀態", alt.Tooltip("節點小時數:Q", format=",.2f")],
        )

        free_gpu_core_hours = max(0, available_gpu_core_hours - used_gpu_core_hours)
        gpu_data = pd.DataFrame({"狀態": ["已使用", "未使用"], "核心小時數": [used_gpu_core_hours, free_gpu_core_hours]})
        gpu_chart_title = "GPU 核心小時使用情況"
        gpu_chart = create_donut_chart(
            gpu_data,
            "核心小時數",
            "狀態",
            gpu_chart_title,
            color_range=["#2196F3", "#e5e7eb"],
            tooltip_override=["狀態", alt.Tooltip("核心小時數:Q", format=",.2f")],
        )

        col1, col2 = st.columns(2)
        with col1:
            st.altair_chart(cpu_chart, use_container_width=True)
            cpu_percentage = (used_cpu_node_hours / available_cpu_node_hours * 100) if available_cpu_node_hours > 0 else 0
            st.markdown(
                f"<h4 style='text-align: center; color: #4CAF50;'>使用率: {cpu_percentage:.2f}%</h4>",
                unsafe_allow_html=True,
            )
            st.markdown(
                f"<p style='text-align: center; font-size: 0.9em; color: #6b7280;'>已使用: {used_cpu_node_hours:,.2f} / 總可用: {available_cpu_node_hours:,.2f} 節點小時</p>",
                unsafe_allow_html=True,
            )

        with col2:
            st.altair_chart(gpu_chart, use_container_width=True)
            gpu_percentage = (used_gpu_core_hours / available_gpu_core_hours * 100) if available_gpu_core_hours > 0 else 0
            st.markdown(
                f"<h4 style='text-align: center; color: #2196F3;'>使用率: {gpu_percentage:.2f}%</h4>",
                unsafe_allow_html=True,
            )
            st.markdown(
                f"<p style='text-align: center; font-size: 0.9em; color: #6b7280;'>已使用: {used_gpu_core_hours:,.2f} / 總可用: {available_gpu_core_hours:,.2f} 核心小時</p>",
                unsafe_allow_html=True,
            )

    with st.container(border=True):
        st.subheader("核心指標", divider="rainbow")

        col1, col2 = st.columns(2)
        with col1:
            st.markdown(
                f"<h3 style='text-align: center;'>CPU 節點小時</h3><p style='font-size: 3em; text-align: center; color: #4CAF50;'>{kpi_data['CPU']['total_node_hours']:,.2f}</p>",
                unsafe_allow_html=True,
            )
        with col2:
            st.markdown(
                f"<h3 style='text-align: center;'>GPU 核心小時</h3><p style='font-size: 3em; text-align: center; color: #2196F3;'>{kpi_data['GPU']['total_core_hours']:,.2f}</p>",
                unsafe_allow_html=True,
            )

        st.markdown("---")

        col3, col4, col5 = st.columns(3)
        with col3:
            st.markdown(
                f"<h4 style='text-align: center;'>總任務數</h4><p style='font-size: 2em; text-align: center;'>{kpi_data['overall_total_jobs']:,}</p>",
                unsafe_allow_html=True,
            )
        with col4:
            st.markdown(
                f"<h4 style='text-align: center;'>獨立使用者數</h4><p style='font-size: 2em; text-align: center;'>{kpi_data['unique_users']:,}</p>",
                unsafe_allow_html=True,
            )
        with col5:
            st.markdown(
                f"<h4 style='text-align: center;'>任務成功率</h4><p style='font-size: 2em; text-align: center;'>{kpi_data['success_rate']:.2f}%</p>",
                unsafe_allow_html=True,
            )

        col6, col7 = st.columns(2)
        with col6:
            st.markdown(
                f"<h4 style='text-align: center;'>平均等待時間 (秒)</h4><p style='font-size: 2em; text-align: center;'>{kpi_data['avg_wait_time']:.2f}</p>",
                unsafe_allow_html=True,
            )
        with col7:
            st.markdown(
                f"<h4 style='text-align: center;'>平均運行時間 (秒)</h4><p style='font-size: 2em; text-align: center;'>{kpi_data['overall_avg_run_time']:.2f}</p>",
                unsafe_allow_html=True,
            )

    st.subheader("📊 資源使用趨勢", divider="rainbow")
    if time_granularity == "daily" and days_in_period > 90:
        st.caption("目前為「每日」且區間較長：趨勢圖已關閉互動縮放以提升顯示速度；可改選「每月」或縮短日期範圍。")

    if not usage_data:
        st.warning("在選定範圍內沒有足夠的資料可供繪製資源使用趨勢圖。")
    else:
        usage_df = pd.DataFrame(usage_data)
        usage_df["period_hours"] = usage_df["daily_node_seconds"] / 3600
        if not usage_df.empty:
            if time_granularity == "quarterly":
                usage_df["date"] = _quarter_strings_to_datetime(usage_df["date"])
            else:
                usage_df["date"] = pd.to_datetime(usage_df["date"])

        time_domain = [pd.to_datetime(start_date).isoformat(), pd.to_datetime(end_date).isoformat()]

        st.markdown("#### CPU 使用趨勢 (節點小時)")
        cpu_usage_df = usage_df[usage_df["resource_type"] == "CPU"]
        if not cpu_usage_df.empty:
            cpu_chart = (
                alt.Chart(cpu_usage_df)
                .mark_line(color="#4CAF50", point=alt.OverlayMarkDef(color="#4CAF50", filled=True))
                .encode(
                    x=alt.X("date:T", title="日期", scale=alt.Scale(domain=time_domain)),
                    y=alt.Y("period_hours:Q", title="節點小時"),
                    tooltip=["date:T", "period_hours:Q"],
                )
            )
            if chart_interactive:
                cpu_chart = cpu_chart.interactive()
            st.altair_chart(cpu_chart, use_container_width=True)
        else:
            st.info("在選定範圍內沒有足夠的 CPU 資料可供繪圖。")

        st.markdown("#### GPU 使用趨勢 (核心小時)")
        gpu_usage_df = usage_df[usage_df["resource_type"] == "GPU"]
        if not gpu_usage_df.empty:
            gpu_chart = (
                alt.Chart(gpu_usage_df)
                .mark_line(color="#2196F3", point=alt.OverlayMarkDef(color="#2196F3", filled=True))
                .encode(
                    x=alt.X("date:T", title="日期", scale=alt.Scale(domain=time_domain)),
                    y=alt.Y("period_hours:Q", title="核心小時"),
                    tooltip=["date:T", "period_hours:Q"],
                )
            )
            if chart_interactive:
                gpu_chart = gpu_chart.interactive()
            st.altair_chart(gpu_chart, use_container_width=True)
        else:
            st.info("在選定範圍內沒有足夠的 GPU 資料可供繪圖。")

    st.info("更詳細的排行榜、使用分佈與原始資料，請至 **詳細統計資訊** 頁面查看。")

elif view == "💻 CPU 帳務詳情":
    st.subheader("CPU 帳務詳情")
    st.caption("此處僅顯示前 1000 筆資料。如需完整資料，請至「詳細統計資訊」頁面下載。")
    with st.spinner("正在載入 CPU 任務列表…"):
        cpu_jobs_data = get_filtered_jobs(
            db_session,
            start_date=start_date,
            end_date=end_date,
            user_name=user_name,
            user_group=user_group,
            queue=queue,
            resource_type="CPU",
            page_size=1000,
            wallet_name=effective_wallet_name,
            include_total=False,
        )
    if cpu_jobs_data["jobs"]:
        st.dataframe(pd.DataFrame(cpu_jobs_data["jobs"]), height=600, use_container_width=True)
    else:
        st.info("沒有找到符合條件的 CPU 任務資料。")

else:
    st.subheader("GPU 帳務詳情")
    st.caption("此處僅顯示前 1000 筆資料。如需完整資料，請至「詳細統計資訊」頁面下載。")
    with st.spinner("正在載入 GPU 任務列表…"):
        gpu_jobs_data = get_filtered_jobs(
            db_session,
            start_date=start_date,
            end_date=end_date,
            user_name=user_name,
            user_group=user_group,
            queue=queue,
            resource_type="GPU",
            page_size=1000,
            wallet_name=effective_wallet_name,
            include_total=False,
        )
    if gpu_jobs_data["jobs"]:
        st.dataframe(pd.DataFrame(gpu_jobs_data["jobs"]), height=600, use_container_width=True)
    else:
        st.info("沒有找到符合條件的 GPU 任務資料。")
