"""Streamlit 專用：維度清單短快取，減少每 rerun 對 Redis／DB 的重複讀取（清單仍為完整集合）。"""
import streamlit as st

from database import db_session_scope
from queries import get_all_groups, get_all_queues, get_all_users, get_all_wallets

_DIM_TTL_SEC = 120


@st.cache_data(ttl=_DIM_TTL_SEC, show_spinner=False)
def streamlit_all_users() -> list:
    with db_session_scope() as db:
        return get_all_users(db)


@st.cache_data(ttl=_DIM_TTL_SEC, show_spinner=False)
def streamlit_all_groups() -> list:
    with db_session_scope() as db:
        return get_all_groups(db)


@st.cache_data(ttl=_DIM_TTL_SEC, show_spinner=False)
def streamlit_all_queues() -> list:
    with db_session_scope() as db:
        return get_all_queues(db)


@st.cache_data(ttl=_DIM_TTL_SEC, show_spinner=False)
def streamlit_all_wallets() -> list:
    with db_session_scope() as db:
        return get_all_wallets(db)


def clear_dimension_caches() -> None:
    """使側欄維度清單快取失效（於 jobs 載入／Redis 報表快取失效後呼叫）。

    僅在 Streamlit 應用執行中才 clear；CLI、pytest、背景載入等無 runtime 時直接略過。
    """
    try:
        if not (hasattr(st, "runtime") and st.runtime.exists()):
            return
    except Exception:
        return
    for fn in (
        streamlit_all_users,
        streamlit_all_groups,
        streamlit_all_queues,
        streamlit_all_wallets,
    ):
        try:
            fn.clear()
        except Exception:
            pass
