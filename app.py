import streamlit as st
import pandas as pd
import json
import datetime
import plotly.express as px
from github import Github, Auth
from github import GithubException
from streamlit_oauth import OAuth2Component
import os

# ==========================================
# 1. KONFIGURASI AWAL & TAMPILAN (SMARTSHEET STYLE)
# ==========================================
st.set_page_config(page_title="CP-PMO Smartsheet Workspace", layout="wide")

# Gaya Tampilan Smartsheet
st.markdown("""
    <style>
        html, body, [data-testid="stMarkdownContainer"] {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            color: #333333;
        }
        .stTabs [data-baseweb="tab-list"] {
            gap: 8px;
            background-color: #F4F5F7;
            padding: 6px 12px;
            border-radius: 4px;
            border-bottom: 2px solid #E2E4E8;
        }
        .stTabs [data-baseweb="tab"] {
            height: 38px;
            background-color: transparent;
            border-radius: 4px;
            color: #5E6C84;
            font-weight: 600;
            font-size: 13px;
            padding: 0px 16px;
        }
        .stTabs [aria-selected="true"] {
            background-color: #FFFFFF !important;
            color: #006644 !important;
            box-shadow: 0px 2px 4px rgba(0,0,0,0.05);
        }
        div.stButton > button:first-child {
            background-color: #006644;
            color: white;
            border: none;
            border-radius: 4px;
            padding: 8px 16px;
            font-weight: 500;
        }
        div.stButton > button:first-child:hover {
            background-color: #004d33;
            color: white;
        }
        .user-profile {
            background-color: #EAECEF;
            padding: 8px 12px;
            border-radius: 4px;
            margin-bottom: 15px;
            font-size: 14px;
        }
    </style>
""", unsafe_allow_html=True)

# ------------------------------------------
# KONFIGURASI SECRETS (GITHUB & GOOGLE OAUTH)
# ------------------------------------------
# Pastikan semua secret ini sudah diisi di Streamlit Cloud Secrets Anda
if all(k in st.secrets for k in ["GITHUB_TOKEN", "REPO_NAME", "GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET"]):
    GITHUB_TOKEN = st.secrets["GITHUB_TOKEN"]
    REPO_NAME = st.secrets["REPO_NAME"]
    CLIENT_ID = st.secrets["GOOGLE_CLIENT_ID"]
    CLIENT_SECRET = st.secrets["GOOGLE_CLIENT_SECRET"]
else:
    st.error("❌ Konfigurasi Secrets Belum Lengkap!")
    st.info("Harap tambahkan GITHUB_TOKEN, REPO_NAME, GOOGLE_CLIENT_ID, dan GOOGLE_CLIENT_SECRET di Dashboard Secrets Streamlit Anda.")
    st.stop()

FILE_PATH = "tasks.json"

# Konfigurasi Endpoint OAuth Google resmi
AUTHORIZATION_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"

# Inisialisasi komponen OAuth
oauth2 = OAuth2Component(CLIENT_ID, CLIENT_SECRET, AUTHORIZATION_URL, TOKEN_URL, TOKEN_URL, REVOKE_URL)

# ==========================================
# 2. PROSES LOGIN / AUTENTIKASI GMAIL
# ==========================================
if "auth" not in st.session_state:
    st.title("🔒 CP-PMO Smartsheet Secure Login")
    st.write("Silakan masuk menggunakan akun Google/Gmail institusi Anda untuk mengakses workspace.")
    
    # Membuat tombol "Login dengan Google" otomatis
    # Sesuaikan redirect_uri dengan URL aplikasi Streamlit Cloud Anda nantinya
    redirect_uri = st.secrets.get("REDIRECT_URI", "http://localhost:8501") 
    result = oauth2.authorize_button(
        name="Continue with Google",
        redirect_uri=redirect_uri,
        scope="openid email profile",
        key="google_auth"
    )
    
    if result and "token" in result:
        st.session_state["auth"] = result["token"]
        # Mengambil informasi profil dari token id
        import base64
        # Decode JWT token untuk mengambil email user
        id_token = result["token"]["id_token"]
        payload = id_token.split(".")[1]
        payload += "=" * ((4 - len(payload) % 4) % 4)
        user_info = json.loads(base64.b64decode(payload).decode("utf-8"))
        st.session_state["user_email"] = user_info.get("email")
        st.session_state["user_name"] = user_info.get("name")
        st.rerun()
    else:
        st.stop()

