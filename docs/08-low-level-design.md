# Low-Level Design – AI Automated Email Job Application System

## Component Detailed Design

### Directory Structure

```
src/
├── app/
│   ├── __init__.py
│   ├── __main__.py          # Entry point: python -m app run
│   ├── config.py           # Config loading & validation
│   ├── cv_parser.py       # PDF/TXT CV parsing
│   ├── scraper.py         # Apify integration
│   ├── filter.py          # Job filtering (LLM-based, structured output)
│   ├── cv_personalizer.py   # CV personalization with PDF generation
│   ├── email_finder.py    # AnyMailFinder integration
│   ├── cover_letter.py   # Cover letter generation
│   ├── gmail_draft.py    # Gmail API integration
│   ├── agent.py         # Orchestrator (parallel + async)
│   ├── models.py       # Pydantic models
│   └── utils.py        # Shared utilities
├── config.yaml
├── data/                   # Generated at runtime
├── credentials.json        # Gmail OAuth (gitignored)
├── tests/
│   └── test_filter.py
└── pyproject.toml
```

**Document Hierarchy:** TDD is the contract of record. LLD conforms to TDD. In case of conflicts, TDD supersedes LLD.

## Class & Object Design

### Core Data Models (`models.py`)

```python
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
import json
from pathlib import Path

# === LLM Configuration ===
class LLMConfig(BaseModel):
    provider: str = "local"  # "local" (Ollama) or "openai"
    model: str = "qwen2.5:7b"
    base_url: str = "http://localhost:11434/v1"
    api_key: str = "ollama"

class SearchConfig(BaseModel):
    urls: list[str] = Field(min_length=1)
    count: int = Field(default=50, ge=1, le=50)

class CVConfig(BaseModel):
    path: str

class GmailConfig(BaseModel):
    draft_only: bool = True
    token_path: str = "data/gmail_token.json"
    credentials_path: str = "credentials.json"

class PrivacyConfig(BaseModel):
    redact_pii: bool = True

# === Main Models ===
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
    accepting_applications: Optional[bool] = None  # May be unknown (None)
    rejection_reason: Optional[str] = None  # Populated after filtering

class FilterDecision(BaseModel):
    """Structured LLM output for filtering"""
    is_qualified: bool
    is_accepting_applications: bool
    reason: Optional[str] = None

class Config(BaseModel):
    search: SearchConfig
    cv: CVConfig
    gmail: GmailConfig
    llm: LLMConfig = Field(default_factory=LLMConfig)
    privacy: PrivacyConfig = Field(default_factory=PrivacyConfig)
    dry_run: bool = False

class RunSummary(BaseModel):
    started_at: str
    finished_at: str
    jobs_found: int
    jobs_filtered: int
    jobs_qualified: int
    drafts_created: int
    errors: list[str]
```

### Utility Functions (`utils.py`)

```python
from pathlib import Path
import json

def save_json(path: str, data: dict | list) -> None:
    """Save data to JSON file"""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2))

def load_json(path: str) -> dict | list:
    """Load data from JSON file"""
    return json.loads(Path(path).read_text())

def get_processed_job_ids() -> set[str]:
    """Get set of already processed job IDs"""
    path = Path("data/processed_jobs.json")
    if path.exists():
        return {entry["job_id"] for entry in json.loads(path.read_text())}
    return set()

def mark_job_processed(job_id: str, draft_id: str) -> None:
    """Record processed job with draft ID"""
    path = Path("data/processed_jobs.json")
    data = []
    if path.exists():
        data = json.loads(path.read_text())
    data.append({
        "job_id": job_id, 
        "draft_id": draft_id, 
        "processed_at": datetime.now().isoformat()
    })
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))

def validate_email(email: str) -> bool:
    """Validate email format"""
    return bool(email and "@" in email and "." in email.split("@")[1])
```

### LLM Client (`utils.py`)

```python
from openai import OpenAI

def get_llm_client() -> OpenAI:
    """Get LLM client (local Ollama or OpenAI)"""
    config = load_config()
    
    if config.llm.provider == "local":
        return OpenAI(
            base_url=config.llm.base_url,
            api_key=config.llm.api_key
        )
    else:
        # Uses OPENAI_API_KEY env var
        return OpenAI()
```

