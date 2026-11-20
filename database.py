import sqlite3
import os
from werkzeug.security import generate_password_hash


def get_db_connection(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _migrate_profiles_table(db):
    """Safely adds academic, semester, stipend, and goal columns to an existing profiles table."""
    existing_cols = {
        row["name"] for row in db.execute("PRAGMA table_info(profiles)").fetchall()
    }
    new_columns = {
         "degree_branch": "TEXT",
        "courses": "TEXT",
        "course_duration": "TEXT",
        "current_semester": "TEXT",
        "target_semester": "TEXT",
        "internship_duration": "TEXT",
        "stipend_expectation": "TEXT",
        "what_i_need": "TEXT",
        "updated_at": "TIMESTAMP",
    }
    for col_name, col_type in new_columns.items():
        if col_name not in existing_cols:
            db.execute(f"ALTER TABLE profiles ADD COLUMN {col_name} {col_type}")


def _seed_default_admin(db):
    """Creates an initial admin account from .env variables if no admin exists yet."""
    admin_email = (os.environ.get("ADMIN_USERNAME") or "").strip().lower()
    admin_password = (os.environ.get("ADMIN_PASSWORD") or "").strip()

    if not admin_email or not admin_password or admin_password == "change-this-admin-password":
        return

    existing_admin = db.execute("SELECT id FROM users WHERE role = 'admin' LIMIT 1").fetchone()
    if not existing_admin:
        existing_user = db.execute("SELECT id FROM users WHERE email = ?", (admin_email,)).fetchone()
        if not existing_user:
            db.execute(
                "INSERT INTO users (email, password, role) VALUES (?, ?, 'admin')",
                (admin_email, generate_password_hash(admin_password))
            )


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

    # 2. Student Profiles Table
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
            what_i_need TEXT,
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

    # 4. Internships Table
    db.execute('''
        CREATE TABLE IF NOT EXISTS internships (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            company_name TEXT NOT NULL,
            company_type TEXT,
            location TEXT,
            work_mode TEXT NOT NULL,
            duration TEXT,
            stipend_type TEXT NOT NULL,
            stipend_amount TEXT,
            required_skills TEXT,
            description TEXT NOT NULL,
            eligibility TEXT,
            application_link TEXT,
            status TEXT NOT NULL DEFAULT 'Draft',
            is_sample_listing INTEGER NOT NULL DEFAULT 0,
            created_by_admin_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (created_by_admin_id) REFERENCES users (id)
        )
    ''')

    # 5. Bookmarks / Wishlist Table
    db.execute('''
        CREATE TABLE IF NOT EXISTS bookmarks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            internship_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(student_id, internship_id),
            FOREIGN KEY (student_id) REFERENCES users (id) ON DELETE CASCADE,
            FOREIGN KEY (internship_id) REFERENCES internships (id) ON DELETE CASCADE
        )
    ''')

    # 6. Applications / Direct Entries Table
    db.execute('''
        CREATE TABLE IF NOT EXISTS applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            internship_id INTEGER,
            company_name TEXT NOT NULL,
            role_applied TEXT NOT NULL,
            resume_filename TEXT,
            notes TEXT,
            status TEXT NOT NULL DEFAULT 'Pending',
            admin_feedback TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (student_id) REFERENCES users (id) ON DELETE CASCADE,
            FOREIGN KEY (internship_id) REFERENCES internships (id) ON DELETE SET NULL
        )
    ''')

    db.execute("CREATE INDEX IF NOT EXISTS idx_internships_status ON internships(status)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_bookmarks_student ON bookmarks(student_id)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_applications_student ON applications(student_id)")

    _seed_default_admin(db)

    db.commit()
    db.close()