# -*- coding: utf-8 -*-
import os
import re
from typing import Dict, Any, List, Optional
import typst

def escape_typst(text: str) -> str:
    """Escapes special Typst markup characters and protects delimiters from premature closing."""
    if not text:
        return ""
    res = str(text)
    res = res.replace(r"\@", "__AT_PLACEHOLDER__")
    res = res.replace(r"\#", "__HASH_PLACEHOLDER__")
    res = res.replace(r"\$", "__DOLLAR_PLACEHOLDER__")
    res = res.replace(r"\[", "__OBRACK_PLACEHOLDER__")
    res = res.replace(r"\]", "__CBRACK_PLACEHOLDER__")
    res = res.replace(r"\*", "__STAR_PLACEHOLDER__")
    
    # Escape literal backslashes so paths or AD domain\user don't break Typst
    res = res.replace("\\", "\\\\")
    
    # Escape special typst syntax characters
    for c in ["#", "$", "@", "<", ">", "[", "]", "*"]:
        res = res.replace(c, f"\\{c}")
        
    res = res.replace("__AT_PLACEHOLDER__", r"\@")
    res = res.replace("__HASH_PLACEHOLDER__", r"\#")
    res = res.replace("__DOLLAR_PLACEHOLDER__", r"\$")
    res = res.replace("__OBRACK_PLACEHOLDER__", r"\[")
    res = res.replace("__CBRACK_PLACEHOLDER__", r"\]")
    res = res.replace("__STAR_PLACEHOLDER__", r"\*")
    return res

def sanitize_skills_dict(skills: Dict[str, Any]) -> Dict[str, Any]:
    """
    Sanitizes and auto-repairs skills dictionary:
    - Strips rogue asterisks, backslashes, and newlines from category names.
    - If a category key was merged/corrupted by previous text processing, splits and recovers original categories.
    - Ensures clean string lists for all categories.
    """
    if not isinstance(skills, dict):
        return {}
    clean_skills = {}
    for raw_cat, raw_items in skills.items():
        cat_str = str(raw_cat).strip()
        if "*" in cat_str or "\\" in cat_str or "\n" in cat_str:
            full_text = f"*{cat_str}:* " + ", ".join(str(i) for i in (raw_items if isinstance(raw_items, list) else [raw_items]))
            cat_chunks = re.split(r'(?:^|\n|\\)\s*(?=\*[^*:\n]+:\*)', full_text)
            for chunk in cat_chunks:
                chunk = chunk.strip()
                m = re.match(r'^\*([^*:\n]+):\*\s*(.*)', chunk, re.DOTALL)
                if m:
                    c_name = re.sub(r'[*\\\n\r]', '', m.group(1)).strip()
                    c_items_raw = m.group(2).replace('\\', '').replace('*', '').strip()
                    c_items = [re.sub(r'[*\\\n\r]', '', it).strip() for it in re.split(r'[,•]\s*', c_items_raw) if re.sub(r'[*\\\n\r]', '', it).strip()]
                    if c_name and c_items:
                        clean_skills[format_category_title(c_name)] = c_items
                else:
                    items_raw = chunk.replace('\\', '').replace('*', '').strip()
                    items = [re.sub(r'[*\\\n\r]', '', it).strip() for it in re.split(r'[,•]\s*', items_raw) if re.sub(r'[*\\\n\r]', '', it).strip()]
                    if items:
                        if any("TCP" in it or "DNS" in it or "DHCP" in it or "Network" in it for it in items):
                            recovered_name = "Networking, Security & Automation"
                        else:
                            recovered_name = "Technical Skills"
                        clean_skills[recovered_name] = items
        else:
            clean_name = re.sub(r'[*\\\n\r]', '', cat_str).strip()
            if clean_name and not clean_name.startswith("#") and not clean_name.startswith("]"):
                items_list = raw_items if isinstance(raw_items, list) else [raw_items]
                clean_items = [
                    re.sub(r'[*\\\n\r]', '', str(it)).strip()
                    for it in items_list
                    if re.sub(r'[*\\\n\r]', '', str(it)).strip()
                    and not str(it).strip().startswith("#")
                    and not str(it).strip().startswith("]")
                ]
                if clean_items:
                    clean_skills[format_category_title(clean_name)] = clean_items
    return clean_skills

