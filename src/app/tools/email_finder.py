"""Email Finder - Finds hiring manager emails via AnyMailFinder API with web fallback."""

import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Optional

import httpx

from ..models import EmailFinderConfig, Job
from . import web_email_finder

logger = logging.getLogger(__name__)

ANYMAILFINDER_URL = "https://api.anymailfinder.com/v5.1/find-email/decision-maker"


def _extract_domain_from_url(url: str) -> str:
    """Extract domain from a URL like 'https://www.govcio.com' -> 'govcio.com'."""
    domain = url.strip()
    for prefix in ("https://", "http://", "www."):
        domain = domain.replace(prefix, "")
    domain = domain.rstrip("/")
    return domain


def _company_to_domains(company: str) -> list[str]:
    """Generate candidate domains from a company name.

    Strips common suffixes, lowercases, removes spaces/special chars,
    then tries .com, .io, .co in order.
    """
    suffixes = ["Inc.", "LLC", "LTD", "Ltd.", "Corp.", "Co.", "Inc", "PBC"]
    cleaned = company
    for s in suffixes:
        cleaned = cleaned.replace(s, "")
    cleaned = re.sub(r'[^a-zA-Z0-9]', '', cleaned).lower()
    if not cleaned:
        return []
    return [f"{cleaned}.com", f"{cleaned}.io", f"{cleaned}.co"]


def _get_domains_for_job(job: Job) -> list[str]:
    """Get candidate domains for a job, preferring company_website over guessing."""
    if job.company_website:
        domain = _extract_domain_from_url(job.company_website)
        if domain and "." in domain:
            return [domain]
    return _company_to_domains(job.company)


async def find_email_for_job(
    job: Job,
    api_key: str,
    categories: list[str],
    max_attempts: int = 3,
) -> dict:
    """Find a hiring manager email for a job via AnyMailFinder.

    Uses job.company_website for domain if available, otherwise guesses from company name.

    Returns:
        {"email": str, "status": "valid"|"risky"|"not_found"|"error"|"credit_exhausted", "domain_used": str, "credit_exhausted": bool}
    """
    domains = _get_domains_for_job(job)
    if not domains:
        return {"email": "", "status": "not_found", "domain_used": "", "credit_exhausted": False}

    credit_exhausted = False

    for domain in domains[:max_attempts]:
        try:
            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda d=domain: httpx.post(
                    ANYMAILFINDER_URL,
                    headers={
                        "Authorization": api_key,
                        "Content-Type": "application/json",
                    },
                    json={
                        "domain": d,
                        "decision_maker_category": categories,
                    },
                    timeout=30.0,
                )
            )

            if response.status_code == 429:
                print(f"    {domain}: rate limited, waiting 5s...")
                await asyncio.sleep(5)
                continue

            if response.status_code == 402:
                body = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
                msg = body.get("message", "payment required or no data")
                print(f"    {domain}: 402 — {msg}")
                credit_exhausted = True
                await asyncio.sleep(2)
                continue

            response.raise_for_status()
            data = response.json()
            email = data.get("email", "")
            email_status = data.get("email_status", "not_found")

            print(f"    {domain}: {email_status} — {email or 'no email'}")

            if email_status in ("valid", "risky") and email:
                return {"email": email, "status": email_status, "domain_used": domain, "credit_exhausted": False}

        except httpx.HTTPStatusError as e:
            print(f"    {domain}: HTTP {e.response.status_code}")
        except Exception as e:
            print(f"    {domain}: error — {e}")

        await asyncio.sleep(2)

    return {"email": "", "status": "not_found", "domain_used": domains[0], "credit_exhausted": credit_exhausted}


async def find_emails_for_jobs(
    jobs: list[Job],
    config: EmailFinderConfig,
    force: bool = False,
) -> dict:
    """Find emails for all filtered jobs.

    Caches results in data/emails.json. Skips jobs already found with "valid" status
    unless force=True.

    Returns:
        Dict mapping job_id -> {"email", "status", "company", "domain_used", "category"}
    """
    emails_path = Path("data/emails.json")
    results = {}

    if emails_path.exists() and not force:
        results = json.loads(emails_path.read_text())

    api_key = config.api_key
    if not api_key or api_key.startswith("${"):
        print("  ❌ ANYMAILFINDER_API_KEY not set — skipping email finding")
        if config.fallback_enabled:
            print("  → Attempting web search fallback...")
            for job in jobs:
                if job.id not in results or results[job.id].get("status") != "valid":
                    domain = _extract_domain_from_url(job.company_website) if job.company_website else None
                    if not domain:
                        domains = _company_to_domains(job.company)
                        domain = domains[0] if domains else None
                    if domain:
                        web_result = await web_email_finder.find_email_via_web(
                            job.company, domain, max_attempts=config.fallback_max_attempts
                        )
                        emails = web_result.get("emails", [])
                        if emails:
                            best = emails[0]
                            results[job.id] = {
                                "email": best["email"],
                                "status": "fallback_verified" if best["type"] == "verified" else "fallback_inferred",
                                "company": job.company,
                                "domain_used": domain,
                                "category": f"web_fallback ({best['confidence']})",
                            }
                            print(f"  → {job.company}: {best['confidence']} ({best['type']}) — {best['email']}")
                        else:
                            results[job.id] = {
                                "email": "",
                                "status": "not_found",
                                "company": job.company,
                                "domain_used": domain,
                                "category": "",
                            }
        else:
            for job in jobs:
                if job.id not in results:
                    results[job.id] = {
                        "email": "",
                        "status": "error",
                        "company": job.company,
                        "domain_used": "",
                        "category": "",
                    }
        return results

    global_credit_exhausted = False

    for job in jobs:
        if job.id in results and results[job.id].get("status") == "valid" and not force:
            print(f"  Skipping {job.company} — email already cached")
            continue

        domains = _get_domains_for_job(job)
        print(f"  {job.company}: trying domains {domains}")
        result = await find_email_for_job(
            job, api_key, config.categories, config.max_domain_attempts
        )

        if result.get("credit_exhausted"):
            global_credit_exhausted = True

        if result["status"] == "not_found" and result.get("credit_exhausted") and config.fallback_enabled:
            print(f"  → {job.company}: credit exhausted, trying web fallback...")
            domain = result["domain_used"]
            if domain:
                web_result = await web_email_finder.find_email_via_web(
                    job.company, domain, max_attempts=config.fallback_max_attempts
                )
                emails = web_result.get("emails", [])
                if emails:
                    best = emails[0]
                    result["email"] = best["email"]
                    result["status"] = "fallback_verified" if best["type"] == "verified" else "fallback_inferred"
                    result["source"] = f"web ({best['confidence']})"
                    print(f"  → {job.company}: {best['confidence']} ({best['type']}) — {best['email']}")

        results[job.id] = {
            "email": result["email"],
            "status": result["status"],
            "company": job.company,
            "domain_used": result["domain_used"],
            "category": ", ".join(config.categories),
        }

        print(f"  → {job.company}: {result['status']} — {result['email'] or 'not found'}")

        if result["status"] != "valid":
            await asyncio.sleep(2)

    if global_credit_exhausted and config.fallback_enabled:
        print("  ⚠️ AnyMailFinder credits exhausted - remaining jobs will use web fallback")

    emails_path.parent.mkdir(parents=True, exist_ok=True)
    emails_path.write_text(json.dumps(results, indent=2, default=str))

    return results
