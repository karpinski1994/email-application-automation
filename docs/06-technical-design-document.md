# Technical Design Document – AI Automated Email Job Application System

## Directory Structure

```
email-application-automation/
├── src/
│   └── app/
│       ├── __init__.py
│       ├── __main__.py          # Entry point: python -m app run
│       ├── config.py            # Config loading & validation
│       ├── models.py           # Pydantic models
│       ├── cv_parser.py        # PDF/TXT CV parsing
│       ├── scraper.py          # Apify integration
│       ├── filter.py           # Job filtering (LLM-based, structured output)
│       ├── cv_personalizer.py # CV personalization with PDF generation
│       ├── email_finder.py    # AnyMailFinder integration
│       ├── cover_letter.py   # Cover letter generation
│       ├── gmail_draft.py   # Gmail API integration
│       ├── agent.py          # Orchestrator with parallel processing
│       └── utils.py          # Shared utilities (save_json, etc.)
├── config.yaml
├── data/                    # Generated at runtime
├── credentials.json        # Gmail OAuth (gitignored)
├── tests/
│   └── test_filter.py
└── pyproject.toml
```

## Class/Object Design

### Config Model

```python
from pydantic import BaseModel, Field
from typing import Optional

class LLMConfig(BaseModel):
    provider: str = "local"  # "local" (Ollama) or "openai"
    model: str = "qwen2.5:7b"  # Default local model
    base_url: str = "http://localhost:11434/v1"  # Ollama OpenAI-compatible endpoint
    api_key: str = "ollama"  # Dummy for local, real key for OpenAI

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
    redact_pii: bool = True  # Redact PII before sending to LLM

class Config(BaseModel):
    search: SearchConfig
    cv: CVConfig
    gmail: GmailConfig
    llm: LLMConfig = Field(default_factory=LLMConfig)
    privacy: PrivacyConfig = Field(default_factory=PrivacyConfig)
    dry_run: bool = False  # Skip actual Gmail draft creation
```

### Job Model (Unified)

```python
class Job(BaseModel):
    id: str
    title: str
    company: str
    description: str
    url: str
    location: Optional[str] = None
    hiring_manager_name: Optional[str] = None
    requirements: list[str] = Field(default_factory=list)  # Added from LLD
    posted_date: Optional[str] = None
    accepting_applications: Optional[bool] = None  # May be unknown (None)
    rejection_reason: Optional[str] = None  # Populated after filtering
```

### RunSummary Model

```python
from datetime import datetime

class RunSummary(BaseModel):
    started_at: str  # ISO8601 string for JSON serialization
    finished_at: str
    jobs_found: int
    jobs_filtered: int
    jobs_qualified: int
    drafts_created: int
    errors: list[str]
```

### FilterResult Model (Structured LLM Output)

```python
from pydantic import BaseModel
from typing import Optional

class FilterDecision(BaseModel):
    is_qualified: bool
    is_accepting_applications: bool
    reason: Optional[str] = None
```

### Local LLM Integration

```python
# utils.py
def get_llm_client() -> OpenAI:
    """Get LLM client (local Ollama or OpenAI)"""
    config = load_config()
    
    if config.llm.provider == "local":
        return OpenAI(
            base_url=config.llm.base_url,
            api_key=config.llm.api_key  # "ollama"
        )
    else:
        return OpenAI()  # Uses OPENAI_API_KEY env var
```

### Gmail OAuth Flow

```python
# gmail_draft.py
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.draft"]

def get_gmail_credentials() -> Credentials:
    """Load or refresh Gmail OAuth credentials"""
    token_path = Path(config.gmail.token_path)
    creds_path = Path(config.gmail.credentials_path)
    
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), GMAIL_SCOPES)
        if creds and creds.expired and creds.refresh_token:
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
```

### Job Deduplication

```python
# utils.py
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
    data.append({"job_id": job_id, "draft_id": draft_id, "processed_at": datetime.now().isoformat()})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))
```

### Parallel Processing with Asyncio

