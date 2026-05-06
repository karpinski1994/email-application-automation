"""Applied Jobs Tracker - Prevents duplicate applications."""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional


def sanitize_url_for_folder(url: str) -> str:
    """Sanitize URL to be used as a folder name."""
    # Remove protocol and common prefixes
    cleaned = re.sub(r'^https?://(www\.)?', '', url)
    # Replace special chars with underscores
    cleaned = re.sub(r'[^\w\-]', '_', cleaned)
    # Remove multiple underscores
    cleaned = re.sub(r'_+', '_', cleaned)
    # Truncate to 100 chars to avoid filesystem limits
    return cleaned[:100]


class AppliedTracker:
    """Tracks which jobs have been applied to (drafts created) using job URL as identifier."""
    
    def __init__(self, path: str = "data/applied_jobs.json"):
        self.path = Path(path)
        self.applied: list = []
        self._load()
    
    def _load(self):
        """Load applied jobs from JSON file."""
        try:
            if self.path.exists():
                data = json.loads(self.path.read_text())
                self.applied = data.get("applied", [])
        except Exception:
            self.applied = []
    
    def _save(self):
        """Save applied jobs to JSON file."""
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps({"applied": self.applied}, indent=2))
        except Exception:
            pass  # Fail silently if we can't save
    
    def is_applied(self, job_url: str) -> bool:
        """Check if job was already applied (by URL)."""
        if not job_url:
            return False
        return any(j.get("job_url") == job_url for j in self.applied)
    
    def mark_applied(
        self,
        job_url: str,
        company: str,
        draft_id: Optional[str] = None,
        subject: str = "",
        to: str = ""
    ):
        """Record a job as applied (draft created)."""
        if not job_url:
            return
        
        if not self.is_applied(job_url):
            self.applied.append({
                "job_url": job_url,
                "job_folder": sanitize_url_for_folder(job_url),
                "company": company,
                "applied_at": datetime.now().isoformat(),
                "draft_id": draft_id or "",
                "subject": subject,
                "to": to
            })
            self._save()
    
    def get_applied_count(self) -> int:
        """Return count of applied jobs."""
        return len(self.applied)
    
    def get_applied_companies(self) -> list:
        """Return list of companies already applied to."""
        return [j.get("company", "") for j in self.applied if j.get("company")]
    
    def get_applied_urls(self) -> list:
        """Return list of URLs already applied to."""
        return [j.get("job_url", "") for j in self.applied if j.get("job_url")]