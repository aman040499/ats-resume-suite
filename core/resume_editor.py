# -*- coding: utf-8 -*-
import os
import re
import json
import copy
from typing import Dict, Any, List, Optional, Tuple
import pypdfium2 as pdfium
from core.compiler import compile_tailored_pdf, compile_typst_source_to_pdf, generate_typst_source, extract_clean_url, format_category_title, sanitize_skills_dict
from core.gemini_client import call_gemini

def render_pdf_preview_images(pdf_path: str, output_dir: str = "output_resumes/previews") -> List[str]:
    """
    Renders all pages of a PDF file into high-resolution PNG images for instant UI display.
    """
    if not os.path.exists(pdf_path):
        return []

    os.makedirs(output_dir, exist_ok=True)
    base_name = os.path.splitext(os.path.basename(pdf_path))[0]
    preview_images = []

    try:
        pdf = pdfium.PdfDocument(pdf_path)
        for idx, page in enumerate(pdf):
            # scale=2.0 provides ~144 DPI for crystal clear text preview
            img = page.render(scale=2.0).to_pil()
            out_img_path = os.path.join(output_dir, f"{base_name}_p{idx+1}.png")
            img.save(out_img_path)
            preview_images.append(out_img_path)
    except Exception as e:
        print(f"[Resume Editor] Error rendering preview for {pdf_path}: {e}")

    return preview_images

def recompile_resume_data(resume_data: Dict[str, Any], output_pdf_path: str) -> Tuple[str, List[str]]:
    """
    Compiles structured resume data into PDF and generates rendered PNG preview images.
    Supports customizable spacing, font sizes, margins, and visibility toggles.
    Safely sanitizes inputs and handles any syntax edge cases.
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_pdf_path)), exist_ok=True)
    pers = resume_data.setdefault("personal", {})
    if "linkedin" in pers:
        pers["linkedin"] = extract_clean_url(pers["linkedin"])
    if "github" in pers:
        pers["github"] = extract_clean_url(pers["github"])

    # Always sanitize skills dictionary to prevent rogue asterisks or delimiters
    resume_data["skills"] = sanitize_skills_dict(resume_data.get("skills", {}))

    sep_edu = resume_data.get("separate_education_and_certs", True)
    try:
        compile_tailored_pdf(
            personal=pers,
            summary=resume_data.get("summary", ""),
            skills=resume_data.get("skills", {}),
            experience=resume_data.get("experience", []),
            education=resume_data.get("education", []),
            output_pdf_path=output_pdf_path,
            certifications=resume_data.get("certifications", []),
            achievements=resume_data.get("achievements", []),
            projects=resume_data.get("projects", []),
            section_spacing=resume_data.get("section_spacing", "0.35em"),
            font_size=resume_data.get("font_size", "9.1pt"),
            top_margin=resume_data.get("top_margin", "1.1cm"),
            bottom_margin=resume_data.get("bottom_margin", "1.1cm"),
            separate_education_and_certs=sep_edu,
            pagebreak_before_experience=resume_data.get("pagebreak_before_experience", False),
            pagebreak_before_projects=resume_data.get("pagebreak_before_projects", False),
            pagebreak_before_education=resume_data.get("pagebreak_before_education", False),
            pagebreak_before_certs=resume_data.get("pagebreak_before_certs", False),
            pagebreak_before_achievements=resume_data.get("pagebreak_before_achievements", False)
        )
    except Exception as e:
        print(f"[Resume Editor] Primary compilation note: {e}. Running sanitized fallback.")
        safe_summary = re.sub(r'#\w+[\(\[].*?[\)\]]', '', str(resume_data.get("summary", "")))
        safe_exp = copy.deepcopy(resume_data.get("experience", []))
        for r in safe_exp:
            r["bullets"] = [re.sub(r'#\w+[\(\[].*?[\)\]]', '', str(b)) for b in r.get("bullets", [])]
        compile_tailored_pdf(
            personal=pers,
            summary=safe_summary,
            skills=resume_data.get("skills", {}),
            experience=safe_exp,
            education=resume_data.get("education", []),
            output_pdf_path=output_pdf_path,
            certifications=resume_data.get("certifications", []),
            achievements=resume_data.get("achievements", []),
            projects=resume_data.get("projects", []),
            section_spacing=resume_data.get("section_spacing", "0.35em"),
            font_size=resume_data.get("font_size", "9.1pt"),
            top_margin=resume_data.get("top_margin", "1.1cm"),
            bottom_margin=resume_data.get("bottom_margin", "1.1cm"),
            separate_education_and_certs=sep_edu,
            pagebreak_before_experience=resume_data.get("pagebreak_before_experience", False),
            pagebreak_before_projects=resume_data.get("pagebreak_before_projects", False),
            pagebreak_before_education=resume_data.get("pagebreak_before_education", False),
            pagebreak_before_certs=resume_data.get("pagebreak_before_certs", False),
            pagebreak_before_achievements=resume_data.get("pagebreak_before_achievements", False)
        )

    preview_imgs = render_pdf_preview_images(output_pdf_path)
    return output_pdf_path, preview_imgs

def recompile_raw_typst(typst_source: str, output_pdf_path: str) -> Tuple[str, List[str]]:
    """
    Directly compiles raw Typst markup code and renders preview images.
    """
    compile_typst_source_to_pdf(typst_source, output_pdf_path)
    preview_imgs = render_pdf_preview_images(output_pdf_path)
    return output_pdf_path, preview_imgs

def apply_instruction_to_resume(
    resume_data: Dict[str, Any],
    instruction: str,
    api_key: Optional[str] = None
) -> Tuple[Dict[str, Any], str]:
    """
    Applies user natural-language instruction using Gemini LLM if available,
    or smart local deterministic rules as fallback.
    """
    clean_inst = (instruction or "").strip()
    if not clean_inst:
        return resume_data, "No instruction provided."

    data_copy = copy.deepcopy(resume_data)

    # 1. Try Gemini LLM if API key is present
    raw_key = api_key or ""
    key = str(raw_key).strip().strip('"').strip("'") if raw_key else ""
    if key:
        llm_success, updated_data, message = _apply_instruction_via_gemini(data_copy, clean_inst, key)
        if llm_success:
            return updated_data, message

    # 2. Fallback to smart local rule parser
    return _apply_instruction_locally(data_copy, clean_inst)

def _apply_instruction_via_gemini(
    resume_data: Dict[str, Any],
    instruction: str,
    api_key: str
) -> Tuple[bool, Dict[str, Any], str]:
    prompt = f"""
