"""Job Scraper - Fetches jobs from Apify."""

import httpx
import asyncio
from ..models import Job, ApifyConfig


async def scrape_jobs(urls: list[str], apify_config: ApifyConfig, count: int = 50) -> list[Job]:
    """Scrape jobs from configured URLs using Apify.
    
    Args:
        urls: List of job search URLs
        apify_config: Apify configuration
        count: Maximum number of jobs to scrape
    
    Returns:
        List of Job objects
    """
    if not apify_config.api_token:
        print("Apify API token not configured, using mock data")
        return _get_mock_jobs(count)
    
    return await _scrape_with_apify(urls, apify_config, count)


async def _scrape_with_apify(urls: list[str], config: ApifyConfig, count: int) -> list[Job]:
    """Real Apify implementation using synchronous run endpoint."""
    actor_id = config.actor_id
    actual_count = max(count, 10)
    
    async with httpx.AsyncClient(timeout=180.0) as client:
        print(f"Scraping with Apify actor: {actor_id}")
        
        response = await client.post(
            f"https://api.apify.com/v2/acts/{actor_id}/run-sync-get-dataset-items",
            params={"token": config.api_token},
            headers={"Accept": "application/json"},
            json={
                "urls": urls,
                "count": actual_count,
                "scrapeCompany": True,
                "splitByLocation": False,
            }
        )
        
        if response.status_code not in (200, 201):
            raise Exception(f"Apify request failed: {response.status_code} - {response.text}")
        
        items = response.json()
        
        if isinstance(items, dict) and "data" in items:
            items = items["data"]
        
        if not items:
            print("No jobs returned from Apify")
            return []
        
        print(f"Got {len(items)} jobs from Apify")
        
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
                accepting_applications=item.get("applyMethod", {}) != "none" if isinstance(item.get("applyMethod"), str) else True,
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