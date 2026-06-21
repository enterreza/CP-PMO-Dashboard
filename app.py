import streamlit as st
import pandas as pd
import json
import datetime
import plotly.express as px
from github import Github, Auth
from github import GithubException
from streamlit_oauth import OAuth2Component
import base64
import io
import requests
from io import BytesIO

# ==========================================
# 1. KONFIGURASI AWAL & TAMPILAN (SMARTSHEET STYLE)
# ==========================================
st.set_page_config(page_title="CP-PMO Smartsheet Workspace", layout="wide")

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
            white-space: pre-wrap;
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
        div.stDownloadButton > button:first-child {
            background-color: #FFFFFF;
            color: #006644;
            border: 1px solid #006644;
            border-radius: 4px;
            padding: 8px 16px;
            font-weight: 500;
        }
        div.stDownloadButton > button:first-child:hover {
            background-color: #F4F5F7;
            color: #004d33;
            border: 1px solid #004d33;
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

if all(k in st.secrets for k in ["GITHUB_TOKEN", "REPO_NAME", "GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "REDIRECT_URI"]):
    GITHUB_TOKEN = st.secrets["GITHUB_TOKEN"]
    REPO_NAME = st.secrets["REPO_NAME"]
    CLIENT_ID = st.secrets["GOOGLE_CLIENT_ID"]
    CLIENT_SECRET = st.secrets["GOOGLE_CLIENT_SECRET"]
    REDIRECT_URI = st.secrets["REDIRECT_URI"]
else:
    st.error("❌ Konfigurasi Secrets Belum Lengkap di Streamlit Cloud!")
    st.stop()

FILE_PATH = "tasks.json"
AUTHORIZATION_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"

oauth2 = OAuth2Component(
    CLIENT_ID, CLIENT_SECRET, AUTHORIZATION_URL, TOKEN_URL, TOKEN_URL, REVOKE_URL
)

# ==========================================
# 2. PROSES LOGIN / AUTENTIKASI GMAIL
# ==========================================
if "auth" not in st.session_state:
    st.title("🔒 CP-PMO Smartsheet Secure Login")
    st.write("Silakan masuk menggunakan akun Google/Gmail Anda untuk mengakses workspace.")
    
    result = oauth2.authorize_button(
        name="Continue with Google",
        redirect_uri=REDIRECT_URI,
        scope="openid email profile",
        key="google_auth"
    )
    
    if result and "token" in result:
        st.session_state["auth"] = result["token"]
        id_token = result["token"]["id_token"]
        payload = id_token.split(".")[1]
        payload += "=" * ((4 - len(payload) % 4) % 4)
        user_info = json.loads(base64.b64decode(payload).decode("utf-8"))
        st.session_state["user_email"] = user_info.get("email")
        st.session_state["user_name"] = user_info.get("name")
        st.rerun()
    else:
        st.stop()

user_email = st.session_state["user_email"]
user_name = st.session_state["user_name"]

# ==========================================
# 3. PENGATURAN HAK AKSES & LOGO HMD
# ==========================================
ADMIN_EMAILS = [email.lower() for email in ["enter.reza@gmail.com", "admin_pmo@gmail.com"]]
is_admin = user_email.lower() in ADMIN_EMAILS

@st.cache_data
def load_logo_from_github(repo_name, github_token):
    try:
        raw_logo_url = f"https://raw.githubusercontent.com/{repo_name}/main/Logo HMD.png"
        headers = {"Authorization": f"token {github_token}"}
        response = requests.get(raw_logo_url, headers=headers)
        if response.status_code == 200:
            return BytesIO(response.content)
        return None
    except Exception:
        return None

logo_data = load_logo_from_github(REPO_NAME, GITHUB_TOKEN)

col_header1, col_header2 = st.columns([1, 4])
with col_header1:
    if logo_data:
        st.image(logo_data, width=140)
with col_header2:
    st.markdown(f"""
        <div class="user-profile">
            👤 Login: <b>{user_name}</b> ({user_email}) | 
            🔑 Akses: <b>{'🟢 ADMIN (Full Access)' if is_admin else '🔵 TEAM MEMBER (Read-Only)'}</b>
        </div>
    """, unsafe_allow_html=True)

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
                repo.create_file(FILE_PATH, "Initial commit", "[]")
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
    
    # Menambahkan kolom baru: Subtask, Issues/Kendala, Follow Up
    columns = [
        "Task ID", "Project Name", "Task Name", "Subtask", "Assigned To", 
        "Status", "Progress (%)", "Start Date", "Due Date", 
        "Issues/Kendala", "Follow Up/Tindak Lanjut", "Notes", "GDrive Link"
    ]
    
    if not data_json:
        df = pd.DataFrame(columns=columns)
    else:
        df = pd.DataFrame(data_json)
    
    # Pengisian nilai default jika kolom baru belum ada di file JSON lama
    for col in columns:
        if col not in df.columns:
            if col == "Project Name":
                df[col] = "Project Utama"
            else:
                df[col] = ""
            
    st.session_state["master_df"] = df[columns]
    return df[columns]

def save_data_to_github(repo, contents, df, message="Update PMO data via Dashboard"):
    data_json = df.to_json(orient="records")
    repo.update_file(path=FILE_PATH, message=message, content=data_json, sha=contents.sha)

repo, contents = get_github_file()
df_tasks = load_data(contents)

if not df_tasks.empty:
    df_tasks["Progress (%)"] = pd.to_numeric(df_tasks["Progress (%)"])

if is_admin:
    tabs_list = ["📊 Portfolio & Gantt View", "➕ Tambah Proyek / Task Baru", "🔄 Edit Baris Data", "❌ Hapus Baris Data"]
else:
    tabs_list = ["📊 Portfolio & Gantt View (Read Only)"]

active_tabs = st.tabs(tabs_list)

STATUS_OPTIONS = ["To Do", "In Progress", "Pending", "Done"]

# ------------------------------------------
# TAB 1: PORTFOLIO & FILTER GANTT VIEW + DOWNLOAD
# ------------------------------------------
with active_tabs[0]:
    st.subheader("📋 CP-PMO Multi-Project Sheet Workspace")
    
    if not df_tasks.empty:
        available_projects = sorted(df_tasks["Project Name"].unique().tolist())
        
        col_filter1, col_filter2, col_download = st.columns([2, 2, 1])
        with col_filter1:
            project_filter = st.selectbox("📂 Pilih Tampilan Proyek:", ["✨ Tampilkan Semua Proyek"] + available_projects)
        
        if project_filter == "✨ Tampilkan Semua Proyek":
            df_filtered = df_tasks
            report_filename = f"PMO_Portfolio_Report_{datetime.date.today()}.xlsx"
        else:
            df_filtered = df_tasks[df_tasks["Project Name"] == project_filter]
            report_filename = f"PMO_Report_{project_filter.replace(' ', '_')}_{datetime.date.today()}.xlsx"
            
        with col_download:
            st.markdown("<div style='padding-top: 28px;'></div>", unsafe_allow_html=True)
            
            @st.cache_data
            def convert_df_to_excel(df):
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    df.to_excel(writer, index=False, sheet_name='PMO_Data_Report')
                return output.getvalue()
            
            excel_data = convert_df_to_excel(df_filtered)
            
            st.download_button(
                label="📥 Download Report (Excel)",
                data=excel_data,
                file_name=report_filename,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
            
        total_tasks = len(df_filtered)
        avg_progress = df_filtered["Progress (%)"].mean() if total_tasks > 0 else 0
        completed_tasks = len(df_filtered[df_filtered["Status"] == "Done"])
        in_progress_tasks = len(df_filtered[df_filtered["Status"] == "In Progress"])
        pending_tasks = len(df_filtered[df_filtered["Status"] == "Pending"])
        
        col1, col2, col3, col4, col5 = st.columns(5)
        col1.metric("Total Rows Filtered", total_tasks)
        col2.metric("Project Avg Progress", f"{avg_progress:.1f}%")
        col3.metric("Tasks Completed", completed_tasks)
        col4.metric("Active In-Progress", in_progress_tasks)
        col5.metric("Tasks Pending", pending_tasks)
        
        st.markdown("---")
        st.markdown("### 📅 Smartsheet Timeline Multi-Gantt")
        
        if total_tasks > 0:
            df_gantt = df_filtered.copy()
            df_gantt["Clean Start"] = pd.to_datetime(df_gantt["Start Date"], errors='coerce').fillna(pd.Timestamp(datetime.date.today()))
            df_gantt["Clean Due"] = pd.to_datetime(df_gantt["Due Date"], errors='coerce').fillna(df_gantt["Clean Start"] + pd.Timedelta(days=1))
            
            # Label Gantt Chart menggabungkan Task & Subtask jika ada
            df_gantt["Display_Label"] = df_gantt.apply(
                lambda r: f"{r['Task Name']} ({r['Subtask']})" if r['Subtask'] else r['Task Name'], axis=1
            )
            
            if project_filter == "✨ Tampilkan Semua Proyek":
                df_gantt["Gantt_Label"] = df_gantt["Project Name"] + " - " + df_gantt["Display_Label"]
            else:
                df_gantt["Gantt_Label"] = df_gantt["Display_Label"]
                
            fig_gantt = px.timeline(
                df_gantt, x_start="Clean Start", x_end="Clean Due", y="Gantt_Label",
                color="Status", text="Assigned To", hover_data=["Project Name", "Start Date", "Due Date", "Progress (%)", "Issues/Kendala"],
                color_discrete_map={'To Do': '#FF8A8A', 'In Progress': '#7BC9FF', 'Pending': '#FFD966', 'Done': '#A3E4D7'}
            )
            fig_gantt.update_layout(plot_bgcolor="white", paper_bgcolor="white", height=400, margin=dict(t=10, b=10, l=10, r=10), yaxis_title="")
            fig_gantt.update_yaxes(categoryorder="category ascending")
            fig_gantt.update_xaxes(showgrid=True, gridcolor="#E2E4E8")
            fig_gantt.update_yaxes(showgrid=True, gridcolor="#E2E4E8")
            st.plotly_chart(fig_gantt, use_container_width=True)
        else:
            st.info("Tidak ada data kegiatan dalam proyek ini.")

        st.markdown("---")
        st.markdown("### 📄 Sheet Interactive Row Grid")
        st.dataframe(
            df_filtered, use_container_width=True, hide_index=True,
            column_config={
                "GDrive Link": st.column_config.LinkColumn("Attachment"),
                "Progress (%)": st.column_config.ProgressColumn("Overall Progress", format="%d%%")
            }
        )
    else:
        st.info("ℹ️ Lembar kerja Anda kosong.")

# ------------------------------------------
# HAK AKSES KHUSUS ADMINISTRATOR
# ------------------------------------------
if is_admin:
    # TAB 2: TAMBAH PROYEK / TASK BARU
    with active_tabs[1]:
        st.subheader("Add New Project or Task Item")
        existing_projects = sorted(df_tasks["Project Name"].unique().tolist()) if not df_tasks.empty else ["Project Utama"]
        
        with st.form("input_form", clear_on_submit=True):
            col_a, col_b = st.columns(2)
            with col_a:
                project_name_select = st.selectbox("📂 Pilih Projek Eksis (Atau tulis baru):", ["-- Tulis Projek Baru --"] + existing_projects)
                project_name_custom = st.text_input("📝 Tulis Nama Projek Baru:")
                task_name = st.text_input("Task Name / Main Activity")
                subtask_name = st.text_input("Subtask Name (Optional)")
                assigned = st.text_input("Assigned To (PIC Name)")
            with col_b:
                status = st.selectbox("Allocation Status", STATUS_OPTIONS)
                progress = st.slider("Progress (%)", 0, 100, 0 if status != "Done" else 100)
                start_date = st.date_input("Start Date Plan", value=datetime.date.today())
                due_date = st.date_input("Due Date Target", value=datetime.date.today() + datetime.timedelta(days=7))
                gdrive_link = st.text_input("Google Drive Link Documentation")
                
            st.markdown("---")
            col_c, col_d = st.columns(2)
            with col_c:
                issues_val = st.text_area("Issues / Kendala Lapangan")
            with col_d:
                follow_up_val = st.text_area("Follow Up / Tindak Lanjut Solusi")
                
            notes = st.text_area("General Comments & Notes")
            submit_btn = st.form_submit_button("Insert Row to Workspace")
            
            if submit_btn:
                final_project_name = project_name_custom if project_name_select == "-- Tulis Projek Baru --" else project_name_select
                
                if final_project_name.strip() != "" and task_name and assigned:
                    new_id = f"TSK-{len(df_tasks) + 1:03d}"
                    new_task = {
                        "Task ID": new_id, "Project Name": final_project_name.strip(), "Task Name": task_name, 
                        "Subtask": subtask_name, "Assigned To": assigned, "Status": status, "Progress (%)": int(progress), 
                        "Start Date": str(start_date), "Due Date": str(due_date), "Issues/Kendala": issues_val,
                        "Follow Up/Tindak Lanjut": follow_up_val, "Notes": notes, "GDrive Link": gdrive_link
                    }
                    updated_df = pd.concat([df_tasks, pd.DataFrame([new_task])], ignore_index=True)
                    
                    st.session_state["master_df"] = updated_df
                    save_data_to_github(repo, contents, updated_df, message=f"Insert row {new_id}")
                    
                    st.success(f"🎉 Sukses! Task baru **{task_name}** ({new_id}) berhasil disimpan.")
                    st.balloons()
                    st.rerun()
                else:
                    st.error("❌ Nama Projek, Nama Task, dan PIC wajib diisi!")

    # TAB 3: EDIT BARIS DATA
    with active_tabs[2]:
        st.subheader("Update Sheet Row Values")
        if not df_tasks.empty:
            task_options = [f"{row['Task ID']} - [{row['Project Name']}] {row['Task Name']} ({row['Subtask']})" for _, row in df_tasks.iterrows()]
            selected_option = st.selectbox("Pilih nomor indeks baris tugas:", task_options)
            
            if selected_option:
                selected_id = selected_option.split(" - ")[0]
                task_row = df_tasks[df_tasks["Task ID"] == selected_id].iloc[0]
                
                default_start = pd.to_datetime(task_row["Start Date"]).date() if task_row["Start Date"] != "" else datetime.date.today()
                default_due = pd.to_datetime(task_row["Due Date"]).date() if task_row["Due Date"] != "" else datetime.date.today()
                
                with st.form("update_form"):
                    st.info(f"Mengedit ID: {task_row['Task ID']} | Proyek: **{task_row['Project Name']}**")
                    col_u1, col_u2 = st.columns(2)
                    with col_u1:
                        u_project = st.text_input("Ubah Nama Proyek", value=task_row["Project Name"])
                        u_task_name = st.text_input("Ubah Nama Task", value=task_row["Task Name"])
                        u_subtask = st.text_input("Ubah Subtask", value=task_row["Subtask"])
                        current_status_idx = STATUS_OPTIONS.index(task_row["Status"]) if task_row["Status"] in STATUS_OPTIONS else 0
                        u_status = st.selectbox("Update Status", STATUS_OPTIONS, index=current_status_idx)
                    with col_u2:
                        u_assigned = st.text_input("Ubah PIC", value=task_row["Assigned To"])
                        u_progress = st.slider("Update Progress (%)", 0, 100, int(task_row["Progress (%)"]))
                        u_start = st.date_input("Change Start Date", value=default_start)
                        u_due = st.date_input("Change Due Date", value=default_due)
                    
                    st.markdown("---")
                    col_u3, col_u4 = st.columns(2)
                    with col_u3:
                        u_issues = st.text_area("Change Issues / Kendala", value=task_row["Issues/Kendala"])
                    with col_u4:
                        u_follow_up = st.text_area("Change Follow Up / Tindak Lanjut", value=task_row["Follow Up/Tindak Lanjut"])
                        
                    u_gdrive = st.text_input("Change GDrive URL Link", value=task_row["GDrive Link"])
                    u_notes = st.text_area("Change Comments/Notes", value=task_row["Notes"])
                    
                    if u_progress == 100: u_status = "Done"
                    
                    update_btn = st.form_submit_button("Commit Changes")
                    if update_btn:
                        idx = df_tasks[df_tasks["Task ID"] == selected_id].index[0]
                        df_tasks.at[idx, "Project Name"] = u_project
                        df_tasks.at[idx, "Task Name"] = u_task_name
                        df_tasks.at[idx, "Subtask"] = u_subtask
                        df_tasks.at[idx, "Assigned To"] = u_assigned
                        df_tasks.at[idx, "Status"] = u_status
                        df_tasks.at[idx, "Progress (%)"] = int(u_progress)
                        df_tasks.at[idx, "Start Date"] = str(u_start)
                        df_tasks.at[idx, "Due Date"] = str(u_due)
                        df_tasks.at[idx, "Issues/Kendala"] = u_issues
                        df_tasks.at[idx, "Follow Up/Tindak Lanjut"] = u_follow_up
                        df_tasks.at[idx, "Notes"] = u_notes
                        df_tasks.at[idx, "GDrive Link"] = u_gdrive
                        
                        st.session_state["master_df"] = df_tasks
                        save_data_to_github(repo, contents, df_tasks, message=f"Update row {selected_id}")
                        st.success(f"💾 Perubahan baris data **{selected_id}** sukses disimpan!")
                        st.rerun()
        else:
            st.info("ℹ️ Tidak ada data untuk dimodifikasi.")

    # TAB 4: HAPUS BARIS DATA
    with active_tabs[3]:
        st.subheader("Remove Selected Row From Workspace")
        if not df_tasks.empty:
            del_task_options = [f"{row['Task ID']} - [{row['Project Name']}] {row['Task Name']}" for _, row in df_tasks.iterrows()]
            selected_del_option = st.selectbox("Pilih Baris yang ingin dihapus:", del_task_options)
            
            if selected_del_option:
                del_id = selected_del_option.split(" - ")[0]
                del_row = df_tasks[df_tasks["Task ID"] == del_id].iloc[0]
                
                with st.form("delete_form"):
                    st.warning(f"Apakah Anda yakin menghapus Task dari Proyek: {del_row['Project Name']}?")
                    confirm_check = st.checkbox("Saya mengonfirmasi untuk melakukan penghapusan data ini")
                    delete_btn = st.form_submit_button("🔴 Delete Selected Row")
                    if delete_btn and confirm_check:
                        filtered_df = df_tasks[df_tasks["Task ID"] != del_id]
                        st.session_state["master_df"] = filtered_df
                        save_data_to_github(repo, contents, filtered_df, message=f"Delete row {del_id}")
                        st.success(f"🗑️ Baris data **{del_id}** sukses dihapus!")
                        st.rerun()
