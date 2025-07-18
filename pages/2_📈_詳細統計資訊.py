import streamlit as st
from datetime import date
import pandas as pd
import altair as alt

from database import get_db
from queries import (
    get_top_users_by_core_hours, get_top_groups_by_core_hours, 
    get_job_status_distribution, get_all_users, get_all_groups, 
    get_all_queues, get_all_wallets, get_wallet_usage_by_resource_type, 
    get_top_wallets_by_core_hours, get_usage_by_queue, get_filtered_jobs,
    get_average_job_runtime_by_queue, get_peak_usage_heatmap,
    get_first_job_date, get_last_job_date, get_failure_rate_by_group, get_failure_rate_by_user,
    get_average_wait_time_by_queue
)

st.set_page_config(page_title="詳細統計資訊", layout="wide")

st.title("📈 詳細統計資訊")

# --- Helper Functions ---
def create_bar_chart(df, x_col, y_col, x_title, y_title, title, sort_order='-x', tooltip_override=None):
    """Creates a generic Altair bar chart with all Y-axis labels."""
    tooltip = tooltip_override if tooltip_override else [y_col, x_col]
    chart = alt.Chart(df).mark_bar().encode(
        x=alt.X(x_col, title=x_title),
        y=alt.Y(y_col, sort=sort_order, title=y_title, axis=alt.Axis(labelLimit=0)),
        tooltip=tooltip
    ).properties(title=title, height=alt.Step(40)).configure_title(
        fontSize=20
    ).configure_axis(
        labelFontSize=14,
        titleFontSize=16
    )
    return chart

def create_donut_chart(df, theta_col, color_col, title, tooltip_override=None):
    """Creates a generic Altair donut chart."""
    tooltip = tooltip_override if tooltip_override else [color_col, theta_col]
    chart = alt.Chart(df).mark_arc(outerRadius=120, innerRadius=50).encode(
        theta=alt.Theta(field=theta_col, type="quantitative"),
        color=alt.Color(field=color_col, type="nominal", title="圖例", scale=alt.Scale(scheme='category20b')),
        order=alt.Order(field=theta_col, sort="descending"),
        tooltip=tooltip
    ).properties(title=title).configure_title(
        fontSize=20
    ).configure_legend(
        titleFontSize=16,
        labelFontSize=14
    )
    return chart

def create_stacked_bar_chart(df, x_col, color_col, title):
    """Creates a generic Altair stacked bar chart."""
    df['dummy_y'] = ' '
    chart = alt.Chart(df).mark_bar().encode(
        x=alt.X(x_col, stack="normalize", axis=alt.Axis(format=".0%"), title="比例"),
        y=alt.Y('dummy_y', axis=None),
        color=alt.Color(color_col, title="圖例", legend=alt.Legend(orient="bottom")),
        order=alt.Order(x_col, sort='descending'),
        tooltip=[color_col, x_col, alt.Tooltip('percentage', format=".1%", title="比例")]
    ).properties(title=title).configure_title(
        fontSize=20
    ).configure_axis(
        labelFontSize=14,
        titleFontSize=16
    ).configure_legend(
        titleFontSize=16,
        labelFontSize=14
    )
    return chart

# --- Database Session ---
db_session = next(get_db())

# --- Sidebar Filters ---
st.sidebar.header("篩選條件")
initial_start_date = get_first_job_date(db_session)
initial_end_date = get_last_job_date(db_session)
start_date = st.sidebar.date_input("開始日期", initial_start_date, key="stats_start_date")
end_date = st.sidebar.date_input("結束日期", initial_end_date, key="stats_end_date")
top_n = st.sidebar.number_input("排行榜顯示數量", min_value=3, max_value=20, value=10, step=1)

all_users = ["(全部)"] + get_all_users(db_session)
all_queues = ["(全部)"] + get_all_queues(db_session)
all_wallets = ["(全部)"] + [w['name'] for w in get_all_wallets(db_session)]
all_groups = ["(全部)"] + get_all_groups(db_session)

user_name = st.sidebar.selectbox("使用者名稱", all_users, key="stats_user_name")
user_group = st.sidebar.selectbox("使用者群組", all_groups, key="stats_user_group")
wallet_name = st.sidebar.selectbox("錢包", all_wallets, key="stats_wallet_name")
queue = st.sidebar.selectbox("佇列", all_queues, key="stats_queue")

