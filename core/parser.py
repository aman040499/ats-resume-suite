# -*- coding: utf-8 -*-
import os
import io
import json
import re
from typing import Dict, Any, Optional, Union, List, Tuple
import pypdf
import pdfplumber

from core.gemini_client import call_gemini, ping_gemini

def extract_links_from_pdf(pdf_source: Union[str, bytes, io.BytesIO]) -> List[str]:
    """Extracts all hyperlinks and URIs embedded in PDF annotations."""
    if isinstance(pdf_source, str):
        with open(pdf_source, "rb") as f:
            pdf_bytes = io.BytesIO(f.read())
    elif isinstance(pdf_source, bytes):
        pdf_bytes = io.BytesIO(pdf_source)
    else:
        pdf_bytes = pdf_source

    links = []
    try:
        pdf_bytes.seek(0)
        reader = pypdf.PdfReader(pdf_bytes)
        for page in reader.pages:
            if "/Annots" in page:
                for annot in page["/Annots"]:
                    obj = annot.get_object()
                    if "/A" in obj and "/URI" in obj["/A"]:
                        uri = str(obj["/A"]["/URI"]).strip()
                        if uri and uri not in links:
                            links.append(uri)
    except Exception as e:
        print(f"[Parser Warning] Link extraction: {e}")
    return links

def extract_text_from_pdf(pdf_source: Union[str, bytes, io.BytesIO]) -> str:
    if isinstance(pdf_source, str):
        with open(pdf_source, "rb") as f:
            pdf_bytes = io.BytesIO(f.read())
    elif isinstance(pdf_source, bytes):
        pdf_bytes = io.BytesIO(pdf_source)
    else:
        pdf_bytes = pdf_source

    pypdf_text = []
    try:
        pdf_bytes.seek(0)
        reader = pypdf.PdfReader(pdf_bytes)
        for page in reader.pages:
            t = page.extract_text()
            if t:
                pypdf_text.append(t)
    except Exception as e:
        print(f"[Parser Warning] pypdf: {e}")

    pypdf_str = "\n".join(pypdf_text).strip()

    pdfplumber_text = []
    try:
        pdf_bytes.seek(0)
        with pdfplumber.open(pdf_bytes) as pdf:
            for page in pdf.pages:
                pt = page.extract_text(layout=False) or page.extract_text(layout=True)
                if pt:
                    pdfplumber_text.append(pt)
    except Exception as e2:
        print(f"[Parser Warning] pdfplumber: {e2}")

    pdfplumber_str = "\n".join(pdfplumber_text).strip()

    if len(pdfplumber_str) >= len(pypdf_str):
        return pdfplumber_str
    return pypdf_str

def test_gemini_api_key(api_key: str) -> Tuple[bool, str]:
    return ping_gemini(api_key)

