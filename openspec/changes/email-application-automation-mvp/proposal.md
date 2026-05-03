## Why

Manual job applications are highly repetitive: searching listings, identifying roles, finding contacts, and writing tailored cover letters for each position. This doesn't scale—a job seeker spending 30 minutes per application targets 5-8 jobs/day. The solution is an AI-driven automation system using local LLM (Ollama) with Pydantic AI agents for cognitive tasks, creating personalized Gmail drafts at scale with zero cost and complete privacy.

## What Changes

- Replace manual job application workflow with automated pipeline
- Use local LLM (Ollama + Qwen 2.5:7b) instead of cloud APIs
- Implement deterministic Python orchestrator + Pydantic AI agentic tools
- Add job filtering (qualification + accepting status) using structured LLM output
- Add CV personalization with HTML + weasyprint PDF generation
- Add multi-tool email discovery (API → parse description → guess pattern)
- Add deduplication to avoid duplicate drafts
- Add parallel processing with asyncio (max 5 concurrent jobs)
- Add progress reporting with rich.progress

## Capabilities

### New Capabilities
- `job-scraping`: Scrape job listings from configured URLs via Apify API
- `job-filtering`: Filter jobs by qualification match + accepting status using Pydantic AI structured output
- `cv-personalization`: Generate personalized CV PDFs using Pydantic AI + HTML template + weasyprint
- `email-discovery`: Find hiring manager emails with multi-tool fallback reasoning
- `cover-letter-generation`: Generate professional cover letters using Pydantic AI system prompts
- `gmail-draft-creation`: Create Gmail drafts with PDF attachments
- `parallel-processing`: Process multiple jobs concurrently with semaphore
- `job-deduplication`: Track processed jobs to avoid duplicates

### Modified Capabilities
- (None - this is a greenfield MVP project)

## Impact

- New dependencies: pydantic-ai, ollama, weasyprint, jinja2, httpx, tenacity, rich, google-auth-oauthlib, google-api-python-client
- New modules: config.py, models.py, cv_parser.py, scraper.py, filter.py, cv_personalizer.py, email_finder.py, cover_letter.py, gmail_draft.py, agent.py, utils.py
- New data paths: data/processed_jobs.json for deduplication
- New config: config.yaml with llm, privacy, dry_run settings