import streamlit as st
import pandas as pd
import json
import plotly.express as px
from github import Github
from github import GithubException

# ==========================================
# 1. KONFIGURASI AWAL & TAMPILAN
# ==========================================
st.set_page_config(page_title="Project Management Dashboard", layout="wide")

# Path file penyimpanan data di dalam repositori GitHub Anda
FILE_PATH = "tasks.json"  

# Mengambil kredensial dari Streamlit Advanced Settings (Secrets)
if "GITHUB_TOKEN" in st.secrets and "REPO_NAME" in st.secrets:
    GITHUB_TOKEN = st.secrets["GITHUB_TOKEN"]
    REPO_NAME = st.secrets["REPO_NAME"]
else:
    st.error("❌ Konfigurasi Secrets (GITHUB_TOKEN / REPO_NAME) belum diatur di Streamlit Cloud Advanced Settings.")
    st.info("Silakan ke Dashboard Streamlit Cloud -> Settings -> Secrets, lalu tambahkan token Anda.")
    st.stop()

# ==========================================
# 2. FUNGSI INTEGRASI GITHUB API
# ==========================================
def get_github_file():
    """Mengambil file data tasks.json langsung dari repositori GitHub"""
    try:
        # Menggunakan class Auth agar sesuai dengan standar PyGithub terbaru
        from github import Auth
        
        auth = Auth.Token(GITHUB_TOKEN)
        g = Github(auth=auth)
        repo = g.get_repo(REPO_NAME)
        try:
            contents = repo.get_contents(FILE_PATH)
            return repo, contents
        except GithubException as e:
            # Jika file 'tasks.json' belum ada di repo, buat baru secara otomatis dengan array kosong
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
    
    # Jika file kosong, siapkan struktur kolom default
    if not data_json:
        return pd.DataFrame(columns=["Task ID", "Task Name", "Assigned To", "Status", "Progress (%)", "Due Date"])
        
    return pd.DataFrame(data_json)

def save_data_to_github(repo, contents, df):
    """Menyimpan/Push kembali DataFrame terbaru ke file JSON di GitHub"""
    data_json = df.to_json(orient="records")
    repo.update_file(
        path=FILE_PATH,
        message="Update task data via Streamlit Dashboard",
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

st.title("🚀 Project Management Dashboard")
st.write("Sistem manajemen tugas terintegrasi langsung dengan database repositori GitHub Anda.")

# Memastikan tipe data progress adalah numerik agar aman saat divisualisasikan
if not df_tasks.empty:
    df_tasks["Progress (%)"] = pd.to_numeric(df_tasks["Progress (%)"])

# Membuat Tab Navigasi Antarmuka
tab_summary, tab_input, tab_update = st.tabs(["📊 Summary & Analytics", "➕ Add New Task", "🔄 Update Progress"])

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
        
        # Tata Letak Grafik/Visualisasi
        col_chart1, col_chart2 = st.columns(2)
        
        with col_chart1:
            st.markdown("**Distribution of Task Status**")
            fig_status = px.pie(
                df_tasks, 
                names='Status', 
                color='Status',
                color_discrete_map={'To Do': '#ff4b4b', 'In Progress': '#00a3e0', 'Done': '#00de6a'}
            )
            fig_status.update_layout(margin=dict(t=20, b=20, l=20, r=20), height=300)
            st.plotly_chart(fig_status, use_container_width=True)
            
        with col_chart2:
            st.markdown("**Progress per Task**")
            fig_prog = px.bar(
                df_tasks, 
                x='Task Name', 
                y='Progress (%)', 
                color='Status',
                text='Progress (%)',
                color_discrete_map={'To Do': '#ff4b4b', 'In Progress': '#00a3e0', 'Done': '#00de6a'}
            )
            fig_prog.update_layout(margin=dict(t=20, b=20, l=20, r=20), height=300)
            fig_prog.update_traces(textposition='outside')
            st.plotly_chart(fig_prog, use_container_width=True)

        st.markdown("---")
        st.markdown("**All Active Tasks Table**")
        st.dataframe(df_tasks, use_container_width=True, hide_index=True)
    else:
        st.info("ℹ️ Database kosong. Silakan masuk ke tab **Add New Task** untuk menambahkan tugas pertama Anda.")

# ------------------------------------------
# TAB 2: INPUT TASK BARU
# ------------------------------------------
with tab_input:
    st.subheader("Create a New Project Task")
    with st.form("input_form", clear_on_submit=True):
        task_name = st.text_input("Task Name")
        assigned_to = st.text_input("Assigned To")
        status = st.selectbox("Initial Status", ["To Do", "In Progress", "Done"])
        progress = st.slider("Initial Progress (%)", 0, 100, 0 if status != "Done" else 100)
        due_date = st.date_input("Due Date")
        
        submit_btn = st.form_submit_button("Add Task")
        
        if submit_btn:
            if task_name and assigned_to:
                # Membuat format Task ID otomatis (contoh: TSK-001)
                new_id = f"TSK-{len(df_tasks) + 1:03d}"
                
                new_task = {
                    "Task ID": new_id,
                    "Task Name": task_name,
                    "Assigned To": assigned_to,
                    "Status": status,
                    "Progress (%)": int(progress),
                    "Due Date": str(due_date)
                }
                
                # Menggabungkan data baru dan melakukan push ke repositori GitHub
                updated_df = pd.concat([df_tasks, pd.DataFrame([new_task])], ignore_index=True)
                save_data_to_github(repo, contents, updated_df)
            else:
                st.error("❌ Kolom 'Task Name' dan 'Assigned To' wajib diisi!")

# ------------------------------------------
# TAB 3: UPDATE TASK & PROGRESS
# ------------------------------------------
with tab_update:
    st.subheader("Modify Existing Task Status & Progress")
    
    if not df_tasks.empty:
        # Membuat opsi dropdown berdasarkan ID dan Nama Task
        task_options = [f"{row['Task ID']} - {row['Task Name']}" for _, row in df_tasks.iterrows()]
        selected_option = st.selectbox("Select Task to Update", task_options)
        
        if selected_option:
            selected_id = selected_option.split(" - ")[0]
            task_row = df_tasks[df_tasks["Task ID"] == selected_id].iloc[0]
            
            with st.form("update_form"):
                st.info(f"Target: **{task_row['Task Name']}** | Assigned to: *{task_row['Assigned To']}*")
                
                # Mengambil nilai lama sebagai default form value
                current_status_idx = ["To Do", "In Progress", "Done"].index(task_row["Status"])
                new_status = st.selectbox("Update Status", ["To Do", "In Progress", "Done"], index=current_status_idx)
                new_progress = st.slider("Update Progress (%)", 0, 100, int(task_row["Progress (%)"]))
                
                # Otomatisasi logika hubungan antara progress slider dan status dropdown
                if new_progress == 100:
                    new_status = "Done"
                elif new_progress > 0 and new_status == "To Do":
                    new_status = "In Progress"
                    
                update_btn = st.form_submit_button("Save Updates")
                
                if update_btn:
                    # Mencari indeks baris data yang sesuai dan memperbarui nilainya
                    idx = df_tasks[df_tasks["Task ID"] == selected_id].index[0]
                    df_tasks.at[idx, "Status"] = new_status
                    df_tasks.at[idx, "Progress (%)"] = int(new_progress)
                    
                    # Push pembaruan data ke GitHub
                    save_data_to_github(repo, contents, df_tasks)
    else:
        st.info("ℹ️ Tidak ada data tugas yang tersedia untuk diperbarui.")
