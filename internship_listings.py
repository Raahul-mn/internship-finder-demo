from database import get_db_connection
from validators import validate_internship_status


def create_internship(db_path, data, admin_id):
    """Creates a new internship listing and returns its ID."""
    db = get_db_connection(db_path)
    try:
        cursor = db.execute(
            '''
            INSERT INTO internships (
                title, company_name, company_type, location, work_mode,
                duration, stipend_type, stipend_amount, required_skills,
                description, eligibility, application_link, status,
                is_sample_listing, created_by_admin_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                data["title"],
                data["company_name"],
                data["company_type"],
                data["location"],
                data["work_mode"],
                data["duration"],
                data["stipend_type"],
                data["stipend_amount"],
                data["required_skills"],
                data["description"],
                data["eligibility"],
                data["application_link"],
                data["status"],
                data["is_sample_listing"],
                admin_id,
            ),
        )
        db.commit()
        return cursor.lastrowid
    finally:
        db.close()


def update_internship(db_path, internship_id, data):
    """Updates an existing internship listing."""
    db = get_db_connection(db_path)
    try:
        db.execute(
            '''
            UPDATE internships
            SET title = ?, company_name = ?, company_type = ?, location = ?,
                work_mode = ?, duration = ?, stipend_type = ?, stipend_amount = ?,
                required_skills = ?, description = ?, eligibility = ?,
                application_link = ?, status = ?, is_sample_listing = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            ''',
            (
                data["title"],
                data["company_name"],
                data["company_type"],
                data["location"],
                data["work_mode"],
                data["duration"],
                data["stipend_type"],
                data["stipend_amount"],
                data["required_skills"],
                data["description"],
                data["eligibility"],
                data["application_link"],
                data["status"],
                data["is_sample_listing"],
                internship_id,
            ),
        )
        db.commit()
    finally:
        db.close()


def update_internship_status(db_path, internship_id, new_status):
    """Updates listing status (Draft, Approved, Rejected, Expired)."""
    if not validate_internship_status(new_status):
        raise ValueError(f"Invalid internship status: {new_status}")

    db = get_db_connection(db_path)
    try:
        db.execute(
            "UPDATE internships SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (new_status, internship_id),
        )
        db.commit()
    finally:
        db.close()


def delete_internship(db_path, internship_id):
    """Deletes an internship listing by ID."""
    db = get_db_connection(db_path)
    try:
        db.execute("DELETE FROM internships WHERE id = ?", (internship_id,))
        db.commit()
    finally:
        db.close()


def get_internship_by_id(db_path, internship_id):
    """Fetches a single internship row or None."""
    db = get_db_connection(db_path)
    try:
        return db.execute("SELECT * FROM internships WHERE id = ?", (internship_id,)).fetchone()
    finally:
        db.close()


def get_all_internships_admin(db_path, status_filter=""):
    """Returns all internships for admin management, optionally filtered by status."""
    db = get_db_connection(db_path)
    try:
        if status_filter and validate_internship_status(status_filter):
            return db.execute(
                "SELECT * FROM internships WHERE status = ? ORDER BY created_at DESC, id DESC",
                (status_filter,),
            ).fetchall()
        return db.execute(
            "SELECT * FROM internships ORDER BY created_at DESC, id DESC"
        ).fetchall()
    finally:
        db.close()


def search_approved_internships(
    db_path,
    query="",
    work_mode="",
    stipend_type="",
    location="",
    duration="",
    skills="",
):
    """
    Returns ONLY 'Approved' (and non-expired) internships matching search & filters.
    Uses strictly parameterized SQL queries.
    """
    sql = "SELECT * FROM internships WHERE status = 'Approved'"
    params = []

    if query:
        like_q = f"%{query.strip()}%"
        sql += " AND (title LIKE ? OR company_name LIKE ? OR description LIKE ? OR required_skills LIKE ?)"
        params.extend([like_q, like_q, like_q, like_q])

    if work_mode:
        sql += " AND work_mode = ?"
        params.append(work_mode.strip())

    if stipend_type:
        sql += " AND stipend_type = ?"
        params.append(stipend_type.strip())

    if location:
        sql += " AND location LIKE ?"
        params.append(f"%{location.strip()}%")

    if duration:
        sql += " AND duration LIKE ?"
        params.append(f"%{duration.strip()}%")

    if skills:
        for skill_token in [s.strip() for s in skills.split(",") if s.strip()]:
            sql += " AND required_skills LIKE ?"
            params.append(f"%{skill_token}%")

    sql += " ORDER BY created_at DESC, id DESC"

    db = get_db_connection(db_path)
    try:
        return db.execute(sql, params).fetchall()
    finally:
        db.close()


def get_student_bookmarked_ids(db_path, student_id):
    """Returns a set of internship IDs bookmarked by the given student."""
    db = get_db_connection(db_path)
    try:
        rows = db.execute(
            "SELECT internship_id FROM bookmarks WHERE student_id = ?",
            (student_id,),
        ).fetchall()
        return {row["internship_id"] for row in rows}
    finally:
        db.close()


def get_student_saved_internships(db_path, student_id):
    """Returns full internship details for all listings bookmarked by this student."""
    db = get_db_connection(db_path)
    try:
        return db.execute(
            '''
            SELECT i.*, b.created_at AS bookmarked_at
            FROM bookmarks b
            JOIN internships i ON b.internship_id = i.id
            WHERE b.student_id = ?
            ORDER BY b.created_at DESC, b.id DESC
            ''',
            (student_id,),
        ).fetchall()
    finally:
        db.close()


def add_bookmark(db_path, student_id, internship_id):
    """Adds a bookmark safely, preventing duplicates."""
    db = get_db_connection(db_path)
    try:
        db.execute(
            "INSERT OR IGNORE INTO bookmarks (student_id, internship_id) VALUES (?, ?)",
            (student_id, internship_id),
        )
        db.commit()
    finally:
        db.close()


def remove_bookmark(db_path, student_id, internship_id):
    """Removes a bookmark owned by the student."""
    db = get_db_connection(db_path)
    try:
        db.execute(
            "DELETE FROM bookmarks WHERE student_id = ? AND internship_id = ?",
            (student_id, internship_id),
        )
        db.commit()
    finally:
        db.close()


def toggle_bookmark(db_path, student_id, internship_id):
    """Toggles a bookmark on/off and returns True if bookmarked, False if removed."""
    db = get_db_connection(db_path)
    try:
        existing = db.execute(
            "SELECT id FROM bookmarks WHERE student_id = ? AND internship_id = ?",
            (student_id, internship_id),
        ).fetchone()
        if existing:
            db.execute(
                "DELETE FROM bookmarks WHERE student_id = ? AND internship_id = ?",
                (student_id, internship_id),
            )
            db.commit()
            return False
        else:
            db.execute(
                "INSERT INTO bookmarks (student_id, internship_id) VALUES (?, ?)",
                (student_id, internship_id),
            )
            db.commit()
            return True
    finally:
        db.close()


def seed_sample_internships(db_path, admin_id):
    """Inserts 3 clearly labeled sample internship listings for demo purposes."""
    samples = [
        {
            "title": "Python Backend Developer Intern",
            "company_name": "Zoho Labs (Sample)",
            "company_type": "Tier 2 Product Scale-up",
            "location": "Chennai",
            "work_mode": "On-site",
            "duration": "2 Months",
            "stipend_type": "Paid",
            "stipend_amount": "₹20,000 / month",
            "required_skills": "Python, Flask, SQLite, REST APIs, Git",
            "description": "Work with backend platform engineers to build internal REST microservices, write automated pytest suites, and optimize relational database queries.",
            "eligibility": "B.E./B.Tech CSE/IT (Semesters 5–8), minimum 7.5 CGPA.",
            "application_link": "",
            "status": "Approved",
            "is_sample_listing": 1,
        },
        {
            "title": "Full-Stack Web Engineering Intern",
            "company_name": "Razorpay DevWorks (Sample)",
            "company_type": "Tier 2 Product Scale-up",
            "location": "Bengaluru",
            "work_mode": "Hybrid",
            "duration": "6 Months",
            "stipend_type": "Paid",
            "stipend_amount": "₹30,000 / month",
            "required_skills": "Python, JavaScript, HTML, CSS, SQL",
            "description": "Develop merchant onboarding workflows, build clean dashboard components, and collaborate on API reliability improvements.",
            "eligibility": "Final-year undergraduate students eligible for 6-month credit internship.",
            "application_link": "",
            "status": "Approved",
            "is_sample_listing": 1,
        },
        {
            "title": "AI & Data Engineering Intern",
            "company_name": "Kochi CloudTech Startups (Sample)",
            "company_type": "Tier 3 High-Growth Startup",
            "location": "Kochi",
            "work_mode": "Remote",
            "duration": "3 Months",
            "stipend_type": "Paid",
            "stipend_amount": "₹12,000 / month",
            "required_skills": "Python, SQL, Pandas, Prompt Engineering",
            "description": "Build structured data extraction pipelines, evaluate LLM outputs, and assist with analytics dashboards for early-stage SaaS products.",
            "eligibility": "Open to all semesters with strong GitHub project portfolio.",
            "application_link": "",
            "status": "Approved",
            "is_sample_listing": 1,
        },
    ]
    created = 0
    for item in samples:
        create_internship(db_path, item, admin_id)
        created += 1
    return created