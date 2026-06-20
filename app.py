import streamlit as st
import pandas as pd
import json
import datetime
import plotly.express as px
from github import Github, Auth
from github import GithubException

# ==========================================
# 1. KONFIGURASI AWAL & TAMPILAN
# ==========================================
st.set_page_config(page_title="CP-PMO Dashboard 2.0", layout="wide")

# Path file di repositori GitHub
FILE_PATH = "tasks.json"  

# Mengambil kredensial dari Streamlit Secrets
if "GITHUB_TOKEN" in st.secrets and "REPO_NAME" in st.secrets:
    GITHUB_TOKEN = st.secrets["GITHUB_TOKEN"]
    REPO_NAME = st.secrets["REPO_NAME"]
else:
    st.error("❌ Konfigurasi Secrets (GITHUB_TOKEN / REPO_NAME) belum diatur di Streamlit Cloud.")
    st.info("Silakan ke Dashboard Streamlit Cloud -> Settings -> Secrets, lalu tambahkan token Anda.")
    st.stop()

# ==========================================
# 2. FUNGSI INTEGRASI GITHUB API
# ==========================================
def get_github_file():
    """Mengambil file data tasks.json langsung dari repositori GitHub"""
    try:
        auth = Auth.Token(GITHUB_TOKEN)
        g = Github(auth=auth)
        repo = g.get_repo(REPO_NAME)
        try:
            contents = repo.get_contents(FILE_PATH)
            return repo, contents
        except GithubException as e:
            # Jika file 'tasks.json' belum ada di repo, buat baru secara otomatis
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
    """Mengonversi isi file JSON dari GitHub menjadi Pandas DataFrame"""
    if contents is None:
        return pd.DataFrame()
    
    data_str = contents.decoded_content.decode('utf-8')
    data_json = json.loads(data_str)
    
    # Kerangka kolom master (termasuk fitur baru)
    columns = ["Task ID", "Task Name", "Assigned To", "Status", "Progress (%)", "Start Date", "Due Date", "Notes", "GDrive Link"]
    
    if not data_json:
        return pd.DataFrame(columns=columns)
        
    df = pd.DataFrame(data_json)
    
    # Memastikan kolom baru tetap ada meskipun baris data lama belum memilikinya
    for col in columns:
        if col not in df.columns:
            df[col] = ""
            
    return df[columns]

def save_data_to_github(repo, contents, df):
    """Menyimpan/Push kembali DataFrame terbaru ke file JSON di GitHub"""
    data_json = df.to_json(orient="records")
    repo.update_file(
        path=FILE_PATH,
        message="Update PMO data via Dashboard",
        content=data_json,
        sha=contents.sha
    )
    st.success("💾 Data berhasil disinkronisasi dan disimpan ke GitHub!")
    st.rerun()

# ==========================================
# 3. ALUR UTAMA APLIKASI
# ==========================================
repo, contents = get_github_file()
df_tasks = load_data(contents)

st.title("🚀 CP-PMO Dashboard 2.0")
st.write("Sistem manajemen tugas terintegrasi langsung dengan database repositori GitHub Anda.")

if not df_tasks.empty:
    df_tasks["Progress (%)"] = pd.to_numeric(df_tasks["Progress (%)"])

# Membuat Tab Navigasi Antarmuka
tab_summary, tab_input, tab_update = st.tabs(["📊 Summary & Analytics", "➕ Add New Task", "🔄 Update Task"])

# ------------------------------------------
# TAB 1: DASHBOARD SUMMARY
# ------------------------------------------
with tab_summary:
    st.subheader("Project Key Performance Indicators")
    
    if not df_tasks.empty:
        # Menghitung Metrik Utama
        total_tasks = len(df_tasks)
        avg_progress = df_tasks["Progress (%)"].mean()
        completed_tasks = len(df_tasks[df_tasks["Status"] == "Done"])
        in_progress_tasks = len(df_tasks[df_tasks["Status"] == "In Progress"])
        
        # Menampilkan Metrics Cards
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Tasks", total_tasks)
        col2.metric("Average Progress", f"{avg_progress:.1f}%")
        col3.metric("Tasks Completed", completed_tasks)
        col4.metric("Tasks In Progress", in_progress_tasks)
        
        st.markdown("---")
        
        # Grafik Distribusi Progress per Task
        st.markdown("**Progress per Task**")
        fig_prog = px.bar(
            df_tasks, 
            x='Task Name', 
            y='Progress (%)', 
            color='Status',
            text='Progress (%)',
            hover_data=["Start Date", "Due Date", "Assigned To"],
            color_discrete_map={'To Do': '#ff4b4b', 'In Progress': '#00a3e0', 'Done': '#00de6a'}
        )
        fig_prog.update_layout(margin=dict(t=20, b=20, l=20, r=20), height=350)
        fig_prog.update_traces(textposition='outside')
        st.plotly_chart(fig_prog, use_container_width=True)

        st.markdown("---")
        st.markdown("**Master Task Table**")
        st.dataframe(df_tasks, use_container_width=True, hide_index=True)
    else:
        st.info("ℹ️ Database kosong. Silakan masuk ke tab **Add New Task** untuk menambahkan tugas pertama Anda.")

