import streamlit as st
import pandas as pd
from database import SessionLocal, get_db
from auth import get_user, create_user, verify_password
from queries import get_all_registered_users, set_user_quota, delete_user,     get_all_group_mappings, add_group_mapping, delete_group_mapping,     get_all_groups, get_all_users,     get_all_group_to_group_mappings, add_group_to_group_mapping, delete_group_to_group_mapping,     create_wallet, delete_wallet, get_all_wallets, update_wallet,     add_group_to_wallet_mapping, delete_group_to_wallet_mapping, get_all_group_to_wallet_mappings,     add_user_to_wallet_mapping, delete_user_to_wallet_mapping, get_all_user_to_wallet_mappings # New imports

st.set_page_config(page_title="管理後台", layout="wide")

st.title("⚙️ 管理後台")

# --- Database Session ---
db_session = next(get_db())

# --- Permission Check ---
# This check relies on st.session_state["user_role"] set in app.py after successful login
if "user_role" not in st.session_state or st.session_state["user_role"] != "admin":
    st.error("您沒有權限存取此頁面。請以管理員身份登入。")
    st.stop() # Stop execution if not admin

tab1, tab2, tab3, tab4, tab5 = st.tabs(["帳戶管理", "用量與額度", "群組對應規則", "群組對群組對應規則", "錢包管理"])

with tab1:
    st.header("帳戶管理")

    # Display existing users
    st.subheader("現有使用者")
    users = get_all_registered_users(db_session)
    if users:
        users_df = pd.DataFrame(users)
        st.dataframe(users_df, use_container_width=True)
    else:
        st.info("目前沒有註冊使用者。")

    # Add new user form
    st.subheader("新增使用者")
    with st.form("new_user_form"):
        new_username = st.text_input("使用者名稱")
        new_password = st.text_input("密碼", type="password")
        role = st.selectbox("角色", ["user", "admin"])
        submitted = st.form_submit_button("新增使用者")
        if submitted:
            try:
                create_user(db_session, new_username, new_password, role)
                db_session.commit()
                st.success(f"已成功建立使用者: {new_username}")
                st.rerun() # Rerun to update user list
            except Exception as e:
                db_session.rollback() # Rollback the session on error
                if "UNIQUE constraint failed" in str(e):
                    st.error(f"建立使用者失敗: 使用者名稱 '{new_username}' 已存在。")
                else:
                    st.error(f"建立使用者失敗: {e}")

    # Delete user form
    st.subheader("刪除使用者")
    with st.form("delete_user_form"):
        user_to_delete = st.selectbox("選擇要刪除的使用者", [u['username'] for u in users] if users else [])
        submitted = st.form_submit_button("刪除使用者")
        if submitted:
            if user_to_delete:
                user_obj = get_user(db_session, user_to_delete)
                if user_obj and delete_user(db_session, user_obj.id):
                    st.success(f"使用者 {user_to_delete} 已被刪除。")
                    st.rerun() # Rerun to update user list
                else:
                    st.error(f"刪除使用者 {user_to_delete} 失敗。")
            else:
                st.warning("請選擇一個使用者。")

with tab2:
    st.header("用量與額度監控")
    st.write("這裡將會顯示各個帳戶的用量百分比，並提供設定額度的介面。")
    # Placeholder for quota display and setting
    st.info("用量顯示和額度設定功能正在開發中。")

