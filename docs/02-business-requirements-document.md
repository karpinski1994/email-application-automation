# Business Requirements Document – AI Automated Email Job Application System

## Project Overview (context & vision)

A Python-based automation system that replaces a brittle n8n workflow with a type-safe, extensible codebase. The system orchestrates CV parsing, job scraping, email discovery, and Gmail draft creation—all via a deterministic Python async pipeline with LLM-powered tools. Vision: enable solo job seekers to apply to 50 jobs/day without manual effort.

## Business Objectives

| Objective | Metric | Target |
|-----------|--------|--------|
| Scale application volume | Gmail drafts created/day | ≥50 |
| Maintain zero-cost operation | Direct API spend/month | $0 |
| Ensure reliability | Successful run rate | ≥90% |
| Reduce setup friction | Time from config to first run | <30 min |

## Target Audience / User Personas

| Persona | Role | Needs |
|---------|------|-------|
| Primary User | Solo job seeker | Apply to many jobs efficiently without manual effort |
| Technical User | Solo developer (same person) | Maintainable, extensible codebase with type safety |

## Business Process Mapping

### As-Is (Current)
1. Manually search job boards Indeed, LinkedIn, etc.
2. Open each listing, read requirements
3. Search for hiring manager email (manual Google search or AnyMailFinder)
4. Write cover letter from scratch
5. Compose Gmail draft
6. Repeat 5-8 times/day

### To-Be (Target)
1. Configure `config.yaml` with search URLs, CV path, Gmail settings
2. Run `python -m app run`
3. System reads CV from configured path
4. System scrapes jobs via configured URLs (Apify actor)
5. System filters jobs candidate doesn't fit (qualification mismatch, no longer accepting applications)
6. System creates personalized CV for each remaining job (tailor to job requirements, not complete rewrite)
7. System finds emails via AnyMailFinder (or free fallback)
8. System composes application email
9. Gmail draft created with personalized CV attached
10. Repeat up to 50x/day automatically

## High-Level Functional Needs

| ID | Capability | Priority |
|----|-----------|----------|
| F1 | CV parsing (PDF/TXT) | Must have |
| F2 | Job listing scraping via Apify | Must have |
| F3 | Job filtering (qualification mismatch, no longer accepting applications) | Must have |
| F4 | CV personalization per job (tailor to job requirements) | Must have |
| F5 | Email discovery via AnyMailFinder | Must have |
| F6 | AI-generated personalized cover letter | Must have |
| F7 | Gmail draft creation via API | Must have |
| F8 | Config management (YAML) | Must have |
| F9 | API key validation on startup | Must have |
| F10 | Logging after each step | Should have |
| F11 | Local storage for all intermediate data | Should have |
| F12 | Scheduling/cron support | Could have |
| F13 | FastAPI REST wrapper | Could have |
| F14 | Free fallback email discovery (DuckDuckGo + pattern guessing) | Future (May have) |

## Financial / Operational Constraints

| Constraint | Details |
|------------|---------|
| Budget | $0 (free tier APIs only) |
| Timeline | MVP in 4 weeks |
| Technical debt | Replace n8n JSON; no hardcoded values |
| Token budget | ~$10-50/month acceptable to user |

## Glossary

| Term | Definition |
|------|------------|
| CV | Curriculum Vitae / resume document |
| AnyMailFinder | Paid email discovery API service |
| Free Fallback | Email discovery via DuckDuckGo + pattern guessing + MX verify (future) |
| n8n | No-code workflow automation tool |
| LLM | Large Language Model (Ollama/OpenAI) for cognitive tasks |
| Top-of-funnel | Early stage of job application (outreach) |

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