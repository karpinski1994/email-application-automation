# Step 4: Email Finding — Implementation Plan

## Overview

Add email finding as the new step 4, before CV personalization (which becomes step 5). This ensures we only personalize CVs for jobs where we have a deliverable email address.

## New Pipeline Order

| Step | What | Output File |
|------|------|-------------|
| 1 | Parse CV | `data/cv_parsed.json` |
| 2 | Scrape Jobs | `data/apify_results.json` |
| 3 | Filter Jobs | `data/filtered_jobs.json` |
| **4** | **Find Emails (NEW)** | `data/emails.json` |
| 5 | Personalize CVs + Compose Emails | `data/cvs/{job_id}/` |

## AnyMailFinder API Details

- **Endpoint**: `POST https://api.anymailfinder.com/v5.1/find-email/decision-maker`
- **Auth**: `Authorization: eUSnO2MeVwx6dpKNq7kY5LMi` (from `.env` `ANYMAILFINDER_API_KEY`)
- **Request body**:
  ```json
  {
    "domain": "company.com",
    "decision_maker_category": ["engineering", "hr"]
  }
  ```
- **Response**:
  ```json
  {
    "email": "someone@company.com",
    "email_status": "valid"
  }
  ```
- `email_status` values: `"valid"`, `"risky"`, `"not_found"`
- Billing: 1 credit per valid email found; risky/not_found are free

## Output Format — `data/emails.json`

```json
{
  "4409863569": {
    "email": "someone@jobsai.com",
    "status": "valid",
    "company": "Jobs Ai",
    "domain_used": "jobsai.com",
    "category": "engineering"
  },
  "4396747770": {
    "email": "",
    "status": "not_found",
    "company": "Horizontal Talent",
    "domain_used": "horizontaltalent.com",
    "category": "engineering"
  }
}
```

---

## Implementation Steps

### Step 1: Add `EmailFinderConfig` to `models.py`

**File**: `src/app/models.py`

Add new config model:

```python
class EmailFinderConfig(BaseModel):
    """Email finder configuration."""
    provider: str = "anymailfinder"
    api_key: str = ""
    categories: list[str] = Field(default_factory=lambda: ["engineering", "hr"])
    max_domain_attempts: int = 3
```

Add to `Config` class:

```python
class Config(BaseModel):
    ...
    email_finder: EmailFinderConfig = Field(default_factory=EmailFinderConfig)
```

### Step 2: Add `email_finder` section to `config.yaml`

**File**: `config.yaml`

```yaml
# Email Finder Configuration
email_finder:
  provider: "anymailfinder"
  api_key: "${ANYMAILFINDER_API_KEY}"
  categories:
    - "engineering"
    - "hr"
  max_domain_attempts: 3
```

### Step 3: Add domain resolution helper

**File**: `src/app/tools/email_finder.py`

Add function to convert company name → list of candidate domains:

```python
def _company_to_domains(company: str) -> list[str]:
    """Generate candidate domains from a company name.

    Tries common TLDs in order: .com, .io, .co
    Strips common suffixes like "Inc.", "LLC", etc.
    """
```

Logic:
1. Strip suffixes: "Inc.", "LLC", "Ltd.", "Corp.", "Co."
2. Lowercase, remove spaces/special chars
3. Try `.com` first, then `.io`, then `.co`
4. Return list of candidate domains

Examples:
- `"GovCIO"` → `["govcio.com", "govcio.io", "govcio.co"]`
- `"Jobs Ai"` → `["jobsai.com", "jobsai.io", "jobsai.co"]`
- `"Horizontal Talent"` → `["horizontaltalent.com", ...]`

### Step 4: Rewrite `email_finder.py` with real API integration

**File**: `src/app/tools/email_finder.py`

Functions to implement:

#### `find_email_for_company(company: str, api_key: str, categories: list[str]) -> dict`

- Calls AnyMailFinder decision-maker endpoint
- Tries candidate domains from `_company_to_domains()` one at a time
- On first `"valid"` or `"risky"` result, returns immediately
- On `"not_found"`, tries next domain variant
- Returns `{"email": "...", "status": "valid"|"risky"|"not_found", "domain_used": "..."}`

Pseudocode:
```
domains = _company_to_domains(company)
for domain in domains[:max_attempts]:
    response = POST /v5.1/find-email/decision-maker
        domain=domain
        decision_maker_category=categories
    if response.email_status in ("valid", "risky"):
        return {email, status, domain_used=domain}
    if rate_limited:
        sleep(2)
        retry
return {email: "", status: "not_found", domain_used=domains[0]}
```

#### `find_emails_for_jobs(jobs: list[Job], config: EmailFinderConfig) -> dict`

- Iterates all filtered jobs
- Calls `find_email_for_company()` for each
- Respects cached results in `data/emails.json` (skip if already found with `"valid"` status)
- Sleeps 2s between API calls (polite rate limiting)
- Returns the full `emails.json` dict

Pseudocode:
```
results = load cached emails.json if exists
for job in jobs:
    if job.id in results and results[job.id]["status"] == "valid":
        continue  # skip cached
    result = find_email_for_company(job.company, api_key, categories)
    results[job.id] = {email, status, company, domain_used, category}
    sleep(2)
save emails.json
return results
```