with tab3:
    st.header("群組對應規則管理")
    st.write("設定特定的群組帳務應歸屬於哪個使用者帳戶。")

    # Display existing mappings
    st.subheader("現有群組對應規則")
    mappings = get_all_group_mappings(db_session)
    if mappings:
        mappings_df = pd.DataFrame(mappings)
        st.dataframe(mappings_df, use_container_width=True)
    else:
        st.info("目前沒有設定群組對應規則。")

    # Add new mapping form
    st.subheader("新增群組對應規則")
    with st.form("add_mapping_form"):
        all_groups_from_jobs = get_all_groups(db_session) # Get groups from job data
        all_registered_users = get_all_users(db_session) # Get all registered users

        source_group = st.selectbox("來源群組 (Source Group)", all_groups_from_jobs)
        target_username = st.selectbox("目標使用者 (Target User)", all_registered_users)
        submitted = st.form_submit_button("新增規則")
        if submitted:
            try:
                add_group_mapping(db_session, source_group, target_username)
                st.success(f"已設定規則: 群組 {source_group} 的帳務將歸屬於 {target_username}")
                st.rerun() # Rerun to update mapping list
            except Exception as e:
                st.error(f"新增規則失敗: {e}")

    # Delete mapping form
    st.subheader("刪除群組對應規則")
    with st.form("delete_mapping_form"):
        mapping_options = {f"ID: {m['id']} - Group: {m['source_group']} -> User: {m['target_username']}": m['id'] for m in mappings} if mappings else {}
        selected_mapping_display = st.selectbox("選擇要刪除的規則", list(mapping_options.keys()))
        submitted = st.form_submit_button("刪除規則")
        if submitted:
            if selected_mapping_display:
                mapping_id_to_delete = mapping_options[selected_mapping_display]
                if delete_group_mapping(db_session, mapping_id_to_delete):
                    st.success(f"對應規則 ID {mapping_id_to_delete} 已被刪除。")
                    st.rerun() # Rerun to update mapping list
                else:
                    st.error(f"刪除規則 ID {mapping_id_to_delete} 失敗。")
            else:
                st.warning("請選擇一個規則。")

with tab4:
    st.header("群組對群組對應規則管理")
    st.write("設定一個來源群組的帳務應歸屬於另一個目標群組。")

    # Display existing group-to-group mappings
    st.subheader("現有群組對群組對應規則")
    group_to_group_mappings = get_all_group_to_group_mappings(db_session)
    if group_to_group_mappings:
        group_to_group_df = pd.DataFrame(group_to_group_mappings)
        st.dataframe(group_to_group_df, use_container_width=True)
    else:
        st.info("目前沒有設定群組對群組對應規則。")

    # Add new group-to-group mapping form
    st.subheader("新增群組對群組對應規則")
    with st.form("add_group_to_group_mapping_form"):
        all_groups = get_all_groups(db_session) # Get all groups from job data
        source_group_g2g = st.selectbox("來源群組 (Source Group)", all_groups, key="source_group_g2g")
        target_group_g2g = st.selectbox("目標群組 (Target Group)", all_groups, key="target_group_g2g")
        submitted_g2g = st.form_submit_button("新增群組對群組規則")
        if submitted_g2g:
            try:
                add_group_to_group_mapping(db_session, source_group_g2g, target_group_g2g)
                st.success(f"已設定規則: 群組 {source_group_g2g} 的帳務將歸屬於群組 {target_group_g2g}")
                st.rerun() # Rerun to update mapping list
            except Exception as e:
                st.error(f"新增群組對群組規則失敗: {e}")

    # Delete group-to-group mapping form
    st.subheader("刪除群組對群組對應規則")
    with st.form("delete_group_to_group_mapping_form"):
        g2g_mapping_options = {f"ID: {m['id']} - Source: {m['source_group']} -> Target: {m['target_group']}": m['id'] for m in group_to_group_mappings} if group_to_group_mappings else {}
        selected_g2g_mapping_display = st.selectbox("選擇要刪除的群組對群組規則", list(g2g_mapping_options.keys()))
        submitted_delete_g2g = st.form_submit_button("刪除群組對群組規則")
        if submitted_delete_g2g:
            if selected_g2g_mapping_display:
                g2g_mapping_id_to_delete = g2g_mapping_options[selected_g2g_mapping_display]
                if delete_group_to_group_mapping(db_session, g2g_mapping_id_to_delete):
                    st.success(f"群組對群組對應規則 ID {g2g_mapping_id_to_delete} 已被刪除。")
                    st.rerun() # Rerun to update mapping list
                else:
                    st.error(f"刪除群組對群組對應規則 ID {g2g_mapping_id_to_delete} 失敗。")
            else:
                st.warning("請選擇一個群組對群組規則。")

