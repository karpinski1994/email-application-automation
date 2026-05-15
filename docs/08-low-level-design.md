# Low-Level Design – AI Automated Email Job Application System

## Component Detailed Design

### Directory Structure

```
src/
├── app/
│   ├── __init__.py
│   ├── __main__.py          # Entry point: python -m app
│   ├── config.py           # Config loading from YAML + .env
│   ├── agent.py            # Pipeline orchestrator (async)
│   ├── models.py           # Pydantic data models
│   ├── utils.py            # Shared utilities (save_json, load_json, DATA_DIR)
│   │
│   ├── tools/              # Pipeline step implementations
│   │   ├── cv_parser.py       # PDF/TXT CV parsing (pdfplumber)
│   │   ├── scraper.py         # Apify LinkedIn job scraping (async polling)
│   │   ├── filter.py          # Two-stage job filtering (embedding + LLM)
│   │   ├── email_finder.py    # AnyMailFinder API with web fallback
│   │   ├── web_email_finder.py # Web search fallback for emails
│   │   ├── cv_personalizer.py # CV personalization with PDF generation
│   │   ├── email_composer.py  # Email subject/body generation
│   │   ├── cover_letter.py    # (legacy, now in email_composer)
│   │   ├── gmail_draft.py     # Gmail API integration (OAuth2)
│   │   ├── applied_tracker.py  # Track applied jobs
│   │   └── __init__.py
│   │
│   └── templates/
│       └── cv_template.html   # Jinja2 CV HTML template
│
├── data/                   # Generated at runtime (gitignored)
├── config.yaml             # Main configuration
├── config.example.yaml     # Example configuration
├── .env                    # API keys (gitignored)
├── pyproject.toml
└── README.md
```

---

## Class & Object Design

### Core Data Models (`models.py`)

```python
from pydantic import BaseModel, Field
from typing import Optional
from pathlib import Path

# === Configuration Models ===

class SearchConfig(BaseModel):
    urls: list[str] = Field(min_length=1, description="List of job search URLs")
    count: int = Field(default=100, ge=1, le=200, description="Max jobs to process")

class CVConfig(BaseModel):
    path: str = Field(description="Path to CV file (PDF or TXT)")

class GmailConfig(BaseModel):
    draft_only: bool = True
    token_path: str = "data/gmail_token.json"
    credentials_path: str = "credentials.json"

class LLMConfig(BaseModel):
    provider: str = "local"  # "local" (Ollama) or "openai"
    model: str = "qwen2.5:7b"
    base_url: str = "http://localhost:11434/v1"
    api_key: str = "ollama"

class ApifyConfig(BaseModel):
    api_token: str = ""
    actor_id: str = "apify/linkedin-jobs-scraper"

class FilterConfig(BaseModel):
    embedding_shortlist_size: int = 20
    llm_fit_threshold: int = 70
    embedding_model: str = "nomic-embed-text"
    scoring_model: str = "llama3.2"

class EmailFinderConfig(BaseModel):
    provider: str = "anymailfinder"
    api_key: str = ""
    categories: list[str] = Field(default_factory=lambda: ["engineering", "hr"])
    max_domain_attempts: int = 3
    fallback_enabled: bool = True
    fallback_max_attempts: int = 3

class PrivacyConfig(BaseModel):
    redact_pii: bool = True

# === Main Config ===
class Config(BaseModel):
    search: SearchConfig
    cv: CVConfig
    gmail: GmailConfig
    llm: LLMConfig = Field(default_factory=LLMConfig)
    apify: ApifyConfig = Field(default_factory=ApifyConfig)
    filter: FilterConfig = Field(default_factory=FilterConfig)
    email_finder: EmailFinderConfig = Field(default_factory=EmailFinderConfig)
    privacy: PrivacyConfig = Field(default_factory=PrivacyConfig)
    dry_run: bool = False

# === Job Model ===
class Job(BaseModel):
    id: str
    title: str
    company: str
    description: str
    url: str
    location: Optional[str] = None
    hiring_manager_name: Optional[str] = None
    requirements: list[str] = Field(default_factory=list)
    posted_date: Optional[str] = None
    accepting_applications: Optional[bool] = None
    rejection_reason: Optional[str] = None
    # Additional fields from Apify
    remote_allowed: Optional[bool] = None
    employment_type: Optional[str] = None
    seniority_level: Optional[str] = None
    company_website: Optional[str] = None

class FilterDecision(BaseModel):
    is_qualified: bool
    is_accepting_applications: bool
    reason: Optional[str] = None

class CVData(BaseModel):
    name: str
    email: str
    phone: str
    location: str
    summary: str
    experience: list[dict]
    skills: str
    education: str

class RunSummary(BaseModel):
    started_at: str
    finished_at: str
    jobs_found: int
    jobs_filtered: int
    jobs_qualified: int
    drafts_created: int
    errors: list[str]
```

