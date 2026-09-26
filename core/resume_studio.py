# -*- coding: utf-8 -*-
import os
import re
import copy
import hashlib
from typing import Dict, Any, Optional
import streamlit as st
from core.compiler import generate_typst_source, format_category_title, sanitize_skills_dict
from core.resume_editor import (
    apply_instruction_to_resume,
    recompile_resume_data,
    recompile_raw_typst,
    render_pdf_preview_images,
    parse_typst_to_resume_dict
)

def _clear_studio_widget_keys(prefix: str):
    """
    Clears all cached input widget values for Tab 2 for this editor session so
    Streamlit re-binds cleanly to the updated active_resume data without wiping Tab 3.
    """
    preserve = {f"{prefix}_active_resume", f"{prefix}_initial_resume", f"{prefix}_editor_feedback", f"{prefix}_active_sig"}
    for k in list(st.session_state.keys()):
        if k.startswith(f"{prefix}_") and k not in preserve and not k.startswith(f"{prefix}_raw_typst_area_"):
            st.session_state.pop(k, None)

def _sync_typst_after_edit(active_resume: Dict[str, Any], session_prefix: str) -> str:
    """
    Regenerates raw Typst source code from structured active_resume and syncs
    the Tab 3 textarea widget key in session state so Tab 2 and Tab 3 never drift apart.
    """
    new_typst = generate_typst_source(
        personal=active_resume.get("personal", {}),
        summary=active_resume.get("summary", ""),
        skills=active_resume.get("skills", {}),
        experience=active_resume.get("experience", []),
        education=active_resume.get("education", []),
        certifications=active_resume.get("certifications", []),
        achievements=active_resume.get("achievements", []),
        projects=active_resume.get("projects", []),
        section_spacing=active_resume.get("section_spacing", "0.35em"),
        font_size=active_resume.get("font_size", "9.1pt"),
        top_margin=active_resume.get("top_margin", "1.1cm"),
        bottom_margin=active_resume.get("bottom_margin", "1.1cm"),
        separate_education_and_certs=active_resume.get("separate_education_and_certs", True),
        pagebreak_before_experience=active_resume.get("pagebreak_before_experience", False),
        pagebreak_before_projects=active_resume.get("pagebreak_before_projects", False),
        pagebreak_before_education=active_resume.get("pagebreak_before_education", False),
        pagebreak_before_certs=active_resume.get("pagebreak_before_certs", False),
        pagebreak_before_achievements=active_resume.get("pagebreak_before_achievements", False),
        custom_headings=active_resume.get("custom_headings"),
        additional_sections=active_resume.get("additional_sections")
    )
    active_resume["raw_typst_code"] = new_typst
    new_ver = active_resume.get("typst_version", 0) + 1
    active_resume["typst_version"] = new_ver
    st.session_state[f"{session_prefix}_raw_typst_area_{new_ver}"] = new_typst
    return new_typst

