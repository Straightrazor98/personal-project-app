# app.py - Project Tracker Streamlit Application
import streamlit as st
import pandas as pd
import numpy as np
import sqlite3
import hashlib
import datetime
from pathlib import Path
import base64
import re
import os
from datetime import datetime
# ============= DATABASE SETUP =============
def init_db():
    """Initialize database and create tables if they don't exist"""
    conn = sqlite3.connect('project_tracker.db', check_same_thread=False)
    c = conn.cursor()
    
    # Create users table
    c.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # Create projects table
    c.execute('''
    CREATE TABLE IF NOT EXISTS projects (
        id INTEGER PRIMARY KEY,
        title TEXT NOT NULL,
        description TEXT,
        tag_name TEXT,
        tag_color TEXT,
        priority TEXT DEFAULT 'medium',
        completed BOOLEAN DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # Create notes table
    c.execute('''
    CREATE TABLE IF NOT EXISTS notes (
        id INTEGER PRIMARY KEY,
        project_id INTEGER NOT NULL,
        content TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (project_id) REFERENCES projects (id) ON DELETE CASCADE
    )
    ''')
    
    # Create tags table
    c.execute('''
    CREATE TABLE IF NOT EXISTS tags (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        color TEXT NOT NULL,
        count INTEGER DEFAULT 0
    )
    ''')
    
    # Add default tags if they don't exist
    c.execute("SELECT COUNT(*) FROM tags")
    if c.fetchone()[0] == 0:
        default_tags = [
            ('Work', '#0ea5e9'),
            ('Personal', '#f59e0b'),
            ('Urgent', '#ef4444'),
            ('Low Priority', '#10b981'),
            ('Research', '#8b5cf6')
        ]
        c.executemany("INSERT INTO tags (name, color) VALUES (?, ?)", default_tags)
    
    # Check if admin user exists, create if not
    c.execute("SELECT COUNT(*) FROM users WHERE username = 'admin'")
    if c.fetchone()[0] == 0:
        admin_password = hash_password('ecomcpa123')
        c.execute("INSERT INTO users (username, password) VALUES (?, ?)", ('admin', admin_password))
    
    # Check if personal user exists, create if not
    c.execute("SELECT COUNT(*) FROM users WHERE username = 'jthasty'")
    if c.fetchone()[0] == 0:
        user_password = hash_password('Razorstraight98!')
        c.execute("INSERT INTO users (username, password) VALUES (?, ?)", ('jthasty', user_password))
    
    conn.commit()
    conn.close()
def get_db_connection():
    """Get a database connection"""
    conn = sqlite3.connect('project_tracker.db', check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn
def hash_password(password):
    """Hash a password for storing"""
    return hashlib.sha256(password.encode()).hexdigest()
def verify_password(stored_password, provided_password):
    """Verify a stored password against the provided password"""
    return stored_password == hash_password(provided_password)
# ============= AUTHENTICATION FUNCTIONS =============
def authenticate_user(username, password):
    """Authenticate a user by username and password"""
    conn = get_db_connection()
    user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    conn.close()
    
    if user and verify_password(user['password'], password):
        return dict(user)
    return None
def register_user(username, password):
    """Register a new user"""
    if not username or not password:
        return False, "Username and password are required"
    
    if len(password) < 8:
        return False, "Password must be at least 8 characters long"
    
    # Check for password strength
    if not (re.search(r'[A-Z]', password) and 
            re.search(r'[a-z]', password) and 
            re.search(r'[0-9]', password)):
        return False, "Password must contain upper and lowercase letters and at least one number"
    
    conn = get_db_connection()
    
    # Check if username exists
    existing_user = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
    if existing_user:
        conn.close()
        return False, "Username already exists"
    
    try:
        hashed_password = hash_password(password)
        conn.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, hashed_password))
        conn.commit()
        user_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        conn.close()
        return True, dict(user)
    except Exception as e:
        conn.close()
        return False, f"Error creating user: {str(e)}"
# ============= PROJECT FUNCTIONS =============
def get_projects(completed=None):
    """Get all projects, optionally filtered by completion status"""
    conn = get_db_connection()
    query = "SELECT * FROM projects"
    params = []
    
    if completed is not None:
        query += " WHERE completed = ?"
        params.append(1 if completed else 0)
    
    query += " ORDER BY updated_at DESC"
    
    projects = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(project) for project in projects]
def get_project(project_id):
    """Get a project by ID"""
    conn = get_db_connection()
    project = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    conn.close()
    return dict(project) if project else None
def create_project(title, description=None, tag_name=None, tag_color=None, priority="medium"):
    """Create a new project"""
    conn = get_db_connection()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    try:
        cursor = conn.execute(
            """
            INSERT INTO projects 
            (title, description, tag_name, tag_color, priority, created_at, updated_at) 
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """, 
            (title, description, tag_name, tag_color, priority, now, now)
        )
        project_id = cursor.lastrowid
        
        # Update tag count if tag is provided
        if tag_name:
            conn.execute(
                "UPDATE tags SET count = count + 1 WHERE name = ?", 
                (tag_name,)
            )
        
        conn.commit()
        project = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        conn.close()
        return dict(project)
    except Exception as e:
        conn.close()
        raise Exception(f"Error creating project: {str(e)}")
def update_project(project_id, **kwargs):
    """Update a project"""
    conn = get_db_connection()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Get current project for tag update
    current_project = conn.execute("SELECT tag_name FROM projects WHERE id = ?", (project_id,)).fetchone()
    old_tag = current_project['tag_name'] if current_project else None
    
    # Prepare update fields
    update_fields = []
    update_values = []
    
    for key, value in kwargs.items():
        if key in ['title', 'description', 'tag_name', 'tag_color', 'priority', 'completed']:
            update_fields.append(f"{key} = ?")
            update_values.append(value)
    
    # Add updated_at timestamp
    update_fields.append("updated_at = ?")
    update_values.append(now)
    
    # Add project_id to values
    update_values.append(project_id)
    
    try:
        conn.execute(
            f"UPDATE projects SET {', '.join(update_fields)} WHERE id = ?", 
            update_values
        )
        
        # Update tag counts if tag changed
        new_tag = kwargs.get('tag_name')
        if old_tag != new_tag:
            if old_tag:
                conn.execute("UPDATE tags SET count = MAX(0, count - 1) WHERE name = ?", (old_tag,))
            if new_tag:
                conn.execute("UPDATE tags SET count = count + 1 WHERE name = ?", (new_tag,))
        
        conn.commit()
        project = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        conn.close()
        return dict(project) if project else None
    except Exception as e:
        conn.close()
        raise Exception(f"Error updating project: {str(e)}")
def mark_project_complete(project_id, completed):
    """Mark a project as complete or incomplete"""
    return update_project(project_id, completed=completed)
def delete_project(project_id):
    """Delete a project"""
    conn = get_db_connection()
    
    # Get project to update tag count
    project = conn.execute("SELECT tag_name FROM projects WHERE id = ?", (project_id,)).fetchone()
    
    try:
        conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        
        # Update tag count if project had a tag
        if project and project['tag_name']:
            conn.execute(
                "UPDATE tags SET count = MAX(0, count - 1) WHERE name = ?", 
                (project['tag_name'],)
            )
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        conn.close()
        return False
# ============= NOTE FUNCTIONS =============
def get_notes(project_id):
    """Get notes for a project"""
    conn = get_db_connection()
    notes = conn.execute(
        "SELECT * FROM notes WHERE project_id = ? ORDER BY created_at DESC", 
        (project_id,)
    ).fetchall()
    conn.close()
    return [dict(note) for note in notes]
def create_note(project_id, content):
    """Create a new note for a project"""
    conn = get_db_connection()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    try:
        cursor = conn.execute(
            "INSERT INTO notes (project_id, content, created_at) VALUES (?, ?, ?)", 
            (project_id, content, now)
        )
        note_id = cursor.lastrowid
        
        # Update project's updated_at timestamp
        conn.execute(
            "UPDATE projects SET updated_at = ? WHERE id = ?", 
            (now, project_id)
        )
        
        conn.commit()
        note = conn.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
        conn.close()
        return dict(note)
    except Exception as e:
        conn.close()
        raise Exception(f"Error creating note: {str(e)}")
def update_note(note_id, content):
    """Update a note"""
    conn = get_db_connection()
    
    try:
        # Get project_id to update its timestamp
        note = conn.execute("SELECT project_id FROM notes WHERE id = ?", (note_id,)).fetchone()
        if not note:
            conn.close()
            return None
        
        project_id = note['project_id']
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        conn.execute("UPDATE notes SET content = ? WHERE id = ?", (content, note_id))
        
        # Update project's updated_at timestamp
        conn.execute(
            "UPDATE projects SET updated_at = ? WHERE id = ?", 
            (now, project_id)
        )
        
        conn.commit()
        updated_note = conn.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
        conn.close()
        return dict(updated_note) if updated_note else None
    except Exception as e:
        conn.close()
        raise Exception(f"Error updating note: {str(e)}")
def delete_note(note_id):
    """Delete a note"""
    conn = get_db_connection()
    
    try:
        # Get project_id to update its timestamp
        note = conn.execute("SELECT project_id FROM notes WHERE id = ?", (note_id,)).fetchone()
        if not note:
            conn.close()
            return False
        
        project_id = note['project_id']
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        conn.execute("DELETE FROM notes WHERE id = ?", (note_id,))
        
        # Update project's updated_at timestamp
        conn.execute(
            "UPDATE projects SET updated_at = ? WHERE id = ?", 
            (now, project_id)
        )
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        conn.close()
        return False
# ============= TAG FUNCTIONS =============
def get_tags():
    """Get all tags"""
    conn = get_db_connection()
    tags = conn.execute("SELECT * FROM tags ORDER BY name").fetchall()
    conn.close()
    return [dict(tag) for tag in tags]
def create_tag(name, color):
    """Create a new tag"""
    conn = get_db_connection()
    
    try:
        cursor = conn.execute("INSERT INTO tags (name, color, count) VALUES (?, ?, 0)", (name, color))
        tag_id = cursor.lastrowid
        conn.commit()
        tag = conn.execute("SELECT * FROM tags WHERE id = ?", (tag_id,)).fetchone()
        conn.close()
        return dict(tag)
    except Exception as e:
        conn.close()
        raise Exception(f"Error creating tag: {str(e)}")
# ============= STREAMLIT UI =============
def format_datetime(dt_str):
    """Format datetime string for display"""
    if not dt_str:
        return ""
    dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
    return dt.strftime("%B %d, %Y at %I:%M %p")
def format_date(dt_str):
    """Format date string for display"""
    if not dt_str:
        return ""
    dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
    return dt.strftime("%b %d, %Y")
def format_time_ago(dt_str):
    """Format time ago for display"""
    if not dt_str:
        return ""
    
    dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
    now = datetime.now()
    diff = now - dt
    
    days = diff.days
    seconds = diff.seconds
    
    if days > 365:
        years = days // 365
        return f"{years} year{'s' if years != 1 else ''} ago"
    elif days > 30:
        months = days // 30
        return f"{months} month{'s' if months != 1 else ''} ago"
    elif days > 0:
        return f"{days} day{'s' if days != 1 else ''} ago"
    elif seconds > 3600:
        hours = seconds // 3600
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    elif seconds > 60:
        minutes = seconds // 60
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    else:
        return "just now"
def main():
    # Initialize database
    init_db()
    
    # Set page config and CSS
    st.set_page_config(
        page_title="Project Tracker",
        page_icon="📋",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    # Custom CSS
    st.markdown('''
    <style>
        .main .block-container {
            padding-top: 2rem;
            padding-bottom: 2rem;
        }
        .stTabs [data-baseweb="tab-list"] {
            gap: 8px;
        }
        .stTabs [data-baseweb="tab"] {
            padding: 8px 16px;
            border-radius: 4px;
        }
        .stTabs [aria-selected="true"] {
            background-color: rgba(0, 0, 0, 0.05);
        }
        .card {
            border: 1px solid rgba(0, 0, 0, 0.1);
            border-radius: 8px;
            padding: 16px;
            margin-bottom: 16px;
            background-color: white;
        }
        .small-btn {
            font-size: 0.8rem !important;
            padding: 0.1rem 0.5rem !important;
        }
        .note-card {
            border-left: 3px solid #4CAF50;
            padding-left: 10px;
            margin-bottom: 10px;
            background-color: #f7f7f7;
            border-radius: 0 4px 4px 0;
        }
        .tag {
            display: inline-block;
            padding: 2px 8px;
            border-radius: 12px;
            font-size: 0.8rem;
            margin-right: 8px;
            color: white;
        }
        .info-text {
            color: rgba(0, 0, 0, 0.6);
            font-size: 0.9rem;
        }
        .note-date {
            font-size: 0.7rem;
            color: rgba(0, 0, 0, 0.5);
            margin-top: 5px;
        }
        .badge {
            display: inline-block;
            padding: 3px 8px;
            background-color: #f0f0f0;
            border-radius: 10px;
            font-size: 0.75rem;
            color: #666;
        }
        .sidebar .stButton button {
            width: 100%;
        }
        .header-container {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
        }
        .user-info {
            font-size: 0.9rem;
            color: rgba(0, 0, 0, 0.6);
        }
    </style>
    ''', unsafe_allow_html=True)
    
    # Initialize session state for authentication
    if 'user' not in st.session_state:
        st.session_state.user = None
    
    # Authentication view
    if not st.session_state.user:
        st.title("Project Tracker")
        
        # 2-column layout for login/register
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("Login")
            login_username = st.text_input("Username", key="login_username")
            login_password = st.text_input("Password", type="password", key="login_password")
            login_button = st.button("Login", key="login_button")
            
            if login_button:
                user = authenticate_user(login_username, login_password)
                if user:
                    st.session_state.user = user
                    st.experimental_rerun()
                else:
                    st.error("Invalid username or password")
        
        with col2:
            st.subheader("Register")
            st.caption("Create a new account")
            reg_username = st.text_input("Username", key="reg_username")
            reg_password = st.text_input("Password", type="password", key="reg_password", 
                                         help="Must be at least 8 characters with upper and lowercase letters and numbers")
            
            register_button = st.button("Register", key="register_button")
            
            if register_button:
                success, result = register_user(reg_username, reg_password)
                if success:
                    st.session_state.user = result
                    st.success("Account created successfully!")
                    st.experimental_rerun()
                else:
                    st.error(result)
    # Main application view (when user is logged in)
    else:
        # Initialize session states for project management
        if 'active_tab' not in st.session_state:
            st.session_state.active_tab = "active"
        if 'edit_project_id' not in st.session_state:
            st.session_state.edit_project_id = None
        if 'view_notes_project_id' not in st.session_state:
            st.session_state.view_notes_project_id = None
        if 'edit_note_id' not in st.session_state:
            st.session_state.edit_note_id = None
            
        # Page header
        st.markdown(
            f'''
            <div class="header-container">
                <h1>Project Tracker</h1>
                <div class="user-info">
                    Logged in as <b>{st.session_state.user["username"]}</b>
                </div>
            </div>
            ''', 
            unsafe_allow_html=True
        )
        
        # Sidebar with logout button
        with st.sidebar:
            st.button("Logout", key="logout", on_click=lambda: st.session_state.update({"user": None}))
        
        # Tabs for active/completed projects
        tab1, tab2 = st.tabs(["Active Projects", "Completed Projects"])
        
        # Active Projects Tab
        with tab1:
            st.subheader("Active Projects")
            
            # Project creation form
            with st.expander("Add New Project", expanded=False):
                with st.form("add_project_form", clear_on_submit=True):
                    st.markdown("### Create a new project")
                    project_title = st.text_input("Project Title", key="new_project_title")
                    project_description = st.text_area("Description / Next Steps", key="new_project_description", 
                                                      placeholder="What needs to be done next?")
                    
                    # Get tags for dropdown
                    tags = get_tags()
                    tag_options = [""] + [tag["name"] for tag in tags]
                    selected_tag = st.selectbox("Tag (optional)", tag_options, index=0)
                    
                    # Get tag color if tag is selected
                    tag_color = None
                    if selected_tag:
                        for tag in tags:
                            if tag["name"] == selected_tag:
                                tag_color = tag["color"]
                    
                    # Form submission
                    submit_button = st.form_submit_button("Create Project")
                    if submit_button and project_title:
                        try:
                            create_project(
                                title=project_title,
                                description=project_description,
                                tag_name=selected_tag if selected_tag else None,
                                tag_color=tag_color
                            )
                            st.success("Project created successfully!")
                            st.experimental_rerun()
                        except Exception as e:
                            st.error(f"Error creating project: {str(e)}")
            
            # Display active projects
            active_projects = get_projects(completed=False)
            
            if not active_projects:
                st.info("No active projects. Create your first project using the form above.")
            else:
                # Search input for projects
                search_term = st.text_input("Search projects", placeholder="Search by title or description...")
                
                # Filter projects based on search
                if search_term:
                    filtered_projects = [
                        p for p in active_projects 
                        if search_term.lower() in p["title"].lower() or 
                           (p["description"] and search_term.lower() in p["description"].lower())
                    ]
                else:
                    filtered_projects = active_projects
                
                if not filtered_projects and search_term:
                    st.warning(f"No projects found matching '{search_term}'")
                
                # Project list
                for project in filtered_projects:
                    with st.container():
                        col1, col2 = st.columns([0.9, 0.1])
                        
                        with col1:
                            # Project card
                            st.markdown(f'''
                            <div class="card">
                                <h3>{project["title"]}</h3>
                                
                                {f'<div style="margin: 8px 0;">{project["description"]}</div>' if project["description"] else ''}
                                
                                {f'<div style="margin: 8px 0;"><span class="tag" style="background-color: {project["tag_color"]};">{project["tag_name"]}</span></div>' if project["tag_name"] else ''}
                                
                                <div style="display: flex; justify-content: space-between; margin-top: 10px;">
                                    <div class="info-text">Created: {format_date(project["created_at"])}</div>
                                    <div class="info-text">Updated: {format_time_ago(project["updated_at"])}</div>
                                </div>
                            </div>
                            ''', unsafe_allow_html=True)
                            
                            # Project actions
                            col_actions1, col_actions2, col_actions3 = st.columns(3)
                            
                            with col_actions1:
                                if st.button("Mark Complete", key=f"complete_{project['id']}"):
                                    mark_project_complete(project["id"], True)
                                    st.experimental_rerun()
                            
                            with col_actions2:
                                if st.button("View Notes", key=f"notes_{project['id']}"):
                                    st.session_state.view_notes_project_id = project["id"]
                                    st.experimental_rerun()
                            
                            with col_actions3:
                                if st.button("Edit", key=f"edit_{project['id']}"):
                                    st.session_state.edit_project_id = project["id"]
                                    st.experimental_rerun()
        
        # Completed Projects Tab
        with tab2:
            st.subheader("Completed Projects")
            
            # Display completed projects
            completed_projects = get_projects(completed=True)
            
            if not completed_projects:
                st.info("No completed projects yet.")
            else:
                # Search input for completed projects
                search_completed = st.text_input("Search completed projects", placeholder="Search by title or description...")
                
                # Filter projects based on search
                if search_completed:
                    filtered_completed = [
                        p for p in completed_projects 
                        if search_completed.lower() in p["title"].lower() or 
                           (p["description"] and search_completed.lower() in p["description"].lower())
                    ]
                else:
                    filtered_completed = completed_projects
                
                if not filtered_completed and search_completed:
                    st.warning(f"No completed projects found matching '{search_completed}'")
                
                # Completed project list
                for project in filtered_completed:
                    with st.container():
                        col1, col2 = st.columns([0.9, 0.1])
                        
                        with col1:
                            # Project card (with completed styling)
                            st.markdown(f'''
                            <div class="card" style="border-left: 4px solid #10b981;">
                                <h3 style="text-decoration: line-through;">{project["title"]}</h3>
                                
                                {f'<div style="margin: 8px 0;">{project["description"]}</div>' if project["description"] else ''}
                                
                                {f'<div style="margin: 8px 0;"><span class="tag" style="background-color: {project["tag_color"]};">{project["tag_name"]}</span></div>' if project["tag_name"] else ''}
                                
                                <div style="display: flex; justify-content: space-between; margin-top: 10px;">
                                    <div class="info-text">Created: {format_date(project["created_at"])}</div>
                                    <div class="info-text">Completed: {format_time_ago(project["updated_at"])}</div>
                                </div>
                            </div>
                            ''', unsafe_allow_html=True)
                            
                            # Project actions for completed projects
                            col_actions1, col_actions2 = st.columns(2)
                            
                            with col_actions1:
                                if st.button("Mark Active", key=f"reactivate_{project['id']}"):
                                    mark_project_complete(project["id"], False)
                                    st.experimental_rerun()
                            
                            with col_actions2:
                                if st.button("View Notes", key=f"c_notes_{project['id']}"):
                                    st.session_state.view_notes_project_id = project["id"]
                                    st.experimental_rerun()
        
        # View/Edit Project Notes
        if st.session_state.view_notes_project_id:
            project_id = st.session_state.view_notes_project_id
            project = get_project(project_id)
            
            if project:
                with st.sidebar:
                    st.header(f"Notes for {project['title']}")
                    
                    # Add new note
                    st.subheader("Add Note")
                    with st.form("add_note_form", clear_on_submit=True):
                        note_content = st.text_area("New Note", placeholder="Enter your note here...")
                        submit_note = st.form_submit_button("Add Note")
                        
                        if submit_note and note_content.strip():
                            create_note(project_id, note_content)
                            st.success("Note added!")
                            st.experimental_rerun()
                    
                    # Close notes view
                    if st.button("Close Notes", key="close_notes"):
                        st.session_state.view_notes_project_id = None
                        st.session_state.edit_note_id = None
                        st.experimental_rerun()
                    
                    # Fetch and display notes
                    notes = get_notes(project_id)
                    if not notes:
                        st.info("No notes for this project yet.")
                    else:
                        st.subheader("Project Notes")
                        
                        for note in notes:
                            # Note container
                            with st.expander(f"Note from {format_date(note['created_at'])}", expanded=True):
                                # Check if we're editing this note
                                if st.session_state.edit_note_id == note['id']:
                                    with st.form(f"edit_note_{note['id']}", clear_on_submit=False):
                                        edited_content = st.text_area("Edit Note", value=note["content"], key=f"edit_note_content_{note['id']}")
                                        
                                        col1, col2 = st.columns(2)
                                        with col1:
                                            cancel_edit = st.form_submit_button("Cancel")
                                        with col2:
                                            save_edit = st.form_submit_button("Save Changes")
                                        
                                        if save_edit and edited_content.strip():
                                            update_note(note['id'], edited_content)
                                            st.session_state.edit_note_id = None
                                            st.success("Note updated!")
                                            st.experimental_rerun()
                                        
                                        if cancel_edit:
                                            st.session_state.edit_note_id = None
                                            st.experimental_rerun()
                                else:
                                    st.markdown(note["content"])
                                    st.markdown(f'<div class="note-date">Created on {format_datetime(note["created_at"])}</div>', unsafe_allow_html=True)
                                    
                                    col1, col2 = st.columns(2)
                                    with col1:
                                        if st.button("Edit", key=f"edit_note_{note['id']}"):
                                            st.session_state.edit_note_id = note['id']
                                            st.experimental_rerun()
                                    with col2:
                                        if st.button("Delete", key=f"delete_note_{note['id']}"):
                                            delete_note(note['id'])
                                            st.success("Note deleted")
                                            st.experimental_rerun()
        
        # Edit Project Form
        if st.session_state.edit_project_id:
            project_id = st.session_state.edit_project_id
            project = get_project(project_id)
            
            if project:
                with st.sidebar:
                    st.header(f"Edit Project: {project['title']}")
                    
                    with st.form("edit_project_form", clear_on_submit=False):
                        title = st.text_input("Title", value=project["title"])
                        description = st.text_area("Description / Next Steps", value=project["description"] or "")
                        
                        # Tags
                        tags = get_tags()
                        tag_options = [""] + [tag["name"] for tag in tags]
                        default_index = 0
                        
                        if project["tag_name"]:
                            for i, tag_name in enumerate(tag_options):
                                if tag_name == project["tag_name"]:
                                    default_index = i
                                    break
                        
                        selected_tag = st.selectbox("Tag", tag_options, index=default_index)
                        
                        # Get tag color if tag is selected
                        tag_color = None
                        if selected_tag:
                            for tag in tags:
                                if tag["name"] == selected_tag:
                                    tag_color = tag["color"]
                        
                        # Form buttons
                        col1, col2 = st.columns(2)
                        with col1:
                            cancel_edit = st.form_submit_button("Cancel")
                        with col2:
                            save_edit = st.form_submit_button("Save Changes")
                        
                        if save_edit:
                            try:
                                update_project(
                                    project_id,
                                    title=title,
                                    description=description,
                                    tag_name=selected_tag if selected_tag else None,
                                    tag_color=tag_color
                                )
                                st.success("Project updated!")
                                st.session_state.edit_project_id = None
                                st.experimental_rerun()
                            except Exception as e:
                                st.error(f"Error updating project: {str(e)}")
                        
                        if cancel_edit:
                            st.session_state.edit_project_id = None
                            st.experimental_rerun()
if __name__ == "__main__":
    main()