---

## Utility Functions (`utils.py`)

```python
import json
from pathlib import Path
from typing import Any

# Constants
DATA_DIR = Path("data")

def is_cached(path: Path) -> bool:
    """Check if a cache file exists and is not empty."""
    return path.exists() and path.stat().st_size > 0

def save_json(path: Path, data: list | dict) -> None:
    """Save data to JSON file with atomic write (temp + rename)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(".tmp")
    temp_path.write_text(json.dumps(data, indent=2, default=str))
    temp_path.rename(path)

def load_json(path: Path) -> list | dict:
    """Load data from JSON file."""
    return json.loads(path.read_text())

def ensure_data_dir() -> None:
    """Ensure data directory exists."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
```

---

## Config Loader (`config.py`)

```python
import os
import yaml
from pathlib import Path
from dotenv import load_dotenv
from .models import Config

def load_config(config_path: str = "config.yaml") -> Config:
    """Load configuration from YAML file and .env."""
    load_dotenv()
    
    config_file = Path(config_path)
    if not config_file.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    
    with open(config_file) as f:
        raw = yaml.safe_load(f)
    
    # Substitute env vars
    if "apify" in raw and "api_token" in raw["apify"]:
        raw["apify"]["api_token"] = os.getenv("APIFY_API_KEY", raw["apify"].get("api_token", ""))
    
    if "email_finder" in raw and "api_key" in raw["email_finder"]:
        raw["email_finder"]["api_key"] = os.getenv("ANYMAILFINDER_API_KEY", raw["email_finder"].get("api_key", ""))
    
    return Config(**raw)

def get_api_key(key: str) -> str:
    """Get API key from environment variable."""
    return os.getenv(key, "")
```

---

## CV Parser (`tools/cv_parser.py`)

```python
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
    return """John Doe
Email: john.doe@email.com | Phone: (555) 123-4567 | Location: San Francisco, CA

PROFESSIONAL SUMMARY
Experienced software engineer with 5+ years of experience in Python, JavaScript, and cloud technologies.

WORK EXPERIENCE
Senior Python Developer at Tech Corp (2020 - Present)
- Built microservices using FastAPI and Docker

SKILLS
Python, JavaScript, TypeScript, React, Node.js, AWS, Docker, PostgreSQL, MongoDB

EDUCATION
Bachelor of Science in Computer Science, University of California, 2018"""
```

---

## Scraper (`tools/scraper.py`)

```python
import httpx
import asyncio
from ..models import Job, ApifyConfig

APIFY_API_BASE = "https://api.apify.com/v2"
POLL_INTERVAL_SECONDS = 10
MAX_POLL_DURATION_SECONDS = 1200  # 20 minutes

async def scrape_jobs(urls: list[str], apify_config: ApifyConfig, count: int = 50) -> list[Job]:
    """Scrape jobs from configured URLs using Apify.
    
    Uses async run approach (POST /runs → poll status → GET dataset items)
    to avoid the 300s timeout limitation of the synchronous endpoint.
    
    Actor: apify/linkedin-jobs-scraper
    """
    if not apify_config.api_token:
        print("⚠️  Apify API token not configured, using mock data")
        return _get_mock_jobs(count)
    
    return await _scrape_with_apify(urls, apify_config, count)

async def _scrape_with_apify(urls: list[str], config: ApifyConfig, count: int) -> list[Job]:
    """Async Apify run with polling - handles long-running scrapes."""
    # 1. Start actor run
    start_response = await client.post(
        f"{APIFY_API_BASE}/acts/{config.actor_id}/runs",
        params={"token": config.api_token},
        json={"urls": urls, "count": max(count, 10), "scrapeCompany": True}
    )
    run_id = start_response.json()["data"]["id"]
    
    # 2. Poll until finished
    while elapsed < MAX_POLL_DURATION_SECONDS:
        await asyncio.sleep(POLL_INTERVAL_SECONDS)
        status_response = await client.get(
            f"{APIFY_API_BASE}/actor-runs/{run_id}",
            params={"token": config.api_token}
        )
        current_status = status_response.json()["data"]["status"]
        if current_status in ("SUCCEEDED", "FAILED", "ABORTED"):
            break
    
    # 3. Fetch dataset items
    items_response = await client.get(
        f"{APIFY_API_BASE}/datasets/{dataset_id}/items",
        params={"token": config.api_token, "format": "json", "clean": "true"}
    )
    items = items_response.json()
    
    # 4. Map to Job models
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
            remote_allowed=item.get("workRemoteAllowed"),
            employment_type=item.get("employmentType"),
            seniority_level=item.get("seniorityLevel"),
        )
        jobs.append(job)
    return jobs
```

