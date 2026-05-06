# Technical Design Document – AI Automated Email Job Application System

## 1. Overview

The Email Application Automation system is a deterministic Python async pipeline that automates the job application process. It uses local LLMs (Ollama) for cognitive tasks, reducing costs and maintaining privacy.

**Core Pattern:** Deterministic orchestrator + LLM-powered tools

- **Orchestrator:** Pure Python async pipeline - controls flow, parallelism, error handling, caching
- **Tools:** Use LLM via direct API calls for cognitive tasks inside each step

This pattern ensures:
- Rigidly linear workflow (no dynamic branching decisions)
- No cost/latency of LLM "what to do next" decisions
- No hallucination risks (LLM skipping steps)

## 2. Directory Structure

```
email-application-automation/
├── src/
│   └── app/
│       ├── __init__.py
│       ├── __main__.py          # Entry point: python -m app
│       ├── config.py            # Config loading from YAML + .env
│       ├── agent.py             # Pipeline orchestrator (async)
│       ├── models.py            # Pydantic data models
│       ├── utils.py             # Shared utilities
│       │
│       └── tools/               # Pipeline step implementations
│           ├── cv_parser.py         # PDF/TXT CV parsing (pdfplumber)
│           ├── scraper.py          # Apify LinkedIn job scraping (async polling)
│           ├── filter.py             # Two-stage job filtering (embedding + LLM)
│           ├── email_finder.py      # AnyMailFinder API with web fallback
│           ├── web_email_finder.py # Web search fallback for emails
│           ├── cv_personalizer.py  # CV personalization with PDF generation
│           ├── email_composer.py   # Email subject/body generation
│           ├── cover_letter.py    # (legacy - now in email_composer)
│           ├── gmail_draft.py    # Gmail API integration (OAuth2)
│           └── applied_tracker.py # Track applied jobs to avoid duplicates
│       │
│       └── templates/
│           └── cv_template.html   # Jinja2 CV HTML template
│
├── data/                   # Generated at runtime (gitignored)
├── config.yaml             # Main configuration
├── config.example.yaml     # Example configuration
├── .env                    # API keys (gitignored)
├── pyproject.toml
└── README.md
```

## 3. Data Models

### 3.1 Configuration Models (`models.py`)

```python
from pydantic import BaseModel, Field
from typing import Optional

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
```

### 3.2 Job Model

```python
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
```

### 3.3 Filter Decision Model

```python
class FilterDecision(BaseModel):
    is_qualified: bool
    is_accepting_applications: bool
    reason: Optional[str] = None
```

### 3.4 Run Summary Model

```python
class RunSummary(BaseModel):
    started_at: str
    finished_at: str
    jobs_found: int
    jobs_filtered: int
    jobs_qualified: int
    drafts_created: int
    errors: list[str]
```

## 4. Pipeline Steps

The pipeline consists of 6 sequential steps:

| Step | Component | Description |
|------|----------|------------|
| 1 | CV Parser | Parse PDF/TXT CV into text |
| 2 | Scraper | Scrape jobs via Apify |
| 3 | Filter | Two-stage filtering (embedding + LLM) |
| 4 | Email Finder | Find hiring manager emails |
| 5 | CV Personalizer | Generate personalized CV PDFs |
| 6 | Gmail Draft | Create Gmail drafts |

### 4.1 Step 1: CV Parser (`tools/cv_parser.py`)

Parses CV files (PDF or TXT) into text content.

- **Input:** CV file path (PDF or TXT)
- **Output:** Raw CV text
- **Library:** pdfplumber for PDF, built-in for TXT

### 4.2 Step 2: Scraper (`tools/scraper.py`)

Scrapes jobs from LinkedIn using Apify.

- **Input:** Job search URLs
- **Output:** List of Job objects
- **Library:** httpx (async)
- **Features:** Async polling with status check

### 4.3 Step 3: Filter (`tools/filter.py`)

Two-stage job filtering:
1. **Stage 1:** Embedding-based pre-filtering (nomic-embed-text)
2. **Stage 2:** LLM detailed scoring (llama3.2)

- **Input:** Jobs + CV text
- **Output:** Tuple of (qualifying_jobs, rejected_jobs)
- **Features:** Threshold-based filtering, pre-filters jobs without company website

### 4.4 Step 4: Email Finder (`tools/email_finder.py`)

Finds hiring manager emails via AnyMailFinder API with web fallback.

- **Input:** Company name / domain
- **Output:** Email address with status
- **Features:** API + web search fallback

### 4.5 Step 5: CV Personalizer (`tools/cv_personalizer.py`)

Generates personalized CV PDFs for each job.

- **Input:** Base CV + Job
- **Output:** PDF file path
- **Features:** Jinja2 template + weasyprint HTML→PDF

### 4.6 Step 6: Gmail Draft (`tools/gmail_draft.py`)

Creates Gmail drafts with PDF attachments.

- **Input:** To, subject, body, PDF attachment
- **Output:** Draft ID
- **Features:** OAuth2 + Gmail API

