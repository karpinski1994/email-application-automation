"""Web-based email finder using DuckDuckGo search as fallback."""

import asyncio
import logging
import re
from typing import Optional

from ddgs import DDGS

logger = logging.getLogger(__name__)

EMAIL_REGEX = re.compile(
    r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
)


def _extract_emails_from_text(text: str) -> list[str]:
    """Extract all email addresses from text."""
    return list(set(EMAIL_REGEX.findall(text)))


def _is_valid_email(email: str) -> bool:
    """Basic email validation."""
    if not email or '@' not in email:
        return False
    local, domain = email.rsplit('@', 1)
    if not local or not domain or '.' not in domain:
        return False
    if len(domain) < 2:
        return False
    return True


def _guess_email_patterns(domain: str, first_name: Optional[str] = None, last_name: Optional[str] = None) -> list[dict]:
    """Generate guessed email patterns for a domain."""
    guesses = []

    if first_name and last_name:
        patterns = [
            f"{first_name.lower()}.{last_name.lower()}@{domain}",
            f"{first_name.lower()}{last_name.lower()}@{domain}",
            f"{first_name[0].lower()}{last_name.lower()}@{domain}",
            f"{first_name.lower()}{last_name[0].lower()}@{domain}",
        ]
        for pattern in patterns:
            guesses.append({
                "email": pattern,
                "source": "pattern_inference",
                "confidence": "low",
                "type": "inferred"
            })

    common_patterns = [
        f"contact@{domain}",
        f"info@{domain}",
        f"hello@{domain}",
    ]
    for pattern in common_patterns:
        guesses.append({
            "email": pattern,
            "source": "common_pattern",
            "confidence": "low",
            "type": "inferred"
        })

    return guesses


async def find_email_via_web(
    company: str,
    domain: str,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
    max_attempts: int = 3,
) -> dict:
    """Find email addresses via web search (DuckDuckGo).

    Strategy:
    1. Search for "site:domain email" or "email @domain"
    2. Search for specific patterns like "firstname.lastname@domain"
    3. Generate guessed patterns as last resort

    Returns:
        {
            "emails": [
                {"email": str, "source": str, "confidence": "high|medium|low", "type": "verified|inferred"}
            ]
        }
    """
    results = []
    seen_emails = set()

    queries = [
        f"site:{domain} contact email",
        f"site:{domain} @ {domain}",
    ]

    if first_name and last_name:
        queries.extend([
            f'"{first_name} {last_name}" email {domain}',
            f"{first_name}.{last_name}@{domain}",
        ])

    queries = queries[:max_attempts]

    try:
        loop = asyncio.get_event_loop()
        with DDGS() as ddgs:
            for query in queries:
                try:
                    search_results = await loop.run_in_executor(
                        None,
                        lambda q=query: ddgs.text(q, max_results=5)
                    )

                    for result in search_results:
                        text_content = f"{result.get('title', '')} {result.get('body', '')}"
                        emails = _extract_emails_from_text(text_content)

                        for email in emails:
                            if email not in seen_emails and _is_valid_email(email):
                                seen_emails.add(email)
                                results.append({
                                    "email": email,
                                    "source": f"duckduckgo: {result.get('title', 'unknown')[:50]}",
                                    "confidence": "medium",
                                    "type": "verified"
                                })

                except Exception as e:
                    logger.debug(f"Search query failed: {query} — {e}")
                    continue

    except Exception as e:
        logger.warning(f"DuckDuckGo search failed: {e}")

    if not results and domain:
        guessed = _guess_email_patterns(domain, first_name, last_name)
        results.extend(guessed)

    deduplicated = []
    seen = set()
    for r in results:
        if r["email"].lower() not in seen:
            seen.add(r["email"].lower())
            deduplicated.append(r)

    return {"emails": deduplicated[:10]}