---

## Filter (`tools/filter.py`)

```python
import asyncio
import httpx
from pathlib import Path
from ..models import Job

# Two-stage filtering:
# Stage 1: Embedding-based pre-filtering (nomic-embed-text via Ollama)
# Stage 2: LLM detailed scoring (llama3.2 via Ollama)

SYSTEM_PROMPT = """You are a technical recruiter. Score job-CV fit from 0-100.

IMPORTANT RULES:
1. You MUST score EVERY job listed in the user message
2. You MUST use the exact format: JOB_ID | SCORE | REASON
3. NO other text, NO explanations, NO summaries
4. Frontend/React/TypeScript roles = good fit (score 40-90)
5. Backend-only/Java/Django roles = low score (0-30)
6. Junior/Entry roles = score 0-20

SCORING:
- 80-100: Perfect (React+TS, senior/lead, remote/LATAM)
- 60-79: Strong (React+TS role, maybe some gaps)
- 40-59: Good (Frontend with React, seniority OK)
- 20-39: Weak (Frontend but different stack)
- 0-19: No match (backend-only, mobile, junior)"""

async def filter_jobs(
    jobs: list[Job],
    cv_text: str,
    llm_base_url: str = "http://localhost:11434/v1",
    llm_model: str = "qwen2.5:7b",
    llm_api_key: str = "ollama",
    llm_provider: str = "local",
    min_score: int = 5,
) -> tuple[list[Job], list[Job]]:
    """Filter jobs using two-stage approach.
    
    Stage 1: Embedding similarity (nomic-embed-text) — top N jobs pass.
    Stage 2: LLM scoring (llama3.2) — batch scoring, threshold filter.
    
    Returns:
        (qualifying_jobs, rejected_jobs)
    """
    raw_path = Path("data/apify_results.json")
    if not raw_path.exists():
        return [], list(jobs)
    
    # Pre-filter: remove jobs without company website
    raw_data = json.loads(raw_path.read_text())
    website_filtered = [item for item in raw_data if item.get("companyWebsite")]
    
    # Stage 1: Embedding pre-filtering
    cv_embedding = _get_embedding(cv_text[:2000], "nomic-embed-text")
    shortlist = _stage1_embedding_filter(website_filtered, cv_text, filter_config, cv_embedding)
    
    # Stage 2: LLM scoring
    scored = await _stage2_llm_scoring(shortlist, cv_text, filter_config, "llama3.2")
    
    # Apply threshold
    qualifying, rejected = [], []
    for idx, item, score, reason in scored:
        job = _raw_to_job(item, idx, score, reason)
        if score >= filter_config.llm_fit_threshold:
            qualifying.append(job)
        else:
            job.rejection_reason = f"LLM score {score}/100: {reason}"
            rejected.append(job)
    
    return qualifying, rejected
```

---

## CV Personalizer (`tools/cv_personalizer.py`)

