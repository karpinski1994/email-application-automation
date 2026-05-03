## ADDED Requirements

### Requirement: PII redaction before LLM calls
The system SHALL redact PII from CV and job descriptions before sending to LLM when privacy.redact_pii is true.

**NEW:** Default privacy setting

#### Scenario: Redact names
- **WHEN** privacy.redact_pii is True AND CV contains name
- **THEN** replace name with "[REDACTED]" before LLM call

#### Scenario: Redact emails
- **WHEN** privacy.redact_pii is True AND CV contains email
- **THEN** replace email with "[EMAIL]" before LLM call

#### Scenario: Redact phones
- **WHEN** privacy.redact_pii is True AND CV contains phone
- **THEN** replace phone with "[PHONE]" before LLM call

### Requirement: Prompt injection sanitization
The system SHALL sanitize job descriptions before inserting into LLM prompts.

#### Scenario: Strip code blocks
- **WHEN** job description contains markdown code blocks
- **THEN** remove code blocks before LLM prompt

#### Scenario: Escape special characters
- **WHEN** job description contains `<`, `>`, `{{`, `}}`
- **THEN** escape to prevent injection

### Requirement: Context window management
The system SHALL truncate text to prevent context overflow for smaller local models.

#### Scenario: Truncate job description
- **WHEN** job.description is longer than 2000 chars
- **THEN** truncate to job.description[:2000] before LLM call

#### Scenario: Truncate CV
- **WHEN** cv_text is longer than 3000 chars
- **THEN** truncate to cv_text[:3000] before LLM call

### Requirement: Secure credential storage
The system SHALL store OAuth tokens in data/ directory that is gitignored.

#### Scenario: Token in data directory
- **WHEN** OAuth token is created
- **THEN** store in data/gmail_token.json (not project root)

#### Scenario: No credentials in git
- **WHEN** git status is checked
- **THEN** data/ directory is in .gitignore

### Requirement: Secrets in .env, not config.yaml
The system SHALL store all API keys and secrets in .env file, not in config.yaml.

#### Scenario: Load secrets from .env
- **WHEN** config is loaded
- **THEN** secrets loaded from .env via python-dotenv

#### Scenario: No secrets in config
- **WHEN** user commits config.yaml
- **THEN** No API keys present (they're in .env which is gitignored)