def parse_resume_profile(
    raw_text: str,
    engine: str = "on_premises",
    api_key: Optional[str] = None,
    pdf_links: Optional[List[str]] = None
) -> Dict[str, Any]:
    """Universal multi-industry resume profiler with zero-storage Gemini cloud or local fallback."""
    raw_key = api_key or ""
    key = str(raw_key).strip().strip('"').strip("'") if raw_key else ""

    if engine == "gemini" and key:
        prompt = f"""
        Analyze this resume and extract candidate profile JSON.
        CRITICAL REQUIREMENTS:
        1. ACCURATELY IDENTIFY THE CANDIDATE'S ACTUAL DOMAIN (Banking & Financial Services, IT Support & Systems, Accounting & Finance, Software Engineering, Healthcare, Human Resources, etc.).
        2. DETERMINE 6-8 HIGHLY TARGETED JOB TITLES THAT DIRECTLY MATCH THEIR ACTUAL RESPONSIBILITIES AND CAREER PROGRESSION.
           DO NOT invent unrelated titles. NEVER return company names, city names, or universities as titles.
        3. EXTRACT ALL VERIFIED CORE SKILLS, COMPLIANCE KNOWLEDGE, AND TECHNICAL SOFTWARE MENTIONED.
        4. EXTRACT ALL WORK EXPERIENCE ROLES IN FULL DEPTH:
           - Include EVERY employer and position held.
           - Preserve 5 to 10 rich, detailed accomplishment bullets per position. DO NOT compress to 2-3 bullets.
           - Extract company-specific and departmental achievements/awards.
        5. EXTRACT ALL DEGREES, CERTIFICATIONS, AND LICENSES.

        RESUME TEXT:
        {raw_text[:9000]}

        Return STRICTLY valid JSON conforming to:
        {{
            "personal": {{
                "name": "Full Name",
                "email": "Email",
                "phone": "Phone",
                "location": "City, Province/State",
                "country": "Canada or USA or UK",
                "linkedin": "LinkedIn URL or empty",
                "github": "Portfolio / GitHub URL or empty"
            }},
            "summary": "Professional summary paragraph or empty",
            "domain": "Accurate Domain Name",
            "target_job_titles": [
                "Title 1", "Title 2", "Title 3", "Title 4", "Title 5"
            ],
            "seniority_level": "Senior (~5 yrs) or Mid (~3 yrs) or Junior (~1 yr)",
            "years_of_experience": 5,
            "skills": {{
                "core_competencies": ["Skill 1", "Skill 2"],
                "industry_and_compliance": ["Compliance 1", "Compliance 2"],
                "software_and_tools": ["Tool 1", "Tool 2"]
            }},
            "experience": [
                {{
                    "company": "Company Name",
                    "title": "Exact Ground-Truth Job Title",
                    "dates": "Exact Dates",
                    "location": "Location",
                    "bullets": ["Detailed Bullet 1", "Detailed Bullet 2", "Detailed Bullet 3", "Detailed Bullet 4", "Detailed Bullet 5"],
                    "achievements": ["Award or honor if applicable"]
                }}
            ],
            "projects": [
                {{
                    "title": "Project Title",
                    "technologies": "Technologies used",
                    "bullets": ["Bullet 1", "Bullet 2"]
                }}
            ],
            "education": [
                {{
                    "degree": "Degree Name",
                    "institution": "Institution Name",
                    "year": "Month & Year",
                    "details": "Concentrations or honors"
                }}
            ],
            "certifications": ["Certification 1", "Certification 2"],
            "achievements": ["Major Award 1", "Major Award 2"]
        }}
        """
        success, resp_text, model_or_err = call_gemini(key, prompt, json_mode=True)
        if success:
            try:
                data = json.loads(resp_text)
                data["engine_used"] = f"Gemini ({model_or_err})"
                data["llm_status"] = "success"
                # Ensure certifications, achievements, and projects exist
                if not data.get("certifications") or not data.get("projects"):
                    loc_exp, loc_projs, loc_edu, certs, achs, _, _, loc_custom_heads, loc_add_secs = extract_full_candidate_history(raw_text)
                    if not data.get("certifications"):
                        data["certifications"] = certs
                    if not data.get("achievements"):
                        data["achievements"] = achs
                    if not data.get("projects"):
                        data["projects"] = loc_projs
                    if not data.get("education") and loc_edu:
                        data["education"] = loc_edu
                    if not data.get("custom_headings"):
                        data["custom_headings"] = loc_custom_heads
                    if not data.get("additional_sections"):
                        data["additional_sections"] = loc_add_secs
                if pdf_links:
                    for lk in pdf_links:
                        if "linkedin.com" in lk.lower() and not data["personal"].get("linkedin"):
                            data["personal"]["linkedin"] = lk
                        elif any(gw in lk.lower() for gw in ["github.com", "portfolio", "gitlab.com"]) and not data["personal"].get("github"):
                            data["personal"]["github"] = lk
                return data
            except Exception as parse_err:
                print(f"[Parser] Gemini JSON parse error: {parse_err}")

        fallback_res = universal_on_premises_parser(raw_text)
        fallback_res["engine_used"] = "Local Offline Engine (Gemini fallback)"
        fallback_res["llm_error"] = model_or_err
        if pdf_links:
            for lk in pdf_links:
                if "linkedin.com" in lk.lower():
                    fallback_res["personal"]["linkedin"] = lk
                elif any(gw in lk.lower() for gw in ["github.com", "portfolio", "gitlab.com"]):
                    fallback_res["personal"]["github"] = lk
        return fallback_res

    res = universal_on_premises_parser(raw_text)
    res["engine_used"] = "100% On-Premises Local Engine"
    if pdf_links:
        for lk in pdf_links:
            if "linkedin.com" in lk.lower():
                res["personal"]["linkedin"] = lk
            elif any(gw in lk.lower() for gw in ["github.com", "portfolio", "gitlab.com"]):
                res["personal"]["github"] = lk
    return res

def _extract_clean_explicit_titles(raw_text: str) -> List[str]:
    role_kws = {
        'specialist', 'analyst', 'advisor', 'banker', 'representative', 'officer', 'manager', 
        'administrator', 'admin', 'technician', 'engineer', 'consultant', 'associate', 'teller', 
        'underwriter', 'coordinator', 'clerk', 'auditor', 'accountant', 'developer', 'architect', 
        'lead', 'supervisor', 'generalist', 'recruiter', 'director', 'investigator',
        'doctor', 'nurse', 'therapist', 'practitioner', 'pharmacist', 'scientist', 'researcher',
        'designer', 'copywriter', 'strategist', 'marketer', 'buyer', 'planner', 'counsel',
        'attorney', 'paralegal', 'executive', 'treasurer', 'controller', 'broker', 'trader',
        'operator', 'instructor', 'teacher', 'professor', 'programmer', 'scientist'
    }
    blacklist_words = {
        'college', 'university', 'school', 'press', 'microsoft', 'google', 'ibm', 'amazon', 
        'summary', 'skills', 'education', 'experience', 'interests', 'languages', 'certifications',
        'curriculum', 'resume', 'phone', 'email', 'linkedin', 'github', 'portfolio', 'incident',
        'degree', 'diploma', 'bachelor', 'master', 'post graduate', 'certificate', 'institute',
        'references', 'activities', 'hobbies', 'awards'
    }
    found = []
    lines = [l.strip() for l in raw_text.splitlines() if l.strip()]
    for line in lines:
        clean_l = re.sub(r'\(.*?\)', '', line)
        clean_l = re.sub(r'\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4}\b', '', clean_l, flags=re.I)
        clean_l = re.sub(r'\b\d{4}\s*[\u2014\u2013\-]\s*\d{4}\b', '', clean_l)
        clean_l = re.sub(r'\b\d{4}\s*[\u2014\u2013\-]\s*(Present|Current)\b', '', clean_l, flags=re.I)
        parts = re.split(r'[\u2014\u2013\|\t•]', clean_l)
        for p in parts:
            p_strip = p.strip().strip(':-–| ')
            words = [w.lower() for w in re.findall(r'[A-Za-z]+', p_strip)]
            if any(w in role_kws for w in words):
                if not any(b in p_strip.lower() for b in blacklist_words):
                    if 1 <= len(words) <= 5:
                        formatted = ' '.join(w.title() for w in p_strip.split())
                        formatted = formatted.replace('It Support', 'IT Support').replace('It Systems', 'IT Systems').replace('Ui/Ux', 'UI/UX').replace('Qa', 'QA')
                        if formatted not in found:
                            found.append(formatted)
    return found