```python
# agent.py
import asyncio

async def run(config: Config) -> RunSummary:
    started_at = datetime.now().isoformat()
    processed_ids = get_processed_job_ids()
    
    # Phase 1: Sequential (depends on previous output)
    cv_text = parse_cv(config.cv.path)
    jobs = scrape_jobs(config.search.urls, config)
    qualifying, rejected = await filter_jobs(jobs, cv_text)
    
    # Phase 2: Parallel per-job processing
    new_jobs = [j for j in qualifying if j.id not in processed_ids]
    
    semaphore = asyncio.Semaphore(5)  # Max 5 concurrent
    
    async def process_job(job: Job) -> Optional[str]:
        async with semaphore:
            try:
                # Validate email before proceeding
                email = await find_email(job.company, job.hiring_manager_name)
                if not email or "@" not in email:
                    return f"{job.id}: No valid email found"
                
                cv_path = await personalize_cv(cv_text, job)
                letter = await generate_cover_letter(job, cv_text)
                draft_id = await create_draft(email, job.title, letter, cv_path, get_gmail_credentials())
                mark_job_processed(job.id, draft_id)
                return None
            except Exception as e:
                return f"{job.id}: {str(e)}"
    
    results = await asyncio.gather(*[process_job(j) for j in new_jobs[:config.search.count]])
    errors = [r for r in results if r is not None]
    
    return RunSummary(
        started_at=started_at,
        finished_at=datetime.now().isoformat(),
        jobs_found=len(jobs),
        jobs_filtered=len(rejected),
        jobs_qualified=len(qualifying),
        drafts_created=len(qualifying) - len(errors),
        errors=errors
    )
```

### Error Handling with Tenacity

```python
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from httpx import HTTPStatusError

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(HTTPStatusError)
)
def find_email(company: str, hiring_manager: Optional[str] = None) -> str:
    """Find email with automatic retry on rate limit"""
    # ... implementation
```

### Progress Reporting

```python
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

async def run(config: Config) -> RunSummary:
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
    ) as progress:
        # ... pipeline with progress updates
```

## Design Patterns

| Pattern | Usage |
|---------|-------|
| **Sequential Pipeline** | Main orchestrator runs steps in order, not LLM-routed |
| **Tool-as-Function** | Each module is a pure function, not a class |
| **Try/Except + Tenacity** | Retries with exponential backoff for API calls |
| **Singleton Config** | One Config instance passed through pipeline |

## Database Schema

### Local JSON files (no database)

```python
# data/apify_results.json
[
  {"id": "...", "title": "...", "company": "...", "description": "...", "url": "...", "location": "..."}
]

# data/filtered_jobs.json
[Job, ...]

# data/filtered_out_jobs.json
[Job, ...]

# data/run_summary.json
{"started_at": "...", "finished_at": "...", "jobs_found": 50, "jobs_filtered": 30, "jobs_qualified": 20, "drafts_created": 18, "errors": []}
```

## API Endpoint Specifications

### Apify

```
POST https://api.apify.com/v2/acts/{actor_id}/run-sync-get-dataset-items
Headers:
  Authorization: Bearer {APIFY_API_KEY}
  Accept: application/json
  Content-Type: application/json
Body:
{
  "count": 100,
  "scrapeCompany": true,
  "splitByLocation": false,
  "urls": ["https://www.linkedin.com/jobs/search/?..."]
}
Response: [{"id": "...", "title": "...", "company": "...", "description": "...", "url": "...", "location": "..."}, ...]
```

**Notes:**
- `actor_id` is `hKByXkMQaC5Qt9UMN` (LinkedIn jobs scraper)
- `count` is the number of jobs to retrieve (1-100)
- `scrapeCompany` when true includes company data in results
- `splitByLocation` when false returns combined results
- `urls` is a dynamic list of LinkedIn job search URLs

### AnyMailFinder

Two modes:
1. **With hiring manager name** (preferred):
```
POST https://anymailfinder.io/v4/guess/generate
Headers: Authorization: Bearer {ANYMAILFINDER_API_KEY}
Body: {"company": "...", "full_name": "..."}
Response: {"email": "..."}
```
2. **Company-wide search** (fallback when name not available):
```
POST https://anymailfinder.io/v4/company/search
Headers: Authorization: Bearer {ANYMAILFINDER_API_KEY}
Body: {"company": "..."}
Response: {"emails": [{"email": "...", "role": "...", "confidence": 0.9}]}
```

If `job.hiring_manager_name` is missing, use company-wide search and pick the highest-confidence email.

### Gmail

**MIME multipart construction required:**

```python
import email.mime.multipart
import email.mime.base
import base64

def create_draft_mime(to: str, subject: str, body: str, attachment_path: pathlib.Path) -> str:
    # Create MIME multipart message
    msg = email.mime.multipart.MIMEMultipart('mixed')
    msg['To'] = to
    msg['Subject'] = subject
    
    # Add body
    body_part = email.mime.text.MIMEText(body, 'plain')
    msg.attach(body_part)
    
    # Attach PDF
    with open(attachment_path, 'rb') as f:
        attachment = email.mime.base.MIMEBase('application', 'pdf')
        attachment.set_payload(f.read())
    encoders.encode_base64(attachment)
    attachment.add_header('Content-Disposition', 'attachment', filename=attachment_path.name)
    msg.attach(attachment)
    
    # Return base64 encoded raw MIME
    return base64.urlsafe_b64encode(msg.as_bytes()).decode('utf-8')
```

