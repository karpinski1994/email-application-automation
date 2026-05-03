## ADDED Requirements

### Requirement: Find hiring manager email
The system SHALL discover hiring manager email using Pydantic AI agent with multi-tool fallback (NOT simple API call).

**CORRECTED:** Uses POST https://api.anymailfinder.com/v4/search/text.json

#### Scenario: API returns email
- **WHEN** AnyMailFinder API returns valid email
- **THEN** system returns email address

#### Scenario: API fails - parse description
- **WHEN** AnyMailFinder API returns empty
- **THEN** agent parses job description for embedded email (Tool 2)

#### Scenario: Both fail - guess pattern
- **WHEN** API returns empty AND no email in description
- **THEN** agent guesses email pattern (first.last@domain.com) (Tool 3)

#### Scenario: No email found
- **WHEN** all tools fail
- **THEN** system returns empty string

### Requirement: Circuit breaker on API failures
The system SHALL stop retrying after 5 consecutive failures.

#### Scenario: Circuit open
- **WHEN** 5 consecutive API failures occur
- **THEN** subsequent calls return empty immediately