### Config Loader (`config.py`)

```python
import yaml
from pathlib import Path

def load_config() -> Config:
    """Load and validate config.yaml"""
    with open("config.yaml") as f:
        raw = yaml.safe_load(f)
    return Config(**raw)
```

### Config Loader (`config.py`)

```python
def load_config() -> Config:
    """Load and validate config.yaml"""
    with open("config.yaml") as f:
        raw = yaml.safe_load(f)
    return Config(**raw)

def validate_api_keys(config: Config) -> bool:
    """Check required env vars are set"""
    required = [config.api_keys.google, config.api_keys.anymailfinder, config.api_keys.apify]
    return all(required)
```

### CV Parser (`cv_parser.py`)

```python
def parse_cv(path: str) -> str:
    """Parse PDF/TXT to plain text"""
    suffix = Path(path).suffix.lower()
    if suffix == ".pdf":
        return parse_pdf(path)
    elif suffix == ".txt":
        return Path(path).read_text()
    else:
        raise ValueError(f"Unsupported CV format: {suffix}")

def parse_pdf(path: str) -> str:
    """Extract text from PDF using pdfplumber"""
    with pdfplumber.open(path) as pdf:
        return "\n".join(page.extract_text() for page in pdf.pages)
```

### Scraper (`scraper.py`)

```python
def scrape_jobs(urls: list[str], config: Config) -> list[Job]:
    """Scrape jobs from each URL via Apify"""
    jobs = []
    for url in urls:
        response = httpx.post(
            "https://api.apify.com/v2/acts/~actor_id/run",
            json={"urls": [url]},
            headers={"Authorization": f"Bearer {config.api_keys.apify}"}
        )
        jobs.extend(parse_apify_response(response.json()))
    return jobs

def parse_apify_response(data: dict) -> list[Job]:
    """Map Apify output to Job models"""
    # Apify returns 'jobs' array
    return [
        Job(
            id=job.get("id", str(uuid4())),
            title=job.get("title", ""),
            company=job.get("company", ""),
            location=job.get("location"),
            description=job.get("description", ""),
            requirements=job.get("requirements", []),
            url=job.get("url", ""),
            posted_date=job.get("postedDate"),
            accepting_applications=job.get("acceptingApplications", True)
        )
        for job in data.get("jobs", [])
    ]
```

### Filter (`filter.py`)

```python
import json
from pydantic_ai import Agent, RunContext
from pydantic import BaseModel
from typing import Optional
from app.config import load_config

class FilterDecision(BaseModel):
    """Structured response from Pydantic AI for job filtering"""
    is_qualified: bool
    is_accepting_applications: bool
    reason: Optional[str] = None

# Pydantic AI Agent for filtering
# Uses result_type to enforce structured output - no manual JSON parsing needed!
filtering_agent = Agent(
    'ollama:qwen2.5:7b',
    result_type=FilterDecision,
    system_prompt="""You are an expert HR assistant. Evaluate if the candidate's CV 
matches the job requirements. Determine if the job is still accepting applications.
Be strict - only recommend if the candidate clearly meets the requirements."""
)

@filtering_agent.tool
async def check_company_reputation(ctx: RunContext, company: str) -> str:
    """Tool: Check if company is known for high bar"""
    # Could call external API to check company info
    pass

async def filter_jobs(jobs: list[Job], cv_text: str) -> tuple[list[Job], list[Job]]:
    """Filter jobs using Pydantic AI agent.
    
    The agent automatically:
    - Constructs prompts from result_type schema
    - Parses LLM response into FilterDecision
    - Handles retries on validation errors
    
    Returns:
        tuple[qualifying_jobs, rejected_jobs]
    """
    config = load_config()
    model = config.llm.model
    
    qualifying = []
    rejected = []
    
    for job in jobs:
        try:
            # Pydantic AI handles prompt construction and JSON parsing
            decision = await filtering_agent.run(f"""Evaluate:

CV:
{cv_text}

Job: {job.title} at {job.company}
Requirements: {", ".join(job.requirements) if job.requirements else "Not specified"}
Description: {job.description[:500]}""")
            
            if decision.is_qualified and decision.is_accepting_applications:
                qualifying.append(job)
            else:
                job.rejection_reason = decision.reason or "Failed checks"
                rejected.append(job)
        except Exception as e:
            job.rejection_reason = f"Agent error: {str(e)}"
            rejected.append(job)
    
    return qualifying, rejected
```

