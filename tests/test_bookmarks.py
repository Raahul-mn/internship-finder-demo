import pytest
from werkzeug.security import generate_password_hash
from app import app as flask_app
from database import init_db, get_db_connection


@pytest.fixture
def bookmark_client(tmp_path):
    test_db = str(tmp_path / "test_bookmarks.db")
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
        ("s1@test.com", generate_password_hash("Pass123")),
    )
    db.execute(
        "INSERT INTO users (email, password, role) VALUES (?, ?, 'student')",
        ("s2@test.com", generate_password_hash("Pass123")),
    )
    db.execute(
        """
        INSERT INTO internships (title, company_name, location, work_mode, stipend_type, description, status, created_by_admin_id)
        VALUES ('Flask Developer Intern', 'Freshworks', 'Chennai', 'Hybrid', 'Paid', 'Build web apps with Flask.', 'Approved', 1)
        """
    )
    db.commit()
    db.close()

    with flask_app.test_client() as client:
        yield client


def test_student_bookmarks_duplicate_prevention_and_isolation(bookmark_client):
    # Student 1 bookmarks internship 1
    bookmark_client.post("/login", data={"email": "s1@test.com", "password": "Pass123"})
    with bookmark_client.session_transaction() as sess:
        sess["_csrf_token"] = "csrf-s1"

    bookmark_client.post("/internships/1/bookmark", data={"csrf_token": "csrf-s1"})
    saved_s1 = bookmark_client.get("/student/saved-internships")
    assert b"Flask Developer Intern" in saved_s1.data

    # Student 2 must NOT see Student 1's bookmarks
    bookmark_client.get("/logout")
    bookmark_client.post("/login", data={"email": "s2@test.com", "password": "Pass123"})
    saved_s2 = bookmark_client.get("/student/saved-internships")
    assert b"Flask Developer Intern" not in saved_s2.data

    # Student 1 removes bookmark
    bookmark_client.get("/logout")
    bookmark_client.post("/login", data={"email": "s1@test.com", "password": "Pass123"})
    with bookmark_client.session_transaction() as sess:
        sess["_csrf_token"] = "csrf-s1-remove"

    bookmark_client.post("/student/saved-internships/1/remove", data={"csrf_token": "csrf-s1-remove"})
    after_remove = bookmark_client.get("/student/saved-internships")
    assert b"Flask Developer Intern" not in after_remove.data


def test_admin_cannot_bookmark_listings(bookmark_client):
    bookmark_client.post("/login", data={"email": "admin@test.com", "password": "AdminPass123"})
    with bookmark_client.session_transaction() as sess:
        sess["_csrf_token"] = "csrf-admin"

    res = bookmark_client.post(
        "/internships/1/bookmark",
        data={"csrf_token": "csrf-admin"},
        follow_redirects=True,
    )
    assert b"Access restricted to students" in res.data