You are an expert resume editor and ATS specialist.
The user wants to make a modification to their tailored resume.

USER INSTRUCTION:
"{instruction}"

CURRENT RESUME DATA (JSON):
{json.dumps(resume_data, indent=2)}

CAPABILITIES & RULES:
1. Apply the user's requested change precisely. This includes:
   - Configuring links behind text: If the user asks to put a link behind "LinkedIn" or "GitHub", ensure the personal object has "show_linkedin": true, "linkedin_label": "LinkedIn" (or "show_github": true, "github_label": "GitHub") and the URL in "linkedin" or "github" is a pure URL string (e.g. "https://linkedin.com/in/..."). NEVER insert raw Typst #link() or markdown brackets into JSON string values!
   - Link Colors & Styling: If the user asks to change the link color (e.g. "make the text blue for LinkedIn and GitHub", "blue links", "change link color to #0A66C2", "green links", "black links"), set "link_color": "<hex_code_or_color>" in the personal object (e.g. "link_color": "#0A66C2"). If user asks to underline links, set "underline_links": true in the personal object.
   - Toggling link visibility: If the user asks to hide or not show GitHub (or LinkedIn, phone, email, location), set "show_github": false in the personal object.
   - Separating or combining Education & Certifications: If the user asks to separate Education and Certifications into distinct sections, set "separate_education_and_certs": true. If user asks to combine/merge them, set "separate_education_and_certs": false.
   - Removing "Key Achievements" or removing points underneath it (set "achievements": [] inside experience roles and clean any trailing "Key Achievements:" text from bullets).
   - Adding, removing, or modifying skills in technical skills.
   - Adjusting layout spacing (e.g. set "section_spacing": "0.55em" or "0.22em", "font_size": "9.1pt" or "8.9pt").
   - Rewriting, adding, or deleting experience bullets, or adding, editing, or deleting technical projects (each project in the "projects" list has "title": str, "technologies": str, "bullets": list[str]).
   - Updating header/contact details or education/certifications.
2. Preserve all unaffected sections and retain strict truthfulness.
3. Return STRICTLY a valid JSON object with two top-level keys:
   "updated_resume": <the complete updated resume JSON matching the original schema>,
   "explanation": "<one concise sentence explaining exactly what was changed>"
