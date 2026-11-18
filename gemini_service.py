import os
import re
import json
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
    if val > 10.0 and val <= 100.0:
        return round(val / 10.0, 2)
    if 0.0 <= val <= 10.0:
        return round(val, 2)
    return None


def _analyze_academic_standing(p):
    """
    Computes deterministic CGPA tier bands, semester transition readiness,
    and calibrated match scores so both Gemini and fallback match CGPA accurately.
    """
    cgpa_val = _parse_cgpa_scale_10(p.get("cgpa"))
    skills_list = [s.strip() for s in (p.get("skills") or "").split(",") if s.strip()]
    has_projects = bool((p.get("projects") or "").strip())

    skill_bonus = min(len(skills_list) * 2, 10)
    project_bonus = 6 if has_projects else 0

    if cgpa_val is None:
        band = "Unverified CGPA Band (Skill & Portfolio Evaluated)"
        tier_guidance = "Focus on Tier 2 Mid-Size Product Firms and Tier 3 Startups that evaluate GitHub projects over strict CGPA cutoffs."
        primary_score = min(72 + skill_bonus + project_bonus, 90)
        secondary_score = min(76 + skill_bonus + project_bonus, 92)
    elif cgpa_val >= 8.5:
        band = f"High Distinction Band ({cgpa_val}/10 — Clears 8.5+ Enterprise & R&D Cutoffs)"
        tier_guidance = "Clears strict CGPA filters at Tier 1 Global Tech R&D Centers and top Tier 2 Product Scale-ups, while remaining highly competitive for Tier 3 Startups."
        primary_score = min(84 + skill_bonus + project_bonus, 97)
        secondary_score = min(80 + skill_bonus + project_bonus, 95)
    elif cgpa_val >= 7.5:
        band = f"Strong Product-Tier Band ({cgpa_val}/10 — Clears 7.0–7.5 Product Company Cutoffs)"
        tier_guidance = "Strong match for Tier 2 Product Scale-ups & SaaS Companies (7.0–7.5 cutoff) and Tier 3 High-Growth Startups. Some Tier 1 MNCs enforce an 8.0+ filter."
        primary_score = min(76 + skill_bonus + project_bonus, 92)
        secondary_score = min(80 + skill_bonus + project_bonus, 94)
    elif cgpa_val >= 6.5:
        band = f"Skill-First & Startup Band ({cgpa_val}/10 — Below 7.5 Enterprise Filters)"
        tier_guidance = "Many Tier 1/Tier 2 enterprises enforce a 7.5+ CGPA cutoff; best conversion odds are in Tier 3 VC-Backed Startups and Mid-Size Product Engineering Teams that prioritize live projects."
        primary_score = min(65 + skill_bonus + project_bonus, 84)
        secondary_score = min(76 + skill_bonus + project_bonus, 90)
    else:
        band = f"Portfolio-Driven Recovery Band ({cgpa_val}/10 — Below Standard CGPA Cutoffs)"
        tier_guidance = "Bypass automated CGPA filters by targeting early-stage startups, open-source fellowships, and skill-tested developer internships while improving upcoming semester grades."
        primary_score = min(56 + skill_bonus + project_bonus, 76)
        secondary_score = min(70 + skill_bonus + project_bonus, 85)

    return {
        "cgpa_numeric": cgpa_val,
        "band": band,
        "tier_guidance": tier_guidance,
        "primary_score": primary_score,
        "secondary_score": secondary_score,
    }


def _validate_recommendations(data):
    """Validates that the parsed JSON matches the required template structure."""
    if not isinstance(data, dict):
        return False
    if not isinstance(data.get("opportunities"), list) or len(data["opportunities"]) == 0:
        return False
    if not isinstance(data.get("workflows"), list):
        return False
    if not isinstance(data.get("profile_insights"), list):
        return False
    for item in data["opportunities"]:
        if not isinstance(item, dict):
            return False
        if not item.get("company_tier") or not isinstance(item.get("companies"), list):
            return False
        if not item.get("matched_role") or not isinstance(item.get("eligibility_points"), list):
            return False
        score = item.get("match_score")
        if score is not None and (not isinstance(score, int) or not (0 <= score <= 100)):
            item["match_score"] = None
    return True


