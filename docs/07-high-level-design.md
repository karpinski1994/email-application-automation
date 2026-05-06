# High-Level Design – AI Automated Email Job Application System

## 1. Conceptual Architecture

**Pattern:** Deterministic Python Async Pipeline with LLM-powered Tools

The system follows a **deterministic orchestrator + LLM-powered tools** pattern:
- **Orchestrator:** Pure Python async pipeline - controls flow, parallelism, error handling, caching
- **Tools:** Use LLM via direct API calls (Ollama httpx) for cognitive tasks inside each step

This pattern is correct because:
- Workflow is rigidly linear (Parse CV → Scrape → Filter → Personalize → Email → Draft)
- Avoids cost/latency of LLM "what to do next" decisions
- Avoids hallucination risks (LLM skipping steps)
- Python controls the track; LLMs handle the cognitive work on the track

## 2. System Architecture Diagram

```
┌──────────────────────────────────────────────────────────────┐
│              Deterministic Python Orchestrator                │
│                (agent.py - async pipeline)                  │
│            Supports: --step N, --force, --dry-run          │
└─────────────────────┬────────────────────────────────────┘
                      │
         ┌────────────▼────────────┐
         │    Config Loader       │
         │    (config.py)         │
         └────────┬───────────────┘
                  │
         ┌────────▼────────────┐
         │    CV Parser         │
         │ (tools/cv_parser.py) │  ← pdfplumber (PDF) or read_text (TXT)
         └────────┬─────────────┘
                  │
         ┌────────▼────────────┐
         │    Scraper          │
         │ (tools/scraper.py)  │  ← Apify API (async polling)
         └────────┬─────────────┘
                  │
         ┌────────▼────────────┐
         │  Filter (Two-Stage) │
         │ (tools/filter.py)   │  ← Stage1: nomic-embed-text (embedding)
         └────────┬────────────┘        Stage2: llama3.2 (LLM scoring)
                  │
         ┌────────▼────────────┐
         │  Email Finder       │
         │ (tools/email_finder) │  ← AnyMailFinder API + web fallback
         └────────┬────────────┘
                  │
         ┌────────▼────────────┐
         │  CV Personalizer  │
         │(tools/cv_personalizer)│ ← Deterministic parse + LLM tailoring
         └────────┬────────────┘   ← weasyprint HTML→PDF
                  │
         ┌────────▼────────────┐
         │  Email Composer   │
         │(tools/email_composer)│ ← Template-based (no LLM)
         └────────┬────────────┘
                  │
         ┌────────▼────────────┐
         │  Gmail Draft       │
         │ (tools/gmail_draft) │  ← Gmail API OAuth2
         └─────────────────────┘
```

## 3. System Decomposition

| Module/Service | Responsibility | Input | Output |
|---------------|---------------|-------|--------|
| `config.py` | Load & validate config.yaml | `config.yaml` | `Config` object |
| `cv_parser.py` | Parse PDF/TXT CV | CV file path | Raw CV text |
| `scraper.py` | Scrape jobs via Apify | Search URLs | `list[Job]` |
| `filter.py` | Filter jobs (qualification + accepting status) | Jobs + CV text | `tuple[qualifying, rejected]` |
| `cv_personalizer.py` | Generate personalized CV PDF | Base CV + Job | PDF file path |
| `email_composer.py` | Compose application email | Job + CV data | Email body |
| `email_finder.py` | Discover hiring manager email | Company name | Email address |
| `gmail_draft.py` | Create Gmail draft | To, subject, body, attachment | Draft ID |

## 4. Data Flow & Communication

### 4.1 Synchronous Sequential Flow

All components execute in a hybrid manner:
- Steps 1-3: Sequential (each depends on previous output)
- Steps 4-6: Parallel per-job processing (no inter-job dependencies)

```
Config (YAML) → CV Parse → Scrape → Filter → For Each Job:
    → Personalize CV → Find Email → Compose Email → Create Gmail Draft
```

**Protocol:** Direct Python function calls (no HTTP/REST between modules)

