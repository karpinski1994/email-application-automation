"""Gmail Draft Creator - Creates Gmail drafts."""

from pathlib import Path
from typing import Optional


async def create_draft(
    to: str,
    subject: str,
    body: str,
    attachment_path: Path,
    credentials: Optional[object] = None
) -> str:
    """Create Gmail draft with PDF attachment.
    
    Args:
        to: Recipient email
        subject: Email subject
        body: Email body
        attachment_path: Path to PDF attachment
        credentials: Gmail OAuth credentials
    
    Returns:
        Draft ID
    """
    # Mock implementation
    draft_id = f"mock_draft_{to}"
    
    # Save to cache
    import json
    cache_file = Path(f"data/drafts/{draft_id}.json")
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps({
        "to": to,
        "subject": subject,
        "draft_id": draft_id
    }))
    
    return draft_id


# Real implementation would use Gmail API