effective_wallet_name = wallet_name if wallet_name != "(全部)" else None

# --- Main Content ---

with st.expander("🔥 系統使用熱圖", expanded=True):
    heatmap_data = get_peak_usage_heatmap(db_session, start_date, end_date, user_name, user_group, queue, effective_wallet_name)
    if heatmap_data:
        df_heatmap = pd.DataFrame(heatmap_data)
        df_heatmap['day_of_week'] = df_heatmap['day_of_week'].astype(int)
        
        days_of_week = {1: '週一', 2: '週二', 3: '週三', 4: '週四', 5: '週五', 6: '週六', 0: '週日'}
        hours_of_day = list(range(24))
        full_grid = pd.DataFrame([(d, h) for d in days_of_week.keys() for h in hours_of_day], columns=['day_of_week', 'hour_of_day'])
        
        df_heatmap = pd.merge(full_grid, df_heatmap, on=['day_of_week', 'hour_of_day'], how='left').fillna(0)

        day_map_sort = {1: 0, 2: 1, 3: 2, 4: 3, 5: 4, 6: 5, 0: 6}
        df_heatmap['sort_order'] = df_heatmap['day_of_week'].map(day_map_sort)
        df_heatmap['day_of_week_str'] = df_heatmap['day_of_week'].map(days_of_week)

        heatmap = alt.Chart(df_heatmap).mark_rect().encode(
            x=alt.X('hour_of_day:O', title='時段 (0-23)', axis=alt.Axis(labelAngle=0)),
            y=alt.Y('day_of_week_str:O', title='星期', sort=alt.EncodingSortField(field="sort_order")),
            color=alt.Color('job_count:Q', title='任務數', scale=alt.Scale(scheme='viridis')),
            tooltip=['day_of_week_str', 'hour_of_day', 'job_count']
        ).properties(
            title="系統使用尖峰時段分析"
        )
        st.altair_chart(heatmap, use_container_width=True)
    else:
        st.info("沒有足夠的資料可產生熱圖。")

with st.expander("🏆 資源使用排行榜", expanded=True):
    col1, col2, col3 = st.columns(3)
    with col1:
        top_users = get_top_users_by_core_hours(db_session, start_date, end_date, user_group, queue, effective_wallet_name, limit=top_n)
        if top_users:
            st.altair_chart(create_bar_chart(pd.DataFrame(top_users), 'core_hours', 'user_name', '節點小時', '使用者', f"Top {top_n} 使用者"), use_container_width=True)
        else:
            st.info("沒有使用者資料可供顯示。")

    with col2:
        top_groups = get_top_groups_by_core_hours(db_session, start_date, end_date, user_name, queue, effective_wallet_name, limit=top_n)
        if top_groups:
            st.altair_chart(create_bar_chart(pd.DataFrame(top_groups), 'core_hours', 'user_group', '節點小時', '群組', f"Top {top_n} 群組"), use_container_width=True)
        else:
            st.info("沒有群組資料可供顯示。")

    with col3:
        top_wallets = get_top_wallets_by_core_hours(db_session, start_date, end_date, limit=top_n)
        if top_wallets:
            st.altair_chart(create_bar_chart(pd.DataFrame(top_wallets), 'core_hours', 'wallet_name', '節點小時', '錢包', f"Top {top_n} 錢包"), use_container_width=True)
        else:
            st.info("沒有錢包資料可供顯示。")

with st.expander("📉 任務失敗率分析", expanded=True):
    col1, col2 = st.columns(2)
    with col1:
        group_failure_rate = get_failure_rate_by_group(db_session, start_date, end_date, limit=top_n)
        if group_failure_rate:
            df_group_rate = pd.DataFrame(group_failure_rate)
            df_group_rate['failure_rate_str'] = df_group_rate['failure_rate'].apply(lambda x: f'{x:.2f}%')
            st.altair_chart(create_bar_chart(
                df_group_rate, 'failure_rate', 'group', '失敗率 (%)', '群組', f"Top {top_n} 高失敗率群組",
                tooltip_override=['group', alt.Tooltip('failure_rate_str', title='失敗率'), 'total_jobs']
            ), use_container_width=True)
        else:
            st.info("沒有群組失敗率資料可供顯示。")
    with col2:
        user_failure_rate = get_failure_rate_by_user(db_session, start_date, end_date, limit=top_n)
        if user_failure_rate:
            df_user_rate = pd.DataFrame(user_failure_rate)
            df_user_rate['failure_rate_str'] = df_user_rate['failure_rate'].apply(lambda x: f'{x:.2f}%')
            st.altair_chart(create_bar_chart(
                df_user_rate, 'failure_rate', 'user', '失敗率 (%)', '使用者', f"Top {top_n} 高失敗率使用者",
                tooltip_override=['user', alt.Tooltip('failure_rate_str', title='失敗率'), 'total_jobs']
            ), use_container_width=True)
        else:
            st.info("沒有使用者失敗率資料可供顯示。")

