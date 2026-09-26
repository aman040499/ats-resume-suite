import os
import sys

print("Testing imports...")
import jobspy
import typst
import pypdf
import pdfplumber
import sklearn
import google.genai
import streamlit

print("All imports successful!")

from core.compiler import compile_tailored_pdf
from core.ats_scorer import score_job_against_resume
from core.resume_fixer import generate_minimal_resume_fixes

mock_profile = {
    "personal": {
        "name": "Alex Mercer",
        "email": "alex.mercer@example.com",
        "phone": "+1 (555) 234-5678",
        "location": "San Francisco, CA",
        "linkedin": "https://linkedin.com/in/alexmercer",
        "github": "https://github.com/alexmercer"
    },
    "target_job_titles": ["Senior Backend Engineer", "Full Stack Developer"],
    "seniority_level": "Senior",
    "years_of_experience": 5,
    "skills": {
        "languages": ["Python", "Go", "TypeScript", "SQL"],
        "frameworks": ["FastAPI", "React", "Django", "Node.js"],
        "cloud_and_devops": ["AWS", "Docker", "Kubernetes", "PostgreSQL", "Redis"]
    },
    "experience": [
        {
            "company": "ScaleTech Systems",
            "title": "Senior Backend Engineer",
            "dates": "2022 - Present",
            "bullets": [
                "Architected event-driven microservices with FastAPI and Kafka processing 5M events daily.",
                "Optimized PostgreSQL connection pooling and indexing, lowering p95 latency by 35%."
            ]
        }
    ],
    "education": [
        {
            "degree": "B.S. in Computer Science",
            "institution": "University of California, Berkeley",
            "year": "2019"
        }
    ]
}

high_match_job = {
    "id": "test_job_1",
    "title": "Senior Python Backend Engineer",
    "company": "CloudWave Inc",
    "location": "Remote",
    "description": """
    CloudWave is hiring a Senior Python Backend Engineer.
    Requirements:
    - 4+ years of professional backend development with Python, FastAPI, and PostgreSQL.
    - Hands-on experience with Docker, Kubernetes, and distributed streaming (Kafka).
    - Strong database optimization and system design experience.
    """,
    "site": "linkedin",
    "job_url": "https://example.com/job1"
}

low_match_job = {
    "id": "test_job_2",
    "title": "Registered Nurse - ICU",
    "company": "City Health Hospital",
    "location": "Remote",
    "description": """
    Looking for a Certified Registered Nurse with 3+ years experience in Intensive Care Unit (ICU),
    BLS, ACLS certification, patient triage and electronic health records.
    """,
    "site": "indeed",
    "job_url": "https://example.com/job2"
}

resume_raw = """
Alex Mercer - Senior Backend Engineer
Skills: Python, Go, TypeScript, SQL, FastAPI, React, Django, AWS, Docker, Kubernetes, PostgreSQL, Redis, Kafka.
Experience:
Senior Backend Engineer at ScaleTech Systems (2022 - Present)
Architected event-driven microservices with FastAPI and Kafka processing 5M events daily.
Optimized PostgreSQL connection pooling and indexing, lowering p95 latency by 35%.
"""

print("\n--- Testing ATS Scorer with High Match Job ---")
eval_high = score_job_against_resume(mock_profile, resume_raw, high_match_job, threshold=70.0)
print(f"High match job score: {eval_high['overall_ats_score']}% | Passes 70% Cutoff: {bool(eval_high['passes_threshold'])}")
assert bool(eval_high['passes_threshold']) is True, "High match job should pass 70% threshold"

print("\n--- Testing ATS Scorer with Low Match Job ---")
eval_low = score_job_against_resume(mock_profile, resume_raw, low_match_job, threshold=70.0)
print(f"Low match job score: {eval_low['overall_ats_score']}% | Passes 70% Cutoff: {bool(eval_low['passes_threshold'])}")
assert bool(eval_low['passes_threshold']) is False, "Low match job should be rejected by 70% cutoff"

print("\n--- Testing Typst ATS PDF Compilation ---")
os.makedirs("test_output", exist_ok=True)
pdf_path = os.path.join("test_output", "sample_ats_resume.pdf")
compile_tailored_pdf(
    personal=mock_profile["personal"],
    summary="Senior Backend Engineer specialized in distributed Python and cloud infrastructure.",
    skills=mock_profile["skills"],
    experience=mock_profile["experience"],
    education=mock_profile["education"],
    output_pdf_path=pdf_path
)
assert os.path.exists(pdf_path), "PDF was not created!"
print(f"Typst successfully generated ATS PDF: {pdf_path} (Size: {os.path.getsize(pdf_path)} bytes)")

print("\nALL PIPELINE TESTS PASSED!")
