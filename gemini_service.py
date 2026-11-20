import os
import re
import json
import time
import logging
from google import genai
from google.genai import types

logger = logging.getLogger(__name__)


def _parse_cgpa_scale_10(cgpa_raw):
    """Extracts a numeric 10-point CGPA from strings like '8.45', '8.45 / 10', or '84%'."""
    if not cgpa_raw:
        return None
    match = re.search(r"(\d+(?:\.\d+)?)", str(cgpa_raw))
    if not match:
        return None
    val = float(match.group(1))
    if 10.0 < val <= 100.0:
        return round(val / 10.0, 2)
    if 0.0 <= val <= 10.0:
        return round(val, 2)
    return None


def _extract_skill_tokens(skills_raw, resume_raw=""):
    """Normalizes declared skills plus key tech keywords extracted from resume_text."""
    declared = [s.strip() for s in str(skills_raw or "").split(",") if s.strip()]
    seen = {s.lower() for s in declared}

    common_tech = [
        "Python", "Flask", "Django", "FastAPI", "SQL", "SQLite", "PostgreSQL", "MySQL",
        "JavaScript", "TypeScript", "React", "Node.js", "HTML", "CSS", "Git", "Docker",
        "AWS", "Linux", "Java", "C++", "Pandas", "NumPy", "Machine Learning", "REST API",
        "MongoDB", "Express", "Next.js", "Tailwind", "Bootstrap", "PyTorch", "TensorFlow"
    ]
    resume_lower = str(resume_raw or "").lower()
    for tech in common_tech:
        if tech.lower() in resume_lower and tech.lower() not in seen:
            declared.append(tech)
            seen.add(tech.lower())

    return declared


def _compute_role_skill_alignment(skills_list, role_raw, courses_raw):
    """Computes genuine overlap between student skills/courses and target role expectations."""
    role_lower = (role_raw or "software engineering intern").lower()
    skills_lower = {s.lower() for s in skills_list}
    courses_lower = (courses_raw or "").lower()

    role_expectations = {
        "backend": {"python", "flask", "django", "fastapi", "node.js", "sql", "sqlite", "postgresql", "mysql", "rest api", "git", "java"},
        "frontend": {"html", "css", "javascript", "typescript", "react", "next.js", "tailwind", "bootstrap", "git"},
        "full": {"python", "javascript", "html", "css", "sql", "sqlite", "react", "node.js", "flask", "git", "rest api"},
        "data": {"python", "sql", "pandas", "numpy", "machine learning", "pytorch", "tensorflow", "mysql", "postgresql"},
        "ai": {"python", "machine learning", "pytorch", "tensorflow", "pandas", "numpy", "rest api", "flask", "fastapi"},
    }

    target_set = {"python", "sql", "git", "html", "css", "javascript"}
    for key, expected in role_expectations.items():
        if key in role_lower:
            target_set = expected
            break

    matched = [s for s in skills_list if s.lower() in target_set]
    missing = [req.title() for req in sorted(target_set - skills_lower)][:3]

    overlap_ratio = len(matched) / max(len(target_set), 1)
    course_bonus = 4 if any(k in courses_lower for k in ("dbms", "database", "data structures", "os", "web", "algorithms", "ai", "ml")) else 0
    skill_score_boost = int(round(overlap_ratio * 14)) + course_bonus

    return {
        "matched_for_role": matched if matched else skills_list[:3],
        "missing_for_role": missing if missing else ["Docker", "Automated Testing (pytest)"],
        "skill_score_boost": skill_score_boost,
    }


