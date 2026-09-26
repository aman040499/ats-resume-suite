# -*- coding: utf-8 -*-
# Pre-import tls_client and jobspy on main thread to initialize Windows CGO DLLs safely
import tls_client
import jobspy
from jobspy import scrape_jobs

import os
import hashlib
from typing import List, Dict, Any, Optional
import pandas as pd
from datetime import datetime

def generate_job_id(title: str, company: str, job_url: str) -> str:
    key = f"{title.lower()}_{company.lower()}_{job_url}"
    return hashlib.md5(key.encode("utf-8")).hexdigest()[:12]

import requests
from bs4 import BeautifulSoup

def _scrape_remotive_jobs(search_term: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Scrapes remote postings from Remotive API matching the search term."""
    try:
        url = f"https://remotive.com/api/remote-jobs?search={search_term}"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        r = requests.get(url, headers=headers, timeout=8)
        if r.status_code == 200:
            data = r.json().get("jobs", [])
            results = []
            for item in data[:limit]:
                title = item.get("title", "").strip()
                company = item.get("company_name", "").strip()
                job_url = item.get("url", "").strip()
                desc_html = item.get("description", "")
                desc_text = BeautifulSoup(desc_html, "html.parser").get_text(separator=" ").strip()
                if title and job_url and len(desc_text) >= 30:
                    results.append({
                        "title": title,
                        "company": company,
                        "location": item.get("candidate_required_location", "Remote"),
                        "job_url": job_url,
                        "date_posted": str(item.get("publication_date", "Recent"))[:10],
                        "description": desc_text,
                        "site": "remotive",
                        "salary_min": None,
                        "salary_max": None,
                        "currency": "CAD"
                    })
            return results
    except Exception as e:
        print(f"[Scraper Notice] Remotive error for '{search_term}': {e}")
    return []

def _scrape_jobicy_jobs(search_term: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Scrapes remote postings from Jobicy API matching the search term."""
    try:
        url = f"https://jobicy.com/api/v2/remote-jobs?count={limit}&tag={search_term.lower()}"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        r = requests.get(url, headers=headers, timeout=8)
        if r.status_code == 200:
            data = r.json().get("jobs", [])
            results = []
            for item in data[:limit]:
                title = item.get("jobTitle", "").strip()
                company = item.get("companyName", "").strip()
                job_url = item.get("url", "").strip()
                desc_html = item.get("jobDescription", "")
                desc_text = BeautifulSoup(desc_html, "html.parser").get_text(separator=" ").strip()
                if title and job_url and len(desc_text) >= 30:
                    results.append({
                        "title": title,
                        "company": company,
                        "location": item.get("jobGeo", "Remote"),
                        "job_url": job_url,
                        "date_posted": str(item.get("pubDate", "Recent"))[:10],
                        "description": desc_text,
                        "site": "jobicy",
                        "salary_min": item.get("annualSalaryMin"),
                        "salary_max": item.get("annualSalaryMax"),
                        "currency": item.get("salaryCurrency", "CAD")
                    })
            return results
    except Exception as e:
        print(f"[Scraper Notice] Jobicy error for '{search_term}': {e}")
    return []

from concurrent.futures import ThreadPoolExecutor, as_completed

def _scrape_remoteco_jobs(search_term: str, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Scrapes remote jobs from remote-first feeds matching the search term.
    Includes Remote.co web/feed parser with reliable fast timeout.
    """
    results = []
    # 1. Try Remote.co search with browser headers
    try:
        url = f"https://remote.co/remote-jobs/search/?search_keywords={search_term}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        }
        r = requests.get(url, headers=headers, timeout=4)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, "html.parser")
            for a in soup.find_all("a", href=True):
                if "/job/" in a["href"]:
                    title = a.text.strip()
                    if title and len(title) > 3:
                        job_url = a["href"]
                        if not job_url.startswith("http"):
                            job_url = "https://remote.co" + job_url
                        results.append({
                            "title": title,
                            "company": "Remote.co Verified Employer",
                            "location": "Remote",
                            "job_url": job_url,
                            "date_posted": "Recent",
                            "description": f"Remote opportunity for {title}. Check full posting on Remote.co.",
                            "site": "remote.co",
                            "salary_min": None,
                            "salary_max": None,
                            "currency": "CAD"
                        })
                        if len(results) >= limit:
                            return results
    except Exception as e:
        print(f"[Scraper Notice] Remote.co web direct skipped: {e}")

    # 2. Fast remote feed backup if remote.co web direct blocks
    if not results:
        try:
            feed_url = "https://weworkremotely.com/remote-jobs.rss"
            rf = requests.get(feed_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=4)
            if rf.status_code == 200:
                import xml.etree.ElementTree as ET
                root = ET.fromstring(rf.content)
                term_lower = search_term.lower()
                for item in root.findall(".//item"):
                    raw_title = item.find("title").text or ""
                    link = item.find("link").text or ""
                    desc = item.find("description").text or ""
                    clean_desc = BeautifulSoup(desc, "html.parser").get_text(separator=" ").strip()
                    if any(w in (raw_title + " " + clean_desc).lower() for w in term_lower.split()):
                        parts = raw_title.split(":", 1)
                        company = parts[0].strip() if len(parts) > 1 else "Remote Organization"
                        title = parts[1].strip() if len(parts) > 1 else raw_title.strip()
                        results.append({
                            "title": title,
                            "company": company,
                            "location": "Remote",
                            "job_url": link,
                            "date_posted": "Recent",
                            "description": clean_desc[:2500] if clean_desc else f"Remote {title} opportunity.",
                            "site": "remote.co",
                            "salary_min": None,
                            "salary_max": None,
                            "currency": "CAD"
                        })
                        if len(results) >= limit:
                            break
        except Exception as e_feed:
            print(f"[Scraper Notice] Remote feed backup skipped: {e_feed}")

    return results

def _scrape_single_task(site: str, term: str, location: str, query_location: str, results_wanted: int, hours_old: int, country_indeed: str, city_filter: str = "") -> List[Dict[str, Any]]:
    """Worker task executed concurrently for high-speed multi-board scraping."""
    task_jobs = []
    
    # 1. API-based remote boards
    if site == "remotive":
        return _scrape_remotive_jobs(term, limit=results_wanted)
    elif site == "jobicy":
        return _scrape_jobicy_jobs(term, limit=results_wanted)
    elif site == "remote.co":
        return _scrape_remoteco_jobs(term, limit=results_wanted)

    # 2. JobSpy platforms (Indeed, LinkedIn, Glassdoor)
    try:
        is_remote_flag = True if "remote" in location.lower() else False
        scraped_df: pd.DataFrame = scrape_jobs(
            site_name=[site],
            search_term=term,
            location=query_location,
            results_wanted=results_wanted,
            hours_old=hours_old,
            country_indeed=country_indeed,
            is_remote=is_remote_flag
        )

        if (scraped_df is None or scraped_df.empty) and site == "linkedin" and query_location != "Canada":
            scraped_df = scrape_jobs(
                site_name=["linkedin"],
                search_term=term,
                location="Canada",
                results_wanted=results_wanted,
                hours_old=hours_old,
                is_remote=is_remote_flag
            )

        if scraped_df is not None and not scraped_df.empty:
            for _, row in scraped_df.iterrows():
                title = str(row.get("title") or "").strip()
                company = str(row.get("company") or "").strip()
                job_url = str(row.get("job_url") or "").strip()
                desc = str(row.get("description") or "").strip()
                job_loc = str(row.get("location") or location)

                if not title or not job_url or len(desc) < 30:
                    continue

                # Apply city filter if user specified a specific city
                if city_filter and city_filter.lower() != "all":
                    cf = city_filter.lower().strip()
                    if cf not in job_loc.lower() and cf not in desc.lower()[:300]:
                        continue

                task_jobs.append({
                    "site": site,
                    "title": title,
                    "company": company,
                    "location": job_loc,
                    "job_url": job_url,
                    "date_posted": str(row.get("date_posted") or "Past 7 days"),
                    "salary_min": row.get("min_amount"),
                    "salary_max": row.get("max_amount"),
                    "currency": str(row.get("currency") or "CAD"),
                    "description": desc,
                    "search_term": term,
                    "scraped_at": datetime.utcnow().isoformat()
                })
    except Exception as e:
        print(f"[Scraper Notice] {site} query for '{term}' skipped: {e}")

    return task_jobs

def scrape_recent_jobs(
    search_terms: List[str],
    location: str = "Ontario, Canada",
    results_per_term: int = 10,
    hours_old: int = 168,  # 7 days
    country_indeed: str = "Canada",
    sites: Optional[List[str]] = None,
    city_filter: str = ""
) -> List[Dict[str, Any]]:
    """
    High-speed parallelized job scraper querying boards concurrently across threads.
    Includes Indeed, LinkedIn, Remote.co, Remotive, Jobicy with city-level filtering.
    """
    if not sites:
        sites = ["indeed", "linkedin"]

    all_jobs = []
    seen_ids = set()

    query_location = location
    if city_filter and city_filter.lower() != "all":
        query_location = f"{city_filter.strip()}, {country_indeed}"

    # Build work items for ThreadPoolExecutor
    tasks = []
    for term in search_terms:
        for site in sites:
            tasks.append((site, term, location, query_location, results_per_term, hours_old, country_indeed, city_filter))

    print(f"[Fast Scraper] Executing {len(tasks)} search tasks concurrently...")

    max_workers = min(8, max(2, len(tasks)))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_task = {
            executor.submit(_scrape_single_task, *t): t for t in tasks
        }
        for future in as_completed(future_to_task):
            task_info = future_to_task[future]
            try:
                task_res = future.result()
                for job in task_res:
                    job_id = generate_job_id(job["title"], job["company"], job["job_url"])
                    if job_id not in seen_ids:
                        seen_ids.add(job_id)
                        job["id"] = job_id
                        all_jobs.append(job)
            except Exception as exc:
                print(f"[Fast Scraper Notice] Task {task_info[0]} for '{task_info[1]}' generated exception: {exc}")

    print(f"[Fast Scraper] Concurrently collected {len(all_jobs)} unique listings.")
    return all_jobs
