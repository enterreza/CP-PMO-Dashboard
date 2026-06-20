import streamlit as st
import pandas as pd
import json
import datetime
import plotly.express as px
from github import Github, Auth
from github import GithubException

# ==========================================
# 1. KONFIGURASI AWAL & TAMPILAN (SMARTSHEET STYLE)
# ==========================================
st.set_page_config(page_title="CP-PMO Smartsheet Dashboard", layout="wide")

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
    </style>
""", unsafe_allow_html=True)

# Path database di repositori GitHub Anda
FILE_PATH = "tasks.json"  

if "GITHUB_TOKEN" in st.secrets and "REPO_NAME" in st.secrets:
    GITHUB_TOKEN = st.secrets["GITHUB_TOKEN"]
    REPO_NAME = st.secrets["REPO_NAME"]
else:
    st.error("❌ Konfigurasi Secrets (GITHUB_TOKEN / REPO_NAME) belum diatur di Streamlit Cloud.")
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

# ==========================================
# 3. ALUR UTAMA APLIKASI
# ==========================================
repo, contents = get_github_file()
df_tasks = load_data(contents)

st.title("📋 CP-PMO Smartsheet Workspace")
st.write("Grid lembar kerja kolaboratif terstruktur yang disinkronkan langsung ke basis data repositori GitHub.")

if not df_tasks.empty:
    df_tasks["Progress (%)"] = pd.to_numeric(df_tasks["Progress (%)"])

tab_summary, tab_input, tab_update, tab_delete = st.tabs([
    "📊 Grid & Gantt View", 
    "➕ Row Row / Task", 
    "🔄 Edit Row Item",
    "❌ Delete Row Item"
])

# ------------------------------------------
# TAB 1: DASHBOARD SUMMARY & GANTT VIEW (SMARTSHEET STYLE)
# ------------------------------------------
with tab_summary:
    if not df_tasks.empty:
        total_tasks = len(df_tasks)
        avg_progress = df_tasks["Progress (%)"].mean()
        completed_tasks = len(df_tasks[df_tasks["Status"] == "Done"])
        in_progress_tasks = len(df_tasks[df_tasks["Status"] == "In Progress"])
        
        # Ringkasan KPI Atas bergaya kotak mini metrik Smartsheet
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Sheets Row", total_tasks)
        col2.metric("Sheet Avg Progress", f"{avg_progress:.1f}%")
        col3.metric("Completed Status", completed_tasks)
        col4.metric("Active Allocation", in_progress_tasks)
        
        st.markdown("---")
        st.markdown("### 📅 Smartsheet Timeline Split-Gantt")
        
        # Copy data untuk penanganan visualisasi
        df_gantt = df_tasks.copy()
        df_gantt["Clean Start"] = pd.to_datetime(df_gantt["Start Date"], errors='coerce')
        df_gantt["Clean Due"] = pd.to_datetime(df_gantt["Due Date"], errors='coerce')
        
        df_gantt["Clean Start"] = df_gantt["Clean Start"].fillna(pd.Timestamp(datetime.date.today()))
        df_gantt["Clean Due"] = df_gantt["Clean Due"].fillna(df_gantt["Clean Start"] + pd.Timedelta(days=1))
        
        # Pembuatan Timeline menggunakan kombinasi Soft Palette
        fig_gantt = px.timeline(
            df_gantt,
            x_start="Clean Start",
            x_end="Clean Due",
            y="Task Name",
            color="Status",
            text="Assigned To",
            hover_data=["Start Date", "Due Date", "Progress (%)"],
            # Aplikasi Palet Warna Muted/Soft Premium
            color_discrete_map={
                'To Do': '#FF8A8A',       # Terracotta Muted Red
                'In Progress': '#7BC9FF', # Soft Sky Blue
                'Done': '#A3E4D7'         # Soft Mint Green
            }
        )
        fig_gantt.update_yaxes(categoryorder="category ascending")
        fig_gantt.update_layout(
            plot_bgcolor="white",
            paper_bgcolor="white",
            xaxis_title="Timeline Calendar",
            yaxis_title="",
            height=340,
            margin=dict(t=10, b=10, l=10, r=10),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        fig_gantt.update_xaxes(showgrid=True, gridcolor="#E2E4E8")
        fig_gantt.update_yaxes(showgrid=True, gridcolor="#E2E4E8")
        st.plotly_chart(fig_gantt, use_container_width=True)

        st.markdown("---")
        st.markdown("### 📄 Sheet Interactive Row Grid")
        # Menampilkan data tabel dengan gaya interaktif penuh bawaan streamlit dataframe (bisa filter, sort, resize)
        st.dataframe(
            df_tasks, 
            use_container_width=True, 
            hide_index=True,
            column_config={
                "GDrive Link": st.column_config.LinkColumn("Attachment (GDrive Link)"),
                "Progress (%)": st.column_config.ProgressColumn("Overall Progress", format="%d%%", min_value=0, max_value=100)
            }
        )
    else:
        st.info("ℹ️ Lembar kerja Anda saat ini masih kosong. Silakan masuk ke tab **Row Row / Task** untuk membuat baris data baru.")

# ------------------------------------------
# TAB 2: INPUT ROW BARU (Dengan Notifikasi Berhasil)
# ------------------------------------------
with tab_input:
    st.subheader("Add New Row Item to Sheet")
    with st.form("input_form", clear_on_submit=True):
        col_a, col_b = st.columns(2)
        with col_a:
            task_name = st.text_input("Task Name / Activity Description")
            assigned = st.text_input("Assigned To (PIC Name)")
            start_date = st.date_input("Start Date Plan", value=datetime.date.today())
        with col_b:
            status = st.selectbox("Allocation Status", ["To Do", "In Progress", "Done"])
            progress = st.slider("Progress Weight (%)", 0, 100, 0 if status != "Done" else 100)
            due_date = st.date_input("Due Date Target", value=datetime.date.today() + datetime.timedelta(days=7))
            
        gdrive_link = st.text_input("Google Drive Documentation Link (URL)")
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
                save_data_to_github(repo, contents, updated_df, message=f"Insert new sheet row {new_id}")
                
                # Mengirimkan Alert Notifikasi Berhasil ala Smartsheet
                st.success(f"✔️ Row **{new_id}** ({task_name}) telah sukses ditambahkan ke dalam database workspace!")
                st.balloons()
                st.rerun()
            else:
                st.error("❌ Validasi Gagal! Kolom 'Task Name' dan 'Assigned To' tidak diperbolehkan kosong.")

# ------------------------------------------
# TAB 3: EDIT ROW ITEMS (Dengan Notifikasi Berhasil)
# ------------------------------------------
with tab_update:
    st.subheader("Update Sheet Row Values")
    if not df_tasks.empty:
        task_options = [f"{row['Task ID']} - {row['Task Name']}" for _, row in df_tasks.iterrows()]
        selected_option = st.selectbox("Pilih nomor indeks baris tugas", task_options)
        
        if selected_option:
            selected_id = selected_option.split(" - ")[0]
            task_row = df_tasks[df_tasks["Task ID"] == selected_id].iloc[0]
            
            # Parsing penanggalan
            default_start = pd.to_datetime(task_row["Start Date"]).date() if task_row["Start Date"] != "" else datetime.date.today()
            default_due = pd.to_datetime(task_row["Due Date"]).date() if task_row["Due Date"] != "" else datetime.date.today()
            
            with st.form("update_form"):
                st.caption(f"ID Target: {task_row['Task ID']} | Nama Projek: {task_row['Task Name']}")
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
                
                # Otomatisasi Logika Status Kombinasi kemajuan
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
                    save_data_to_github(repo, contents, df_tasks, message=f"Update sheet row {selected_id}")
                    
                    # Alert Pembaruan Data Berhasil
                    st.success(f"💾 Perubahan baris data **{selected_id}** sukses diperbarui ke server repositori!")
                    st.rerun()
    else:
        st.info("ℹ️ Tidak ada data yang tersedia untuk dimodifikasi.")

# ------------------------------------------
# TAB 4: DELETE SHEET ROWS (Dengan Notifikasi Berhasil)
# ------------------------------------------
with tab_delete:
    st.subheader("Remove Selected Row From Worksheet")
    if not df_tasks.empty:
        del_task_options = [f"{row['Task ID']} - {row['Task Name']}" for _, row in df_tasks.iterrows()]
        selected_del_option = st.selectbox("Pilih Baris yang ingin dihapus Permanen", del_task_options, key="del_select")
        
        if selected_del_option:
            del_id = selected_del_option.split(" - ")[0]
            del_row = df_tasks[df_tasks["Task ID"] == del_id].iloc[0]
            st.warning(f"⚠️ **PERINGATAN SISTEM:** Anda akan menghapus baris data berikut dari berkas lembar kerja secara permanen:")
            st.code(f"Row ID: {del_row['Task ID']}\nTask Title: {del_row['Task Name']}\nPIC: {del_row['Assigned To']}")
            
            with st.form("delete_form"):
                confirm_check = st.checkbox("Saya mengonfirmasi untuk melakukan penghapusan baris baris ini")
                delete_btn = st.form_submit_button("🔴 Delete Selected Row")
                if delete_btn:
                    if confirm_check:
                        filtered_df = df_tasks[df_tasks["Task ID"] != del_id]
                        
                        st.session_state["master_df"] = filtered_df
                        save_data_to_github(repo, contents, filtered_df, message=f"Delete sheet row {del_id}")
                        
                        # Alert Penghapusan Sukses
                        st.success(f"🗑️ Baris data **{del_id}** sukses dihapus secara bersih dari berkas utama.")
                        st.rerun()
                    else:
                        st.error("❌ Batalkan Aksi! Kotak persetujuan konfirmasi wajib dicentang.")