def render_resume_studio_tab(
    curation: Dict[str, Any],
    profile: Dict[str, Any],
    job: Dict[str, Any],
    api_key: Optional[str] = None,
    session_prefix: str = "direct"
):
    """
    Renders the complete interactive Resume Studio:
    1. Live Visual Preview & 1-Click PDF Download
    2. Direct In-Resume Editor: Every single letter on the resume is editable.
       - Personal details (Name, email, phone, location, LinkedIn, GitHub)
       - Executive Summary
       - Technical Skills (names, categories, add/remove)
       - Professional Experience (title, company, dates, bullets, Key Achievements with remove option)
       - Projects (title, tech, bullets)
       - Education & Certifications
       - Spacing & Margins (leave space anywhere)
    3. Dedicated LLM Instructions Box at the end of the editor.
    4. Raw Typst Source Code Editor.
    """
    cand_name = str(profile.get("personal", {}).get("name", "")).strip().lower()
    cand_email = str(profile.get("personal", {}).get("email", "")).strip().lower()
    job_ref = str(job.get("id", job.get("company", "job"))).strip().lower()
    cur_summary = str(curation.get("tailored_summary", ""))[:60].strip()
    cur_pdf = str(curation.get("pdf_path", "")).strip()

    # Generate unique signature for this exact candidate & curation combination
    sig_raw = f"{cand_name}|{cand_email}|{job_ref}|{cur_summary}|{cur_pdf}"
    curation_sig = hashlib.md5(sig_raw.encode("utf-8")).hexdigest()[:12]

    state_key = f"{session_prefix}_active_resume"
    init_key = f"{session_prefix}_initial_resume"
    feedback_key = f"{session_prefix}_editor_feedback"
    sig_key = f"{session_prefix}_active_sig"

    # Strict Candidate Isolation: Check if existing session state belongs to this exact candidate
    stored_sig = st.session_state.get(sig_key)
    existing_resume = st.session_state.get(state_key, {})
    existing_name = str(existing_resume.get("personal", {}).get("name", "")).strip().lower()

    mismatch = False
    if state_key not in st.session_state:
        mismatch = True
    elif stored_sig != curation_sig:
        mismatch = True
    elif cand_name and existing_name and existing_name != cand_name:
        mismatch = True

    if mismatch:
        # Candidate or curation has changed!
        # Completely wipe all widget keys and session state for this prefix
        for k in list(st.session_state.keys()):
            if k.startswith(f"{session_prefix}_"):
                del st.session_state[k]

        st.session_state[sig_key] = curation_sig

    # 1. Initialize session resume state if not present (or freshly wiped)
    if state_key not in st.session_state:
        pdf_path = curation.get("pdf_path") or os.path.join(os.getcwd(), "output_resumes", f"{session_prefix}_tailored_resume.pdf")
        
        # Clean any stray "Key Achievements:" from initial bullets
        raw_exp = copy.deepcopy(curation.get("tailored_experience", profile.get("experience", [])))
        for r in raw_exp:
            cleaned_b = []
            for b in r.get("bullets", []):
                cb = re.sub(r"(?:[.:\s]+|^)Key Achievements:?\s*$", "", str(b), flags=re.IGNORECASE).strip()
                cb = re.sub(r"^Key Achievements:?\s*", "", cb, flags=re.IGNORECASE).strip()
                if cb:
                    cleaned_b.append(cb)
            r["bullets"] = cleaned_b

        resume_data = {
            "personal": copy.deepcopy(profile.get("personal", {})),
            "summary": curation.get("tailored_summary", ""),
            "skills": copy.deepcopy(curation.get("tailored_skills", profile.get("skills", {}))),
            "experience": raw_exp,
            "projects": copy.deepcopy(profile.get("projects", [])),
            "education": copy.deepcopy(profile.get("education", [])),
            "certifications": copy.deepcopy(profile.get("certifications", [])),
            "achievements": copy.deepcopy(profile.get("achievements", [])),
            "custom_headings": copy.deepcopy(profile.get("custom_headings", {})),
            "additional_sections": copy.deepcopy(profile.get("additional_sections", [])),
            "section_spacing": "0.35em",
            "font_size": "9.1pt",
            "top_margin": "1.1cm",
            "bottom_margin": "1.1cm",
            "pdf_path": pdf_path,
            "preview_images": []
        }

        # If an existing typ file is on disk with user edits (e.g. 5 certs, multi-projects), load it
        typ_path = pdf_path.replace(".pdf", ".typ")
        if os.path.exists(typ_path):
            try:
                with open(typ_path, "r", encoding="utf-8") as f:
                    disk_code = f.read()
                disk_parsed = parse_typst_to_resume_dict(disk_code, baseline=resume_data)
                for field in ["personal", "summary", "skills", "experience", "projects", "education", "certifications", "achievements", "custom_headings", "additional_sections"]:
                    if disk_parsed.get(field):
                        resume_data[field] = disk_parsed[field]
                if "separate_education_and_certs" in disk_parsed:
                    resume_data["separate_education_and_certs"] = disk_parsed["separate_education_and_certs"]
            except Exception as e:
                print(f"[Studio Init] Notice loading disk typst: {e}")

        # Compile freshly using the unified, gap-free compiler
        pdf_path, imgs = recompile_resume_data(resume_data, pdf_path)
        resume_data["preview_images"] = imgs
        _sync_typst_after_edit(resume_data, session_prefix)

        st.session_state[state_key] = resume_data
        st.session_state[init_key] = copy.deepcopy(resume_data)

    active_resume = st.session_state[state_key]

    # Ensure preview images exist and raw typst code is synced
    if not active_resume.get("raw_typst_code"):
        _sync_typst_after_edit(active_resume, session_prefix)

    if not active_resume.get("preview_images") or not os.path.exists(active_resume["preview_images"][0] if active_resume.get("preview_images") else ""):
        _, imgs = recompile_resume_data(active_resume, active_resume["pdf_path"])
        active_resume["preview_images"] = imgs

    # Display feedback message if any
    if feedback_key in st.session_state:
        msg_type, msg_text = st.session_state[feedback_key]
        if msg_type == "success":
            st.success(msg_text)
        elif msg_type == "info":
            st.info(msg_text)
        elif msg_type == "error":
            st.error(msg_text)
        del st.session_state[feedback_key]

    # Studio Navigation Tabs
    tab_view, tab_edit, tab_raw = st.tabs([
        "👁️ Live Visual Preview & Download",
        "✏️ Direct In-Resume Editor (Every Letter Editable)",
        "📄 Raw Typst Source Code Editor"
    ])

    # =========================================================================
    # TAB 1: LIVE VISUAL PREVIEW & 1-CLICK PDF DOWNLOAD
    # =========================================================================
    cand_name_for_dl = active_resume.get("personal", {}).get("name", "Candidate")
    safe_cand_name = re.sub(r'[^a-zA-Z0-9_\- ]', '', str(cand_name_for_dl)).strip().replace(' ', '_')
    dl_pdf_filename = f"{safe_cand_name or 'Candidate'}_Resume.pdf"

    with tab_view:
        col_dl1, col_rec1 = st.columns([3.5, 1.2])
        with col_dl1:
            if os.path.exists(active_resume.get("pdf_path", "")):
                with open(active_resume["pdf_path"], "rb") as f:
                    st.download_button(
                        label="📥 Download ATS-Friendly Resume PDF",
                        data=f,
                        file_name=dl_pdf_filename,
                        mime="application/pdf",
                        type="primary",
                        use_container_width=True
                    )
        with col_rec1:
            if st.button("🔄 Force Recompile Preview", key=f"{session_prefix}_recomp_top", use_container_width=True):
                _, imgs = recompile_resume_data(active_resume, active_resume["pdf_path"])
                active_resume["preview_images"] = imgs
                st.session_state[state_key] = active_resume
                st.session_state[feedback_key] = ("success", "🔄 Recompiled resume and generated fresh preview.")
                st.rerun()

        # Top AI Quick Prompt Box
        st.markdown("""
        <div style="background-color: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 8px; padding: 12px 16px; margin: 12px 0;">
            <span style="font-weight: 600; color: #1E293B;">⚡ Quick AI Instruction:</span>
            <span style="color: #64748B; font-size: 0.9rem;">(e.g. <i>"Remove Key Achievements"</i>, <i>"Add 'Hyper-V' in skills"</i>, <i>"Leave more space before projects"</i>)</span>
        </div>
        """, unsafe_allow_html=True)

        with st.form(key=f"{session_prefix}_ai_top_form", clear_on_submit=True):
            cin, csub = st.columns([4.2, 1.2])
            with cin:
                top_inst = st.text_input("Quick AI Instruction", placeholder="Type instruction (e.g. Put link behind LinkedIn, Hide GitHub, Remove Key Achievements)...", label_visibility="collapsed")
            with csub:
                submit_top = st.form_submit_button("⚡ Apply Change", type="primary", use_container_width=True)

            if submit_top and top_inst.strip():
                try:
                    with st.spinner("Applying AI instruction and updating resume..."):
                        updated, explanation = apply_instruction_to_resume(active_resume, top_inst.strip(), api_key=api_key)
                        pdf_path, imgs = recompile_resume_data(updated, updated["pdf_path"])
                        updated["preview_images"] = imgs
                        _sync_typst_after_edit(updated, session_prefix)
                        st.session_state[state_key] = updated
                        st.session_state[feedback_key] = ("success", f"✅ {explanation}")
                        _clear_studio_widget_keys(session_prefix)
                        st.rerun()
                except Exception as err:
                    st.error(f"⚠️ Notice: Unable to apply that change ({err}). Your resume is preserved safely.")

        # Quick Suggestion Chips
        c_q1, c_q2, c_q3, c_q4, c_q5 = st.columns(5)
        if c_q1.button("🗑️ Remove Achievements", key=f"{session_prefix}_q_rem_ach", use_container_width=True):
            try:
                updated, explanation = apply_instruction_to_resume(active_resume, "Remove Key Achievements and points underneath it", api_key=api_key)
                pdf_path, imgs = recompile_resume_data(updated, updated["pdf_path"])
                updated["preview_images"] = imgs
                _sync_typst_after_edit(updated, session_prefix)
                st.session_state[state_key] = updated
                st.session_state[feedback_key] = ("success", f"✅ {explanation}")
                _clear_studio_widget_keys(session_prefix)
                st.rerun()
            except Exception as err:
                st.error(f"⚠️ Error: {err}")

        if c_q2.button("🔗 Link Behind 'LinkedIn'", key=f"{session_prefix}_q_link_li", use_container_width=True):
            try:
                updated, explanation = apply_instruction_to_resume(active_resume, "put link behind linkedin text", api_key=api_key)
                pdf_path, imgs = recompile_resume_data(updated, updated["pdf_path"])
                updated["preview_images"] = imgs
                _sync_typst_after_edit(updated, session_prefix)
                st.session_state[state_key] = updated
                st.session_state[feedback_key] = ("success", f"✅ {explanation}")
                _clear_studio_widget_keys(session_prefix)
                st.rerun()
            except Exception as err:
                st.error(f"⚠️ Error: {err}")

        if c_q3.button("🚫 Hide GitHub Link", key=f"{session_prefix}_q_hide_gh", use_container_width=True):
            try:
                updated, explanation = apply_instruction_to_resume(active_resume, "dont show github", api_key=api_key)
                pdf_path, imgs = recompile_resume_data(updated, updated["pdf_path"])
                updated["preview_images"] = imgs
                _sync_typst_after_edit(updated, session_prefix)
                st.session_state[state_key] = updated
                st.session_state[feedback_key] = ("success", f"✅ {explanation}")
                _clear_studio_widget_keys(session_prefix)
                st.rerun()
            except Exception as err:
                st.error(f"⚠️ Error: {err}")

        if c_q4.button("➕ Add 'Hyper-V'", key=f"{session_prefix}_q_h_v", use_container_width=True):
            try:
                updated, explanation = apply_instruction_to_resume(active_resume, "Add 'Hyper-V' in skills", api_key=api_key)
                pdf_path, imgs = recompile_resume_data(updated, updated["pdf_path"])
                updated["preview_images"] = imgs
                _sync_typst_after_edit(updated, session_prefix)
                st.session_state[state_key] = updated
                st.session_state[feedback_key] = ("success", f"✅ {explanation}")
                _clear_studio_widget_keys(session_prefix)
                st.rerun()
            except Exception as err:
                st.error(f"⚠️ Error: {err}")

        if c_q5.button("↺ Reset Draft", key=f"{session_prefix}_q_init_rst", use_container_width=True):
            try:
                init_data = copy.deepcopy(st.session_state[init_key])
                pdf_path, imgs = recompile_resume_data(init_data, init_data["pdf_path"])
                init_data["preview_images"] = imgs
                _sync_typst_after_edit(init_data, session_prefix)
                st.session_state[state_key] = init_data
                st.session_state[feedback_key] = ("info", "↺ Reset resume back to the initial tailored draft.")
                _clear_studio_widget_keys(session_prefix)
                st.rerun()
            except Exception as err:
                st.error(f"⚠️ Error: {err}")

        # Render High-Res Images
        imgs = active_resume.get("preview_images", [])
        if imgs:
            for idx, img_path in enumerate(imgs):
                if os.path.exists(img_path):
                    st.markdown("""
                    <div style="border: 1px solid #CBD5E1; border-radius: 8px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); overflow: hidden; margin-top: 15px; margin-bottom: 25px; background: white;">
                    """, unsafe_allow_html=True)
                    st.image(img_path, caption=f"Page {idx+1} of {len(imgs)} (Exact Print & ATS Layout)", use_container_width=True)
                    st.markdown("</div>", unsafe_allow_html=True)
        else:
            st.info("Generating live document preview...")
            _, imgs = recompile_resume_data(active_resume, active_resume["pdf_path"])
            active_resume["preview_images"] = imgs
            st.session_state[state_key] = active_resume
            st.rerun()

        # Bottom Download button
        if os.path.exists(active_resume.get("pdf_path", "")):
            with open(active_resume["pdf_path"], "rb") as f:
                st.download_button(
                    label="📥 Download ATS-Friendly Resume PDF",
                    data=f,
                    file_name=dl_pdf_filename,
                    mime="application/pdf",
                    key=f"{session_prefix}_dl_bottom",
                    use_container_width=True
                )

    # =========================================================================
    # TAB 2: DIRECT IN-RESUME EDITOR (EVERY SINGLE LETTER EDITABLE)
    # =========================================================================
    with tab_edit:
        st.markdown("### ✏️ Complete Resume Editor")
        st.caption("Every single letter, word, bullet, and section is directly editable below. You can also completely remove or clear 'Key Achievements' and points underneath it.")

        with st.form(key=f"{session_prefix}_full_editor_form"):
            # 1. Header & Contact Information + Visibility Toggles
            st.markdown("#### 👤 1. Personal Details & Header Display Settings")
            pers = active_resume.setdefault("personal", {})
            
            new_name = st.text_input("Full Name", value=pers.get("name", "Candidate"), key=f"{session_prefix}_p_name")

            c_p1, c_p2, c_p3 = st.columns(3)
            with c_p1:
                new_email = st.text_input("Email Address", value=pers.get("email", ""), key=f"{session_prefix}_p_email")
                show_email = st.checkbox("Show Email on Resume", value=pers.get("show_email", True), key=f"{session_prefix}_chk_email")
            with c_p2:
                new_phone = st.text_input("Mobile Phone", value=pers.get("phone", ""), key=f"{session_prefix}_p_phone")
                show_phone = st.checkbox("Show Phone on Resume", value=pers.get("show_phone", True), key=f"{session_prefix}_chk_phone")
            with c_p3:
                new_loc = st.text_input("Location (City, Province)", value=pers.get("location", ""), key=f"{session_prefix}_p_loc")
                show_loc = st.checkbox("Show Location on Resume", value=pers.get("show_location", True), key=f"{session_prefix}_chk_loc")

            # Dedicated Section: Clickable Links & Visibility
            st.markdown("##### 🔗 Clickable Header Links (LinkedIn & GitHub / Portfolio)")
            st.caption("Put links directly behind words like 'LinkedIn' and 'GitHub'. Recruiters see clean text and clicking opens your profile.")

            col_li1, col_li2 = st.columns([3, 1.5])
            with col_li1:
                new_li = st.text_input("LinkedIn Profile URL", value=pers.get("linkedin", ""), placeholder="e.g. https://linkedin.com/in/aman040499", key=f"{session_prefix}_p_li")
            with col_li2:
                new_li_label = st.text_input("Link Display Text (LinkedIn)", value=pers.get("linkedin_label", "LinkedIn") or "LinkedIn", key=f"{session_prefix}_p_li_lbl")
            show_li = st.checkbox("Show LinkedIn on Resume (Link behind word 'LinkedIn')", value=pers.get("show_linkedin", True), key=f"{session_prefix}_chk_li")

            col_gh1, col_gh2 = st.columns([3, 1.5])
            with col_gh1:
                new_gh = st.text_input("GitHub / Portfolio URL", value=pers.get("github", ""), placeholder="e.g. https://github.com/aman040499/Enterprise-AD-Lab-Portfolio", key=f"{session_prefix}_p_gh")
            with col_gh2:
                new_gh_label = st.text_input("Link Display Text (GitHub)", value=pers.get("github_label", "GitHub") or "GitHub", key=f"{session_prefix}_p_gh_lbl")
            show_gh = st.checkbox("Show GitHub / Portfolio on Resume (Uncheck if you don't need to show GitHub)", value=pers.get("show_github", True), key=f"{session_prefix}_chk_gh")

            # Dedicated Link Color & Styling Controls
            st.markdown("###### 🎨 Link Text Color & Styling")
            col_lc1, col_lc2, col_lc3 = st.columns([2, 1.2, 1.3])
            
            preset_options = [
                "Professional Blue (#0A66C2)",
                "Modern GitHub Blue (#0969DA)",
                "Royal Blue (#1D4ED8)",
                "Modern Teal (#0F766E)",
                "Forest Green (#3F7F4A)",
                "Dark Slate (#334155)",
                "Classic Black (#000000)",
                "Custom Hex Color"
            ]
            
            curr_link_color = pers.get("link_color", "#0A66C2").upper()
            init_preset_idx = 0
            for i, opt in enumerate(preset_options):
                if curr_link_color in opt:
                    init_preset_idx = i
                    break
            else:
                if curr_link_color != "#0A66C2":
                    init_preset_idx = len(preset_options) - 1

            with col_lc1:
                selected_link_preset = st.selectbox(
                    "Link Color Preset",
                    preset_options,
                    index=init_preset_idx,
                    help="Choose the color for 'LinkedIn' and 'GitHub' text links.",
                    key=f"{session_prefix}_sel_link_color"
                )

            preset_hex_map = {
                "Professional Blue": "#0A66C2",
                "Modern GitHub Blue": "#0969DA",
                "Royal Blue": "#1D4ED8",
                "Modern Teal": "#0F766E",
                "Forest Green": "#3F7F4A",
                "Dark Slate": "#334155",
                "Classic Black": "#000000"
            }
            preset_base = selected_link_preset.split(" (")[0]
            suggested_hex = preset_hex_map.get(preset_base, curr_link_color)
            if not (suggested_hex.startswith("#") and len(suggested_hex) == 7):
                suggested_hex = "#0A66C2"

            with col_lc2:
                picked_link_color = st.color_picker(
                    "Custom Color",
                    value=suggested_hex,
                    help="Pick any custom color for the links.",
                    key=f"{session_prefix}_pick_link_color"
                )

            final_link_color = picked_link_color if "Custom" in selected_link_preset else suggested_hex

            with col_lc3:
                st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
                underline_links = st.checkbox(
                    "Underline Links",
                    value=pers.get("underline_links", False),
                    help="Render a subtle underline beneath clickable links.",
                    key=f"{session_prefix}_chk_underline_links"
                )

            curr_headings = active_resume.setdefault("custom_headings", {})

            # 2. Professional Summary
            st.markdown("#### 📝 2. Professional Executive Summary")
            col_sh1, col_sh2 = st.columns([1.8, 3])
            with col_sh1:
                new_h_summary = st.text_input("Section Heading Title (Summary)", value=curr_headings.get("summary", "PROFESSIONAL SUMMARY"), key=f"{session_prefix}_h_summary")
            new_summary = st.text_area(
                "Executive Summary Text",
                value=active_resume.get("summary", ""),
                height=110,
                key=f"{session_prefix}_edit_summary"
            )

            st.markdown("---")

            # 3. Technical Skills by Category
            st.markdown("#### 🛠️ 3. Technical Skills (Categories & Skills)")
            col_skh1, col_skh2 = st.columns([1.8, 3])
            with col_skh1:
                new_h_skills = st.text_input("Section Heading Title (Skills)", value=curr_headings.get("skills", "TECHNICAL SKILLS"), key=f"{session_prefix}_h_skills")
            skills_dict = sanitize_skills_dict(active_resume.get("skills", {}))
            active_resume["skills"] = skills_dict
            edited_skills = {}
            for cat, items in list(skills_dict.items()):
                cat_label = format_category_title(cat)
                current_val = ", ".join(items) if isinstance(items, list) else str(items)
                
                col_c1, col_c2 = st.columns([1.5, 3])
                with col_c1:
                    new_cat_label = st.text_input(f"Category Name", value=cat_label, key=f"{session_prefix}_cat_name_{cat}")
                with col_c2:
                    new_val = st.text_input(f"Skills for {cat_label} (Comma-separated)", value=current_val, key=f"{session_prefix}_skill_{cat}")
                
                clean_cat = format_category_title(new_cat_label.strip()) if new_cat_label.strip() else cat
                items_list = [i.strip() for i in new_val.split(",") if i.strip()]
                if items_list:
                    edited_skills[clean_cat] = items_list

            # Add New Categories (Multiple Slots: 1, 2, or 3)
            st.markdown("##### ➕ Add More Categories")
            st.caption("Add one, two, or three custom skill categories below. Leave blank if not needed.")
            cat_placeholders = [
                ("e.g. Automation & AI", "e.g. Generative AI, LLMs, LangChain, Python"),
                ("e.g. Cloud & Infrastructure", "e.g. Microsoft Azure, AWS, Docker, Kubernetes"),
                ("e.g. Methodologies & Tools", "e.g. Agile, Scrum, Jira, Git, CI/CD")
            ]
            for slot_i, (p_cat, p_skills) in enumerate(cat_placeholders, start=1):
                c_nc1, c_nc2 = st.columns([1.5, 3])
                with c_nc1:
                    new_cat_name = st.text_input(
                        f"➕ Add Category #{slot_i} (Optional)",
                        placeholder=p_cat,
                        key=f"{session_prefix}_new_cat_name_{slot_i}"
                    )
                with c_nc2:
                    new_cat_skills = st.text_input(
                        f"Skills for Category #{slot_i}",
                        placeholder=p_skills,
                        key=f"{session_prefix}_new_cat_skills_{slot_i}"
                    )
                if new_cat_name.strip() and new_cat_skills.strip():
                    clean_new_cat = format_category_title(new_cat_name.strip())
                    edited_skills[clean_new_cat] = [i.strip() for i in new_cat_skills.split(",") if i.strip()]

            st.markdown("---")

            # 4. Professional Experience & Achievements
            st.markdown("#### 💼 4. Professional Experience & Key Achievements")
            st.caption("Edit job titles, dates, locations, bullet points, and Key Achievements. Leave Key Achievements blank to remove them entirely.")
            col_exh1, col_exh2 = st.columns([1.8, 3])
            with col_exh1:
                new_h_exp = st.text_input("Section Heading Title (Experience)", value=curr_headings.get("experience", "PROFESSIONAL EXPERIENCE"), key=f"{session_prefix}_h_exp")

            edited_experience = copy.deepcopy(active_resume.get("experience", []))
            for exp_idx, role in enumerate(edited_experience):
                st.markdown(f"**Position #{exp_idx+1}:**")
                ce1, ce2 = st.columns(2)
                with ce1:
                    role["title"] = st.text_input(f"Job Title #{exp_idx+1}", value=role.get("title", ""), key=f"{session_prefix}_exp_title_{exp_idx}")
                    role["company"] = st.text_input(f"Company #{exp_idx+1}", value=role.get("company", ""), key=f"{session_prefix}_exp_company_{exp_idx}")
                with ce2:
                    role["dates"] = st.text_input(f"Dates #{exp_idx+1}", value=role.get("dates", ""), key=f"{session_prefix}_exp_dates_{exp_idx}")
                    role["location"] = st.text_input(f"Location #{exp_idx+1}", value=role.get("location", ""), key=f"{session_prefix}_exp_loc_{exp_idx}")

                # Clean stray Key Achievements from bullets text
                raw_b_list = role.get("bullets", [])
                cleaned_b_list = []
                for b in raw_b_list:
                    cb = re.sub(r"(?:[.:\s]+|^)Key Achievements:?\s*$", "", str(b), flags=re.IGNORECASE).strip()
                    cb = re.sub(r"^Key Achievements:?\s*", "", cb, flags=re.IGNORECASE).strip()
                    if cb:
                        cleaned_b_list.append(cb)

                current_bullets_text = "\n".join(cleaned_b_list)
                new_bullets_text = st.text_area(
                    f"Responsibilities / Bullets for {role.get('company', 'Role')} (One bullet per line)",
                    value=current_bullets_text,
                    height=180,
                    key=f"{session_prefix}_exp_bullets_{exp_idx}"
                )
                role["bullets"] = [b.strip() for b in new_bullets_text.splitlines() if b.strip()]

                # KEY ACHIEVEMENTS (Fully Editable and Removable!)
                raw_achs = role.get("achievements", [])
                clean_achs = [str(a).strip().strip("•*-· ") for a in raw_achs if str(a).strip()]
                current_achs_text = "\n".join(clean_achs)
                new_achs_text = st.text_area(
                    f"🏆 Key Achievements for {role.get('company', 'Role')} (Leave empty to REMOVE 'Key Achievements' and all points underneath it)",
                    value=current_achs_text,
                    height=90,
                    help="To remove 'Key Achievements' from your resume, simply erase all text from this box!",
                    key=f"{session_prefix}_exp_achs_{exp_idx}"
                )
                role["achievements"] = [a.strip() for a in new_achs_text.splitlines() if a.strip()]

            st.markdown("---")

            # 5. Technical Projects
            st.markdown("#### 🚀 5. Technical Projects")
            st.caption("Edit existing projects, remove any unwanted project, or use the dedicated slots below to add up to 2 new technical projects.")
            col_prh1, col_prh2 = st.columns([1.8, 3])
            with col_prh1:
                new_h_proj = st.text_input("Section Heading Title (Projects)", value=curr_headings.get("projects", "PROJECTS"), key=f"{session_prefix}_h_proj")
            projects_list = copy.deepcopy(active_resume.get("projects", []))
            kept_projects = []
            for p_idx, proj in enumerate(projects_list):
                st.markdown(f"**Project #{p_idx+1}:**")
                cp1, cp2, cp3 = st.columns([5, 5, 2])
                with cp1:
                    proj["title"] = st.text_input(f"Project Title #{p_idx+1}", value=proj.get("title", ""), key=f"{session_prefix}_proj_title_{p_idx}")
                with cp2:
                    proj["technologies"] = st.text_input(f"Technologies Used #{p_idx+1}", value=proj.get("technologies", ""), key=f"{session_prefix}_proj_tech_{p_idx}")
                with cp3:
                    st.write("")
                    remove_this_proj = st.checkbox(f"🗑️ Remove #{p_idx+1}", key=f"{session_prefix}_del_proj_{p_idx}")
                
                current_p_bullets = "\n".join(proj.get("bullets", []))
                new_p_bullets = st.text_area(
                    f"Project Bullets #{p_idx+1} (One per line)",
                    value=current_p_bullets,
                    height=100,
                    key=f"{session_prefix}_proj_bullets_{p_idx}"
                )
                proj["bullets"] = [b.strip() for b in new_p_bullets.splitlines() if b.strip()]
                if not remove_this_proj:
                    kept_projects.append(proj)
            projects_list = kept_projects

            # Dedicated Addition Slots for 2 New Projects
            st.markdown("##### ➕ Add New Projects (2 Dedicated Project Slots)")
            with st.expander("➕ Add Technical Projects (Slot 1 & Slot 2)", expanded=True):
                st.markdown("**🚀 Project Addition #1:**")
                c_p1_a, c_p1_b = st.columns([2, 3])
                with c_p1_a:
                    add_p1_title = st.text_input(
                        "Project Title (Slot 1)",
                        placeholder="e.g. Distributed Cloud Storage Architecture",
                        key=f"{session_prefix}_add_proj_title_1"
                    )
                with c_p1_b:
                    add_p1_tech = st.text_input(
                        "Technologies Used (Slot 1)",
                        placeholder="e.g. Python, AWS S3, FastAPI, Docker",
                        key=f"{session_prefix}_add_proj_tech_1"
                    )
                add_p1_bullets = st.text_area(
                    "Project Bullets (Slot 1 — One per line)",
                    placeholder="Architected high-throughput storage backend processing 50K files daily.\nContainerized service with Docker and deployed to AWS ECS cluster.",
                    height=90,
                    key=f"{session_prefix}_add_proj_bullets_1"
                )

                st.markdown("---")
                st.markdown("**🚀 Project Addition #2:**")
                c_p2_a, c_p2_b = st.columns([2, 3])
                with c_p2_a:
                    add_p2_title = st.text_input(
                        "Project Title (Slot 2)",
                        placeholder="e.g. Network Monitoring & Telemetry Dashboard",
                        key=f"{session_prefix}_add_proj_title_2"
                    )
                with c_p2_b:
                    add_p2_tech = st.text_input(
                        "Technologies Used (Slot 2)",
                        placeholder="e.g. React, TypeScript, Prometheus, Grafana",
                        key=f"{session_prefix}_add_proj_tech_2"
                    )
                add_p2_bullets = st.text_area(
                    "Project Bullets (Slot 2 — One per line)",
                    placeholder="Implemented real-time latency visualization telemetry for 200+ servers.\nAutomated alerting pipeline reducing mean incident detection time by 40%.",
                    height=90,
                    key=f"{session_prefix}_add_proj_bullets_2"
                )

            if add_p1_title.strip() or add_p1_bullets.strip():
                projects_list.append({
                    "title": add_p1_title.strip(),
                    "technologies": add_p1_tech.strip(),
                    "bullets": [b.strip() for b in add_p1_bullets.splitlines() if b.strip()]
                })
            if add_p2_title.strip() or add_p2_bullets.strip():
                projects_list.append({
                    "title": add_p2_title.strip(),
                    "technologies": add_p2_tech.strip(),
                    "bullets": [b.strip() for b in add_p2_bullets.splitlines() if b.strip()]
                })

            st.markdown("---")

            # 6. Education & Certifications
            st.markdown("#### 🎓 6. Education & Certifications")
            col_edh1, col_edh2 = st.columns(2)
            with col_edh1:
                new_h_edu = st.text_input("Section Heading Title (Education)", value=curr_headings.get("education", "EDUCATION"), key=f"{session_prefix}_h_edu")
            with col_edh2:
                new_h_certs = st.text_input("Section Heading Title (Certifications)", value=curr_headings.get("certifications", "CERTIFICATIONS & LICENSES"), key=f"{session_prefix}_h_certs")
            education_list = copy.deepcopy(active_resume.get("education", []))
            if not education_list:
                education_list = [{"institution": "", "degree": "", "year": "", "details": ""}]
            for e_idx, edu in enumerate(education_list):
                ce1, ce2 = st.columns(2)
                with ce1:
                    edu["institution"] = st.text_input(f"Institution #{e_idx+1}", value=edu.get("institution", ""), key=f"{session_prefix}_edu_inst_{e_idx}")
                    edu["degree"] = st.text_input(f"Degree / Diploma #{e_idx+1}", value=edu.get("degree", ""), key=f"{session_prefix}_edu_deg_{e_idx}")
                with ce2:
                    edu["year"] = st.text_input(f"Year / Dates #{e_idx+1}", value=str(edu.get("year", "")), key=f"{session_prefix}_edu_yr_{e_idx}")
                    edu["details"] = st.text_input(f"Concentrations / Focus #{e_idx+1}", value=edu.get("details", ""), key=f"{session_prefix}_edu_det_{e_idx}")

            # Optional extra education entry
            st.markdown("##### ➕ Add Another Education Entry (Optional)")
            ce_add1, ce_add2 = st.columns(2)
            with ce_add1:
                add_inst = st.text_input("Institution (Optional)", placeholder="e.g. University of Toronto", key=f"{session_prefix}_add_edu_inst")
                add_deg = st.text_input("Degree / Diploma (Optional)", placeholder="e.g. Bachelor of Computer Science", key=f"{session_prefix}_add_edu_deg")
            with ce_add2:
                add_yr = st.text_input("Year / Dates (Optional)", placeholder="e.g. 2024", key=f"{session_prefix}_add_edu_yr")
                add_det = st.text_input("Concentrations / Focus (Optional)", placeholder="e.g. Honours, Dean's List", key=f"{session_prefix}_add_edu_det")
            if add_inst.strip() or add_deg.strip():
                education_list.append({
                    "institution": add_inst.strip(),
                    "degree": add_deg.strip(),
                    "year": add_yr.strip(),
                    "details": add_det.strip()
                })

            # Certifications & Licenses (Fully Editable)
            st.markdown("##### 📜 Certifications & Licenses")
            st.caption("Edit existing certifications, add new ones, or clear a box to remove it. Formatted as clean ATS bullet points.")

            raw_cert_list = active_resume.get("certifications", [])
            # Normalize cert list into string items
            norm_certs = []
            for c in raw_cert_list:
                if isinstance(c, dict):
                    parts = [c.get("name", "")]
                    if c.get("issuer"):
                        parts.append(c["issuer"])
                    line = " — ".join(p for p in parts if p)
                    if c.get("year"):
                        line += f" | {c['year']}"
                    if line.strip():
                        norm_certs.append(line.strip())
                elif isinstance(c, str) and c.strip():
                    norm_certs.append(re.sub(r"^[-•*·\s]+", "", c).strip())

            edited_certs = []
            # Render individual editable row for each existing certification
            if norm_certs:
                for c_idx, cert_str in enumerate(norm_certs):
                    col_ct1, col_ct2 = st.columns([4.2, 0.8])
                    with col_ct1:
                        new_c_val = st.text_input(
                            f"Certification #{c_idx+1}",
                            value=cert_str,
                            key=f"{session_prefix}_cert_item_{c_idx}",
                            help="Edit the certification name, organization, or date. Clear this field to remove it."
                        )
                    with col_ct2:
                        st.caption("Active Bullet")
                    if new_c_val.strip():
                        edited_certs.append(new_c_val.strip())
            else:
                st.info("No certifications currently listed. Use the slots below to add your certifications.")

            # Multiple dedicated slots to add new certifications (Slots 1, 2, 3)
            st.markdown("###### ➕ Add New Certifications")
            c_placeholders = [
                "e.g. Microsoft Certified: Azure Fundamentals (AZ-900)",
                "e.g. Canadian Securities Course (CSC) — Canadian Securities Institute",
                "e.g. Anti-Money Laundering (AML) Compliance Certification"
            ]
            for slot_i, p_text in enumerate(c_placeholders, start=1):
                new_add_cert = st.text_input(
                    f"➕ Add Certification #{slot_i} (Optional)",
                    placeholder=p_text,
                    key=f"{session_prefix}_add_cert_{slot_i}"
                )
                if new_add_cert.strip():
                    clean_added_cert = re.sub(r"^[-•*·\s]+", "", new_add_cert).strip()
                    if clean_added_cert and clean_added_cert not in edited_certs:
                        edited_certs.append(clean_added_cert)

            # Bulk Edit Expander (for pasting multiple certifications at once)
            with st.expander("📋 Bulk Paste / Edit Certifications List", expanded=False):
                bulk_certs_text = st.text_area(
                    "Paste multiple certifications (One per line)",
                    value="\n".join(edited_certs) if edited_certs else "",
                    height=100,
                    key=f"{session_prefix}_bulk_certs_textarea",
                    help="You can paste or edit the full list of certifications here."
                )
                use_bulk = st.checkbox("Override with Bulk List upon Save", value=False, key=f"{session_prefix}_chk_use_bulk_certs")
                if use_bulk:
                    edited_certs = [c.strip() for c in bulk_certs_text.splitlines() if c.strip()]

            # Section separation toggle
            separate_edu_certs = st.checkbox(
                "Separate 'Education' and 'Certifications & Licenses' into distinct sections (Industry Standard)",
                value=active_resume.get("separate_education_and_certs", True),
                help="When enabled, creates two dedicated sections with professional green headers. Certifications will be formatted as clean ATS-friendly bullet points.",
                key=f"{session_prefix}_sep_edu_certs"
            )

            st.markdown("---")

            # 7. Additional / Custom Sections (Volunteer Experience, Languages, Publications, etc.)
            st.markdown("#### 📑 7. Additional & Custom Sections (Volunteer, Publications, Languages, etc.)")
            st.caption("Add or customize any extra section. Sections are rendered in the professional house green heading format.")
            
            existing_add_sections = copy.deepcopy(active_resume.get("additional_sections", []))
            edited_add_sections = []
            
            if existing_add_sections:
                for a_idx, a_sec in enumerate(existing_add_sections):
                    st.markdown(f"**Section #{a_idx+1}:**")
                    col_as1, col_as2 = st.columns([4, 1])
                    with col_as1:
                        a_title = st.text_input(f"Section Heading Title #{a_idx+1}", value=a_sec.get("title", ""), key=f"{session_prefix}_add_sec_title_{a_idx}")
                    with col_as2:
                        st.write("")
                        del_sec = st.checkbox(f"🗑️ Delete #{a_idx+1}", key=f"{session_prefix}_del_add_sec_{a_idx}")
                    
                    raw_content = a_sec.get("content", [])
                    if isinstance(raw_content, list):
                        c_text = "\n".join(str(item) for item in raw_content)
                    else:
                        c_text = str(raw_content)
                        
                    a_content = st.text_area(
                        f"Section Content #{a_idx+1} (Bullet points start with - or •)",
                        value=c_text,
                        height=100,
                        key=f"{session_prefix}_add_sec_content_{a_idx}"
                    )
                    if not del_sec and a_title.strip() and a_content.strip():
                        c_lines = [line.strip() for line in a_content.splitlines() if line.strip()]
                        edited_add_sections.append({
                            "title": a_title.strip().upper(),
                            "content": c_lines
                        })
            
            # Slot to add a brand new custom section
            st.markdown("##### ➕ Add a New Custom Section")
            c_as_add1, c_as_add2 = st.columns([2, 3])
            with c_as_add1:
                new_sec_title = st.text_input(
                    "New Section Title",
                    placeholder="e.g. VOLUNTEER EXPERIENCE or LANGUAGES",
                    key=f"{session_prefix}_new_custom_sec_title"
                )
            with c_as_add2:
                new_sec_content = st.text_area(
                    "New Section Content (One bullet per line)",
                    placeholder="• Community Mentor at Local STEM Program (2022 – Present)\n• English (Fluent), French (Professional Working Proficiency)",
                    height=80,
                    key=f"{session_prefix}_new_custom_sec_content"
                )
            if new_sec_title.strip() and new_sec_content.strip():
                clean_new_lines = [l.strip() for l in new_sec_content.splitlines() if l.strip()]
                edited_add_sections.append({
                    "title": new_sec_title.strip().upper(),
                    "content": clean_new_lines
                })

            st.markdown("---")

            # 8. Spacing & Layout Customizer (Leave Space Anywhere)
            st.markdown("#### 📐 8. Spacing & Layout Controls (Adjust Breathing Room)")
            c_sp1, c_sp2, c_sp3 = st.columns(3)
            with c_sp1:
                new_spacing = st.selectbox(
                    "Vertical Section Spacing",
                    ["0.22em (Compact / Fit 1 Page)", "0.35em (Standard Canadian Format)", "0.55em (Spacious / Extra Breathing Room)"],
                    index=1 if active_resume.get("section_spacing") == "0.35em" else (2 if "0.55" in active_resume.get("section_spacing", "") else 0),
                    key=f"{session_prefix}_sec_spacing"
                )
            with c_sp2:
                new_font_size = st.selectbox(
                    "Body Text Font Size",
                    ["8.8pt (Small / High Density)", "9.1pt (Standard Clean)", "9.5pt (Large / Readable)"],
                    index=1 if active_resume.get("font_size") == "9.1pt" else (2 if "9.5" in active_resume.get("font_size", "") else 0),
                    key=f"{session_prefix}_font_size"
                )
            with c_sp3:
                new_margins = st.selectbox(
                    "Top / Bottom Margins",
                    ["0.8cm (Maximum Space)", "1.1cm (Standard Clean)", "1.4cm (Comfortable)"],
                    index=1,
                    key=f"{session_prefix}_margins"
                )

            # Page Break Controls (Send Heading to Next Page)
            st.markdown("##### 📄 Page Break Controls (Send Headings to Next Page)")
            st.caption("Push any section heading cleanly to the top of the next page. Built-in 3-line orphan heading prevention automatically pushes headings to Page 2 if fewer than 3 lines can fit under them.")
            cpb1, cpb2 = st.columns(2)
            with cpb1:
                pb_certs = st.checkbox(
                    "📄 Push 'Certifications & Licenses' to Next Page",
                    value=active_resume.get("pagebreak_before_certs", False),
                    key=f"{session_prefix}_pb_certs",
                    help="Forces the 'CERTIFICATIONS & LICENSES' heading and its bullets to start cleanly on the next page."
                )
                pb_edu = st.checkbox(
                    "📄 Push 'Education' to Next Page",
                    value=active_resume.get("pagebreak_before_education", False),
                    key=f"{session_prefix}_pb_edu",
                    help="Forces the 'EDUCATION' heading and its details to start cleanly on the next page."
                )
            with cpb2:
                pb_proj = st.checkbox(
                    "📄 Push 'Technical Projects' to Next Page",
                    value=active_resume.get("pagebreak_before_projects", False),
                    key=f"{session_prefix}_pb_proj",
                    help="Forces the 'PROJECTS' heading to start cleanly on the next page."
                )
                pb_exp = st.checkbox(
                    "📄 Push 'Professional Experience' to Next Page",
                    value=active_resume.get("pagebreak_before_experience", False),
                    key=f"{session_prefix}_pb_exp",
                    help="Forces the 'PROFESSIONAL EXPERIENCE' heading to start cleanly on the next page."
                )

            # SAVE MANUAL EDITS BUTTON
            save_manual = st.form_submit_button("💾 Save All Manual Changes & Recompile PDF", type="primary", use_container_width=True)

            if save_manual:
                active_resume["personal"] = {
                    "name": new_name,
                    "email": new_email,
                    "phone": new_phone,
                    "location": new_loc,
                    "linkedin": new_li,
                    "github": new_gh,
                    "show_email": show_email,
                    "show_phone": show_phone,
                    "show_location": show_loc,
                    "show_linkedin": show_li,
                    "show_github": show_gh,
                    "linkedin_label": new_li_label,
                    "github_label": new_gh_label,
                    "link_color": final_link_color,
                    "underline_links": underline_links
                }
                active_resume["summary"] = new_summary
                active_resume["skills"] = sanitize_skills_dict(edited_skills)
                active_resume["experience"] = edited_experience
                # Clean projects list: retain projects with at least a title or a bullet
                clean_projects_list = []
                for p in projects_list:
                    p_t = p.get("title", "").strip()
                    p_b = [b.strip() for b in p.get("bullets", []) if b.strip()]
                    if p_t or p_b:
                        clean_projects_list.append({
                            "title": p_t,
                            "technologies": p.get("technologies", "").strip(),
                            "bullets": p_b
                        })
                active_resume["projects"] = clean_projects_list

                # Clean education list
                clean_edu_list = []
                for edu in education_list:
                    if edu.get("institution", "").strip() or edu.get("degree", "").strip():
                        clean_edu_list.append({
                            "institution": edu.get("institution", "").strip(),
                            "degree": edu.get("degree", "").strip(),
                            "year": str(edu.get("year", "")).strip(),
                            "details": edu.get("details", "").strip()
                        })
                active_resume["education"] = clean_edu_list

                clean_unique_certs = []
                seen_certs = set()
                for c in edited_certs:
                    clean_c = re.sub(r"^[-•*·\s]+", "", str(c)).strip()
                    norm_c = re.sub(r'[\s\-—|]+', ' ', clean_c).lower()
                    if norm_c and norm_c not in seen_certs:
                        seen_certs.add(norm_c)
                        clean_unique_certs.append(clean_c)
                active_resume["certifications"] = clean_unique_certs

                # Save custom heading titles
                active_resume["custom_headings"] = {
                    "summary": (new_h_summary.strip() if new_h_summary.strip() else "PROFESSIONAL SUMMARY").upper(),
                    "skills": (new_h_skills.strip() if new_h_skills.strip() else "TECHNICAL SKILLS").upper(),
                    "experience": (new_h_exp.strip() if new_h_exp.strip() else "PROFESSIONAL EXPERIENCE").upper(),
                    "projects": (new_h_proj.strip() if new_h_proj.strip() else "PROJECTS").upper(),
                    "education": (new_h_edu.strip() if new_h_edu.strip() else "EDUCATION").upper(),
                    "certifications": (new_h_certs.strip() if new_h_certs.strip() else "CERTIFICATIONS & LICENSES").upper()
                }

                # Save additional / custom sections
                active_resume["additional_sections"] = edited_add_sections

                active_resume["separate_education_and_certs"] = separate_edu_certs
                active_resume["section_spacing"] = new_spacing.split()[0]
                active_resume["font_size"] = new_font_size.split()[0]
                active_resume["top_margin"] = new_margins.split()[0]
                active_resume["bottom_margin"] = new_margins.split()[0]
                active_resume["pagebreak_before_certs"] = pb_certs
                active_resume["pagebreak_before_education"] = pb_edu
                active_resume["pagebreak_before_projects"] = pb_proj
                active_resume["pagebreak_before_experience"] = pb_exp

                # Clear category, education, cert, project, and custom section add slots so they are blank on next render
                for slot_i in range(1, 4):
                    st.session_state.pop(f"{session_prefix}_new_cat_name_{slot_i}", None)
                    st.session_state.pop(f"{session_prefix}_new_cat_skills_{slot_i}", None)
                    st.session_state.pop(f"{session_prefix}_add_cert_{slot_i}", None)
                for slot_i in (1, 2):
                    st.session_state.pop(f"{session_prefix}_add_proj_title_{slot_i}", None)
                    st.session_state.pop(f"{session_prefix}_add_proj_tech_{slot_i}", None)
                    st.session_state.pop(f"{session_prefix}_add_proj_bullets_{slot_i}", None)
                for k in list(st.session_state.keys()):
                    if k.startswith(f"{session_prefix}_del_proj_") or k.startswith(f"{session_prefix}_del_add_sec_"):
                        st.session_state.pop(k, None)
                st.session_state.pop(f"{session_prefix}_add_edu_inst", None)
                st.session_state.pop(f"{session_prefix}_add_edu_deg", None)
                st.session_state.pop(f"{session_prefix}_add_edu_yr", None)
                st.session_state.pop(f"{session_prefix}_add_edu_det", None)
                st.session_state.pop(f"{session_prefix}_chk_use_bulk_certs", None)
                st.session_state.pop(f"{session_prefix}_new_custom_sec_title", None)
                st.session_state.pop(f"{session_prefix}_new_custom_sec_content", None)

                try:
                    with st.spinner("Recompiling tailored PDF and generating preview..."):
                        pdf_path, imgs = recompile_resume_data(active_resume, active_resume["pdf_path"])
                        active_resume["preview_images"] = imgs
                        
                        # Synchronize Raw Typst tab code and widget state with latest manual edits!
                        _sync_typst_after_edit(active_resume, session_prefix)
                        _clear_studio_widget_keys(session_prefix)
                        
                        st.session_state[state_key] = active_resume
                        st.session_state[feedback_key] = ("success", "💾 All manual edits saved, PDF recompiled, and Raw Typst tab synchronized successfully!")
                        st.rerun()
                except Exception as err:
                    st.error(f"⚠️ Notice: Unable to recompile ({err}). Your edits are safely preserved.")

        # =====================================================================
        # 8. DEDICATED LLM INSTRUCTIONS TEXTBOX AT THE END OF THE EDITOR
        # =====================================================================
        st.markdown("""
        <div style="background-color: #EFF6FF; border: 1.5px solid #93C5FD; border-radius: 10px; padding: 18px 22px; margin-top: 30px;">
            <h4 style="margin-top: 0; color: #1E3A8A; display: flex; align-items: center; gap: 8px;">
                🤖 AI Assistant — Pass Custom Instructions to LLM
            </h4>
            <p style="color: #1E40AF; font-size: 0.95rem; margin-bottom: 12px;">
                Have an additional request or refinement? Type it below (e.g. <b>"Make the text blue for LinkedIn and GitHub"</b>, <b>"Separate Education and Certifications"</b>, <b>"Put link behind LinkedIn text"</b>, <b>"Don't show GitHub"</b>, <b>"Remove Key Achievements and points underneath it"</b>). The LLM processes your command and updates the resume instantly.
            </p>
        </div>
        """, unsafe_allow_html=True)

        with st.form(key=f"{session_prefix}_ai_end_form", clear_on_submit=True):
            end_instruction = st.text_area(
                "Pass Instructions to LLM:",
                placeholder="Type any custom instruction here (e.g. Make link text blue for LinkedIn and GitHub, Separate Education and Certifications, Put link behind LinkedIn, Don't show GitHub, Remove Key Achievements)...",
                height=90,
                key=f"{session_prefix}_end_inst_input"
            )
            c_exec, c_clr_ach = st.columns([3, 2])
            with c_exec:
                submit_end = st.form_submit_button("⚡ Execute LLM Instruction & Update Resume", type="primary", use_container_width=True)
            with c_clr_ach:
                submit_quick_ach = st.form_submit_button("🗑️ Quick Remove 'Key Achievements'", use_container_width=True)

            if submit_end and end_instruction.strip():
                try:
                    with st.spinner("LLM applying custom instructions..."):
                        updated, explanation = apply_instruction_to_resume(active_resume, end_instruction.strip(), api_key=api_key)
                        pdf_path, imgs = recompile_resume_data(updated, updated["pdf_path"])
                        updated["preview_images"] = imgs
                        new_typst = generate_typst_source(
                            personal=updated.get("personal", {}),
                            summary=updated.get("summary", ""),
                            skills=updated.get("skills", {}),
                            experience=updated.get("experience", []),
                            education=updated.get("education", []),
                            certifications=updated.get("certifications", []),
                            achievements=updated.get("achievements", []),
                            projects=updated.get("projects", []),
                            section_spacing=updated.get("section_spacing", "0.35em"),
                            font_size=updated.get("font_size", "9.1pt"),
                            top_margin=updated.get("top_margin", "1.1cm"),
                            bottom_margin=updated.get("bottom_margin", "1.1cm"),
                            separate_education_and_certs=updated.get("separate_education_and_certs", True),
                            pagebreak_before_experience=updated.get("pagebreak_before_experience", False),
                            pagebreak_before_projects=updated.get("pagebreak_before_projects", False),
                            pagebreak_before_education=updated.get("pagebreak_before_education", False),
                            pagebreak_before_certs=updated.get("pagebreak_before_certs", False),
                            pagebreak_before_achievements=updated.get("pagebreak_before_achievements", False),
                            custom_headings=updated.get("custom_headings"),
                            additional_sections=updated.get("additional_sections")
                        )
                        updated["raw_typst_code"] = new_typst
                        updated["typst_version"] = updated.get("typst_version", 0) + 1
                        st.session_state[state_key] = updated
                        st.session_state[feedback_key] = ("success", f"✅ {explanation}")
                        _clear_studio_widget_keys(session_prefix)
                        st.rerun()
                except Exception as err:
                    st.error(f"⚠️ Notice: Unable to apply instruction ({err}). Resume preserved safely.")

            if submit_quick_ach:
                try:
                    with st.spinner("Removing Key Achievements and points..."):
                        updated, explanation = apply_instruction_to_resume(active_resume, "Remove Key Achievements and points underneath it", api_key=api_key)
                        pdf_path, imgs = recompile_resume_data(updated, updated["pdf_path"])
                        updated["preview_images"] = imgs
                        new_typst = generate_typst_source(
                            personal=updated.get("personal", {}),
                            summary=updated.get("summary", ""),
                            skills=updated.get("skills", {}),
                            experience=updated.get("experience", []),
                            education=updated.get("education", []),
                            certifications=updated.get("certifications", []),
                            achievements=updated.get("achievements", []),
                            projects=updated.get("projects", []),
                            section_spacing=updated.get("section_spacing", "0.35em"),
                            font_size=updated.get("font_size", "9.1pt"),
                            top_margin=updated.get("top_margin", "1.1cm"),
                            bottom_margin=updated.get("bottom_margin", "1.1cm"),
                            separate_education_and_certs=updated.get("separate_education_and_certs", True),
                            pagebreak_before_experience=updated.get("pagebreak_before_experience", False),
                            pagebreak_before_projects=updated.get("pagebreak_before_projects", False),
                            pagebreak_before_education=updated.get("pagebreak_before_education", False),
                            pagebreak_before_certs=updated.get("pagebreak_before_certs", False),
                            pagebreak_before_achievements=updated.get("pagebreak_before_achievements", False),
                            custom_headings=updated.get("custom_headings"),
                            additional_sections=updated.get("additional_sections")
                        )
                        updated["raw_typst_code"] = new_typst
                        updated["typst_version"] = updated.get("typst_version", 0) + 1
                        st.session_state[state_key] = updated
                        st.session_state[feedback_key] = ("success", f"✅ {explanation}")
                        _clear_studio_widget_keys(session_prefix)
                        st.rerun()
                except Exception as err:
                    st.error(f"⚠️ Notice: Unable to remove achievements ({err}). Resume preserved safely.")

    # =========================================================================
    # TAB 3: RAW TYPST SOURCE CODE EDITOR
    # =========================================================================
    with tab_raw:
        st.markdown("### 📄 Direct Typst Source Code Editor")
        st.caption("For complete micro-control over every single character, margin, and spacing tag (`#v(...)`). Changes compile directly into the PDF and synchronize all editor tabs.")

        raw_typst_content = active_resume.get("raw_typst_code")
        if not raw_typst_content:
            raw_typst_content = generate_typst_source(
                personal=active_resume.get("personal", {}),
                summary=active_resume.get("summary", ""),
                skills=active_resume.get("skills", {}),
                experience=active_resume.get("experience", []),
                education=active_resume.get("education", []),
                certifications=active_resume.get("certifications", []),
                achievements=active_resume.get("achievements", []),
                projects=active_resume.get("projects", []),
                section_spacing=active_resume.get("section_spacing", "0.35em"),
                font_size=active_resume.get("font_size", "9.1pt"),
                top_margin=active_resume.get("top_margin", "1.1cm"),
                bottom_margin=active_resume.get("bottom_margin", "1.1cm"),
                separate_education_and_certs=active_resume.get("separate_education_and_certs", True),
                pagebreak_before_experience=active_resume.get("pagebreak_before_experience", False),
                pagebreak_before_projects=active_resume.get("pagebreak_before_projects", False),
                pagebreak_before_education=active_resume.get("pagebreak_before_education", False),
                pagebreak_before_certs=active_resume.get("pagebreak_before_certs", False),
                pagebreak_before_achievements=active_resume.get("pagebreak_before_achievements", False),
                custom_headings=active_resume.get("custom_headings"),
                additional_sections=active_resume.get("additional_sections")
            )

        typst_ver = active_resume.get("typst_version", 0)

        with st.form(key=f"{session_prefix}_raw_typst_form"):
            edited_typst = st.text_area(
                "Typst Document Source Code",
                value=raw_typst_content,
                height=450,
                key=f"{session_prefix}_raw_typst_area_{typst_ver}"
            )
            save_raw = st.form_submit_button("💾 Apply Raw Code & Recompile PDF (Syncs All Tabs)", type="primary", use_container_width=True)

            if save_raw:
                try:
                    with st.spinner("Compiling Typst code and synchronizing all editor tabs..."):
                        pdf_path, imgs = recompile_raw_typst(edited_typst, active_resume["pdf_path"])
                        
                        # Two-way sync: parse Typst code back into structured active_resume!
                        updated_structured = parse_typst_to_resume_dict(edited_typst, baseline=active_resume)
                        updated_structured["preview_images"] = imgs
                        updated_structured["pdf_path"] = pdf_path
                        new_ver = typst_ver + 1
                        updated_structured["raw_typst_code"] = edited_typst
                        updated_structured["typst_version"] = new_ver
                        st.session_state[f"{session_prefix}_raw_typst_area_{new_ver}"] = edited_typst
                        
                        # Purge widget cache so Tab 2 instantly updates with the newly parsed data
                        _clear_studio_widget_keys(session_prefix)
                        
                        st.session_state[state_key] = updated_structured
                        st.session_state[feedback_key] = ("success", "💾 Raw Typst code compiled into PDF and all editor tabs synchronized successfully!")
                        st.rerun()
                except Exception as e:
                    st.error(f"Typst compilation error: {e}")