### CV Personalizer (`cv_personalizer.py`)

```python
from weasyprint import HTML
from jinja2 import Template
from pathlib import Path
import tempfile

# HTML CV Template - professional layout with placeholders
CV_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body { font-family: Arial, sans-serif; margin: 40px; color: #333; }
        h1 { color: #1a4a7a; border-bottom: 2px solid #1a4a7a; }
        h2 { color: #2a5a8a; margin-top: 20px; }
        .contact { color: #666; margin-bottom: 20px; }
        .section { margin-bottom: 15px; }
        .skills { background: #f5f5f5; padding: 10px; border-radius: 5px; }
    </style>
</head>
<body>
    <h1>{{ name }}</h1>
    <div class="contact">{{ email }} | {{ phone }} | {{ location }}</div>
    
    <h2>Professional Summary</h2>
    <p>{{ summary }}</p>
    
    <h2>Experience</h2>
    {% for job in experience %}
    <div class="section">
        <strong>{{ job.title }}</strong> at {{ job.company }}<br>
        <em>{{ job.dates }}</em>
        <ul>{{ job.highlights }}</ul>
    </div>
    {% endfor %}
    
    <h2>Skills</h2>
    <div class="skills">{{ skills }}</div>
    
    <h2>Education</h2>
    <p>{{ education }}</p>
</body>
</html>"""

class CVData(BaseModel):
    """Structured CV data from Pydantic AI"""
    name: str
    email: str
    phone: str
    location: str
    summary: str
    experience: list[dict]  # [{"title": ..., "company": ..., "dates": ..., "highlights": ...}]
    skills: str
    education: str

# Pydantic AI Agent for CV personalization
cv_agent = Agent(
    'ollama:qwen2.5:7b',
    result_type=CVData,
    system_prompt="""You create professional CVs tailored to specific job requirements.
Highlight relevant experience and skills that match the job.
Output only valid JSON matching the schema exactly."""
)

async def personalize_cv(base_cv_text: str, job: Job) -> Path:
    """Generate personalized CV PDF using Pydantic AI agent.
    
    The agent:
    1. Receives CV + job requirements
    2. Returns structured CVData (Pydantic model)
    3. Renders to HTML template
    4. Converts to PDF via weasyprint
    """
    # Pydantic AI handles JSON parsing - no manual response_format needed
    cv_data = await cv_agent.run(f"""Create a tailored CV:

Original CV:
{base_cv_text}

Job Requirements:
{", ".join(job.requirements) if job.requirements else "Not specified"}

Job Title: {job.title}
Company: {job.company}""")
    
    # Expose the experience list for Jinja2
    cv_dict = cv_data.model_dump()
    experience_list = cv_dict.pop('experience', [])
    
    # Render HTML from template
    html_content = Template(CV_TEMPLATE).render(
        **cv_dict,
        experience=experience_list
    )
    
    # Convert HTML to PDF via weasyprint
    output_path = Path(f"data/cvs/personalized_cv_{job.id}.pdf")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    HTML(string=html_content).write_pdf(output_path)
    
    return output_path
```

### Email Finder (`email_finder.py`)

