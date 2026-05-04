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
- [x] 0.1a Run: `pip list | grep -E "pydantic|httpx|rich|yaml"` → FOUND: pydantic 2.12.5, httpx 0.28.1, rich 13.9.4, pyyaml (installed)
- [x] 0.1b Run: `pip list | grep -E "google|oauth"` → FOUND: requests-oauthlib 2.0.0 (google-auth-oauthlib needs install)
- [x] 0.1c Run: `pip list | grep -E "pdfplumber|weasyprint"` → NOT FOUND (needed install)

### 0.2 Install Missing Dependencies Only
- [x] 0.2a `pip install pydantic-ai` - Already installed
- [x] 0.2b `pip install httpx tenacity rich pyyaml python-dotenv` - Already installed
- [x] 0.2c `pip install google-auth-oauthlib google-api-python-client` - INSTALLED
- [x] 0.2d `pip install pdfplumber` - INSTALLED in venv
- [x] 0.2e **Note:** `sentence-transformers` is NOT required.
  We use Ollama's native embedding API (`/api/embeddings`) directly via `httpx`.
  This avoids the `torch` dependency conflict.

### 0.3 Install Weasyprint (Has System Dependencies)
- [x] 0.3a Test: `python -c "from weasyprint import HTML"` → SUCCESS (system deps OK)
- [x] 0.3b If fails: `pip install weasyprint` - Already installed in step 0.2
- [x] 0.3c If fails on Mac: `brew install cairo pango libffi` - System deps not needed

### 0.4 Install Ollama (If Using Local LLM)
- [x] 0.4a Check: `which ollama` OR `curl http://localhost:11434/v1/models` → INSTALLED at /usr/local/bin/ollama
- [x] 0.4b If not installed: https://ollama.com/install - NOT NEEDED (already installed)
- [x] 0.4c Pull models:
  - `ollama pull qwen2.5:7b` - INSTALLED (4.7 GB) — for CV personalization, cover letters
  - `ollama pull nomic-embed-text` - INSTALLED (274 MB) — for job embedding similarity (Stage 1)
  - `ollama pull llama3.2` - INSTALLED (2.0 GB) — for job scoring (Stage 2)
- [x] 0.4d Test: `curl http://localhost:11434/v1/models` → Server responds (running)
- [x] 0.4e Verify embedding API: `curl -s http://localhost:11434/api/embeddings -d '{"model":"nomic-embed-text","prompt":"test"}' | head -c 200` → works

---

## Step 1: Project Setup

- [x] 1.1 Create `src/app/` directory structure with `__init__.py` files
- [x] 1.2 Create `config.yaml` (NO secrets - all in .env)
- [x] 1.3 Create `.env.example` template (no actual keys)
- [x] 1.4 Add `data/` and `*.env` to `.gitignore`
- [x] 1.5 Test: `python -c "from app.config import load_config; print('OK')"` → SUCCESS

---

## Step 2: Core Infrastructure - Test Individually

- [x] 2.1 `models.py` - Test: `python -c "from app.models import Job, Config; print('OK')"` → SUCCESS
- [x] 2.2 `config.py` - Test: `python -c "from app.config import load_config; c=load_config(); print(c.llm.provider)"` → SUCCESS
- [x] 2.3 `utils.py` - Test: atomic_write_json, get_llm_client → SUCCESS

---

## Step 3: Module: CV Parser (Step 1) - Test Independently

- [x] 3.1 Implement `cv_parser.py` with `parse_cv()`
- [x] 3.2 Test: `python -c "from app.cv_parser import parse_cv; print(parse_cv('your_cv.pdf')[:100])"`
- [x] 3.3 SKIP: If `data/cv_parsed.json` exists, load from file instead of parsing

**Cache File:** `data/cv_parsed.json`

---

## Step 4: Module: Job Scraper (Step 2) - Test Independently

- [x] 4.1 Implement `scraper.py` with `scrape_jobs()`
- [x] 4.2 Test: `python -c "from app.scraper import scrape_jobs; jobs=scrape_jobs(['your_url']); print(len(jobs))"`
- [x] 4.3 SKIP: If `data/apify_results.json` exists, load from file instead of scraping

**Cache File:** `data/apify_results.json`

---

## Step 5: Module: Job Filter (Step 3) - Two-Stage Approach

