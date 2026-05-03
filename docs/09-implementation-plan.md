# Implementation Plan - Email Application Automation MVP

## Overview: Data-Driven Caching Pattern

This implementation uses a **data-driven caching pattern** where every step checks `data/` for existing output before calling expensive APIs. This saves API credits, speeds up development, and allows resuming from failures.

### Key Principles:
1. **Check before calling APIs** - If data file exists, load instead of re-calling API
2. **Phase-by-phase development** - Build pipeline first with mocks, then replace with real code
3. **Test after each step** - Verify each module works before moving on
4. **Per-job caching** - Resume from failures without losing progress

---

## Step 0: Prerequisites (Check & Install Only What's Missing)

### 0.1 Check Existing Python Packages
- [ ] 0.1a Run: `pip list | grep -E "pydantic|httpx|rich|yaml"`
- [ ] 0.1b Run: `pip list | grep -E "google|oauth"`
- [ ] 0.1c Run: `pip list | grep -E "pdfplumber|weasyprint"`

### 0.2 Install Missing Dependencies Only
- [ ] 0.2a `pip install pydantic-ai` - If not installed
- [ ] 0.2b `pip install httpx tenacity rich pyyaml python-dotenv` - Common deps
- [ ] 0.2c `pip install google-auth-oauthlib google-api-python-client` - Gmail
- [ ] 0.2d `pip install pdfplumber` - CV parsing

### 0.3 Install Weasyprint (Has System Dependencies)
- [ ] 0.3a Test: `python -c "from weasyprint import HTML"` - Try import first
- [ ] 0.3b If fails: `pip install weasyprint`
- [ ] 0.3c If fails on Mac: `brew install cairo pango libffi` - System deps

### 0.4 Install Ollama (If Using Local LLM)
- [ ] 0.4a Check: `which ollama` OR `curl http://localhost:11434/v1/models`
- [ ] 0.4b If not installed: https://ollama.com/install
- [ ] 0.4c Pull model: `ollama pull qwen2.5:7b`
- [ ] 0.4d Test: `curl http://localhost:11434/v1/models`

---

## Step 1: Project Setup

- [ ] 1.1 Create `src/app/` directory structure with `__init__.py` files
- [ ] 1.2 Create `config.yaml` (NO secrets - all in .env)
- [ ] 1.3 Create `.env.example` template (no actual keys)
- [ ] 1.4 Add `data/` and `*.env` to `.gitignore`
- [ ] 1.5 Test: `python -c "from app.config import load_config; print('OK')"`

---

## Step 2: Core Infrastructure - Test Individually

- [ ] 2.1 `models.py` - Test: `python -c "from app.models import Job, Config; print('OK')"`
- [ ] 2.2 `config.py` - Test: `python -c "from app.config import load_config; c=load_config(); print(c.llm.provider)"`
- [ ] 2.3 `utils.py` - Test: atomic_write_json, get_llm_client

---

## Step 3: Module: CV Parser (Step 1) - Test Independently

- [ ] 3.1 Implement `cv_parser.py` with `parse_cv()`
- [ ] 3.2 Test: `python -c "from app.cv_parser import parse_cv; print(parse_cv('your_cv.pdf')[:100])"`
- [ ] 3.3 SKIP: If `data/cv_parsed.json` exists, load from file instead of parsing

**Cache File:** `data/cv_parsed.json`

---

## Step 4: Module: Job Scraper (Step 2) - Test Independently

- [ ] 4.1 Implement `scraper.py` with `scrape_jobs()`
- [ ] 4.2 Test: `python -c "from app.scraper import scrape_jobs; jobs=scrape_jobs(['your_url']); print(len(jobs))"`
- [ ] 4.3 SKIP: If `data/apify_results.json` exists, load from file instead of scraping

**Cache File:** `data/apify_results.json`

---

## Step 5: Module: Job Filter (Step 3) - Test Independently

- [ ] 5.1 Implement `filter.py` with filtering_agent
- [ ] 5.2 Test: `python -c "from app.filter import filter_jobs; print('OK')"`
- [ ] 5.3 SKIP: If `data/filtered_jobs.json` exists, load from file

**Cache Files:** `data/filtered_jobs.json`, `data/filtered_out_jobs.json`

---

## Step 6: Module: CV Personalizer (Step 4) - Test Independently

- [ ] 6.1 Implement `cv_personalizer.py` with cv_agent + weasyprint
- [ ] 6.2 Test: Generate one PDF manually
- [ ] 6.3 SKIP: If `data/cvs/personalized_cv_{job_id}.pdf` exists, skip generation

**Cache File:** `data/cvs/personalized_cv_{job_id}.pdf` (per-job)

---

