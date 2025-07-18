import streamlit as st
from database import SessionLocal
from auth import authenticate_user, get_user

# Set page configuration
st.set_page_config(
    page_title="運算資源帳務系統",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize session state variables if they don't exist
if "username" not in st.session_state:
    st.session_state["username"] = None
if "user_role" not in st.session_state:
    st.session_state["user_role"] = None

# --- Authentication Logic ---
def check_password():
    """Returns `True` if the user had a correct password."""

    def password_entered():
        """Checks whether a password entered by the user is correct."""
        db = SessionLocal()
        try:
            user = authenticate_user(db, st.session_state["username"], st.session_state["password"])
            if user:
                st.session_state["password_correct"] = True
                st.session_state["user_id"] = user.id
                st.session_state["username"] = user.username
                st.session_state["user_role"] = user.role
                del st.session_state["password"]  # Don't store password.
            else:
                st.session_state["password_correct"] = False
        finally:
            db.close()

    if "password_correct" not in st.session_state or not st.session_state["password_correct"]:
        st.title("📊 系統登入")
        st.text_input("使用者名稱", on_change=password_entered, key="username")
        st.text_input("密碼", type="password", on_change=password_entered, key="password")
        if "password_correct" in st.session_state and not st.session_state["password_correct"]:
            st.error("😕 帳號或密碼不正確")
        return False
    else:
        return True

# --- Main App ---

if check_password():
    st.sidebar.success(f"歡迎, {st.session_state['username']} ({st.session_state['user_role']})！")
    st.sidebar.header("導覽")

    # Streamlit automatically handles multi-page navigation based on files in the 'pages/' directory.
    # No explicit st.sidebar.page() calls are needed here.

    st.markdown("### 歡迎使用運算資源帳務系統!")
    st.markdown("請從左側的導覽列選擇一個頁面開始。")

    st.info("**儀表板資訊**: 查看您或您群組的資源使用情況。", icon="📊")
    if st.session_state["user_role"] == "admin":
        st.info("**管理者控制台**: (僅限管理員) 管理使用者、額度與系統設定。", icon="⚙️")
