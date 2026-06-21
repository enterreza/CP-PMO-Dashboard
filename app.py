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

# ==========================================
# 1. KONFIGURASI AWAL & TAMPILAN (SMARTSHEET STYLE)
# ==========================================
st.set_page_config(page_title="CP-PMO Smartsheet Workspace", layout="wide")

# Injeksi CSS Khusus untuk Mengubah UI Menjadi Gaya Smartsheet (Clean, Grid-based, Muted Colors)
st.markdown("""
    <style>
        /* Mengubah font utama aplikasi */
        html, body, [data-testid="stMarkdownContainer"] {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            color: #333333;
        }
        
        /* Mengubah gaya navigasi Tab ala Smartsheet Toolbar */
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
            color: #006644 !important; /* Hijau khas Smartsheet */
            box-shadow: 0px 2px 4px rgba(0,0,0,0.05);
        }
        
        /* Tombol Utama Bergaya Smartsheet */
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
        
        /* Tombol download Streamlit agar serasi dengan tema */
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

# ------------------------------------------
# KONFIGURASI SECRETS (GITHUB & GOOGLE OAUTH)
# ------------------------------------------
if all(k in st.secrets for k in ["GITHUB_TOKEN", "REPO_NAME", "GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "REDIRECT_URI"]):
    GITHUB_TOKEN = st.secrets["GITHUB_TOKEN"]
    REPO_NAME = st.secrets["REPO_NAME"]
    CLIENT_ID = st.secrets["GOOGLE_CLIENT_ID"]
    CLIENT_SECRET = st.secrets["GOOGLE_CLIENT_SECRET"]
    REDIRECT_URI = st.secrets["REDIRECT_URI"]
else:
    st.error("❌ Konfigurasi Secrets Belum Lengkap!")
    st.info("Harap periksa kembali GITHUB_TOKEN, REPO_NAME, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, dan REDIRECT_URI di Dashboard Secrets Streamlit Cloud Anda.")
    st.stop()

FILE_PATH = "tasks.json"
AUTHORIZATION_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"

# Inisialisasi komponen OAuth2 secara eksplisit dengan redirect URI
oauth2 = OAuth2Component(
    client_id=CLIENT_ID,
    client_secret=CLIENT_SECRET,
    authorize_endpoint=AUTHORIZATION_URL,
    token_endpoint=TOKEN_URL,
    refresh_token_endpoint=TOKEN_URL,
    revoke_endpoint=REVOKE_URL
)

# ==========================================
# 2. PROSES LOGIN / AUTENTIKASI GMAIL
# ==========================================
if "auth" not in st.session_state:
    st.title("🔒 CP-PMO Smartsheet Secure Login")
    st.write("Silakan masuk menggunakan akun Google/Gmail institusi Anda untuk mengakses workspace.")
    
    result = oauth2.authorize_button(
        name="Continue with Google",
        redirect_uri=REDIRECT_URI,
        scope="openid email profile",
        key="google_auth"
    )
    
    if result and "token" in result:
        st.session_state["auth"] = result["token"]
        # Decode JWT token untuk mengambil data email pengguna
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
# 3. PENGATURAN HAK AKSES (ROLE-BASED LOWERCASE CHECK)
# ==========================================
ADMIN_EMAILS = [email.lower() for email in [
    "enter.reza@gmail.com", 
    "admin_pmo@gmail.com"
]]

is_admin = user_email.lower() in ADMIN_EMAILS

st.markdown(f"""
    <div class="user-profile">
        👤 Login sebagai: <b>{user_name}</b> ({user_email}) | 
        🔑 Hak Akses: <b>{'🟢 ADMIN (Full Access)' if is_admin else '🔵 TEAM MEMBER (Read-Only)'}</b>
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
    
    columns = ["Task ID", "Project Name", "Task Name", "Assigned To", "Status", "Progress (%)", "Start Date", "Due Date", "Notes", "GDrive Link"]
    
    if not data_json:
        df = pd.DataFrame(columns=columns)
    else:
        df = pd.DataFrame(data_json)
    
    # Migrasi aman jika data json lama belum memiliki kolom 'Project Name'
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
    repo.update_file(
        path=FILE_PATH,
        message=message,
        content=data_json,
        sha=contents.sha
    )

# Memuat data
repo, contents = get_github_file()
df_tasks = load_data(contents)

if not df_tasks.empty:
    df_tasks["Progress (%)"] = pd.to_numeric(df_tasks["Progress (%)"])

# Pembagian Tab Navigasi berdasarkan Role
if is_admin:
    tabs_list = ["📊 Portfolio & Gantt View", "➕ Tambah Proyek / Task Baru", "🔄 Edit Baris Data", "❌ Hapus Baris Data"]
else:
    tabs_list = ["📊 Portfolio & Gantt View (Read Only)"]

active_tabs = st.tabs(tabs_list)

# ------------------------------------------
# TAB 1: PORTFOLIO & FILTER GANTT VIEW + EKSPOR REPORT
# ------------------------------------------
with active_tabs[0]:
    st.subheader("📋 CP-PMO Multi-Project Sheet Workspace")
    
    if not df_tasks.empty:
        available_projects = sorted(df_tasks["Project Name"].unique().tolist())
        
        # Grid Toolbar ala Smartsheet
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
            
            # Pemrosesan konversi Excel berkecepatan tinggi dengan Caching
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
            
        # Kalkulasi Indikator Metrik
        total_tasks = len(df_filtered)
        avg_progress = df_filtered["Progress (%)"].mean() if total_tasks > 0 else 0
        completed_tasks = len(df_filtered[df_filtered["Status"] == "Done"])
        in_progress_tasks = len(df_filtered[df_filtered["Status"] == "In Progress"])
        
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Rows Filtered", total_tasks)
        col2.metric("Project Avg Progress", f"{avg_progress:.1f}%")
        col3.metric("Tasks Completed", completed_tasks)
        col4.metric("Active In-Progress", in_progress_tasks)
        
        st.markdown("---")
        st.markdown("### 📅 Smartsheet Timeline Multi-Gantt")
        
        if total_tasks > 0:
            df_gantt = df_filtered.copy()
            df_gantt["Clean Start"] = pd.to_datetime(df_gantt["Start Date"], errors='coerce').fillna(pd.Timestamp(datetime.date.today()))
            df_gantt["Clean Due"] = pd.to_datetime(df_gantt["Due Date"], errors='coerce').fillna(df_gantt["Clean Start"] + pd.Timedelta(days=1))
            
            if project_filter == "✨ Tampilkan Semua Proyek":
                df_gantt["Gantt_Label"] = df_gantt["Project Name"] + " - " + df_gantt["Task Name"]
            else:
                df_gantt["Gantt_Label"] = df_gantt["Task Name"]
                
            fig_gantt = px.timeline(
                df_gantt, x_start="Clean Start", x_end="Clean Due", y="Gantt_Label",
                color="Status", text="Assigned To", hover_data=["Project Name", "Start Date", "Due Date", "Progress (%)"],
                # Muted & Premium Soft Color Palette
                color_discrete_map={'To Do': '#FF8A8A', 'In Progress': '#7BC9FF', 'Done': '#A3E4D7'}
            )
            fig_gantt.update_layout(
                plot_bgcolor="white", paper_bgcolor="white", height=380, 
                margin=dict(t=10, b=10, l=10, r=10), yaxis_title=""
            )
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
                "GDrive Link": st.column_config.LinkColumn("Attachment/Link File"),
                "Progress (%)": st.column_config.ProgressColumn("Overall Progress", format="%d%%")
            }
        )
    else:
        st.info("ℹ️ Lembar kerja Anda kosong. Silakan tambahkan item pertama Anda di bawah.")

