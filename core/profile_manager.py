# -*- coding: utf-8 -*-
import os
import json
import re
import copy
from typing import Dict, Any, List, Optional

PROFILES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "profiles")

def ensure_profiles_dir() -> str:
    """Ensures the profiles storage directory exists on disk."""
    if not os.path.exists(PROFILES_DIR):
        os.makedirs(PROFILES_DIR, exist_ok=True)
    return PROFILES_DIR

def _safe_filename(name: str) -> str:
    """Converts a user-defined profile name into a safe filesystem filename."""
    cleaned = re.sub(r'[\\/*?:"<>|]', "", name).strip()
    return cleaned or "default_profile"

def list_saved_profiles() -> List[str]:
    """Returns a sorted list of saved profile names from the server."""
    ensure_profiles_dir()
    profiles = []
    try:
        for fname in os.listdir(PROFILES_DIR):
            if fname.lower().endswith(".json"):
                profile_name = os.path.splitext(fname)[0]
                profiles.append(profile_name)
    except Exception as e:
        print(f"[ProfileManager Error] list_saved_profiles: {e}")
    return sorted(profiles)

def load_profile(name: str) -> Optional[Dict[str, Any]]:
    """Loads a profile dictionary by name from disk."""
    ensure_profiles_dir()
    safe_name = _safe_filename(name)
    file_path = os.path.join(PROFILES_DIR, f"{safe_name}.json")
    if not os.path.exists(file_path):
        return None
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data
    except Exception as e:
        print(f"[ProfileManager Error] load_profile '{name}': {e}")
        return None

def save_profile(name: str, profile_data: Dict[str, Any]) -> str:
    """
    Saves a profile dictionary to disk under profiles/<safe_name>.json.
    Returns the absolute path to the saved file.
    """
    ensure_profiles_dir()
    safe_name = _safe_filename(name)
    file_path = os.path.join(PROFILES_DIR, f"{safe_name}.json")
    
    normalized = normalize_profile_data(profile_data, profile_name=name)
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(normalized, f, indent=2, ensure_ascii=False)
    return file_path

def delete_profile(name: str) -> bool:
    """Deletes a profile file from disk."""
    ensure_profiles_dir()
    safe_name = _safe_filename(name)
    file_path = os.path.join(PROFILES_DIR, f"{safe_name}.json")
    if os.path.exists(file_path):
        try:
            os.remove(file_path)
            return True
        except Exception as e:
            print(f"[ProfileManager Error] delete_profile '{name}': {e}")
            return False
    return False

def normalize_profile_data(data: Dict[str, Any], profile_name: str = "") -> Dict[str, Any]:
    """Ensures consistent schema for master career profiles."""
    res = copy.deepcopy(data) if data else {}
    return {
        "profile_name": profile_name or res.get("profile_name", "My Career Profile"),
        "personal": {
            "name": res.get("personal", {}).get("name", "Candidate Name"),
            "email": res.get("personal", {}).get("email", ""),
            "phone": res.get("personal", {}).get("phone", ""),
            "location": res.get("personal", {}).get("location", ""),
            "country": res.get("personal", {}).get("country", "Canada"),
            "linkedin": res.get("personal", {}).get("linkedin", ""),
            "github": res.get("personal", {}).get("github", ""),
            "portfolio": res.get("personal", {}).get("portfolio", "")
        },
        "summary": res.get("summary", ""),
        "domain": res.get("domain", "Professional"),
        "target_job_titles": res.get("target_job_titles", []),
        "seniority_level": res.get("seniority_level", "Mid"),
        "years_of_experience": res.get("years_of_experience", 2),
        "skills": res.get("skills", {
            "core_competencies": [],
            "industry_and_compliance": [],
            "software_and_tools": []
        }),
        "experience": res.get("experience", []),
        "projects": res.get("projects", []),
        "education": res.get("education", []),
        "certifications": res.get("certifications", []),
        "achievements": res.get("achievements", []),
        "raw_resume_text": res.get("raw_resume_text", "")
    }

def profile_to_resume_dict(profile_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Converts a master profile into the candidate profile dictionary structure
    expected by core compiler, scorer, and studio components.
    """
    p = normalize_profile_data(profile_data)
    return {
        "personal": p["personal"],
        "summary": p["summary"],
        "domain": p["domain"],
        "target_job_titles": p["target_job_titles"],
        "seniority_level": p["seniority_level"],
        "years_of_experience": p["years_of_experience"],
        "skills": p["skills"],
        "experience": p["experience"],
        "projects": p["projects"],
        "education": p["education"],
        "certifications": p["certifications"],
        "achievements": p["achievements"],
        "engine_used": "Saved Master Profile"
    }

def resume_dict_to_profile(resume_dict: Dict[str, Any], profile_name: str = "", raw_text: str = "") -> Dict[str, Any]:
    """Converts a parsed resume dictionary into a master profile structure."""
    prof = normalize_profile_data(resume_dict, profile_name=profile_name)
    if raw_text:
        prof["raw_resume_text"] = raw_text
    return prof