```python
import asyncio
import json
import re
from pathlib import Path
from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML
from app.models import Job
from app.config import load_config

# Deterministic CV parsing - no LLM needed for parsing structure
def _parse_cv_text(cv_text: str) -> dict:
    """Parse cv.txt into structured dict based on known format:
    - Line 1: Name
    - Line 2: Title  
    - Lines 3-5: Contact info
    - "About" section -> summary
    - "Tech Stack" section -> skills dict
    - "Experience" section -> list of jobs
    - "Education" section -> list
    """
    lines = cv_text.strip().split("\n")
    # ... deterministic parsing using regex for each section
    return {"name": ..., "title": ..., "summary": ..., "skills": {...}, ...}

async def _tailor_for_job(cv_data: dict, job: Job) -> dict:
    """Quick LLM call to generate:
    - tailored_summary: 2-3 sentence summary for this job
    - tailored_skills: comma-separated skills reordered by relevance  
    - cv_title: adaptive job title for CV header
    """
    # Calls LLM via httpx to get tailored content
    return {"tailored_summary": ..., "tailored_skills": ..., "cv_title": ...}

async def personalize_cv(cv_text: str, job: Job, force: bool = False, to_email: str = None) -> Path:
    """Generate personalized CV for a job.
    
    1. Parse base CV text deterministically
    2. LLM call to tailor summary/skills/title for job
    3. Render Jinja2 template (src/app/templates/cv_template.html)
    4. Convert HTML to PDF via weasyprint
    5. Generate email via email_composer
    
    Output: data/cvs/{job_id}/personalized_cv.pdf + email.json
    """
    job_dir = Path("data/cvs") / str(job.id)
    job_dir.mkdir(parents=True, exist_ok=True)
    
    cv_data = get_parsed_cv(cv_text)
    tailored = await _tailor_for_job(cv_data, job)
    cv_data = {**cv_data, **tailored}
    
    # Load Jinja2 template
    template_dir = Path("src/app/templates")
    env = Environment(loader=FileSystemLoader(str(template_dir)))
    template = env.get_template("cv_template.html")
    
    html_content = template.render(**cv_data)
    output_path = job_dir / "personalized_cv.html"
    output_path.write_text(html_content)
    
    # Convert to PDF
    pdf_path = job_dir / "personalized_cv.pdf"
    HTML(string=html_content).write_pdf(pdf_path)
    
    # Generate email
    from app.tools.email_composer import compose_email
    email_data = compose_email(job, cv_text, cv_data=cv_data, to_email=to_email)
    (job_dir / "email.json").write_text(json.dumps(email_data, indent=2))
    
    return output_path
```

---

## Email Finder (`tools/email_finder.py`)

```python
import asyncio
import json
import re
import httpx
from pathlib import Path
from ..models import EmailFinderConfig, Job

ANYMAILFINDER_URL = "https://api.anymailfinder.com/v5.1/find-email/decision-maker"

def _extract_domain_from_url(url: str) -> str:
    """Extract domain from URL like 'https://www.govcio.com' -> 'govcio.com'."""
    domain = url.strip()
    for prefix in ("https://", "http://", "www."):
        domain = domain.replace(prefix, "")
    return domain.rstrip("/")

def _company_to_domains(company: str) -> list[str]:
    """Generate candidate domains from company name (cleans suffixes, tries .com/.io/.co)."""
    suffixes = ["Inc.", "LLC", "LTD", "Ltd.", "Corp.", "Co.", "Inc", "PBC"]
    cleaned = company
    for s in suffixes:
        cleaned = cleaned.replace(s, "")
    cleaned = re.sub(r'[^a-zA-Z0-9]', '', cleaned).lower()
    return [f"{cleaned}.com", f"{cleaned}.io", f"{cleaned}.co"]

async def find_email_for_job(
    job: Job,
    api_key: str,
    categories: list[str],
    max_attempts: int = 3,
) -> dict:
    """Find hiring manager email via AnyMailFinder.
    
    Uses job.company_website for domain if available, otherwise guesses.
    
    Returns:
        {"email": str, "status": "valid"|"risky"|"not_found"|"error"|"credit_exhausted", ...}
    """
    # Prefer company_website, else guess from company name
    if job.company_website:
        domain = _extract_domain_from_url(job.company_website)
        if domain:
            domains = [domain]
    else:
        domains = _company_to_domains(job.company)
    
    for domain in domains[:max_attempts]:
        response = await httpx.post(
            ANYMAILFINDER_URL,
            headers={"Authorization": api_key, "Content-Type": "application/json"},
            json={"domain": domain, "decision_maker_category": categories},
            timeout=30.0
        )
        if response.status_code == 200:
            data = response.json()
            email = data.get("email", "")
            # ... status determination logic
    
    # Fallback: web search via web_email_finder.py
    return {"email": ..., "status": ...}
```

---

## Email Composer (`tools/email_composer.py`)

