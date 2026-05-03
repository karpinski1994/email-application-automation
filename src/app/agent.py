"""Main orchestrator for Email Application Automation."""

import asyncio
import json
from datetime import datetime
from pathlib import Path

from .config import load_config
from .models import Config, RunSummary
from .utils import DATA_DIR, is_cached, save_json, load_json, ensure_data_dir

from .tools.cv_parser import parse_cv, parse_cv_mock
from .tools.scraper import scrape_jobs
from .tools.filter import filter_jobs
from .tools.email_finder import find_email
from .tools.cover_letter import generate_cover_letter
from .tools.cv_personalizer import personalize_cv
from .tools.gmail_draft import create_draft


async def run(config: Config, force: bool = False, step: int = 1, dry_run: bool = False) -> RunSummary:
    """Run the email application automation pipeline.
    
    Args:
        config: Configuration object
        force: Force re-run even if cache exists
        step: Start from step N (1-7)
        dry_run: Don't call external APIs
    
    Returns:
        RunSummary with statistics
    """
    ensure_data_dir()
    started_at = datetime.now().isoformat()
    errors = []
    
    # Step 1: Parse CV (always use real CV, mocks are for other steps)
    if step <= 1:
        cv_path = DATA_DIR / "cv_parsed.json"
        if force or not is_cached(cv_path):
            try:
                cv_text = parse_cv(config.cv.path)
            except FileNotFoundError:
                print(f"CV not found: {config.cv.path}, using mock")
                cv_text = parse_cv_mock()
            save_json(cv_path, {"text": cv_text})
        else:
            cv_text = load_json(cv_path).get("text", "")
        print(f"Step 1: CV parsed ({len(cv_text)} chars)")
    
    # Step 2: Scrape Jobs
    if step <= 2:
        jobs_path = DATA_DIR / "apify_results.json"
        if force or not is_cached(jobs_path):
            if dry_run:
                jobs = await scrape_jobs(config.search.urls, config.search.count)
            else:
                jobs = await scrape_jobs(config.search.urls, config.search.count)
            save_json(jobs_path, [j.model_dump() for j in jobs])
        else:
            jobs_data = load_json(jobs_path)
            from .models import Job
            jobs = [Job(**j) for j in jobs_data]
        print(f"Step 2: Scraped {len(jobs)} jobs")
    
    # Step 3: Filter Jobs
    if step <= 3:
        filtered_path = DATA_DIR / "filtered_jobs.json"
        if force or not is_cached(filtered_path):
            qualifying, rejected = await filter_jobs(jobs, cv_text)
            save_json(filtered_path, [j.model_dump() for j in qualifying])
            save_json(DATA_DIR / "filtered_out_jobs.json", [j.model_dump() for j in rejected])
        else:
            qualifying_data = load_json(filtered_path)
            from .models import Job
            qualifying = [Job(**j) for j in qualifying_data]
        print(f"Step 3: {len(qualifying)} jobs qualified")
    
    # Steps 4-7: Process each job
    drafts_created = 0
    for i, job in enumerate(qualifying[:config.search.count]):
        try:
            # Step 4: Personalize CV
            cv_pdf = await personalize_cv(cv_text, job)
            
            # Step 5: Find email
            email = await find_email(job.company, job.hiring_manager_name)
            if not email:
                errors.append(f"{job.id}: No email found")
                continue
            
            # Step 6: Generate cover letter
            letter = await generate_cover_letter(job, cv_text)
            
            # Step 7: Create Gmail draft
            if not dry_run:
                draft_id = await create_draft(email, f"Application for {job.title}", letter, cv_pdf)
            else:
                draft_id = f"dry_run_{i}"
            
            drafts_created += 1
            print(f"  Job {i+1}/{len(qualifying)}: Created draft for {job.title}")
            
        except Exception as e:
            errors.append(f"{job.id}: {str(e)}")
    
    finished_at = datetime.now().isoformat()
    
    summary = RunSummary(
        started_at=started_at,
        finished_at=finished_at,
        jobs_found=len(jobs),
        jobs_filtered=len(jobs) - len(qualifying),
        jobs_qualified=len(qualifying),
        drafts_created=drafts_created,
        errors=errors
    )
    
    save_json(DATA_DIR / "run_summary.json", summary.model_dump())
    
    return summary
