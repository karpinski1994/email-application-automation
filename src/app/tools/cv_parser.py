"""CV Parser - Extracts text from CV files."""

from pathlib import Path
import pdfplumber


def parse_cv(path: str) -> str:
    """Parse CV file and return text content.
    
    Args:
        path: Path to CV file (PDF or TXT)
    
    Returns:
        Extracted text content
    
    Raises:
        ValueError: If file format is not supported
    """
    cv_path = Path(path)
    
    if not cv_path.exists():
        raise FileNotFoundError(f"CV file not found: {path}")
    
    suffix = cv_path.suffix.lower()
    
    if suffix == ".pdf":
        return _parse_pdf(cv_path)
    elif suffix == ".txt":
        return cv_path.read_text()
    else:
        raise ValueError(f"Unsupported CV format: {suffix}")


def _parse_pdf(path: Path) -> str:
    """Extract text from PDF using pdfplumber."""
    with pdfplumber.open(path) as pdf:
        pages = [page.extract_text() for page in pdf.pages]
    return "\n\n".join([p for p in pages if p])


# Mock version for testing without real CV
def parse_cv_mock() -> str:
    """Return mock CV text for testing."""
    return """
John Doe
Email: john.doe@email.com | Phone: (555) 123-4567 | Location: San Francisco, CA

PROFESSIONAL SUMMARY
Experienced software engineer with 5+ years of experience in Python, JavaScript, and cloud technologies.

WORK EXPERIENCE
Senior Python Developer at Tech Corp (2020 - Present)
- Built microservices using FastAPI and Docker
- Reduced API latency by 40% through caching optimization

Python Developer at Startup Inc (2018 - 2020)
- Developed REST APIs using Flask and PostgreSQL
- Implemented CI/CD pipelines using GitHub Actions

SKILLS
Python, JavaScript, TypeScript, React, Node.js, AWS, Docker, PostgreSQL, MongoDB

EDUCATION
Bachelor of Science in Computer Science, University of California, 2018
"""
