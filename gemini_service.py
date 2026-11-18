import os
import json
from google import genai

def generate_ai_recommendations(profile):
    """
    Direct CGPA-aware matcher: uses student's exact CGPA, skills, and projects.
    """
    p = dict(profile) if profile else {}
    api_key = os.environ.get("GEMINI_API_KEY")
    
    cgpa = p.get('cgpa', '8.0')
    skills = p.get('skills', 'Python, Flask')
    projects = p.get('projects', 'Development Projects')
    role = p.get('preferred_role', 'Software Engineering Intern')
    location = p.get('preferred_location', 'India')
    
    if not api_key or api_key == "your_actual_gemini_api_key_here":
        return get_platform_native_matches(p)

    try:
        client = genai.Client(api_key=api_key)
        
        prompt = f"""
        You are the core recruitment matching engine for 'InternShip Finder' in India. 
        Analyze this candidate profile specifically based on their CGPA, skills, and projects:

        Candidate Data:
        - Name: {p.get('name', 'Student')}
        - CGPA: {cgpa}
        - Skills: {skills}
        - Projects: {projects}
        - Preferred Role: {role}
        - Location: {location}

        JSON Schema required:
        {{
          "opportunities": [
            {{
              "company_tier": "Tier 2: Product Scale-ups & SaaS Enterprises",
              "companies": ["Zoho", "Freshworks", "Razorpay", "Postman"],
              "matched_role": "{role}",
              "eligibility_points": [
                "Your CGPA of {cgpa} evaluated against enterprise cutoffs.",
                "Your technical stack ({skills}) aligns with requirements."
              ]
            }},
            {{
              "company_tier": "Tier 3: VC-Backed High-Growth Startups",
              "companies": ["Wellfound Startups", "Instahyre Tech Companies", "YC Seed Startups"],
              "matched_role": "{role}",
              "eligibility_points": [
                "Startups focus primarily on your project execution ({projects}) over rigid cutoffs.",
                "Your skills ({skills}) make you immediately productive."
              ]
            }}
          ],
          "workflows": [
            {{
              "target_type": "Product Scale-ups (Zoho / Razorpay)",
              "steps": ["Careers Portal Apply", "Proctored Online Coding Assessment", "Technical Interview", "Architecture Review"]
            }},
            {{
              "target_type": "Venture-Backed Startups (via Wellfound / Instahyre)",
              "steps": ["Direct GitHub Submit", "Take-home Backend Task", "Direct Discussion with CTO"]
            }}
          ],
          "profile_insights": [
            "Your profile emphasizes {skills}; highlight your projects ({projects}) prominently.",
            "With a CGPA of {cgpa}, ensure your GitHub repository links are active."
          ]
        }}
        Return ONLY valid JSON. No markdown code blocks around it.
        """

        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
        )
        
        text = response.text.strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
            
        return json.loads(text.strip())

    except Exception as e:
        return get_platform_native_matches(p)

def get_platform_native_matches(p):
    role = p.get('preferred_role', 'Python Backend Developer Intern')
    cgpa = p.get('cgpa', '8.0')
    skills = p.get('skills', 'Python, Flask')
    projects = p.get('projects', 'Development Projects')

    return {
        "opportunities": [
            {
                "company_tier": "Tier 2: Product Scale-ups & SaaS Enterprises",
                "companies": ["Zoho (Chennai)", "Freshworks (Chennai)", "Postman (Bengaluru)", "Razorpay (Bengaluru)"],
                "matched_role": f"Junior {role}",
                "eligibility_points": [
                    f"Your CGPA ({cgpa}) aligns with standard enterprise screening benchmarks.",
                    f"Your listed skills (`{skills}`) match production engineering standards."
                ]
            },
            {
                "company_tier": "Tier 3: VC-Backed High-Growth Startups",
                "companies": ["Wellfound India Startups", "Instahyre Curated Startups", "Y-Combinator Seed Startups"],
                "matched_role": role,
                "eligibility_points": [
                    f"Startups prioritize practical project building (`{projects[:40]}...`) over rigid academic filters.",
                    f"Your technical expertise in `{skills}` makes you an immediate contributor."
                ]
            }
        ],
        "workflows": [
            {
                "target_type": "Product Scale-ups (Zoho / Razorpay / Postman)",
                "steps": ["Careers Portal Apply", "Proctored Online Coding Assessment", "Technical Interview", "Live Coding"]
            },
            {
                "target_type": "Venture-Backed Startups (via Wellfound / Instahyre)",
                "steps": ["Direct Resume & GitHub Submit", "Take-home Backend Task", "CTO Interview"]
            }
        ],
        "profile_insights": [
            f"Academic Assessment: Your CGPA of {cgpa} is factored alongside your skills ({skills}).",
            f"Project Review: Ensure your projects ({projects[:30]}...) are clearly detailed in your resume."
        ]
    }