# -*- coding: utf-8 -*-
import json
import requests
from typing import Tuple, Optional, Any, Dict, List

# In-memory volatile cache for discovered model (Zero-Storage / Never written to disk)
_SESSION_DISCOVERED_MODEL: Optional[str] = None
_SESSION_API_VERSION: str = "v1beta"

def get_ordered_model_candidates(api_key: str) -> Tuple[List[str], str, Optional[str]]:
    """
    Retrieves and ranks the active models for this key from Google AI Studio.
    Filters out discontinued models and prioritizes stable flash/pro models.
    """
    clean_key = str(api_key).strip().strip('"').strip("'")
    
    preferred_order = [
        "gemini-2.0-flash",
        "gemini-1.5-flash",
        "gemini-1.5-flash-latest",
        "gemini-1.5-pro",
        "gemini-1.5-pro-latest",
        "gemini-pro"
    ]
    
    for api_version in ["v1beta", "v1"]:
        url = f"https://generativelanguage.googleapis.com/{api_version}/models?key={clean_key}"
        try:
            resp = requests.get(url, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                models = data.get("models", [])
                supported = [
                    m.get("name") for m in models
                    if "generateContent" in m.get("supportedGenerationMethods", [])
                ]
                
                # Filter out discontinued / preview models like 2.5-flash
                supported = [m for m in supported if "2.5-flash" not in m]

                ranked = []
                # First add by preference
                for pref in preferred_order:
                    for m in supported:
                        if pref in m and m not in ranked:
                            ranked.append(m)
                
                # Add any remaining supported models
                for m in supported:
                    if m not in ranked:
                        ranked.append(m)

                if ranked:
                    return ranked, api_version, None
            else:
                err = resp.json().get("error", {})
                msg = err.get("message", f"HTTP {resp.status_code}")
                if resp.status_code in [400, 401, 403]:
                    return [], api_version, f"Google API Error ({resp.status_code}): {msg}"
        except Exception as e:
            continue

    # Fallback to standard model names if ListModels is unreachable
    return ["models/gemini-2.0-flash", "models/gemini-1.5-flash", "models/gemini-1.5-pro"], "v1beta", None

def call_gemini(api_key: str, prompt: str, json_mode: bool = False) -> Tuple[bool, str, str]:
    """
    Executes a Gemini API request with zero persistence (in-memory only).
    Automatically falls back across all available models until one succeeds.
    Returns: (success: bool, text_response: str, model_used_or_error: str)
    """
    global _SESSION_DISCOVERED_MODEL, _SESSION_API_VERSION

    if not api_key or not str(api_key).strip():
        return False, "", "API key is missing or empty."

    clean_key = str(api_key).strip().strip('"').strip("'")

    # If already verified a working model in this session, use it directly
    api_version = _SESSION_API_VERSION
    if _SESSION_DISCOVERED_MODEL:
        candidates = [_SESSION_DISCOVERED_MODEL]
    else:
        discovered, api_version, err = get_ordered_model_candidates(clean_key)
        if not discovered and err:
            return False, "", err
        candidates = discovered

    last_err = ""
    for model_name in candidates:
        clean_model_path = model_name if model_name.startswith("models/") else f"models/{model_name}"
        url = f"https://generativelanguage.googleapis.com/{api_version}/{clean_model_path}:generateContent?key={clean_key}"

        headers = {"Content-Type": "application/json"}
        payload: Dict[str, Any] = {
            "contents": [{
                "parts": [{"text": prompt}]
            }],
            "generationConfig": {
                "temperature": 0.1
            }
        }
        if json_mode:
            payload["generationConfig"]["responseMimeType"] = "application/json"

        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=35)
            data = resp.json()

            if resp.status_code == 200:
                candidates_out = data.get("candidates", [])
                if candidates_out:
                    parts = candidates_out[0].get("content", {}).get("parts", [])
                    if parts and "text" in parts[0]:
                        display_name = clean_model_path.replace("models/", "")
                        # Cache the working model for this session
                        _SESSION_DISCOVERED_MODEL = clean_model_path
                        _SESSION_API_VERSION = api_version
                        return True, parts[0]["text"], display_name
            else:
                err_obj = data.get("error", {})
                err_msg = err_obj.get("message", f"HTTP {resp.status_code}")
                last_err = err_msg
                # If model is discontinued or 404, loop and try the next model
                continue
        except Exception as ex:
            last_err = str(ex)
            continue

    return False, "", f"Google API Error: {last_err}"

def ping_gemini(api_key: str) -> Tuple[bool, str]:
    """
    Pings Google Gemini to verify the API key and find a working model.
    Zero storage: does not write the key to disk.
    """
    if not api_key or not str(api_key).strip():
        return False, "Please paste a valid Gemini API Key."

    clean_key = str(api_key).strip().strip('"').strip("'")
    success, text, model_or_err = call_gemini(clean_key, "Respond with: PONG", json_mode=False)

    if success:
        return True, f"Connected to Google {model_or_err} successfully! (Session-Only / Never Stored)"
    else:
        return False, f"Connection Failed: {model_or_err}"

def reset_gemini_session():
    """Wipes all cached model metadata from memory upon session exit."""
    global _SESSION_DISCOVERED_MODEL, _SESSION_API_VERSION
    _SESSION_DISCOVERED_MODEL = None
    _SESSION_API_VERSION = "v1beta"