def generate_ai_recommendations(profile):
    """
    Location-specific, CGPA-calibrated, and semester-aware internship matcher.
    """
    p = dict(profile) if profile else {}
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    model_name = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash").strip()

    if not model_name or model_name == "your-selected-gemini-model":
        model_name = "gemini-2.5-flash"

    academic = _analyze_academic_standing(p)

    name = p.get('name') or 'Student'
    college = p.get('college') or 'Not specified'
    cgpa = p.get('cgpa') or 'Not specified'
    courses = p.get('courses') or 'Not specified'
    course_duration = p.get('course_duration') or '4 Years (8 Semesters)'
    current_semester = p.get('current_semester') or 'Not specified'
    target_semester = p.get('target_semester') or 'Upcoming Semester'
    internship_duration = p.get('internship_duration') or '2 to 6 Months'
    stipend_expectation = p.get('stipend_expectation') or 'Paid / Standard'
    skills = p.get('skills') or 'Python'
    projects = p.get('projects') or 'Academic coursework projects'
    role = p.get('preferred_role') or 'Software Engineering Intern'
    location = p.get('preferred_location') or 'Remote / India'
    resume_text = (p.get('resume_text') or '')[:1500]

    if not api_key or api_key in ("your_actual_gemini_api_key_here", "your-gemini-api-key"):
        return get_platform_native_matches(p, academic, fallback_reason="Missing GEMINI_API_KEY in .env")

    try:
        client = genai.Client(api_key=api_key)

        prompt = f"""
You are the core internship recommendation engine for 'InternShip Finder' in India.
Generate highly specific, realistic career guidance calibrated to the student's exact CGPA band, college, degree/courses, course duration, semester window, internship duration, stipend expectation, projects, and target city.

CANDIDATE PROFILE (ALL 8 PARAMETERS):
1. College / University: {college}
2. CGPA / Academic Score: {cgpa} -> Pre-Evaluated Standing: {academic['band']}
3. Degree & Completed Courses: {courses}
4. Total Course Duration: {course_duration}
5. Current Semester: {current_semester}
6. Target Semester for Internship: {target_semester}
7. Desired Internship Duration & Stipend ("How Much"): {internship_duration} | Stipend Expectation: {stipend_expectation}
8. Projects Built: {projects}
- Technical Skills: {skills}
- Preferred Internship Role: {role}
- Preferred Location: {location}
- Resume Extract: {resume_text if resume_text else "Not uploaded"}

CALIBRATION & SPECIFICITY RULES:
1. STRICT LOCATION LOCK ({location}): Every single company in "companies" MUST have an established engineering office or active tech hub in "{location}" (or be remote-first if "{location}" is Remote). Never list companies from other cities unless they operate a major development center in "{location}". Clearly treat them as example target employers for guidance—do NOT claim they have active live openings today or generate URLs.
2. STRICT CGPA & TIER MATCHING: Follow this exact CGPA assessment: "{academic['tier_guidance']}". Do NOT recommend 8.5+ CGPA-locked MNCs as high-probability matches if the student's CGPA is below 7.5; instead shift focus to startups and product teams that hire by project portfolio. Set "match_score" around {academic['primary_score']} for the best-fitting tier and {academic['secondary_score']} for the secondary tier.
3. SEMESTER & DURATION REALITY CHECK: Explicitly evaluate the transition from "{current_semester}" to "{target_semester}" inside a "{course_duration}" degree:
   - If target is Semester 5/6, align with 2-month summer internships and realistic summer stipend ranges.
   - If target is Semester 7/8 (or final semester of a 3-year/2-year course), align with 6-month credit-bearing / PPO-track internships.
   - Directly comment on whether "{stipend_expectation}" for "{internship_duration}" is realistic for "{role}" in "{location}".
4. COURSE & PROJECT GROUNDING: Cite specific subjects from "{courses}" and actual builds from "{projects}" in your eligibility points and insights.

Return ONLY valid JSON matching this exact structure:
{{
  "opportunities": [
    {{
      "company_tier": "<Tier 1 / Tier 2 / Tier 3 label calibrated to {cgpa} CGPA>",
      "companies": [
        "<Example Company 1 in {location}>",
        "<Example Company 2 in {location}>",
        "<Example Company 3 in {location}>",
        "<Example Company 4 in {location}>"
      ],
      "matched_role": "<Specific role matching {role} and {skills}>",
      "match_score": {academic['primary_score']},
      "location_fit": "<Why these 4 companies match {location} specifically>",
      "timeline_fit": "<Evaluation of {current_semester} -> {target_semester} ({course_duration}), {internship_duration}, and {stipend_expectation}>",
      "eligibility_points": [
        "<CGPA ({cgpa}) & College ({college}) cutoff evaluation for {courses}>",
        "<Project ({projects}) & Skills ({skills}) technical evaluation>"
      ]
    }},
    {{
      "company_tier": "<Secondary Tier calibrated to {cgpa} CGPA>",
      "companies": [
        "<Example Company 5 in {location}>",
        "<Example Company 6 in {location}>",
        "<Example Company 7 in {location}>"
      ],
      "matched_role": "<Alternative/adjacent role matching {skills}>",
      "match_score": {academic['secondary_score']},
      "location_fit": "<Local ecosystem fit in {location}>",
      "timeline_fit": "<How {internship_duration} in {target_semester} fits this tier's hiring cycle>",
      "eligibility_points": [
        "<How projects ({projects}) strengthen candidacy here>",
        "<Skill gap or coursework ({courses}) advantage>"
      ]
    }}
  ],
  "workflows": [
    {{
      "target_type": "<Selection track for Tier 1/2 in {location}>",
      "steps": ["<Step 1>", "<Step 2>", "<Step 3>", "<Step 4>"]
    }},
    {{
      "target_type": "<Selection track for Startups/Product Teams in {location}>",
      "steps": ["<Step 1>", "<Step 2>", "<Step 3>"]
    }}
  ],
  "profile_insights": [
    "<CGPA ({cgpa}) & Academic Standing ({college}, {courses}, {course_duration}) strategy>",
    "<Semester & Compensation Plan: Preparing between {current_semester} and {target_semester} for {internship_duration} ({stipend_expectation})>",
    "<Project & Resume Upgrade: Specific improvement for {projects} targeting {role} in {location}>"
  ]
}}
"""

        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.25
            )
        )

        text = response.text.strip()
        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]

        parsed = json.loads(text.strip())
        if not _validate_recommendations(parsed):
            logger.warning("Gemini JSON failed validation; activating offline fallback.")
            return get_platform_native_matches(p, academic, fallback_reason="Invalid AI response structure")

        parsed["engine_source"] = f"Gemini Live AI ({model_name})"
        parsed["academic_band"] = academic["band"]
        return parsed

    except Exception as e:
        logger.error(f"Gemini API error: {e}")
        return get_platform_native_matches(p, academic, fallback_reason=f"API Error: {str(e)[:80]}")


