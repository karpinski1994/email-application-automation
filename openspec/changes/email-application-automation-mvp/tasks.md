## 0. Prerequisites (Check & Install Only What's Missing)

### 0.1 Check existing Python packages
- [ ] 0.1a Run: `pip list | grep -E "pydantic|httpx|rich|yaml"`
- [ ] 0.1b Run: `pip list | grep -E "google|oauth"`
- [ ] 0.1c Run: `pip list | grep -E "pdfplumber|weasyprint"`

### 0.2 Install missing dependencies only
- [ ] 0.2a `pip install pydantic-ai` - If not installed
- [ ] 0.2b `pip install httpx tenacity rich pyyaml python-dotenv` - Common deps
- [ ] 0.2c `pip install google-auth-oauthlib google-api-python-client` - Gmail
- [ ] 0.2d `pip install pdfplumber` - CV parsing

### 0.3 Install weasyprint (has system dependencies)
- [ ] 0.3a Test: `python -c "from weasyprint import HTML"` - Try import first
- [ ] 0.3b If fails: `pip install weasyprint`
- [ ] 0.3c If fails on Mac: `brew install cairo pango libffi` - System deps

### 0.4 Install Ollama (if using local LLM)
- [ ] 0.4a Check: `which ollama` OR `curl http://localhost:11434/v1/models`
- [ ] 0.4b If not installed: https://ollama.com/install
- [ ] 0.4c Pull model: `ollama pull qwen2.5:7b`
- [ ] 0.4d Test: `curl http://localhost:11434/v1/models`

---

## Implementation Plan - Data-Driven Caching Pattern

This implementation uses a data-driven caching pattern where every step checks `data/` for existing output before calling expensive APIs.

Each phase:
1. Implement the caching utility (the most important piece)
2. Create empty placeholder functions that return mock data
3. Test the orchestrator with mocks (instant, free)
4. Replace ONE mock with real code
5. Test that step works
6. Move to next phase

---

## Phase 1: Pipeline Skeleton & Caching Engine

### 1.1 Create Directory Structure
- [ ] 1.1a mkdir -p src/app/tools data/cvs data/emails data/cover_letters data/drafts

### 1.2 Create Caching Utility (app/utils.py)
- [ ] 1.2a Implement is_cached(path) - check if file exists and not empty
- [ ] 1.2b Implement save_json(path, data) - atomic write (temp + rename)
- [ ] 1.2c Implement load_json(path) - load and parse JSON
- [ ] 1.2d Test: Run python -c "from app.utils import is_cached, save_json, load_json"

### 1.3 Create Empty Placeholder Tools (returns mock data)
- [ ] 1.3a app/tools/cv_parser.py - returns mock "CV text"
- [ ] 1.3b app/tools/scraper.py - returns mock [Job, Job, Job]
- [ ] 1.3c app/tools/filter.py - returns mock [qualified jobs]
- [ ] 1.3d app/tools/email_finder.py - returns mock "email@test.com"
- [ ] 1.3e app/tools/cover_letter.py - returns mock "cover letter"
- [ ] 1.3f app/tools/cv_personalizer.py - creates dummy PDF
- [ ] 1.3g app/tools/gmail_draft.py - returns mock "draft_id"

### 1.4 Create Models (app/models.py)
- [ ] 1.4a Config model with yaml + env loading
- [ ] 1.4b Job model
- [ ] 1.4c RunSummary model

### 1.5 Build Orchestrator (app/agent.py) - ALL MOCKS
- [ ] 1.5a Implement run() with cache checks
- [ ] 1.5b Pipeline: CV → Scrape → Filter → For each job: Email → Letter → CV → Draft
- [ ] 1.5c Add --force flag to clear cache
- [ ] 1.5d Add --step flag to start from step N

### 1.6 Create CLI (app/__main__.py)
- [ ] 1.6a argparse with --force, --step, --dry-run, --count, --provider
- [ ] 1.6b Entry point: python -m app run

### TEST PHASE 1:
```bash
python -m app run
# Should create data/ with mock JSON files
python -m app run  
# Should load from cache instantly
python -m app run --force
# Should clear and recreate
```

---

## Phase 2: Real Config & CV Parsing

### 2.1 Implement app/config.py
- [ ] 2.1a Use pydantic-settings for .env loading
- [ ] 2.1b Use pyyaml for config.yaml loading
- [ ] 2.1c Validate required fields

