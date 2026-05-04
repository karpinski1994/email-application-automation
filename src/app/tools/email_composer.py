"""Email Composer - Generates personalized application emails for each job."""

import re

from app.models import Job

CANDIDATE_EMAIL = "gabriel.menacho.silva@gmail.com"


def _extract_candidate_email(cv_text: str) -> str:
    match = re.search(r'[\w.+-]+@[\w-]+\.[\w.]+', cv_text)
    return match.group(0) if match else CANDIDATE_EMAIL


def compose_email(job: Job, cv_text: str, cv_data: dict = None, to_email: str = None) -> dict:
    """Generate a personalized application email for a job.

    Uses already-personalized CV data to build the email body without
    an extra LLM call. Falls back to a simple template if cv_data is
    not available.

    Args:
        job: Job listing
        cv_text: Candidate's CV text
        cv_data: Already-personalized CV data from _personalize_cv_content()

    Returns:
        Dict with to, cc, subject, body, attachments.
    """
    candidate_email = _extract_candidate_email(cv_text)

    if cv_data:
        name = cv_data.get("name", "Gabriel Menacho")
        summary = cv_data.get("tailored_summary") or cv_data.get("summary", "")
        skills = cv_data.get("tailored_skills") or cv_data.get("skills_flat") or cv_data.get("skills", "")

        body = (
            f"Dear Hiring Team,\n\n"
            f"I am writing to apply for the {job.title} position at {job.company}. "
            f"{summary}\n\n"
            f"My key strengths for this role include: {skills}. "
            f"I would welcome the opportunity to discuss how my experience aligns with your team's needs.\n\n"
            f"Please find my CV attached for your review. I look forward to hearing from you.\n\n"
            f"Best regards,\n{name}"
        )
    else:
        body = (
            f"Dear Hiring Team,\n\n"
            f"I am writing to express my interest in the {job.title} position at {job.company}. "
            f"Please find my CV attached for your review.\n\n"
            f"Best regards,\nGabriel Menacho"
        )

    return {
        "to": to_email or f"PENDING: find email for {job.company}",
        "cc": candidate_email,
        "subject": f"RE: {job.title}",
        "body": body,
        "attachments": ["personalized_cv.html"],
    }
