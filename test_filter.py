"""Quick test for LLM filtering with 1 job."""

import asyncio
import json
from pathlib import Path
from app.tools.filter import filter_jobs

async def test():
    # Load CV
    cv_data = json.loads(Path("data/cv_parsed.json").read_text())
    cv_text = cv_data.get("text", "")
    print(f"CV loaded: {len(cv_text)} chars")
    
    # Load 1 job from apify_results.json
    raw_data = json.loads(Path("data/apify_results.json").read_text())
    print(f"Total jobs in file: {len(raw_data)}")
    
    # Test with just 1 job
    test_job = raw_data[0]
    print(f"Testing with: {test_job.get('title')} @ {test_job.get('companyName', 'Unknown')}")
    print(f"Description (first 200 chars): {str(test_job.get('descriptionText', test_job.get('descriptionHtml', '')))[:200]}...")
    
    # Call filter
    print("\nCalling LLM...")
    qualifying, rejected = await filter_jobs(
        [test_job],  # Pass as list
        cv_text,
        min_score=5,
    )
    
    print(f"\nResults: {len(qualifying)} qualified, {len(rejected)} rejected")
    if qualifying:
        print(f"✅ QUALIFIED: {qualifying[0].title}")
    if rejected:
        print(f"❌ REJECTED: {rejected[0].title}")
        print(f"   Reason: {rejected[0].rejection_reason}")

asyncio.run(test())