def extract_clean_url(raw_val: str) -> str:
    """Extracts and sanitizes pure URL from plain text, markdown, typst, or HTML."""
    if not raw_val:
        return ""
    s = str(raw_val).strip()
    m_md = re.search(r'\[.*?\]\((https?://[^\s\)]+|[^\s\)]+)\)', s)
    if m_md:
        s = m_md.group(1)
    m_typ = re.search(r'#link\([\"\'](.*?)[\"\']\)', s)
    if m_typ:
        s = m_typ.group(1)
    m_href = re.search(r'href=[\"\'](.*?)[\"\']', s)
    if m_href:
        s = m_href.group(1)
    s = s.strip('"\'<>[]() ')
    s = s.replace('"', '').replace("'", "")
    if s and not s.startswith(("http://", "https://")):
        s = f"https://{s}"
    return s

def format_typst_color(col: Optional[str]) -> str:
    """Sanitizes color names or hex strings into Typst rgb(...) representation."""
    if not col:
        return 'rgb("#0A66C2")'
    c = str(col).strip().lower()
    color_map = {
        "blue": "#0A66C2",
        "professional blue": "#0A66C2",
        "linkedin blue": "#0A66C2",
        "github blue": "#0969DA",
        "sky blue": "#0284C7",
        "royal blue": "#1D4ED8",
        "navy": "#1E3A8A",
        "teal": "#0F766E",
        "green": "#3F7F4A",
        "forest green": "#3F7F4A",
        "black": "#000000",
        "dark slate": "#334155",
        "slate": "#475569",
        "gray": "#4B5563"
    }
    if c in color_map:
        return f'rgb("{color_map[c]}")'
    if c.startswith("#"):
        clean_hex = c.strip("#").upper()
        if len(clean_hex) in [3, 6, 8]:
            return f'rgb("#{clean_hex}")'
    elif re.match(r'^[0-9a-fA-F]{6}$', c):
        return f'rgb("#{c.upper()}")'
    return 'rgb("#0A66C2")'

def format_category_title(cat: str) -> str:
    """
    Intelligently formats category names while preserving exact acronyms and casing:
    - 'AI' -> 'AI', 'IT' -> 'IT', 'API' -> 'API', 'AWS' -> 'AWS', etc.
    - If user wrote all-caps words (e.g. 'AI', 'ERP', 'CI/CD'), preserve them!
    - Only convert snake_case or all-lowercase words to Title Case.
    """
    if not cat:
        return ""
    
    KNOWN_ACRONYMS = {
        "AI": "AI",
        "IT": "IT",
        "API": "API",
        "APIS": "APIs",
        "LLM": "LLM",
        "LLMS": "LLMs",
        "AWS": "AWS",
        "GCP": "GCP",
        "IAM": "IAM",
        "SQL": "SQL",
        "ERP": "ERP",
        "CRM": "CRM",
        "CI/CD": "CI/CD",
        "CICD": "CI/CD",
        "OS": "OS",
        "UI": "UI",
        "UX": "UX",
        "UI/UX": "UI/UX",
        "AD": "AD",
        "DNS": "DNS",
        "DHCP": "DHCP",
        "VPN": "VPN",
        "REST": "REST",
        "JSON": "JSON",
        "XML": "XML",
        "LAN": "LAN",
        "WAN": "WAN",
        "ITSM": "ITSM",
        "ITIL": "ITIL",
        "ETL": "ETL",
        "BI": "BI",
        "ML": "ML",
        "SAAS": "SaaS",
        "PAAS": "PaaS",
        "IAAS": "IaaS",
        "DEVOPS": "DevOps",
        "M365": "M365",
        "O365": "O365",
        "SCCM": "SCCM",
        "MDM": "MDM"
    }

    raw = str(cat).replace("_", " ").strip()
    words = raw.split()
    formatted_words = []
    
    for i, w in enumerate(words):
        clean_w = re.sub(r'^[^\w]+|[^\w]+$', '', w.upper())
        if clean_w in KNOWN_ACRONYMS:
            target_acronym = KNOWN_ACRONYMS[clean_w]
            formatted_w = re.sub(rf'\b{re.escape(clean_w)}\b', target_acronym, w, flags=re.IGNORECASE)
            formatted_words.append(formatted_w)
        elif w.isupper() and len(w) > 1:
            formatted_words.append(w)
        elif any(c.isupper() for c in w[1:]):
            formatted_words.append(w)
        else:
            if w.lower() in ["and", "&", "of", "for", "in", "to", "with"] and i > 0:
                formatted_words.append("&" if w in ["and", "&"] else w.lower())
            else:
                formatted_words.append(w.capitalize())

    return " ".join(formatted_words)

