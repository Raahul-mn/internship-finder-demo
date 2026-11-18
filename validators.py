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

# --- Milestone 6: Internship Listing Validators ---
ALLOWED_WORK_MODES = {"Remote", "On-site", "Hybrid"}
ALLOWED_STIPEND_TYPES = {"Paid", "Unpaid", "Not specified"}
ALLOWED_INTERNSHIP_STATUSES = {"Draft", "Approved", "Rejected", "Expired"}


def validate_internship_status(status):
    """Checks that an internship status is one of the allowed workflow values."""
    return status in ALLOWED_INTERNSHIP_STATUSES


def validate_internship_form(form_data):
    """
    Validates admin internship creation/edit form inputs.
    Returns (is_valid: bool, errors: list[str], cleaned_data: dict).
    """
    errors = []

    title = (form_data.get("title") or "").strip()
    company_name = (form_data.get("company_name") or "").strip()
    company_type = (form_data.get("company_type") or "").strip()
    location = (form_data.get("location") or "").strip()
    work_mode = (form_data.get("work_mode") or "").strip()
    duration = (form_data.get("duration") or "").strip()
    stipend_type = (form_data.get("stipend_type") or "").strip()
    stipend_amount = (form_data.get("stipend_amount") or "").strip()
    required_skills = (form_data.get("required_skills") or "").strip()
    description = (form_data.get("description") or "").strip()
    eligibility = (form_data.get("eligibility") or "").strip()
    application_link = (form_data.get("application_link") or "").strip()
    status = (form_data.get("status") or "Draft").strip()
    is_sample_listing = 1 if form_data.get("is_sample_listing") in ("1", "on", "true", True, 1) else 0

    if not title or len(title) < 3:
        errors.append("Internship title is required (minimum 3 characters).")
    if not company_name or len(company_name) < 2:
        errors.append("Company name is required (minimum 2 characters).")
    if work_mode not in ALLOWED_WORK_MODES:
        errors.append("Work mode must be Remote, On-site, or Hybrid.")
    if stipend_type not in ALLOWED_STIPEND_TYPES:
        errors.append("Stipend type must be Paid, Unpaid, or Not specified.")
    if not description or len(description) < 15:
        errors.append("Description is required (minimum 15 characters).")
    if status not in ALLOWED_INTERNSHIP_STATUSES:
        errors.append("Invalid listing status selected.")
    if application_link and not (application_link.startswith("http://") or application_link.startswith("https://")):
        errors.append("Application link must start with http:// or https://.")

    cleaned_data = {
        "title": title,
        "company_name": company_name,
        "company_type": company_type,
        "location": location,
        "work_mode": work_mode,
        "duration": duration,
        "stipend_type": stipend_type,
        "stipend_amount": stipend_amount,
        "required_skills": required_skills,
        "description": description,
        "eligibility": eligibility,
        "application_link": application_link,
        "status": status,
        "is_sample_listing": is_sample_listing,
    }
    return (len(errors) == 0), errors, cleaned_data