"""Applied Jobs Tracker - Prevents duplicate applications."""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional


class AppliedTracker:
    """Tracks which jobs have been applied to (drafts created)."""
    
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
    
    def is_applied(self, job_id: str) -> bool:
        """Check if job was already applied."""
        if not job_id:
            return False
        return any(j.get("job_id") == job_id for j in self.applied)
    
    def mark_applied(
        self,
        job_id: str,
        company: str,
        draft_id: Optional[str] = None,
        subject: str = "",
        to: str = ""
    ):
        """Record a job as applied (draft created)."""
        if not job_id:
            return
        
        if not self.is_applied(job_id):
            self.applied.append({
                "job_id": job_id,
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