### Step 5: Update `agent.py` — new step 4 block

**File**: `src/app/agent.py`

Changes:
1. Move lazy import: `if step <= 4: from app.tools.email_finder import find_emails_for_jobs`
2. Add step 4 block between step 3 and current step 4
3. Renumber current step 4 to step 5
4. Update lazy import for step 5: `if step <= 5: from app.tools.cv_personalizer import ...`

New step 4 block:
```python
# Step 4: Find Emails
if step <= 4:
    emails_path = DATA_DIR / "emails.json"
    if step == 4:
        filtered_path = DATA_DIR / "filtered_jobs.json"
        if filtered_path.exists():
            filtered_data = load_json(filtered_path)
            qualifying = [Job(**j) for j in filtered_data]

    from app.tools.email_finder import find_emails_for_jobs
    emails = await find_emails_for_jobs(qualifying, config.email_finder)
    save_json(emails_path, emails)

    valid_count = sum(1 for v in emails.values() if v["status"] == "valid")
    risky_count = sum(1 for v in emails.values() if v["status"] == "risky")
    not_found_count = sum(1 for v in emails.values() if v["status"] == "not_found")
    print(f"Step 4: Found {valid_count}/{len(emails)} emails ({valid_count} valid, {risky_count} risky, {not_found_count} not found)")

    if step == 4:
        # Early return for step=4 only
        ...
```

### Step 6: Update `cv_personalizer.py` — step 5, filter by email availability

**File**: `src/app/tools/cv_personalizer.py`

Changes to `personalize_all_filtered()`:

1. Load `data/emails.json`
2. Filter jobs list: only process jobs where `emails[job.id]["status"]` is `"valid"` or `"risky"`
3. Skip jobs with `"not_found"` status (log message)
4. Pass the actual email address to `personalize_cv()` so it can write it into `email.json`

New parameter: `personalize_cv(cv_text, job, force, to_email=None)`

When `to_email` is provided, write it to `email.json` `to` field instead of `"PENDING: ..."`.

### Step 7: Update `email_composer.py` — accept real `to_email`

**File**: `src/app/tools/email_composer.py`

Changes to `compose_email()`:

- Add parameter: `to_email: str = None`
- If `to_email` is provided, use it for `to` field
- If not, fall back to `"PENDING: find email for {company}"`

```python
def compose_email(job: Job, cv_text: str, cv_data: dict = None, to_email: str = None) -> dict:
    ...
    return {
        "to": to_email or f"PENDING: find email for {job.company}",
        ...
    }
```

### Step 8: Update `__main__.py` — step number references

**File**: `src/app/__main__.py`

- Update step range documentation if needed
- Ensure `--step=4` now routes to email finding
- Ensure `--step=5` routes to CV personalization

### Step 9: Clean up old step 4 data

After running the new step 5, the `email.json` files in `data/cvs/{id}/` should have real email addresses instead of `"PENDING: ..."`. Run:

```bash
source .venv/bin/activate && PYTHONPATH=src python3 -m app run --step=5 --force
```

---

## Execution Order

| # | Task | File | Estimated Time |
|---|------|------|----------------|
| 1 | Add `EmailFinderConfig` model | `src/app/models.py` | 2 min |
| 2 | Add config section | `config.yaml` | 1 min |
| 3 | Rewrite `email_finder.py` with real API + domain resolver | `src/app/tools/email_finder.py` | 10 min |
| 4 | Update `agent.py` step numbering + new step 4 | `src/app/agent.py` | 5 min |
| 5 | Update `cv_personalizer.py` for step 5 + email filtering | `src/app/tools/cv_personalizer.py` | 5 min |
| 6 | Update `email_composer.py` for `to_email` param | `src/app/tools/email_composer.py` | 2 min |
| 7 | Update `__main__.py` step references | `src/app/__main__.py` | 2 min |
| 8 | Syntax check | — | 1 min |
| 9 | Test step 4: `python3 -m app run --step=4 --force` | — | 2 min |
| 10 | Test step 5: `python3 -m app run --step=5 --force` | — | 1 min |
| 11 | Verify emails in `data/cvs/{id}/email.json` | — | 1 min |

**Total estimated: ~30 min**

---

## Testing Commands

```bash
# Step 4: Find emails
source .venv/bin/activate && PYTHONPATH=src python3 -m app run --step=4 --force

# Inspect results
cat data/emails.json | python3 -m json.tool

# Step 5: Personalize CVs (only for jobs with valid emails)
source .venv/bin/activate && PYTHONPATH=src python3 -m app run --step=5 --force

# Verify email.json has real addresses
cat data/cvs/*/email.json | python3 -m json.tool
```

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Company domain guess is wrong | Try up to 3 TLDs (.com, .io, .co) |
| AnyMailFinder API down/fails | Catch exceptions, mark as `"not_found"`, log warning |
| API key invalid | Log clear error, fall back to `"not_found"` status |
| Rate limiting | 2-second delay between requests |
| Credits exhausted | `"not_found"` is free, only `"valid"` costs credits |
| Cached email becomes stale | `--force` flag re-queries all jobs |
