import os
import json
import secrets
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, abort
from werkzeug.security import generate_password_hash, check_password_hash

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from database import init_db, get_db_connection
from gemini_service import generate_ai_recommendations
from validators import validate_internship_form, validate_internship_status
from internship_listings import (
    create_internship,
    update_internship,
    update_internship_status,
    delete_internship,
    get_internship_by_id,
    get_all_internships_admin,
    search_approved_internships,
    get_student_bookmarked_ids,
    get_student_saved_internships,
    toggle_bookmark,
    remove_bookmark,
    seed_sample_internships,
)

app = Flask(__name__)
app.config['SECRET_KEY'] = (
    os.environ.get('SECRET_KEY', '').strip()
    or 'internship_finder_secret_key_2026'
)
app.config['DATABASE_PATH'] = (
    os.environ.get('DATABASE_PATH', '').strip()
    or os.path.join(app.instance_path, 'internship_finder.db')
)

init_db(app)


# --- CSRF Protection Helpers ---
def get_csrf_token():
    if '_csrf_token' not in session:
        session['_csrf_token'] = secrets.token_hex(32)
    return session['_csrf_token']


def verify_csrf():
    token = request.form.get('csrf_token', '')
    session_token = session.get('_csrf_token', '')
    if not token or not session_token or not secrets.compare_digest(token, session_token):
        abort(403)


app.jinja_env.globals['csrf_token'] = get_csrf_token


@app.errorhandler(403)
def forbidden_error(error):
    flash('Security validation failed (missing or invalid CSRF token). Please refresh and try again.', 'error')
    return render_template('index.html', title="403 Forbidden — InternShip Finder"), 403


# --- Auth Decorators ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