def compile_tailored_pdf(
    personal: Dict[str, Any],
    summary: str,
    skills: Dict[str, Any],
    experience: list,
    education: list,
    output_pdf_path: str,
    certifications: Optional[list] = None,
    achievements: Optional[list] = None,
    projects: Optional[list] = None,
    section_spacing: str = "0.35em",
    font_size: str = "9.1pt",
    top_margin: str = "1.1cm",
    bottom_margin: str = "1.1cm",
    separate_education_and_certs: bool = True,
    pagebreak_before_experience: bool = False,
    pagebreak_before_projects: bool = False,
    pagebreak_before_education: bool = False,
    pagebreak_before_certs: bool = False,
    pagebreak_before_achievements: bool = False
) -> str:
    """
    Compiles structured resume data into an ATS-compliant, beautifully formatted PDF
    matching the modern, high-appeal visual layout of the candidate's original resume.
    Preserves exact job titles, dates, companies, education concentrations, and projects.
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_pdf_path)), exist_ok=True)
    typ_source_path = output_pdf_path.replace(".pdf", ".typ")

    typst_doc = generate_typst_source(
        personal=personal,
        summary=summary,
        skills=skills,
        experience=experience,
        education=education,
        certifications=certifications,
        achievements=achievements,
        projects=projects,
        section_spacing=section_spacing,
        font_size=font_size,
        top_margin=top_margin,
        bottom_margin=bottom_margin,
        separate_education_and_certs=separate_education_and_certs,
        pagebreak_before_experience=pagebreak_before_experience,
        pagebreak_before_projects=pagebreak_before_projects,
        pagebreak_before_education=pagebreak_before_education,
        pagebreak_before_certs=pagebreak_before_certs,
        pagebreak_before_achievements=pagebreak_before_achievements
    )

    with open(typ_source_path, "w", encoding="utf-8") as f:
        f.write(typst_doc)

    typst.compile(typ_source_path, output=output_pdf_path)
    return output_pdf_path

def compile_typst_source_to_pdf(typst_source: str, output_pdf_path: str) -> str:
    """
    Directly compiles raw Typst markup code into a PDF file.
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_pdf_path)), exist_ok=True)
    typ_source_path = output_pdf_path.replace(".pdf", ".typ")
    with open(typ_source_path, "w", encoding="utf-8") as f:
        f.write(typst_source)
    typst.compile(typ_source_path, output=output_pdf_path)
    return output_pdf_path

