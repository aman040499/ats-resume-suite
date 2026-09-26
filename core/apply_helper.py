import os
import webbrowser
from typing import Optional

def open_job_application(job_url: str, pdf_resume_path: Optional[str] = None, use_playwright: bool = False):
    """
    Assists in opening the job application.
    If use_playwright is True, launches a persistent Chromium browser that remembers logins
    and attempts to prepare the application with the tailored resume.
    Otherwise, opens the user default browser and reveals the generated PDF.
    """
    if not use_playwright:
        webbrowser.open(job_url)
        return {"status": "opened_in_browser", "url": job_url}

    try:
        from playwright.sync_api import sync_playwright

        user_dir = os.path.abspath("./browser_data_profile")
        os.makedirs(user_dir, exist_ok=True)

        with sync_playwright() as p:
            browser = p.chromium.launch_persistent_context(
                user_data_dir=user_dir,
                headless=False,
                channel="chrome"  # use system Chrome if installed, or default chromium
            )
            page = browser.new_page()
            page.goto(job_url)

            # Check if file upload input exists
            if pdf_resume_path and os.path.exists(pdf_resume_path):
                file_input = page.query_selector('input[type="file"]')
                if file_input:
                    try:
                        file_input.set_input_files(os.path.abspath(pdf_resume_path))
                        print(f"[Apply Helper] Attached tailored resume: {pdf_resume_path}")
                    except Exception as e:
                        print(f"[Apply Helper] Auto-upload non-critical warning: {e}")

            # Keep open for the user to confirm & submit
            page.wait_for_timeout(5000)
            return {"status": "launched_playwright", "url": job_url}
    except Exception as ex:
        print(f"[Apply Helper] Playwright execution failed, falling back to standard browser: {ex}")
        webbrowser.open(job_url)
        return {"status": "opened_in_browser_fallback", "url": job_url}
