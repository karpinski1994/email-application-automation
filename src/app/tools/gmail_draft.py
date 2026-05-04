"""Gmail Draft Creator - Creates Gmail drafts using Gmail API."""

import base64
import json
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

SCOPES = ['https://www.googleapis.com/auth/gmail.compose']


def _load_credentials(credentials_path: str = "credentials.json"):
    """Load OAuth credentials from JSON file."""
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    creds = None
    token_path = Path("data/gmail_token.json")

    if token_path.exists():
        creds = Credentials.from_authorized_user_info(
            json.loads(token_path.read_text()), SCOPES
        )

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(None)
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                credentials_path, SCOPES
            )
            creds = flow.run_local_server(port=0)

        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(creds.to_json())

    return creds


def _create_mime_message(to: str, subject: str, body: str, attachment_path: Path = None) -> str:
    """Create a MIME message for the email."""
    message = MIMEMultipart()
    message['to'] = to
    message['subject'] = subject

    message.attach(MIMEText(body, 'plain'))

    if attachment_path and attachment_path.exists():
        import email.mime.application
        with open(attachment_path, 'rb') as f:
            att = email.mime.application.MIMEApplication(f.read(), _subtype='pdf')
        att.add_header('Content-Disposition', 'attachment', filename=attachment_path.name)
        message.attach(att)

    return base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')


async def create_draft(
    to: str,
    subject: str,
    body: str,
    attachment_path: Path,
    credentials_path: str = "credentials.json"
) -> str:
    """Create Gmail draft with PDF attachment.

    Args:
        to: Recipient email
        subject: Email subject
        body: Email body
        attachment_path: Path to PDF attachment
        credentials_path: Path to OAuth credentials JSON

    Returns:
        Draft ID
    """
    try:
        from googleapiclient.discovery import build

        creds = _load_credentials(credentials_path)
        service = build('gmail', 'v1', credentials=creds)

        raw_message = _create_mime_message(to, subject, body, attachment_path)

        draft = {
            'message': {
                'raw': raw_message
            }
        }

        result = service.users().drafts().create(
            userId='me',
            body=draft
        ).execute()

        draft_id = result.get('id')
        logger.info(f"Created Gmail draft: {draft_id}")

        cache_file = Path(f"data/drafts/{draft_id}.json")
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps({
            "to": to,
            "subject": subject,
            "draft_id": draft_id
        }))

        return draft_id

    except Exception as e:
        logger.error(f"Failed to create Gmail draft: {e}")
        return f"error: {str(e)}"


async def create_draft_mock(
    to: str,
    subject: str,
    body: str,
    attachment_path: Path = None
) -> str:
    """Mock implementation for testing without Gmail credentials."""
    draft_id = f"mock_draft_{to}"

    cache_file = Path(f"data/drafts/{draft_id}.json")
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps({
        "to": to,
        "subject": subject,
        "draft_id": draft_id
    }))

    logger.info(f"Created mock draft: {draft_id}")
    return draft_id