# Jika sudah berhasil login, ambil data user
user_email = st.session_state["user_email"]
user_name = st.session_state["user_name"]

# ==========================================
# 3. PENGATURAN HAK AKSES (ROLE-BASED ACCESS CONTROL)
# ==========================================
# DAFTAR EMAIL ADMIN (Bisa Add, Update, Delete)
ADMIN_EMAILS = [
    "admin_pmo@gmail.com", 
    "manager_pmo@yourcompany.com"
]

# Cek apakah user saat ini adalah admin atau sekadar viewer (Read-Only)
is_admin = user_email in ADMIN_EMAILS

# Tampilkan info login di sidebar/atas halaman
st.markdown(f"""
    <div class="user-profile">
        👤 Login sebagai: <b>{user_name}</b> ({user_email}) | 
        🔑 Hak Akses: <b>{'🟢 ADMIN (Full Access)' if is_admin else '🔵 TEAM MEMBER (Read-Only)'}</b>
    </div>
""", unsafe_allow_html=True)

# Tombol Logout jika diperlukan
if st.sidebar.button("🚪 Logout Account"):
    del st.session_state["auth"]
    if "master_df" in st.session_state:
        del st.session_state["master_df"]
    st.rerun()

# ==========================================
# 4. FUNGSI INTEGRASI GITHUB API
# ==========================================
def get_github_file():
    try:
        auth_gh = Auth.Token(GITHUB_TOKEN)
        g = Github(auth=auth_gh)
        repo = g.get_repo(REPO_NAME)
        try:
            contents = repo.get_contents(FILE_PATH)
            return repo, contents
        except GithubException as e:
            if e.status == 404:
                repo.create_file(FILE_PATH, "Initial commit for project management", "[]")
                contents = repo.get_contents(FILE_PATH)
                return repo, contents
            else:
                raise e
    except Exception as e:
        st.error(f"⚠️ Gagal terhubung ke GitHub: {e}")
        return None, None

def load_data(contents):
    if "master_df" in st.session_state:
        return st.session_state["master_df"]
        
    if contents is None:
        return pd.DataFrame()
    
    data_str = contents.decoded_content.decode('utf-8')
    data_json = json.loads(data_str)
    
    columns = ["Task ID", "Task Name", "Assigned To", "Status", "Progress (%)", "Start Date", "Due Date", "Notes", "GDrive Link"]
    
    if not data_json:
        df = pd.DataFrame(columns=columns)
    else:
        df = pd.DataFrame(data_json)
    
    for col in columns:
        if col not in df.columns:
            df[col] = ""
            
    st.session_state["master_df"] = df[columns]
    return df[columns]

def save_data_to_github(repo, contents, df, message="Update PMO data via Dashboard"):
    data_json = df.to_json(orient="records")
    repo.update_file(
        path=FILE_PATH,
        message=message,
        content=data_json,
        sha=contents.sha
    )

# Load data utama
repo, contents = get_github_file()
df_tasks = load_data(contents)

if not df_tasks.empty:
    df_tasks["Progress (%)"] = pd.to_numeric(df_tasks["Progress (%)"])

# Pembatasan tab berdasarkan Role Akses
if is_admin:
    tabs_list = ["📊 Grid & Gantt View", "➕ Row Baru / Task", "🔄 Edit Row Item", "❌ Delete Row Item"]
else:
    tabs_list = ["📊 Grid & Gantt View (Read Only)"]

active_tabs = st.tabs(tabs_list)