def _get_location_companies(location_raw, cgpa_val):
    """Returns location-specific Tier 2 and Tier 3 example companies in India."""
    loc = (location_raw or "").lower()
    if "chennai" in loc:
        t2 = ["Zoho (Chennai)", "Freshworks (Chennai)", "Kissflow (Chennai)", "Chargebee (Chennai)"]
        t3 = ["SurveySparrow (Chennai)", "Mad Street Den (Chennai)", "Facilio (Chennai)"]
    elif "bengaluru" in loc or "bangalore" in loc:
        t2 = ["Razorpay (Bengaluru)", "Postman (Bengaluru)", "BrowserStack (Bengaluru)", "CRED (Bengaluru)"]
        t3 = ["Hasura (Bengaluru)", "Appsmith (Bengaluru)", "Sarvam AI (Bengaluru)"]
    elif "hyderabad" in loc:
        t2 = ["Darwinbox (Hyderabad)", "Kore.ai (Hyderabad)", "Zenoti (Hyderabad)", "HighRadius (Hyderabad)"]
        t3 = ["Yellow.ai (Hyderabad)", "Progress (Hyderabad)", "SenecaGlobal (Hyderabad)"]
    elif "pune" in loc or "mumbai" in loc:
        t2 = ["Druva (Pune)", "Icertis (Pune)", "PubMatic (Pune)", "Gupshup (Mumbai)"]
        t3 = ["Fynd (Mumbai)", "Simpl (Mumbai)", "MindTickle (Pune)"]
    elif "delhi" in loc or "noida" in loc or "gurgaon" in loc or "gurugram" in loc:
        t2 = ["Zomato (Gurugram)", "Paytm (Noida)", "PolicyBazaar (Gurugram)", "Info Edge (Noida)"]
        t3 = ["Shiprocket (Delhi NCR)", "Cars24 (Gurugram)", "BharatPe (Delhi NCR)"]
    elif "kochi" in loc or "trivandrum" in loc or "thiruvananthapuram" in loc or "kerala" in loc:
        t2 = ["IBS Software (Kochi)", "QBurst (Kochi/Trivandrum)", "UST (Thiruvananthapuram)", "Experion Technologies (Kochi)"]
        t3 = ["KeyValue Software Systems (Kochi)", "Fingent (Kochi)", "litmus7 (Kochi)"]
    else:
        t2 = ["Zoho (Chennai)", "Razorpay (Bengaluru)", "Postman (Bengaluru)", "Darwinbox (Hyderabad)"]
        t3 = ["Hasura (Remote/Bengaluru)", "Appsmith (Remote)", "Wellfound India Remote Startups"]

    if cgpa_val is not None and cgpa_val < 7.5:
        return t3, t2
    return t2, t3