**Rationale:** 
- Simple for 50 jobs/day (low volume)
- Parallel processing for per-job steps (reduces ~15min to ~3min)
- Easier debugging with sequential initial steps

### 4.2 Data Passing Format

| Transition | Data Format |
|------------|------------|
| Config → CV Parser | `Config` object |
| CV Parser → Scraper | `str` (CV text) |
| Scraper → Filter | `list[Job]` (Pydantic models) |
| Filter → Personalizer | `list[Job]`, `str` (CV text) |
| Personalizer → Email Finder | `Job` object |
| Email Finder → Email Composer | `str` (email), `Job` |
| Email Composer → Gmail Draft | `str` (letter), `Path` (CV PDF) |

## 5. Integration Architecture

### 5.1 External Services

| Service | Integration Method | Purpose |
|---------|------------------|---------|
| **Apify** | HTTP REST API | Job scraping |
| **AnyMailFinder** | HTTP REST API | Email discovery (with fallback) |
| **Gmail API** | OAuth2 + REST | Draft creation |
| **Ollama** | HTTP REST (OpenAI-compatible) | LLM for cognitive tasks |

### 5.2 Tools Using LLM

| Tool | Uses LLM | Why |
|------|---------|-----|
| **Filter** | Yes | Cognitive evaluation, structured decision output |
| **CV Personalizer** | Yes | Structured content generation → HTML template |
| **Email Composer** | No | Template-based, no LLM needed |
| **Email Finder** | No | API-based with web fallback |

| Component | NOT an LLM Agent | Why |
|-----------|----------------|-----|
| **Orchestrator** | Python only | Fixed pipeline, no "what to do next" decisions |

## 6. Local LLM (Ollama) Recommendation

### 6.1 Runtime