### 2.2 Implement app/tools/cv_parser.py (REAL)
- [ ] 2.2a Use pdfplumber for PDF
- [ ] 2.2b Read TXT directly
- [ ] 2.2c Raise ValueError for unsupported format

### 2.3 Create config.yaml and .env.example
- [ ] 2.3a config.yaml with search.urls, llm settings
- [ ] 2.3b .env.example template (NO real keys)

### TEST PHASE 2:
```bash
rm data/cv_parsed.json
python -m app run --force
# Should parse real CV
cat data/cv_parsed.json | head -c 200
```

---

## Phase 3: Apify Scraper

### 3.1 Implement app/tools/scraper.py (REAL)
- [ ] 3.1a Use httpx.AsyncClient
- [ ] 3.1b Use /run-sync-get-dataset-items endpoint (FIXED)
- [ ] 3.1c Add Tenacity retry for 429

### TEST PHASE 3:
```bash
rm data/apify_results.json
python -m app run --force --step=2
# Should hit Apify
python -m app run
# Should use cache, no Apify call
```

---

## Phase 4: LLM Client & Job Filter

### 4.1 Implement app/llm_client.py
- [ ] 4.1a Setup AsyncOpenAI
- [ ] 4.1b Support local (Ollama) and OpenAI provider
- [ ] 4.1c get_semaphore() - returns 1 for local, 5 for cloud

### 4.2 Implement app/tools/filter.py (REAL)
- [ ] 4.2a Use Pydantic AI with result_type=FilterDecision
- [ ] 4.2b Truncate job.description[:2000] (context fix)
- [ ] 4.2c Save filtered_jobs.json and filtered_out_jobs.json

### TEST PHASE 4:
```bash
rm data/filtered_jobs.json
python -m app run --force --step=3
# Should call LLM
python -m app run
# Should use cache
```

---

## Phase 5: Email Discovery (Per-Job Caching)

### 5.1 Implement app/tools/email_finder.py (REAL)
- [ ] 5.1a Use httpx with correct endpoint (FIXED)
- [ ] 5.1b Per-job caching: data/emails/{job_id}.json
- [ ] 5.1c Add circuit breaker

### TEST PHASE 5:
```bash
python -m app run --step=5
# Should find emails per-job
# Kill process mid-run
# Run again - should resume from where it stopped
```

---

## Phase 6: Generation (CV & Cover Letter)

### 6.1 Implement app/tools/cover_letter.py (REAL)
- [ ] 6.1a LLM call with system prompt
- [ ] 6.1b Save data/cover_letters/{job_id}.txt

### 6.2 Implement app/tools/cv_personalizer.py (REAL)
- [ ] 6.2a LLM generates JSON
- [ ] 6.2b Jinja2 HTML template
- [ ] 6.2c Wrap WeasyPrint in asyncio.to_thread() (FIXED)
- [ ] 6.2d Save data/cvs/{job_id}.pdf

### TEST PHASE 6:
```bash
python -m app run --step=6
# Should generate PDFs and cover letters
ls data/cvs/
cat data/cover_letters/*.txt | head
```

---

## Phase 7: Gmail Draft Creator

### 7.1 Implement app/tools/gmail_draft.py (REAL)
- [ ] 7.1a OAuth flow
- [ ] 7.1b MIME multipart (text + PDF)
- [ ] 7.1c Base64 encode
- [ ] 7.1d Call Gmail API
- [ ] 7.1e Per-job caching: data/drafts/{job_id}.json

### TEST PHASE 7:
```bash
python -m app run --step=7
# Should create real Gmail drafts
# Check Gmail web UI for drafts
python -m app run
# Should use cache, no duplicate drafts
```

---

## Phase 8: Concurrency & Hardening

### 8.1 Add Async Concurrency
- [ ] 8.1a Use asyncio.Semaphore from get_semaphore()
- [ ] 8.1b Fix dry-run: return mock data immediately

### 8.2 Fix Race Condition
- [ ] 8.2a Change to JSON Lines format (.jsonl) for atomic append

### 8.3 Final Testing
- [ ] 8.3a Run with OpenAI (parallel)
- [ ] 8.3b Run with Ollama (sequential)
- [ ] 8.3c Run --dry-run (no API calls)

---

## DEBUG COMMANDS REFERENCE

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