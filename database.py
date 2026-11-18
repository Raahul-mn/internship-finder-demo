import sqlite3
import os

def get_db_connection(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def init_db(app):
    db_path = app.config['DATABASE_PATH']
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    
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

    # 2. Student Profiles Table (Includes CGPA)
    db.execute('''
        CREATE TABLE IF NOT EXISTS profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE NOT NULL,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            college TEXT,
            cgpa TEXT,
            skills TEXT NOT NULL,
            projects TEXT,
            courses TEXT,
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