with tab5:
    st.header("錢包管理")

    # --- Wallet List ---
    st.subheader("現有錢包")
    wallets = get_all_wallets(db_session)
    if wallets:
        wallets_df = pd.DataFrame(wallets)
        st.dataframe(wallets_df, use_container_width=True)
    else:
        st.info("目前沒有建立任何錢包。")

    # --- Add Wallet ---
    st.subheader("新增錢包")
    with st.form("add_wallet_form"):
        wallet_name = st.text_input("錢包名稱")
        wallet_description = st.text_area("錢包描述 (可選)")
        submitted_wallet = st.form_submit_button("新增錢包")
        if submitted_wallet:
            try:
                create_wallet(db_session, wallet_name, wallet_description)
                st.success(f"錢包 '{wallet_name}' 已成功建立。")
                st.rerun()
            except Exception as e:
                st.error(f"建立錢包失敗: {e}")

    # --- Update Wallet ---
    st.subheader("修改錢包")
    with st.form("update_wallet_form"):
        # Get current wallets for selection
        current_wallets = get_all_wallets(db_session)
        wallet_options_update = {f"ID: {w['id']} - {w['name']}": w for w in current_wallets} if current_wallets else {}
        selected_wallet_display_update = st.selectbox("選擇要修改的錢包", list(wallet_options_update.keys()), key="update_wallet_select")

        selected_wallet_obj = wallet_options_update.get(selected_wallet_display_update)
        
        default_name = selected_wallet_obj['name'] if selected_wallet_obj else ""
        default_description = selected_wallet_obj['description'] if selected_wallet_obj else ""

        new_wallet_name = st.text_input("新錢包名稱", value=default_name, key="new_wallet_name_input")
        new_wallet_description = st.text_area("新錢包描述 (可選)", value=default_description, key="new_wallet_description_input")
        
        submitted_update_wallet = st.form_submit_button("修改錢包")

        if submitted_update_wallet:
            if selected_wallet_obj:
                try:
                    update_wallet(db_session, selected_wallet_obj['id'], new_wallet_name, new_wallet_description)
                    st.success(f"錢包 '{new_wallet_name}' 已成功更新。")
                    st.rerun()
                except Exception as e:
                    st.error(f"更新錢包失敗: {e}")
            else:
                st.warning("請選擇一個錢包進行修改。")

    # --- Delete Wallet ---
    st.subheader("刪除錢包")
    with st.form("delete_wallet_form"):
        wallet_options = {f"ID: {w['id']} - {w['name']}": w['id'] for w in wallets} if wallets else {}
        selected_wallet_display = st.selectbox("選擇要刪除的錢包", list(wallet_options.keys()))
        submitted_delete_wallet = st.form_submit_button("刪除錢包")
        if submitted_delete_wallet:
            if selected_wallet_display:
                wallet_id_to_delete = wallet_options[selected_wallet_display]
                if delete_wallet(db_session, wallet_id_to_delete):
                    st.success(f"錢包 ID {wallet_id_to_delete} 已被刪除。")
                    st.rerun()
                else:
                    st.error(f"刪除錢包 ID {wallet_id_to_delete} 失敗。")
            else:
                st.warning("請選擇一個錢包。")

    st.markdown("--- ")

    # --- Group to Wallet Mappings ---
    st.subheader("群組對錢包對應規則")
    st.write("設定特定群組的帳務應歸屬於哪個錢包。")
    g2w_mappings = get_all_group_to_wallet_mappings(db_session)
    if g2w_mappings:
        g2w_df = pd.DataFrame(g2w_mappings)
        st.dataframe(g2w_df, use_container_width=True)
    else:
        st.info("目前沒有設定群組對錢包對應規則。")

    with st.form("add_g2w_mapping_form"):
        all_groups = get_all_groups(db_session)
        all_wallet_names = [w['name'] for w in wallets]
        source_group_g2w = st.selectbox("來源群組", all_groups, key="source_group_g2w_add")
        target_wallet_name_g2w = st.selectbox("目標錢包", all_wallet_names, key="target_wallet_name_g2w_add")
        submitted_add_g2w = st.form_submit_button("新增群組對錢包規則")
        if submitted_add_g2w:
            try:
                add_group_to_wallet_mapping(db_session, source_group_g2w, target_wallet_name_g2w)
                st.success(f"已設定規則: 群組 {source_group_g2w} 的帳務將歸屬於錢包 {target_wallet_name_g2w}")
                st.rerun()
            except Exception as e:
                st.error(f"新增群組對錢包規則失敗: {e}")

    with st.form("delete_g2w_mapping_form"):
        g2w_mapping_options = {f"ID: {m['id']} - Group: {m['source_group']} -> Wallet: {m['wallet_name']}": m['id'] for m in g2w_mappings} if g2w_mappings else {}
        selected_g2w_mapping_display = st.selectbox("選擇要刪除的群組對錢包規則", list(g2w_mapping_options.keys()))
        submitted_delete_g2w = st.form_submit_button("刪除群組對錢包規則")
        if submitted_delete_g2w:
            if selected_g2w_mapping_display:
                g2w_mapping_id_to_delete = g2w_mapping_options[selected_g2w_mapping_display]
                if delete_group_to_wallet_mapping(db_session, g2w_mapping_id_to_delete):
                    st.success(f"群組對錢包對應規則 ID {g2w_mapping_id_to_delete} 已被刪除。")
                    st.rerun()
                else:
                    st.error(f"刪除群組對錢包對應規則 ID {g2w_mapping_id_to_delete} 失敗。")
            else:
                st.warning("請選擇一個群組對錢包規則。")

    st.markdown("--- ")

    # --- User to Wallet Mappings ---
    st.subheader("使用者對錢包對應規則")
    st.write("設定特定使用者的帳務應歸屬於哪個錢包。")
    u2w_mappings = get_all_user_to_wallet_mappings(db_session)
    if u2w_mappings:
        u2w_df = pd.DataFrame(u2w_mappings)
        st.dataframe(u2w_df, use_container_width=True)
    else:
        st.info("目前沒有設定使用者對錢包對應規則。")

    with st.form("add_u2w_mapping_form"):
        all_users = get_all_users(db_session)
        all_wallet_names = [w['name'] for w in wallets]
        source_username_u2w = st.selectbox("來源使用者", all_users, key="source_username_u2w_add")
        target_wallet_name_u2w = st.selectbox("目標錢包", all_wallet_names, key="target_wallet_name_u2w_add")
        submitted_add_u2w = st.form_submit_button("新增使用者對錢包規則")
        if submitted_add_u2w:
            try:
                add_user_to_wallet_mapping(db_session, source_username_u2w, target_wallet_name_u2w)
                st.success(f"已設定規則: 使用者 {source_username_u2w} 的帳務將歸屬於錢包 {target_wallet_name_u2w}")
                st.rerun()
            except Exception as e:
                st.error(f"新增使用者對錢包規則失敗: {e}")

    with st.form("delete_u2w_mapping_form"):
        u2w_mapping_options = {f"ID: {m['id']} - User: {m['username']} -> Wallet: {m['wallet_name']}": m['id'] for m in u2w_mappings} if u2w_mappings else {}
        selected_u2w_mapping_display = st.selectbox("選擇要刪除的使用者對錢包規則", list(u2w_mapping_options.keys()))
        submitted_delete_u2w = st.form_submit_button("刪除使用者對錢包規則")
        if submitted_delete_u2w:
            if selected_u2w_mapping_display:
                u2w_mapping_id_to_delete = u2w_mapping_options[selected_u2w_mapping_display]
                if delete_user_to_wallet_mapping(db_session, u2w_mapping_id_to_delete):
                    st.success(f"使用者對錢包對應規則 ID {u2w_mapping_id_to_delete} 已被刪除。")
                    st.rerun()
                else:
                    st.error(f"刪除使用者對錢包對應規則 ID {u2w_mapping_id_to_delete} 失敗。")
            else:
                st.warning("請選擇一個使用者對錢包規則。")