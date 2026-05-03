"""Job Scraper - Fetches jobs from Apify LinkedIn Jobs Scraper.

Uses the async run approach (POST /runs → poll status → GET dataset items)
to avoid the 300s timeout limitation of the synchronous endpoint.
This is critical because LinkedIn job scraping can take 5-20 minutes
depending on the number of results and URLs.

Actor: curious_coder/linkedin-jobs-scraper (ID: hKByXkMQaC5Qt9UMN)
Docs: https://apify.com/curious_coder/linkedin-jobs-scraper/api
"""

import httpx
import asyncio
from ..models import Job, ApifyConfig

# Apify API base
APIFY_API_BASE = "https://api.apify.com/v2"

# Polling config
POLL_INTERVAL_SECONDS = 10
MAX_POLL_DURATION_SECONDS = 1200  # 20 minutes max wait


async def scrape_jobs(urls: list[str], apify_config: ApifyConfig, count: int = 50) -> list[Job]:
    """Scrape jobs from configured URLs using Apify.
    
    Args:
        urls: List of LinkedIn job search URLs
        apify_config: Apify configuration (api_token, actor_id)
        count: Maximum number of jobs to scrape
    
    Returns:
        List of Job objects
    """
    if not apify_config.api_token:
        print("⚠️  Apify API token not configured, using mock data")
        return _get_mock_jobs(count)
    
    return await _scrape_with_apify(urls, apify_config, count)


async def _scrape_with_apify(urls: list[str], config: ApifyConfig, count: int) -> list[Job]:
    """Scrape LinkedIn jobs using async Apify run with polling.
    
    Flow:
    1. POST /v2/acts/{actor_id}/runs  → starts the actor, returns run metadata
    2. Poll GET /v2/actor-runs/{runId} every 10s until status is terminal
    3. GET /v2/datasets/{datasetId}/items → fetch the scraped job data
    
    This avoids the 300s timeout of the synchronous endpoint and handles
    long-running scrapes (5-20 minutes) gracefully.
    """
    actor_id = config.actor_id
    # Actor requires count >= 10
    actual_count = max(count, 10)
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        # ── Step 1: Start the actor run ──────────────────────────────
        print(f"🚀 Starting Apify actor: {actor_id}")
        print(f"   URLs: {len(urls)} search URLs")
        print(f"   Count: {actual_count} jobs requested")
        
        start_response = await client.post(
            f"{APIFY_API_BASE}/acts/{actor_id}/runs",
            params={"token": config.api_token},
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            json={
                "urls": urls,
                "count": actual_count,
                "scrapeCompany": True,
                "splitByLocation": False,
            }
        )
        
        if start_response.status_code not in (200, 201):
            raise Exception(
                f"Apify run start failed: {start_response.status_code} - {start_response.text}"
            )
        
        run_data = start_response.json().get("data", start_response.json())
        run_id = run_data["id"]
        dataset_id = run_data.get("defaultDatasetId")
        
        print(f"✅ Run started: {run_id}")
        print(f"   Dataset ID: {dataset_id}")
        print(f"   Console: https://console.apify.com/actors/runs/{run_id}")
        
        # ── Step 2: Poll until the run finishes ──────────────────────
        elapsed = 0
        final_status = None
        
        while elapsed < MAX_POLL_DURATION_SECONDS:
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
            elapsed += POLL_INTERVAL_SECONDS
            
            status_response = await client.get(
                f"{APIFY_API_BASE}/actor-runs/{run_id}",
                params={"token": config.api_token},
            )
            
            if status_response.status_code != 200:
                print(f"⚠️  Poll error ({status_response.status_code}), retrying...")
                continue
            
            status_data = status_response.json().get("data", status_response.json())
            current_status = status_data.get("status", "UNKNOWN")
            
            # Show progress every 30 seconds
            if elapsed % 30 == 0 or current_status not in ("RUNNING", "READY"):
                print(f"   ⏳ [{elapsed}s] Status: {current_status}")
            
            # Terminal statuses
            if current_status in ("SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"):
                final_status = current_status
                dataset_id = status_data.get("defaultDatasetId", dataset_id)
                break
        
        if final_status is None:
            raise Exception(
                f"Apify run timed out after {MAX_POLL_DURATION_SECONDS}s. "
                f"Run ID: {run_id} — check https://console.apify.com/actors/runs/{run_id}"
            )
        
        # ── Step 3: Fetch dataset items ──────────────────────────────
        # IMPORTANT: Fetch items even on ABORTED status — partial data is
        # still available in the dataset (as noted in the actor's issue tracker).
        if final_status in ("FAILED", "TIMED-OUT"):
            print(f"⚠️  Run ended with status: {final_status}")
            print(f"   Attempting to fetch any partial results from dataset...")
        elif final_status == "ABORTED":
            print(f"⚠️  Run was ABORTED (possible account limit hit)")
            print(f"   Fetching partial results from dataset...")
        else:
            print(f"✅ Run SUCCEEDED")
        
        if not dataset_id:
            raise Exception(f"No dataset ID available for run {run_id}")
        
        items_response = await client.get(
            f"{APIFY_API_BASE}/datasets/{dataset_id}/items",
            params={
                "token": config.api_token,
                "format": "json",
                "clean": "true",
            },
            timeout=60.0,
        )
        
        if items_response.status_code != 200:
            raise Exception(
                f"Failed to fetch dataset items: {items_response.status_code} - {items_response.text}"
            )
        
        items = items_response.json()
        
        if not items or not isinstance(items, list):
            print("⚠️  No jobs returned from Apify dataset")
            return []
        
        print(f"📦 Got {len(items)} jobs from Apify dataset")
        
        # ── Step 4: Map to Job models ────────────────────────────────
        jobs = []
        for i, item in enumerate(items[:count]):
            job = Job(
                id=f"job_{i+1}",
                title=item.get("title", "Unknown"),
                company=item.get("companyName") or item.get("company") or "Unknown",
                description=item.get("descriptionText", item.get("descriptionHtml", "")),
                url=item.get("link", item.get("url", "")),
                location=item.get("location", ""),
                requirements=_extract_requirements(item),
                posted_date=item.get("postedAt", ""),
                accepting_applications=(
                    item.get("applyMethod", {}) != "none"
                    if isinstance(item.get("applyMethod"), str)
                    else True
                ),
            )
            jobs.append(job)
        
        return jobs


def _extract_requirements(item: dict) -> list[str]:
    """Extract requirements from job item."""
    requirements = []
    for key in ["skills", "experienceLevel", "employmentType", "jobFunction"]:
        if value := item.get(key):
            if isinstance(value, list):
                requirements.extend(value)
            else:
                requirements.append(str(value))
    return requirements


def _get_mock_jobs(count: int) -> list[Job]:
    """Generate mock jobs for testing."""
    jobs = []
    for i in range(min(count, 10)):
        jobs.append(Job(
            id=f"job_{i+1}",
            title=f"Python Developer - Position {i+1}",
            company=f"Tech Company {i+1}",
            description=f"We are looking for a Python developer to join our team. "
                       f"Requirements: Python, Django, PostgreSQL, 3+ years experience.",
            url=f"https://example.com/jobs/{i+1}",
            location="San Francisco, CA",
            requirements=["Python", "Django", "PostgreSQL"],
            accepting_applications=True
        ))
    return jobs