API call:
```
POST https://gmail.googleapis.com/gmail/v1/users/me/drafts
Headers: Authorization: Bearer {access_token}
Body: {"message": {"raw": "base64_mime_string"}}
Response: {"id": "...", "threadId": "..."}
```

### OpenAI (LLM)

```
POST https://api.openai.com/v1/chat/completions
Headers: Authorization: Bearer {OPENAI_API_KEY}
Body: {"model": "gpt-4o", "messages": [{"role": "user", "content": "..."}]}
Response: {"choices": [{"message": {"content": "..."}}]}
```

---

### Example `config.yaml`

```yaml
search:
  urls:
    - "https://www.linkedin.com/jobs/search-results/?keywords=front-end%20developer%20latam&f_SAL=..."
    - "https://www.linkedin.com/jobs/search-results/?keywords=python%20developer%20remote&f_WT=2"
  count: 50

cv:
  path: "./cv.pdf"

gmail:
  draft_only: true
```

**API keys loaded from `.env` (not in config.yaml):**
```bash
# .env
GOOGLE_API_KEY=...
ANYMAILFINDER_API_KEY=...
APIFY_API_KEY=...
OPENAI_API_KEY=...
```
POST https://api.openai.com/v1/chat/completions
Headers: Authorization: Bearer {OPENAI_API_KEY}
Body: {"model": "gpt-4o", "messages": [{"role": "user", "content": "..."}]}
Response: {"choices": [{"message": {"content": "..."}}]}
```

## Sequence Diagrams

### Main Pipeline (with skip detection)

```
1. load_config() → resolve .env for API keys
   ↓
2. parse_cv(cv.path)
   → If data/cv_parsed.json exists AND not --rerun: LOAD (skip)
   → Else: parse CV → save data/cv_parsed.json
   ↓
3. scrape_jobs(search.urls)
   → If data/apify_results.json exists AND not --rerun: LOAD (skip)
   → Else: scrape → save data/apify_results.json
   ↓
4. filter_jobs(jobs, cv_text)  # Uses LLM structured output
   → If data/filtered_jobs.json exists AND not --rerun: LOAD (skip)
   → Else: call LLM → save data/filtered_jobs.json
   ↓
5. Load processed_jobs.json (deduplication) - skip already processed
   ↓
6. For each NEW qualifying job:
    a. find_email(job.company)
       → If data/emails/{job.id}.json exists: SKIP
       → Else: call API → save data/emails/{job.id}.json
    b. personalize_cv(base_cv, job)
       → If data/cvs/personalized_cv_{job.id}.pdf exists: SKIP
       → Else: call LLM → generate PDF → save
    c. generate_cover_letter(job, cv_text)
       → If data/cover_letters/{job_id}.txt exists: SKIP
       → Else: call LLM → save
    d. create_draft(email, cover_letter, cv_attachment_path)
       → If data/drafts/{job_id}.json exists: SKIP
       → If --dry-run: log only, skip API
       → Else: call Gmail API → save
    e. Mark job processed in processed_jobs.json
   ↓
7. save run_summary.json
   ↓
8. Display progress with rich.progress
```

### CLI Arguments

```python
# For __main__.py
parser.add_argument("--step", type=int, choices=[1,2,3,4,5,6,7],
                 help="Start from step N")
parser.add_argument("--skip-steps", type=str,
                 help="Comma-separated steps to skip (e.g., '2,3')")
parser.add_argument("--rerun", action="store_true",
                 help="Clear all intermediate data before running")
parser.add_argument("--dry-run", action="store_true",
                 help="Don't call any external APIs")
parser.add_argument("--count", type=int, default=50,
                 help="Limit jobs to process")
parser.add_argument("--provider", choices=["local", "openai"],
                 default="local", help="LLM provider")
```

**Note:** Steps 4, 6b, and 6c use the LLM (OpenAI API or local Ollama). Parallel execution in step 6 reduces pipeline time from ~15min to ~3min for 50 jobs.

**Note:** Steps 4, 5a, and 5c use the LLM (OpenAI API). These are the only places where the LLM is called—not for routing, just for generating content.
1. load_config()
   ↓
2. parse_cv(cv.path)
   → save data/cv_parsed.json
   ↓
3. scrape_jobs(search.urls)
   → save data/apify_results.json
   ↓
4. filter_jobs(jobs, cv_text)  # Filters: qualification match + accepting applications
   → save data/filtered_jobs.json
   → save data/filtered_out_jobs.json
   ↓
5. For each job in filtered_jobs:
   a. personalize_cv(base_cv, job)
      → save data/cvs/personalized_cv_{job.id}.pdf
   b. find_email(job.company, job.hiring_manager)
      → save data/emails/{job.id}.json
   c. generate_cover_letter(job, cv_text)
      → save data/cover_letters/{job.id}.txt
   d. create_draft(email, cover_letter, cv_attachment)
      → save data/drafts/{job.id}.json
   ↓
6. save run_summary.json
```