```python
import re
from app.models import Job

CANDIDATE_EMAIL = "jon.doe@gmail.com"

def _extract_candidate_email(cv_text: str) -> str:
    """Extract email from CV text using regex."""
    match = re.search(r'[\w.+-]+@[\w-]+\.[\w.]+', cv_text)
    return match.group(0) if match else CANDIDATE_EMAIL

def compose_email(job: Job, cv_text: str, cv_data: dict = None, to_email: str = None) -> dict:
    """Generate personalized application email for a job.
    
    Uses already-personalized CV data (tailored_summary, tailored_skills)
    to build email body without extra LLM call.
    
    Args:
        job: Job listing
        cv_text: Candidate's CV text
        cv_data: Already-personalized CV data from cv_personalizer
    
    Returns:
        Dict with to, cc, subject, body keys
    """
    candidate_email = _extract_candidate_email(cv_text)
    
    if cv_data:
        name = cv_data.get("name", "Jon Doe")
        summary = cv_data.get("tailored_summary") or cv_data.get("summary", "")
        skills = cv_data.get("tailored_skills") or cv_data.get("skills_flat", "")
        
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
            f"Best regards,\nJon Doe"
        )
    
    return {
        "to": to_email or f"PENDING: find email for {job.company}",
        "cc": candidate_email,
        "subject": f"RE: {job.title}",
        "body": body,
        "attachments": ["personalized_cv.html"],
    }
```

---

## Gmail Draft (`tools/gmail_draft.py`)

```python
import base64
import json
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

SCOPES = ['https://www.googleapis.com/auth/gmail.compose']

def _load_credentials(credentials_path: str = "credentials.json"):
    """Load OAuth credentials from JSON file.
    
    Uses cached token if valid, otherwise runs OAuth flow.
    First run: opens browser for consent.
    Token saved to data/gmail_token.json.
    """
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    
    creds = None
    token_path = Path("data/gmail_token.json")
    
    if token_path.exists():
        creds = Credentials.from_authorized_user_info(
            json.loads(token_path.read_text()), SCOPES
        )
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(None)
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                credentials_path, SCOPES
            )
            creds = flow.run_local_server(port=0)
        
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(creds.to_json())
    
    return creds

def _create_mime_message(to: str, subject: str, body: str, attachment_path: Path = None) -> str:
    """Create a MIME message for the email."""
    message = MIMEMultipart()
    message['to'] = to
    message['subject'] = subject
    message.attach(MIMEText(body, 'plain'))
    
    if attachment_path and attachment_path.exists():
        import email.mime.application
        with open(attachment_path, 'rb') as f:
            att = email.mime.application.MIMEApplication(f.read(), _subtype='pdf')
        att.add_header('Content-Disposition', 'attachment', filename=attachment_path.name)
        message.attach(att)
    
    return base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')

async def create_draft(
    to: str,
    subject: str,
    body: str,
    attachment_path: Path,
    credentials_path: str = "credentials.json"
) -> str:
    """Create Gmail draft with PDF attachment.
    
    Returns:
        Draft ID on success, "error: ..." on failure
    """
    try:
        from googleapiclient.discovery import build
        
        creds = _load_credentials(credentials_path)
        service = build('gmail', 'v1', credentials=creds)
        
        raw_message = _create_mime_message(to, subject, body, attachment_path)
        
        draft = {
            'message': {'raw': raw_message}
        }
        
        result = service.users().drafts().create(
            userId='me',
            body=draft
        ).execute()
        
        draft_id = result.get('id')
        logger.info(f"Created Gmail draft: {draft_id}")
        
        # Save draft metadata
        cache_file = Path(f"data/drafts/{draft_id}.json")
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps({
            "to": to,
            "subject": subject,
            "draft_id": draft_id
        }))
        
        return draft_id
    
    except Exception as e:
        logger.error(f"Failed to create Gmail draft: {e}")
        return f"error: {str(e)}"
```

---

## Applied Tracker (`tools/applied_tracker.py`)

```python
import json
from pathlib import Path
from datetime import datetime
from app.utils import DATA_DIR

class AppliedTracker:
    """Track jobs that have been applied to avoid duplicates."""
    
    def __init__(self, path: Path = None):
        self.path = path or DATA_DIR / "processed_jobs.json"
        self._ensure_file()
    
    def _ensure_file(self):
        if not self.path.exists():
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text("[]")
    
    def _load(self) -> list:
        return json.loads(self.path.read_text())
    
    def _save(self, data: list):
        self.path.write_text(json.dumps(data, indent=2))
    
    def is_applied(self, job_url: str) -> bool:
        """Check if job URL has already been applied to."""
        applied = self._load()
        return any(entry.get("job_url") == job_url for entry in applied)
    
    def mark_applied(self, job_url: str, company: str, draft_id: str = None, 
                  subject: str = None, to: str = None):
        """Mark a job as applied."""
        applied = self._load()
        applied.append({
            "job_url": job_url,
            "company": company,
            "draft_id": draft_id,
            "subject": subject,
            "to": to,
            "applied_at": datetime.now().isoformat()
        })
        self._save(applied)
    
    def get_applied_count(self) -> int:
        """Get count of applied jobs."""
        return len(self._load())
```