def extract_full_candidate_history(raw_text: str):
    """
    Universal multi-industry parser:
    Extracts career depth, projects, education, certifications, awards, custom headings,
    and preserves unknown/custom sections in additional_sections.
    """
    text = re.sub(r'[\ufffd\u2013\u2014]', '—', raw_text)
    raw_lines = [l.strip() for l in text.splitlines() if l.strip()]
    
    sec_kws = {
        'SUMMARY': [
            'PROFESSIONAL SUMMARY', 'SUMMARY', 'EXECUTIVE SUMMARY', 'SUMMARY STATEMENT',
            'PROFILE', 'ABOUT ME', 'PERSONAL PROFILE', 'PROFESSIONAL PROFILE',
            'CAREER SUMMARY', 'OBJECTIVE', 'CAREER OBJECTIVE', 'OVERVIEW',
            'QUALIFICATIONS SUMMARY', 'EXECUTIVE PROFILE', 'HIGHLIGHTS OF QUALIFICATIONS'
        ],
        'SKILLS': [
            'TECHNICAL SKILLS', 'SKILLS', 'CORE COMPETENCIES', 'CORE SKILLS',
            'AREAS OF EXPERTISE', 'KEY SKILLS', 'SKILLS & COMPETENCIES',
            'TECHNICAL EXPERTISE', 'TOOLKIT', 'PROFICIENCIES', 'COMPETENCIES',
            'TECHNICAL PROFICIENCIES', 'SKILLS & EXPERTISE', 'PROFESSIONAL SKILLS',
            'KEY COMPETENCIES', 'CORE QUALIFICATIONS', 'RELEVANT SKILLS'
        ],
        'EXPERIENCE': [
            'PROFESSIONAL EXPERIENCE', 'WORK EXPERIENCE', 'EXPERIENCE',
            'EMPLOYMENT HISTORY', 'WORK HISTORY', 'CAREER HISTORY',
            'RELEVANT EXPERIENCE', 'EXPERIENCE & RESPONSIBILITIES',
            'PROFESSIONAL BACKGROUND', 'CAREER HIGHLIGHTS', 'EMPLOYMENT'
        ],
        'PROJECTS': [
            'PROJECTS', 'PROJECT', 'TECHNICAL PROJECTS', 'KEY PROJECTS',
            'ACADEMIC PROJECTS', 'SELECTED PROJECTS', 'PERSONAL PROJECTS',
            'NOTABLE PROJECTS', 'PORTFOLIO', 'PROJECT WORK'
        ],
        'EDUCATION': [
            'EDUCATION & CERTIFICATIONS', 'EDUCATION AND CERTIFICATIONS',
            'EDUCATION', 'ACADEMIC BACKGROUND', 'ACADEMIC QUALIFICATIONS',
            'EDUCATIONAL BACKGROUND', 'QUALIFICATIONS', 'ACADEMIC CREDENTIALS',
            'DEGREES & EDUCATION'
        ],
        'CERTIFICATIONS': [
            'CERTIFICATIONS & LICENSES', 'CERTIFICATIONS AND LICENSES', 'LICENSES & CERTIFICATIONS',
            'CERTIFICATIONS', 'LICENSES', 'CERTIFICATES', 'PROFESSIONAL CERTIFICATIONS',
            'CREDENTIALS', 'PROFESSIONAL DEVELOPMENT', 'LICENSING & CREDENTIALS'
        ],
        'ACHIEVEMENTS': [
            'KEY HONORS & PROFESSIONAL RECOGNITION', 'HONORS & AWARDS',
            'AWARDS & HONORS', 'AWARDS', 'ACHIEVEMENTS', 'KEY ACHIEVEMENTS',
            'ACCOMPLISHMENTS', 'HONORS', 'RECOGNITIONS', 'PROFESSIONAL HONORS'
        ]
    }
    
    lines_by_sec = {
        'HEADER': [], 'SUMMARY': [], 'SKILLS': [], 'EXPERIENCE': [], 
        'PROJECTS': [], 'EDUCATION': [], 'CERTIFICATIONS': [], 'ACHIEVEMENTS': []
    }
    custom_headings = {}
    additional_sections = []
    current_custom_sec = None

    current_sec = 'HEADER'
    for l in raw_lines:
        clean_upper = l.upper().strip(': ')
        matched_sec = None
        matched_kw = None
        matched_post = None
        for sec_name, keywords in sec_kws.items():
            for kw in sorted(keywords, key=len, reverse=True):
                if clean_upper == kw or clean_upper == kw + ':' or clean_upper.startswith(kw + '—') or clean_upper.startswith(kw + '-'):
                    matched_sec = sec_name
                    matched_kw = l.strip(': ')
                    break
                elif clean_upper.startswith(kw + ':'):
                    matched_sec = sec_name
                    matched_kw = kw
                    matched_post = l.split(':', 1)[1].strip()
                    break
                elif clean_upper.startswith(kw + ' ') and len(clean_upper.split()) <= 4:
                    matched_sec = sec_name
                    matched_kw = l.strip(': ')
                    break
            if matched_sec:
                break

        if matched_sec:
            current_sec = matched_sec
            current_custom_sec = None
            if matched_sec.lower() not in custom_headings:
                custom_headings[matched_sec.lower()] = matched_kw
            if matched_post:
                lines_by_sec[matched_sec].append(matched_post)
        else:
            # Check if this line looks like an unknown/custom section heading (e.g. PUBLICATIONS, VOLUNTEER, LANGUAGES)
            is_potential_custom_heading = (
                len(l.split()) <= 4 and len(l) <= 40
                and (l.isupper() or l.istitle())
                and not l.startswith(('•', '*', '-', '·'))
                and not any(c in l for c in ['@', 'http', 'www', '|', '\\', '/', '(', ')'])
                and not re.search(r'\b(19|20)\d{2}\b', l)
                and current_sec in ['EDUCATION', 'CERTIFICATIONS', 'ACHIEVEMENTS', 'PROJECTS']
            )
            if is_potential_custom_heading:
                current_custom_sec = l.strip(': ')
                current_sec = 'ADDITIONAL'
                additional_sections.append({'title': current_custom_sec, 'content': []})
            else:
                if current_sec == 'ADDITIONAL' and additional_sections:
                    additional_sections[-1]['content'].append(l)
                elif current_sec in lines_by_sec:
                    lines_by_sec[current_sec].append(l)

    # 1. Summary
    extracted_summary = " ".join(lines_by_sec['SUMMARY']).strip()

    # 2. Skills (Universal, data-driven categories)
    extracted_skills = {}
    current_cat = 'Core Competencies'
    merged_skill_lines = []
    for l in lines_by_sec['SKILLS']:
        clean = l.strip('•*-· \t')
        is_new = l.startswith(('•', '*', '-', '·')) or (':' in clean and len(clean.split(':', 1)[0].split()) <= 5)
        if is_new or not merged_skill_lines:
            merged_skill_lines.append(clean)
        else:
            merged_skill_lines[-1] += ' ' + clean

    for l in merged_skill_lines:
        clean = l.strip('•*-· \t')
        if not clean:
            continue
        if ':' in clean:
            parts = clean.split(':', 1)
            cat = parts[0].strip()
            items_str = parts[1].strip()
            if any(ck in cat.lower() for ck in ['certif', 'licens', 'credential']):
                c_items = [i.strip() for i in re.split(r'[,|•·;]', items_str) if i.strip()]
                for it in c_items:
                    lines_by_sec['CERTIFICATIONS'].append(it)
                continue
            if len(cat.split()) <= 6 and len(cat) <= 55:
                current_cat = cat
                items = [i.strip() for i in re.split(r'[,|•·;]', items_str) if i.strip()]
                extracted_skills[current_cat] = items
                continue
        items = [i.strip() for i in re.split(r'[,|•·;]', clean) if i.strip()]
        if current_cat in extracted_skills:
            extracted_skills[current_cat].extend(items)
        else:
            extracted_skills[current_cat] = items

    cleaned_skills = {}
    for cat, items in extracted_skills.items():
        seen = set()
        c_items = []
        for it in items:
            it_c = it.strip().strip(':')
            if it_c and it_c.lower() not in seen and len(it_c) > 1:
                seen.add(it_c.lower())
                c_items.append(it_c)
        if c_items:
            cleaned_skills[cat] = c_items

    # 3. Experience
    exp_lines = lines_by_sec['EXPERIENCE']
    experience = []
    curr_exp = None
    in_achievements = False
    date_regex = re.compile(r'(\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4}\b|\b\d{4}\s*[\u2014\u2013—–\-]\s*(?:Present|Current|\d{4})\b|\b(19|20)\d{2}\b)', re.I)

    i = 0
    while i < len(exp_lines):
        line = exp_lines[i]
        is_bullet_start = line.startswith(('•', '*', '-', '·'))
        
        if not is_bullet_start and (i + 1 < len(exp_lines)):
            next_line = exp_lines[i+1]
            d_curr = date_regex.search(line)
            d_next = date_regex.search(next_line)
            
            if d_next and not d_curr:
                if curr_exp:
                    experience.append(curr_exp)
                
                # Pattern A: line = "Title — Company", next_line = "Dates | Location"
                if any(sep in line for sep in ['—', '–']) or ' - ' in line:
                    parts = re.split(r'[—–]| - ', line)
                    p0 = parts[0].strip()
                    p1 = parts[1].strip() if len(parts) > 1 else ''
                    
                    role_words = {'specialist', 'analyst', 'clerk', 'representative', 'officer', 'technician', 'engineer', 'lead', 'manager', 'associate', 'administrator', 'banker', 'advisor', 'consultant', 'developer', 'nurse', 'doctor', 'accountant', 'director'}
                    if any(w in p0.lower() for w in role_words):
                        title, company = p0, p1
                    elif any(w in p1.lower() for w in role_words):
                        title, company = p1, p0
                    else:
                        title, company = p0, p1
                        
                    nl_parts = [p.strip() for p in next_line.split('|')]
                    dates = nl_parts[0]
                    location = nl_parts[1] if len(nl_parts) > 1 else ''
                    curr_exp = {'title': title, 'company': company, 'dates': dates, 'location': location, 'bullets': [], 'achievements': []}
                    in_achievements = False
                    i += 2
                    continue
                elif '|' in line:
                    # Pattern B: line = "Company | Location", next_line = "Title (Dates)"
                    c_parts = [p.strip() for p in line.split('|')]
                    company = c_parts[0]
                    location = c_parts[1] if len(c_parts) > 1 else ''
                    
                    t_match = re.search(r'^(.*?)\s*[\(\[]([^\(\)]*?\d{4}[^\(\)]*)[\)\]]$', next_line)
                    if t_match:
                        title = t_match.group(1).strip('—–- ')
                        dates = t_match.group(2).strip('()[] ')
                    else:
                        title = next_line
                        dates = ''
                    curr_exp = {'title': title, 'company': company, 'dates': dates, 'location': location, 'bullets': [], 'achievements': []}
                    in_achievements = False
                    i += 2
                    continue

        if curr_exp:
            clean_b = line.strip('•*-· \t')
            if clean_b:
                ach_label_match = re.match(r'^(?:Key\s+Achievements?|Key\s+Accomplishments?|Achievements?|Major\s+Achievements?|Awards?):?\s*(.*)$', clean_b, re.IGNORECASE)
                if ach_label_match:
                    in_achievements = True
                    post_text = ach_label_match.group(1).strip('•*-· \t')
                    if post_text:
                        curr_exp['achievements'].append(post_text)
                elif in_achievements:
                    if is_bullet_start or not curr_exp['achievements']:
                        curr_exp['achievements'].append(clean_b)
                    else:
                        curr_exp['achievements'][-1] += " " + clean_b
                else:
                    if re.search(r'(?:Key\s+Achievements?|Key\s+Accomplishments?|Achievements?):?', clean_b, re.IGNORECASE):
                        parts = re.split(r'(?:Key\s+Achievements?|Key\s+Accomplishments?|Achievements?):?', clean_b, flags=re.IGNORECASE)
                        bullet_part = parts[0].strip('•*-· \t')
                        ach_part = parts[1].strip('•*-· \t') if len(parts) > 1 else ''
                        if bullet_part:
                            curr_exp['bullets'].append(bullet_part)
                        if ach_part:
                            curr_exp['achievements'].append(ach_part)
                            in_achievements = True
                    elif is_bullet_start:
                        curr_exp['bullets'].append(clean_b)
                    elif curr_exp['bullets']:
                        curr_exp['bullets'][-1] += " " + clean_b
                    else:
                        curr_exp['bullets'].append(clean_b)
        i += 1
        
    if curr_exp:
        experience.append(curr_exp)

    # 4. Projects
    proj_lines = lines_by_sec['PROJECTS']
    projects = []
    curr_proj = None
    
    for l in proj_lines:
        clean_l = l.strip('•*-· \t')
        if not clean_l:
            continue
        if clean_l.lower().startswith(('technologies:', 'tools:', 'tech stack:')):
            if curr_proj:
                curr_proj['technologies'] = clean_l
        elif l.startswith(('•', '*', '-', '·')):
            if curr_proj:
                curr_proj['bullets'].append(clean_l)
        elif curr_proj and curr_proj['bullets']:
            curr_proj['bullets'][-1] += " " + clean_l
        else:
            if curr_proj:
                projects.append(curr_proj)
            curr_proj = {'title': clean_l, 'technologies': '', 'bullets': []}
            
    if curr_proj:
        projects.append(curr_proj)

    # 5. Education & Certifications
    edu_lines = lines_by_sec['EDUCATION']
    education = []
    certs = []
    global_achievements = []
    
    cert_pattern_words = [
        'certified', 'certif', 'license', 'licensure', 'az-', 'sc-', 'ms-', 'comptia', 
        'security+', 'network+', 'a+', 'ccna', 'cisco', 'aws', 'itil', 'pmp', 'capm',
        'cpa', 'cfa', 'series 7', 'series 63', 'frm', 'csc', 'cams', 'acca', 'cisa',
        'rn', 'bls', 'acls', 'cpr', 'cna', 'nclex', 'six sigma', 'scrum', 'csm',
        'hubspot', 'google analytics', 'salesforce'
    ]
    
    for l in edu_lines:
        clean_l = l.strip('•*-· \t')
        if not clean_l:
            continue
        if any(k in clean_l.lower() for k in cert_pattern_words):
            sub_certs = re.split(r'[•·]', clean_l)
            for sc in sub_certs:
                s_strip = sc.strip()
                if s_strip and len(s_strip) > 3 and not any(x in s_strip.lower() for x in ['concentrations:', 'focus:', 'coursework:']):
                    certs.append(s_strip)
        elif any(k in clean_l.lower() for k in ['concentrations:', 'focus:', 'coursework:', 'honors:', 'minor:']):
            if education:
                education[-1]['details'] = clean_l
        elif any(k in clean_l.lower() for k in ['college', 'university', 'institute', 'school', 'academy', 'bachelor', 'master', 'phd', 'doctorate', 'diploma', 'associate', 'degree', 'b.sc', 'm.sc', 'b.a', 'm.a', 'b.eng', 'b.tech', 'mba', 'b.com', 'm.com']):
            parts = re.split(r'[—–\-\|]', clean_l)
            yr_m = re.search(r'((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4}|\b(19|20)\d{2}\b)', clean_l, re.I)
            yr = yr_m.group(0) if yr_m else ''
            
            if len(parts) >= 2:
                inst = parts[0].strip()
                deg = parts[1].strip()
                deg = re.sub(r'\(.*?\)', '', deg).strip(' |—–-')
                education.append({'institution': inst, 'degree': deg, 'year': yr, 'details': ''})
            else:
                education.append({'institution': clean_l, 'degree': 'Degree / Diploma', 'year': yr, 'details': ''})

    for l in lines_by_sec['CERTIFICATIONS']:
        clean_c = l.strip('•*-· \t')
        if clean_c and len(clean_c) > 2:
            if ',' in clean_c and not any(deg_w in clean_c.lower() for deg_w in ['university', 'college', 'institute', 'school']):
                for sub_c in clean_c.split(','):
                    s_c = sub_c.strip()
                    if s_c and len(s_c) > 2:
                        certs.append(s_c)
            else:
                certs.append(clean_c)

    for l in lines_by_sec['ACHIEVEMENTS']:
        clean_a = l.strip('•*-· \t')
        if clean_a and len(clean_a) > 3:
            global_achievements.append(clean_a)

    # Deduplicate certs
    seen_certs = set()
    deduped_certs = []
    for c in certs:
        if c.lower() not in seen_certs:
            seen_certs.add(c.lower())
            deduped_certs.append(c)

    return experience, projects, education, deduped_certs, global_achievements, extracted_summary, cleaned_skills, custom_headings, additional_sections

