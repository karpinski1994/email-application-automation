## ADDED Requirements

### Requirement: Create Gmail draft
The system SHALL create Gmail draft with PDF attachment and cover letter body.

#### Scenario: Dry run mode
- **WHEN** config.dry_run is True
- **THEN** system logs draft creation but skips API call

#### Scenario: Normal draft creation
- **WHEN** config.dry_run is False
- **THEN** system creates draft with attachment via Gmail API

#### Scenario: OAuth token expired
- **WHEN** credentials are expired
- **THEN** system refreshes token automatically

### Requirement: OAuth authentication
The system SHALL authenticate with Gmail using OAuth2 flow.

#### Scenario: First run
- **WHEN** no token exists
- **THEN** browser opens for OAuth consent flow

#### Scenario: Token exists
- **WHEN** token.json exists
- **THEN** system loads credentials from file