```python
import httpx
from pydantic_ai import Agent, RunContext
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from typing import Optional

ANYMAILFINDER_API_URL = "https://api.anymailfinder.com/v4/search/text.json"

# Pydantic AI Agent for email finding
# This is where agents shine - the LLM can use multiple tools and reason about failures!
email_hunter_agent = Agent(
    'ollama:qwen2.5:7b',
    result_type=str,  # Just want the email string
    system_prompt="""You find contact information for hiring managers.
Use the provided tools to locate emails.
If API fails, try parsing the job description for hidden emails."""
)

@email_hunter_agent.tool
async def search_anymailfinder(ctx: RunContext, company: str, name: str = "") -> str:
    """Tool 1: Try AnyMailFinder API"""
    config = load_config()
    
    response = httpx.post(
        ANYMAILFINDER_API_URL,
        json={"company": company, "name": name},
        headers={
            "Authorization": f"Bearer {config.api_keys.anymailfinder}",
            "Content-Type": "application/json"
        },
        timeout=30.0
    )
    
    data = response.json()
    return data.get("email", "")

@email_hunter_agent.tool
async def parse_job_description_for_email(ctx: RunContext, job_description: str) -> str:
    """Tool 2: Fallback - if API fails, search job description for hidden emails"""
    import re
    # Simple regex to find email patterns in job description
    email_pattern = r'[\w\.-]+@[\w\.-]+\.\w+'
    matches = re.findall(email_pattern, job_description)
    return matches[0] if matches else ""

@email_hunter_agent.tool  
async def guess_email_pattern(ctx: RunContext, first_name: str, last_name: str, domain: str) -> str:
    """Tool 3: Fallback - guess email pattern if nothing else works"""
    patterns = [
        f"{first_name}.{last_name}@{domain}",
        f"{first_name}{last_name}@{domain}",
        f"{first_name[0]}{last_name}@{domain}",
    ]
    return patterns[0]  # Return best guess

async def find_email(company: str, hiring_manager: Optional[str] = None, job_description: str = "") -> str:
    """Find email using Pydantic AI agent.
    
    The agent:
    1. Tries AnyMailFinder API first
    2. If fails, parses job description for hidden emails
    3. If still fails, guesses the email pattern
    
    No need for manual error handling - the agent decides!
    """
    result = await email_hunter_agent.run(
        f"Find email for hiring manager at {company}" + 
        (f" ({hiring_manager})" if hiring_manager else ""),
        # Tools are available to the agent automatically
    )
    return result
```
```

### Cover Letter (`cover_letter.py`)

```python
from pydantic_ai import Agent

# Pydantic AI Agent for cover letters
# Uses system_prompt to enforce professional tone - no preamble, no sign-off without name
cover_letter_agent = Agent(
    'ollama:qwen2.5:7b',
    result_type=str,  # Plain text output
    system_prompt="""You write professional cover letters. Rules:
1. No placeholders like [Your Name] - use actual CV details
2. No preamble like "Here is my cover letter:"
3. No sign-off without the name - just the body
4. Be concise, professional, and tailored to the job."""
)

async def generate_cover_letter(job: Job, cv_text: str) -> str:
    """Generate personalized cover letter using Pydantic AI agent.
    
    The agent's system prompt enforces:
    - No preamble
    - No placeholder placeholders
    - Professional tone
    """
    result = await cover_letter_agent.run(f"""Write a cover letter for:

Job: {job.title} at {job.company}
Description: {job.description}

CV:
{cv_text}""")
    
    return result.strip()
```

### Gmail Draft (`gmail_draft.py`)

```python
import base64
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
import email
import mimetypes
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.draft"]

def get_gmail_credentials() -> Credentials:
    """Load or refresh Gmail OAuth credentials.
    
    On first run, opens browser for OAuth consent.
    Token is cached in data/gmail_token.json.
    """
    token_path = Path("data/gmail_token.json")
    creds_path = Path("credentials.json")
    
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), GMAIL_SCOPES)
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(token_path, "w") as f:
                f.write(creds.to_json())
        return creds
    
    # First run: browser OAuth flow
    flow = InstalledAppFlow.from_client_secrets_file(
        str(creds_path), GMAIL_SCOPES
    )
    creds = flow.run_local_server(port=0)
    token_path.parent.mkdir(parents=True, exist_ok=True)
    with open(token_path, "w") as f:
        f.write(creds.to_json())
    return creds