def get_platform_native_matches(p, academic=None, fallback_reason="Offline Mode"):
    """CGPA-calibrated, location-aware, semester-specific offline fallback."""
    if academic is None:
        academic = _analyze_academic_standing(p)

    role = p.get('preferred_role') or 'Software Development Intern'
    cgpa = p.get('cgpa') or 'Not specified'
    college = p.get('college') or 'your institution'
    courses = p.get('courses') or 'Core Computer Science'
    course_duration = p.get('course_duration') or '4 Years (8 Semesters)'
    current_sem = p.get('current_semester') or 'Current Semester'
    target_sem = p.get('target_semester') or 'Target Semester'
    intern_dur = p.get('internship_duration') or '2–6 Months'
    stipend = p.get('stipend_expectation') or 'Paid / Standard'
    skills = p.get('skills') or 'Python, SQL'
    projects = p.get('projects') or 'Portfolio Projects'
    location = p.get('preferred_location') or 'Remote / India'

    primary_companies, secondary_companies = _get_location_companies(location, academic["cgpa_numeric"])
    low_cgpa = academic["cgpa_numeric"] is not None and academic["cgpa_numeric"] < 7.5

    primary_tier = (
        f"Tier 3: Project-First High-Growth Startups in {location}"
        if low_cgpa
        else f"Tier 2: Product Scale-ups & SaaS Companies in {location}"
    )
    secondary_tier = (
        f"Tier 2: Mid-Size Product Engineering Teams in {location}"
        if low_cgpa
        else f"Tier 3: High-Growth Startups in {location}"
    )

    return {
        "engine_source": f"Offline Smart Fallback ({fallback_reason})",
        "academic_band": academic["band"],
        "opportunities": [
            {
                "company_tier": primary_tier,
                "companies": primary_companies,
                "matched_role": role,
                "match_score": academic["primary_score"],
                "location_fit": f"Example companies with active engineering centers in {location}.",
                "timeline_fit": f"{current_sem} -> {target_sem} ({course_duration}) | Duration: {intern_dur} | Stipend: {stipend}",
                "eligibility_points": [
                    f"CGPA Calibration ({cgpa}): {academic['tier_guidance']}",
                    f"Academic & Project Fit: {courses} at {college}; projects ({projects[:65]}) + skills ({skills})."
                ]
            },
            {
                "company_tier": secondary_tier,
                "companies": secondary_companies,
                "matched_role": f"Junior {role}",
                "match_score": academic["secondary_score"],
                "location_fit": f"Secondary target ecosystem in {location} / Remote.",
                "timeline_fit": f"Aligned with {target_sem} intake for a {intern_dur} commitment ({stipend}).",
                "eligibility_points": [
                    f"Coursework alignment ({courses}) and practical stack readiness ({skills}).",
                    f"Demonstrated implementation through: {projects[:65]}."
                ]
            }
        ],
        "workflows": [
            {
                "target_type": f"Primary Track in {location}",
                "steps": [
                    f"Apply 6–8 weeks prior to {target_sem}",
                    "Online Coding & Problem-Solving Assessment",
                    f"Technical Interview focused on {skills} & Projects",
                    f"Duration ({intern_dur}) & Stipend ({stipend}) Confirmation"
                ]
            },
            {
                "target_type": f"Startup / Portfolio Track in {location}",
                "steps": [
                    "Submit Resume with live GitHub project links",
                    "Practical Take-Home Build Task",
                    "Engineering Lead / CTO Discussion"
                ]
            }
        ],
        "profile_insights": [
            f"CGPA & Tier Strategy: {academic['band']} — {academic['tier_guidance']}",
            f"Timeline & Stipend Fit: Transitioning from {current_sem} to {target_sem} ({course_duration}) for {intern_dur} at {stipend}.",
            "Career Guidance Notice: Listed companies are location-matched examples for preparation, not live job openings."
        ]
    }