def _analyze_academic_standing(p):
    """
    Computes deterministic CGPA tier bands and role-aligned score ranges
    so CGPA, skills, courses, and projects visibly differentiate every recommendation.
    """
    cgpa_val = _parse_cgpa_scale_10(p.get("cgpa"))
    skills_list = _extract_skill_tokens(p.get("skills"), p.get("resume_text"))
    alignment = _compute_role_skill_alignment(skills_list, p.get("preferred_role"), p.get("courses"))

    projects_text = (p.get("projects") or "").strip()
    project_items = [proj.strip() for proj in re.split(r"[\n;•]+", projects_text) if len(proj.strip()) >= 6]
    project_bonus = min(len(project_items) * 3, 7)

    boost = alignment["skill_score_boost"] + project_bonus

    if cgpa_val is None:
        band = "Unverified CGPA Band (Evaluated on Skills, Courses & Projects)"
        tier_guidance = (
            "CGPA is unspecified. Target Tier 2 Product Scale-ups and Tier 3 Startups that screen "
            "via GitHub projects and coding tasks rather than strict CGPA cutoffs."
        )
        primary_score = min(68 + boost, 90)
        secondary_score = min(72 + boost, 92)
    elif cgpa_val >= 8.5:
        band = f"High Distinction Band ({cgpa_val}/10 — Clears 8.5+ Tier 1 & R&D Cutoffs)"
        tier_guidance = (
            f"At {cgpa_val}/10 CGPA, the candidate clears strict 8.0–8.5+ campus/off-campus cutoffs at "
            "Tier 1 Global Tech R&D Centers as well as Tier 2 Product Scale-ups."
        )
        primary_score = min(78 + boost, 97)
        secondary_score = min(75 + boost, 94)
    elif cgpa_val >= 7.5:
        band = f"Strong Product-Tier Band ({cgpa_val}/10 — Clears 7.0–7.5 Product Cutoffs)"
        tier_guidance = (
            f"At {cgpa_val}/10 CGPA, the candidate clears standard 7.0–7.5 product company cutoffs "
            "(Tier 2 SaaS/Fintech Scale-ups), while some Tier 1 MNCs enforce an 8.0+ gate."
        )
        primary_score = min(72 + boost, 92)
        secondary_score = min(75 + boost, 94)
    elif cgpa_val >= 6.5:
        band = f"Skill-First & Startup Band ({cgpa_val}/10 — Below 7.5 Enterprise Cutoffs)"
        tier_guidance = (
            f"At {cgpa_val}/10 CGPA, automated 7.5+ enterprise filters may screen out the resume; "
            "prioritize Tier 3 VC-Backed Startups and Mid-Size Product Teams that hire via practical tasks."
        )
        primary_score = min(62 + boost, 85)
        secondary_score = min(70 + boost, 89)
    else:
        band = f"Portfolio-Driven Recovery Band ({cgpa_val}/10 — Below Standard CGPA Gates)"
        tier_guidance = (
            f"At {cgpa_val}/10 CGPA, bypass automated GPA screens by targeting early-stage startups "
            "and build-first internships where live projects carry full weight."
        )
        primary_score = min(54 + boost, 78)
        secondary_score = min(65 + boost, 84)

    return {
        "cgpa_numeric": cgpa_val,
        "skills_list": skills_list,
        "project_items": project_items,
        "alignment": alignment,
        "band": band,
        "tier_guidance": tier_guidance,
        "primary_score": primary_score,
        "secondary_score": secondary_score,
    }


