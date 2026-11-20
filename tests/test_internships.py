import pytest
from werkzeug.security import generate_password_hash
from app import app as flask_app
from database import init_db, get_db_connection


@pytest.fixture
def client(tmp_path):
    test_db = str(tmp_path / "test_internships.db")
    flask_app.config["TESTING"] = True
    flask_app.config["DATABASE_PATH"] = test_db
    init_db(flask_app)

    db = get_db_connection(test_db)
    db.execute(
        "INSERT INTO users (email, password, role) VALUES (?, ?, 'admin')",
        ("admin@test.com", generate_password_hash("AdminPass123")),
    )
    db.execute(
        "INSERT INTO users (email, password, role) VALUES (?, ?, 'student')",
        ("student@test.com", generate_password_hash("StudentPass123")),
    )
    db.commit()
    db.close()

    with flask_app.test_client() as test_client:
        yield test_client


def _login_and_get_csrf(client, email, password):
    client.post("/login", data={"email": email, "password": password}, follow_redirects=True)
    with client.session_transaction() as sess:
        sess["_csrf_token"] = "test-csrf-token-123"
    return "test-csrf-token-123"


def test_admin_crud_status_and_student_visibility(client):
    csrf = _login_and_get_csrf(client, "admin@test.com", "AdminPass123")

    # 1. Admin creates an Approved listing
    res = client.post(
        "/admin/internships/new",
        data={
            "csrf_token": csrf,
            "title": "Python Backend Intern",
            "company_name": "Zoho",
            "location": "Chennai",
            "work_mode": "On-site",
            "duration": "2 Months",
            "stipend_type": "Paid",
            "stipend_amount": "20000",
            "required_skills": "Python, Flask",
            "description": "Build backend APIs and write automated unit tests.",
            "status": "Approved",
        },
        follow_redirects=True,
    )
    assert res.status_code == 200
    assert b"Python Backend Intern" in res.data

    # 2. Admin creates a Draft listing (must stay hidden from students)
    client.post(
        "/admin/internships/new",
        data={
            "csrf_token": csrf,
            "title": "Unpublished Draft Role",
            "company_name": "HiddenCorp",
            "location": "Bengaluru",
            "work_mode": "Remote",
            "duration": "6 Months",
            "stipend_type": "Paid",
            "required_skills": "Go",
            "description": "Internal draft listing not yet approved for students.",
            "status": "Draft",
        },
        follow_redirects=True,
    )

    # 3. Admin edits listing 1
    edit_res = client.post(
        "/admin/internships/1/edit",
        data={
            "csrf_token": csrf,
            "title": "Senior Python Backend Intern",
            "company_name": "Zoho",
            "location": "Chennai",
            "work_mode": "On-site",
            "duration": "2 Months",
            "stipend_type": "Paid",
            "stipend_amount": "25000",
            "required_skills": "Python, Flask, SQLite",
            "description": "Build backend APIs and write automated unit tests.",
            "status": "Approved",
        },
        follow_redirects=True,
    )
    assert b"Senior Python Backend Intern" in edit_res.data

    # 4. Student logs in: /internships redirects to AI Matchmaker, Approved detail works, Draft is blocked
    client.get("/logout")
    s_csrf = _login_and_get_csrf(client, "student@test.com", "StudentPass123")

    browse = client.get("/internships", follow_redirects=False)
    assert browse.status_code == 302
    assert "/student/recommendations" in browse.headers["Location"]

    approved_detail = client.get("/internships/1")
    assert approved_detail.status_code == 200
    assert b"Senior Python Backend Intern" in approved_detail.data

    draft_detail = client.get("/internships/2", follow_redirects=False)
    assert draft_detail.status_code == 302

    # Student blocked from creating or deleting listings
    forbidden_create = client.post(
        "/admin/internships/new",
        data={"csrf_token": s_csrf, "title": "Unauthorized"},
        follow_redirects=True,
    )
    assert b"Access restricted to administrators" in forbidden_create.data

    forbidden_delete = client.post(
        "/admin/internships/1/delete",
        data={"csrf_token": s_csrf},
        follow_redirects=True,
    )
    assert b"Access restricted to administrators" in forbidden_delete.data


def test_admin_reject_expire_and_delete(client):
    csrf = _login_and_get_csrf(client, "admin@test.com", "AdminPass123")
    client.post(
        "/admin/internships/new",
        data={
            "csrf_token": csrf,
            "title": "Frontend Intern",
            "company_name": "Freshworks",
            "location": "Chennai",
            "work_mode": "Hybrid",
            "stipend_type": "Paid",
            "description": "Develop responsive UI components for web apps.",
            "status": "Approved",
        },
    )

    # Mark Expired -> detail page blocked for students
    client.post("/admin/internships/1/status", data={"csrf_token": csrf, "status": "Expired"})
    client.get("/logout")
    assert client.get("/internships/1", follow_redirects=False).status_code == 302

    # Admin marks Rejected then Deletes
    csrf = _login_and_get_csrf(client, "admin@test.com", "AdminPass123")
    client.post("/admin/internships/1/status", data={"csrf_token": csrf, "status": "Rejected"})
    del_res = client.post("/admin/internships/1/delete", data={"csrf_token": csrf}, follow_redirects=True)
    assert b"Internship listing deleted" in del_res.data


def test_csrf_rejected_on_admin_post(client):
    _login_and_get_csrf(client, "admin@test.com", "AdminPass123")
    res = client.post("/admin/internships/new", data={"title": "Missing CSRF"})
    assert res.status_code == 403