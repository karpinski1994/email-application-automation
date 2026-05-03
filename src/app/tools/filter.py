"""Job Filter - Filters jobs based on qualifications."""

from ..models import Job, FilterDecision


async def filter_jobs(jobs: list[Job], cv_text: str) -> tuple[list[Job], list[Job]]:
    """Filter jobs by qualification match and accepting status.
    
    Args:
        jobs: List of job listings
        cv_text: Candidate's CV text
    
    Returns:
        Tuple of (qualifying_jobs, rejected_jobs)
    """
    # Mock: Return first 5 as qualified
    qualifying = jobs[:5]
    rejected = jobs[5:]
    return qualifying, rejected


# Real implementation would use Pydantic AI with result_type=FilterDecision
