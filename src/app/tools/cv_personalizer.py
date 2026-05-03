"""CV Personalizer - Generates personalized CV PDFs."""

from pathlib import Path
from ..models import Job


async def personalize_cv(cv_text: str, job: Job) -> Path:
    """Generate personalized CV PDF for a job.
    
    Args:
        cv_text: Base CV text
        job: Job listing
    
    Returns:
        Path to generated PDF
    """
    # Create mock PDF file
    output_dir = Path("data/cvs")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    output_path = output_dir / f"personalized_cv_{job.id}.pdf"
    
    # For now, create a placeholder file
    output_path.write_text(f"Mock PDF for {job.title} at {job.company}")
    
    return output_path


# Real implementation would use Pydantic AI + Jinja2 + WeasyPrint