## 5. Data Flow

```
User runs: python -m app

1. load_config() → Config object
2. parse_cv() → CV text (Step 1)
3. scrape_jobs() → list[Job] (Step 2)
4. filter_jobs() → (qualifying, rejected) (Step 3)
5. For each qualifying job:
   a. find_email() → email (Step 4)
   b. personalize_cv() → PDF (Step 5)
   c. compose_email() → email body (Step 5)
   d. create_draft() → draft ID (Step 6)
6. save run_summary.json
```

## 6. CLI Interface

```bash
# Run full pipeline
python -m app run

# Run specific step
python -m app run --step 3

# Force re-run (ignore cache)
python -m app run --force

# Dry run (no external APIs)
python -m app run --dry-run

# Use cached jobs only
python -m app run --cached

# Include already applied jobs
python -m app run --include-applied

# Stop after filtering
python -m app run --filter-only

# Limit jobs
python -m app run --limit 10
```

## 7. Configuration

### 7.1 Config File (`config.yaml`)

```yaml
search:
  urls:
    - "https://www.linkedin.com/jobs/search-results/?keywords=..."
  count: 50

cv:
  path: "./cv.pdf"

gmail:
  draft_only: true
  credentials_path: "credentials.json"

llm:
  provider: "local"
  model: "qwen2.5:7b"
  base_url: "http://localhost:11434/v1"
  api_key: "ollama"

apify:
  api_token: ""
  actor_id: "apify/linkedin-jobs-scraper"

filter:
  embedding_shortlist_size: 20
  llm_fit_threshold: 70
  embedding_model: "nomic-embed-text"
  scoring_model: "llama3.2"

email_finder:
  provider: "anymailfinder"
  api_key: ""
  categories: ["engineering", "hr"]
  max_domain_attempts: 3
  fallback_enabled: true

privacy:
  redact_pii: true
```

### 7.2 Environment Variables (`.env`)

```bash
APIFY_API_KEY=...
ANYMAILFINDER_API_KEY=...
OPENAI_API_KEY=...
```

## 8. Data Storage

### 8.1 Local Files

```
data/
├── cv_parsed.json              # Step 1 output
├── apify_results.json        # Step 2 output
├── filtered_jobs.json         # Step 3 output (qualifying)
├── filtered_out_jobs.json   # Step 3 output (rejected)
├── emails.json               # Step 4 output
├── cvs/
│   └── {job_id}/
│       ├── personalized_cv.pdf
│       ├── personalized_cv.html
│       ├── email.json
│       └── job_info.json
├── drafts/
│   └── {draft_id}.json
├── run_summary.json
└── gmail_token.json         # OAuth cache
```

### 8.2 Data Consistency

- **No database:** Flat file storage only
- **Checkpoint caching:** Each step's output saved as checkpoint
- **Idempotency:** Runs can be re-executed (overwrites files)

## 9. Local LLM Integration

### 9.1 Ollama

**Runtime:** Ollama - runs locally, exposes OpenAI-compatible API

**Default Model:** `qwen2.5:7b`
- Excellent at JSON formatting and instruction following
- ~8GB RAM/VRAM (runs on M1/M2/M3 Macs, RTX 3060+)
- Zero cost, zero API rate limits, 100% private

**Alternative Models:**
- `llama3.2:3b` - Speed demon (~4GB VRAM)
- `gemma2:9b` - Best quality (~12GB VRAM)

### 9.2 Configuration

```yaml
llm:
  provider: "local"  # or "openai"
  model: "qwen2.5:7b"
  base_url: "http://localhost:11434/v1"
  api_key: "ollama"
```

## 10. External Integrations

| Service | Integration Method | Purpose |
|---------|------------------|---------|
| Apify | HTTP REST API | Job scraping |
| AnyMailFinder | HTTP REST API | Email discovery |
| Gmail API | OAuth2 + REST | Draft creation |
| Ollama | HTTP REST | LLM for cognitive tasks |

## 11. Error Handling

| Error Type | Handling |
|------------|----------|
| Config invalid | Raise error, exit |
| CV not found | Use mock CV |
| Apify failure | Log error, continue to next URL |
| AnyMailFinder rate limit | Skip job or use fallback |
| Gmail failure | Log error, skip job |
| LLM failure | Log error, skip job |

## 12. Security

| Concern | Implementation |
|---------|----------------|
| API Keys | Environment variables only |
| CV Data | Local file storage only |
| Gmail OAuth | User authentication flow |
| No secrets in code | All via config.yaml + env vars |

## 13. Testing Strategy

| Test Type | Coverage |
|----------|---------|
| Unit tests | config.py, filter.py (no API) |
| Integration tests | Full pipeline with mocked APIs |
| Dry-run tests | --dry-run flag, no API calls |

## 14. Future Enhancements

| Component | Planned |
|-----------|---------|
| Scheduling | Cron-based or FastAPI scheduler |
| Cloud deployment | Docker support |
| Parallel processing | asyncio for concurrent runs |