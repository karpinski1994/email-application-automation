# High-Level Design – AI Automated Email Job Application System

## Conceptual Architecture

**Pattern:** Deterministic Python Async Pipeline with Agentic Tools

The system follows a **deterministic orchestrator + agentic tools** pattern:
- **Orchestrator:** Pure Python async pipeline (NOT an LLM agent) - controls flow, parallelism, error handling
- **Tools:** Pydantic AI agents for cognitive tasks inside each step (filtering, CV generation, email discovery, cover letters)

This pattern is correct because:
- Workflow is rigidly linear (Scrape → Filter → Personalize → Email → Draft) - no dynamic branching
- Avoids cost/latency of LLM "what to do next" decisions
- Avoids hallucination risks (LLM skipping steps)
- Python controls the track; Pydantic AI handles the cognitive work on the track

```
┌──────────────────────────────────────────────────────────────┐
│              Deterministic Python Orchestrator            │
│                (agent.py - async pipeline)                 │
└─────────────────────┬────────────────────────────────────┘
                      │
        ┌────────────▼────────────┐
        │    Config Loader        │
        │    (config.py)          │
        └────────┬───────────────┘
                 │
        ┌────────▼────────────┐
        │    CV Parser       │
        │ (cv_parser.py)    │
        └────────┬─────────────┘
                 │
        ┌────────▼────────────┐
        │    Scraper         │
        │  (scraper.py)      │
        │   (Apify API)     │
        └────────┬─────────────┘
                 │
        ┌────────▼────────────┐
        │  Filter Agent      │
        │  (Pydantic AI)     │
        └────────┬─────────────┘
                 │
        ┌────────▼────────────┐
        │ CV Personalizer    │
        │  (Pydantic AI)    │
        └────────┬────────────┘
                 │
        ┌────────▼────────────┐
        │  Email Finder     │
        │  (Pydantic AI)   │
        └────────┬────────────┘
                 │
        ┌────────▼────────────┐
        │ Cover Letter      │
        │  (Pydantic AI)   │
        └────────┬────────────┘
                 │
        ┌────────▼────────────┐
        │  Gmail Draft      │
        │ (gmail_draft.py)  │
        └──────────────────┘
```

**Key Distinction:**
- **Orchestrator (Python):** "I am at the filtering step, execute your logic" - deterministic
- **Agentic Tool (Pydantic AI):** "Evaluate this CV + job, return structured decision" - cognitive
┌──────────────────────────────────────────────────────────────┐
│                    Orchestrator Agent                     │
│                   (Pydantic AI Agent)                    │
└─────────────────────┬────────────────────────────────────┘
                      │
        ┌────────────▼────────────┐
        │    Config Loader        │
        │    (config.py)        │
        └────────┬─────────────┘
                 │
        ┌────────▼────────────┐
        │    CV Parser       │
        │ (cv_parser.py)    │
        └────────┬─────────────┘
                 │
        ┌────────▼────────────┐
        │    Scraper       │
        │  (scraper.py)    │
        │   (Apify)       │
        └────────┬─────────────┘
                 │
        ┌────────▼────────────┐
        │    Filter         │
        │  (filter.py)     │
        │   (LLM-based)   │
        └────────┬─────────────┘
                 │
        ┌────────▼────────────┐
        │ CV Personalizer  │
        │(cv_personalizer) │
        └────────┬────────────┘
                 │
        ┌────────▼────────────┐
        │  Email Finder    │
        │(email_finder.py)│
        └────────┬────────────┘
                 │
        ┌────────▼────────────┐
        │ Cover Letter     │
        │(cover_letter.py) │
        └────────┬────────────┘
                 │
        ┌────────▼────────────┐
        │  Gmail Draft      │
        │ (gmail_draft.py)  │
        └──────────────────┘
```

## System Decomposition

| Module/Service | Responsibility | Input | Output |
|---------------|---------------|-------|--------|
| `config.py` | Load & validate config.yaml | `config.yaml` | `Config` object |
| `cv_parser.py` | Parse PDF/TXT CV | CV file path | Raw CV text |
| `scraper.py` | Scrape jobs via Apify | Search URLs | `list[Job]` |
| `filter.py` | Filter jobs (qualification + accepting status) | Jobs + CV text | `tuple[qualifying, rejected]` |
| `cv_personalizer.py` | Generate personalized CV PDF | Base CV + Job | PDF file path |
| `email_finder.py` | Discover hiring manager email | Company name | Email address |
| `cover_letter.py` | Generate personalized cover letter | Job + CV | Cover letter text |
| `gmail_draft.py` | Create Gmail draft | To, subject, body, attachment | Draft ID |

## Data Flow & Communication

### Synchronous Sequential Flow

All components execute **synchronously** in a single thread:

```
Config (YAML) → CV Parse → Scrape → Filter → For Each Job:
    → Personalize CV → Find Email → Generate Cover Letter → Create Gmail Draft
