# -*- coding: utf-8 -*-
import os
import io
import copy
import hashlib
import json
from typing import Optional, Dict, Any, List
import streamlit as st
import pandas as pd
from dotenv import load_dotenv

import importlib
import core.parser
import core.ats_scorer
import core.resume_fixer
import core.compiler
import core.gemini_client
import core.resume_editor
import core.resume_studio

importlib.reload(core.parser)
importlib.reload(core.ats_scorer)
importlib.reload(core.resume_fixer)
importlib.reload(core.compiler)
importlib.reload(core.gemini_client)
importlib.reload(core.resume_editor)
importlib.reload(core.resume_studio)

from core.parser import extract_text_from_pdf, extract_links_from_pdf, parse_resume_profile, test_gemini_api_key
from core.ats_scorer import score_job_against_resume
from core.resume_fixer import generate_minimal_resume_fixes
from core.compiler import compile_tailored_pdf
from core.gemini_client import reset_gemini_session
from core.resume_editor import parse_typst_to_resume_dict
from core.resume_studio import render_resume_studio_tab

load_dotenv()

st.set_page_config(
    page_title="ATS Resume Studio & AI Job Tailoring Suite",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ----------------- Premium Modern Styling -----------------
st.markdown("""
<style>
    .main-header { font-size: 2.15rem; font-weight: 800; color: #0F172A; margin-bottom: 0.15rem; letter-spacing: -0.02em; }
    .sub-header { font-size: 1.0rem; color: #475569; margin-bottom: 1.2rem; }
    .candidate-pill { background: #F8FAFC; border: 1.5px solid #E2E8F0; border-radius: 10px; padding: 12px 18px; margin-bottom: 16px; }
    .ats-badge-high { background-color: #DCFCE7; color: #15803D; font-weight: 700; padding: 6px 14px; border-radius: 6px; font-size: 1.05rem; }
    .ats-badge-mid { background-color: #FEF3C7; color: #B45309; font-weight: 700; padding: 6px 14px; border-radius: 6px; font-size: 1.05rem; }
    .ats-badge-low { background-color: #FEE2E2; color: #B91C1C; font-weight: 700; padding: 6px 14px; border-radius: 6px; font-size: 1.05rem; }
    .job-card { border: 1.5px solid #CBD5E1; border-radius: 10px; padding: 20px; margin-bottom: 18px; background: #FFFFFF; box-shadow: 0 2px 6px rgba(15, 23, 42, 0.04); }
    .stButton>button { border-radius: 6px; font-weight: 600; }
    .keep-box { background-color: #F0FDF4; border-left: 4px solid #16A34A; padding: 12px 14px; margin-bottom: 8px; border-radius: 4px; }
    .remove-box { background-color: #FEF2F2; border-left: 4px solid #DC2626; padding: 12px 14px; margin-bottom: 8px; border-radius: 4px; }
    .roadmap-box { background-color: #EFF6FF; border-left: 4px solid #2563EB; padding: 12px 14px; margin-bottom: 8px; border-radius: 4px; }
</style>
""", unsafe_allow_html=True)

# ----------------- Helper: Purge Resume Cache -----------------
def purge_resume_session_cache():
    """Purges resume session state and cached generated files."""
    preserve = {
        "session_api_key",
        "gemini_api_key",
        "active_engine_name",
        "local_engine",
        "theme"
    }
    for k in list(st.session_state.keys()):
        if k not in preserve:
            del st.session_state[k]

    st.session_state["resume_profile"] = None
    st.session_state["raw_resume_text"] = ""
    st.session_state["uploaded_filename"] = None
    st.session_state["uploaded_file_hash"] = None
    st.session_state["direct_eval"] = None
    st.session_state["direct_curation"] = None

    try:
        out_dir = os.path.join(os.getcwd(), "output_resumes")
        if os.path.exists(out_dir):
            for fname in os.listdir(out_dir):
                fpath = os.path.join(out_dir, fname)
                if os.path.isfile(fpath):
                    try:
                        os.remove(fpath)
                    except Exception:
                        pass
        prev_dir = os.path.join(out_dir, "previews")
        if os.path.exists(prev_dir):
            for fname in os.listdir(prev_dir):
                fpath = os.path.join(prev_dir, fname)
                if os.path.isfile(fpath):
                    try:
                        os.remove(fpath)
                    except Exception:
                        pass
    except Exception as e:
        print(f"[Purge Cache Error] {e}")

# ----------------- Session State Defaults -----------------
if "resume_profile" not in st.session_state:
    st.session_state["resume_profile"] = None
if "raw_resume_text" not in st.session_state:
    st.session_state["raw_resume_text"] = ""

# ----------------- Sidebar Configuration -----------------
# ----------------- Engine & Pre-Configured Settings -----------------
env_key = os.getenv("GEMINI_API_KEY", "").strip()
session_key = st.session_state.get("session_api_key", "").strip()
active_api_key = session_key or env_key

st.sidebar.title("⚙️ Engine Status")

if active_api_key:
    st.sidebar.success("🟢 AI Engine Active (No key required)")
    active_engine_name = "gemini"
    api_key = active_api_key
else:
    st.sidebar.info("🟢 Zero-Cost Local Engine Active")
    active_engine_name = "on_premises"
    api_key = None

with st.sidebar.expander("🔑 Advanced / Custom API Key (Optional)", expanded=False):
    custom_key = st.text_input(
        "Custom Gemini API Key:",
        value=session_key,
        type="password",
        help="Optional. If you want to use your own Google AI key instead of the server default."
    )
    if custom_key != session_key:
        st.session_state["session_api_key"] = custom_key
        reset_gemini_session()
        st.rerun()

st.sidebar.markdown("---")
if st.sidebar.button("🔄 Clear / Reset Resume Cache", use_container_width=True):
    purge_resume_session_cache()
    st.rerun()

# ----------------- Main Header -----------------
st.markdown('<div class="main-header">ATS Resume Formatter & AI Job Tailoring Suite</div>', unsafe_allow_html=True)
st.markdown(
    f'<div class="sub-header">Fixed Recruiter-Approved ATS Formatting | Instant 0-100% Job Description ATS Scoring & Tailoring. Active Engine: <b>{"100% On-Premises ($0 Cost)" if is_on_premises else "Google Gemini Live Cloud"}</b>.</div>',
    unsafe_allow_html=True
)

# ----------------- Candidate Ingestion Section -----------------
profile = st.session_state.get("resume_profile")

if profile is None:
    st.markdown("""
    <div style="background: linear-gradient(135deg, #F8FAFC, #EFF6FF); border: 1.5px solid #CBD5E1; border-radius: 12px; padding: 22px 26px; margin-bottom: 22px;">
        <h3 style="margin: 0; color: #0F172A;">📥 Step 1: Provide Your Resume</h3>
        <p style="margin: 6px 0 0 0; color: #475569; font-size: 0.95rem;">
            Upload your existing PDF resume or paste plain text. The parser will immediately extract your background and open both tools below.
        </p>
    </div>
    """, unsafe_allow_html=True)

    tab_up_pdf, tab_up_paste = st.tabs(["📤 Upload PDF Resume", "📋 Paste Plain Text"])
    
    with tab_up_pdf:
        up_file = st.file_uploader("Upload your resume in PDF format:", type=["pdf"], key="main_resume_pdf_uploader")
        if up_file is not None:
            f_bytes = up_file.getvalue()
            f_hash = hashlib.md5(f_bytes).hexdigest()
            if st.session_state.get("main_uploaded_hash") != f_hash:
                with st.spinner(f"Analyzing resume with {'Google Gemini' if not is_on_premises else 'Local Engine'}..."):
                    raw_text = extract_text_from_pdf(f_bytes)
                    pdf_links = extract_links_from_pdf(f_bytes)
                    if not raw_text.strip():
                        st.error("Could not extract text from this PDF. Please use the 'Paste Plain Text' tab.")
                    else:
                        parsed = parse_resume_profile(raw_text, engine=active_engine_name, api_key=api_key, pdf_links=pdf_links)
                        st.session_state["resume_profile"] = parsed
                        st.session_state["raw_resume_text"] = raw_text
                        st.session_state["uploaded_filename"] = up_file.name
                        st.session_state["main_uploaded_hash"] = f_hash
                        st.success(f"✅ Resume parsed! Candidate: {parsed.get('personal', {}).get('name', 'Candidate')} | Domain: {parsed.get('domain')}")
                        st.rerun()

    with tab_up_paste:
        p_text = st.text_area("Paste plain resume text here:", height=180, placeholder="Paste your resume content, experience, education, and skills...", key="main_resume_paste_area")
        if st.button("Parse Resume Text", type="primary", key="btn_main_parse_text"):
            if len(p_text.strip()) < 40:
                st.error("Please paste substantial resume text (at least 40 characters).")
            else:
                with st.spinner("Analyzing candidate background..."):
                    parsed = parse_resume_profile(p_text, engine=active_engine_name, api_key=api_key)
                    st.session_state["resume_profile"] = parsed
                    st.session_state["raw_resume_text"] = p_text
                    st.session_state["uploaded_filename"] = "pasted_text"
                    st.success(f"✅ Resume parsed! Candidate: {parsed.get('personal', {}).get('name', 'Candidate')} | Domain: {parsed.get('domain')}")
                    st.rerun()

else:
    # Active Candidate Status Pill
    cand_pers = profile.get("personal", {})
    c_name = cand_pers.get("name", "Candidate")
    c_email = cand_pers.get("email", "N/A")
    c_phone = cand_pers.get("phone", "N/A")
    c_loc = cand_pers.get("location", "Canada")
    c_domain = profile.get("domain", "Professional")
    c_seniority = profile.get("seniority_level", "Mid")
    
    col_pill1, col_pill2 = st.columns([3.8, 1.2])
    with col_pill1:
        st.markdown(f"""
        <div class="candidate-pill">
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <div>
                    <span style="font-size: 1.15rem; font-weight: 700; color: #0F172A;">👤 {c_name}</span>
                    <span style="color: #64748B; margin-left: 12px; font-size: 0.95rem;">{c_email} | {c_phone} | {c_loc}</span>
                </div>
                <div>
                    <span style="background: #E0F2FE; color: #0369A1; font-weight: 600; padding: 4px 10px; border-radius: 6px; font-size: 0.85rem;">{c_domain}</span>
                    <span style="background: #F1F5F9; color: #475569; font-weight: 600; padding: 4px 10px; border-radius: 6px; font-size: 0.85rem; margin-left: 6px;">{c_seniority}</span>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)
    with col_pill2:
        with st.expander("🔄 Switch Resume", expanded=False):
            up_new = st.file_uploader("Upload new PDF:", type=["pdf"], key="switch_resume_uploader")
            if up_new is not None:
                new_bytes = up_new.getvalue()
                new_hash = hashlib.md5(new_bytes).hexdigest()
                if st.session_state.get("switch_uploaded_hash") != new_hash:
                    purge_resume_session_cache()
                    raw_text = extract_text_from_pdf(new_bytes)
                    pdf_links = extract_links_from_pdf(new_bytes)
                    parsed = parse_resume_profile(raw_text, engine=active_engine_name, api_key=api_key, pdf_links=pdf_links)
                    st.session_state["resume_profile"] = parsed
                    st.session_state["raw_resume_text"] = raw_text
                    st.session_state["uploaded_filename"] = up_new.name
                    st.session_state["switch_uploaded_hash"] = new_hash
                    st.rerun()
            if st.button("Clear Candidate", key="btn_clear_candidate", use_container_width=True):
                purge_resume_session_cache()
                st.rerun()

    # =========================================================================
    # TWO CORE TOOLS AS TOP-LEVEL TABS
    # =========================================================================
    tab_studio, tab_analyzer = st.tabs([
        "📄 Tool 1: Instant ATS Resume Formatter & Studio",
        "🎯 Tool 2: Targeted Job ATS Analyzer & AI Tailorer"
    ])

    # =========================================================================
    # TOOL 1: INSTANT ATS RESUME FORMATTER & STUDIO
    # =========================================================================
    with tab_studio:
        st.markdown("### 📄 Fixed ATS Standard Resume Studio & Formatter")
        st.caption(
            "Transforms your resume directly into our fixed, recruiter-approved standard ATS layout. "
            "Real-time visual preview, direct content form editor, interconnected Typst code editor with error boundary, custom typography, manual page breaks, and instant PDF download."
        )

        std_pdf_out = os.path.join(os.getcwd(), "output_resumes", "standardized_ats_resume.pdf")
        std_typ_out = std_pdf_out.replace(".pdf", ".typ")

        # Load any existing disk modifications (such as added certs or projects)
        if os.path.exists(std_typ_out):
            try:
                with open(std_typ_out, "r", encoding="utf-8") as f:
                    disk_code = f.read()
                disk_parsed = parse_typst_to_resume_dict(disk_code, baseline=profile)
                if disk_parsed.get("certifications"):
                    profile["certifications"] = disk_parsed["certifications"]
                if disk_parsed.get("projects"):
                    profile["projects"] = disk_parsed["projects"]
            except Exception as e:
                pass

        std_curation = {
            "tailored_summary": profile.get("summary", "") or "",
            "tailored_skills": copy.deepcopy(profile.get("skills", {})),
            "tailored_experience": copy.deepcopy(profile.get("experience", [])),
            "pdf_path": std_pdf_out
        }

        # Ensure initial compilation into the fixed ATS format exists on disk
        if not os.path.exists(std_pdf_out):
            os.makedirs(os.path.dirname(std_pdf_out), exist_ok=True)
            try:
                with st.spinner("Compiling resume into ATS standard format..."):
                    compile_tailored_pdf(
                        personal=profile.get("personal", {}),
                        summary=std_curation["tailored_summary"],
                        skills=std_curation["tailored_skills"],
                        experience=std_curation["tailored_experience"],
                        education=profile.get("education", []),
                        output_pdf_path=std_pdf_out,
                        certifications=profile.get("certifications", []),
                        achievements=profile.get("achievements", []),
                        projects=profile.get("projects", [])
                    )
            except Exception as err:
                st.error(f"Notice compiling initial PDF: {err}")

        render_resume_studio_tab(
            curation=std_curation,
            profile=profile,
            job={
                "id": "std_ats_format",
                "title": "Standard ATS Resume",
                "company": profile.get("personal", {}).get("name", "Candidate")
            },
            api_key=api_key,
            session_prefix="std_format"
        )

    # =========================================================================
    # TOOL 2: TARGETED JOB ATS ANALYZER & AI TAILORER (ATS INCREASER)
    # =========================================================================
    with tab_analyzer:
        st.markdown("### 🎯 Targeted Job Posting ATS Analyzer & AI Tailorer")
        st.caption(
            "Paste ANY job description from LinkedIn, Indeed, company career pages, or emails to get an instant 0-100% ATS evaluation, experience pruning audit, targeted skill selection, and tailored PDF."
        )

        col_j1, col_j2 = st.columns([1, 1])
        with col_j1:
            target_title = st.text_input("Target Job Title:", value="", placeholder="e.g. IT Support Specialist, Systems Administrator, Financial Analyst")
        with col_j2:
            target_company = st.text_input("Target Company / Organization:", value="", placeholder="e.g. Westlake Corporation, TD Bank, City of Toronto")

        target_jd_text = st.text_area(
            "Paste Target Job Description / Requirements / Qualifications:",
            height=200,
            placeholder="Paste the full job posting requirements, responsibilities, and qualifications here..."
        )

        if st.button("🔍 Run Deep ATS Audit (Score / 100%) & Tailor Resume", type="primary", key="btn_run_ats_audit"):
            if len(target_jd_text.strip()) < 40:
                st.error("Please paste a substantial job description (at least 40 characters).")
            else:
                target_job_item = {
                    "id": "direct_target_job",
                    "title": target_title.strip() or "Target Position",
                    "company": target_company.strip() or "Target Employer",
                    "description": target_jd_text.strip(),
                    "location": "Canada",
                    "site": "Direct JD",
                    "date_posted": "Target Posting",
                    "job_url": "#"
                }

                try:
                    with st.spinner("Step 1/3: Evaluating ATS match against job posting with AI..."):
                        ats_eval = score_job_against_resume(
                            resume_profile=profile,
                            raw_resume_text=st.session_state.get("raw_resume_text", ""),
                            job_item=target_job_item,
                            api_key=api_key,
                            threshold=50.0
                        )

                    with st.spinner("Step 2/3: Applying deep AI resume curation (selecting ONLY skills & experiences needed for this JD)..."):
                        curation = generate_minimal_resume_fixes(
                            resume_profile=profile,
                            job_item=target_job_item,
                            ats_evaluation=ats_eval,
                            api_key=api_key
                        )

                    with st.spinner("Step 3/3: Compiling ATS-tailored PDF and generating live preview..."):
                        pdf_out = os.path.join(os.getcwd(), "output_resumes", "tailored_target_job_resume.pdf")
                        compile_tailored_pdf(
                            personal=profile.get("personal", {}),
                            summary=curation.get("tailored_summary", ""),
                            skills=curation.get("tailored_skills", {}),
                            experience=curation.get("tailored_experience", []),
                            education=profile.get("education", []),
                            output_pdf_path=pdf_out,
                            certifications=profile.get("certifications", []),
                            achievements=profile.get("achievements", []),
                            projects=profile.get("projects", [])
                        )
                        curation["pdf_path"] = pdf_out

                    for k in list(st.session_state.keys()):
                        if k.startswith("direct_"):
                            del st.session_state[k]

                    st.session_state["direct_eval"] = ats_eval
                    st.session_state["direct_job"] = target_job_item
                    st.session_state["direct_curation"] = curation
                    st.rerun()

                except Exception as err:
                    st.error(f"⚠️ Notice during processing: {err}. Preserving candidate session.")
                    import traceback
                    traceback.print_exc()

        # Display Direct JD Results
        if st.session_state.get("direct_eval"):
            ats_eval = st.session_state["direct_eval"]
            curation = st.session_state["direct_curation"]
            job = st.session_state["direct_job"]
            score = ats_eval.get("overall_ats_score", 65.0)

            st.markdown("---")
            score_color_class = "ats-badge-high" if score >= 75 else ("ats-badge-mid" if score >= 50 else "ats-badge-low")
            
            st.markdown(f"""
            <div class="job-card">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <h2 style="margin: 0; color: #0F172A;">{job['title']} &mdash; <span style="color: #2563EB;">{job['company']}</span></h2>
                    <span class="{score_color_class}">ATS Match: {score} / 100%</span>
                </div>
                <p style="margin: 8px 0; color: #475569;">
                    Evaluated by: <b>{ats_eval.get('scoring_engine', 'ATS Engine')}</b> | Projected Post-Curation Score: <b>{curation.get('projected_ats_score')}% ({curation.get('score_increase')})</b>
                </p>
                <p style="color: #334155; font-size: 1rem; margin-bottom: 4px;"><i>{ats_eval.get('summary', '')}</i></p>
            </div>
            """, unsafe_allow_html=True)

            col_m1, col_m2 = st.columns(2)
            with col_m1:
                st.markdown("**✅ Verified Matched Competencies:**")
                matched = ats_eval.get("matched_keywords", [])
                if matched:
                    st.success(", ".join(matched))
                else:
                    st.info("Baseline match based on transferable industry experience.")

            with col_m2:
                st.markdown("**❌ Critical Missing Qualifications in JD:**")
                missing = ats_eval.get("missing_keywords", [])
                if missing:
                    st.error(", ".join(missing))
                else:
                    st.success("No major qualification gaps identified!")

            st.markdown("---")
            tab_prune, tab_diff, tab_audit, tab_pdf = st.tabs([
                "📋 Experience Pruning (Keep vs Remove)",
                "🚀 Google XYZ Bullet Refinements & Roadmap",
                "🛡️ Recruiter Test & Defense Audit",
                "📄 Tailored Resume & 1-Click PDF Download"
            ])

            with tab_prune:
                st.markdown("### Experience Relevance Audit")
                st.caption("Optimizes your resume to ensure the ATS and recruiter see ONLY high-impact, relevant experience.")
                
                c_k, c_r = st.columns(2)
                with c_k:
                    st.markdown("#### ✅ Relevant Experiences to KEEP & EMPHASIZE")
                    for k in curation.get("relevant_experiences_to_keep", []):
                        st.markdown(f"""
                        <div class="keep-box">
                            <b>{k.get('bullet')}</b><br>
                            <small><i>Why: {k.get('importance')}</i></small>
                        </div>
                        """, unsafe_allow_html=True)

                with c_r:
                    st.markdown("#### ❌ Experiences to CONDENSE or REMOVE")
                    for r in curation.get("irrelevant_experiences_to_remove_or_condense", []):
                        st.markdown(f"""
                        <div class="remove-box">
                            <b>{r.get('bullet')}</b><br>
                            <small><i>Reason: {r.get('reason')}</i></small>
                        </div>
                        """, unsafe_allow_html=True)

            with tab_diff:
                st.markdown("### ATS Score Elevation Roadmap (Targeting 85–95%)")
                for step in curation.get("ats_elevation_roadmap", []):
                    st.markdown(f'<div class="roadmap-box">📌 {step}</div>', unsafe_allow_html=True)

                st.markdown("### Google XYZ Achievement Enhancements")
                for diff in curation.get("diff_highlights", []):
                    st.markdown(f"**Section:** `{diff.get('location')}`")
                    st.markdown(f"❌ *Original:* {diff.get('original')}")
                    st.markdown(f"✅ *Curated Natural XYZ:* **{diff.get('suggested')}**")
                    st.caption(f"Rationale: {diff.get('reason')}")
                    st.markdown("---")

            with tab_audit:
                st.markdown("### 🇨🇦 Canadian Recruiter Test & Interview Defense Audit")
                st.caption("Ensures credibility and truthfulness. Avoids over-tailoring or claiming unverified specialized systems.")
                
                ca_1, ca_2 = st.columns(2)
                with ca_1:
                    st.markdown("#### 🎯 Strongest Verified Matches:")
                    for sm in curation.get("strongest_matches", ats_eval.get("matched_keywords", [])):
                        st.markdown(f"- **{sm}**")
                    
                    st.markdown("#### 🔍 Missing Qualifications / Honest Gaps:")
                    for mg in curation.get("missing_qualifications", ats_eval.get("missing_keywords", [])):
                        st.markdown(f"- *{mg}*")

                with ca_2:
                    st.markdown("#### ⚠️ Potential Recruiter Inquiries / Red Flags:")
                    red_flags = curation.get("potential_recruiter_red_flags", [])
                    if red_flags:
                        for rf in red_flags:
                            st.warning(rf)
                    else:
                        st.info("No recruiter red flags detected. Resume maintains clean career logic.")

                    st.markdown("#### ✍️ Claims Requiring Your Confirmation:")
                    claims = curation.get("claims_requiring_confirmation", [])
                    if claims:
                        for cl in claims:
                            st.info(f"👉 {cl}")
                    else:
                        st.success("All claims are directly supported by your original resume history.")

            with tab_pdf:
                render_resume_studio_tab(
                    curation=curation,
                    profile=profile,
                    job=job,
                    api_key=api_key,
                    session_prefix="direct"
                )