def _validate_recommendations(data, academic):
    """Validates parsed JSON and guarantees complete, populated per-company cards."""
    if not isinstance(data, dict):
        return False
    if not isinstance(data.get("opportunities"), list) or len(data["opportunities"]) == 0:
        return False
    if not isinstance(data.get("workflows"), list):
        return False
    if not isinstance(data.get("profile_insights"), list):
        return False

    default_matched = academic["alignment"]["matched_for_role"]
    default_gaps = academic["alignment"]["missing_for_role"]

    for item in data["opportunities"]:
        if not isinstance(item, dict):
            return False
        if not item.get("company_tier") or not isinstance(item.get("companies"), list):
            return False
        if not item.get("matched_role") or not isinstance(item.get("eligibility_points"), list):
            return False

        if not isinstance(item.get("company_cards"), list) or len(item["company_cards"]) == 0:
            item["company_cards"] = [
                {
                    "company_name": comp,
                    "role_title": item["matched_role"],
                    "match_score": item.get("match_score") or academic["primary_score"],
                    "cgpa_cutoff_note": "Evaluated against declared CGPA & completed coursework",
                    "coursework_fit": "Aligned with core CS coursework",
                    "matching_skills": default_matched,
                    "skill_gaps": default_gaps[:2],
                    "project_alignment": "Aligned with candidate's practical development portfolio.",
                    "stipend_duration_fit": "Matches target duration & stipend window",
                    "work_mode": "Hybrid",
                }
                for comp in item["companies"]
            ]
        else:
            for card in item["company_cards"]:
                if not card.get("matching_skills"):
                    card["matching_skills"] = default_matched
                if not card.get("skill_gaps"):
                    card["skill_gaps"] = default_gaps[:2]
                if not card.get("work_mode") or card["work_mode"] not in ("Remote", "On-site", "Hybrid"):
                    card["work_mode"] = "Hybrid"
    return True


