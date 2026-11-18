import os
import json
from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

from database import init_db, get_db_connection
from gemini_service import generate_ai_recommendations

app = Flask(__name__)
app.config['SECRET_KEY'] = 'internship_finder_secret_key_2026'
app.config['DATABASE_PATH'] = os.path.join(app.instance_path, 'internship_finder.db')

init_db(app)

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


@app.route('/')
def index():
    return render_template('index.html', title="InternShip Finder — India")


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        # Safely catch whether the form input is named 'email' or 'username'
        raw_email = request.form.get('email') or request.form.get('username')
        email = raw_email.strip().lower() if raw_email else ''
        password = request.form.get('password')
        role = request.form.get('role', 'student')

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
        # Safely capture whether the form input is named 'email' or 'username'
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


@app.route('/student/dashboard')
@student_required
def student_dashboard():
    db = get_db_connection(app.config['DATABASE_PATH'])
    user_id = session.get('user_id')
    profile = db.execute('SELECT * FROM profiles WHERE user_id = ?', (user_id,)).fetchone()
    db.close()
    return render_template('student_dashboard.html', profile=profile, title="Student Dashboard — InternShip Finder")


@app.route('/student/profile', methods=['GET', 'POST'])
@student_required
def student_profile():
    db = get_db_connection(app.config['DATABASE_PATH'])
    user_id = session.get('user_id')

    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        college = request.form.get('college')
        cgpa = request.form.get('cgpa')
        skills = request.form.get('skills')
        projects = request.form.get('projects')
        courses = request.form.get('courses')
        github_url = request.form.get('github_url')
        linkedin_url = request.form.get('linkedin_url')
        preferred_role = request.form.get('preferred_role')
        preferred_location = request.form.get('preferred_location')

        existing_profile = db.execute('SELECT * FROM profiles WHERE user_id = ?', (user_id,)).fetchone()

        if existing_profile:
            db.execute('''
                UPDATE profiles 
                SET name = ?, email = ?, college = ?, cgpa = ?, skills = ?, projects = ?, courses = ?, 
                    github_url = ?, linkedin_url = ?, preferred_role = ?, preferred_location = ?
                WHERE user_id = ?
            ''', (name, email, college, cgpa, skills, projects, courses, github_url, linkedin_url, 
                  preferred_role, preferred_location, user_id))
        else:
            db.execute('''
                INSERT INTO profiles (user_id, name, email, college, cgpa, skills, projects, courses, 
                                      github_url, linkedin_url, preferred_role, preferred_location)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (user_id, name, email, college, cgpa, skills, projects, courses, 
                  github_url, linkedin_url, preferred_role, preferred_location))

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
        db.execute('UPDATE ai_recommendations SET recommendations_json = ? WHERE student_id = ?', 
                   (recommendations_json_str, user_id))
    else:
        db.execute('INSERT INTO ai_recommendations (student_id, recommendations_json) VALUES (?, ?)', 
                   (user_id, recommendations_json_str))
    db.commit()
    db.close()

    return render_template('recommendations.html', recommendations=recommendations, profile=profile, title="Opportunity Matchmaker — InternShip Finder")


@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    return render_template('admin_dashboard.html', title="Admin Portal — InternShip Finder")


if __name__ == '__main__':
    app.run(debug=True, port=5000)