def create_message_with_attachment(
    sender: str,
    to: str,
    subject: str,
    body: str,
    file_path: str
) -> dict:
    """Create a message with an attachment"""
    message = MIMEMultipart("mixed")
    message["to"] = to
    message["from"] = sender
    message["subject"] = subject
    
    # Text part
    text_part = MIMEText(body, "plain")
    message.attach(text_part)
    
    # Attachment
    content_type, _ = mimetypes.guess_type(file_path)
    if content_type is None:
        content_type = "application/octet-stream"
    
    main_type, sub_type = content_type.split("/", 1)
    
    with open(file_path, "rb") as f:
        attachment_data = f.read()
    
    attachment = MIMEBase(main_type, sub_type)
    attachment.set_payload(attachment_data)
    email.encoders.encode_base64(attachment)
    
    filename = Path(file_path).name
    attachment.add_header(
        "Content-Disposition",
        f'attachment; filename="{filename}"'
    )
    message.attach(attachment)
    
    return {
        "raw": base64.urlsafe_b64encode(message.as_bytes()).decode()
    }

async def create_draft(
    to: str,
    subject: str,
    body: str,
    attachment_path: Path,
    credentials: Optional[Credentials] = None
) -> str:
    """Create Gmail draft with PDF attachment
    
    If config.dry_run is True, skips actual draft creation.
    """
    config = load_config()
    
    if config.dry_run:
        return f"dry_run:{attachment_path.name}"
    
    if credentials is None:
        credentials = get_gmail_credentials()
    
    service = build("gmail", "v1", credentials=credentials)
    
    message = create_message_with_attachment(
        sender="me",
        to=to,
        subject=subject,
        body=body,
        file_path=str(attachment_path)
    )
    
    draft = (
        service.users()
        .drafts()
        .create(userId="me", body={"message": message})
        .execute()
    )
    
    return draft["id"]
```

### Orchestrator (`agent.py`)

```python
import asyncio
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

async def run(config: Config) -> RunSummary:
    """Deterministic Python async orchestrator.
    
    IMPORTANT: This is a PURE PYTHON async pipeline, NOT an LLM agent.
    The workflow is fixed: Scrape → Filter → Personalize → Email → Draft.
    No LLM "decisions" - Python controls the flow.
    
    Phase 1: Sequential (each step depends on previous output)
    Phase 2: Parallel (independent per-job processing)
    """
    started_at = datetime.now().isoformat()
    
    # === PHASE 1: Sequential (depends on previous output) ===
    # No LLM involved - deterministic file parsing
    cv_text = parse_cv(config.cv.path)
    save_json("data/cv_parsed.json", {"text": cv_text})
    
    # No LLM involved - deterministic API call
    jobs = scrape_jobs(config.search.urls, config)
    save_json("data/apify_results.json", Jobs=[j.model_dump() for j in jobs])
    
    # LLM involved: Pydantic AI agent evaluates each job
    qualifying, rejected = await filter_jobs(jobs, cv_text)
    save_json("data/filtered_jobs.json", Jobs=[j.model_dump() for j in qualifying])
    save_json("data/filtered_out_jobs.json", Jobs=[j.model_dump() for j in rejected])
    
    # Deduplication - deterministic set lookup
    processed_ids = get_processed_job_ids()
    new_jobs = [j for j in qualifying if j.id not in processed_ids]
    
    # === PHASE 2: Parallel (independent per-job processing) ===
    semaphore = asyncio.Semaphore(5)  # Max 5 concurrent jobs
    
    async def process_job(job: Job) -> Optional[str]:
        async with semaphore:
            try:
                # LLM involved: Pydantic AI agent finds email
                email_addr = await find_email(
                    job.company, 
                    job.hiring_manager_name,
                    job.description  # For fallback parsing
                )
                if not validate_email(email_addr):
                    return f"{job.id}: No valid email found"
                
                # LLM involved: Pydantic AI agent generates CV
                cv_path = await personalize_cv(cv_text, job)
                
                # LLM involved: Pydantic AI agent generates letter
                letter = await generate_cover_letter(job, cv_text)
                
                # No LLM: Gmail API call
                draft_id = await create_draft(
                    to=email_addr,
                    subject=f"Application for {job.title}",
                    body=letter,
                    attachment_path=cv_path,
                    credentials=get_gmail_credentials()
                )
                
                # Deterministic: record processed job
                mark_job_processed(job.id, draft_id)
                
                return None  # Success
            except Exception as e:
                return f"{job.id}: {str(e)}"
    
    # Run parallel processing with progress bar
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
    ) as progress:
        task = progress.add_task(
            f"Processing {len(new_jobs)} jobs...", 
            total=len(new_jobs)
        )
        
        results = []
        for job in new_jobs[:config.search.count]:
            result = await process_job(job)
            results.append(result)
            progress.advance(task)
    
    errors = [r for r in results if r is not None]
    
    summary = RunSummary(
        started_at=started_at,
        finished_at=datetime.now().isoformat(),
        jobs_found=len(jobs),
        jobs_filtered=len(rejected),
        jobs_qualified=len(qualifying),
        drafts_created=len(new_jobs) - len(errors),
        errors=errors
    )
    
    save_json("data/run_summary.json", summary.model_dump())
    return summary
