"""Job Scraper - Fetches jobs from Apify."""

import httpx
from ..models import Job


async def scrape_jobs(urls: list[str], count: int = 50) -> list[Job]:
    """Scrape jobs from configured URLs using Apify.
    
    Args:
        urls: List of job search URLs
        count: Maximum number of jobs to scrape
    
    Returns:
        List of Job objects
    """
    # Mock implementation for testing
    return _get_mock_jobs(count)


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


# Real implementation (when ready):
# async def scrape_jobs(urls: list[str], config: Config) -> list[Job]:
#     """Real Apify implementation."""
#     async with httpx.AsyncClient() as client:
#         response = await client.post(
#             "https://api.apify.com/v2/acts/...",
#             json={"urls": urls},
#             headers={"Authorization": f"Bearer {config.api_keys.apify}"}
#         )
#         # Parse response...