## Step 7: Module: Email Finder (Step 5) - Test Independently

- [ ] 7.1 Implement `email_finder.py` with Pydantic AI agent
- [ ] 7.2 Test: `python -c "from app.email_finder import find_email; print(find_email('Company'))"`
- [ ] 7.3 SKIP: If `data/emails/{job_id}.json` exists, load from file

**Cache File:** `data/emails/{job_id}.json` (per-job)

---

## Step 8: Module: Cover Letter (Step 6) - Test Independently

- [ ] 8.1 Implement `cover_letter.py` with Pydantic AI agent
- [ ] 8.2 Test: `python -c "from app.cover_letter import generate_cover_letter; print('OK')"`
- [ ] 8.3 SKIP: If `data/cover_letters/{job_id}.txt` exists, load from file

**Cache File:** `data/cover_letters/{job_id}.txt` (per-job)

---

## Step 9: Module: Gmail Draft (Step 7) - Test Independently

- [ ] 9.1 Implement `gmail_draft.py` with OAuth flow
- [ ] 9.2 Test: Create one draft manually with --dry-run
- [ ] 9.3 SKIP: If `data/drafts/{job_id}.json` exists, skip creation

**Cache File:** `data/drafts/{job_id}.json` (per-job)

---

## Step 10: Orchestrator (All Steps Together)

- [ ] 10.1 Implement `agent.py` with deterministic async orchestrator
- [ ] 10.2 Add step detection: Check each data/ file exists before running step
- [ ] 10.3 Add --step flag: `python -m app run --step=3` (start from step 3)
- [ ] 10.4 Add --skip-steps flag: `python -m app run --skip-steps=1,2,3`
- [ ] 10.5 Add --rerun flag: `python -m app run --rerun` (clear all intermediate data)
- [ ] 10.6 Test full pipeline: `python -m app run --dry-run`

---

## Step 11: CLI & Testing

- [ ] 11.1 Create `__main__.py` with argparse:
  - [ ] 11.1a --step N: Start from step N (1-7)
  - [ ] 11.1b --skip-steps: Comma-separated steps to skip
  - [ ] 11.1c --rerun: Force rerun, clear intermediate data
  - [ ] 11.1d --dry-run: Don't call Gmail API
  - [ ] 11.1e --count N: Limit jobs to process
  - [ ] 11.1f --provider: local or openai
- [ ] 11.2 Test individual steps
- [ ] 11.3 Test with --step flag
- [ ] 11.4 Test with --dry-run

---

## Step 12: Cost & Token Tracking

- [ ] 12.1 Track tokens per LLM call
- [ ] 12.2 Add token budget limit with abort
- [ ] 12.3 Log budget usage in run_summary.json

---

## Pipeline Steps Summary

| Step | Name | Cache File | Saves |
|------|------|-----------|-------|
| 1 | Parse CV | data/cv_parsed.json | PDF parsing |
| 2 | Scrape Jobs | data/apify_results.json | Apify credits |
| 3 | Filter Jobs | data/filtered_jobs.json | LLM tokens |
| 4 | Personalize CV | data/cvs/{job_id}.pdf | LLM + WeasyPrint |
| 5 | Find Email | data/emails/{job_id}.json | API calls (per-job) |
| 6 | Cover Letter | data/cover_letters/{job_id}.txt | LLM tokens (per-job) |
| 7 | Gmail Draft | data/drafts/{job_id}.json | API calls (per-job) |

---

## Debug Commands Reference

```bash
# Full run from scratch
python -m app run --rerun

# Start from specific step (1-7)
python -m app run --step=3

# Skip certain steps
python -m app run --skip-steps=2

# Dry run (no API calls)
python -m app run --dry-run

# Test specific step only
python -m app run --step=4 --count=1

# View cached data
ls data/
cat data/cv_parsed.json | jq
cat data/apify_results.json | jq '. | length'

# Clear specific cache
rm data/apify_results.json
rm -r data/emails/*
```

---

## Phase-by-Phase Notes

### Why Build Pipeline First?
1. **Instant testing** - Mocks run in milliseconds, not minutes
2. **Isolated failures** - Each step works before adding complexity
3. **Credit protection** - Real APIs only called when needed
4. **Resume capability** - Kill process mid-run, restart from where you left off

### Per-Job Caching (Steps 4-7)
For steps 4-7, each job has its own cache file. This means:
- If job 23 fails, jobs 1-22 are already cached
- Restarting resumes from job 23
- No need to re-process successful jobs

### Concurrency Note
- **Local LLM (Ollama):** Use `Semaphore(1)` - sequential due to VRAM limits
- **OpenAI:** Use `Semaphore(5)` - parallel execution works