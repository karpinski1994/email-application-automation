"""Job Filter — Two-stage CV-to-job matching.

Stage 1: Embedding-based pre-filtering (nomic-embed-text via Ollama)
         Computes cosine similarity between CV and each job,
         keeps top N jobs (default 20).

Stage 2: LLM detailed scoring (llama3.2 via Ollama)
         Batches all shortlisted jobs into one prompt,
         scores each job 0-100, keeps those >= threshold (default 70).

Reads raw Apify data from data/apify_results.json.
Outputs:
  data/filtered_jobs.json      — jobs that match the CV
  data/filtered_out_jobs.json  — jobs rejected with reasons.

Never modifies data/apify_results.json.
"""

import asyncio
import json
import time
import logging
from pathlib import Path
from typing import Optional

import httpx

from ..models import Job, Config, FilterConfig
from ..config import load_config

logger = logging.getLogger(__name__)

# ────────────────────────────────────────────────────────────────
# EMBEDDING SIMILARITY (Stage 1)
# ────────────────────────────────────────────────────────────────

def _cosine_similarity(a, b):
    """Compute cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _get_embedding(text: str, model: str = "nomic-embed-text") -> list[float]:
    """Get embedding vector from Ollama."""
    try:
        response = httpx.post(
            "http://localhost:11434/api/embeddings",
            json={"model": model, "prompt": text},
            timeout=30.0,
        )
        response.raise_for_status()
        return response.json()["embedding"]
    except Exception as e:
        logger.warning(f"Embedding request failed: {e}")
        return [0.0] * 768  # nomic-embed-text dimension


def _stage1_embedding_filter(
    jobs: list[dict],
    cv_text: str,
    config: FilterConfig,
    cv_embedding: Optional[list[float]] = None,
) -> list[tuple[int, dict, float]]:
    """Return top N jobs by embedding similarity to CV.
    
    Returns list of (index, job_dict, similarity_score).
    """
    if cv_embedding is None:
        logger.info("  → Computing CV embedding...")
        cv_embedding = _get_embedding(cv_text[:2000], config.embedding_model)
    
    logger.info(f"  → Computing job embeddings for {len(jobs)} jobs...")
    job_scores = []
    for i, item in enumerate(jobs):
        # Build job text: title + company + truncated description
        job_text = f"{item.get('title', '')} {item.get('companyName', '')} "
        desc = item.get("descriptionText") or item.get("descriptionHtml") or ""
        job_text += desc[:500]
        
        emb = _get_embedding(job_text, config.embedding_model)
        sim = _cosine_similarity(cv_embedding, emb)
        job_scores.append((i, item, sim))
    
    # Sort by similarity descending
    job_scores.sort(key=lambda x: -x[2])
    
    # Take top N
    top_n = job_scores[: config.embedding_shortlist_size]
    logger.info(f"  → Top {len(top_n)} jobs selected (similarity range: {top_n[-1][2]:.3f} - {top_n[0][2]:.3f})")
    return top_n


# ────────────────────────────────────────────────────────────────
# LLM SCORING (Stage 2)
# ────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a technical recruiter. Score job-CV fit from 0-100.

CV: Gabriel Menacho - Lead Full Stack Engineer, 12+ years experience.
Tech stack: React (8y), TypeScript (8y), Node.js, NestJS, GraphQL, Next.js.
Seniority: Lead/Senior level. Location: Bolivia (open to remote/LATAM).

IMPORTANT RULES:
1. You MUST score EVERY job listed in the user message
2. You MUST use the exact format: JOB_ID | SCORE | REASON
3. NO other text, NO explanations, NO summaries
4. Frontend/React/TypeScript roles = good fit (score 40-90)
5. Backend-only/Java/Django roles = low score (0-30)
6. Junior/Entry roles = score 0-20

SCORING:
- 80-100: Perfect (React+TS, senior/lead, remote/LATAM)
- 60-79: Strong (React+TS role, maybe some gaps)
- 40-59: Good (Frontend with React, seniority OK)
- 20-39: Weak (Frontend but different stack)
- 0-19: No match (backend-only, mobile, junior)

EXAMPLE OUTPUT:
job_1 | 85 | Strong React+TS match, senior level
job_2 | 25 | Frontend but no React mentioned
job_3 | 10 | Backend Java role, no fit

NOW SCORE ALL JOBS FROM THE USER MESSAGE:"""

def _build_batch_text(shortlist: list[tuple[int, dict, float]]) -> str:
    """Build the batch prompt text for all shortlisted jobs."""
    parts = []
    for idx, item, sim in shortlist:
        job_id = item.get("id", f"job_{idx+1}")
        title = item.get("title", "Unknown")
        company = item.get("companyName") or item.get("company") or "Unknown"
        location = item.get("location", "")
        remote = item.get("workRemoteAllowed", False)
        emp_type = item.get("employmentType", "")
        seniority = item.get("seniorityLevel", "")
        desc = item.get("descriptionText") or item.get("descriptionHtml") or ""
        
        parts.append(f"""
--- JOB ID: {job_id} ---
Title: {title}
Company: {company}
Location: {location}
Remote: {remote}
Type: {emp_type}
Seniority: {seniority}
Description (excerpt): {desc[:2000]}
""")
    return "\n".join(parts)


