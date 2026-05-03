"""Job Filter — LLM-powered CV-to-job matching.

Reads raw Apify data from data/apify_results.json.
Compares each job against the candidate's parsed CV using a local LLM.

Outputs:
  data/filtered_jobs.json      — jobs that match the CV
  data/filtered_out_jobs.json  — jobs rejected with reasons

Never modifies data/apify_results.json.
"""

import json
import asyncio
import logging
from pathlib import Path
from typing import Optional

import httpx

from ..models import Job

logger = logging.getLogger(__name__)

# ────────────────────────────────────────────────────────────────
# RULE-BASED PRE-FILTERING (Instant, no LLM)
# Eliminates 70-80% of jobs before calling LLM
# ────────────────────────────────────────────────────────────────

def _rule_based_filter(item: dict) -> tuple[bool, str]:
    """Return (reject, reason) based on deterministic rules only.
    
    Returns:
        (True, reason) if job should be rejected by rules
        (False, "") if job should be evaluated by LLM
    """
    title = item.get("title", "").lower()
    desc = (item.get("descriptionText") or item.get("descriptionHtml") or "").lower()
    company = item.get("companyName", item.get("company", "")).lower()
    
    # Rule 1: Seniority filter (Critical)
    if any(kw in title for kw in ["junior", "jr.", "entry", "intern", "associate", "júnior"]):
        return True, "Junior/Entry level (rule-based)"
    
    if "internship" in item.get("employmentType", "").lower():
        return True, "Internship (rule-based)"
    
    # Rule 2: Location/Citizenship filter (Critical)
    full_text = f"{title} {desc} {company}"
    if any(kw in full_text for kw in ["us citizenship", "must be us citizen", "clearance required"]):
        return True, "US citizenship/clearance required (rule-based)"
    
    # Rule 3: Domain filter (Important)
    if any(kw in title for kw in ["android", "ios", "mobile", "kotlin", "swift"]):
        if "react" not in desc:
            return True, "Mobile role without React (rule-based)"
    
    # Rule 4: Tech stack filter (Important)
    if "angular" in title and "react" not in desc:
        return True, "Strictly Angular without React (rule-based)"
    if "vue" in title and "react" not in desc:
        return True, "Strictly Vue without React (rule-based)"
    
    # Rule 5: CMS filter
    if any(kw in title for kw in ["optimizely", "wordpress", "drupal"]):
        return True, "CMS-specialized role (rule-based)"
    
    # Pass to LLM for nuanced evaluation
    return False, ""


# ────────────────────────────────────────────────────────────────
# LLM CONFIG
# ────────────────────────────────────────────────────────────────

# Max concurrent LLM calls
# Ollama is single-threaded, keep low
# OpenAI can handle 5-10 concurrent
MAX_CONCURRENCY_OLLAMA = 2
MAX_CONCURRENCY_OPENAI = 5

# How many chars of job description to send to the LLM
MAX_DESCRIPTION_CHARS = 1500

# ────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are an expert technical recruiter.

Evaluate if Gabriel Menacho (Lead Full Stack Engineer, 12+ years, React/TypeScript/Node.js) is a good fit for this job.

IMPORTANT RULES:

1. REJECT if job title/description says: "Junior", "Jr.", "Entry Level", "Intern", "Associate"
2. REJECT if location requires: "US Citizenship", "US Citizen", "Clearance"
3. REJECT if strictly mobile role: "Android", "iOS", "Kotlin", "Swift" (not web)
4. REJECT if strictly Angular/Vue with NO mention of React/TypeScript

5. ACCEPT "Frontend Engineer" or "Frontend Developer" title - this does NOT mean junior!
6. ACCEPT if reputable companies (OpenAI, IBM, etc.) have "Frontend Engineer" title
7. ACCEPT if stack includes: React, TypeScript, Next.js, Node.js, GraphQL
8. ACCEPT remote jobs or LATAM locations (candidate is in Bolivia)

Score 1-10:
- 1-3: Poor fit (junior, wrong domain, US-only clearance)
- 4-5: Weak fit (borderline, might be junior, location issue)
- 6-7: Good fit (React stack, senior level implied, remote/LATAM)
- 8-10: Strong fit (explicit Senior/Lead, React/TS, remote)

