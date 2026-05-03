# Technical Requirements Document – AI Automated Email Job Application System

## System Architecture

- **Pattern:** Single orchestrator agent (Pydantic AI) with modular tool handlers
- **Rationale:** Pydantic AI provides built-in agent orchestration with type-safe tools; replaces complex n8n JSON logic
- **Flow:** Config → CV Parse → Scrape → Filter → Personalize → Email → Draft → Gmail

## Technology Stack

| Layer | Technology | Version |
|-------|-----------|---------|
| Runtime | Python | 3.11+ |
| Agent Framework | Pydantic AI | Latest |
| HTTP Client | httpx | Latest |
| CV Parsing | pdfplumber | Latest |
| YAML Config | pydantic-settings + pyyaml | Latest |
| Logging | structlog | Latest |
| PDF Generation | weasyprint + Jinja2 | Latest |

## Data Design & Schema

### config.yaml schema (Pydantic model)

```python
class Search(BaseModel):
    urls: list[str]
    count: int = 50

class CV(BaseModel):
    path: str

class Gmail(BaseModel):
    draft_only: bool = True

class Config(BaseModel):
    search: Search
    cv: CV
    gmail: Gmail
    api_keys: dict[str, str]
```

### Job Listing Schema

```python
class Job(BaseModel):
    id: str
    title: str
    company: str
    description: str
    url: str
    location: str | None = None
```

## API & Integration Specifications

| Service | API | Endpoints |
|---------|-----|-----------|
| Apify | REST | `POST /v2/acts/{actor_id}/run` |
| AnyMailFinder | REST | `POST /v1/find` |
| Gmail | REST | `POST /gmail/v1/users/me/drafts` |
| OpenAI | REST | `POST /v1/chat/completions` |

## Infrastructure & Deployment

- **Runtime:** Local Python (CLI) or Docker container
- **Storage:** Local filesystem (`data/` directory)
- **Config location:** Project root `config.yaml`
- **Credentials:** Environment variables

## Security Architecture

- **API Keys:** Loaded from environment variables
- **OAuth2:** Google Gmail API uses OAuth2 (token file in `~/.config/email-app/`)
- **No hardcoded secrets**

## Performance & Scalability

- Sequential job processing (no concurrency in MVP)
- Rate limiting built into API clients
- Configurable job count limit

## Error Handling & Logging

- All errors logged with context
- Structured JSON logs via structlog
- Each step logs completion/failure
- Run summary with counts

---

### Directory Structure

```
├── app/
│   ├── __main__.py
│   ├── config.py
│   ├── models.py
│   ├── tools/
│   │   ├── cv_parser.py
│   │   ├── scraper.py
│   │   ├── filter.py
│   │   ├── cv_personalizer.py
│   │   ├── email_finder.py
│   │   ├── cover_letter.py
│   │   └── gmail_draft.py
│   ├── agent.py
│   └── logging.py
├── config.yaml
├── pyproject.toml
└── data/  # created at runtime
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

api_keys:
  google: "${GOOGLE_API_KEY}"
  anymailfinder: "${ANYMAILFINDER_API_KEY}"
  apify: "${APIFY_API_KEY}"
```

---

### Data Flow & Logging

Each step logs progress and stores data locally:

```
config.yaml → Load & Validate
     ↓ Log: "Config loaded successfully"
     ↓ Store: data/config_loaded.json
     ↓
Base CV (PDF/TXT) → Parse
     ↓ Log: "CV parsed: X pages, Y characters"
     ↓ Store: data/cv_parsed.json
     ↓
Job URLs → Apify scraper → Job listings
     ↓ Log: "Scraped X jobs from Y URLs"
     ↓ Store: data/apify_results.json
     ↓
Filter (qualification mismatch + not accepting applications) → Qualifying jobs
     ↓ Log: "Filtered X jobs (Y disqualified/not accepting)"
     ↓ Store: data/filtered_jobs.json, data/filtered_out_jobs.json
     ↓
For each job:
  → Personalize CV (LLM)
     ↓ Log: "CV personalized for [job_title]"
     ↓ Store: data/cvs/personalized_cv_[job_id].pdf
  → Find email (AnyMailFinder)
     ↓ Log: "Email found: [email]"
     ↓ Store: data/emails/[job_id].json
  → Generate cover letter (LLM)
     ↓ Log: "Cover letter generated"
     ↓ Store: data/cover_letters/[job_id].txt
  → Create Gmail draft
     ↓ Log: "Draft created: [draft_id]"
     ↓ Store: data/drafts/[job_id].json
     ↓
Summary logs
     ↓ Log: "Run complete: X drafts created, Y errors"
     ↓ Store: data/run_summary.json
```

---

### Local Storage Structure

```
data/
├── config_loaded.json        # Config used
├── cv_parsed.json         # Parsed CV text (Step 1)
├── apify_results.json     # Raw job listings from Apify (Step 2)
├── filtered_jobs.json      # Jobs that passed filter (Step 3)
├── filtered_out_jobs.json # Jobs that failed filter (Step 3)
├── processed_jobs.json   # Job IDs already processed (deduplication)
├── cvs/
│   └── personalized_cv_{job_id}.pdf  # Step 4: CVs per job
├── emails/
│   └── {job_id}.json   # Step 5: Found emails
├── cover_letters/
│   └── {job_id}.txt   # Step 6: Cover letters
├── drafts/
│   └── {job_id}.json # Step 7: Gmail drafts
└── run_summary.json   # Final summary
```

**Skip Detection Logic:**
- Each intermediate file acts as a checkpoint
- If file exists + no --rerun flag → Load instead of re-calling API
- This saves API credits by not re-scraping or re-filtering