def _parse_llm_response(response_text: str, jobs: list[dict]) -> dict[str, tuple[int, str]]:
    """Parse LLM response to extract job_id -> (score, reason)."""
    results = {}
    job_ids = {item.get("id", f"job_{i+1}") for i, item in enumerate(jobs)}
    
    for line in response_text.strip().split("\n"):
        if "|" not in line:
            continue
        # Check if line contains a known job ID
        for jid in job_ids:
            if jid in line:
                parts = [p.strip() for p in line.split("|")]
                if len(parts) >= 3:
                    try:
                        score = int(parts[1].replace("SCORE:", "").strip())
                        reason = parts[2].replace("REASON:", "").strip()
                        results[jid] = (score, reason)
                    except (ValueError, IndexError):
                        pass
                break
    return results


async def _score_single_job(
    item: dict,
    cv_text: str,
    scoring_model: str = "llama3.2",
) -> tuple[int, str]:
    """Score a single job via LLM. Returns (score, reason)."""
    job_id = item.get("id", "unknown")
    title = item.get("title", "Unknown")
    company = item.get("companyName") or item.get("company") or "Unknown"
    location = item.get("location", "")
    remote = item.get("workRemoteAllowed", False)
    emp_type = item.get("employmentType", "")
    seniority = item.get("seniorityLevel", "")
    desc = item.get("descriptionText") or item.get("descriptionHtml") or ""
    
    user_prompt = f"""CV: Gabriel Menacho - Lead Full Stack Engineer, 12+ years.
Tech: React (8y), TypeScript (8y), Node.js, NestJS, GraphQL.
Location: Bolivia (remote/LATAM ok).

Score this ONE job 0-100:
JOB ID: {job_id}
Title: {title}
Company: {company}
Location: {location}
Remote: {remote}
Type: {emp_type}
Seniority: {seniority}
Description: {desc[:1000]}

Output ONLY: {job_id} | SCORE | REASON"""
    
    try:
        response = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: httpx.post(
                "http://localhost:11434/v1/chat/completions",
                headers={"Authorization": "Bearer ollama"},
                json={
                    "model": scoring_model,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": 0.1,
                    "max_tokens": 200,
                },
                timeout=30.0,
            )
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"].strip()
        
        # Parse: "job_1 | 85 | Strong React match"
        if "|" in content:
            parts = [p.strip() for p in content.split("|")]
            if len(parts) >= 3:
                try:
                    score = int(parts[1].replace("SCORE:", "").strip())
                    reason = parts[2].replace("REASON:", "").strip()
                    return score, reason
                except (ValueError, IndexError):
                    pass
        return 0, f"Parse error: {content[:100]}"
    except Exception as e:
        return 0, f"LLM error: {e}"


async def _stage2_llm_scoring(
    shortlist: list[tuple[int, dict, float]],
    cv_text: str,
    config: FilterConfig,
    scoring_model: str = "llama3.2",
) -> list[tuple[int, dict, int, str]]:
    """Score shortlisted jobs via LLM one-by-one.
    
    Returns list of (index, job_dict, score, reason).
    """
    logger.info(f"\nStage 2: LLM detailed scoring ({len(shortlist)} jobs, model: {scoring_model})...")
    t1 = time.time()
    
    results = []
    for idx, item, sim in shortlist:
        job_id = item.get("id", f"job_{idx+1}")
        title = item.get('title', '')
        logger.info(f"  Scoring {job_id}: {title[:40]}...")
        score, reason = await _score_single_job(item, cv_text, scoring_model)
        logger.info(f"    → Score: {score}/100 - {reason}")
        results.append((idx, item, score, reason))
    
    logger.info(f"  → {time.time()-t1:.1f}s total")
    return results


# ────────────────────────────────────────────────────────────────
# MAIN FILTER FUNCTION
# ────────────────────────────────────────────────────────────────

def _raw_to_job(
    item: dict,
    index: int,
    score: int = 0,
    reason: str = "",
    stage: str = "llm",
    llm_fit_threshold: int = 30,
) -> Job:
    """Convert raw Apify item to Job model."""
    requirements = []
    for key in ["skills", "experienceLevel", "employmentType", "jobFunction"]:
        if value := item.get(key):
            if isinstance(value, list):
                requirements.extend(value)
            else:
                requirements.append(str(value))
    
    return Job(
        id=item.get("id", f"job_{index+1}"),
        title=item.get("title", "Unknown"),
        company=item.get("companyName") or item.get("company") or "Unknown",
        description=item.get("descriptionText", item.get("descriptionHtml", ""))[:2000],
        url=item.get("link", item.get("url", "")),
        location=item.get("location", ""),
        requirements=requirements,
        posted_date=item.get("postedAt", ""),
        accepting_applications=True,
        rejection_reason=f"[{stage}] {reason}" if score < llm_fit_threshold else None,
        remote_allowed=item.get("workRemoteAllowed"),
        employment_type=item.get("employmentType"),
        seniority_level=item.get("seniorityLevel"),
        company_website=item.get("companyWebsite") or None,
    )


