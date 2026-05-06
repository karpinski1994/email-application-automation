# Software Requirements Specification – AI Automated Email Job Application System

## 1. Introduction

### Purpose
This SRS defines the functional and non-functional requirements for an AI-driven job application automation system that scrapes job listings, personalizes CVs, discovers hiring manager emails, and creates Gmail drafts.

### Scope
- Configuration via YAML file (`config.yaml`)
- Deterministic Python async pipeline with LLM-powered tools
- Integration with Apify, AnyMailFinder, Gmail, Ollama APIs
- Output: Gmail drafts with personalized CV attached

### Definitions & Acronyms

| Term | Definition |
|------|------------|
| CV | Curriculum Vitae / resume document |
| Apify | Web scraping platform |
| AnyMailFinder | Email discovery API |
| LLM | Large Language Model (Ollama or OpenAI) |
| Draft | Gmail draft (not sent) |
| Ollama | Local LLM runtime |

---

## 2. Overall Description

### Product Perspective
- Standalone Python CLI application
- Orchestrated by deterministic Python async pipeline with LLM-powered tools
- Runs locally or on server

### User Classes & Characteristics

| Class | Description |
|-------|------------|
| End User | Solo job seeker; runs `python -m app run` |
| Developer | Extends/modifies codebase |

### Operating Environment

| Component | Requirement |
|-----------|-------------|
| Python | 3.11+ |
| OS | macOS, Linux |
| Dependencies | See `pyproject.toml` |

---

## 3. System Features & Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| SR1 | System shall load and validate `config.yaml` on startup | Must have |
| SR2 | System shall validate required API keys are set (GOOGLE_API_KEY, ANYMAILFINDER_API_KEY, APIFY_API_KEY) | Must have |
| SR3 | System shall parse base CV from configured path (PDF/TXT) | Must have |
| SR4 | System shall scrape job listings from configured URLs via Apify actor | Must have |
| SR5 | System shall filter jobs where candidate qualifications mismatch job requirements OR job is no longer accepting applications | Must have |
| SR6 | System shall generate personalized CV for each qualifying job | Must have |
| SR7 | System shall discover hiring manager email via AnyMailFinder | Must have |
| SR8 | System shall generate personalized cover letter (LLM) | Must have |
| SR9 | System shall create Gmail draft with CV attached | Must have |
| SR10 | System shall respect `search.count` limit in config | Must have |
| SR11 | System shall log all operations | Should have |
| SR12 | System shall support dry-run mode (no API calls) | Should have |
| SR13 | System shall detect completed steps and skip re-execution to save API credits | Must have |
| SR14 | System shall support --step flag to start from specific step | Should have |
| SR15 | System shall support --skip-steps flag to skip specific steps | Should have |
| SR16 | System shall support --rerun flag to force clean rerun | Should have |

---

## 4. External Interface Requirements

### CLI Usage

| Command | Description |
|---------|------------|
| `python -m app run` | Run full pipeline |
| `python -m app run --step=3` | Start from step 3 (filter) |
| `python -m app run --skip-steps=2` | Skip step 2 (scrape) |
| `python -m app run --rerun` | Clear data and rerun everything |
| `python -m app run --dry-run` | Test without API calls |
| `python -m app run --count=10` | Process only 10 jobs |
| `python -m app run --provider=openai` | Use OpenAI instead of local |

### Hardware/Software Interfaces

| Interface | Description |
|-----------|------------|
| Apify API | Job scraping |
| AnyMailFinder API | Email discovery |
| Gmail API | Draft creation |
| OpenAI API | LLM for CV/cover letter generation |

### Communication Interfaces

| Protocol | Purpose |
|----------|---------|
| HTTPS | All external API calls |

---

## 5. Non-Functional Requirements

### Performance

| Metric | Target |
|--------|--------|
| Time to first draft (excluding API calls) | <30 seconds |
| Time between drafts | <10 seconds |
| Maximum jobs per run | 50 (configurable) |

### Security

| Requirement | Description |
|-------------|-------------|
| API keys | Loaded from environment variables or config (not hardcoded) |
| OAuth2 | Google Gmail API uses OAuth2 tokens |
| Credentials file | Stored in user home directory (`~/.config/email-app/`) |

### Reliability & Availability

| Metric | Target |
|--------|--------|
| Success rate | ≥90% (excluding API rate limits) |
| Error handling | All failures logged, no silent drops |
| Retry logic | Exponential backoff for transient failures |

### Scalability

| Component | Limit |
|-----------|-------|
| Concurrent jobs | 1 (sequential) |
| Daily runs | No limit (depends on API rate limits) |

### Maintainability

| Requirement | Description |
|-------------|-------------|
| Type safety | Pydantic models for all data structures |
| Logging | Structured JSON logs |
| Config | All settings in `config.yaml` |

---

## 6. Constraints & Compliance

| Constraint | Details |
|------------|---------|
| Python version | 3.11+ |
| Free tier limits | AnyMailFinder: 50-100/month; Apify: free tier |
| Email sending | Drafts only (not sent automatically) |
| Rate limits | Respects API tier limits |

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

Each step shall log its progress and store intermediate data locally:

```
config.yaml → Load & Validate
     ↓ Log: "Config loaded successfully"
     ↓ Store: None
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

### Local Storage Structure

All intermediate data shall be stored in `data/` directory:

```
data/
├── config_loaded.json        # Config used
├── cv_parsed.json         # Parsed CV text
├── apify_results.json    # Raw job listings from Apify
├── filtered_jobs.json    # Jobs that passed filter
├── filtered_out_jobs.json # Jobs that failed filter
├── cvs/
│   └── personalized_cv_[job_id].pdf
├── emails/
│   └── [job_id].json
├── cover_letters/
│   └── [job_id].txt
├── drafts/
│   └── [job_id].json
└── run_summary.json
```

- Logs after each step for traceability
- All data stored locally for debugging and reprocessing
- Can resume from any step using stored data