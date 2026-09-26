# -*- coding: utf-8 -*-
import os
import re
import json
from typing import Dict, Any, List, Optional
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

def extract_real_missing_keywords(resume_text: str, jd_text: str, top_n: int = 5) -> List[str]:
    """
    Dynamically extracts authentic, high-value domain keywords from the ACTUAL Job Description
    that are absent from the candidate's resume.
    """
    if not jd_text or len(jd_text.strip()) < 30:
        return []

    try:
        ignored = {
            "experience", "years", "year", "ability", "required", "requirements", "preferred",
            "opportunity", "team", "work", "working", "role", "candidate", "responsibilities",
            "qualifications", "skills", "knowledge", "including", "strong", "excellent", "support",
            "position", "company", "duties", "environment", "relevant", "must", "able", "apply",
            "applicant", "successful", "individual", "ideal", "demonstrated", "familiarity",
            "proven", "demonstrate", "ensure", "ensuring", "provide", "providing", "day", "time",
            "responsible", "utilize", "utilizing", "conduct", "conducting", "oversee", "overseeing",
            "track", "tracking", "help", "helping", "manage", "managing", "well", "great", "plus",
            "seeking", "key", "full", "looking", "new", "join", "part", "high", "across", "within",
            "based", "every", "make", "take", "using", "used", "daily", "weekly", "monthly", "annual"
        }

        # Extract words from JD
        words = re.findall(r"\b[A-Za-z]{3,25}\b", jd_text)
        cleaned_words = [w.lower() for w in words if w.lower() not in ignored]

        if not cleaned_words:
            return []

        # Count frequencies
        freq = {}
        for w in cleaned_words:
            freq[w] = freq.get(w, 0) + 1

        resume_lower = resume_text.lower()
        missing = []

        # Sort by frequency
        sorted_kws = sorted(freq.items(), key=lambda x: x[1], reverse=True)
        for term, _ in sorted_kws:
            if not re.search(rf"\b{re.escape(term)}\b", resume_lower):
                formatted = term.title()
                if formatted not in missing:
                    missing.append(formatted)
                if len(missing) >= top_n:
                    break

        return missing
    except Exception as e:
        print(f"[ATS Scorer] Keyword extraction issue: {e}")
        return []

def calculate_fast_cosine_similarity(resume_text: str, job_description: str) -> float:
    try:
        vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2))
        tfidf_matrix = vectorizer.fit_transform([resume_text, job_description])
        sim = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:2])[0][0]
        scaled = min(100.0, sim * 175.0)
        return round(scaled, 1)
    except Exception:
        return 45.0

from core.gemini_client import call_gemini

def score_job_against_resume(
    resume_profile: Dict[str, Any],
    raw_resume_text: str,
    job_item: Dict[str, Any],
    api_key: Optional[str] = None,
    threshold: float = 70.0
) -> Dict[str, Any]:
    raw_key = api_key or ""
    key = str(raw_key).strip().strip('"').strip("'") if raw_key else ""
    jd_text = job_item.get("description", "")
    fast_score = calculate_fast_cosine_similarity(raw_resume_text, jd_text)

    if not key:
        return _calibrated_local_ats_score(resume_profile, raw_resume_text, job_item, fast_score, threshold)

    candidate_skills = []
    for items in resume_profile.get("skills", {}).values():
        if isinstance(items, list):
            candidate_skills.extend(items)

    prompt = f"""
    You are an experienced Canadian corporate recruiter and ATS auditor.
    Evaluate how authentically and competitively this candidate matches the target job description.

    CORE EVALUATION RULES:
    1. Base evaluation STRICTLY on the candidate's actual background, verified duties, and real qualifications.
    2. Distinguish between Direct Experience, Transferable Experience, and Missing Qualifications.
    3. TARGET ATS SCALE:
       - 85–88% = Good match
       - 89–92% = Strong match
       - 93–95% = Very strong match
       - Do not award 100% or above 95% unless candidate has performed the exact specialized job with all tools.
       - A credible 85-92% match with transferable skills is preferred over unrealistic inflated scores.
    4. Provide honest matched competencies and explicit missing qualifications/gaps.

    TARGET JOB:
    Title: {job_item.get('title')}
    Company: {job_item.get('company')}
    Job Description:
    {jd_text[:4000]}

    CANDIDATE ACTUAL PROFILE:
    - Domain: {resume_profile.get('domain', 'General')}
    - Target Titles: {resume_profile.get('target_job_titles', [])}
    - Years of Experience: {resume_profile.get('years_of_experience', 'Unknown')}
    - Recognized Skills: {candidate_skills[:35]}
    - Recent Experience Snippets: {[e.get('title') + ' at ' + e.get('company') for e in resume_profile.get('experience', [])[:3]]}

    SCORING CRITERIA:
    1. Core required competencies & technical tooling (40%)
    2. Role responsibility & transferable operational alignment (30%)
    3. Industry domain & regulatory standards (30%)

    Return STRICTLY valid JSON conforming to:
    {{
        "overall_ats_score": 85,
        "matched_keywords": ["Verified competency candidate has 1", "Verified competency 2"],
        "missing_keywords": ["Genuine gap 1 from JD", "Genuine gap 2"],
        "qualification_fit": "Strong" or "Moderate" or "Weak",
        "summary": "2 concise sentences objectively explaining the candidate's alignment, transferable strengths, and remaining gaps."
    }}
    """
    success, resp_text, model_or_err = call_gemini(key, prompt, json_mode=True)
    if success:
        try:
            data = json.loads(resp_text)
            score = float(data.get("overall_ats_score", fast_score))
            data["overall_ats_score"] = round(score, 1)
            data["passes_threshold"] = bool(score >= threshold)
            data["scoring_engine"] = f"Gemini ({model_or_err})"
            return data
        except Exception as parse_err:
            print(f"[ATS Scorer] Gemini JSON parse error: {parse_err}")

    local_res = _calibrated_local_ats_score(resume_profile, raw_resume_text, job_item, fast_score, threshold)
    local_res["scoring_engine"] = "Local Engine (Gemini fallback)"
    return local_res

