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
        Draft ID (or error message starting with "error:")
    """
    try:
        # Step 1: Load credentials
        creds = _load_credentials(credentials_path)
        if creds is None:
            raise ValueError(
                "Credentials loading failed - _load_credentials returned None. "
                "Verify that credentials.json exists in project root and contains valid OAuth client credentials. "
                "Troubleshooting: Delete data/gmail_token.json to force re-authentication."
            )
        
        # Step 2: Build Gmail service
        from googleapiclient.discovery import build
        service = build('gmail', 'v1', credentials=creds)
        if service is None:
            raise RuntimeError(
                "Failed to build Gmail service - googleapiclient.discovery.build() returned None. "
                "This may indicate invalid credentials or API configuration issues."
            )
        
        # Step 3: Create MIME message
        raw_message = _create_mime_message(to, subject, body, attachment_path)

        # Step 4: Call Gmail API to create draft
        draft = {
            'message': {
                'raw': raw_message
            }
        }

        result = service.users().drafts().create(
            userId='me',
            body=draft
        ).execute()

        if result is None:
            raise RuntimeError(
                "Gmail API returned None when creating draft. "
                "Check if Gmail API is enabled in Google Cloud Console and credentials have 'gmail.compose' scope."
            )

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

    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        return f"error: {e}"
    except RuntimeError as e:
        logger.error(f"Runtime error: {e}")
        return f"error: {e}"
    except FileNotFoundError as e:
        logger.error(f"File not found error: {e}. Ensure credentials.json exists in project root.")
        return f"error: File not found - {e}"
    except Exception as e:
        error_type = type(e).__name__
        logger.error(f"Failed to create Gmail draft ({error_type}): {e}")
        logger.error("Troubleshooting steps:")
        logger.error("  1. Delete data/gmail_token.json to force re-authentication")
        logger.error("  2. Verify credentials.json exists in project root")
        logger.error("  3. Check Gmail API is enabled in Google Cloud Console")
        logger.error("  4. Ensure OAuth consent screen has your email as test user")
        return f"error: {error_type}: {e}"


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