---

## Orchestrator (`agent.py`)

```python
import asyncio
import json
from datetime import datetime
from pathlib import Path

from app.models import Job, RunSummary
from app.utils import DATA_DIR, ensure_data_dir, is_cached, load_json, save_json

async def run(config, force=False, step=1, dry_run=False, filter_only=False, explicit_step=False, include_applied=False, cached=False):
    """Pipeline orchestrator.
    
    Supports stepping: --step N starts from specific step (1-6).
    Supports caching: each step loads from data/*.json if exists.
    Supports dry-run: skips external API calls.
    """
    ensure_data_dir()
    started_at = datetime.now().isoformat()
    errors = []
    
    # Load Lazy imports - only load modules when actually needed
    if step <= 1:
        from app.tools.cv_parser import parse_cv, parse_cv_mock
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
    
    # Validate prerequisites
    validate_prerequisites(step)
    
    # Show applied jobs count
    if not include_applied:
        try:
            from app.tools.applied_tracker import AppliedTracker
            tracker = AppliedTracker()
            applied_count = tracker.get_applied_count()
            if applied_count > 0:
                print(f"📋 {applied_count} jobs already applied (will be skipped)")
        except Exception:
            pass
    
    # Step 1: Parse CV
    cv_path = DATA_DIR / "cv_parsed.json"
    if step <= 1:
        if force or not is_cached(cv_path):
            try:
                cv_text = parse_cv(config.cv.path)
            except FileNotFoundError:
                cv_text = parse_cv_mock()
            save_json(cv_path, {"text": cv_text})
        else:
            cv_text = load_json(cv_path).get("text", "")
        print(f"Step 1: CV parsed ({len(cv_text)} chars)")
        
        if step == 1 and explicit_step:
            return RunSummary(...)
    
    # Step 2: Scrape jobs (from cache or Apify)
    jobs_path = DATA_DIR / "apify_results.json"
    if step <= 2:
        if is_cached(jobs_path) and cached:
            jobs = _load_jobs_from_apify_cache(jobs_path)
            print(f"Step 2: Loaded {len(jobs)} jobs from cache (skipping Apify call)")
        else:
            jobs = await scrape_jobs(config.search.urls, config.apify, config.search.count)
            save_json(jobs_path, [j.model_dump() for j in jobs])
            print(f"Step 2: Scraped {len(jobs)} jobs")
    
    # Step 3: Filter jobs (two-stage: embedding + LLM)
    if step <= 3:
        # Filter out already-applied jobs (with safety wraps)
        if not include_applied:
            from app.tools.applied_tracker import AppliedTracker
            tracker = AppliedTracker()
            jobs = [j for j in jobs if not tracker.is_applied(j.url)]
        
        # Stage 1 + Stage 2 filtering with LLM
        qualifying, rejected = await filter_jobs(...)
        print(f"Step 3: {len(qualifying)} jobs qualified")
    
    # Early return if filter-only mode
    if filter_only:
        return RunSummary(...)
    
    # Step 4: Find Emails
    if step <= 4:
        emails = await find_emails_for_jobs(qualifying, config.email_finder, force=force)
        print(f"Step 4: Found {valid_count}/{len(emails)} emails")
    
    # Step 5: Personalize CVs
    if step <= 5:
        pdf_paths = await personalize_all_filtered(force=force)
        print(f"Step 5: {len(pdf_paths)} CVs generated")
    
    # Step 6: Create Gmail drafts
    if step <= 6:
        drafts_created = 0
        for job in qualifying[:config.search.count]:
            draft_id = await create_draft(...)
            drafts_created += 1
        
        if tracker:
            tracker.mark_applied(job_url=job.url, company=job.company, ...)
        
        print(f"Step 6: {drafts_created} Gmail drafts created")
    
    # Save run summary
    summary = RunSummary(...)
    save_json(DATA_DIR / "run_summary.json", summary.model_dump())
    return summary
```