def generate_ai_recommendations(profile, override_need=""):
    """
    8-Factor Location-locked, CGPA-calibrated, Coursework-verified, Skill-audited,
    and Project-grounded internship matcher.
    """
    p = dict(profile) if profile else {}
    if override_need and override_need.strip():
        p["what_i_need"] = override_need.strip()

    api_key = os.environ.get("GEMINI_API_KEY", "").strip().strip('"').strip("'")
    model_name = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash").strip()

    if not model_name or model_name == "your-selected-gemini-model":
        model_name = "gemini-2.5-flash"

    academic = _analyze_academic_standing(p)
    skills_joined = ", ".join(academic["skills_list"]) or (p.get("skills") or "Python")

    college = p.get("college") or "Not specified"
    cgpa = p.get("cgpa") or "Not specified"
    degree_branch = p.get("degree_branch") or "Not specified"
    courses = p.get("courses") or "Not specified"
    course_duration = p.get("course_duration") or "4 Years (8 Semesters)"
    current_semester = p.get("current_semester") or "Not specified"
    target_semester = p.get("target_semester") or "Upcoming Semester"
    internship_duration = p.get("internship_duration") or "2 to 6 Months"
    stipend_expectation = p.get("stipend_expectation") or "Paid / Standard"
    what_i_need = p.get("what_i_need") or f"Hands-on {p.get('preferred_role') or 'Software Engineering'} role matching my stack"
    projects = p.get("projects") or "Academic coursework projects"
    role = p.get("preferred_role") or "Software Engineering Intern"
    location = p.get("preferred_location") or "Remote / India"
    resume_text = (p.get("resume_text") or "")[:1800]

    if not api_key or api_key in ("your_actual_gemini_api_key_here", "your-gemini-api-key"):
        return get_platform_native_matches(p, academic, fallback_reason="Missing GEMINI_API_KEY in .env")

    try:
        client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=30000),
        )

        prompt = f"""
You are a strict technical campus & off-campus internship evaluator for Indian engineering students ('InternShip Finder').
Never write generic filler. Every single company card MUST cite exact numbers, completed courses, skills, projects, and user goals from the candidate profile below.

CANDIDATE 8-FACTOR AUDIT PROFILE:
1. College / Institution: {college}
2. Exact CGPA / Score: {cgpa} -> {academic['band']}
  - Cutoff Rule: {academic['tier_guidance']}
3. Degree, Branch & Completed Courses: {degree_branch} | {courses} ({course_duration})
4. Semester Window: Currently in {current_semester} -> Applying for {target_semester}
5. Duration & Stipend Target: {internship_duration} | Expected Stipend: {stipend_expectation}
6. Extracted Technical Skills (Profile + Resume): {skills_joined}
7. Projects Built: {projects}
8. Target Role, Location & Immediate Need ("What I Need"):
  - Preferred Role: {role}
  - Target City / Location: {location}
  - Student's Specific Need: "{what_i_need}"
  - Resume Excerpt: {resume_text if resume_text else "None provided"}

MANDATORY SPECIFICITY RULES:
1. LOCATION LOCK ({location}): Every company MUST have a real engineering center in "{location}" (or be remote-first if "{location}" is Remote). Do NOT claim they are actively hiring today and do NOT invent URLs.
2. COMPANY TIER CALIBRATION:
  - If CGPA >= 8.5, Tier 1 must feature Global Tech R&D / Top Product Giants in {location}, and Tier 2 must feature top SaaS/Fintech Product Scale-ups in {location}.
  - If CGPA is 7.5–8.49, Tier 1 must feature Product Scale-ups in {location} (7.0–7.5 cutoff) and Tier 2 must feature High-Growth Startups in {location}.
  - If CGPA < 7.5, Tier 1 must feature Project-First Startups in {location} (no strict GPA gate) and Tier 2 must feature Mid-Size Product Teams in {location}.
3. INDIVIDUAL COMPANY CARDS (4 in Tier 1, 3 in Tier 2):
  - Give each company a DISTINCT, realistic "match_score" (varying between {max(52, academic['primary_score'] - 7)} and {min(98, academic['primary_score'] + 4)}).
  - "matching_skills": ONLY list technologies the student ACTUALLY possesses in [{skills_joined}].
  - "skill_gaps": Name 1–2 concrete tools that specific company uses which are MISSING from [{skills_joined}].
  - "project_alignment": Name the student's actual project from "{projects}" and explain how to pitch it to that company.
  - "coursework_fit": Connect a specific subject from "{courses}" to that company's engineering work.
  - "cgpa_cutoff_note": State the typical CGPA filter vs {cgpa}.
  - "stipend_duration_fit": Assess {internship_duration} and {stipend_expectation} against "{what_i_need}".
  - "work_mode": Must be strictly one of "Remote", "On-site", or "Hybrid".

Return ONLY valid JSON matching this exact schema:
{{
  "opportunities": [
    {{
      "company_tier": "<Primary Tier calibrated to {cgpa} CGPA in {location}>",
      "companies": ["<Company 1>", "<Company 2>", "<Company 3>", "<Company 4>"],
      "matched_role": "<Specific role aligned with {role} and '{what_i_need}'>",
      "match_score": {academic['primary_score']},
      "location_fit": "<Why these 4 companies fit {location} specifically>",
      "timeline_fit": "<Concrete assessment of {current_semester} -> {target_semester}, {internship_duration}, and {stipend_expectation}>",
      "eligibility_points": [
        "<CGPA ({cgpa}) & completed courses ({courses}) verdict>",
        "<Stack ([{skills_joined}]), projects ({projects}), and goal ('{what_i_need}') verdict>"
      ],
      "company_cards": [
        {{
          "company_name": "<Company 1>",
          "role_title": "<Specific Intern Role at Company 1>",
          "match_score": <int 52-98>,
          "cgpa_cutoff_note": "<Exact CGPA cutoff comparison against {cgpa}>",
          "coursework_fit": "<How '{courses}' applies here>",
          "matching_skills": ["<Matched Skill 1>", "<Matched Skill 2>"],
          "skill_gaps": ["<Missing Skill 1>", "<Missing Skill 2>"],
          "project_alignment": "<How '{projects}' maps to Company 1>",
          "stipend_duration_fit": "<Fit for {internship_duration} & {stipend_expectation}>",
          "work_mode": "<On-site | Hybrid | Remote>"
        }},
        {{
          "company_name": "<Company 2>",
          "role_title": "<Specific Intern Role at Company 2>",
          "match_score": <int 52-98>,
          "cgpa_cutoff_note": "<Exact CGPA cutoff comparison against {cgpa}>",
          "coursework_fit": "<How '{courses}' applies here>",
          "matching_skills": ["<Matched Skill 1>", "<Matched Skill 2>"],
          "skill_gaps": ["<Missing Skill 1>"],
          "project_alignment": "<How '{projects}' maps to Company 2>",
          "stipend_duration_fit": "<Fit for {internship_duration} & {stipend_expectation}>",
          "work_mode": "<On-site | Hybrid | Remote>"
        }},
        {{
          "company_name": "<Company 3>",
          "role_title": "<Specific Intern Role at Company 3>",
          "match_score": <int 52-98>,
          "cgpa_cutoff_note": "<Exact CGPA cutoff comparison against {cgpa}>",
          "coursework_fit": "<How '{courses}' applies here>",
          "matching_skills": ["<Matched Skill 1>", "<Matched Skill 2>"],
          "skill_gaps": ["<Missing Skill 1>"],
          "project_alignment": "<How '{projects}' maps to Company 3>",
          "stipend_duration_fit": "<Fit for {internship_duration} & {stipend_expectation}>",
          "work_mode": "<On-site | Hybrid | Remote>"
        }},
        {{
          "company_name": "<Company 4>",
          "role_title": "<Specific Intern Role at Company 4>",
          "match_score": <int 52-98>,
          "cgpa_cutoff_note": "<Exact CGPA cutoff comparison against {cgpa}>",
          "coursework_fit": "<How '{courses}' applies here>",
          "matching_skills": ["<Matched Skill 1>", "<Matched Skill 2>"],
          "skill_gaps": ["<Missing Skill 1>"],
          "project_alignment": "<How '{projects}' maps to Company 4>",
          "stipend_duration_fit": "<Fit for {internship_duration} & {stipend_expectation}>",
          "work_mode": "<On-site | Hybrid | Remote>"
        }}
      ]
    }},
    {{
      "company_tier": "<Secondary Tier calibrated to {cgpa} CGPA in {location}>",
      "companies": ["<Company 5>", "<Company 6>", "<Company 7>"],
      "matched_role": "<Secondary role aligned with {skills_joined} and '{what_i_need}'>",
      "match_score": {academic['secondary_score']},
      "location_fit": "<Secondary hub advantage in {location}>",
      "timeline_fit": "<How {internship_duration} in {target_semester} fits this tier>",
      "eligibility_points": [
        "<How projects ({projects}) differentiate the candidate here>",
        "<Completed courses ({courses}) and stipend ({stipend_expectation}) alignment>"
      ],
      "company_cards": [
        {{
          "company_name": "<Company 5>",
          "role_title": "<Specific Intern Role at Company 5>",
          "match_score": <int 52-98>,
          "cgpa_cutoff_note": "<Exact CGPA cutoff comparison against {cgpa}>",
          "coursework_fit": "<How '{courses}' applies here>",
          "matching_skills": ["<Matched Skill 1>", "<Matched Skill 2>"],
          "skill_gaps": ["<Missing Skill 1>"],
          "project_alignment": "<How '{projects}' maps to Company 5>",
          "stipend_duration_fit": "<Fit for {internship_duration} & {stipend_expectation}>",
          "work_mode": "<On-site | Hybrid | Remote>"
        }},
        {{
          "company_name": "<Company 6>",
          "role_title": "<Specific Intern Role at Company 6>",
          "match_score": <int 52-98>,
          "cgpa_cutoff_note": "<Exact CGPA cutoff comparison against {cgpa}>",
          "coursework_fit": "<How '{courses}' applies here>",
          "matching_skills": ["<Matched Skill 1>", "<Matched Skill 2>"],
          "skill_gaps": ["<Missing Skill 1>"],
          "project_alignment": "<How '{projects}' maps to Company 6>",
          "stipend_duration_fit": "<Fit for {internship_duration} & {stipend_expectation}>",
          "work_mode": "<On-site | Hybrid | Remote>"
        }},
        {{
          "company_name": "<Company 7>",
          "role_title": "<Specific Intern Role at Company 7>",
          "match_score": <int 52-98>,
          "cgpa_cutoff_note": "<Exact CGPA cutoff comparison against {cgpa}>",
          "coursework_fit": "<How '{courses}' applies here>",
          "matching_skills": ["<Matched Skill 1>", "<Matched Skill 2>"],
          "skill_gaps": ["<Missing Skill 1>"],
          "project_alignment": "<How '{projects}' maps to Company 7>",
          "stipend_duration_fit": "<Fit for {internship_duration} & {stipend_expectation}>",
          "work_mode": "<On-site | Hybrid | Remote>"
        }}
      ]
    }}
  ],
  "workflows": [
    {{
      "target_type": "<Selection track for Primary Tier in {location}>",
      "steps": ["<Step 1>", "<Step 2>", "<Step 3>", "<Step 4>"]
    }},
    {{
      "target_type": "<Selection track for Secondary Tier in {location}>",
      "steps": ["<Step 1>", "<Step 2>", "<Step 3>"]
    }}
  ],
  "profile_insights": [
    "<CGPA ({cgpa}) & Cutoff Audit: Specific action item for {college} / {courses}>",
    "<Skill Gap Action Plan: Top 2 missing skills to add before {target_semester}>",
    "<Project & Goal Pitch: How to quantify '{projects}' for '{what_i_need}' in {location}>"
  ]
}}
"""
        candidate_models = []
        for m in [model_name, "gemini-2.5-flash", "gemini-2.5-flash-lite"]:
            if m and m not in candidate_models:
                candidate_models.append(m)

        response = None
        active_model_used = model_name
        last_err = None

        for candidate in candidate_models:
            try:
                response = client.models.generate_content(
                    model=candidate,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        temperature=0.2,
                        max_output_tokens=8192,
                    ),
                )
                active_model_used = candidate
                break
            except Exception as model_err:
                last_err = model_err
                err_str = str(model_err).upper()
                if any(code in err_str for code in ("404", "NOT_FOUND", "503", "UNAVAILABLE", "429", "RESOURCE_EXHAUSTED", "TIMEOUT", "DEADLINE")):
                    time.sleep(0.5)
                    continue
                raise model_err

        if response is None and last_err is not None:
            raise last_err

        text = (response.text or "").strip()
        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = re.sub(r",\s*([}\]])", r"\1", text.strip())

        parsed = json.loads(text)
        if not _validate_recommendations(parsed, academic):
            logger.warning("Gemini JSON failed validation; activating offline fallback.")
            return get_platform_native_matches(p, academic, fallback_reason="Invalid AI response structure")

        parsed["engine_source"] = f"Gemini Live AI ({active_model_used})"
        parsed["academic_band"] = academic["band"]
        parsed["active_need"] = what_i_need
        return parsed

    except Exception as e:
        logger.error(f"Gemini API error: {e}")
        return get_platform_native_matches(p, academic, fallback_reason=f"API Error: {str(e)[:80]}")