```

**Protocol:** Direct Python function calls (no HTTP/REST between modules)

**Rationale:** 
- Simple for 50 jobs/day (low volume)
- No need for async processing
- Easier debugging with sequential logs

### Data Passing Format

| Transition | Data Format |
|------------|------------|
| Config → CV Parser | `Config` object |
| CV Parser → Scraper | `str` (CV text) |
| Scraper → Filter | `list[Job]` (Pydantic models) |
| Filter → Personalizer | `list[Job]`, `str` (CV text) |
| Personalizer → Email Finder | `Job` object |
| Email Finder → Cover Letter | `str` (email), `Job` |
| Cover Letter → Gmail Draft | `str` (letter), `Path` (CV PDF) |

## Integration Architecture

### External Services

| Service | Integration Method | Purpose |
|---------|------------------|---------|
| **Apify** | HTTP REST API | Job scraping |
| **AnyMailFinder** | Via Pydantic AI Agent tool | Email discovery (with fallback) |
| **Gmail API** | OAuth2 + REST | Draft creation |
| **Ollama** | HTTP REST (OpenAI-compatible) | LLM for cognitive tasks |

### Why Pydantic AI Agents for Tools (Not for Orchestration!)

| Tool | Uses Pydantic AI Agent | Why |
|------|---------------------|-----|
| **Filter** | ✓ Yes | Cognitive evaluation, structured `FilterDecision` output |
| **CV Personalizer** | ✓ Yes | Structured JSON output → HTML template |
| **Email Finder** | ✓ Yes | Multi-tool reasoning (API → parse description → guess pattern) |
| **Cover Letter** | ✓ Yes | System prompt enforces professional tone |

| Component | NOT an LLM Agent | Why |
|-----------|----------------|-----|
| **Orchestrator** | ✗ Python only | Fixed pipeline, no "what to do next" decisions |

The orchestrator is a **deterministic Python async pipeline**. The Pydantic AI agents are used **inside** each tool step for cognitive work.

### Local LLM (Ollama) Recommendation

**Runtime:** [Ollama](https://ollama.com) - runs locally, exposes OpenAI-compatible API

**Default Model:** `qwen2.5:7b`
- Excellent at JSON formatting and instruction following
- ~8GB RAM/VRAM (runs on M1/M2/M3 Macs, RTX 3060+)
- Zero cost, zero API rate limits, 100% private

**Alternative Models:**
- `llama3.2:3b` - Speed demon (~4GB VRAM)
- `gemma2:9b` - Best quality (~12GB VRAM)

**Configuration in `config.yaml`:**
```yaml
llm:
  provider: "local"  # or "openai"
  model: "qwen2.5:7b"
  base_url: "http://localhost:11434/v1"
  api_key: "ollama"