# ------------------------------------------
# TAB 1: DASHBOARD SUMMARY (Dapat diakses oleh ALL USER)
# ------------------------------------------
with active_tabs[0]:
    st.subheader("📋 CP-PMO Smartsheet Workspace")
    if not df_tasks.empty:
        total_tasks = len(df_tasks)
        avg_progress = df_tasks["Progress (%)"].mean()
        completed_tasks = len(df_tasks[df_tasks["Status"] == "Done"])
        in_progress_tasks = len(df_tasks[df_tasks["Status"] == "In Progress"])
        
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Sheets Row", total_tasks)
        col2.metric("Sheet Avg Progress", f"{avg_progress:.1f}%")
        col3.metric("Completed Status", completed_tasks)
        col4.metric("Active Allocation", in_progress_tasks)
        
        st.markdown("---")
        st.markdown("### 📅 Smartsheet Timeline Split-Gantt")
        
        df_gantt = df_tasks.copy()
        df_gantt["Clean Start"] = pd.to_datetime(df_gantt["Start Date"], errors='coerce')
        df_gantt["Clean Due"] = pd.to_datetime(df_gantt["Due Date"], errors='coerce')
        df_gantt["Clean Start"] = df_gantt["Clean Start"].fillna(pd.Timestamp(datetime.date.today()))
        df_gantt["Clean Due"] = df_gantt["Clean Due"].fillna(df_gantt["Clean Start"] + pd.Timedelta(days=1))
        
        fig_gantt = px.timeline(
            df_gantt, x_start="Clean Start", x_end="Clean Due", y="Task Name",
            color="Status", text="Assigned To", hover_data=["Start Date", "Due Date", "Progress (%)"],
            color_discrete_map={'To Do': '#FF8A8A', 'In Progress': '#7BC9FF', 'Done': '#A3E4D7'}
        )
        fig_gantt.update_layout(plot_bgcolor="white", paper_bgcolor="white", height=340, margin=dict(t=10, b=10, l=10, r=10))
        st.plotly_chart(fig_gantt, use_container_width=True)

        st.markdown("---")
        st.markdown("### 📄 Sheet Interactive Row Grid")
        st.dataframe(
            df_tasks, use_container_width=True, hide_index=True,
            column_config={
                "GDrive Link": st.column_config.LinkColumn("Attachment"),
                "Progress (%)": st.column_config.ProgressColumn("Overall Progress", format="%d%%")
            }
        )
    else:
        st.info("ℹ️ Lembar kerja Anda kosong.")

