## Context

**Background:** Manual job application workflow is repetitive and unscalable (5-8 jobs/day). We're building an AI-driven automation system using local LLM (Ollama) to create personalized Gmail drafts at scale.

**Current State:** Greenfield MVP - no existing code.

**Constraints:**
- Zero cost: Local LLM (Ollama) instead of OpenAI API
- Privacy: CV data stays local, no PII sent to external services
- No API keys: Uses local Ollama endpoint
- Must avoid LLM hallucination: Pipeline steps must not be skipped

**Stakeholders:** Solo job seeker who wants to automate 50 applications/day

## Goals / Non-Goals

**Goals:**
- Automate full pipeline: scrape → filter → personalize → email → draft → 50 jobs/day
- Zero cost per run (Ollama is free)
- 100% privacy (local processing only)
- Parallel processing to reduce ~15min to ~3min for 50 jobs
- Deduplication to avoid duplicate drafts
- Progress reporting during execution

**Non-Goals:**
- Not sending emails (drafts only)
- Not LinkedIn outreach
- Not job interview tracking/ATS
- Not cloud deployment (local only for MVP)

## Decisions

### 1. Deterministic Orchestrator + Agentic Tools

**Decision:** Main orchestrator is Python async pipeline, NOT an LLM agent.

**Rationale:** 
- Workflow is rigidly linear (scrape → filter → personalize → email → draft)
- No dynamic branching needed - always the same steps
- Avoids cost/latency of LLM "what to do next" decisions
- Avoids hallucination: LLM might skip cv_personalizer step
- Infinite loop risk with poor prompting

**Alternative Considered:** Pure LLM agent orchestrator (rejected - see rationale)

### 2. Pydantic AI for Tools

**Decision:** Use Pydantic AI agents for cognitive tasks (filter, CV personalizer, email finder, cover letter).

**Rationale:**
- `result_type` enforces structured output - no manual JSON parsing
- Multi-tool email finder can reason: API → parse description → guess pattern
- System prompts enforce professional tone for cover letters

### 3. Local LLM: Ollama + Qwen 2.5:7b

**Decision:** Use Ollama runtime with Qwen 2.5:7b model.

**Rationale:**
- Zero cost per run (vs ~$4.50 with OpenAI)
- No PII sent to external services
- No API rate limits
- Excellent at JSON formatting and instruction following
- ~8GB VRAM (runs on M1/M2/M3 Mac, RTX 3060+)

**Alternative Considered:** 
- llama3.2:3b (faster, less capable)
- gemma2:9b (better quality, more VRAM)
- OpenAI (expensive, privacy concerns)

### 4. HTML + Weasyprint for CV PDFs

**Decision:** LLM generates structured JSON → Jinja2 HTML template → weasyprint PDF.

**Rationale:**
- Full control over CV layout
- LLM generates content, not formatting
- Professional output

**Alternative Considered:** 
- reportlab (more complex)
- python-docx → PDF (requires LibreOffice)
- fpdf2 (limited styling)

### 5. Parallel Processing with Semaphore

**Decision:** asyncio.Semaphore(5) limits concurrent jobs to 5.

**Rationale:**
- Avoids overwhelming local LLM
- Progress bar for UX
- Reduces 50-job pipeline from ~15min to ~3min

### 6. Job Deduplication via processed_jobs.json

**Decision:** Track job_id → draft_id mappings to skip already-processed jobs.

**Rationale:**
- Running twice creates duplicate Gmail drafts
- Simple JSON file, no database needed

## Risks / Trade-offs

- **Ollama not running** → User must run `ollama serve` before pipeline
  - **Mitigation:** Add startup check with instructions

- **Local LLM slower than cloud** → ~3min for 50 jobs vs ~1min
  - **Mitigation:** Parallel processing + progress bar

- **No email found** → Job skipped
  - **Mitigation:** Multi-tool fallback (parse description → guess pattern)

- **CV PDF generation fails** → Job fails
  - **Mitigation:** Try/except in process_job, continue to next

- **Gmail OAuth expires** → Token refresh or re-auth
  - **Mitigation:** Token refresh logic in get_gmail_credentials()

## Migration Plan

1. Create src/app directory structure
2. Implement each module (config, models, cv_parser, scraper, filter, cv_personalizer, email_finder, cover_letter, gmail_draft, agent, utils)
3. Create config.yaml with llm.privacy.dry_run settings
4. Install dependencies: pip install -r requirements.txt
5. Test with dry_run mode first
6. Run ollama serve + ollama pull qwen2.5:7b
7. Run full pipeline

## Open Questions

- Should we add free email fallback (DuckDuckGo + MX verification)?
- Schedule for cron-based automation?
- FastAPI wrapper for concurrent runs?