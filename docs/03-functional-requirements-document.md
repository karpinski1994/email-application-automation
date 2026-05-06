# Functional Requirements Document – AI Automated Email Job Application System

## Functional Overview

The system automates job applications by reading a base CV, scraping job listings, filtering unsuitable roles, personalizing the CV per job, discovering hiring manager emails, and creating Gmail drafts—all configured via `config.yaml`.

## User Personas & Roles

| Role | Description | Permissions |
|------|-------------|-------------|
| End User | Solo job seeker running the application | Full access |
| Developer | Same user maintaining/extending code | Read/write code |

## User Stories

| ID | Story |
|----|-------|
| US1 | "As a user, I want to configure all settings in `config.yaml` so I don't need to pass CLI arguments" |
| US2 | "As a user, I want the system to filter out jobs I don't qualify for OR no longer accepting applications so I don't waste time applying" |
| US3 | "As a user, I want personalized CVs generated for each job so my applications stand out" |
| US4 | "As a user, I want Gmail drafts created (not sent) so I can review before applying" |
| US5 | "As a user, I want a dry-run mode so I can test without consuming API credits" |
| US6 | "As a user, I want logging so I can debug when something fails" |

## Functional Requirements

| ID | Requirement | Priority |
|----|--------------|----------|
| FR1 | System shall read `config.yaml` on startup and validate all required fields exist | Must have |
| FR2 | System shall validate all required API keys are provided in environment or config (GOOGLE_API_KEY, ANYMAILFINDER_API_KEY, APIFY_API_KEY) | Must have |
| FR3 | System shall parse base CV from path specified in `config.yaml` (PDF/TXT) | Must have |
| FR4 | System shall scrape job listings from URLs defined in `config.yaml.search.urls` | Must have |
| FR5 | System shall filter jobs where candidate qualifications mismatch job requirements OR job is no longer accepting applications (LLM-based) | Must have |
| FR6 | System shall generate personalized CV for each qualifying job (tailored, not complete rewrite) | Must have |
| FR7 | System shall discover hiring manager email via AnyMailFinder API using job company | Must have |
| FR7-FREE | System shall discover hiring manager email via free fallback (DuckDuckGo + email pattern guessing + MX verification) | Future (May have) |
| FR8 | System shall generate personalized cover letter using job listing + base CV | Must have |
| FR9 | System shall create Gmail draft with personalized CV attached and cover letter in body | Must have |
| FR10 | System shall log all operations after each step | Should have |
| FR11 | System shall store all intermediate data locally for debugging | Should have |
| FR12 | System shall support dry-run mode (skip API calls, generate local files only) | Should have |
| FR13 | System shall detect completed steps and skip re-execution to save API credits | Must have |
| FR14 | System shall support --step flag to start from specific step | Should have |
| FR15 | System shall support --skip-steps flag to skip specific steps | Should have |
| FR16 | System shall support --rerun flag to force clean rerun | Should have |

## Workflow & Logic

### Pipeline Steps

| Step | Name | Input | Output | Intermediate Data File |
|------|------|-------|--------|-----------------|
| 1 | Parse CV | CV file (PDF/TXT) | cv_text | data/cv_parsed.json |
| 2 | Scrape Jobs | search URLs | list[Job] | data/apify_results.json |
| 3 | Filter Jobs | jobs + cv_text | qualifying + rejected | data/filtered_jobs.json, data/filtered_out_jobs.json |
| 4 | Personalize CV | job + cv_text | PDF | data/cvs/{job_id}/personalized_cv.pdf |
| 5 | Find Email | company | email | data/emails.json |
| 6 | Create Gmail Draft | email + letter + attachment | draft_id | data/cvs/{job_id}/email.json, data/drafts/{job_id}.json |

### Main Pipeline (with skip detection)

```
1. Load config.yaml
2. Validate config (required fields: search.urls, cv.path, gmail.draft_only)
3. Parse CV file → If data/cv_parsed.json exists: LOAD (skip step)
4. For each URL in config.search.urls:
    5. Scrape job listings via Apify → If data/apify_results.json exists: LOAD (skip step)
    6. Filter: Compare candidate qualifications; check accepting status
       → If data/filtered_jobs.json exists: LOAD (skip step)
    7. If mismatch OR not accepting: skip job, continue
    8. Else: proceed
    9. Personalize CV (LLM) → If data/cvs/{job_id}/personalized_cv.pdf exists: SKIP
    10. Find hiring manager email (AnyMailFinder) → If data/emails.json exists: SKIP
    11. Compose application email → If data/cvs/{job_id}/email.json exists: SKIP
    12. Create Gmail draft with CV attached → If data/drafts/{job_id}.json exists: SKIP
    13. If search.count reached: break
14. Log summary (jobs processed, drafts created, errors)
```

### CLI Flags

| Flag | Description |
|------|------------|
| `--step N` | Start from step N (1-6) |
| `--force` | Force rerun, ignore cache |
| `--cached` | Use cached jobs only |
| `--dry-run` | Don't call any external APIs (for testing) |
| `--limit N` | Limit jobs to process |
| `--filter-only` | Stop after filtering (step 3) |
| `--include-applied` | Include already applied jobs |

## Data Requirements

### Input (config.yaml)

| Field | Type | Required | Validation |
|-------|------|----------|------------|
| `search.urls` | list[string] | Yes | At least 1 valid URL |
| `search.count` | int | Yes | 1-50 |
| `cv.path` | string | Yes | Valid file path |
| `gmail.draft_only` | bool | Yes | True/False |

### Output (each job)

| Field | Description |
|-------|-------------|
| `personalized_cv_[job_id].pdf` | CV tailored to job |
| `cover_letter_[job_id].txt` | Personalized cover letter |
| Gmail draft | Draft in Gmail with CV attached |

## Exception Handling

| Scenario | Handling |
|----------|----------|
| `config.yaml` missing | Raise error, exit |
| Missing API keys (GOOGLE_API_KEY, ANYMAILFINDER_API_KEY, APIFY_API_KEY) | Raise error, exit (skip if FREE_FALLBACK enabled) |
| CV file not found | Raise error, exit |
| Apify API failure | Log error, skip URL, continue |
| AnyMailFinder rate limit | Log warning, fallback to FREE_FALLBACK mode if enabled, else skip job |
| No jobs match filter | Log info, exit gracefully |
| Gmail API failure | Log error, skip job, continue |
| LLM API failure | Log error, skip job, continue |

---

### Free Fallback Pipeline (Future)

When AnyMailFinder is unavailable or rate-limited, the system shall support a free email discovery pipeline:

```
1. DuckDuckGo search: "hiring manager [role] [company].com linkedin"
2. Extract LinkedIn profile URL from results
3. (Optional) Use agent-browser to navigate LinkedIn profile
4. Extract name + company domain
5. Guess email pattern: first.last@domain.com
6. Verify via MX record lookup (dns-python)
7. If valid: use for draft; if invalid: skip job
```

**Trade-offs:**
- DDG rarely returns direct emails; requires guess + verify
- agent-browser is Node.js — adds architectural complexity if used
- Higher failure rate than paid API

---

### Local Storage Structure

```
data/
├── config_loaded.json      # Config used
├── cv_parsed.json        # Parsed CV text
├── apify_results.json     # Raw job listings from Apify
├── filtered_jobs.json     # Jobs that passed filter
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

- Each step logs progress after execution
- All data stored locally for debugging and reprocessing

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