with st.expander("📊 使用分佈與效率", expanded=True):
    col1, col2, col3 = st.columns(3)
    with col1:
        job_status_dist = get_job_status_distribution(db_session, start_date, end_date, user_name, user_group, queue, effective_wallet_name)
        if job_status_dist:
            df_status = pd.DataFrame(job_status_dist)
            total_jobs = df_status['job_count'].sum()
            df_status['percentage'] = (df_status['job_count'] / total_jobs * 100).apply(lambda x: f'{x:.2f}%')
            st.altair_chart(create_donut_chart(
                df_status, 'job_count', 'job_status', "任務狀態分佈",
                tooltip_override=['job_status', 'job_count', alt.Tooltip('percentage', title='佔比')]
            ), use_container_width=True)
        else:
            st.info("沒有任務狀態資料可供顯示。")

    with col2:
        avg_runtime = get_average_job_runtime_by_queue(db_session, start_date, end_date, user_name, user_group, effective_wallet_name)
        if avg_runtime:
            st.altair_chart(create_bar_chart(pd.DataFrame(avg_runtime), 'avg_runtime_seconds', 'queue', '平均運行時間 (秒)', '佇列', "佇列效率分析 (平均運行時間)"), use_container_width=True)
        else:
            st.info("沒有佇列效率資料可供顯示。")
            
    with col3:
        avg_waittime = get_average_wait_time_by_queue(db_session, start_date, end_date)
        if avg_waittime:
            st.altair_chart(create_bar_chart(pd.DataFrame(avg_waittime), 'avg_wait_seconds', 'queue', '平均等待時間 (秒)', '佇列', "佇列效率分析 (平均等待時間)"), use_container_width=True)
        else:
            st.info("沒有佇列等待時間資料可供顯示。")

with st.expander("💰 錢包與佇列使用量", expanded=True):
    col1, col2 = st.columns(2)
    with col1:
        cpu_wallet_usage = get_wallet_usage_by_resource_type(db_session, start_date, end_date, "CPU", user_name, user_group, queue, effective_wallet_name)
        if cpu_wallet_usage:
            df = pd.DataFrame(cpu_wallet_usage)
            total = df['core_hours'].sum()
            df['percentage'] = df['core_hours'] / total if total > 0 else 0
            st.altair_chart(create_stacked_bar_chart(df, 'core_hours', 'wallet_name', "CPU 錢包使用比例"), use_container_width=True)
        else:
            st.info("沒有 CPU 錢包資料可供顯示。")

    with col2:
        gpu_wallet_usage = get_wallet_usage_by_resource_type(db_session, start_date, end_date, "GPU", user_name, user_group, queue, effective_wallet_name)
        if gpu_wallet_usage:
            df = pd.DataFrame(gpu_wallet_usage)
            total = df['core_hours'].sum()
            df['percentage'] = df['core_hours'] / total if total > 0 else 0
            st.altair_chart(create_stacked_bar_chart(df, 'core_hours', 'wallet_name', "GPU 錢包使用比例"), use_container_width=True)
        else:
            st.info("沒有 GPU 錢包資料可供顯示。")

with st.expander("📄 原始資料", expanded=False):
    st.info("此處顯示符合篩選條件的前 1000 筆任務資料。")
    jobs_data = get_filtered_jobs(db_session, start_date=start_date, end_date=end_date, user_name=user_name, user_group=user_group, queue=queue, wallet_name=effective_wallet_name, page_size=1000)
    if jobs_data['jobs']:
        df_jobs = pd.DataFrame(jobs_data['jobs'])
        st.dataframe(df_jobs, use_container_width=True)
        
        csv = df_jobs.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="下載 CSV",
            data=csv,
            file_name=f'jobs_report_{start_date}_to_{end_date}.csv',
            mime='text/csv',
        )
    else:
        st.warning("沒有找到符合條件的任務資料。")