"""
    success, resp_text, model_or_err = call_gemini(api_key, prompt, json_mode=True)
    if success:
        try:
            parsed = json.loads(resp_text)
            if "updated_resume" in parsed and isinstance(parsed["updated_resume"], dict):
                upd = parsed["updated_resume"]
                if "personal" in upd and isinstance(upd["personal"], dict):
                    if "linkedin" in upd["personal"]:
                        upd["personal"]["linkedin"] = extract_clean_url(upd["personal"]["linkedin"])
                    if "github" in upd["personal"]:
                        upd["personal"]["github"] = extract_clean_url(upd["personal"]["github"])
                return True, upd, parsed.get("explanation", f"Applied change via {model_or_err}: {instruction}")
        except Exception as e:
            print(f"[Resume Editor] Failed to parse Gemini response: {e}")

    return False, resume_data, "LLM processing unavailable, falling back to local editor."

def _apply_instruction_locally(resume_data: Dict[str, Any], instruction: str) -> Tuple[Dict[str, Any], str]:
    """
    Smart local deterministic parser for common resume editing commands:
    - Putting clickable links behind 'LinkedIn' and 'GitHub'
    - Toggling visibility (showing/hiding GitHub, LinkedIn, etc.)
    - Removing 'Key Achievements' and points underneath it
    - Adding/removing skills
    - Spacing adjustments ('leave space', 'more space', 'compact')
    - Updating summary, bullets, contact details
    """
    inst_lower = instruction.lower().strip()
    pers = resume_data.setdefault("personal", {})

    # 0. LINK BEHIND TEXT & VISIBILITY TOGGLES
    if any(k in inst_lower for k in ["link behind linkedin", "linkedin link", "clickable linkedin", "link on linkedin", "behind linkedin"]):
        pers["show_linkedin"] = True
        pers["linkedin_label"] = "LinkedIn"
        url_m = re.search(r'(https?://[^\s,]+|linkedin\.com/[^\s,]+)', instruction, re.I)
        if url_m:
            pers["linkedin"] = extract_clean_url(url_m.group(1))
        elif not pers.get("linkedin"):
            pers["linkedin"] = "https://linkedin.com"
        else:
            pers["linkedin"] = extract_clean_url(pers["linkedin"])
        return resume_data, "Configured direct clickable link behind the word 'LinkedIn'."

    if any(k in inst_lower for k in ["dont show github", "don't show github", "dont need github", "dont need to show github", "hide github", "remove github", "no github"]):
        pers["show_github"] = False
        return resume_data, "Updated header: GitHub / Portfolio is now hidden from the resume."

    if any(k in inst_lower for k in ["show github", "link behind github", "github link", "clickable github", "behind github"]):
        pers["show_github"] = True
        pers["github_label"] = "GitHub"
        url_m = re.search(r'(https?://[^\s,]+|github\.com/[^\s,]+)', instruction, re.I)
        if url_m:
            pers["github"] = extract_clean_url(url_m.group(1))
        elif not pers.get("github"):
            pers["github"] = "https://github.com"
        else:
            pers["github"] = extract_clean_url(pers["github"])
        return resume_data, "Configured direct clickable link behind the word 'GitHub'."

    if any(k in inst_lower for k in ["dont show linkedin", "hide linkedin", "remove linkedin", "no linkedin"]):
        pers["show_linkedin"] = False
        return resume_data, "Updated header: LinkedIn is now hidden from the resume."

    # 0.1 LINK COLOR & UNDERLINE RULES
    if any(k in inst_lower for k in [
        "link color", "color of link", "color of the link", "links color",
        "make the text blue", "make link blue", "make links blue", "blue link", "blue for linkedin",
        "link blue", "links blue", "text blue for", "make text blue", "make linkedin blue", "make github blue",
        "make links green", "make links black", "make links teal", "underline link", "underline links"
    ]):
        if any(w in inst_lower for w in ["dont underline", "no underline", "remove underline"]):
            pers["underline_links"] = False
            return resume_data, "Removed underline from links."
        if "underline" in inst_lower:
            pers["underline_links"] = True

        hex_m = re.search(r'#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b', instruction)
        if hex_m:
            chosen_hex = f"#{hex_m.group(1)}"
            pers["link_color"] = chosen_hex
            return resume_data, f"Updated link text color to {chosen_hex}."

        if any(w in inst_lower for w in ["blue", "sky blue", "cyan"]):
            pers["link_color"] = "#0A66C2"
            return resume_data, "Updated link text color to Professional Blue (#0A66C2) for 'LinkedIn' and 'GitHub'."
        elif any(w in inst_lower for w in ["teal"]):
            pers["link_color"] = "#0F766E"
            return resume_data, "Updated link text color to Modern Teal (#0F766E)."
        elif any(w in inst_lower for w in ["green", "forest green"]):
            pers["link_color"] = "#3F7F4A"
            return resume_data, "Updated link text color to Forest Green (#3F7F4A)."
        elif any(w in inst_lower for w in ["black", "dark"]):
            pers["link_color"] = "#000000"
            return resume_data, "Updated link text color to Classic Black (#000000)."
        elif any(w in inst_lower for w in ["navy", "dark blue"]):
            pers["link_color"] = "#1E3A8A"
            return resume_data, "Updated link text color to Navy Blue (#1E3A8A)."
        else:
            pers["link_color"] = "#0A66C2"
            return resume_data, "Updated link text color to Professional Blue (#0A66C2)."

    # 1. SEPARATE OR COMBINE EDUCATION & CERTIFICATIONS
    if any(k in inst_lower for k in [
        "separate education and certification", "separate education and cert",
        "separate section education and cert", "separate sections education and cert",
        "separate sections 'education' and 'certifications'", "separate 'education' and 'certifications'",
        "split education and cert", "split education and certification",
        "distinct education and certification", "make certification a separate section",
        "make certifications separate", "separate certifications", "separate education"
    ]):
        resume_data["separate_education_and_certs"] = True
        return resume_data, "Separated 'Education' and 'Certifications & Licenses' into two distinct, industry-standard sections."

    if any(k in inst_lower for k in [
        "combine education and certification", "combine education and cert",
        "merge education and certification", "merge education and cert",
        "keep education and cert together", "single section for education"
    ]):
        resume_data["separate_education_and_certs"] = False
        return resume_data, "Combined Education and Certifications into a single unified section."

    # 2. REMOVE KEY ACHIEVEMENTS & POINTS
    if any(k in inst_lower for k in ["remove key achievement", "remove achievement", "delete key achievement", "delete achievement", "remove points underneath", "no key achievement", "clear achievement"]):
        exp = resume_data.get("experience", [])
        for role in exp:
            role["achievements"] = []
            cleaned_bullets = []
            for b in role.get("bullets", []):
                cb = re.sub(r"(?:[.:\s]+|^)Key Achievements:?\s*$", "", str(b), flags=re.IGNORECASE).strip()
                cb = re.sub(r"^Key Achievements:?\s*", "", cb, flags=re.IGNORECASE).strip()
                if cb:
                    cleaned_bullets.append(cb)
            role["bullets"] = cleaned_bullets
        resume_data["achievements"] = []
        return resume_data, "Removed 'Key Achievements' and all achievement bullet points from resume."

    # 2. SPACING & MARGIN INSTRUCTIONS
    if any(k in inst_lower for k in ["leave space", "add space", "more space", "increase space", "increase spacing"]):
        curr_spacing = resume_data.get("section_spacing", "0.35em")
        resume_data["section_spacing"] = "0.55em"
        return resume_data, "Increased vertical spacing between resume sections (0.55em)."

    if any(k in inst_lower for k in ["less space", "compact", "decrease space", "decrease spacing", "fit 1 page", "fit one page", "single page"]):
        resume_data["section_spacing"] = "0.22em"
        resume_data["font_size"] = "8.9pt"
        return resume_data, "Applied compact 1-page formatting (reduced section spacing to 0.22em and font to 8.9pt)."

    # 3. ADD SKILL(S)
    add_skill_match = re.search(r"(?:add|include|insert)\s+['\"]?([^'\".,]+)['\"]?\s+(?:in|to|into)\s+(?:the\s+)?(?:skills|technical\s+skills|skillset|tools)", inst_lower)
    if not add_skill_match:
        add_skill_match = re.search(r"^add\s+['\"]?([^'\".,]+)['\"]?\s+(?:to\s+)?(?:skills)?$", inst_lower)

    if add_skill_match or (inst_lower.startswith("add ") and "skill" in inst_lower):
        raw_items = add_skill_match.group(1) if add_skill_match else inst_lower.replace("add", "").replace("to skills", "").replace("in skills", "").strip()
        items_to_add = [i.strip().strip("'\"") for i in re.split(r"[,/&]| and ", raw_items) if i.strip()]
        
        skills = resume_data.setdefault("skills", {})
        target_cat = None
        for cat in skills.keys():
            cat_l = cat.lower()
            if any(term in cat_l for term in ["tool", "virtual", "cloud", "infra", "system", "technical", "other", "software"]):
                target_cat = cat
                break
        if not target_cat:
            target_cat = list(skills.keys())[0] if skills else "Technical Tools & Systems"
            if target_cat not in skills:
                skills[target_cat] = []

        added = []
        for item in items_to_add:
            display_item = orig_match.group(0) if orig_match else item.title()
            if display_item.upper() in ["AI", "IT", "AWS", "API", "LLM", "SQL", "ERP", "CRM", "CI/CD", "DNS", "DHCP", "VPN"]:
                display_item = display_item.upper()
            
            already = False
            for cat_name, sk_list in skills.items():
                if any(display_item.lower() == str(s).lower() for s in sk_list):
                    already = True
                    break
            if not already:
                skills[target_cat].append(display_item)
                added.append(display_item)

        if added:
            return resume_data, f"Added {', '.join(added)} to Technical Skills under '{target_cat}'."
        else:
            return resume_data, f"{', '.join(items_to_add)} is already present in Technical Skills."

    # 4. REMOVE SKILL(S)
    remove_skill_match = re.search(r"(?:remove|delete|drop)\s+['\"]?([^'\".,]+)['\"]?\s*(?:from\s+skills)?", inst_lower)
    if remove_skill_match and ("skill" in inst_lower or not any(k in inst_lower for k in ["bullet", "experience", "summary", "job", "achievement"])):
        target_skill = remove_skill_match.group(1).strip().strip("'\"")
        skills = resume_data.get("skills", {})
        removed = []
        for cat, sk_list in skills.items():
            to_keep = []
            for s in sk_list:
                if s.lower() == target_skill.lower() or target_skill.lower() in s.lower():
                    removed.append(s)
                else:
                    to_keep.append(s)
            skills[cat] = to_keep

        if removed:
            return resume_data, f"Removed {', '.join(removed)} from Technical Skills."
        else:
            return resume_data, f"Skill '{target_skill}' was not found in Technical Skills."

    # 5. PERSONAL / CONTACT INFO
    if "change email to" in inst_lower or "set email to" in inst_lower:
        email_match = re.search(r"(?:email to|email:)\s*([^\s,]+)", instruction, re.I)
        if email_match:
            resume_data.setdefault("personal", {})["email"] = email_match.group(1).strip()
            return resume_data, f"Updated candidate email to {email_match.group(1).strip()}."

    if "change phone to" in inst_lower or "set phone to" in inst_lower:
        phone_match = re.search(r"(?:phone to|phone:)\s*([^\s,]+)", instruction, re.I)
        if phone_match:
            resume_data.setdefault("personal", {})["phone"] = phone_match.group(1).strip()
            return resume_data, f"Updated candidate phone to {phone_match.group(1).strip()}."

    # 6. UPDATE SUMMARY
    if any(term in inst_lower for term in ["change summary to", "update summary to", "set summary to", "replace summary with"]):
        parts = re.split(r"(?:change|update|set|replace)\s+summary\s+(?:to|with)[:\s]*", instruction, flags=re.I)
        if len(parts) > 1 and parts[1].strip():
            new_summary = parts[1].strip().strip("'\"")
            resume_data["summary"] = new_summary
            return resume_data, "Updated Professional Executive Summary."

    # 7. ADD BULLET TO EXPERIENCE
    if "add bullet" in inst_lower or "add responsibility" in inst_lower:
        parts = re.split(r"add\s+(?:bullet|responsibility)(?:\s+to\s+experience)?[:\s]*", instruction, flags=re.I)
        if len(parts) > 1 and parts[1].strip():
            new_bullet = parts[1].strip().strip("'\"")
            exp = resume_data.get("experience", [])
            if exp:
                exp[0].setdefault("bullets", []).append(new_bullet)
                return resume_data, f"Added new bullet to {exp[0].get('title', 'Experience')}."

    # 8. CAPITALIZE AI OR RENAME SKILLS CATEGORY
    if any(k in inst_lower for k in ["capitalize ai", "ai in capital", "change ai to ai", "write ai in capital", "automation & ai", "both in capital", "ai both in capital", "ai capital"]):
        skills = resume_data.get("skills", {})
        new_skills = {}
        for cat, items in skills.items():
            fixed_cat = format_category_title(cat)
            new_skills[fixed_cat] = items
        resume_data["skills"] = new_skills
        return resume_data, "Capitalized 'AI' in technical skills categories."

    # 9. ADD / REMOVE PROJECTS
    if any(term in inst_lower for term in ["add 2 projects", "add two projects", "add 2 technical projects", "add two technical projects"]):
        projects = resume_data.setdefault("projects", [])
        projects.append({
            "title": "Cloud Infrastructure & CI/CD Automation Lab",
            "technologies": "Docker, Kubernetes, AWS, Terraform, GitHub Actions, Linux",
            "bullets": [
                "Engineered containerized microservices deployment pipeline utilizing Docker and Kubernetes clusters.",
                "Automated zero-downtime staging and production deployments through declarative GitHub Actions workflows."
            ]
        })
        projects.append({
            "title": "Enterprise Network Monitoring & Telemetry Dashboard",
            "technologies": "Python, Prometheus, Grafana, PowerShell, REST APIs",
            "bullets": [
                "Implemented real-time latency visualization telemetry and automated alerting across distributed infrastructure.",
                "Constructed unified metrics dashboards reducing mean incident detection time by 40%."
            ]
        })
        return resume_data, "Added 2 technical projects to the Projects section."

    if "add project" in inst_lower or "insert project" in inst_lower or "new project" in inst_lower:
        proj_match = re.search(r"(?:add|insert|new)\s+project\s*[:\-]?\s*([^,\n.]+)", instruction, re.I)
        p_title = proj_match.group(1).strip().strip("'\"") if proj_match else "Technical Implementation Project"
        p_tech = ""
        tech_m = re.search(r"(?:technologies|technology|tech|using|with|stack)[:\s]+([^,\n.]+)", instruction, re.I)
        if tech_m:
            p_tech = tech_m.group(1).strip().strip("'\"")
        resume_data.setdefault("projects", []).append({
            "title": p_title,
            "technologies": p_tech,
            "bullets": ["Designed, implemented, and tested production-ready technical solution aligning with industry best practices."]
        })
        return resume_data, f"Added technical project '{p_title}'."

    if any(k in inst_lower for k in ["remove all projects", "delete all projects", "clear projects", "remove projects", "no projects"]):
        resume_data["projects"] = []
        return resume_data, "Removed projects section from resume."

    # 10. PAGE BREAK / PUSH HEADING TO NEXT PAGE
    if any(k in inst_lower for k in ["push cert", "send cert", "pagebreak before cert", "page break before cert", "move cert to next page", "move cert", "push heading"]):
        if any(c in inst_lower for c in ["edu", "education"]):
            resume_data["pagebreak_before_education"] = True
            return resume_data, "Pushed Education section heading to the next page."
        elif any(c in inst_lower for c in ["proj", "project"]):
            resume_data["pagebreak_before_projects"] = True
            return resume_data, "Pushed Projects section heading to the next page."
        else:
            resume_data["pagebreak_before_certs"] = True
            return resume_data, "Pushed 'Certifications & Licenses' heading to the next page."

    if any(k in inst_lower for k in ["push education", "send education", "pagebreak before education", "page break before education"]):
        resume_data["pagebreak_before_education"] = True
        return resume_data, "Pushed Education section heading to the next page."

    if any(k in inst_lower for k in ["push project", "send project", "pagebreak before project", "page break before project"]):
        resume_data["pagebreak_before_projects"] = True
        return resume_data, "Pushed Projects section heading to the next page."

    return resume_data, f"Applied request: '{instruction}'. (For open-ended phrasing, provide Gemini API key in sidebar)."

def parse_typst_to_resume_dict(code: str, baseline: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Parses a Typst resume markup document back into a structured resume dictionary.
    Enables seamless, instant bi-directional synchronization between the Raw Typst
    Source Editor and the Direct In-Resume Editor.
    """
    res = copy.deepcopy(baseline) if baseline else {}

    # 1. Typography, Spacing, and Margins
    size_m = re.search(r'#set\s+text\([^)]*size:\s*([0-9.]+pt)', code)
    if size_m:
        res["font_size"] = size_m.group(1)
        
    spacing_m = re.search(r'#v\(([0-9.]+em)\)\s*\n#text\([^\[\]]*\)\[', code)
    if spacing_m:
        res["section_spacing"] = spacing_m.group(1)

    top_m = re.search(r'top:\s*([0-9.]+(?:cm|mm|pt|in))', code)
    bot_m = re.search(r'bottom:\s*([0-9.]+(?:cm|mm|pt|in))', code)
    if top_m:
        res["top_margin"] = top_m.group(1)
    if bot_m:
        res["bottom_margin"] = bot_m.group(1)

    # 2. Personal & Header Information
    pers = copy.deepcopy(res.get("personal", {}))
    name_m = re.search(r'#text\(\s*16pt,\s*weight:\s*"bold"\)\s*\[(.*?)\]', code)
    if name_m:
        pers["name"] = name_m.group(1).strip()
    
    email_m = re.search(r'Email:\s*([a-zA-Z0-9._%+-]+(?:\\@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}|@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}))', code)
    if not email_m:
        email_m = re.search(r'Email:\s*([^\s|\\\]]+)', code)
    if email_m:
        pers["email"] = email_m.group(1).replace(r"\@", "@").strip()
        pers["show_email"] = True
        
    phone_m = re.search(r'Mobile:\s*([^|\\\n]+)', code)
    if phone_m:
        pers["phone"] = phone_m.group(1).strip()
        pers["show_phone"] = True
        
    loc_m = re.search(r'Mobile:[^|\\\n]+\|\s*([^\\\n]+)', code)
    if loc_m:
        pers["location"] = loc_m.group(1).strip()
        pers["show_location"] = True
        
    li_m = re.search(r'#link\("([^"]+)"\)\[(?:(?!#link).)*?LinkedIn.*?\]', code, re.DOTALL | re.I)
    if li_m:
        pers["linkedin"] = extract_clean_url(li_m.group(1).strip())
        pers["show_linkedin"] = True
    elif "LinkedIn" not in code:
        pers["show_linkedin"] = False
        
    gh_m = re.search(r'#link\("([^"]+)"\)\[(?:(?!#link).)*?GitHub.*?\]', code, re.DOTALL | re.I)
    if gh_m:
        pers["github"] = extract_clean_url(gh_m.group(1).strip())
        pers["show_github"] = True
    elif "GitHub" not in code:
        pers["show_github"] = False
        
    color_m = re.search(r'fill:\s*rgb\("([^"]+)"\)', code)
    if color_m:
        pers["link_color"] = color_m.group(1).strip()
        
    if "#underline[" in code:
        pers["underline_links"] = True
        
    res["personal"] = pers

    # 3. Section Slicing via Regex Headings
    sections = {}
    pattern = r'#text\([^\[\]]*\)\[([A-Z\s&—\-/]{3,})\]'
    matches = list(re.finditer(pattern, code))
    
    for i, m in enumerate(matches):
        heading = m.group(1).strip()
        start = m.end()
        end = matches[i+1].start() if i + 1 < len(matches) else len(code)

        # Check if pagebreak preceded this heading
        prev_end = matches[i-1].end() if i > 0 else 0
        pre_text = code[prev_end:m.start()]
        if "#pagebreak()" in pre_text:
            if heading in ["PROFESSIONAL EXPERIENCE", "EXPERIENCE"]:
                res["pagebreak_before_experience"] = True
            elif heading in ["PROJECTS", "PROJECT", "TECHNICAL PROJECTS"]:
                res["pagebreak_before_projects"] = True
            elif heading in ["EDUCATION", "EDUCATION & CERTIFICATIONS"]:
                res["pagebreak_before_education"] = True
            elif heading in ["CERTIFICATIONS & LICENSES", "CERTIFICATIONS"]:
                res["pagebreak_before_certs"] = True
            elif heading in ["KEY HONORS & PROFESSIONAL RECOGNITION", "ACHIEVEMENTS"]:
                res["pagebreak_before_achievements"] = True

        body = code[start:end].strip()
        body = re.sub(r'#block\s*\([^)]*\)\s*\[\s*', '', body)
        body = re.sub(r'^\s*\]\s*$', '', body, flags=re.MULTILINE)
        body = re.sub(r'\]\s*$', '', body)
        body = re.sub(r'(?:#v\([^)]*\)|#pagebreak\(\)|\s)+$', '', body).strip()
        sections[heading] = body

    # 4. Summary
    for h in ["PROFESSIONAL SUMMARY", "EXECUTIVE SUMMARY", "SUMMARY", "PROFESSIONAL EXECUTIVE SUMMARY"]:
        if h in sections:
            clean_summary = re.sub(r'#v\([^)]*\)', '', sections[h]).strip()
            clean_summary = re.sub(r'^\s*\\\s*', '', clean_summary)
            if clean_summary:
                res["summary"] = clean_summary
            break

    # 5. Technical Skills
    for h in ["TECHNICAL SKILLS", "SKILLS"]:
        if h in sections:
            skills_dict = {}
            current_cat = None
            for line in sections[h].splitlines():
                line = line.strip()
                if not line or line.startswith("#") or line.startswith("]"):
                    continue
                # Line starting with *Category Name:*
                m = re.match(r'^\*([^*:\n]+):\*\s*(.*)', line)
                if m:
                    current_cat = re.sub(r'[*\\\n\r]', '', m.group(1)).strip()
                    raw_items = m.group(2).rstrip('\\').strip()
                    items = [
                        re.sub(r'[*\\\n\r]', '', it).strip()
                        for it in re.split(r'[,•]\s*', raw_items)
                        if re.sub(r'[*\\\n\r]', '', it).strip()
                        and not it.strip().startswith("#")
                        and not it.strip().startswith("]")
                    ]
                    if current_cat:
                        skills_dict[current_cat] = items
                elif current_cat and line:
                    if not line.startswith("#") and not line.startswith("]"):
                        raw_items = line.rstrip('\\').strip()
                        extra_items = [
                            re.sub(r'[*\\\n\r]', '', it).strip()
                            for it in re.split(r'[,•]\s*', raw_items)
                            if re.sub(r'[*\\\n\r]', '', it).strip()
                            and not it.strip().startswith("#")
                            and not it.strip().startswith("]")
                        ]
                        if extra_items:
                            skills_dict[current_cat].extend(extra_items)
            if skills_dict:
                res["skills"] = sanitize_skills_dict(skills_dict)
            break

    # 6. Professional Experience
    for h in ["PROFESSIONAL EXPERIENCE", "EXPERIENCE"]:
        if h in sections:
            exp_list = []
            exp_body = sections[h]
            role_blocks = re.split(r'(?:^|\n)\s*(?=\*[^*]+\*)', exp_body.strip())
            for rb in role_blocks:
                rb = rb.strip()
                header_m = re.search(r'^\*([^*]+)\*(?:\s*—\s*([^\n\\]+))?', rb)
                if not header_m:
                    continue
                title = header_m.group(1).strip()
                company = header_m.group(2).strip() if header_m.group(2) else ""
                
                meta_m = re.search(r'#text\([^\[\]]*\)\[(.*?)\]', rb)
                meta_str = meta_m.group(1).strip() if meta_m else ""
                dates = ""
                loc = ""
                if "|" in meta_str:
                    dates, loc = [p.strip() for p in meta_str.split("|", 1)]
                else:
                    dates = meta_str
                    
                bullets = []
                achs = []
                is_ach = False
                for line in rb.splitlines():
                    line = line.strip()
                    if "Key Achievements" in line:
                        is_ach = True
                        continue
                    if line.startswith("- "):
                        b_text = re.sub(r'^- \s*', '', line).strip()
                        b_text = re.sub(r'#text\(style:\s*"italic"\)\[(.*?)\]', r'\1', b_text)
                        b_text = re.sub(r'\]$', '', b_text).strip()
                        if is_ach:
                            achs.append(b_text)
                        else:
                            bullets.append(b_text)
                
                exp_list.append({
                    "title": title,
                    "company": company,
                    "dates": dates,
                    "location": loc,
                    "bullets": bullets,
                    "achievements": achs
                })
            if exp_list:
                res["experience"] = exp_list
            break

    # 7. Projects (Multi-Project Support)
    for h in ["PROJECTS", "PROJECT", "TECHNICAL PROJECTS"]:
        if h in sections:
            proj_list = []
            proj_body = sections[h]
            p_blocks = re.split(r'(?:^|\n)\s*(?=\*[^*]+\*)', proj_body.strip())
            for pb in p_blocks:
                pb = pb.strip()
                p_header_m = re.search(r'^\*([^*]+)\*', pb)
                if not p_header_m:
                    continue
                p_title = p_header_m.group(1).strip()
                
                tech_m = re.search(r'#text\([^)]*italic[^)]*\)\[(?:Technologies:\s*)?(.*?)\]', pb)
                p_tech = tech_m.group(1).strip() if tech_m else ""
                
                p_bullets = []
                for line in pb.splitlines():
                    line = line.strip()
                    if line.startswith("- "):
                        clean_b = re.sub(r'^- \s*', '', line).strip()
                        clean_b = re.sub(r'\]$', '', clean_b).strip()
                        if clean_b:
                            p_bullets.append(clean_b)
                        
                if p_title or p_bullets:
                    proj_list.append({
                        "title": p_title,
                        "technologies": p_tech,
                        "bullets": p_bullets
                    })
            if proj_list:
                res["projects"] = proj_list
            break

    # 8. Education
    for h in ["EDUCATION", "EDUCATION & CERTIFICATIONS"]:
        if h in sections:
            edu_list = []
            edu_body = sections[h]
            e_blocks = re.split(r'(?:^|\n)\s*(?=\*[^*]+\*)', edu_body.strip())
            for eb in e_blocks:
                eb = eb.strip()
                e_header_m = re.match(r'^\*([^*]+)\*(?:\s*—\s*([^|\n\\]+))?(?:\s*\|\s*([^\n\\]+))?', eb)
                if not e_header_m:
                    continue
                inst = e_header_m.group(1).strip()
                deg = e_header_m.group(2).strip() if e_header_m.group(2) else ""
                yr = e_header_m.group(3).strip() if e_header_m.group(3) else ""
                
                det_m = re.search(r'#text\([^\[\]]*\)\[(.*?)\]', eb)
                details = det_m.group(1).strip() if det_m else ""
                
                if inst or deg:
                    edu_list.append({
                        "institution": inst,
                        "degree": deg,
                        "year": yr,
                        "details": details
                    })
            if edu_list:
                res["education"] = edu_list
            break

    # 9. Certifications
    for h in ["CERTIFICATIONS & LICENSES", "CERTIFICATIONS"]:
        if h in sections:
            cert_list = []
            for line in sections[h].splitlines():
                line = line.strip()
                if line.startswith("- "):
                    clean_c = re.sub(r'^- \s*', '', line).strip()
                    clean_c = re.sub(r'\]$', '', clean_c).strip()
                    if clean_c:
                        cert_list.append(clean_c)
            if cert_list:
                res["certifications"] = cert_list
            res["separate_education_and_certs"] = True
            break

    return res

