"""Cover Letter Generator - Generates personalized cover letters."""

from ..models import Job


async def generate_cover_letter(job: Job, cv_text: str) -> str:
    """Generate personalized cover letter.
    
    Args:
        job: Job listing
        cv_text: Candidate's CV text
    
    Returns:
        Cover letter text
    """
    # Mock implementation
    return f"""Dear Hiring Manager,

I am writing to express my interest in the {job.title} position at {job.company}.

With my experience in software development, I believe I would be a great fit for this role.

Best regards,
John Doe
"""


# Real implementation would use Pydantic AI
