import streamlit as st
import pandas as pd
import json
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
    st.error("❌ Konfigurasi Secrets (GITHUB_TOKEN / REPO_NAME) belum diatur.")
    st.stop()

# ==========================================
# 2. FUNGSI INTEGRASI GITHUB API
# ==========================================
def get_github_file():
    try:
        auth = Auth.Token(GITHUB_TOKEN)
        g = Github(auth=auth)
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
    if contents is None:
        return pd.DataFrame()
    data_str = contents.decoded_content.decode('utf-8')
    data_json = json.loads(data_str)
    
    # Kolom default (termasuk fitur baru)
    columns = ["Task ID", "Task Name", "Assigned To", "Status", "Progress (%)", "Start Date", "Due Date", "Notes", "GDrive Link"]
    
    if not data_json:
        return pd.DataFrame(columns=columns)
        
    df = pd.DataFrame(data_json)
    
    # Memastikan kolom baru ada di dataframe jika data lama belum memilikinya
    for col in columns:
        if col not in df.columns:
            df[col] = ""
    return df[columns] # Memastikan urutan kolom

def save_data_to_github(repo, contents, df):
    data_json = df.to_json(orient="records")
    repo.update_file(
        path=FILE_PATH,
        message="Update PMO data via Dashboard",
        content=data_json,
        sha=contents.sha
    )
    st.success("💾 Data berhasil disimpan ke GitHub!")
    st.rerun()

# ==========================================
# 3. ALUR UTAMA APLIKASI
# ==========================================
repo, contents = get_github_file()
df_tasks = load_data(contents)

st.title("🚀 CP-PMO Dashboard 2.0")

if not df_tasks.empty:
    df_tasks["Progress (%)"] = pd.to_numeric(df_tasks["Progress (%)"])

tab_summary, tab_input, tab_update = st.tabs(["📊 Summary", "➕ Add New Task", "🔄 Update Task"])

# ------------------------------------------
# TAB 1: SUMMARY
# ------------------------------------------
with tab_summary:
    if not df_tasks.empty:
        col1, col2, col3 = st.columns(3)
        col1.metric("Total Tasks", len(df_tasks))
        col2.metric("Avg Progress", f"{df_tasks['Progress (%)'].mean():.1f}%")
        col3.metric("Completed", len(df_tasks[df_tasks["Status"] == "Done"]))
        
        st.markdown("---")
        # Visualisasi sederhana
        fig = px.bar(df_tasks, x="Task Name", y="Progress (%)", color="Status", barmode="group",
                     hover_data=["Start Date", "Due Date", "Assigned To"])
        st.plotly_chart(fig, use_container_width=True)
        
        st.markdown("**Master Task List**")
        # Menampilkan link GDrive agar bisa diklik di tabel
        st.dataframe(df_tasks, use_container_width=True, hide_index=True)
    else:
        st.info("Belum ada data.")

# ------------------------------------------
# TAB 2: ADD NEW TASK
# ------------------------------------------
with tab_input:
    st.subheader("Input Data Project Baru")
    with st.form("input_form", clear_on_submit=True):
        col_a, col_b = st.columns(2)
        with col_a:
            task_name = st.text_input("Nama Task")
            assigned = st.text_input("PIC (Assigned To)")
            start_date = st.date_input("Start Date")
            due_date = st.date_input("Due Date")
        with col_b:
            status = st.selectbox("Status", ["To Do", "In Progress", "Done"])
            progress = st.slider("Progress (%)", 0, 100, 0)
            gdrive_link = st.text_input("Link Google Drive (URL)")
            
        notes = st.text_area("Notes (Freetext Description)")
        
        submit_btn = st.form_submit_button("Tambah Task")
        
        if submit_btn:
            if task_name and assigned:
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
                st.error("Nama Task dan PIC wajib diisi.")

# ------------------------------------------
# TAB 3: UPDATE TASK
# ------------------------------------------
with tab_update:
    if not df_tasks.empty:
        task_options = [f"{row['Task ID']} - {row['Task Name']}" for _, row in df_tasks.iterrows()]
        selected_option = st.selectbox("Pilih Task untuk di-update", task_options)
        
        if selected_option:
            selected_id = selected_option.split(" - ")[0]
            task_row = df_tasks[df_tasks["Task ID"] == selected_id].iloc[0]
            
            with st.form("update_form"):
                st.info(f"Mengedit: {task_row['Task Name']}")
                col_u1, col_u2 = st.columns(2)
                with col_u1:
                    u_status = st.selectbox("Update Status", ["To Do", "In Progress", "Done"], 
                                            index=["To Do", "In Progress", "Done"].index(task_row["Status"]))
                    u_progress = st.slider("Update Progress (%)", 0, 100, int(task_row["Progress (%)"]))
                    u_start = st.date_input("Update Start Date", value=pd.to_datetime(task_row["Start Date"]))
                with col_u2:
                    u_due = st.date_input("Update Due Date", value=pd.to_datetime(task_row["Due Date"]))
                    u_gdrive = st.text_input("Update Link GDrive", value=task_row["GDrive Link"])
                
                u_notes = st.text_area("Update Notes", value=task_row["Notes"])
                
                if st.form_submit_button("Simpan Perubahan"):
                    idx = df_tasks[df_tasks["Task ID"] == selected_id].index[0]
                    df_tasks.at[idx, "Status"] = u_status
                    df_tasks.at[idx, "Progress (%)"] = int(u_progress)
                    df_tasks.at[idx, "Start Date"] = str(u_start)
                    df_tasks.at[idx, "Due Date"] = str(u_due)
                    df_tasks.at[idx, "Notes"] = u_notes
                    df_tasks.at[idx, "GDrive Link"] = u_gdrive
                    save_data_to_github(repo, contents, df_tasks)
    else:
        st.info("Belum ada data untuk di-update.")