def _get_location_companies(location_raw, cgpa_val):
    """Returns location-specific Tier 1, Tier 2, and Tier 3 example companies in India."""
    loc = (location_raw or "").lower()
    if "chennai" in loc:
        t1 = ["PayPal R&D (Chennai)", "Amazon Development Center (Chennai)", "Oracle (Chennai)", "Autodesk (Chennai)"]
        t2 = ["Zoho (Chennai)", "Freshworks (Chennai)", "Kissflow (Chennai)", "Chargebee (Chennai)"]
        t3 = ["SurveySparrow (Chennai)", "Mad Street Den (Chennai)", "Facilio (Chennai)"]
    elif "bengaluru" in loc or "bangalore" in loc:
        t1 = ["Microsoft IDC (Bengaluru)", "Google India (Bengaluru)", "Intuit (Bengaluru)", "Adobe (Bengaluru)"]
        t2 = ["Razorpay (Bengaluru)", "Postman (Bengaluru)", "BrowserStack (Bengaluru)", "CRED (Bengaluru)"]
        t3 = ["Hasura (Bengaluru)", "Appsmith (Bengaluru)", "Sarvam AI (Bengaluru)"]
    elif "hyderabad" in loc:
        t1 = ["Microsoft IDC (Hyderabad)", "Google (Hyderabad)", "ServiceNow (Hyderabad)", "Salesforce (Hyderabad)"]
        t2 = ["Darwinbox (Hyderabad)", "Kore.ai (Hyderabad)", "Zenoti (Hyderabad)", "HighRadius (Hyderabad)"]
        t3 = ["Yellow.ai (Hyderabad)", "Progress (Hyderabad)", "SenecaGlobal (Hyderabad)"]
    elif "pune" in loc or "mumbai" in loc:
        t1 = ["NVIDIA (Pune)", "Mastercard (Pune)", "Morgan Stanley (Mumbai)", "Barclays Tech (Pune)"]
        t2 = ["Druva (Pune)", "Icertis (Pune)", "PubMatic (Pune)", "Gupshup (Mumbai)"]
        t3 = ["Fynd (Mumbai)", "Simpl (Mumbai)", "MindTickle (Pune)"]
    elif "delhi" in loc or "noida" in loc or "gurgaon" in loc or "gurugram" in loc:
        t1 = ["Microsoft (Noida)", "Adobe (Noida)", "Expedia Group (Gurugram)", "American Express (Gurugram)"]
        t2 = ["Zomato (Gurugram)", "Paytm (Noida)", "PolicyBazaar (Gurugram)", "Info Edge (Noida)"]
        t3 = ["Shiprocket (Delhi NCR)", "Cars24 (Gurugram)", "BharatPe (Delhi NCR)"]
    elif "kochi" in loc or "trivandrum" in loc or "thiruvananthapuram" in loc or "kerala" in loc:
        t1 = ["Oracle (Thiruvananthapuram)", "Nissan Digital (Thiruvananthapuram)", "Allianz Technology (Trivandrum)", "EY GDS (Kochi)"]
        t2 = ["IBS Software (Kochi)", "QBurst (Kochi/Trivandrum)", "UST (Thiruvananthapuram)", "Experion Technologies (Kochi)"]
        t3 = ["KeyValue Software Systems (Kochi)", "Fingent (Kochi)", "litmus7 (Kochi)"]
    else:
        t1 = ["Microsoft IDC (Hybrid/India)", "Intuit (Bengaluru/Remote)", "Atlassian (Remote India)", "GitLab (Remote)"]
        t2 = ["Zoho (Chennai)", "Razorpay (Bengaluru)", "Postman (Bengaluru)", "Darwinbox (Hyderabad)"]
        t3 = ["Hasura (Remote/Bengaluru)", "Appsmith (Remote)", "Wellfound India Remote Startups"]

    if cgpa_val is not None and cgpa_val >= 8.5:
        return t1, t2, "Tier 1: Global Tech R&D & Enterprise Centers", "Tier 2: Product Scale-ups & SaaS Leaders"
    if cgpa_val is not None and cgpa_val < 7.5:
        return t3, t2, "Tier 3: Project-First High-Growth Startups", "Tier 2: Mid-Size Product Engineering Teams"
    return t2, t3, "Tier 2: Product Scale-ups & SaaS Companies", "Tier 3: High-Growth Startups"