```

**Key Architectural Distinction:**

| Component | Type | Why |
|-----------|------|-----|
| **Orchestrator** | **Deterministic Python async pipeline** | Fixed workflow, no LLM "decisions" |
| **Filter** | Pydantic AI Agent | Cognitive evaluation, structured output |
| **CV Personalizer** | Pydantic AI Agent | Structured JSON generation |
| **Email Finder** | Pydantic AI Agent with tools | Multi-step reasoning, fallbacks |
| **Cover Letter** | Pydantic AI Agent | System prompt enforcement |
| **Gmail Draft** | Deterministic API call | No LLM needed |
        )
        
        results = []
        for job in new_jobs[:config.search.count]:
            result = await process_job(job)
            results.append(result)
            progress.advance(task)
    
    errors = [r for r in results if r is not None]
    
    summary = RunSummary(
        started_at=started_at,
        finished_at=datetime.now().isoformat(),
        jobs_found=len(jobs),
        jobs_filtered=len(rejected),
        jobs_qualified=len(qualifying),
        drafts_created=len(new_jobs) - len(errors),
        errors=errors
    )
    
    save_json("data/run_summary.json", summary.model_dump())
    return summary
```
    
    for job in qualifying[:config.search.count]:
        try:
            # Personalize CV
            cv_path = personalize_cv(cv_text, job)
            
            # Find email
            email = find_email(job.company, job.hiring_manager)
            
            # Generate cover letter
            letter = generate_cover_letter(job, cv_text)
            
            # Create draft
            draft_id = create_draft(
                to=email,
                subject=f"Application for {job.title}",
                body=letter,
                attachment_path=cv_path,
                credentials=get_gmail_credentials()
            )
            
            drafts_created += 1
            
        except Exception as e:
            errors.append(f"{job.id}: {str(e)}")
    
    finished_at = datetime.now().isoformat()
    
    summary = RunSummary(
        started_at=started_at,
        finished_at=finished_at,
        jobs_found=len(jobs),
        jobs_filtered=len(rejected),
        jobs_qualified=len(qualifying),
        drafts_created=drafts_created,
        errors=errors
    )
    
    save_json("data/run_summary.json", summary.model_dump())
    return summary
