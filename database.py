import sqlite3
import os


def get_db_connection(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _migrate_profiles_table(db):
    """Safely adds new academic, semester, and stipend columns to an existing profiles table."""
    existing_cols = {
        row["name"] for row in db.execute("PRAGMA table_info(profiles)").fetchall()
    }
    new_columns = {
        "courses": "TEXT",
        "course_duration": "TEXT",
        "current_semester": "TEXT",
        "target_semester": "TEXT",
        "internship_duration": "TEXT",
        "stipend_expectation": "TEXT",
        "updated_at": "TIMESTAMP",
    }
    for col_name, col_type in new_columns.items():
        if col_name not in existing_cols:
            db.execute(f"ALTER TABLE profiles ADD COLUMN {col_name} {col_type}")


def init_db(app):
    db_path = app.config['DATABASE_PATH']
    db_dir = os.path.dirname(db_path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)

    db = get_db_connection(db_path)

    # 1. Users Table
    db.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # 2. Student Profiles Table (All 8 Academic, Semester, Duration, Stipend & Project Parameters)
    db.execute('''
        CREATE TABLE IF NOT EXISTS profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE NOT NULL,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            college TEXT,
            cgpa TEXT,
            courses TEXT,
            course_duration TEXT,
            current_semester TEXT,
            target_semester TEXT,
            internship_duration TEXT,
            stipend_expectation TEXT,
            skills TEXT NOT NULL,
            projects TEXT,
            github_url TEXT,
            linkedin_url TEXT,
            preferred_role TEXT,
            preferred_location TEXT,
            resume_text TEXT,
            resume_filename TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')

    # Upgrade existing profiles table in-place if migrating from an earlier milestone
    _migrate_profiles_table(db)

    # 3. AI Recommendations Table
    db.execute('''
        CREATE TABLE IF NOT EXISTS ai_recommendations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER UNIQUE NOT NULL,
            recommendations_json TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (student_id) REFERENCES users (id)
        )
    ''')

    db.commit()
    db.close()