# ------------------------------------------
# PROTEKSI AMAN: BLOK AKSES JIKA BUKAN ADMIN
# ------------------------------------------
if is_admin:
    # TAB 2: INPUT ROW (Hanya Admin)
    with active_tabs[1]:
        st.subheader("Add New Row Item to Sheet")
        with st.form("input_form", clear_on_submit=True):
            col_a, col_b = st.columns(2)
            with col_a:
                task_name = st.text_input("Task Name / Activity")
                assigned = st.text_input("Assigned To (PIC Name)")
                start_date = st.date_input("Start Date", value=datetime.date.today())
            with col_b:
                status = st.selectbox("Allocation Status", ["To Do", "In Progress", "Done"])
                progress = st.slider("Progress (%)", 0, 100, 0 if status != "Done" else 100)
                due_date = st.date_input("Due Date Target", value=datetime.date.today() + datetime.timedelta(days=7))
                
            gdrive_link = st.text_input("Google Drive Link")
            notes = st.text_area("Row Activity Comments & Notes")
            submit_btn = st.form_submit_button("Insert Row")
            
            if submit_btn:
                if task_name and assigned:
                    new_id = f"TSK-{len(df_tasks) + 1:03d}"
                    new_task = {
                        "Task ID": new_id, "Task Name": task_name, "Assigned To": assigned,
                        "Status": status, "Progress (%)": int(progress), 
                        "Start Date": str(start_date), "Due Date": str(due_date),
                        "Notes": notes, "GDrive Link": gdrive_link
                    }
                    updated_df = pd.concat([df_tasks, pd.DataFrame([new_task])], ignore_index=True)
                    st.session_state["master_df"] = updated_df
                    save_data_to_github(repo, contents, updated_df, message=f"Insert row {new_id} by {user_email}")
                    st.success(f"✔️ Row **{new_id}** sukses ditambahkan oleh {user_name}!")
                    st.rerun()

    # TAB 3: EDIT ROW ITEMS (Hanya Admin)
    with active_tabs[2]:
        st.subheader("Update Sheet Row Values")
        if not df_tasks.empty:
            task_options = [f"{row['Task ID']} - {row['Task Name']}" for _, row in df_tasks.iterrows()]
            selected_option = st.selectbox("Pilih nomor indeks baris", task_options)
            
            if selected_option:
                selected_id = selected_option.split(" - ")[0]
                task_row = df_tasks[df_tasks["Task ID"] == selected_id].iloc[0]
                
                default_start = pd.to_datetime(task_row["Start Date"]).date() if task_row["Start Date"] != "" else datetime.date.today()
                default_due = pd.to_datetime(task_row["Due Date"]).date() if task_row["Due Date"] != "" else datetime.date.today()
                
                with st.form("update_form"):
                    col_u1, col_u2 = st.columns(2)
                    with col_u1:
                        current_status_idx = ["To Do", "In Progress", "Done"].index(task_row["Status"])
                        u_status = st.selectbox("Update Status", ["To Do", "In Progress", "Done"], index=current_status_idx)
                        u_progress = st.slider("Update Progress (%)", 0, 100, int(task_row["Progress (%)"]))
                        u_start = st.date_input("Change Start Date", value=default_start)
                    with col_u2:
                        u_due = st.date_input("Change Due Date", value=default_due)
                        u_gdrive = st.text_input("Change GDrive URL Link", value=task_row["GDrive Link"])
                    
                    u_notes = st.text_area("Change Comments/Notes", value=task_row["Notes"])
                    
                    if u_progress == 100: u_status = "Done"
                    elif u_progress > 0 and u_status == "To Do": u_status = "In Progress"
                    
                    update_btn = st.form_submit_button("Commit Changes")
                    if update_btn:
                        idx = df_tasks[df_tasks["Task ID"] == selected_id].index[0]
                        df_tasks.at[idx, "Status"] = u_status
                        df_tasks.at[idx, "Progress (%)"] = int(u_progress)
                        df_tasks.at[idx, "Start Date"] = str(u_start)
                        df_tasks.at[idx, "Due Date"] = str(u_due)
                        df_tasks.at[idx, "Notes"] = u_notes
                        df_tasks.at[idx, "GDrive Link"] = u_gdrive
                        
                        st.session_state["master_df"] = df_tasks
                        save_data_to_github(repo, contents, df_tasks, message=f"Update row {selected_id} by {user_email}")
                        st.success(f"💾 Perubahan baris data **{selected_id}** sukses disimpan!")
                        st.rerun()

    # TAB 4: DELETE SHEET ROWS (Hanya Admin)
    with active_tabs[3]:
        st.subheader("Remove Selected Row From Worksheet")
        if not df_tasks.empty:
            del_task_options = [f"{row['Task ID']} - {row['Task Name']}" for _, row in df_tasks.iterrows()]
            selected_del_option = st.selectbox("Pilih Baris yang ingin dihapus", del_task_options)
            
            if selected_del_option:
                del_id = selected_del_option.split(" - ")[0]
                del_row = df_tasks[df_tasks["Task ID"] == del_id].iloc[0]
                
                with st.form("delete_form"):
                    confirm_check = st.checkbox("Saya mengonfirmasi untuk melakukan penghapusan data ini")
                    delete_btn = st.form_submit_button("🔴 Delete Selected Row")
                    if delete_btn and confirm_check:
                        filtered_df = df_tasks[df_tasks["Task ID"] != del_id]
                        st.session_state["master_df"] = filtered_df
                        save_data_to_github(repo, contents, filtered_df, message=f"Delete row {del_id} by {user_email}")
                        st.success(f"🗑️ Baris data **{del_id}** sukses dihapus!")
                        st.rerun()