def generate_typst_source(
    personal: Dict[str, Any],
    summary: str,
    skills: Dict[str, Any],
    experience: list,
    education: list,
    certifications: Optional[list] = None,
    achievements: Optional[list] = None,
    projects: Optional[list] = None,
    section_spacing: str = "0.35em",
    font_size: str = "9.1pt",
    top_margin: str = "1.1cm",
    bottom_margin: str = "1.1cm",
    separate_education_and_certs: bool = True,
    pagebreak_before_experience: bool = False,
    pagebreak_before_projects: bool = False,
    pagebreak_before_education: bool = False,
    pagebreak_before_certs: bool = False,
    pagebreak_before_achievements: bool = False
) -> str:
    pb_exp = pagebreak_before_experience or personal.get("pagebreak_before_experience", False)
    pb_proj = pagebreak_before_projects or personal.get("pagebreak_before_projects", False)
    pb_edu = pagebreak_before_education or personal.get("pagebreak_before_education", False)
    pb_certs = pagebreak_before_certs or personal.get("pagebreak_before_certs", False)
    pb_ach = pagebreak_before_achievements or personal.get("pagebreak_before_achievements", False)

    name = escape_typst(personal.get("name", "Candidate"))
    email = escape_typst(personal.get("email", ""))
    phone = escape_typst(personal.get("phone", ""))
    location = escape_typst(personal.get("location", ""))
    linkedin = personal.get("linkedin", "")
    github = personal.get("github", "")

    show_email = personal.get("show_email", True)
    show_phone = personal.get("show_phone", True)
    show_location = personal.get("show_location", True)
    show_linkedin = personal.get("show_linkedin", True)
    show_github = personal.get("show_github", True)
    linkedin_label = escape_typst(personal.get("linkedin_label", "LinkedIn") or "LinkedIn")
    github_label = escape_typst(personal.get("github_label", "GitHub") or "GitHub")

    contact_line_1_parts = []
    if email and show_email:
        contact_line_1_parts.append(f"Email: {email}")
    if phone and show_phone:
        contact_line_1_parts.append(f"Mobile: {phone}")
    if location and show_location:
        contact_line_1_parts.append(location)

    link_color = personal.get("link_color", "#0A66C2")
    underline_links = personal.get("underline_links", False)
    typst_link_color = format_typst_color(link_color)

    contact_line_2_parts = []
    clean_li = extract_clean_url(linkedin)
    if clean_li and show_linkedin:
        inner_li = f'#text(fill: {typst_link_color})[{linkedin_label}]'
        if underline_links:
            inner_li = f'#underline[{inner_li}]'
        contact_line_2_parts.append(f'#link("{clean_li}")[{inner_li}]')

    clean_gh = extract_clean_url(github)
    if clean_gh and show_github:
        inner_gh = f'#text(fill: {typst_link_color})[{github_label}]'
        if underline_links:
            inner_gh = f'#underline[{inner_gh}]'
        contact_line_2_parts.append(f'#link("{clean_gh}")[{inner_gh}]')

    contact_block = ""
    if contact_line_1_parts:
        contact_block += " | ".join(contact_line_1_parts)
    if contact_line_2_parts:
        if contact_block:
            contact_block += " \\\n  #v(-0.55em)\n  "
        contact_block += " | ".join(contact_line_2_parts)

    typst_doc = f"""
#set page(paper: "a4", margin: (x: 1.1cm, top: {top_margin}, bottom: {bottom_margin}))
#set text(font: "Liberation Sans", size: {font_size})
#set par(justify: false, leading: 0.52em)

#align(center)[
  #text(16pt, weight: "bold")[{name}] \\
  #v(-0.45em)
  #text(8.8pt)[{contact_block}]
]
"""

    # 1. Professional Summary
    if summary:
        typst_doc += f"""
#v({section_spacing})
#text(10.5pt, weight: "bold", fill: rgb("3F7F4A"))[PROFESSIONAL SUMMARY]
#v(-{section_spacing})
{escape_typst(summary.strip())}
"""

    # 2. Technical Skills
    clean_skills = sanitize_skills_dict(skills)
    if clean_skills:
        typst_doc += f"""
#v({section_spacing})
#text(10.5pt, weight: "bold", fill: rgb("3F7F4A"))[TECHNICAL SKILLS]
#v(-{section_spacing})
"""
        for cat, items in clean_skills.items():
            if not items:
                continue
            safe_cat = re.sub(r'[*\\\n\r]', '', str(cat)).strip()
            cat_name = escape_typst(format_category_title(safe_cat))
            items_str = escape_typst(", ".join([re.sub(r'[*\\\n\r]', '', str(i)).strip() for i in items if str(i).strip()]))
            typst_doc += f"*{cat_name}:* {items_str} \\\n"

    # 3. Professional Experience
    if experience:
        if pb_exp:
            typst_doc += "\n#pagebreak()\n"
        
        # Unbreakable guard: bind heading + first role header + first bullet
        # so heading is never stranded alone at the bottom of a page
        first_exp = experience[0]
        f_title = escape_typst(first_exp.get("title", ""))
        f_company = escape_typst(first_exp.get("company", ""))
        f_dates = escape_typst(str(first_exp.get("dates", "")))
        f_loc = escape_typst(first_exp.get("location", ""))
        f_meta = " | ".join(p for p in [f_dates, f_loc] if p)
        f_header = f"*{f_title}*"
        if f_company:
            f_header += f" — {f_company}"

        f_bullets = first_exp.get("bullets", [])
        first_role_achs = list(first_exp.get("achievements", []))
        typst_doc += f"""
#block(breakable: true)[
#v({section_spacing})
#text(10.5pt, weight: "bold", fill: rgb("3F7F4A"))[PROFESSIONAL EXPERIENCE]
#v(-{section_spacing})
{f_header} \\
#v(-0.55em)
#text(8.6pt, fill: rgb("444444"))[{f_meta}]
#v(-0.2em)
"""
        for bullet in f_bullets:
            b_str = str(bullet).strip()
            if re.search(r'(?:Key\s+Achievements?|Key\s+Accomplishments?|Achievements?):?', b_str, flags=re.IGNORECASE):
                parts = re.split(r'(?:Key\s+Achievements?|Key\s+Accomplishments?|Achievements?):?', b_str, flags=re.IGNORECASE)
                clean_bullet = parts[0].strip()
                if len(parts) > 1 and parts[1].strip():
                    inline_ach = parts[1].strip('•*-· \t')
                    if inline_ach:
                        first_role_achs.append(inline_ach)
            else:
                clean_bullet = b_str

            clean_bullet = re.sub(r"^[-•*·\s]+", "", clean_bullet).strip()
            clean_bullet = re.sub(r"[:\s\-]+$", "", clean_bullet).strip()
            if clean_bullet:
                if not clean_bullet.endswith((".", "!", "?")):
                    clean_bullet += "."
                typst_doc += f"- {escape_typst(clean_bullet)}\n"

        if first_role_achs:
            valid_achs = [str(a).strip() for a in first_role_achs if str(a).strip()]
            if valid_achs:
                typst_doc += "\n#v(0.15em)\n*Key Achievements:* \\\n#v(-0.4em)\n"
                for ach in valid_achs:
                    clean_ach = re.sub(r"^[-•*·\s]+", "", ach).strip()
                    clean_ach = re.sub(r"^(?:Key\s+Achievements?|Key\s+Accomplishments?|Achievements?):?\s*", "", clean_ach, flags=re.IGNORECASE).strip()
                    if clean_ach:
                        typst_doc += f"- #text(style: \"italic\")[{escape_typst(clean_ach)}]\n"
        typst_doc += "]\n"

        # Subsequent roles in experience
        for exp in experience[1:]:
            title = escape_typst(exp.get("title", ""))
            company = escape_typst(exp.get("company", ""))
            dates = escape_typst(str(exp.get("dates", "")))
            loc = escape_typst(exp.get("location", ""))
            meta_parts = [p for p in [dates, loc] if p]
            sub_meta = " | ".join(meta_parts)

            header_text = f"*{title}*"
            if company:
                header_text += f" — {company}"

            typst_doc += f"""
#v(0.25em)
#block(breakable: true)[
{header_text} \\
#v(-0.55em)
#text(8.6pt, fill: rgb("444444"))[{sub_meta}]
#v(-0.2em)
"""
            role_achs = list(exp.get("achievements", []))
            for bullet in exp.get("bullets", []):
                b_str = str(bullet).strip()
                if re.search(r'(?:Key\s+Achievements?|Key\s+Accomplishments?|Achievements?):?', b_str, flags=re.IGNORECASE):
                    parts = re.split(r'(?:Key\s+Achievements?|Key\s+Accomplishments?|Achievements?):?', b_str, flags=re.IGNORECASE)
                    clean_bullet = parts[0].strip()
                    if len(parts) > 1 and parts[1].strip():
                        inline_ach = parts[1].strip('•*-· \t')
                        if inline_ach:
                            role_achs.append(inline_ach)
                else:
                    clean_bullet = b_str

                clean_bullet = re.sub(r"^[-•*·\s]+", "", clean_bullet).strip()
                clean_bullet = re.sub(r"[:\s\-]+$", "", clean_bullet).strip()
                if clean_bullet:
                    if not clean_bullet.endswith((".", "!", "?")):
                        clean_bullet += "."
                    typst_doc += f"- {escape_typst(clean_bullet)}\n"

            if role_achs:
                valid_achs = [str(a).strip() for a in role_achs if str(a).strip()]
                if valid_achs:
                    typst_doc += "\n#v(0.15em)\n*Key Achievements:* \\\n#v(-0.4em)\n"
                    for ach in valid_achs:
                        clean_ach = re.sub(r"^[-•*·\s]+", "", ach).strip()
                        clean_ach = re.sub(r"^(?:Key\s+Achievements?|Key\s+Accomplishments?|Achievements?):?\s*", "", clean_ach, flags=re.IGNORECASE).strip()
                        if clean_ach:
                            typst_doc += f"- #text(style: \"italic\")[{escape_typst(clean_ach)}]\n"
            typst_doc += "]\n"

    # 4. Project Section
    clean_projects = []
    for proj in (projects or []):
        if not isinstance(proj, dict):
            continue
        p_title = proj.get("title", "").strip()
        p_tech = proj.get("technologies", "").strip()
        raw_b = proj.get("bullets", [])
        p_bullets = [re.sub(r"^[-•*·\s]+", "", str(b)).strip() for b in raw_b if str(b).strip()]
        if p_title or p_bullets:
            clean_projects.append({
                "title": p_title,
                "technologies": p_tech,
                "bullets": p_bullets
            })

    if clean_projects:
        if pb_proj:
            typst_doc += "\n#pagebreak()\n"
        proj_heading = "PROJECTS" if len(clean_projects) > 1 else "PROJECT"

        # Unified block for first project: binds heading, tech stack, and all bullets
        first_proj = clean_projects[0]
        p_title = escape_typst(first_proj["title"])
        p_tech = escape_typst(first_proj["technologies"])
        clean_tech = p_tech
        if clean_tech and not clean_tech.lower().startswith("technologies:"):
            clean_tech = f"Technologies: {clean_tech}"

        first_p_bullets = first_proj["bullets"]

        typst_doc += f"""
#block(breakable: true)[
#v({section_spacing})
#text(10.5pt, weight: "bold", fill: rgb("3F7F4A"))[{proj_heading}]
#v(-{section_spacing})
"""
        if p_title:
            typst_doc += f"*{p_title}* \\\n"
        if clean_tech:
            typst_doc += f"#v(-0.55em)\n#text(8.6pt, style: \"italic\")[{clean_tech}]\n"
        typst_doc += "#v(-0.2em)\n"
        for bullet in first_p_bullets:
            clean_bullet = bullet
            if clean_bullet and not clean_bullet.endswith((".", "!", "?")):
                clean_bullet += "."
            typst_doc += f"- {escape_typst(clean_bullet)}\n"
        typst_doc += "]\n"

        for i, proj in enumerate(clean_projects[1:], start=1):
            p_title = escape_typst(proj["title"])
            p_tech = escape_typst(proj["technologies"])
            typst_doc += f"""
#v(0.25em)
#block(breakable: true)[
"""
            if p_title:
                typst_doc += f"*{p_title}* \\\n"
            if p_tech:
                clean_tech = p_tech
                if not clean_tech.lower().startswith("technologies:"):
                    clean_tech = f"Technologies: {clean_tech}"
                typst_doc += f"#v(-0.55em)\n#text(8.6pt, style: \"italic\")[{clean_tech}]\n"
            typst_doc += "#v(-0.2em)\n"
            for bullet in proj["bullets"]:
                clean_bullet = bullet
                if clean_bullet and not clean_bullet.endswith((".", "!", "?")):
                    clean_bullet += "."
                typst_doc += f"- {escape_typst(clean_bullet)}\n"
            typst_doc += "]\n"

    # 5. Education & Certifications
    clean_certs = []
    for c in (certifications or []):
        if isinstance(c, dict):
            c_name = c.get("name", "").strip()
            c_issuer = c.get("issuer", "").strip()
            c_year = str(c.get("year", "")).strip()
            parts = [c_name]
            if c_issuer:
                parts.append(c_issuer)
            line = " — ".join(p for p in parts if p)
            if c_year:
                line += f" | {c_year}"
            if line.strip():
                clean_certs.append(line.strip())
        elif isinstance(c, str) and c.strip():
            clean_certs.append(re.sub(r"^[-•*·\s]+", "", c).strip())

    if separate_education_and_certs:
        # Standalone Education Section
        if education:
            if pb_edu:
                typst_doc += "\n#pagebreak()\n"

            # Bind heading + first education entry in unbreakable block
            first_edu = education[0]
            deg = escape_typst(first_edu.get("degree", "").strip())
            inst = escape_typst(first_edu.get("institution", "").strip())
            yr = escape_typst(str(first_edu.get("year", "")).strip())
            details = escape_typst(first_edu.get("details", "").strip())

            edu_line = f"*{inst}*"
            if deg:
                edu_line += f" — {deg}"
            if yr:
                edu_line += f" | {yr}"

            typst_doc += f"""
#block(breakable: false)[
#v({section_spacing})
#text(10.5pt, weight: "bold", fill: rgb("3F7F4A"))[EDUCATION]
#v(-{section_spacing})
{edu_line} \\
"""
            if details:
                d_lower = details.lower().replace("concentrations:", "").replace("focus:", "").strip()
                deg_lower = deg.lower().strip()
                if d_lower and (d_lower not in deg_lower) and (deg_lower not in d_lower):
                    typst_doc += f"#v(-0.55em)\n#text(8.6pt)[{details}] \\\n"
            typst_doc += "]\n"

            for edu in education[1:]:
                deg = escape_typst(edu.get("degree", "").strip())
                inst = escape_typst(edu.get("institution", "").strip())
                yr = escape_typst(str(edu.get("year", "")).strip())
                details = escape_typst(edu.get("details", "").strip())

                edu_line = f"*{inst}*"
                if deg:
                    edu_line += f" — {deg}"
                if yr:
                    edu_line += f" | {yr}"

                typst_doc += f"{edu_line} \\\n"
                if details:
                    d_lower = details.lower().replace("concentrations:", "").replace("focus:", "").strip()
                    deg_lower = deg.lower().strip()
                    if d_lower and (d_lower not in deg_lower) and (deg_lower not in d_lower):
                        typst_doc += f"#v(-0.55em)\n#text(8.6pt)[{details}] \\\n"

        # Standalone Certifications Section
        if clean_certs:
            if pb_certs:
                typst_doc += "\n#pagebreak()\n"

            typst_doc += f"""
#block(breakable: true)[
#v({section_spacing})
#text(10.5pt, weight: "bold", fill: rgb("3F7F4A"))[CERTIFICATIONS & LICENSES]
#v(-{section_spacing})
"""
            for cert in clean_certs:
                typst_doc += f"- {escape_typst(cert)}\n"
            typst_doc += "]\n"
    else:
        # Combined Education & Certifications Section
        if education or clean_certs:
            if pb_edu or pb_certs:
                typst_doc += "\n#pagebreak()\n"
            edu_heading = "EDUCATION & CERTIFICATIONS" if clean_certs else "EDUCATION"

            if education:
                first_edu = education[0]
                deg = escape_typst(first_edu.get("degree", "").strip())
                inst = escape_typst(first_edu.get("institution", "").strip())
                yr = escape_typst(str(first_edu.get("year", "")).strip())
                details = escape_typst(first_edu.get("details", "").strip())

                edu_line = f"*{inst}*"
                if deg:
                    edu_line += f" — {deg}"
                if yr:
                    edu_line += f" | {yr}"

                typst_doc += f"""
#block(breakable: false)[
#v({section_spacing})
#text(10.5pt, weight: "bold", fill: rgb("3F7F4A"))[{edu_heading}]
#v(-{section_spacing})
{edu_line} \\
"""
                if details:
                    d_lower = details.lower().replace("concentrations:", "").replace("focus:", "").strip()
                    deg_lower = deg.lower().strip()
                    if d_lower and (d_lower not in deg_lower) and (deg_lower not in d_lower):
                        typst_doc += f"#v(-0.55em)\n#text(8.6pt)[{details}] \\\n"
                typst_doc += "]\n"

                for edu in education[1:]:
                    deg = escape_typst(edu.get("degree", "").strip())
                    inst = escape_typst(edu.get("institution", "").strip())
                    yr = escape_typst(str(edu.get("year", "")).strip())
                    details = escape_typst(edu.get("details", "").strip())

                    edu_line = f"*{inst}*"
                    if deg:
                        edu_line += f" — {deg}"
                    if yr:
                        edu_line += f" | {yr}"

                    typst_doc += f"{edu_line} \\\n"
                    if details:
                        d_lower = details.lower().replace("concentrations:", "").replace("focus:", "").strip()
                        deg_lower = deg.lower().strip()
                        if d_lower and (d_lower not in deg_lower) and (deg_lower not in d_lower):
                            typst_doc += f"#v(-0.55em)\n#text(8.6pt)[{details}] \\\n"
            else:
                typst_doc += f"""
#block(breakable: true)[
#v({section_spacing})
#text(10.5pt, weight: "bold", fill: rgb("3F7F4A"))[{edu_heading}]
#v(-{section_spacing})
"""
                for cert in clean_certs:
                    typst_doc += f"- {escape_typst(cert)}\n"
                typst_doc += "]\n"

            if education and clean_certs:
                typst_doc += "\n#v(0.15em)\n*Certifications:* \\\n#v(-0.4em)\n"
                for cert in clean_certs:
                    typst_doc += f"- {escape_typst(cert)}\n"

    # 6. Global Key Honors & Recognition
    if achievements:
        if pb_ach:
            typst_doc += "\n#pagebreak()\n"
        clean_g_achs = [re.sub(r"^[-•*·\s]+", "", str(ach)).strip() for ach in achievements if re.sub(r"^[-•*·\s]+", "", str(ach)).strip()]
        if clean_g_achs:
            typst_doc += f"""
#block(breakable: true)[
#v({section_spacing})
#text(10.5pt, weight: "bold", fill: rgb("3F7F4A"))[KEY HONORS & PROFESSIONAL RECOGNITION]
#v(-{section_spacing})
"""
            for ach in clean_g_achs:
                typst_doc += f"- {escape_typst(ach)}\n"
            typst_doc += "]\n"

    return typst_doc