# ------------------------------------------
# TAB 2: INPUT TASK BARU
# ------------------------------------------
with tab_input:
    st.subheader("Input Data Project Baru")
    with st.form("input_form", clear_on_submit=True):
        col_a, col_b = st.columns(2)
        with col_a:
            task_name = st.text_input("Nama Task")
            assigned = st.text_input("PIC (Assigned To)")
            start_date = st.date_input("Start Date", value=datetime.date.today())
            due_date = st.date_input("Due Date", value=datetime.date.today())
        with col_b:
            status = st.selectbox("Status", ["To Do", "In Progress", "Done"])
            progress = st.slider("Progress (%)", 0, 100, 0 if status != "Done" else 100)
            gdrive_link = st.text_input("Link Google Drive (URL)")
            
        notes = st.text_area("Notes (Freetext Description)")
        
        submit_btn = st.form_submit_button("Tambah Task")
        
        if submit_btn:
            if task_name and assigned:
                # Membuat format Task ID otomatis
                new_id = f"TSK-{len(df_tasks) + 1:03d}"
                
                new_task = {
                    "Task ID": new_id,
                    "Task Name": task_name,
                    "Assigned To": assigned,
                    "Status": status,
                    "Progress (%)": int(progress),
                    "Start Date": str(start_date),
                    "Due Date": str(due_date),
                    "Notes": notes,
                    "GDrive Link": gdrive_link
                }
                
                updated_df = pd.concat([df_tasks, pd.DataFrame([new_task])], ignore_index=True)
                save_data_to_github(repo, contents, updated_df)
            else:
                st.error("❌ Kolom 'Nama Task' dan 'PIC' wajib diisi!")

# ------------------------------------------
# TAB 3: UPDATE TASK & PROGRESS
# ------------------------------------------
with tab_update:
    st.subheader("Modify Existing Task Status & Progress")
    
    if not df_tasks.empty:
        # Dropdown pilihan task berdasarkan ID dan Nama
        task_options = [f"{row['Task ID']} - {row['Task Name']}" for _, row in df_tasks.iterrows()]
        selected_option = st.selectbox("Pilih Task untuk di-update", task_options)
        
        if selected_option:
            selected_id = selected_option.split(" - ")[0]
            task_row = df_tasks[df_tasks["Task ID"] == selected_id].iloc[0]
            
            # --- PROTEKSI ERROR TANGGAL KOSONG (NaT / Blank String) ---
            if task_row["Start Date"] == "" or pd.isna(task_row["Start Date"]):
                default_start = datetime.date.today()
            else:
                default_start = pd.to_datetime(task_row["Start Date"]).date()

            if task_row["Due Date"] == "" or pd.isna(task_row["Due Date"]):
                default_due = datetime.date.today()
            else:
                default_due = pd.to_datetime(task_row["Due Date"]).date()
            # -----------------------------------------------------------
            
            with st.form("update_form"):
                st.info(f"Mengedit Task: **{task_row['Task Name']}** | PIC: *{task_row['Assigned To']}*")
                
                col_u1, col_u2 = st.columns(2)
                with col_u1:
                    current_status_idx = ["To Do", "In Progress", "Done"].index(task_row["Status"])
                    u_status = st.selectbox("Update Status", ["To Do", "In Progress", "Done"], index=current_status_idx)
                    u_progress = st.slider("Update Progress (%)", 0, 100, int(task_row["Progress (%)"]))
                    u_start = st.date_input("Update Start Date", value=default_start)
                with col_u2:
                    u_due = st.date_input("Update Due Date", value=default_due)
                    u_gdrive = st.text_input("Update Link GDrive", value=task_row["GDrive Link"])
                
                u_notes = st.text_area("Update Notes (Freetext)", value=task_row["Notes"])
                
                # Otomatisasi logika status jika slider digeser
                if u_progress == 100:
                    u_status = "Done"
                elif u_progress > 0 and u_status == "To Do":
                    u_status = "In Progress"
                
                update_btn = st.form_submit_button("Simpan Perubahan")
                
                if update_btn:
                    # Ambil indeks baris data dan update isinya
                    idx = df_tasks[df_tasks["Task ID"] == selected_id].index[0]
                    df_tasks.at[idx, "Status"] = u_status
                    df_tasks.at[idx, "Progress (%)"] = int(u_progress)
                    df_tasks.at[idx, "Start Date"] = str(u_start)
                    df_tasks.at[idx, "Due Date"] = str(u_due)
                    df_tasks.at[idx, "Notes"] = u_notes
                    df_tasks.at[idx, "GDrive Link"] = u_gdrive
                    
                    save_data_to_github(repo, contents, df_tasks)
    else:
        st.info("ℹ️ Tidak ada data tugas yang tersedia untuk diperbarui.")