**[Ollama](https://ollama.com)** - runs locally, exposes OpenAI-compatible API

### 6.2 Default Model

`qwen2.5:7b`:
- Excellent at JSON formatting and instruction following
- ~8GB RAM/VRAM (runs on M1/M2/M3 Macs, RTX 3060+)
- Zero cost, zero API rate limits, 100% private

### 6.3 Alternative Models

| Model | VRAM | Best For |
|-------|------|---------|
| `llama3.2:3b` | ~4GB | Speed |
| `gemma2:9b` | ~12GB | Quality |
| `qwen2.5:7b` | ~8GB | Balanced |

### 6.4 Configuration

```yaml
llm:
  provider: "local"  # or "openai"
  model: "qwen2.5:7b"
  base_url: "http://localhost:11434/v1"
  api_key: "ollama"
```

### 6.5 Benefits

- Zero cost per run (vs ~$4.50 with OpenAI)
- No PII sent to external services
- No rate limits
- Parallel processing possible (reduces ~15min to ~3min)

## 7. High-Level Data Strategy

### 7.1 Source of Truth

| Data Type | Storage | Source |
|----------|---------|--------|
| Config | `config.yaml` | User-provided YAML |
| CV | File system | User-provided PDF/TXT |
| Job listings | `data/apify_results.json` | Apify API |
| Filtered jobs | `data/filtered_jobs.json` | LLM filter |
| Personalized CVs | `data/cvs/*.pdf` | Generated PDF |
| Email addresses | `data/emails.json` | AnyMailFinder |
| Gmail drafts | Gmail API | Created drafts |
| Run summary | `data/run_summary.json` | Orchestrator |
| Applied jobs | `data/processed_jobs.json` | AppliedTracker |

### 7.2 Data Consistency

- **No database:** Flat file storage only
- **Checkpoint caching:** Each step's output saved as checkpoint
- **Idempotency:** Runs can be re-executed (overwrites files)

### 7.3 Local Storage Structure

```
data/
├── cv_parsed.json              # Step 1 checkpoint
├── apify_results.json         # Step 2 checkpoint
├── filtered_jobs.json        # Step 3 checkpoint (qualifying)
├── filtered_out_jobs.json    # Step 3 checkpoint (rejected)
├── emails.json               # Step 4 output
├── processed_jobs.json       # Deduplication: job_id -> draft_id
├── cvs/
│   └── {job_id}/
│       ├── personalized_cv.pdf
│       ├── personalized_cv.html
│       ├── email.json
│       └── job_info.json
├── drafts/
│   └── {draft_id}.json
├── gmail_token.json          # OAuth token
└── run_summary.json        # Final summary
```

**Key Feature:** Each step's output is saved as a checkpoint. On subsequent runs:
- If checkpoint exists + not --force → Load from file (skip API call)
- This prevents wasting Apify/AnyMailFinder credits on re-scraping

## 8. Infrastructure & Deployment

### 8.1 Runtime Environment

| Component | Environment |
|-----------|--------------|
| Python | 3.11+ (local) |
| OS | macOS, Linux |
| Deployment | `python -m app run` |

### 8.2 Requirements

- **Python Packages:** See `pyproject.toml`
- **External:** Ollama (optional, for local LLM)

### 8.3 Future (Out of Scope for MVP)

| Component | Planned |
|-----------|---------|
| Scheduling | Cron-based or FastAPI scheduler |
| Cloud deployment | Not planned |
| Containerization | Docker (optional for portability) |

## 9. Cross-Cutting Concerns

### 9.1 Security

| Concern | Implementation |
|---------|----------------|
| API Keys | Environment variables only |
| CV Data | Local file storage only |
| Gmail OAuth | User authentication flow |
| No secrets in code | All via `config.yaml` + env vars |
| PII Handling | Config option `privacy.redact_pii: true` |

### 9.2 Observability

| Concern | Implementation |
|---------|----------------|
| Logging | Print statements + structured output |
| Progress | Console output during execution |
| Metrics | `run_summary.json` (jobs found, filtered, drafts created) |
| Errors | Logged to console + stored in `run_summary.json` |
| Debugging | All intermediate data stored locally |

### 9.3 Scalability

**Current limits (50 jobs/day):**
- Sequential processing: sufficient for MVP
- Apify rate limits: 1 request per URL
- AnyMailFinder: 50-100 lookups/month (free tier)
- Gmail API: No strict limits for drafts

**Scaling path (if needed):**
- Parallel job processing with `asyncio`
- Batch Apify requests
- FastAPI wrapper for concurrent runs

### 9.4 Error Handling

| Error Type | Handling |
|------------|----------|
| Config invalid | Raise error, exit |
| CV not found | Use mock CV |
| Apify failure | Log error, continue |
| AnyMailFinder rate limit | Use fallback or skip |
| Gmail failure | Log error, skip job |
| LLM failure | Log error, skip job |

## 10. CLI Interface

```bash
# Full pipeline
python -m app run

# Specific step (1-6)
python -m app run --step 3

# Force re-run, ignore cache
python -m app run --force

# Use cached jobs only
python -m app run --cached

# Dry run (no external APIs)
python -m app run --dry-run

# Include already applied jobs
python -m app run --include-applied

# Stop after filtering
python -m app run --filter-only

# Limit jobs
python -m app run --limit 10

# Custom config file
python -m app run --config my_config.yaml
```

## 11. End-to-End Flow

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

      [Email Composer]
      → compose_email(job, cv_data)
      → Template-based generation
      → Output: email body

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

## 12. Key Distinctions

| Component | Type | Implementation |
|-----------|------|-------------|
| **Orchestrator** | Python async pipeline | Fixed workflow, caching, step control |
| **Filter** | Two-stage (embedding + LLM) | nomic-embed-text + llama3.2 via httpx |
| **CV Personalizer** | Deterministic parse + LLM | Regex parsing + weasyprint PDF |
| **Email Finder** | API + web fallback | AnyMailFinder API + DuckDuckGo search |
| **Email Composer** | Template-based | f-string templates |
| **Gmail Draft** | Gmail API OAuth2 | google-api-python-client |

| Component | NOT | Why |
|-----------|-----|-----|
| **Orchestrator** | LLM agent | Fixed pipeline, no dynamic decisions |
| **Email Composer** | LLM | Template-based, deterministic |