---

## Database Schema – Physical Design

**No database used.** Flat files only:

| File | Format | Contents |
|------|--------|---------|
| `config.yaml` | YAML | User configuration |
| `.env` | ENV | API keys (APIFY_API_KEY, ANYMAILFINDER_API_KEY, OPENAI_API_KEY) |
| `data/cv_parsed.json` | JSON | Parsed CV text |
| `data/apify_results.json` | JSON | Raw job listings from Apify |
| `data/filtered_jobs.json` | JSON | Qualifying jobs (passed filter) |
| `data/filtered_out_jobs.json` | JSON | Rejected jobs with reasons |
| `data/emails.json` | JSON | Found emails per job ID |
| `data/cvs/{job_id}/personalized_cv.html` | HTML | Generated CV HTML |
| `data/cvs/{job_id}/personalized_cv.pdf` | PDF | Generated CV PDF |
| `data/cvs/{job_id}/email.json` | JSON | Composed email (to, subject, body) |
| `data/cvs/{job_id}/job_info.json` | JSON | Job details for reference |
| `data/processed_jobs.json` | JSON | Applied jobs (deduplication) |
| `data/drafts/{draft_id}.json` | JSON | Gmail draft metadata |
| `data/run_summary.json` | JSON | Run metrics |
| `data/gmail_token.json` | JSON | OAuth cache (gitignored) |

---

## Sequence Diagram

```
┌─────────┐     ┌──────────┐    ┌─────────┐    ┌───────┐
│ Orchestr │     │CV Parser │    │Scraper  │    │ Filter │
└────┬────┘     └────┬─────┘    └────┬────┘    └───┬────┘
     │                │               │              │
     │ load_config()  │              │              │
     │───────────────>>│              │              │
     │                │              │              │
     │ parse_cv()     │              │              │
     │───────────────>>│              │              │
     │                │              │              │
     │   cv_text      │              │              │
     │<<─────────────│              │              │
     │               │              │              │
     │ scrape_jobs() │              │              │
     │───────────────────────────────────────>>│
     │               │              │              │
     │      list[jobs]              │              │
     │<<───────────────────────────────────────│
     │               │              │              │
     │ filter_jobs(jobs, cv_text)  │              │
     │────────────────────────────────────────>>│
     │               │              │              │
     │      (qualifying, rejected) │              │
     │<<─────────────────────────────────────────│
     │               │              │              │
     │ For each job in qualifying:               │
     │    │               │              │              │
     │    │ personalize_cv()           │              │
     │    │────────────────────────────────────>>│
     │    │               │              │              │
     │    │      cv_path                        │              │
     │    │<<────────────────────────────────────│
     │    │               │              │              │
     │    │ find_email()                       │              │
     │    │────────────────────────────────────────>>│
     │    │               │              │              │
     │    │      email                          │              │
     │    │<<─────────────────────────────────────│
     │    │               ��              │              │
     │    │ compose_email()             │              │
     │    │───────────────────────────────────────>>│
     │    │               │              │              │
     │    │      email body                    │              │
     │    │<<────────────────────────────────────│
     │    │               │              │              │
     │    │ create_draft() │              │              │
     │    │────────────────────────────────────────>>│
     │    │               │              │              │
     │    │    draft_id    │              │              │
     │    │<<─────────────────────────────────────│
     │               │              │              │
     │ write run_summary()                    │
     │────────────────────────────────────────>>│
```

---

## API Interface Definitions

### Config API

```python
def load_config() -> Config:
    """Load config.yaml"""
    pass
```

### CV Parser API

```python
def parse_cv(path: str) -> str:
    """Parse CV file to text.
    
    Args:
        path: Path to CV file (PDF or TXT)
    
    Returns:
        Extracted text content
    
    Raises:
        FileNotFoundError: If CV file not found
        ValueError: If unsupported format
    """
    pass
```

### Scraper API

```python
async def scrape_jobs(urls: list[str], apify_config: ApifyConfig, count: int) -> list[Job]:
    """Scrape jobs from URLs.
    
    Args:
        urls: List of job search URLs
        config: Config with API keys
        count: Max jobs to retrieve
    
    Returns:
        List of Job objects
    
    Raises:
        httpx.HTTPError: On API failure
    """
    pass
```

### Filter API