```

## Database Schema – Physical Design

**No database used.** Flat files only:

| File | Format | Contents |
|------|--------|---------|
| `config.yaml` | YAML | User configuration |
| `data/apify_results.json` | JSON | Raw job listings |
| `data/filtered_jobs.json` | JSON | Qualifying jobs |
| `data/filtered_out_jobs.json` | JSON | Rejected jobs |
| `data/cvs/*.pdf` | PDF | Personalized CVs |
| `data/emails/*.json` | JSON | Found emails |
| `data/cover_letters/*.txt` | Text | Generated letters |
| `data/drafts/*.json` | JSON | Gmail draft metadata |
| `data/run_summary.json` | JSON | Run metrics |

## Detailed Logic & Algorithms

### Job Filtering Algorithm

```python
async def filter_jobs(jobs: list[Job], cv_text: str) -> tuple[list[Job], list[Job]]:
    """
    Filter jobs using LLM evaluation.
    
    Criteria:
    1. Candidate qualifications match job requirements
    2. Job is accepting applications
    
    For each job:
    1. Construct prompt with CV + job details
    2. Call LLM to evaluate
    3. Parse response (YES/YES = qualify)
    4. If NO to either: add to rejected with reason
    5. If YES to both: add to qualifying
    """
    qualifying = []
    rejected = []
    
    for job in jobs:
        # Skip if definitely not accepting
        if job.accepting_applications is False:
            rejected.append(job)
            continue
        
        # Use LLM for qualified check
        reason = await evaluate_job(job, cv_text)
        
        if reason is None:
            qualifying.append(job)
        else:
            job.rejection_reason = reason
            rejected.append(job)
    
    return qualifying, rejected
```

## Sequence Diagrams

### Main Pipeline Sequence

```
┌─────────┐     ┌──────────┐    ┌─────────┐    ┌──────��─┐
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
     │ scrape_jobs()   │              │              │
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
     │    │               │              │              │
     │    │ generate_cover_letter()             │              │
     │    │───────────────────────────────────────>>│
     │    │               │              │              │
     │    │      letter                         │              │
     │    │<<─────────────────────────────────────│
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

## API Interface Definitions

### Config API

```python
def load_config() -> Config:
    """Load config.yaml"""
    pass

def validate_config(config: Config) -> list[str]:
    """Validate config.
    
    Returns list of validation errors (empty if valid).
    """
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
def scrape_jobs(urls: list[str], config: Config) -> list[Job]:
    """Scrape jobs from URLs.
    
    Args:
        urls: List of job search URLs
        config: Config with API keys
    
    Returns:
        List of Job objects
    
    Raises:
        httpx.HTTPError: On API failure
    """
    pass
```

### Filter API

```python
async def filter_jobs(jobs: list[Job], cv_text: str) -> tuple[list[Job], list[Job]]:
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
def find_email(company: str, hiring_manager: Optional[str] = None) -> str:
    """Find hiring manager email.
    
    Args:
        company: Company name
        hiring_manager: Optional hiring manager name
    
    Returns:
        Email address or empty string if not found
    """
    pass
```

### Gmail Draft API

```python
def create_draft(
    to: str,
    subject: str,
    body: str,
    attachment_path: Path,
    credentials: Credentials
) -> str:
    """Create Gmail draft.
    
    Args:
        to: Recipient email
        subject: Email subject
        body: Email body
        attachment_path: Path to PDF attachment
        credentials: Gmail OAuth credentials
    
    Returns:
        Draft ID
    """
    pass
```

## State Management & Data Persistence

### Local File State

| State | Storage | Persistence |
|-------|--------|-------------|
| Config | In-memory | `config.yaml` |
| CV text | In-memory | `data/cv_parsed.json` |
| Jobs | In-memory | `data/apify_results.json` |
| Filtered jobs | In-memory | `data/filtered_jobs.json` |
| Generated CVs | Files | `data/cvs/*.pdf` |
| Found emails | Files | `data/emails/*.json` |
| Cover letters | Files | `data/cover_letters/*.txt` |
| Gmail drafts | API | Not stored locally |
| Run summary | Files | `data/run_summary.json` |

### No Caching

- Each run is independent
- No state carried between runs
- Previous data overwritten on re-run

## Unit Testing Strategy

### Test Cases by Module

| Module | Test Focus | Test Cases |
|--------|------------|------------|
| `config.py` | Validation | Invalid YAML, missing fields, invalid paths |
| `cv_parser.py` | Parsing | PDF, TXT, invalid format |
| `filter.py` | Filtering | qualification match, not accepting |
| `email_finder.py` | Response parsing | Valid response, empty, invalid JSON |
| `cover_letter.py` | Prompt construction | Empty job, missing fields |

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
| OpenAI (LLM) | `openai-mock` |

### Coverage Target

- Unit tests: ≥80% for logic (filter.py, config.py)
- Integration tests: Skip (require API keys)