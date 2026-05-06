"""Main orchestrator for Email Application Automation."""

import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from app.models import Job, RunSummary
from app.utils import DATA_DIR, ensure_data_dir, is_cached, load_json, save_json


def validate_prerequisites(step: int) -> None:
    """Validate required cache files exist before running a step.
    
    Args:
        step: The step number to run (1-6)
        
    Raises:
        FileNotFoundError: If required cache files from previous steps are missing
    """
    prerequisite_hints = {
        2: {"file": "cv_parsed.json", "step": 1, "desc": "Parse your CV"},
        3: {"file": "apify_results.json", "step": 2, "desc": "Scrape jobs from LinkedIn"},
        4: {"file": "filtered_jobs.json", "step": 3, "desc": "Filter jobs by CV match"},
        5: {"file": "emails.json", "step": 4, "desc": "Find hiring manager emails"},
        6: {"file": "emails.json", "step": 4, "desc": "Find hiring manager emails"},
    }
    
    # Special case: step 5 needs both filtered_jobs.json AND emails.json
    if step == 5:
        if not (DATA_DIR / "filtered_jobs.json").exists():
            raise FileNotFoundError(
                f"Missing data/filtered_jobs.json\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"Run step 3 first to filter jobs:\n"
                f"  source .venv/bin/activate && PYTHONPATH=src python3 -m app --step 3\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            )
        if not (DATA_DIR / "emails.json").exists():
            raise FileNotFoundError(
                f"Missing data/emails.json\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"Run step 4 first to find emails:\n"
                f"  source .venv/bin/activate && PYTHONPATH=src python3 -m app --step 4\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            )
        return
    
    if step > 1 and step in prerequisite_hints:
        hint = prerequisite_hints[step]
        required_file = DATA_DIR / hint["file"]
        
        if not required_file.exists():
            raise FileNotFoundError(
                f"Missing data/{hint['file']}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"Run step {hint['step']} first ({hint['desc']}):\n"
                f"  source .venv/bin/activate && PYTHONPATH=src python3 -m app --step {hint['step']}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            )


async def run(config, force=False, step=1, dry_run=False, filter_only=False):
    """Run the email application automation pipeline.
    
    Args:
        config: Configuration object
        force: Force re-run even if cache exists
        step: Start from step N (1-7)
        dry_run: Don't call external APIs
        filter_only: Stop after filtering (step 3)
    
    Returns:
        RunSummary with statistics
    """
    # Lazy imports — only load modules when actually needed
    if step <= 1:
        from app.tools.cv_parser import parse_cv, parse_cv_mock
        from app.config import load_config
    if step <= 2:
        from app.tools.scraper import scrape_jobs
    if step <= 3:
        from app.tools.filter import filter_jobs
    if step <= 4:
        from app.tools.email_finder import find_emails_for_jobs
    if step <= 5:
        from app.tools.cv_personalizer import personalize_all_filtered, personalize_cv
    if step <= 6:
        from app.tools.gmail_draft import create_draft
    ensure_data_dir()
    validate_prerequisites(step)
    started_at = datetime.now().isoformat()
    errors = []
    
    # Step 1: Parse CV (always ensure cv_text is available)
    cv_path = DATA_DIR / "cv_parsed.json"
    if step <= 1:
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
        
        if step == 1:
            finished_at = datetime.now().isoformat()
            print()
            print("=" * 50)
            print("STEP 1 COMPLETE: CV Parsed")
            print("=" * 50)
            print(f"CV text: {len(cv_text)} characters")
            print(f"Output: data/cv_parsed.json")
            print()
            print("Next: Run --step 2 to scrape jobs from LinkedIn")
            return RunSummary(
                started_at=started_at,
                finished_at=finished_at,
                jobs_found=0,
                jobs_filtered=0,
                jobs_qualified=0,
                drafts_created=0,
                errors=errors,
            )
    else:
        if cv_path.exists():
            cv_text = load_json(cv_path).get("text", "")
            print(f"Step 1: (skipped, loaded {len(cv_text)} chars from cache)")
        else:
            cv_text = ""
            print("Step 1: No cached CV found")
    
    # Step 2: Load Jobs (from cache or scrape)
    jobs_path = DATA_DIR / "apify_results.json"
    if step <= 2:
        if is_cached(jobs_path) and not force:
            # Load from existing file — DO NOT overwrite
            jobs = _load_jobs_from_apify_cache(jobs_path)
            print(f"Step 2: Loaded {len(jobs)} jobs from cache (skipping Apify call)")
            
            if step == 2:
                finished_at = datetime.now().isoformat()
                print()
                print("=" * 50)
                print("STEP 2 COMPLETE: Jobs Scraped")
                print("=" * 50)
                print(f"Jobs found: {len(jobs)}")
                print(f"Output: data/apify_results.json")
                print()
                print("Next: Run --step 3 to filter jobs by CV match")
                return RunSummary(
                    started_at=started_at,
                    finished_at=finished_at,
                    jobs_found=len(jobs),
                    jobs_filtered=0,
                    jobs_qualified=0,
                    drafts_created=0,
                    errors=errors,
                )
        else:
            jobs = await scrape_jobs(config.search.urls, config.apify, config.search.count)
            save_json(jobs_path, [j.model_dump() for j in jobs])
            print(f"Step 2: Scraped {len(jobs)} jobs")
        
        if step == 2:
            finished_at = datetime.now().isoformat()
            print()
            print("=" * 50)
            print("STEP 2 COMPLETE: Jobs Scraped")
            print("=" * 50)
            print(f"Jobs found: {len(jobs)}")
            print(f"Output: data/apify_results.json")
            print()
            print("Next: Run --step 3 to filter jobs by CV match")
            return RunSummary(
                started_at=started_at,
                finished_at=finished_at,
                jobs_found=len(jobs),
                jobs_filtered=0,
                jobs_qualified=0,
                drafts_created=0,
                errors=errors,
            )
    else:
        # Starting from step > 2, still need to load jobs for downstream steps
        if is_cached(jobs_path):
            jobs = _load_jobs_from_apify_cache(jobs_path)
            print(f"Step 2: (skipped, loaded {len(jobs)} jobs from cache)")
        else:
            print("Step 2: No cached jobs found and step was skipped!")
            jobs = []
    
    # Step 3: Filter Jobs
    if step <= 3:
        filtered_path = DATA_DIR / "filtered_jobs.json"
        if force or not is_cached(filtered_path):
            # Determine LLM config based on provider
            if config.llm.provider == "openai":
                llm_base_url = "https://api.openai.com/v1"
                llm_api_key = config.llm.api_key or os.getenv("OPENAI_API_KEY", "")
            else:
                llm_base_url = config.llm.base_url
                llm_api_key = config.llm.api_key
            
            qualifying, rejected = await filter_jobs(
                jobs, cv_text,
                llm_base_url=llm_base_url,
                llm_model=config.llm.model,
                llm_api_key=llm_api_key,
                llm_provider=config.llm.provider,
                min_score=5,  # Lowered from 6 to allow "decent fit"
            )
            save_json(filtered_path, [j.model_dump() for j in qualifying])
            save_json(DATA_DIR / "filtered_out_jobs.json", [j.model_dump() for j in rejected])
        else:
            qualifying_data = load_json(filtered_path)
            qualifying = [Job(**j) for j in qualifying_data]
        print(f"Step 3: {len(qualifying)} jobs qualified")
        
        if step == 3:
            finished_at = datetime.now().isoformat()
            print()
            print("=" * 50)
            print("STEP 3 COMPLETE: Jobs Filtered")
            print("=" * 50)
            print(f"Jobs found: {len(jobs) if jobs else 0}")
            print(f"Jobs qualified: {len(qualifying)}")
            print(f"Jobs filtered: {(len(jobs) - len(qualifying)) if jobs and qualifying else 0}")
            print(f"Output: data/filtered_jobs.json")
            print()
            print("Next: Run --step 4 to find hiring manager emails")
            return RunSummary(
                started_at=started_at,
                finished_at=finished_at,
                jobs_found=len(jobs) if jobs else 0,
                jobs_filtered=len(jobs) - len(qualifying) if jobs and qualifying else 0,
                jobs_qualified=len(qualifying),
                drafts_created=0,
                errors=errors,
            )
    
    # Early return if filter-only mode
    if filter_only:
        finished_at = datetime.now().isoformat()
        rejected_path = DATA_DIR / "filtered_out_jobs.json"
        if rejected_path.exists():
            rejected_data = load_json(rejected_path)
            jobs_filtered = len(rejected_data)
        else:
            jobs_filtered = len(jobs) - len(qualifying)
        return RunSummary(
            started_at=started_at,
            finished_at=finished_at,
            jobs_found=len(jobs),
            jobs_filtered=jobs_filtered,
            jobs_qualified=len(qualifying),
            drafts_created=0,
            errors=errors,
        )
    
    # Step 4: Find Emails (if starting at step 4, load filtered jobs from cache)
    if step <= 4:
        if step == 4 or (step < 4 and not qualifying):
            filtered_path = DATA_DIR / "filtered_jobs.json"
            if filtered_path.exists():
                filtered_data = load_json(filtered_path)
                qualifying = [Job(**j) for j in filtered_data]
                print(f"Step 4: Loaded {len(qualifying)} jobs from cache for email finding")
        
        if qualifying:
            print(f"Step 4: Finding emails for {len(qualifying)} jobs...")
            emails = await find_emails_for_jobs(qualifying, config.email_finder, force=force)
            save_json(DATA_DIR / "emails.json", emails)
            
            valid_count = sum(1 for v in emails.values() if v.get("status") == "valid")
            risky_count = sum(1 for v in emails.values() if v.get("status") == "risky")
            fallback_verified_count = sum(1 for v in emails.values() if v.get("status") == "fallback_verified")
            fallback_inferred_count = sum(1 for v in emails.values() if v.get("status") == "fallback_inferred")
            not_found_count = sum(1 for v in emails.values() if v.get("status") in ("not_found", "error"))
            print(f"Step 4: Found {valid_count}/{len(emails)} emails ({valid_count} valid, {risky_count} risky, {fallback_verified_count} fallback verified, {fallback_inferred_count} fallback inferred, {not_found_count} not found)")
        else:
            print("Step 4: No qualifying jobs to find emails for")
        
        if step == 4:
            finished_at = datetime.now().isoformat()
            print()
            print("=" * 50)
            print("STEP 4 COMPLETE: Emails Found")
            print("=" * 50)
            print(f"Jobs processed: {len(qualifying)}")
            print(f"Valid: {valid_count}, Risky: {risky_count}, Fallback verified: {fallback_verified_count}, Fallback inferred: {fallback_inferred_count}, Not found: {not_found_count}")
            print(f"Output: data/emails.json")
            print()
            print("Next: Run --step 5 to personalize CVs")
            return RunSummary(
                started_at=started_at,
                finished_at=finished_at,
                jobs_found=len(jobs) if 'jobs' in dir() else 0,
                jobs_filtered=0,
                jobs_qualified=len(qualifying),
                drafts_created=0,
                errors=errors,
            )
    
    # Step 5: Personalize CVs (if starting at step 5, load from cache)
    if step <= 5:
        if step == 5 or (step < 5 and not qualifying):
            filtered_path = DATA_DIR / "filtered_jobs.json"
            if filtered_path.exists():
                filtered_data = load_json(filtered_path)
                qualifying = [Job(**j) for j in filtered_data]
                print(f"Step 5: Loaded {len(qualifying)} jobs from cache for CV personalization")
        
        if qualifying:
            print(f"Step 5: Personalizing CVs for {len(qualifying)} jobs...")
            pdf_paths = await personalize_all_filtered(force=force)
            print(f"Step 5: {len(pdf_paths)} CVs generated in data/cvs/")
        else:
            print("Step 5: No qualifying jobs to personalize CVs for")
        
        if step == 5:
            finished_at = datetime.now().isoformat()
            print()
            print("=" * 50)
            print("STEP 5 COMPLETE: CVs Personalized")
            print("=" * 50)
            print(f"CVs generated: {len(pdf_paths)}")
            print(f"Output: data/cvs/ (one folder per job)")
            print()
            print("Next: Run --step 6 to create Gmail drafts")
            return RunSummary(
                started_at=started_at,
                finished_at=finished_at,
                jobs_found=len(jobs) if 'jobs' in dir() else 0,
                jobs_filtered=0,
                jobs_qualified=len(qualifying),
                drafts_created=0,
                errors=errors,
            )
    
    # Step 6: Create Gmail drafts
    if step <= 6:
        if step == 6:
            filtered_path = DATA_DIR / "filtered_jobs.json"
            if filtered_path.exists():
                filtered_data = load_json(filtered_path)
                qualifying = [Job(**j) for j in filtered_data]
                print(f"Step 6: Loaded {len(qualifying)} jobs from cache for Gmail drafts")

        if qualifying:
            print(f"Step 6: Creating Gmail drafts for {len(qualifying)} jobs...")
            drafts_created = 0
            for i, job in enumerate(qualifying[:config.search.count]):
                try:
                    job_dir = DATA_DIR / "cvs" / str(job.id)
                    email_json_path = job_dir / "email.json"
                    pdf_path = job_dir / "personalized_cv.pdf"

                    if not email_json_path.exists():
                        errors.append(f"{job.id}: No email.json found - run step 5 first")
                        continue

                    email_data = load_json(email_json_path)

                    if not dry_run:
                        draft_id = await create_draft(
                            to=email_data.get("to", ""),
                            subject=email_data.get("subject", ""),
                            body=email_data.get("body", ""),
                            attachment_path=pdf_path if pdf_path.exists() else None,
                            credentials_path=config.gmail.credentials_path
                        )
                    else:
                        draft_id = f"dry_run_{i}"

                    drafts_created += 1
                    print(f"  Job {i+1}/{len(qualifying)}: Created draft for {job.company}")

                except Exception as e:
                    errors.append(f"{job.id}: {str(e)}")

            print(f"Step 6: {drafts_created} Gmail drafts created")
        
            if step == 6:
                finished_at = datetime.now().isoformat()
                print()
                print("=" * 50)
                print("STEP 6 COMPLETE: Gmail Drafts Created")
                print("=" * 50)
                print(f"Drafts created: {drafts_created}")
                print(f"Output: Check your Gmail Drafts folder")
                print()
                if errors:
                    print(f"Warnings: {len(errors)}")
                    for e in errors[:3]:
                        print(f"  - {e}")
                return RunSummary(
                    started_at=started_at,
                    finished_at=finished_at,
                    jobs_found=len(jobs) if 'jobs' in dir() else 0,
                    jobs_filtered=0,
                    jobs_qualified=len(qualifying),
                    drafts_created=drafts_created,
                    errors=errors,
                )
        else:
            print("Step 6: No qualifying jobs to create drafts for")
    
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


def _load_jobs_from_apify_cache(jobs_path):
    """Load jobs from cached apify_results.json.
    
    Handles both formats:
    - Raw Apify format (companyName, link, descriptionText, etc.)
    - Already-converted Job model format (company, url, description, etc.)
    """
    raw_data = load_json(jobs_path)
    jobs = []
    
    for i, item in enumerate(raw_data):
        # Detect format: raw Apify has "companyName", Job model has "company"
        if "companyName" in item or "link" in item:
            # Raw Apify format → map to Job
            job = Job(
                id=item.get("id", f"job_{i+1}"),
                title=item.get("title", "Unknown"),
                company=item.get("companyName") or item.get("company") or "Unknown",
                description=item.get("descriptionText", item.get("descriptionHtml", "")),
                url=item.get("link", item.get("url", "")),
                location=item.get("location", ""),
                requirements=_extract_requirements_from_raw(item),
                posted_date=item.get("postedAt", ""),
                accepting_applications=(
                    item.get("applyMethod", {}) != "none"
                    if isinstance(item.get("applyMethod"), str)
                    else True
                ),
                remote_allowed=item.get("workRemoteAllowed"),
                employment_type=item.get("employmentType"),
                seniority_level=item.get("seniorityLevel"),
                company_website=item.get("companyWebsite") or None,
            )
        else:
            # Already a Job model dict
            job = Job(**item)
        
        jobs.append(job)
    
    return jobs


def _extract_requirements_from_raw(item):
    """Extract requirements from raw Apify job item."""
    requirements = []
    for key in ["skills", "experienceLevel", "employmentType", "jobFunction"]:
        if value := item.get(key):
            if isinstance(value, list):
                requirements.extend(value)
            else:
                requirements.append(str(value))
    return requirements