## Error & Exception Handling

```python
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

class RateLimitError(Exception):
    """Raised when API returns 429"""
    pass

class APIError(Exception):
    """Raised for unrecoverable API errors"""
    pass

# Only retry on RateLimitError
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(RateLimitError)
)
def call_api_with_retry():
    try:
        return api_call()
    except RateLimitError:
        raise  # tenacity retries
    except APIError as e:
        log.error(f"Unrecoverable API error: {e}")
        return None  # skip, don't retry
```

| Error Type | Action |
|-----------|--------|
| Missing config | Raise ConfigError, exit |
| CV file not found | Raise FileNotFoundError, exit |
| Apify API error | Log, skip URL, continue |
| AnyMailFinder rate limit | Log warning, skip job (could fallback to company search) |
| Gmail API error | Log, skip job |
| OpenAI API error | Log, skip job |

## Testing Strategy

| Test Type | Coverage |
|----------|---------|
| Unit tests | config.py, filter.py (no API) |
| Integration tests | Full pipeline with mocked APIs |
| Dry-run tests | --dry-run flag, no API calls |

---

## Directory Structure

```
email-application-automation/
├── app/
│   ├── __main__.py          # CLI entry: python -m app run
│   ├── __init__.py
│   ├── config.py           # load_config()
│   ├── models.py          # Pydantic models
│   ├── agent.py           # Main orchestrator
│   └── tools/
│       ├── __init__.py
│       ├── cv_parser.py    # parse_cv()
│       ├── scraper.py     # scrape_jobs()
│       ├── filter.py       # filter_jobs()
│       ├── cv_personalizer.py  # personalize_cv()
│       ├── email_finder.py   # find_email()
│       ├── cover_letter.py   # generate_cover_letter()
│       └── gmail_draft.py   # create_draft()
├── config.yaml
├── pyproject.toml
├── requirements.txt
└── data/               # created at runtime
    ├── cv_parsed.json
    ├── apify_results.json
    ├── filtered_jobs.json
    ├── filtered_out_jobs.json
    ├── cvs/
    ├── emails/
    ├── cover_letters/
    ├── drafts/
    └── run_summary.json
```

---

## CLI Interface

```bash
# Normal run
python -m app run

# Dry-run (no API calls)
python -m app run --dry-run

# Help
python -m app run --help
```

---

## Config Validation

```python
import os
import re
from functools import lru_cache

def resolve_env_vars(value: str) -> str:
    """Resolve ${VAR_NAME} patterns in config values."""
    pattern = r'\$\{(\w+)\}'
    def replacer(match):
        var_name = match.group(1)
        return os.getenv(var_name, match.group(0))
    return re.sub(pattern, replacer, value)

def resolve_config_env_vars(config: dict) -> dict:
    """Recursively resolve environment variables in config."""
    if isinstance(config, dict):
        return {k: resolve_config_env_vars(v) for k, v in config.items()}
    elif isinstance(config, list):
        return [resolve_config_env_vars(item) for item in config]
    elif isinstance(config, str) and '${' in config:
        return resolve_env_vars(config)
    return config

# On startup
def validate_config(config: Config) -> None:
    if not config.search.urls:
        raise ConfigError("search.urls is required")
    if not config.cv.path:
        raise ConfigError("cv.path is required")
    # Check API keys exist
    required_keys = ["google", "anymailfinder", "apify", "openai"]
    for key in required_keys:
        if not config.api_keys.get(key):
            raise ConfigError(f"api_keys.{key} is required (or set as environment variable)")
```

**Note:** Secrets should be stored in `.env` file (loaded via `python-dotenv`), not in `config.yaml`. `config.yaml` should only contain non-secret configuration.

```yaml
# config.yaml (non-secret config only)
search:
  urls:
    - "https://www.linkedin.com/jobs/search-results/?keywords=..."
  count: 50
cv:
  path: "./cv.pdf"
gmail:
  draft_only: true
```

```bash
# .env (secrets - never commit)
GOOGLE_API_KEY=sk-...
ANYMAILFINDER_API_KEY=sk-...
APIFY_API_KEY=sk-...
OPENAI_API_KEY=sk-...
```