def universal_on_premises_parser(raw_text: str) -> Dict[str, Any]:
    lines = [l.strip() for l in raw_text.splitlines() if l.strip()]

    # 1. Contact & Location (Universal International Support)
    email_match = re.search(r"[\w\.-]+@[\w\.-]+\.[a-zA-Z]{2,}", raw_text)
    
    # Support North American & International phone numbers (+1, +44, +91, +61, +49, standard 10-digit, etc.)
    phone_candidates = re.findall(r'(?:(?:\+|00)\d{1,3}[\s.-]?)?(?:\(?\d{2,5}\)?[\s.-]?)?\d{3,4}[\s.-]?\d{3,5}\b', raw_text[:1500])
    phone_val = ""
    for pc in phone_candidates:
        digits = re.sub(r'\D', '', pc)
        if 9 <= len(digits) <= 15:
            phone_val = pc.strip(' -.,|')
            break
    if not phone_val:
        # Fallback to standard North American pattern
        fallback_p = re.search(r"(\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}", raw_text[:1500])
        if fallback_p:
            phone_val = fallback_p.group(0).strip()

    linkedin_match = re.search(r"(https?://)?(www\.)?linkedin\.com/in/[\w\-]+", raw_text, re.IGNORECASE)
    github_match = re.search(r"(https?://)?(www\.)?github\.com/[\w\-]+(/[\w\-]+)?", raw_text, re.IGNORECASE)
    github_val = github_match.group(0) if github_match else ""

    # Universal Name Detection
    name = "Candidate"
    for l in lines[:8]:
        clean_l = l.strip()
        # Clean out common formatting noise
        test_str = re.sub(r'[*_#]', '', clean_l).strip()
        if len(test_str.split()) in [2, 3, 4] and not any(c in test_str for c in ["@", "http", "www", "/", "\\", "|", ":", ";"]):
            if not any(kw in test_str.lower() for kw in ["curriculum", "resume", "cv", "summary", "profile", "contact", "phone", "email", "address", "portfolio"]):
                if not re.search(r'\b\d{4}\b', test_str):
                    name = test_str
                    break

    # Dynamic Location & Country Detection
    detected_country = "Canada" if any(c in raw_text for c in ["Ontario", "Toronto", "Canada", "Vancouver", "Montreal", "Calgary", "Ottawa", "Brampton", "Mississauga", "437", "416", "647", "905"]) else (
        "USA" if any(c in raw_text for c in ["USA", "United States", "New York", "California", "San Francisco", "Austin", "Seattle", "Chicago", "Texas", "Florida"]) else (
            "United Kingdom" if any(c in raw_text for c in ["UK", "United Kingdom", "London", "Manchester", "Birmingham", "+44"]) else (
                "India" if any(c in raw_text for c in ["India", "Bangalore", "Bengaluru", "Mumbai", "Delhi", "Hyderabad", "Pune", "+91"]) else (
                    "Australia" if any(c in raw_text for c in ["Australia", "Sydney", "Melbourne", "Brisbane", "+61"]) else "Remote"
                )
            )
        )
    )

    detected_location = ""
    # Check lines near header for explicit City, State/Province/Country
    for l in lines[1:8]:
        if any(kw in l for kw in [",", "|"]) and not any(c in l for c in ["@", "http", "www"]):
            parts = [p.strip() for p in re.split(r'[,|•]', l) if p.strip()]
            for p in parts:
                if any(w in p.lower() for w in ["ontario", "toronto", "vancouver", "calgary", "montreal", "brampton", "mississauga", "new york", "san francisco", "austin", "seattle", "chicago", "london", "sydney", "remote", "texas", "california", "florida", "bangalore", "mumbai"]):
                    detected_location = p
                    break
            if detected_location:
                break

    if not detected_location:
        loc_match = re.search(r"\b(Ontario|Toronto|Vancouver|Calgary|Montreal|Brampton|Mississauga|New York|San Francisco|Austin|Seattle|Chicago|London|Sydney|Melbourne|Bangalore|Mumbai|Remote)\b", raw_text, re.IGNORECASE)
        if loc_match:
            detected_location = f"{loc_match.group(0)}, {detected_country}" if detected_country not in ["Remote", ""] else loc_match.group(0)
        else:
            detected_location = f"{detected_country}" if detected_country != "Remote" else "Remote"

    explicit_titles = _extract_clean_explicit_titles(raw_text)

    # 2. Comprehensive Multi-Industry Domain Scoring (12 Domains)
    domain_keywords = {
        "Software Engineering": [
            "python", "javascript", "typescript", "react", "fastapi", "django", "backend",
            "frontend", "full stack", "fullstack", "software engineer", "microservices", "docker",
            "kubernetes", "sql", "postgresql", "mongodb", "graphql", "node.js", "java", "c++", "c#"
        ],
        "Data Science & AI Analytics": [
            "machine learning", "deep learning", "nlp", "llm", "pandas", "numpy", "pytorch",
            "tensorflow", "data scientist", "data analyst", "power bi", "tableau", "bigquery",
            "data pipeline", "etl", "scikit-learn", "statistics", "data engineering"
        ],
        "IT Support & Infrastructure": [
            "active directory", "windows server", "group policy", "gpo", "servicenow", "help desk",
            "desktop support", "tier 1", "tier 2", "tier 1-2", "powershell", "dns", "dhcp",
            "azure ad", "endpoint", "incident management", "troubleshooting", "hardware", "office 365",
            "systems administrator", "network administrator"
        ],
        "Banking & Lending Operations": [
            "loan", "loans", "lending", "loan servicing", "loan modification", "commercial loan",
            "business loan", "credit analysis", "risk assessment", "due diligence", "collections",
            "delinquency", "loaniq", "mortgage", "mortgages", "personal banker", "financial advisor",
            "aml", "kyc", "fintrac", "retail banking", "commercial banking", "wealth management",
            "deposits", "cash handling", "lines of credit", "reconciliation", "underwriting",
            "financial services representative", "natwest", "rbc", "td bank", "bmo", "scotia", "cibc"
        ],
        "Accounting & Corporate Finance": [
            "accounting", "accountant", "general ledger", "accounts payable", "accounts receivable",
            "bank reconciliation", "financial reporting", "financial statements", "gaap", "ifrs",
            "audit", "tax", "bookkeeper", "bookkeeping", "payroll", "quickbooks", "invoice processing",
            "cpa", "financial analyst", "variance analysis"
        ],
        "Healthcare & Clinical Operations": [
            "nursing", "nurse", "patient care", "clinical", "hospital", "healthcare", "triage",
            "medication administration", "vital signs", "electronic health records", "ehr", "emr",
            "epic", "cerner", "bls", "acls", "cpr", "rn", "registered nurse", "icu", "emergency department"
        ],
        "Marketing & Digital Growth": [
            "digital marketing", "seo", "sem", "content strategy", "social media", "google analytics",
            "campaign management", "email marketing", "growth marketing", "brand awareness",
            "conversion rate", "hubspot", "copywriting", "lead generation"
        ],
        "Sales & Business Development": [
            "account executive", "business development", "b2b sales", "cold calling", "prospecting",
            "pipeline management", "salesforce", "crm", "closing deals", "client relationship",
            "quota attainment", "lead qualification", "negotiation"
        ],
        "Human Resources & Talent Acquisition": [
            "human resources", "talent acquisition", "recruiter", "recruiting", "onboarding",
            "hr generalist", "employee relations", "hris", "workday", "benefits administration",
            "performance management", "talent development"
        ],
        "Operations & Supply Chain": [
            "supply chain", "logistics", "procurement", "inventory management", "warehouse",
            "operations manager", "process improvement", "lean", "six sigma", "vendor management",
            "project manager", "pmp", "agile", "scrum"
        ],
        "Legal & Regulatory Compliance": [
            "legal counsel", "compliance officer", "regulatory compliance", "contract review",
            "due diligence", "risk management", "litigation", "corporate governance", "paralegal",
            "data privacy", "gdpr", "hipaa"
        ],
        "Engineering (Civil / Mechanical / Electrical)": [
            "mechanical engineering", "electrical engineering", "civil engineering", "autocad",
            "solidworks", "schematics", "pcb", "structural analysis", "manufacturing", "plc"
        ]
    }

    lower_text = raw_text.lower()
    domain_scores = {}
    for dom, kws in domain_keywords.items():
        domain_scores[dom] = sum(1 for kw in kws if re.search(rf"\b{re.escape(kw)}\b", lower_text))

    sorted_domains = sorted(domain_scores.items(), key=lambda x: x[1], reverse=True)
    top_domain, max_score = sorted_domains[0]

    if max_score == 0:
        if explicit_titles:
            t0 = explicit_titles[0].lower()
            if any(w in t0 for w in ["developer", "engineer", "programmer"]):
                top_domain = "Software Engineering"
            elif any(w in t0 for w in ["accountant", "accounting", "finance"]):
                top_domain = "Accounting & Corporate Finance"
            elif any(w in t0 for w in ["nurse", "clinical", "medical"]):
                top_domain = "Healthcare & Clinical Operations"
            elif any(w in t0 for w in ["bank", "lending", "credit"]):
                top_domain = "Banking & Lending Operations"
            else:
                top_domain = "Professional Services"
        else:
            top_domain = "Professional Services"

    # Dynamic Inferred Roles
    domain_roles_map = {
        "Software Engineering": ["Software Engineer", "Full Stack Developer", "Backend Developer", "Frontend Developer", "DevOps Engineer"],
        "Data Science & AI Analytics": ["Data Scientist", "Data Analyst", "Machine Learning Engineer", "BI Analyst", "Data Engineer"],
        "IT Support & Infrastructure": ["IT Support Specialist", "Systems Administrator", "Help Desk Specialist", "Network Administrator", "Cloud Support Engineer"],
        "Banking & Lending Operations": ["Lending Operations Specialist", "Loan Servicing Specialist", "Commercial Lending Analyst", "Credit Analyst", "Personal Banker"],
        "Accounting & Corporate Finance": ["Staff Accountant", "Financial Analyst", "Senior Accountant", "Accounts Payable Specialist", "Bookkeeper"],
        "Healthcare & Clinical Operations": ["Registered Nurse (RN)", "Clinical Coordinator", "Healthcare Specialist", "Nurse Practitioner", "Clinical Nurse"],
        "Marketing & Digital Growth": ["Marketing Specialist", "Digital Marketing Manager", "Growth Marketer", "Content Marketing Strategist", "SEO Specialist"],
        "Sales & Business Development": ["Account Executive", "Business Development Manager", "Sales Representative", "Client Relationship Manager"],
        "Human Resources & Talent Acquisition": ["Human Resources Specialist", "Talent Acquisition Partner", "HR Generalist", "Recruiter", "HR Coordinator"],
        "Operations & Supply Chain": ["Operations Coordinator", "Supply Chain Analyst", "Project Manager", "Logistics Coordinator", "Operations Manager"],
        "Legal & Regulatory Compliance": ["Compliance Specialist", "Legal Counsel", "Risk & Compliance Analyst", "Paralegal", "Corporate Governance Officer"],
        "Engineering (Civil / Mechanical / Electrical)": ["Project Engineer", "Mechanical Engineer", "Electrical Engineer", "Design Engineer", "Systems Engineer"],
        "Professional Services": ["Operations Specialist", "Project Coordinator", "Business Analyst", "Consultant", "Client Services Associate"]
    }

    inferred_roles = domain_roles_map.get(top_domain, ["Professional Consultant", "Operations Specialist", "Business Analyst"])

    final_titles = []
    seen_lower = set()
    for t in explicit_titles + inferred_roles:
        clean_t = t.strip()
        if clean_t.lower() not in seen_lower:
            seen_lower.add(clean_t.lower())
            final_titles.append(clean_t)

    years = 2
    exp_match = re.search(r"(\d+)\+?\s*years?\s+of\s+experience", raw_text, re.IGNORECASE)
    if exp_match:
        years = int(exp_match.group(1))
    elif re.search(r"\b(Senior|Lead|Manager|Director|Principal)\b", raw_text, re.IGNORECASE):
        years = 5

    seniority = f"Senior (~{years} yrs)" if years >= 5 else f"Mid (~{years} yrs)"

    # Extract complete multi-employer work history, education, certifications, awards, projects, summary, skills, custom headings, and additional sections
    full_experience, projects, full_education, certifications, achievements, extracted_summary, cleaned_skills, custom_headings, additional_sections = extract_full_candidate_history(raw_text)

    # Clean default skills if none extracted from resume text
    if not cleaned_skills:
        cleaned_skills = {
            "Core Competencies": [t for t in final_titles[:6]]
        }

    return {
        "personal": {
            "name": name,
            "email": email_match.group(0) if email_match else "",
            "phone": phone_val,
            "location": detected_location,
            "country": detected_country,
            "linkedin": linkedin_match.group(0) if linkedin_match else "",
            "github": github_val,
            "show_email": True,
            "show_phone": True,
            "show_location": True,
            "show_linkedin": True,
            "show_github": bool(github_val)
        },
        "summary": extracted_summary,
        "domain": top_domain,
        "target_job_titles": final_titles[:8],
        "seniority_level": seniority,
        "years_of_experience": years,
        "skills": cleaned_skills,
        "experience": full_experience if full_experience else [
            {
                "company": "Recent Employer",
                "title": explicit_titles[0] if explicit_titles else final_titles[0],
                "dates": "Recent",
                "bullets": ["Executed core operations, maintained compliance standards, and supported business goals."]
            }
        ],
        "projects": projects,
        "education": full_education if full_education else [
            {
                "degree": "Degree / Diploma",
                "institution": "University / College",
                "year": "Completed"
            }
        ],
        "certifications": certifications,
        "achievements": achievements,
        "custom_headings": custom_headings,
        "additional_sections": additional_sections
    }
