import re

def validate_registration(username, password, confirm_password):
    if not username or len(username.strip()) < 3:
        return "Username must be at least 3 characters long."
    if not password or len(password) < 6:
        return "Password must be at least 6 characters long."
    if password != confirm_password:
        return "Passwords do not match."
    return None

def validate_email(email):
    pattern = r'^[\w\.-]+@[\w\.-]+\.\w+$'
    return bool(re.match(pattern, email))

def validate_profile(name, email, skills):
    """Validates student profile required fields."""
    if not name or len(name.strip()) < 2:
        return "Full name is required."
    if not email or not validate_email(email):
        return "A valid email address is required."
    if not skills or len(skills.strip()) < 2:
        return "Skills are required for AI recommendations."
    return None