# ------------------------------------------
# HAK AKSES KHUSUS ADMINISTRATOR
# ------------------------------------------
if is_admin:
    # TAB 2: TAMBAH PROYEK / TASK BARU (Dengan Notifikasi Berhasil)
    with active_tabs[1]:
        st.subheader("Add New Project or Task Item")
        existing_projects = sorted(df_tasks["Project Name"].unique().tolist()) if not df_tasks.empty else ["Project Utama"]
        
        with st.form("input_form", clear_on_submit=True):
            col_a, col_b = st.columns(2)
            with col_a:
                project_name_select = st.selectbox("📂 Pilih Projek Eksis (Atau tulis baru di kolom bawah):", ["-- Tulis Projek Baru --"] + existing_projects)
                project_name_custom = st.text_input("📝 Tulis Nama Projek Baru (Jika memilih opsi tulis baru di atas):")
                task_name = st.text_input("Task Name / Activity Description")
                assigned = st.text_input("Assigned To (PIC Name)")
            with col_b:
                status = st.selectbox("Allocation Status", ["To Do", "In Progress", "Done"])
                progress = st.slider("Progress (%)", 0, 100, 0 if status != "Done" else 100)
                start_date = st.date_input("Start Date Plan", value=datetime.date.today())
                due_date = st.date_input("Due Date Target", value=datetime.date.today() + datetime.timedelta(days=7))
                
            gdrive_link = st.text_input("Google Drive Link Documentation")
            notes = st.text_area("Row Comments & Notes")
            submit_btn = st.form_submit_button("Insert Row to Workspace")
            
            if submit_btn:
                final_project_name = project_name_custom if project_name_select == "-- Tulis Projek Baru --" else project_name_select
                
                if final_project_name.strip() != "" and task_name and assigned:
                    new_id = f"TSK-{len(df_tasks) + 1:03d}"
                    new_task = {
                        "Task ID": new_id, "Project Name": final_project_name.strip(), "Task Name": task_name, 
                        "Assigned To": assigned, "Status": status, "Progress (%)": int(progress), 
                        "Start Date": str(start_date), "Due Date": str(due_date), "Notes": notes, "GDrive Link": gdrive_link
                    }
                    updated_df = pd.concat([df_tasks, pd.DataFrame([new_task])], ignore_index=True)
                    
                    # Sinkronisasi Instan ke memori state lokal & push background ke GitHub
                    st.session_state["master_df"] = updated_df
                    save_data_to_github(repo, contents, updated_df, message=f"Insert row {new_id} for {final_project_name}")
                    
                    st.success(f"🎉 Sukses! Task baru **{task_name}** ({new_id}) berhasil disimpan ke dalam Proyek {final_project_name}.")
                    st.balloons()
                    st.rerun()
                else:
                    st.error("❌ Validasi Error: Nama Projek, Nama Task, dan PIC wajib diisi!")

    # TAB 3: EDIT BARIS DATA (Dengan Notifikasi Berhasil)
    with active_tabs[2]:
        st.subheader("Update Sheet Row Values")
        if not df_tasks.empty:
            task_options = [f"{row['Task ID']} - [{row['Project Name']}] {row['Task Name']}" for _, row in df_tasks.iterrows()]
            selected_option = st.selectbox("Pilih nomor indeks baris tugas:", task_options)
            
            if selected_option:
                selected_id = selected_option.split(" - ")[0]
                task_row = df_tasks[df_tasks["Task ID"] == selected_id].iloc[0]
                
                default_start = pd.to_datetime(task_row["Start Date"]).date() if task_row["Start Date"] != "" else datetime.date.today()
                default_due = pd.to_datetime(task_row["Due Date"]).date() if task_row["Due Date"] != "" else datetime.date.today()
                
                with st.form("update_form"):
                    st.info(f"Mengedit ID: {task_row['Task ID']} | Proyek Asal: **{task_row['Project Name']}**")
                    col_u1, col_u2 = st.columns(2)
                    with col_u1:
                        u_project = st.text_input("Ubah/Edit Nama Proyek", value=task_row["Project Name"])
                        u_task_name = st.text_input("Ubah Nama Task", value=task_row["Task Name"])
                        current_status_idx = ["To Do", "In Progress", "Done"].index(task_row["Status"])
                        u_status = st.selectbox("Update Status", ["To Do", "In Progress", "Done"], index=current_status_idx)
                    with col_u2:
                        u_progress = st.slider("Update Progress (%)", 0, 100, int(task_row["Progress (%)"]))
                        u_start = st.date_input("Change Start Date", value=default_start)
                        u_due = st.date_input("Change Due Date", value=default_due)
                    
                    u_gdrive = st.text_input("Change GDrive URL Link", value=task_row["GDrive Link"])
                    u_notes = st.text_area("Change Comments/Notes", value=task_row["Notes"])
                    
                    if u_progress == 100: u_status = "Done"
                    elif u_progress > 0 and u_status == "To Do": u_status = "In Progress"
                    
                    update_btn = st.form_submit_button("Commit Changes")
                    if update_btn:
                        idx = df_tasks[df_tasks["Task ID"] == selected_id].index[0]
                        df_tasks.at[idx, "Project Name"] = u_project
                        df_tasks.at[idx, "Task Name"] = u_task_name
                        df_tasks.at[idx, "Status"] = u_status
                        df_tasks.at[idx, "Progress (%)"] = int(u_progress)
                        df_tasks.at[idx, "Start Date"] = str(u_start)
                        df_tasks.at[idx, "Due Date"] = str(u_due)
                        df_tasks.at[idx, "Notes"] = u_notes
                        df_tasks.at[idx, "GDrive Link"] = u_gdrive
                        
                        st.session_state["master_df"] = df_tasks
                        save_data_to_github(repo, contents, df_tasks, message=f"Update row {selected_id}")
                        st.success(f"💾 Sukses! Perubahan baris data **{selected_id}** berhasil diperbarui.")
                        st.rerun()
        else:
            st.info("ℹ️ Tidak ada data untuk dimodifikasi.")

    # TAB 4: HAPUS BARIS DATA (Dengan Notifikasi Berhasil)
    with active_tabs[3]:
        st.subheader("Remove Selected Row From Worksheet")
        if not df_tasks.empty:
            del_task_options = [f"{row['Task ID']} - [{row['Project Name']}] {row['Task Name']}" for _, row in df_tasks.iterrows()]
            selected_del_option = st.selectbox("Pilih Baris yang ingin dihapus secara Permanen", del_task_options, key="del_select")
            
            if selected_del_option:
                del_id = selected_del_option.split(" - ")[0]
                del_row = df_tasks[df_tasks["Task ID"] == del_id].iloc[0]
                
                st.warning(f"⚠️ **PERINGATAN SISTEM:** Anda akan menghapus baris data berikut dari lembar kerja secara permanen:")
                st.code(f"Row ID: {del_row['Task ID']}\nProject: {del_row['Project Name']}\nTask Title: {del_row['Task Name']}")
                
                with st.form("delete_form"):
                    confirm_check = st.checkbox("Saya mengonfirmasi untuk melakukan penghapusan data ini")
                    delete_btn = st.form_submit_button("🔴 Delete Selected Row")
                    
                    if delete_btn:
                        if confirm_check:
                            filtered_df = df_tasks[df_tasks["Task ID"] != del_id]
                            st.session_state["master_df"] = filtered_df
                            save_data_to_github(repo, contents, filtered_df, message=f"Delete row {del_id}")
                            st.success(f"🗑️ Sukses! Baris data **{del_id}** telah berhasil dihapus secara permanen.")
                            st.rerun()
                        else:
                            st.error("❌ Batalkan Aksi! Kotak persetujuan konfirmasi wajib dicentang.")
        else:
            st.info("ℹ️ Tidak ada data tugas yang tersedia untuk bisa dihapus.")