RESPOND ONLY WITH JSON (no markdown, no extra text):
{"fit": true/false, "score": 1-10, "reason": "brief explanation"}
"""


def _build_job_summary(item: dict) -> str:
    """Build a concise job summary from raw Apify fields."""
    parts = []
    
    title = item.get("title", "Unknown")
    company = item.get("companyName", item.get("company", "Unknown"))
    parts.append(f"Title: {title}")
    parts.append(f"Company: {company}")
    
    if loc := item.get("location"):
        parts.append(f"Location: {loc}")
    
    if seniority := item.get("seniorityLevel"):
        parts.append(f"Seniority: {seniority}")
    
    if std_title := item.get("standardizedTitle"):
        parts.append(f"Standardized Title: {std_title}")
    
    if emp_type := item.get("employmentType"):
        parts.append(f"Employment Type: {emp_type}")
    
    if remote := item.get("workRemoteAllowed"):
        parts.append(f"Remote: {'Yes' if remote else 'No'}")
    
    if job_func := item.get("jobFunction"):
        parts.append(f"Function: {job_func}")
    
    if salary := item.get("salary") or item.get("salaryInsights"):
        parts.append(f"Salary: {salary}")
    
    # Check for deal-breaker keywords
    title_lower = title.lower()
    if any(kw in title_lower for kw in ["junior", "júnior", "jr.", "entry", "intern"]):
        parts.append("⚠️ JUNIOR/ENTRY LEVEL DETECTED")
    
    if any(kw in title_lower for kw in ["android", "ios", "mobile", "kotlin", "swift"]):
        parts.append("⚠️ MOBILE ROLE DETECTED")
    
    # Use descriptionText (cleaner than HTML), truncated
    desc = item.get("descriptionText", "") or item.get("descriptionHtml", "")
    if desc:
        desc = desc[:MAX_DESCRIPTION_CHARS]
        parts.append(f"\nJob Description:\n{desc}")
    
    return "\n".join(parts)


async def _evaluate_job(
    client: httpx.AsyncClient,
    item: dict,
    cv_text: str,
    base_url: str,
    model: str,
    api_key: str,
    index: int,
    total: int,
) -> tuple[dict, bool, int, str]:
    """Evaluate a single job against the CV using the LLM.
    
    Returns: (raw_item, fit, score, reason)
    """
    job_summary = _build_job_summary(item)
    title = item.get("title", "Unknown")
    company = item.get("companyName", item.get("company", "Unknown"))
    
    user_prompt = f"""Evaluate this job:

=== CANDIDATE CV (first 1000 chars) ===
{cv_text[:1000]}

=== JOB LISTING ===
{job_summary}