```

**Benefits:**
- Zero cost per run (vs ~$4.50 with OpenAI)
- No PII sent to external services
- No rate limits
- Parallel processing possible (reduces ~15min to ~3min)

### API boundaries

- **Inbound:** `config.yaml` (YAML file read), CV file (PDF/TXT)
- **Outbound:** Gmail draft creation only
- **All other integrations:** Call-level, not exposed as REST

## High-Level Data Strategy

### Source of Truth

| Data Type | Storage | Source |
|----------|---------|--------|
| Config | `config.yaml` | User-provided YAML |
| CV | File system | User-provided PDF/TXT |
| Job listings | `data/apify_results.json` | Apify API |
| Filtered jobs | `data/filtered_jobs.json` | LLM filter |
| Personalized CVs | `data/cvs/*.pdf` | Generated PDF |
| Email addresses | `data/emails/*.json` | AnyMailFinder |
| Cover letters | `data/cover_letters/*.txt` | LLM generation |
| Gmail drafts | Gmail API | Created drafts |
| Run summary | `data/run_summary.json` | Orchestrator |

### Data Consistency

- **No database:** Flat file storage only
- **No caching:** Each run is independent
- **Idempotency:** Runs can be re-executed (overwrites files)

### Local Storage Structure (Checkpoints for Skip Detection)

```
data/
├── config_loaded.json      # Config used
├── cv_parsed.json        # Step 1 checkpoint
├── apify_results.json     # Step 2 checkpoint
├── filtered_jobs.json     # Step 3 checkpoint
├── filtered_out_jobs.json # Rejected jobs
├── processed_jobs.json    # Deduplication tracking
├── cvs/
│   └── personalized_cv_{job_id}.pdf  # Step 4: Per-job
├── emails/
│   └── {job_id}.json  # Step 5: Per-job
├── cover_letters/
│   └── {job_id}.txt  # Step 6: Per-job
├── drafts/
│   └── {job_id}.json # Step 7: Per-job
├── gmail_token.json   # OAuth token
└── run_summary.json # Final summary
```

**Key Feature:** Each step's output is saved as a checkpoint. On subsequent runs:
- If checkpoint exists + not --rerun → Load from file (skip API call)
- This prevents wasting Apify/AnyMailFinder credits on re-scraping
data/
├── config_loaded.json      # Config used
├── cv_parsed.json        # Parsed CV text
├── apify_results.json     # Raw job listings
├── filtered_jobs.json     # Qualifying jobs
├── filtered_out_jobs.json # Rejected jobs
├── processed_jobs.json    # Deduplication: job_id -> draft_id mapping
├── cvs/
│   └── personalized_cv_{job_id}.pdf
├── emails/
│   └── {job_id}.json
├── cover_letters/
│   └── {job_id}.txt
├── drafts/
│   └── {job_id}.json
├── gmail_token.json      # Gmail OAuth token
└── run_summary.json
```

## Infrastructure & Deployment View

### Runtime Environment

| Component | Environment |
|-----------|--------------|
| Python | 3.11+ (local) |
| OS | macOS, Linux |
| Deployment | Manual (`python -m app run`) |

### Future (Out of Scope for MVP)

| Component | Planned |
|-----------|---------|
| Scheduling | Cron-based or FastAPI scheduler |
| Cloud deployment | Not planned |
| Containerization | Docker (optional for portability) |

### No External Infrastructure Required

- No database server
- No message queue
- No load balancer
- No CDN

## Cross-Cutting Concerns

### Security

| Concern | Implementation |
|---------|----------------|
| API Keys | Environment variables only |
| CV Data | Local file storage only |
| Gmail OAuth | User authentication flow |
| No secrets in code | All via `config.yaml` + env vars |
| PII Handling | Config option `privacy.redact_pii: true` + redaction step before LLM |
| Prompt Injection | Sanitize job descriptions before LLM prompts |

### Observability

| Concern | Implementation |
|---------|----------------|
| Logging | structlog after each step |
| Progress | rich.progress bar during parallel processing |
| Metrics | `run_summary.json` (jobs found, filtered, drafts created) |
| Errors | Logged to console + stored in `run_summary.json` |
| Debugging | All intermediate data stored locally |

### Scalability

**Current limits (50 jobs/day):**
- Sequential processing: sufficient for MVP
- Apify rate limits: 1 request per URL
- AnyMailFinder: 50-100 lookups/month (free tier)
- Gmail API: No strict limits for drafts

**Scaling path (if needed):**
- Parallel job processing with `asyncio`
- Batch Apify requests
- FastAPI wrapper for concurrent runs

### Error Handling

| Error Type | Handling |
|------------|----------|
| Config invalid | Raise error, exit |
| CV not found | Raise error, exit |
| Apify failure | Log error, skip URL, continue |
| AnyMailFinder rate limit | Skip job or use free fallback |
| Gmail failure | Log error, skip job |
| LLM failure | Log error, skip job |

## Component Interaction Diagram

### End-to-End Flow

```
1. User configures config.yaml
2. User runs: python -m app run

   [Config Loader]
   → load_config()
   → validate API keys
   → Output: Config

   [CV Parser]
   → parse_cv(config.cv.path)
   → Output: cv_text

   [Scraper]
   → scrape_jobs(config.search.urls)
   → Apify API call
   → Output: list[Job]

   [Filter]
   → filter_jobs(jobs, cv_text)
   → LLM evaluation (qualification match + accepting status)
   → Output: tuple[qualifying, rejected]

   For each qualifying job:
      [CV Personalizer]
      → personalize_cv(cv_text, job)
      → LLM generates tailored content
      → Output: PDF path

      [Email Finder]
      → find_email(job.company)
      → AnyMailFinder API call
      → Output: email address

      [Cover Letter]
      → generate_cover_letter(job, cv_text)
      → LLM generates letter
      → Output: letter text

      [Gmail Draft]
      → create_draft(to, subject, body, attachment)
      → Gmail API call
      → Output: draft ID

   [Orchestrator]
   → write run_summary.json
   → Output: RunSummary

3. User reviews Gmail drafts in Gmail UI
4. User sends manually when ready
```

### Parallel Opportunities

The following can run in parallel **if scaled**:
- `personalize_cv()` for different jobs (no dependencies)
- `find_email()` for different jobs (no dependencies)
- `generate_cover_letter()` for different jobs (no dependencies)

Current implementation: Sequential (simplest for MVP)