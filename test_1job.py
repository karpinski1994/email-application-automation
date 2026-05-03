"""Quick test: 1 job with rule-based filtering."""

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
    test_job = [raw_data[0]]  # Just 1 job
    
    print(f"Testing with: {test_job[0].get('title')} @ {test_job[0].get('companyName', 'Unknown')}")
    print(f"Description (first 200 chars): {str(test_job[0].get('descriptionText', test_job[0].get('descriptionHtml', ''))[:200]}...")
    
    # Call filter (rule-based + LLM)
    print("\nCalling filter_jobs...")
    qualifying, rejected = await filter_jobs(
        test_job,  # Pass as list
        cv_text,
        llm_base_url="http://localhost:11434/v1",  # Local Ollama
        llm_model="qwen2.5:7b",
        llm_api_key="ollama",
        llm_provider="local",
        min_score=5,
    )
    
    print(f"\nResults: {len(qualifying)} qualified, {len(rejected)} rejected")
    if qualifying:
        print(f"✅ QUALIFIED: {qualifying[0].title}")
    if rejected:
        print(f"❌ REJECTED: {rejected[0].title}")
        print(f"   Reason: {rejected[0].rejection_reason}")

asyncio.run(test())