Respond ONLY with JSON: {{"fit": true/false, "score": 1-10, "reason": "..."}}
"""

    try:
        response = await client.post(
            f"{base_url}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.1,
                "max_tokens": 200,
            },
            timeout=60.0,
        )
        response.raise_for_status()
        
        content = response.json()["choices"][0]["message"]["content"].strip()
        
        # Parse JSON from response (handle markdown code blocks)
        if "```" in content:
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
            content = content.strip()
        
        result = json.loads(content)
        fit = result.get("fit", False)
        score = result.get("score", 0)
        reason = result.get("reason", "No reason given")
        
        status = "✅" if fit else "❌"
        logger.info(f"  [{index+1}/{total}] {status} {title} @ {company} — score:{score}/10 — {reason}")
        
        return item, fit, score, reason
        
    except (json.JSONDecodeError, KeyError) as e:
        logger.warning(f"  [{index+1}/{total}] ⚠️  Parse error for {title} @ {company}: {e}")
        # On parse error, reject the job (safer)
        return item, False, 0, f"LLM parse error: {e}"
    except httpx.HTTPError as e:
        logger.warning(f"  [{index+1}/{total}] ⚠️  HTTP error for {title} @ {company}: {e}")
        return item, False, 0, f"LLM HTTP error: {e}"


def _raw_to_job(item: dict, index: int, score: int = 0, reason: str = "") -> Job:
    """Convert raw Apify item to Job model."""
    requirements = []
    for key in ["employmentType", "jobFunction", "seniorityLevel"]:
        if value := item.get(key):
            requirements.append(str(value))
    
    return Job(
        id=item.get("id", f"job_{index+1}"),
        title=item.get("title", "Unknown"),
        company=item.get("companyName", item.get("company", "Unknown")),
        description=item.get("descriptionText", item.get("descriptionHtml", ""))[:2000],
        url=item.get("link", item.get("url", "")),
        location=item.get("location", ""),
        requirements=requirements,
        posted_date=item.get("postedAt", ""),
        accepting_applications=True,
        rejection_reason=reason if not reason.startswith("✅") else None,
    )


async def filter_jobs(
    jobs: list[Job],
    cv_text: str,
    llm_base_url: str = "http://localhost:11434/v1",
    llm_model: str = "qwen2.5:7b",
    llm_api_key: str = "ollama",
    llm_provider: str = "local",  # "local" or "openai"
    min_score: int = 5,
) -> tuple[list[Job], list[Job]]:
    """Filter jobs by comparing each against the CV using LLM.
    
    Reads raw data from data/apify_results.json for richer context.
    Never modifies that file.
    
    Uses rule-based pre-filtering to eliminate 70-80% of jobs instantly,
    then sends only borderline cases to LLM for nuanced evaluation.
    
    Args:
        jobs: Job models (fallback, not used if raw file exists)
        cv_text: Candidate's parsed CV text
        llm_base_url: LLM API base URL
        llm_model: Model name
        llm_api_key: API key
        llm_provider: "local" (Ollama) or "openai"
        min_score: Minimum score (1-10) to qualify
    
    Returns:
        (qualifying_jobs, rejected_jobs)
    """
    raw_path = Path("data/apify_results.json")
    
    if not raw_path.exists():
        logger.error("data/apify_results.json not found — cannot filter")
        return [], list(jobs)
    
    raw_data = json.loads(raw_path.read_text())
    total = len(raw_data)
    
    logger.info(f"🔍 Filtering {total} jobs against CV using {llm_model}")
    logger.info(f"   Min score to qualify: {min_score}/10")
    
    # Set concurrency based on provider
    if llm_provider == "openai":
        max_concurrency = MAX_CONCURRENCY_OPENAI
    else:
        max_concurrency = MAX_CONCURRENCY_OLLAMA
    logger.info(f"   Concurrency: {max_concurrency} (provider: {llm_provider})")
    
    qualifying: list[Job] = []
    rejected: list[Job] = []
    
    # Phase 1: Rule-based pre-filtering (instant, eliminates 70-80%)
    logger.info(f"\n⚡ Phase 1: Rule-based pre-filtering...")
    rule_rejected = 0
    llm_candidates = []
    
    for i, item in enumerate(raw_data):
        reject, reason = _rule_based_filter(item)
        if reject:
            job = _raw_to_job(item, i, 0, reason)
            rejected.append(job)
            rule_rejected += 1
        else:
            llm_candidates.append((i, item))
    
    logger.info(f"   Rule-based: {rule_rejected} rejected, {len(llm_candidates)} passed to LLM")
    
    # Phase 2: LLM evaluation for borderline cases only
    if llm_candidates:
        logger.info(f"\n🤖 Phase 2: LLM evaluation for {len(llm_candidates)} jobs...")
        semaphore = asyncio.Semaphore(max_concurrency)
        
        async def evaluate_with_semaphore(item_data: tuple[int, dict]):
            idx, item = item_data
            async with semaphore:
                return await _evaluate_job(
                    client, item, cv_text, llm_base_url, llm_model, llm_api_key, idx, total
                )
        
        async with httpx.AsyncClient() as client:
            tasks = [evaluate_with_semaphore(data) for data in llm_candidates]
            results = await asyncio.gather(*tasks)
        
        for (i, item), (raw_item, fit, score, reason) in zip(llm_candidates, results):
            job = _raw_to_job(item, i, score, reason)
            
            if fit and score >= min_score:
                qualifying.append(job)
            else:
                job.rejection_reason = f"Score {score}/10: {reason}"
                rejected.append(job)
    
    logger.info(f"\n📊 Final Results: {len(qualifying)} qualified, {len(rejected)} rejected")
    
    return qualifying, rejected