def _build_offline_company_cards(companies, base_score, role, cgpa, courses, academic, projects, intern_dur, stipend):
    """Generates rich per-company structured cards when offline fallback is triggered."""
    matched = academic["alignment"]["matched_for_role"]
    gaps = academic["alignment"]["missing_for_role"]
    cards = []
    for idx, comp in enumerate(companies):
        score = max(55, min(96, base_score - (idx * 2)))
        cards.append({
            "company_name": comp,
            "role_title": role,
            "match_score": score,
            "cgpa_cutoff_note": f"Evaluated against {cgpa} CGPA ({academic['band'].split('—')[0].strip()})",
            "coursework_fit": f"Applies {courses[:55]} fundamentals",
            "matching_skills": matched[:4],
            "skill_gaps": [gaps[idx % len(gaps)]],
            "project_alignment": f"Pitch '{projects[:70]}' to prove end-to-end build ownership.",
            "stipend_duration_fit": f"{intern_dur} | {stipend}",
            "work_mode": "Hybrid" if idx % 2 == 0 else "On-site",
        })
    return cards


def get_platform_native_matches(p, academic=None, fallback_reason="Offline Mode"):
    """8-Factor CGPA-calibrated, location-aware, skill-audited offline fallback."""
    if academic is None:
        academic = _analyze_academic_standing(p)

    role = p.get("preferred_role") or "Software Development Intern"
    cgpa = p.get("cgpa") or "Not specified"
    college = p.get("college") or "your institution"
    courses = p.get("courses") or "Core Computer Science"
    course_duration = p.get("course_duration") or "4 Years (8 Semesters)"
    current_sem = p.get("current_semester") or "Current Semester"
    target_sem = p.get("target_semester") or "Target Semester"
    intern_dur = p.get("internship_duration") or "2–6 Months"
    stipend = p.get("stipend_expectation") or "Paid / Standard"
    what_i_need = p.get("what_i_need") or f"Practical {role} experience"
    skills_str = ", ".join(academic["skills_list"]) or "Python, SQL"
    projects = p.get("projects") or "Portfolio Projects"
    location = p.get("preferred_location") or "Remote / India"

    primary_companies, secondary_companies, primary_label, secondary_label = _get_location_companies(
        location, academic["cgpa_numeric"]
    )

    return {
        "engine_source": f"Offline Smart Fallback ({fallback_reason})",
        "academic_band": academic["band"],
        "active_need": what_i_need,
        "opportunities": [
            {
                "company_tier": f"{primary_label} in {location}",
                "companies": primary_companies,
                "matched_role": role,
                "match_score": academic["primary_score"],
                "location_fit": f"Companies with active engineering centers in {location}.",
                "timeline_fit": f"{current_sem} -> {target_sem} ({course_duration}) | {intern_dur} | {stipend}",
                "eligibility_points": [
                    f"CGPA Calibration ({cgpa}): {academic['tier_guidance']}",
                    f"Coursework & Goal Fit: {courses} at {college}; aligned with '{what_i_need}'.",
                ],
                "company_cards": _build_offline_company_cards(
                    primary_companies, academic["primary_score"], role, cgpa, courses, academic, projects, intern_dur, stipend
                ),
            },
            {
                "company_tier": f"{secondary_label} in {location}",
                "companies": secondary_companies,
                "matched_role": f"Junior {role}",
                "match_score": academic["secondary_score"],
                "location_fit": f"Secondary target ecosystem in {location} / Remote.",
                "timeline_fit": f"Aligned with {target_sem} intake for {intern_dur} ({stipend}).",
                "eligibility_points": [
                    f"Coursework alignment ({courses}) and practical stack readiness ({skills_str}).",
                    f"Demonstrated implementation through: {projects[:65]}.",
                ],
                "company_cards": _build_offline_company_cards(
                    secondary_companies, academic["secondary_score"], f"Junior {role}", cgpa, courses, academic, projects, intern_dur, stipend
                ),
            },
        ],
        "workflows": [
            {
                "target_type": f"Primary Track in {location}",
                "steps": [
                    f"Apply 6–8 weeks prior to {target_sem}",
                    "Online Coding & Problem-Solving Assessment",
                    f"Technical Interview focused on {skills_str} & Projects",
                    f"Duration ({intern_dur}) & Stipend ({stipend}) Confirmation",
                ],
            },
            {
                "target_type": f"Secondary / Portfolio Track in {location}",
                "steps": [
                    "Submit Resume with live GitHub project links",
                    "Practical Take-Home Build Task",
                    "Engineering Lead / CTO Discussion",
                ],
            },
        ],
        "profile_insights": [
            f"CGPA & Tier Strategy: {academic['band']} — {academic['tier_guidance']}",
            f"Immediate Need Alignment: Filtered for '{what_i_need}' ({intern_dur}, {stipend}).",
            "Use + Wishlist or Create & Apply Entry directly on any company card above.",
        ],
    }