- [x] 5.1 Implement two-stage filtering in `filter.py`:
  - Stage 1: Embedding pre-filtering (nomic-embed-text via Ollama API)
    * Computes CV embedding, job embeddings, cosine similarity
    * Keeps top N jobs (default 20) for Stage 2
    * Uses Ollama's native embedding API at `/api/embeddings`
  - Stage 2: LLM scoring (llama3.2 via Ollama)
    * Batches all shortlisted jobs into one prompt
    * Scores each job 0-100, parses response
    * Filters jobs with score >= threshold (default 70)
  - No sentence-transformers needed (uses Ollama API directly)
- [x] 5.2 Test: `python -c "from app.filter import filter_jobs; print('OK')"` → SUCCESS
- [x] 5.3 SKIP: If `data/filtered_jobs.json` exists, load from file

**Cache Files:** `data/filtered_jobs.json`, `data/filtered_out_jobs.json`
**Ollama Models:** `nomic-embed-text` (embedding), `llama3.2` (scoring)

- [x] 5.4 Tested with mock data: ✅ Works — 1 qualified (Frontend Engineer), 1 rejected (Junior Developer)
- [x] 5.5 Uses OpenAI-compatible endpoint for LLM scoring (reliable)

---

## Step 6: Module: CV Personalizer (Step 4) - Test Independently

- [x] 6.1 Implement `cv_personalizer.py` with cv_agent + weasyprint (mock)
- [x] 6.2 Test: Generate one PDF manually
- [x] 6.3 SKIP: If `data/cvs/personalized_cv_{job_id}.pdf` exists, skip generation

**Cache File:** `data/cvs/personalized_cv_{job_id}.pdf` (per-job)

---

## Step 7: Module: Email Finder (Step 5) - Test Independently

- [x] 7.1 Implement `email_finder.py` with Pydantic AI agent (mock)
- [x] 7.2 Test: `python -c "from app.email_finder import find_email; print(find_email('Company'))"`
- [x] 7.3 SKIP: If `data/emails/{job_id}.json` exists, load from file

**Cache File:** `data/emails/{job_id}.json` (per-job)

---

## Step 8: Module: Cover Letter (Step 6) - Test Independently

- [x] 8.1 Implement `cover_letter.py` with Pydantic AI agent (mock)
- [x] 8.2 Test: `python -c "from app.cover_letter import generate_cover_letter; print('OK')"` → SUCCESS
- [x] 8.3 SKIP: If `data/cover_letters/{job_id}.txt` exists, load from file

**Cache File:** `data/cover_letters/{job_id}.txt` (per-job)

---

## Step 9: Module: Gmail Draft (Step 7) - Test Independently

- [x] 9.1 Implement `gmail_draft.py` with OAuth flow (mock)
- [x] 9.2 Test: Create one draft manually with --dry-run → SUCCESS (5 drafts created)
- [x] 9.3 SKIP: If `data/drafts/{job_id}.json` exists, skip creation

**Cache File:** `data/drafts/{job_id}.json` (per-job)

---

## Step 10: Orchestrator (All Steps Together)

- [x] 10.1 Implement `agent.py` with deterministic async orchestrator
- [x] 10.2 Add step detection: Check each data/ file exists before running step
- [x] 10.3 Add --step flag: `python -m app run --step=3` (start from step 3)
- [x] 10.4 Add --skip-steps flag: `python -m app run --skip-steps=1,2,3`
- [x] 10.5 Add --rerun flag: `python -m app run --rerun` (clear all intermediate data)
- [x] 10.6 Test full pipeline: `python -m app run --dry-run` → SUCCESS

---

## Step 11: CLI & Testing

- [x] 11.1 Create `__main__.py` with argparse:
  - [x] 11.1a --step N: Start from step N (1-7)
  - [x] 11.1b --skip-steps: Comma-separated steps to skip
  - [x] 11.1c --rerun: Force rerun, clear intermediate data
  - [x] 11.1d --dry-run: Don't call Gmail API
  - [x] 11.1e --count N: Limit jobs to process
  - [x] 11.1f --provider: local or openai
- [x] 11.2 Test individual steps
- [x] 11.3 Test with --step flag
- [x] 11.4 Test with --dry-run

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
python -m app run --skip_steps=2

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

---

## Next Steps (Phase 1: LLM Integration)

1. **Implement real LLM calls** in:
   - `filter.py` - job qualification with LLM
   - `cover_letter.py` - personalized letters
   - `cv_parser.py` - structured CV extraction

2. **Create config.yaml** with your settings:
   ```yaml
   llm:
     provider: "local"
     model: "qwen2.5:7b"
   ```

3. **Prepare your CV** file (PDF or TXT)

4. **Test with real data** using `--dry-run` first