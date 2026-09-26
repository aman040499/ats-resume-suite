# ?? Resume-First Autonomous Job Hunter & ATS Gatekeeper

An intelligent, autonomous job hunting and resume curation tool. You upload **only your resume**, and the tool takes care of the rest:
1. **Profiles Your Resume**: Extracts target job titles, core skills, seniority, and location preferences automatically.
2. **Aggregated Discovery**: Concurrently searches LinkedIn, Indeed, Glassdoor, and ZipRecruiter for postings published within the last **7 days** (168 hours).
3. **Strict $\ge 70\%$ ATS Gatekeeper**: Evaluates every discovered job description against your resume and ruthlessly prunes anything under a 70% ATS match score.
4. **Minimal Resume Fixer (Google XYZ)**: For jobs $\ge 70\%$, identifies the remaining gap and suggests minimal, truthful tweaks (never inventing fake experience) to elevate your score to 85–95%+.
5. **Instant Typst PDF Compiler**: Compiles an ATS-compliant, single-column vector PDF in milliseconds.
6. **One-Click Review & Confirmation**: Lets you review bullet-by-bullet diffs, download the tailored PDF, and click **[Confirm & Apply]** to open the application in your browser.

---

## ?? Quickstart

### 1. Requirements
- Python 3.12 (already installed in `.venv`)
- Windows / macOS / Linux

### 2. Configure Gemini API Key
Copy `.env.example` to `.env` or enter your key in the web sidebar:
```bash
GEMINI_API_KEY="your_api_key_here"
```

### 3. Launch the Dashboard
Double click `start.bat` or run in terminal:
```bash
.\.venv\Scripts\activate
streamlit run app.py
```

---

## ?? Architecture
- `core/parser.py`: PDF text extraction and candidate profiling.
- `core/scraper.py`: Multi-board job scraper (`python-jobspy`) with 7-day filter.
- `core/ats_scorer.py`: Two-phase ATS matching engine (fast cosine filter + deep Gemini evaluation with $\ge 70\%$ cutoff).
- `core/resume_fixer.py`: Minimal bullet point optimizer using Google's XYZ formula.
- `core/compiler.py`: Sub-second ATS PDF generator via Typst.
- `core/apply_helper.py`: Semi-automated browser launcher for rapid submission.
- `app.py`: Streamlit command center.