async def filter_jobs(
    jobs: list[Job],
    cv_text: str,
    llm_base_url: str = "http://localhost:11434/v1",
    llm_model: str = "qwen2.5:7b",
    llm_api_key: str = "ollama",
    llm_provider: str = "local",
    min_score: int = 5,
) -> tuple[list[Job], list[Job]]:
    """Filter jobs by comparing each against the CV using two-stage approach.
    
    Stage 1: Embedding similarity (nomic-embed-text) — top N jobs pass.
    Stage 2: LLM scoring (llama3.2) — batch scoring, threshold filter.
    
    Reads raw data from data/apify_results.json for richer context.
    Never modifies that file.
    
    Args:
        jobs: Job models (fallback, not used if raw file exists)
        cv_text: Candidate's parsed CV text
        llm_base_url: (unused, kept for compatibility)
        llm_model: (unused, kept for compatibility)
        llm_api_key: (unused, kept for compatibility)
        llm_provider: (unused, kept for compatibility)
        min_score: (unused, kept for compatibility)
    
    Returns:
        (qualifying_jobs, rejected_jobs)
    """
    raw_path = Path("data/apify_results.json")
    
    if not raw_path.exists():
        logger.error("data/apify_results.json not found — cannot filter")
        return [], list(jobs)
    
    raw_data = json.loads(raw_path.read_text())
    total = len(raw_data)
    
    config = load_config()
    filter_config = config.filter
    
    # ── Pre-filter: remove jobs without company website ────────────
    no_website = []
    website_filtered = []
    for item in raw_data:
        website = item.get("companyWebsite")
        if not website or website == "N/A":
            job = _raw_to_job(item, 0, 0, "No company website", "pre-filter", filter_config.llm_fit_threshold)
            job.rejection_reason = "No company website — cannot find email"
            no_website.append(job)
        else:
            website_filtered.append(item)
    
    if no_website:
        logger.info(f"🔍 Pre-filter: {len(no_website)} jobs rejected (no company website)")
    
    raw_data = website_filtered
    
    logger.info(f"🔍 Filtering {total} jobs using two-stage approach")
    logger.info(f"   Embedding model: {filter_config.embedding_model}")
    logger.info(f"   Scoring model: {filter_config.scoring_model}")
    logger.info(f"   Shortlist size: {filter_config.embedding_shortlist_size}")
    logger.info(f"   LLM threshold: {filter_config.llm_fit_threshold}")
    
    t0 = time.time()
    
    # ── Stage 1: Embedding pre-filtering ──────────────────────
    logger.info(f"\n📊 Stage 1: Embedding pre-filtering...")
    cv_embedding = _get_embedding(cv_text[:2000], filter_config.embedding_model)
    shortlist = _stage1_embedding_filter(
        raw_data, cv_text, filter_config, cv_embedding
    )
    logger.info(f"  → {time.time()-t0:.1f}s | Top similarity: {shortlist[0][2]:.3f} | Shortlist: {len(shortlist)} jobs")
    
    # ── Stage 2: LLM scoring on shortlist ────────────────────
    scored = await _stage2_llm_scoring(
        shortlist, cv_text, filter_config, filter_config.scoring_model
    )
    
    # ── Final filter: combine scores, apply threshold ────────────
    logger.info(f"\n{'='*60}")
    logger.info("FINAL RANKING (Embedding + LLM):")
    logger.info(f"{'='*60}")
    
    qualifying: list[Job] = []
    rejected: list[Job] = []
    
    # Summary: show all scores
    all_scores = [(item.get("id", f"job_{idx+1}"), score, reason) for idx, item, score, reason in scored]
    logger.info(f"All LLM scores: {[(id, s) for id, s, _ in all_scores]}")
    
    for idx, item, score, reason in sorted(scored, key=lambda x: -x[2]):
        job = _raw_to_job(item, idx, score, reason, "llm", filter_config.llm_fit_threshold)
        
        if score >= filter_config.llm_fit_threshold:
            logger.info(f"✅ [{score}/100] {job.title} @ {job.company}")
            logger.info(f"   {reason}")
            qualifying.append(job)
        else:
            job.rejection_reason = f"LLM score {score}/100: {reason}"
            logger.info(f"❌ [{score}/100] {job.title} @ {job.company}")
            logger.info(f"   {reason}")
            rejected.append(job)
    
    logger.info(f"\n{'='*60}")
    logger.info(f"FINAL: {len(qualifying)} qualified, {len(rejected) + len(no_website)} rejected ({len(no_website)} no website, {len(rejected)} low score)")
    logger.info(f"Total time: {time.time()-t0:.1f}s")
    
    rejected.extend(no_website)
    
    return qualifying, rejected
