#!/usr/bin/env python3
"""
Test script for Apify LinkedIn Jobs Scraper API integration.

Usage:
    # Quick connectivity test (just starts a run and checks status, then aborts)
    python test_apify.py --quick

    # Full scrape test with 5 jobs (costs ~$0.005)
    python test_apify.py --full

    # Full scrape with custom count
    python test_apify.py --full --count 20
"""

import asyncio
import argparse
import os
import json
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
load_dotenv()

APIFY_API_BASE = "https://api.apify.com/v2"


async def test_quick():
    """Quick connectivity test - verify API key, actor access, and run start."""
    import httpx
    
    api_token = os.getenv("APIFY_API_KEY", "")
    actor_id = "hKByXkMQaC5Qt9UMN"
    
    if not api_token:
        print("❌ APIFY_API_KEY not found in .env")
        return False
    
    print(f"✅ API key found: {api_token[:15]}...{api_token[-4:]}")
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Test 1: Verify the actor exists
        print("\n── Test 1: Actor accessibility ──")
        actor_response = await client.get(
            f"{APIFY_API_BASE}/acts/{actor_id}",
            params={"token": api_token},
        )
        
        if actor_response.status_code == 200:
            actor_data = actor_response.json().get("data", {})
            print(f"✅ Actor found: {actor_data.get('title', 'Unknown')}")
            print(f"   ID: {actor_data.get('id', 'Unknown')}")
            print(f"   Username: {actor_data.get('username', 'Unknown')}/{actor_data.get('name', 'Unknown')}")
        else:
            print(f"❌ Actor not accessible: {actor_response.status_code}")
            print(f"   Response: {actor_response.text[:200]}")
            return False
        
        # Test 2: Start a small run (1 job) and immediately abort to save credits
        print("\n── Test 2: Run start + abort (no credits consumed) ──")
        
        test_url = "https://www.linkedin.com/jobs/search/?keywords=test&position=1&pageNum=0"
        
        run_response = await client.post(
            f"{APIFY_API_BASE}/acts/{actor_id}/runs",
            params={"token": api_token},
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            json={
                "urls": [test_url],
                "count": 10,
                "scrapeCompany": False,
                "splitByLocation": False,
            }
        )
        
        if run_response.status_code in (200, 201):
            run_data = run_response.json().get("data", run_response.json())
            run_id = run_data.get("id", "unknown")
            dataset_id = run_data.get("defaultDatasetId", "unknown")
            status = run_data.get("status", "unknown")
            
            print(f"✅ Run started successfully!")
            print(f"   Run ID: {run_id}")
            print(f"   Dataset ID: {dataset_id}")
            print(f"   Status: {status}")
            
            # Immediately abort the run to save credits
            print(f"\n   Aborting run to save credits...")
            abort_response = await client.post(
                f"{APIFY_API_BASE}/actor-runs/{run_id}/abort",
                params={"token": api_token},
            )
            if abort_response.status_code == 200:
                print(f"✅ Run aborted successfully")
            else:
                print(f"⚠️  Abort response: {abort_response.status_code}")
        else:
            print(f"❌ Run start failed: {run_response.status_code}")
            print(f"   Response: {run_response.text[:300]}")
            return False
        
        # Test 3: Verify dataset endpoint works
        print("\n── Test 3: Dataset endpoint ──")
        items_response = await client.get(
            f"{APIFY_API_BASE}/datasets/{dataset_id}/items",
            params={
                "token": api_token,
                "format": "json",
                "clean": "true",
            },
        )
        
        if items_response.status_code == 200:
            items = items_response.json()
            print(f"✅ Dataset endpoint works (items so far: {len(items) if isinstance(items, list) else 0})")
        else:
            print(f"⚠️  Dataset response: {items_response.status_code}")
    
    print("\n" + "=" * 50)
    print("✅ All connectivity tests passed!")
    print("=" * 50)
    return True


async def test_full(count: int = 5):
    """Full integration test - runs a real scrape with a small count."""
    # Import from the project
    sys.path.insert(0, str(Path(__file__).parent / "src"))
    from app.config import load_config
    from app.tools.scraper import scrape_jobs
    
    print(f"🚀 Running full Apify scrape test with count={count}")
    print(f"   Estimated cost: ${count * 0.001:.3f}")
    print()
    
    config = load_config()
    
    # Override count for test
    urls = config.search.urls
    print(f"URLs from config.yaml:")
    for i, url in enumerate(urls, 1):
        # Show just the keywords part for readability
        kw = url.split("keywords=")[1].split("&")[0] if "keywords=" in url else url
        print(f"  {i}. ...keywords={kw}")
    print()
    
    try:
        jobs = await scrape_jobs(urls, config.apify, count=count)
        
        print()
        print("=" * 60)
        print(f"RESULTS: {len(jobs)} jobs scraped")
        print("=" * 60)
        
        for job in jobs[:5]:
            print(f"\n  📋 {job.title}")
            print(f"     🏢 {job.company}")
            print(f"     📍 {job.location or 'N/A'}")
            print(f"     🔗 {job.url[:80]}..." if len(job.url) > 80 else f"     🔗 {job.url}")
            if job.requirements:
                print(f"     📝 {', '.join(job.requirements[:5])}")
        
        if len(jobs) > 5:
            print(f"\n  ... and {len(jobs) - 5} more jobs")
        
        # Save results to data/
        output_path = Path("data/test_apify_results.json")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(
            [j.model_dump() for j in jobs], indent=2, default=str
        ))
        print(f"\n💾 Results saved to: {output_path}")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    parser = argparse.ArgumentParser(description="Test Apify API integration")
    parser.add_argument("--quick", action="store_true", help="Quick connectivity test (free, no credits)")
    parser.add_argument("--full", action="store_true", help="Full scrape test (costs ~$0.005 per 5 jobs)")
    parser.add_argument("--count", type=int, default=5, help="Number of jobs for full test (default: 5)")
    
    args = parser.parse_args()
    
    if not args.quick and not args.full:
        print("Usage:")
        print("  python test_apify.py --quick     # Free connectivity test")
        print("  python test_apify.py --full       # Real scrape test (~$0.005)")
        print("  python test_apify.py --full --count 20")
        return
    
    if args.quick:
        success = asyncio.run(test_quick())
    else:
        success = asyncio.run(test_full(args.count))
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
