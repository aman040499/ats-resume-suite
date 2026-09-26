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
                    _, loc_projs, loc_edu, certs, achs, _, _ = extract_full_candidate_history(raw_text)
                    if not data.get("certifications"):
                        data["certifications"] = certs
                    if not data.get("achievements"):
                        data["achievements"] = achs
                    if not data.get("projects"):
                        data["projects"] = loc_projs
                    if not data.get("education") and loc_edu:
                        data["education"] = loc_edu
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
        'lead', 'supervisor', 'generalist', 'recruiter', 'director', 'investigator'
    }
    blacklist_words = {
        'college', 'university', 'school', 'press', 'microsoft', 'google', 'ibm', 'amazon', 
        'bex', 'toronto', 'ontario', 'canada', 'mississauga', 'brampton', 'summary', 'skills', 
        'education', 'experience', 'interests', 'languages', 'certifications', 'curriculum', 
        'resume', 'phone', 'email', 'linkedin', 'github', 'portfolio', 'incident', 'degree',
        'diploma', 'bachelor', 'master', 'post graduate', 'certificate', 'institute'
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
                        formatted = formatted.replace('It Support', 'IT Support').replace('It Systems', 'IT Systems')
                        if formatted not in found:
                            found.append(formatted)
    return found

def extract_full_candidate_history(raw_text: str):
    """
    Parses full multi-employer career depth, projects, education details, certifications, and awards.
    Preserves exact job titles, dates, companies, concentrations, and bullet accomplishments.
    """
    text = re.sub(r'[\ufffd\u2013\u2014]', '—', raw_text)
    raw_lines = [l.strip() for l in text.splitlines() if l.strip()]
    
    sec_kws = {
        'SUMMARY': ['PROFESSIONAL SUMMARY', 'SUMMARY', 'PROFILE', 'ABOUT ME'],
        'SKILLS': ['TECHNICAL SKILLS', 'SKILLS', 'SUMMARY OF SKILLS', 'CORE COMPETENCIES'],
        'EXPERIENCE': ['PROFESSIONAL EXPERIENCE', 'WORK EXPERIENCE', 'EXPERIENCE', 'EMPLOYMENT HISTORY', 'WORK HISTORY'],
        'PROJECTS': ['PROJECT', 'PROJECTS', 'TECHNICAL PROJECTS', 'KEY PROJECTS', 'ACADEMIC PROJECTS'],
        'EDUCATION': ['EDUCATION & CERTIFICATIONS', 'EDUCATION AND CERTIFICATIONS', 'EDUCATION', 'ACADEMIC BACKGROUND'],
        'CERTIFICATIONS': ['CERTIFICATIONS', 'LICENSES & CERTIFICATIONS', 'PROFESSIONAL DEVELOPMENT']
    }
    
    lines_by_sec = {
        'HEADER': [], 'SUMMARY': [], 'SKILLS': [], 'EXPERIENCE': [], 
        'PROJECTS': [], 'EDUCATION': [], 'CERTIFICATIONS': []
    }
    
    current_sec = 'HEADER'
    for l in raw_lines:
        clean_upper = l.upper().strip(': ')
        matched_sec = None
        for sec_name, keywords in sec_kws.items():
            if any(clean_upper == kw or clean_upper.startswith(kw + ' ') or clean_upper.startswith(kw + ':') for kw in keywords):
                matched_sec = sec_name
                break
        if matched_sec:
            current_sec = matched_sec
        else:
            lines_by_sec[current_sec].append(l)

    # 1. Summary
    extracted_summary = " ".join(lines_by_sec['SUMMARY']).strip()

    # 2. Skills
    extracted_skills = {}
    current_cat = 'Core Competencies'
    merged_skill_lines = []
    for l in lines_by_sec['SKILLS']:
        clean = l.strip('•*-· \t')
        is_new = l.startswith(('•', '*', '-', '·')) or (':' in clean and len(clean.split(':', 1)[0].split()) <= 4)
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
            if len(cat.split()) <= 6 and len(cat) <= 50:
                current_cat = cat
                items = [i.strip() for i in re.split(r'[,|•·]', items_str) if i.strip()]
                extracted_skills[current_cat] = items
                continue
        items = [i.strip() for i in re.split(r'[,|•·]', clean) if i.strip()]
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
                    
                    role_words = {'specialist', 'analyst', 'clerk', 'representative', 'officer', 'technician', 'engineer', 'lead', 'manager', 'associate', 'administrator', 'banker', 'advisor', 'consultant', 'developer'}
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
                    # Check if Key Achievements is accidentally glued inline into this line
                    if re.search(r'(?:Key\s+Achievements?|Key\s+Accomplishments?|Achievements?):?', clean_b, re.IGNORECASE):
                        parts = re.split(r'(?:Key\s+Achievements?|Key\s+Accomplishments?|Achievements?):?', clean_b, flags=re.IGNORECASE)
                        bullet_part = parts[0].strip('•*-· \t')
                        ach_part = parts[1].strip('•*-· \t') if len(parts) > 1 else ''
                        if bullet_part:
                            curr_exp['bullets'].append(bullet_part)
                        if ach_part:
                            curr_exp['achievements'].append(ach_part)
                            in_achievements = True
                    elif any(k in clean_b for k in ['Award', 'Top-rated Performer', 'Employee of the Month', 'Control Champ']):
                        curr_exp['achievements'].append(clean_b)
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
        if clean_l.lower().startswith('technologies:'):
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
    
    skill_kws = ['microsoft & automation', 'networking & remote', 'it support & itsm', 'windows & endpoint', 'identity & infrastructure']
    
    for l in edu_lines:
        clean_l = l.strip('•*-· \t')
        if not clean_l or any(sk in clean_l.lower() for sk in skill_kws):
            continue
        if any(k in clean_l.lower() for k in ['certified', 'certif', 'license', 'az-', 'sc-', 'ms-', 'comptia', 'security+', 'network+', 'a+', 'ccna', 'cisco', 'aws', 'itil', 'pmp']):
            sub_certs = re.split(r'[•·]', clean_l)
            for sc in sub_certs:
                s_strip = sc.strip()
                if s_strip and any(w in s_strip.lower() for w in ['certified', 'certif', 'fundamentals', 'administrator', 'az-', 'sc-', 'comptia', 'security+', 'network+', 'a+', 'ccna', 'itil', 'aws', 'in progress']):
                    if not any(x in s_strip.lower() for x in [', powershell', ', microsoft excel', 'concentrations:']):
                        certs.append(s_strip)
        elif any(k in clean_l.lower() for k in ['concentrations:', 'focus:', 'coursework:']):
            if education:
                education[-1]['details'] = clean_l
        elif any(k in clean_l.lower() for k in ['college', 'university', 'institute', 'school', 'academy']):
            parts = re.split(r'[—–\-\|]', clean_l)
            yr_m = re.search(r'((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4}|\b(19|20)\d{2}\b)', clean_l, re.I)
            yr = yr_m.group(0) if yr_m else ''
            
            if len(parts) >= 2:
                inst = parts[0].strip()
                deg = parts[1].strip()
                deg = re.sub(r'\(.*?\)', '', deg).strip(' |—–-')
                education.append({'institution': inst, 'degree': deg, 'year': yr, 'details': ''})
            else:
                education.append({'institution': clean_l, 'degree': 'Diploma / Degree', 'year': yr, 'details': ''})

    for l in lines_by_sec['CERTIFICATIONS']:
        clean_c = l.strip('•*-· \t')
        if clean_c and len(clean_c) > 5:
            certs.append(clean_c)

    # Deduplicate certs
    seen_certs = set()
    deduped_certs = []
    for c in certs:
        if c.lower() not in seen_certs:
            seen_certs.add(c.lower())
            deduped_certs.append(c)

    return experience, projects, education, deduped_certs, global_achievements, extracted_summary, cleaned_skills

def universal_on_premises_parser(raw_text: str) -> Dict[str, Any]:
    lines = [l.strip() for l in raw_text.splitlines() if l.strip()]

    # 1. Contact & Location
    email_match = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", raw_text)
    phone_match = re.search(r"(\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}", raw_text)
    linkedin_match = re.search(r"(https?://)?(www\.)?linkedin\.com/in/[\w\-]+", raw_text, re.IGNORECASE)

    name = "Candidate"
    for l in lines[:6]:
        clean_l = l.strip()
        if len(clean_l.split()) in [2, 3, 4] and not any(c in clean_l for c in ["@", "http", "www", "/", "\\", "|", ":", ";"]):
            if not any(kw in clean_l.lower() for kw in ["curriculum", "resume", "cv", "summary", "profile", "contact", "phone", "email"]):
                name = clean_l
                break

    detected_country = "Canada" if any(c in raw_text for c in ["Ontario", "Toronto", "Canada", "Vancouver", "Montreal", "Calgary", "Ottawa", "Brampton", "Mississauga", "437", "416", "647", "905"]) else "USA"
    detected_location = f"Ontario, {detected_country}" if detected_country == "Canada" else "Remote"
    loc_match = re.search(r"\b(Ontario|Toronto|Vancouver|Calgary|Montreal|Brampton|Mississauga|New York|San Francisco|Austin|Seattle|Chicago|London)\b", raw_text, re.IGNORECASE)
    if loc_match:
        detected_location = f"{loc_match.group(0)}, {detected_country}"

    explicit_titles = _extract_clean_explicit_titles(raw_text)

    # 2. Comprehensive Domain Scoring
    domain_keywords = {
        "Banking & Lending Operations": [
            "loan", "loans", "lending", "loan servicing", "loan modification", "commercial loan",
            "business loan", "credit analysis", "risk assessment", "due diligence", "collections",
            "delinquency", "loaniq", "mortgage", "mortgages", "personal banker", "financial advisor",
            "aml", "kyc", "fintrac", "retail banking", "commercial banking", "wealth management",
            "deposits", "cash handling", "lines of credit", "reconciliation", "underwriting",
            "financial services representative", "natwest", "rbc", "td bank", "bmo", "scotia", "cibc"
        ],
        "Accounting & Finance": [
            "accounting", "accountant", "general ledger", "accounts payable", "accounts receivable",
            "bank reconciliation", "financial reporting", "financial statements", "gaap", "ifrs",
            "audit", "tax", "bookkeeper", "bookkeeping", "payroll", "quickbooks", "invoice processing"
        ],
        "IT Support & Infrastructure": [
            "active directory", "windows server", "group policy", "gpo", "servicenow", "help desk",
            "desktop support", "tier 1", "tier 2", "tier 1-2", "powershell", "dns", "dhcp",
            "azure ad", "endpoint", "incident management", "troubleshooting", "hardware", "office 365"
        ],
        "Software Engineering": [
            "python", "javascript", "typescript", "react", "fastapi", "django", "backend",
            "frontend", "full stack", "fullstack", "software engineer", "microservices", "docker", "kubernetes", "sql"
        ],
        "Human Resources": [
            "human resources", "talent acquisition", "recruiter", "recruiting", "onboarding",
            "hr generalist", "employee relations", "hris", "workday"
        ],
        "Operations & Project Management": [
            "project manager", "pmp", "scrum master", "agile", "operations manager",
            "supply chain", "logistics", "procurement", "process improvement"
        ]
    }

    lower_text = raw_text.lower()
    domain_scores = {}
    for dom, kws in domain_keywords.items():
        domain_scores[dom] = sum(1 for kw in kws if re.search(rf"\b{re.escape(kw)}\b", lower_text))

    sorted_domains = sorted(domain_scores.items(), key=lambda x: x[1], reverse=True)
    top_domain, max_score = sorted_domains[0]

    if max_score == 0:
        top_domain = "Banking & Lending Operations" if any(b in lower_text for b in ["bank", "td", "rbc", "bmo", "cibc", "loan", "credit"]) else "Professional Services"

    skills_by_domain = {
        "Banking & Lending Operations": {
            "Lending, Credit & Loan Operations": [
                "Commercial Loans", "Business Loans", "Loan Servicing", "Loan Modifications", "Loan Processing",
                "Credit Analysis", "Risk Assessment", "Due Diligence", "Collections & Delinquency",
                "Payment Resolution", "Loan Underwriting", "Mortgages", "Lines of Credit", "Personal Lending",
                "Operational Controls", "Portfolio Reporting"
            ],
            "Banking & Financial Advisory": [
                "Personal Banker", "Financial Advisory", "Retail Banking", "Commercial Banking",
                "Deposits", "Cash Handling", "Wire Transfers", "Account Openings", "Wealth Management",
                "Mutual Funds", "RRSP", "TFSA", "GIC", "Customer Relationship Management"
            ],
            "Compliance & Risk Regulations": [
                "AML", "Anti-Money Laundering", "KYC", "Know Your Customer", "FINTRAC",
                "Fraud Prevention", "Regulatory Compliance", "Risk Management", "Auditing", "Quality Controls"
            ],
            "Banking Tools & Accounting Systems": [
                "LoanIQ", "Microsoft Excel", "Power BI", "Salesforce", "Microsoft Dynamics 365",
                "MicroStrategy", "CRM Systems", "Accounts Payable", "General Ledger", "Bank Reconciliations"
            ]
        },
        "Accounting & Finance": {
            "Financial & Cost Accounting": [
                "General Ledger", "Accounts Payable", "Accounts Receivable", "Bank Reconciliations",
                "Financial Statements", "Journal Entries", "Financial Reporting", "Budgeting",
                "Variance Analysis", "Tax Preparation", "Payroll Processing", "Invoice Processing"
            ],
            "Accounting Standards & Tools": [
                "GAAP", "IFRS", "Internal Controls", "QuickBooks", "SAP", "Microsoft Excel", "Power BI"
            ]
        },
        "IT Support & Infrastructure": {
            "IT Support & ITSM": [
                "Tier 1 Support", "Tier 2 Support", "Tier 1-2 Support", "Incident Management",
                "Service Requests", "ServiceNow", "Ticket Prioritization", "Root Cause Analysis",
                "Escalation Management", "Technical Documentation", "ITSM", "Help Desk", "Desktop Support"
            ],
            "Windows, Directory & Endpoint": [
                "Windows 10/11", "Windows Server 2022", "Windows Server", "Active Directory",
                "Group Policy", "GPO", "DNS", "DHCP", "PowerShell", "Azure AD", "Hardware Troubleshooting",
                "Endpoint Administration", "Remote Management"
            ]
        },
        "Software Engineering": {
            "Languages & Frameworks": [
                "Python", "JavaScript", "TypeScript", "React", "Node.js", "FastAPI", "Django", "SQL", "PostgreSQL"
            ],
            "DevOps & Architecture": [
                "Docker", "Kubernetes", "AWS", "CI/CD", "Git", "Microservices", "REST APIs"
            ]
        }
    }

    active_bank = skills_by_domain.get(top_domain, skills_by_domain["Banking & Lending Operations"])
    detected_skills = {}
    for cat, sk_list in active_bank.items():
        matched = []
        for s in sk_list:
            if re.search(rf"(?<!\w){re.escape(s)}(?!\w)", raw_text, re.IGNORECASE):
                matched.append(s)
        if matched:
            detected_skills[cat] = list(dict.fromkeys(matched))

    if top_domain == "Banking & Lending Operations":
        inferred_roles = [
            "Lending Operations Specialist",
            "Loan Servicing Specialist",
            "Commercial Lending Analyst",
            "Credit Analyst",
            "Personal Banker",
            "Financial Services Representative",
            "Financial Advisor",
            "Banking Operations Specialist",
            "Accounting Clerk"
        ]
    elif top_domain == "Accounting & Finance":
        inferred_roles = [
            "Staff Accountant",
            "Financial Analyst",
            "Accounts Payable / Receivable Specialist",
            "Senior Accountant",
            "Bookkeeper",
            "Accounting Clerk"
        ]
    elif top_domain == "IT Support & Infrastructure":
        inferred_roles = [
            "IT Support Specialist",
            "Help Desk Specialist",
            "IT Systems Administrator",
            "Junior System Administrator",
            "Junior IT Support / Sys Admin",
            "Active Directory Administrator (AD Admin)",
            "Desktop Support Specialist"
        ]
    elif top_domain == "Human Resources":
        inferred_roles = [
            "Human Resources Specialist",
            "Recruiter / Talent Acquisition",
            "HR Generalist",
            "HR Coordinator"
        ]
    elif top_domain == "Operations & Project Management":
        inferred_roles = [
            "Project Manager",
            "Operations Coordinator",
            "Operations Manager",
            "Supply Chain Analyst"
        ]
    elif top_domain == "Software Engineering":
        inferred_roles = ["Software Engineer", "Full Stack Developer", "Backend Developer"]
    else:
        inferred_roles = ["Banking Specialist", "Financial Services Representative", "Operations Analyst"]

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
    elif re.search(r"\b(Senior|Lead|Manager)\b", raw_text, re.IGNORECASE):
        years = 5

    seniority = f"Senior (~{years} yrs)" if years >= 5 else f"Mid (~{years} yrs)"

    # Extract complete multi-employer work history, education, certifications, awards, projects, summary, and skills
    full_experience, projects, full_education, certifications, achievements, extracted_summary, cleaned_skills = extract_full_candidate_history(raw_text)

    github_match = re.search(r"(https?://)?(www\.)?github\.com/[\w\-]+(/[\w\-]+)?", raw_text, re.IGNORECASE)
    github_val = github_match.group(0) if github_match else ""

    final_skills = cleaned_skills if cleaned_skills else detected_skills

    return {
        "personal": {
            "name": name,
            "email": email_match.group(0) if email_match else "",
            "phone": phone_match.group(0) if phone_match else "",
            "location": detected_location,
            "country": detected_country,
            "linkedin": linkedin_match.group(0) if linkedin_match else "",
            "github": github_val
        },
        "summary": extracted_summary,
        "domain": top_domain,
        "target_job_titles": final_titles[:8],
        "seniority_level": seniority,
        "years_of_experience": years,
        "skills": final_skills,
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
        "achievements": achievements
    }