def student_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or session.get('role') != 'student':
            flash('Access restricted to students.', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or session.get('role') != 'admin':
            flash('Access restricted to administrators.', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


# --- Public & Auth Routes ---
@app.route('/')
def index():
    featured = search_approved_internships(app.config['DATABASE_PATH'])[:3]
    return render_template('index.html', featured_internships=featured, title="InternShip Finder — India")


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        raw_email = request.form.get('email') or request.form.get('username')
        email = raw_email.strip().lower() if raw_email else ''
        password = request.form.get('password')
        role = 'student'

        if not email or not password:
            flash('Email and password are required.', 'error')
            return redirect(url_for('register'))

        db = get_db_connection(app.config['DATABASE_PATH'])
        existing_user = db.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()

        if existing_user:
            flash('Email already registered. Please log in.', 'error')
            db.close()
            return redirect(url_for('login'))

        hashed_password = generate_password_hash(password)
        db.execute('INSERT INTO users (email, password, role) VALUES (?, ?, ?)', (email, hashed_password, role))
        db.commit()
        db.close()

        flash('Registration successful! Please log in.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html', title="Register — InternShip Finder")


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        raw_email = request.form.get('email') or request.form.get('username')
        email = raw_email.strip().lower() if raw_email else ''
        password = request.form.get('password')

        db = get_db_connection(app.config['DATABASE_PATH'])
        user = db.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
        db.close()

        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['email'] = user['email']
            session['role'] = user['role']
            flash('Logged in successfully!', 'success')

            if user['role'] == 'admin':
                return redirect(url_for('admin_dashboard'))
            else:
                return redirect(url_for('student_dashboard'))
        else:
            flash('Invalid email or password.', 'error')

    return render_template('login.html', title="Login — InternShip Finder")


@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully.', 'success')
    return redirect(url_for('index'))


# --- Student Profile & AI Matchmaker Routes ---
@app.route('/student/dashboard')
@student_required
def student_dashboard():
    db = get_db_connection(app.config['DATABASE_PATH'])
    user_id = session.get('user_id')
    profile = db.execute('SELECT * FROM profiles WHERE user_id = ?', (user_id,)).fetchone()
    app_row = db.execute(
        "SELECT COUNT(*) AS cnt FROM applications WHERE student_id = ?",
        (user_id,)
    ).fetchone()
    application_count = app_row['cnt'] if app_row else 0
    db.close()
    bookmarked_ids = get_student_bookmarked_ids(app.config['DATABASE_PATH'], user_id)
    return render_template(
        'student_dashboard.html',
        profile=profile,
        bookmark_count=len(bookmarked_ids),
        application_count=application_count,
        title="Student Dashboard — InternShip Finder"
    )


@app.route('/student/profile', methods=['GET', 'POST'])
@student_required
def student_profile():
    db = get_db_connection(app.config['DATABASE_PATH'])
    user_id = session.get('user_id')

    if request.method == 'POST':
        name = (request.form.get('name') or '').strip()
        email = (request.form.get('email') or '').strip()
        college = (request.form.get('college') or '').strip()
        cgpa = (request.form.get('cgpa') or '').strip()
        degree_branch = (request.form.get('degree_branch') or '').strip()
        courses = (request.form.get('courses') or '').strip()
        course_duration = (request.form.get('course_duration') or '').strip()
        current_semester = (request.form.get('current_semester') or '').strip()
        target_semester = (request.form.get('target_semester') or '').strip()
        internship_duration = (request.form.get('internship_duration') or '').strip()
        stipend_expectation = (request.form.get('stipend_expectation') or '').strip()
        what_i_need = (request.form.get('what_i_need') or '').strip()
        skills = (request.form.get('skills') or '').strip()
        projects = (request.form.get('projects') or '').strip()
        github_url = (request.form.get('github_url') or '').strip()
        linkedin_url = (request.form.get('linkedin_url') or '').strip()
        preferred_role = (request.form.get('preferred_role') or '').strip()
        preferred_location = (request.form.get('preferred_location') or '').strip()

        if not name or not email or not skills:
            flash('Name, email, and technical skills are required.', 'error')
            db.close()
            return redirect(url_for('student_profile'))

        existing_profile = db.execute('SELECT * FROM profiles WHERE user_id = ?', (user_id,)).fetchone()

        if existing_profile:
            db.execute('''
                UPDATE profiles 
                SET name = ?, email = ?, college = ?, cgpa = ?, degree_branch = ?, courses = ?,
                    course_duration = ?, current_semester = ?, target_semester = ?,
                    internship_duration = ?, stipend_expectation = ?, what_i_need = ?,
                    skills = ?, projects = ?, github_url = ?, linkedin_url = ?,
                    preferred_role = ?, preferred_location = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ?
            ''', (
                name, email, college, cgpa, degree_branch, courses,
                course_duration, current_semester, target_semester,
                internship_duration, stipend_expectation, what_i_need,
                skills, projects, github_url, linkedin_url,
                preferred_role, preferred_location, user_id
            ))
        else:
            db.execute('''
                INSERT INTO profiles (
                    user_id, name, email, college, cgpa, degree_branch, courses,
                    course_duration, current_semester, target_semester,
                    internship_duration, stipend_expectation, what_i_need,
                    skills, projects, github_url, linkedin_url,
                    preferred_role, preferred_location
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                user_id, name, email, college, cgpa, degree_branch, courses,
                course_duration, current_semester, target_semester,
                internship_duration, stipend_expectation, what_i_need,
                skills, projects, github_url, linkedin_url,
                preferred_role, preferred_location
            ))

        db.commit()
        db.close()
        flash('Profile saved successfully!', 'success')
        return redirect(url_for('student_dashboard'))

    profile = db.execute('SELECT * FROM profiles WHERE user_id = ?', (user_id,)).fetchone()
    db.close()
    return render_template('profile_form.html', profile=profile, title="Candidate Profile — InternShip Finder")

@app.route('/student/recommendations')
@student_required
def generate_recommendations():
    db = get_db_connection(app.config['DATABASE_PATH'])
    user_id = session.get('user_id')

    profile = db.execute('SELECT * FROM profiles WHERE user_id = ?', (user_id,)).fetchone()

    if not profile:
        flash('Please complete your profile before viewing opportunity matches.', 'error')
        db.close()
        return redirect(url_for('student_profile'))

    recommendations = generate_ai_recommendations(profile)
    recommendations_json_str = json.dumps(recommendations)

    existing_rec = db.execute('SELECT * FROM ai_recommendations WHERE student_id = ?', (user_id,)).fetchone()
    if existing_rec:
        db.execute(
            'UPDATE ai_recommendations SET recommendations_json = ?, updated_at = CURRENT_TIMESTAMP WHERE student_id = ?',
            (recommendations_json_str, user_id)
        )
    else:
        db.execute(
            'INSERT INTO ai_recommendations (student_id, recommendations_json) VALUES (?, ?)',
            (user_id, recommendations_json_str)
        )
    db.commit()
    db.close()



    return render_template(
        'recommendations.html',
        recommendations=recommendations,
        profile=profile,
        title="Opportunity Matchmaker — InternShip Finder"
    )

@app.route('/student/ai-opportunity-entry', methods=['POST'])
@student_required
def save_ai_opportunity_entry():
    verify_csrf()
    student_id = session['user_id']
    action_mode = (request.form.get('action_mode') or 'wishlist').strip()
    company_name = (request.form.get('company_name') or '').strip()
    role_title = (request.form.get('role_title') or '').strip()
    location = (request.form.get('location') or 'India').strip()
    work_mode = (request.form.get('work_mode') or 'Hybrid').strip()
    if work_mode not in ('Remote', 'On-site', 'Hybrid'):
        work_mode = 'Hybrid'
    matched_skills = (request.form.get('matched_skills') or '').strip()
    note = (request.form.get('application_note') or '').strip()

    if not company_name or not role_title:
        flash('Company name and role title are required.', 'error')
        return redirect(url_for('generate_recommendations'))

    db = get_db_connection(app.config['DATABASE_PATH'])
    admin_row = db.execute("SELECT id FROM users WHERE role = 'admin' LIMIT 1").fetchone()
    creator_id = admin_row['id'] if admin_row else student_id

    existing = db.execute(
        "SELECT id FROM internships WHERE title = ? AND company_name = ? LIMIT 1",
        (role_title, company_name),
    ).fetchone()

    if existing:
        internship_id = existing['id']
    else:
        cursor = db.execute(
            '''
            INSERT INTO internships (
                title, company_name, company_type, location, work_mode,
                stipend_type, required_skills, description, status,
                is_sample_listing, created_by_admin_id
            )
            VALUES (?, ?, 'AI Matched Target', ?, ?, 'Paid', ?, ?, 'Approved', 0, ?)
            ''',
            (
                role_title,
                company_name,
                location,
                work_mode,
                matched_skills,
                note or f"AI-matched {role_title} opportunity at {company_name} ({location}).",
                creator_id,
            ),
        )
        internship_id = cursor.lastrowid

    # Always save to Wishlist/Bookmarks so the student keeps track of the opportunity
    db.execute(
        "INSERT OR IGNORE INTO bookmarks (student_id, internship_id) VALUES (?, ?)",
        (student_id, internship_id),
    )

    if action_mode == 'apply':
        profile_row = db.execute(
            "SELECT resume_filename FROM profiles WHERE user_id = ?",
            (student_id,)
        ).fetchone()
        resume_file = profile_row['resume_filename'] if profile_row else None

        existing_app = db.execute(
            "SELECT id FROM applications WHERE student_id = ? AND company_name = ? AND role_applied = ?",
            (student_id, company_name, role_title)
        ).fetchone()

        if existing_app:
            db.execute(
                '''
                UPDATE applications
                SET notes = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                ''',
                (note, existing_app['id'])
            )
            flash(f'Updated your existing application entry for {role_title} at {company_name}!', 'success')
        else:
            db.execute(
                '''
                INSERT INTO applications (
                    student_id, internship_id, company_name, role_applied, resume_filename, notes, status
                )
                VALUES (?, ?, ?, ?, ?, ?, 'Applied')
                ''',
                (student_id, internship_id, company_name, role_title, resume_file, note)
            )
            flash(f'Created & submitted application entry for {role_title} at {company_name} (Status: Applied)!', 'success')
    else:
        flash(f'Bookmarked {role_title} at {company_name}!', 'success')

    db.commit()
    db.close()
    return redirect(url_for('saved_internships'))

# ==============================================================================
# MILESTONE 6: INTERNSHIP LISTINGS, SEARCH, FILTERS & BOOKMARKS
# ==============================================================================

@app.route('/internships')
def browse_internships():
    # Deprecated static browse board -> redirect directly to AI Matchmaker
    if session.get('role') == 'student':
        return redirect(url_for('generate_recommendations'))
    return redirect(url_for('index'))


@app.route('/internships/<int:internship_id>')
def internship_details(internship_id):
    internship = get_internship_by_id(app.config['DATABASE_PATH'], internship_id)
    if not internship:
        flash('Internship listing not found.', 'error')
        return redirect(url_for('browse_internships'))

    if session.get('role') != 'admin' and internship['status'] != 'Approved':
        flash('This internship listing is not currently available.', 'error')
        return redirect(url_for('browse_internships'))

    is_bookmarked = False
    if session.get('role') == 'student' and session.get('user_id'):
        bookmarked_ids = get_student_bookmarked_ids(app.config['DATABASE_PATH'], session['user_id'])
        is_bookmarked = internship_id in bookmarked_ids

    return render_template(
        'internship_details.html',
        internship=internship,
        is_bookmarked=is_bookmarked,
        title=f"{internship['title']} — InternShip Finder",
    )


@app.route('/internships/<int:internship_id>/bookmark', methods=['POST'])
@student_required
def bookmark_internship(internship_id):
    verify_csrf()
    internship = get_internship_by_id(app.config['DATABASE_PATH'], internship_id)
    if not internship or internship['status'] != 'Approved':
        flash('Cannot bookmark an unavailable internship listing.', 'error')
        return redirect(url_for('browse_internships'))

    now_bookmarked = toggle_bookmark(app.config['DATABASE_PATH'], session['user_id'], internship_id)
    flash('Internship saved to your bookmarks!' if now_bookmarked else 'Removed from saved internships.', 'success')

    next_page = request.form.get('next')
    if next_page and next_page.startswith('/'):
        return redirect(next_page)
    return redirect(url_for('browse_internships'))

@app.route('/student/saved-internships')
@student_required
def saved_internships():
    db = get_db_connection(app.config['DATABASE_PATH'])
    user_id = session['user_id']
    saved = get_student_saved_internships(app.config['DATABASE_PATH'], user_id)
    applications = db.execute(
        '''
        SELECT * FROM applications
        WHERE student_id = ?
        ORDER BY created_at DESC, id DESC
        ''',
        (user_id,)
    ).fetchall()
    db.close()

    applied_by_internship = {app_row['internship_id']: app_row for app_row in applications if app_row['internship_id']}
    return render_template(
        'saved_internships.html',
        saved_internships=saved,
        applications=applications,
        applied_by_internship=applied_by_internship,
        title="Bookmarked Internships — InternShip Finder",
    )


@app.route('/student/saved-internships/<int:internship_id>/remove', methods=['POST'])
@student_required
def unsave_internship(internship_id):
    verify_csrf()
    remove_bookmark(app.config['DATABASE_PATH'], session['user_id'], internship_id)
    flash('Bookmark removed.', 'success')
    return redirect(url_for('saved_internships'))


# --- Admin Internship Management Routes ---
ALLOWED_APPLICATION_STATUSES = ("Applied", "Under Review", "Shortlisted", "Selected", "Rejected")


@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    all_listings = get_all_internships_admin(app.config['DATABASE_PATH'])
    db = get_db_connection(app.config['DATABASE_PATH'])
    try:
        applications = db.execute(
            '''
            SELECT a.*,
                   u.email AS student_username,
                   u.email AS student_email,
                   p.name AS student_name,
                   p.college AS student_college,
                   p.cgpa AS student_cgpa,
                   p.skills AS student_skills,
                   p.courses AS student_courses
            FROM applications a
            JOIN users u ON a.student_id = u.id
            LEFT JOIN profiles p ON a.student_id = p.user_id
            ORDER BY a.updated_at DESC, a.id DESC
            '''
        ).fetchall()
    finally:
        db.close()

    stats = {
        "total_listings": len(all_listings),
        "total_applications": len(applications),
        "pending_review": sum(1 for a in applications if (a["status"] or "Applied") in ("Applied", "Under Review")),
        "shortlisted": sum(1 for a in applications if a["status"] == "Shortlisted"),
        "selected": sum(1 for a in applications if a["status"] == "Selected"),
    }
    return render_template(
        'admin_dashboard.html',
        total_listings=len(all_listings),
        applications=applications,
        stats=stats,
        allowed_statuses=ALLOWED_APPLICATION_STATUSES,
        title="Admin Portal — InternShip Finder"
    )

@app.route('/admin/applications/<int:app_id>/status', methods=['POST'])
@admin_required
def admin_update_application_status(app_id):
    verify_csrf()
    new_status = (request.form.get('status') or '').strip()
    admin_feedback = (request.form.get('admin_feedback') or '').strip()

    if new_status not in ALLOWED_APPLICATION_STATUSES:
        flash('Invalid application status selected.', 'error')
        return redirect(url_for('admin_dashboard'))

    db = get_db_connection(app.config['DATABASE_PATH'])
    try:
        db.execute(
            '''
            UPDATE applications
            SET status = ?, admin_feedback = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            ''',
            (new_status, admin_feedback, app_id),
        )
        db.commit()
    finally:
        db.close()

    flash(f'Application #{app_id} updated to "{new_status}".', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/internships')
@admin_required
def admin_internships():
    status_filter = (request.args.get('status') or '').strip()
    listings = get_all_internships_admin(app.config['DATABASE_PATH'], status_filter=status_filter)
    return render_template(
        'admin_internships.html',
        internships=listings,
        status_filter=status_filter,
        title="Manage Internships — Admin Portal",
    )


@app.route('/admin/internships/new', methods=['GET', 'POST'])
@admin_required
def admin_new_internship():
    if request.method == 'POST':
        verify_csrf()
        is_valid, errors, cleaned = validate_internship_form(request.form)
        if not is_valid:
            for err in errors:
                flash(err, 'error')
            return render_template(
                'admin_internship_form.html',
                internship=cleaned,
                is_edit=False,
                title="Add Internship — Admin Portal",
            ), 400

        create_internship(app.config['DATABASE_PATH'], cleaned, session['user_id'])
        flash('Internship listing created successfully!', 'success')
        return redirect(url_for('admin_internships'))

    return render_template(
        'admin_internship_form.html',
        internship=None,
        is_edit=False,
        title="Add Internship — Admin Portal",
    )


@app.route('/admin/internships/<int:internship_id>/edit', methods=['GET', 'POST'])
@admin_required
def admin_edit_internship(internship_id):
    internship = get_internship_by_id(app.config['DATABASE_PATH'], internship_id)
    if not internship:
        flash('Internship listing not found.', 'error')
        return redirect(url_for('admin_internships'))

    if request.method == 'POST':
        verify_csrf()
        is_valid, errors, cleaned = validate_internship_form(request.form)
        if not is_valid:
            for err in errors:
                flash(err, 'error')
            cleaned['id'] = internship_id
            return render_template(
                'admin_internship_form.html',
                internship=cleaned,
                is_edit=True,
                title="Edit Internship — Admin Portal",
            ), 400

        update_internship(app.config['DATABASE_PATH'], internship_id, cleaned)
        flash('Internship listing updated successfully!', 'success')
        return redirect(url_for('admin_internships'))

    return render_template(
        'admin_internship_form.html',
        internship=internship,
        is_edit=True,
        title="Edit Internship — Admin Portal",
    )


@app.route('/admin/internships/<int:internship_id>/status', methods=['POST'])
@admin_required
def admin_change_internship_status(internship_id):
    verify_csrf()
    new_status = (request.form.get('status') or '').strip()
    if not validate_internship_status(new_status):
        flash('Invalid internship status requested.', 'error')
        return redirect(url_for('admin_internships'))

    internship = get_internship_by_id(app.config['DATABASE_PATH'], internship_id)
    if not internship:
        flash('Internship listing not found.', 'error')
        return redirect(url_for('admin_internships'))

    update_internship_status(app.config['DATABASE_PATH'], internship_id, new_status)
    flash(f'Listing marked as {new_status}.', 'success')
    return redirect(url_for('admin_internships'))


@app.route('/admin/internships/<int:internship_id>/delete', methods=['POST'])
@admin_required
def admin_delete_internship(internship_id):
    verify_csrf()
    delete_internship(app.config['DATABASE_PATH'], internship_id)
    flash('Internship listing deleted.', 'success')
    return redirect(url_for('admin_internships'))


@app.route('/admin/internships/seed-samples', methods=['POST'])
@admin_required
def admin_seed_samples():
    verify_csrf()
    count = seed_sample_internships(app.config['DATABASE_PATH'], session['user_id'])
    flash(f'Added {count} labeled sample internship listings.', 'success')
    return redirect(url_for('admin_internships'))


if __name__ == '__main__':
    app.run(debug=True, port=5000)