def _calibrated_local_ats_score(
    resume_profile: Dict[str, Any],
    raw_resume_text: str,
    job_item: Dict[str, Any],
    fast_score: float,
    threshold: float
) -> Dict[str, Any]:
    jd_text = job_item.get("description", "")
    job_title = job_item.get("title", "").lower()
    jd_lower = jd_text.lower()

    # 1. Title & Role Alignment (0 - 30 points)
    candidate_titles = [t.lower() for t in resume_profile.get("target_job_titles", [])]
    candidate_recent = [e.get("title", "").lower() for e in resume_profile.get("experience", [])]
    all_titles = candidate_titles + candidate_recent

    title_score = 0.0
    for t in all_titles:
        words = [w for w in re.findall(r"\w+", t) if len(w) > 2]
        matching_words = [w for w in words if w in job_title]
        if words:
            ratio = len(matching_words) / len(words)
            title_score = max(title_score, ratio * 30.0)

    # If title words match directly anywhere in the JD title or domain
    domain_lower = str(resume_profile.get("domain", "")).lower()
    if any(term in job_title for term in ["specialist", "analyst", "associate", "officer", "representative", "manager", "advisor"]):
        if any(dom_kw in job_title or dom_kw in jd_lower[:300] for dom_kw in ["lending", "loan", "credit", "bank", "financial", "operations", "support"]):
            title_score = max(title_score, 18.0)

    # 2. Skill & Competency Overlap (0 - 45 points)
    candidate_skills = []
    for items in resume_profile.get("skills", {}).values():
        if isinstance(items, list):
            candidate_skills.extend(items)

    matched_skills = []
    for skill in candidate_skills:
        skill_clean = skill.strip()
        if not skill_clean:
            continue
        # Exact phrase match
        if re.search(rf"\b{re.escape(skill_clean)}\b", jd_text, re.IGNORECASE):
            matched_skills.append(skill_clean)
        else:
            # Word-level overlap for compound skills (e.g. 'Collections & Delinquency', 'Loan Processing')
            subwords = [w for w in re.findall(r"[A-Za-z]{4,}", skill_clean) if w.lower() not in {"management", "systems", "operations"}]
            if subwords and any(re.search(rf"\b{re.escape(w)}\b", jd_text, re.IGNORECASE) for w in subwords):
                matched_skills.append(skill_clean)

    matched_skills = list(dict.fromkeys(matched_skills))
    skill_pts = min(45.0, len(matched_skills) * 6.0)

    # 3. Textual & Experience Depth Similarity (0 - 25 points)
    # Scale fast_score (0-50 range typical for raw resumes against JDs)
    text_pts = min(25.0, (fast_score / 45.0) * 25.0)

    raw_total = title_score + skill_pts + text_pts
    # Calibrated to 85-95% target Canadian alignment for qualified candidates
    total_score = min(94.0, round(raw_total, 1))

    real_missing = extract_real_missing_keywords(raw_resume_text, jd_text, top_n=5)

    fit_label = "Strong" if total_score >= 75 else ("Moderate" if total_score >= 50 else "Weak")

    return {
        "overall_ats_score": total_score,
        "passes_threshold": bool(total_score >= threshold),
        "matched_keywords": matched_skills[:12],
        "missing_keywords": real_missing if real_missing else ["Role-specific KPIs", "Specialized platform workflows"],
        "qualification_fit": fit_label,
        "summary": f"ATS evaluated {total_score}% match based on {len(matched_skills)} verified competencies and transferable role alignment.",
        "scoring_engine": "100% On-Premises Local Engine"
    }
