"""側欄日期預設與起訖正規化（儀表板、詳細統計、使用報表共用，避免各頁邏輯漂移）。"""
from datetime import date, timedelta
from typing import Tuple

# 資料庫 jobs 最早～最晚跨度超過此天數時，預設開始日改為「結束日前」最近視窗
LONG_SPAN_THRESHOLD_DAYS = 180
DEFAULT_RECENT_WINDOW_DAYS = 90


def sidebar_default_date_range(
    data_earliest: date,
    data_latest: date,
) -> Tuple[date, date]:
    """
    依 jobs 的最早／最晚 start 日期，回傳側欄 date_input 的建議 (default_start, default_end)。

    規則與原儀表板／詳細統計／使用報表一致：跨度 > 180 天時，預設開始改為結束日前 90 天。
    """
    if (data_latest - data_earliest).days > LONG_SPAN_THRESHOLD_DAYS:
        default_start = max(
            data_earliest,
            data_latest - timedelta(days=DEFAULT_RECENT_WINDOW_DAYS),
        )
    else:
        default_start = data_earliest
    return default_start, data_latest


def normalize_start_end_dates(start: date, end: date) -> Tuple[date, date]:
    """若開始日晚於結束日，對調（與詳細統計／報表頁行為一致）。"""
    if start > end:
        return end, start
    return start, end
