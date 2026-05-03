"""CLI entry point for Email Application Automation."""

import argparse
import asyncio
import sys

from app.config import load_config
from app.agent import run


def main():
    parser = argparse.ArgumentParser(description="Email Application Automation")
    parser.add_argument("command", nargs="?", default="run", help="Command to run")
    parser.add_argument("--force", "-f", action="store_true", help="Force re-run, ignore cache")
    parser.add_argument("--step", "-s", type=int, default=1, help="Start from step N (1-7)")
    parser.add_argument("--dry-run", action="store_true", help="Dry run, don't call external APIs")
    parser.add_argument("--count", "-c", type=int, default=50, help="Max jobs to process")
    parser.add_argument("--config", default="config.yaml", help="Config file path")
    
    args = parser.parse_args()
    
    if args.command == "run":
        try:
            config = load_config(args.config)
            config.search.count = args.count
            config.dry_run = args.dry_run
            
            print(f"Starting Email Application Automation...")
            print(f"Config: {config.llm.provider} / {config.llm.model}")
            print(f"Dry run: {args.dry_run}")
            print(f"Force: {args.force}")
            print(f"Step: {args.step}")
            print()
            
            summary = asyncio.run(run(config, force=args.force, step=args.step, dry_run=args.dry_run))
            
            print()
            print("=" * 50)
            print("RUN COMPLETE")
            print("=" * 50)
            print(f"Jobs found: {summary.jobs_found}")
            print(f"Jobs filtered: {summary.jobs_filtered}")
            print(f"Jobs qualified: {summary.jobs_qualified}")
            print(f"Drafts created: {summary.drafts_created}")
            if summary.errors:
                print(f"Errors: {len(summary.errors)}")
                for e in summary.errors[:5]:
                    print(f"  - {e}")
            
        except FileNotFoundError as e:
            print(f"Error: {e}")
            print("Run 'cp config.example.yaml config.yaml' to create config")
            sys.exit(1)
        except Exception as e:
            print(f"Error: {e}")
            sys.exit(1)
    else:
        print(f"Unknown command: {args.command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
