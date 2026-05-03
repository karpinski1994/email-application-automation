# Business Case & Project Charter – AI Automated Email Job Application System

## Part 1: Business Case (The Why)

### Executive Summary
This project automates the top-of-funnel job application process by replacing a manual, repetitive workflow with an AI-driven system. Using a deterministic Python orchestrator with Pydantic AI agentic tools for cognitive tasks, the system reads a candidate's CV, scrapes job listings, discovers hiring manager contacts, and drafts personalized Gmail cover letters—enabling the user to scale from ~5 manual applications/day to 50 automated applications/day at zero cost.

### Problem Statement
Applying to jobs manually is highly repetitive: searching listings, identifying relevant roles, finding decision-maker contacts, and writing tailored cover letters for each position. This process doesn't scale—a job seeker spending 30 minutes per application can realistically target 5-8 jobs/day. The bottleneck isn't effort; it's time. The current n8n workflow exists but is brittle (hardcoded config, no type safety, hard to extend).

### Strategic Alignment
- **Goal:** Enable solo job seekers to compete with applicants who outspend them on中介 services
- **Philosophy:** Own your automation stack; avoid vendor lock-in from job board premium features or recruitment agencies
- **Maintainability:** Python codebase > no-code n8n; type-safe, observable, extensible

### Cost-Benefit Analysis

| Category | Details |
|----------|---------|
| **Direct Costs** | $0 (free tier APIs only; user has existing Gmail, AnyMailFinder, Apify accounts) |
| **Opportunity Cost Savings** | 50 jobs/day × 30 min/job = 25 hours/week recovered. Assume user's time valued at $0 (student/bootstrapping) — otherwise ~$200-500/week at $10-20/hr |
| **Intangible Benefits** | Faster response to new listings; consistent, personalized outreach; no "spray and pray"; reduced decision fatigue |
| **LLM Token Cost** | ~$0.50-2/day depending on job volume (GPT-4o per job listing processed). Budget is $0 but token spend is accepted as necessary operating cost |

---

## Part 2: Project Charter (The What & How)

### Project Purpose & Objectives (SMART)

| Objective | Specific | Measurable | Achievable | Relevant | Time-Bound |
|-----------|-----------|-------------|------------|----------|------------|
| Output | Automate CV-to-draft pipeline | 50 Gmail drafts/day | Yes, with AI | Yes, core goal | End of Q2 2026 |
| Reliability | System runs without manual intervention | 90% success rate on runs | Yes | Yes | End of Q2 2026 |
| Extensibility | Add dry-run mode, scheduling, FastAPI wrapper | All features working | Yes | Yes | Q3 2026 |
| Cost | Zero direct spend | $0/month (free tier) | Yes if enforced | Yes | Ongoing |

### Scope & Boundaries

**In Scope:**
- CV parsing (PDF/TXT)
- Job listing scraping (Apify actor)
- Job filtering (qualification mismatch, no longer accepting applications)
- CV personalization per job (tailor to job requirements)
- Hiring manager email discovery (AnyMailFinder API)
- Gmail draft creation (Google Gmail API)
- Config-driven (YAML) - no hardcoded values
- Deterministic Python async orchestrator with Pydantic AI agentic tools
- Logging after each step
- Local storage for all intermediate data (debugging & reprocessing)

**Future (Out of Scope for MVP):**
- Free fallback email discovery (DuckDuckGo + pattern guessing)

**Out of Scope:**
- Actually sending emails (drafts only; user reviews before send)
- Job interview tracking / ATS integration
- LinkedIn outreach
- Paid job board access
- Schedule/cron automation (Phase 2, not MVP)

### Key Stakeholders

| Role | Name | Responsibility |
|------|-----|----------------|
| Sponsor | User (solo developer) | Approves budget, sets priorities |
| End User | Same user | Runs system, reviews drafts |
| Technical Lead | User (solo developer) | Builds, maintains, extends |
| External Dependency | Google (Gmail/Docs API) | Provides email/draft infrastructure |
| External Dependency | Apify | Provides job scraping actor |
| External Dependency | AnyMailFinder | Provides email discovery API |

### Milestone Schedule

| Phase | Milestone | Target |
|-------|----------|--------|
| 1 | MVP: End-to-end pipeline runs | 4 weeks |
| 2 | Observability: Logging, error handling | Week 5 |
| 3 | Extensibility: Dry-run, config management | Week 6-8 |
| 4 | Production readiness: FastAPI wrapper, scheduling | Q3 2026 |

### Budget Estimate

| Item | Cost |
|------|------|
| Total Budget | **$0** |
| API Calls (AnyMailFinder) | $0 (free tier cap: 50-100 lookups/month) |
| Apify | $0 (free tier) |
| Gmail API | $0 (OAuth2 free tier) |
| LLM Tokens | ~$10-50/month (user absorbs; not part of $0 budget) |

### Initial Risk Log

| ID | Risk | Likelihood | Impact | Mitigation |
|----|------|------------|--------|-------------|
| R1 | AnyMailFinder rate limit hit (free tier) | High | High | Implement per-run limits; fail gracefully; support free fallback (DuckDuckGo + email pattern guessing) |
| R2 | Hardcoded config causes run failure | High | High | Move all config to `config.yaml`; validate on startup |
| R3 | Google OAuth2 token expiry | Medium | High | Implement token refresh; add expiry warning |
| R4 | API changes break scraper (Apify actor) | Medium | Medium | Pin actor version; monitor logs |
| R5 | LLM cost exceeds budget | Low | Medium | Add per-run token budget cap; abort if threshold hit |
| R6 | Disk space runs out | Low | Low | Clean old runs periodically; limit stored data |

### Success Criteria (Measurable)

| Criterion | Target |
|-----------|--------|
| Gmail drafts created/day | ≥50 |
| Cost to run (direct APIs) | $0/month |
| System failure rate | <10% |
| Time to first draft | <10 min (after config) |