```python
async def filter_jobs(jobs: list[Job], cv_text: str, ...) -> tuple[list[Job], list[Job]]:
    """Filter jobs by qualification and accepting status.
    
    Args:
        jobs: List of scraped jobs
        cv_text: Parsed CV text
    
    Returns:
        Tuple of (qualifying_jobs, rejected_jobs)
    """
    pass
```

### Email Finder API

```python
async def find_email_for_job(job: Job, api_key: str, ...) -> dict:
    """Find hiring manager email.
    
    Args:
        job: Job with company info
        api_key: AnyMailFinder API key
    
    Returns:
        Dict with email and status
    """
    pass
```

### CV Personalizer API

```python
async def personalize_cv(cv_text: str, job: Job, ...) -> Path:
    """Generate personalized CV for a job.
    
    Args:
        cv_text: Parsed CV text
        job: Job to personalize for
    
    Returns:
        Path to generated PDF
    """
    pass
```

### Email Composer API

```python
def compose_email(job: Job, cv_text: str, cv_data: dict = None, to_email: str = None) -> dict:
    """Compose application email.
    
    Args:
        job: Job listing
        cv_text: Parsed CV text
        cv_data: Personalized CV data
    
    Returns:
        Dict with to, cc, subject, body
    """
    pass
```

### Gmail Draft API

```python
async def create_draft(
    to: str,
    subject: str,
    body: str,
    attachment_path: Path,
    credentials_path: str = "credentials.json"
) -> str:
    """Create Gmail draft.
    
    Args:
        to: Recipient email
        subject: Email subject
        body: Email body
        attachment_path: Path to PDF attachment
        credentials_path: Path to Gmail OAuth credentials
    
    Returns:
        Draft ID or error message
    """
    pass
```

---

## State Management & Data Persistence

### Local File State

| State | Storage | Persistence |
|-------|--------|-------------|
| Config | In-memory | `config.yaml` |
| CV text | In-memory | `data/cv_parsed.json` |
| Jobs | In-memory | `data/apify_results.json` |
| Filtered jobs | In-memory | `data/filtered_jobs.json` |
| Generated CVs | Files | `data/cvs/*.pdf` |
| Found emails | Files | `data/emails.json` |
| Processed jobs | Files | `data/processed_jobs.json` |
| Gmail drafts | API | Not stored locally |
| Run summary | Files | `data/run_summary.json` |

### Caching Logic

- Each run is independent (unless --cached is used)
- Previous data can be overwritten using --force
- Can resume from specific step using --step N

---

## Unit Testing Strategy

### Test Cases by Module

| Module | Test Focus | Test Cases |
|--------|------------|------------|
| `config.py` | Validation | Invalid YAML, missing fields, invalid paths |
| `cv_parser.py` | Parsing | PDF, TXT, invalid format |
| `filter.py` | Filtering | qualification match, not accepting |
| `email_finder.py` | Response parsing | Valid response, empty, invalid JSON |
| `email_composer.py` | Template construction | Empty job, missing fields |

### Example Test Cases

```python
def test_filter_qualifying_job():
    """Job that candidate qualifies for"""
    job = Job(id="1", title="Dev", company="X", requirements=["Python"])
    cv = "I am a Python developer"
    
    qualifying, rejected = run_filter([job], cv)
    
    assert len(qualifying) == 1
    assert len(rejected) == 0

def test_filter_not_accepting_applications():
    """Job not accepting applications"""
    job = Job(
        id="2", title="Dev", company="X", 
        requirements=["Python"], accepting_applications=False
    )
    cv = "I am a Python developer"
    
    qualifying, rejected = run_filter([job], cv)
    
    assert len(qualifying) == 0
    assert len(rejected) == 1

def test_filter_qualification_mismatch():
    """Job candidate doesn't qualify for"""
    job = Job(id="3", title="Surgeon", company="X", requirements=["MD"])
    cv = "I am a software developer"
    
    qualifying, rejected = run_filter([job], cv)
    
    assert len(qualifying) == 0
    assert len(rejected) == 1
```

### Mocking Strategy

| External Dependency | Mock |
|-------------------|------|
| Apify API | `httpx-mock` |
| AnyMailFinder | `httpx-mock` |
| Gmail API | `google-api-mock` |
| Ollama/OpenAI | Mock response |

### Coverage Target

- Unit tests: ≥80% for logic modules (filter.py, config.py)
- Integration tests: Skip (require API keys)