# streamlit_app.py

import streamlit as st
import sqlite3
import hashlib
import os
import binascii
from datetime import datetime

DB_FILE = "tracker.db"

# ---- Database Helpers ----
def get_conn():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn()
    c = conn.cursor()
    # Users
    c.execute("""
      CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL
      )
    """)
    # Projects
    c.execute("""
      CREATE TABLE IF NOT EXISTS projects (
        id INTEGER PRIMARY KEY,
        user_id INTEGER NOT NULL,
        title TEXT NOT NULL,
        description TEXT,
        tag_name TEXT,
        tag_color TEXT,
        priority TEXT DEFAULT 'medium',
        completed INTEGER DEFAULT 0,
        created_at TEXT,
        updated_at TEXT,
        FOREIGN KEY(user_id) REFERENCES users(id)
      )
    """)
    # Notes
    c.execute("""
      CREATE TABLE IF NOT EXISTS notes (
        id INTEGER PRIMARY KEY,
        project_id INTEGER NOT NULL,
        content TEXT NOT NULL,
        created_at TEXT,
        FOREIGN KEY(project_id) REFERENCES projects(id)
      )
    """)
    # Tags
    c.execute("""
      CREATE TABLE IF NOT EXISTS tags (
        id INTEGER PRIMARY KEY,
        name TEXT UNIQUE NOT NULL,
        color TEXT NOT NULL,
        count INTEGER DEFAULT 0
      )
    """)
    conn.commit()

def hash_password(password: str) -> str:
    salt = binascii.hexlify(os.urandom(16)).decode()
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100000)
    return f"{binascii.hexlify(dk).decode()}:{salt}"

def verify_password(stored: str, supplied: str) -> bool:
    try:
        hashed, salt = stored.split(":")
        dk = hashlib.pbkdf2_hmac("sha256", supplied.encode(), salt.encode(), 100000)
        return binascii.hexlify(dk).decode() == hashed
    except:
        return False

def get_user(username: str):
    row = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    return row

def authenticate(username: str, password: str):
    row = get_user(username)
    if row and verify_password(row["password"], password):
        return row["id"]
    return None

# ---- Initialize DB & Connection ----
init_db()
conn = get_conn()

# ---- Streamlit UI ----
st.set_page_config(page_title="📁 Project Folder Tracker")
st.title("📁 Personal Project Folder")

# --- Authentication Flows ---
if "user_id" not in st.session_state:
    st.header("👤 Register")
    with st.form("register_form"):
        reg_user = st.text_input("Username")
        reg_pass = st.text_input("Password", type="password")
        if st.form_submit_button("Register"):
            if get_user(reg_user):
                st.error("Username already exists")
            else:
                conn.execute(
                    "INSERT INTO users(username,password) VALUES (?,?)",
                    (reg_user, hash_password(reg_pass)),
                )
                conn.commit()
                st.success("Registered! Please log in below.")

    st.header("🔑 Login")
    with st.form("login_form"):
        log_user = st.text_input("Username", key="login_user")
        log_pass = st.text_input("Password", type="password", key="login_pass")
        if st.form_submit_button("Login"):
            uid = authenticate(log_user, log_pass)
            if uid:
                st.session_state.user_id = uid
                st.session_state.username = log_user
                st.experimental_rerun()
            else:
                st.error("Invalid credentials")
else:
    st.sidebar.success(f"Logged in as: {st.session_state.username}")
    page = st.sidebar.radio("Navigate", ["Projects", "Notes", "Tags", "Logout"])

    # --- Add Tag (always available) ---
    with st.expander("➕ Add New Tag", expanded=False):
        with st.form("tag_form"):
            tname = st.text_input("Tag Name")
            tcolor = st.color_picker("Tag Color", "#00ff00")
            if st.form_submit_button("Save Tag"):
                try:
                    conn.execute(
                        "INSERT INTO tags(name,color) VALUES (?,?)",
                        (tname, tcolor),
                    )
                    conn.commit()
                    st.success(f"Tag '{tname}' created")
                except sqlite3.IntegrityError:
                    st.error("Tag already exists")

    # --- Projects Page ---
    if page == "Projects":
        st.header("🗂️ Your Projects")
        # Create Project
        with st.form("proj_form"):
            ptitle = st.text_input("Title")
            pdesc = st.text_area("Description")
            tags_list = [r["name"] for r in conn.execute("SELECT name FROM tags").fetchall()]
            ptag = st.selectbox("Tag (optional)", [""] + tags_list)
            pcolor = "#00ff00"
            if ptag:
                r = conn.execute("SELECT color FROM tags WHERE name=?", (ptag,)).fetchone()
                if r: pcolor = r["color"]
            pcolor = st.color_picker("Tag Color", pcolor)
            pprio = st.selectbox("Priority", ["low", "medium", "high"], index=1)
            if st.form_submit_button("Create Project"):
                now = datetime.now().isoformat()
                conn.execute("""
                    INSERT INTO projects
                    (user_id,title,description,tag_name,tag_color,priority,created_at,updated_at)
                    VALUES (?,?,?,?,?,?,?,?)""",
                    (st.session_state.user_id, ptitle, pdesc, ptag, pcolor, pprio, now, now))
                conn.commit()
                st.success("Project added!")

        # List & Toggle Complete
        st.subheader("Filter Projects")
        status = st.radio("Show", ["active","completed","all"], index=0)
        q = "SELECT * FROM projects WHERE user_id=?"
        args = [st.session_state.user_id]
        if status == "active":     q += " AND completed=0"
        elif status == "completed": q += " AND completed=1"
        q += " ORDER BY updated_at DESC"
        rows = conn.execute(q, args).fetchall()

        for r in rows:
            key = f"proj_{r['id']}"
            checked = st.checkbox(f"{r['title']} — {r['description']}", value=bool(r["completed"]), key=key)
            if checked != bool(r["completed"]):
                new = 1 if checked else 0
                now = datetime.now().isoformat()
                conn.execute("UPDATE projects SET completed=?,updated_at=? WHERE id=?", (new, now, r["id"]))
                conn.commit()
                st.experimental_rerun()

    # --- Notes Page ---
    elif page == "Notes":
        st.header("📝 Notes for Projects")
        projects = conn.execute(
            "SELECT id,title FROM projects WHERE user_id=?", (st.session_state.user_id,)
        ).fetchall()
        proj_map = {f"{p['id']}: {p['title']}": p['id'] for p in projects}
        sel = st.selectbox("Select a Project", list(proj_map.keys()))
        pid = proj_map[sel]

        with st.form("note_form"):
            note = st.text_area("New Note")
            if st.form_submit_button("Add Note"):
                now = datetime.now().isoformat()
                conn.execute("INSERT INTO notes(project_id,content,created_at) VALUES (?,?,?)", (pid, note, now))
                conn.commit()
                st.success("Note added!")

        st.markdown("**Existing Notes:**")
        for n in conn.execute("SELECT * FROM notes WHERE project_id=? ORDER BY created_at", (pid,)):
            st.write(f"- {n['content']} *(added {n['created_at']})*")

    # --- Tags Page ---
    elif page == "Tags":
        st.header("🏷️ All Tags")
        for t in conn.execute
