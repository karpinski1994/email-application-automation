## ADDED Requirements

### Requirement: Track processed jobs
The system SHALL track job_id → draft_id mappings to avoid duplicate processing using in-memory set.

**CORRECTED:** Use in-memory set, NOT read-modify-write on shared JSON file

#### Scenario: Skip already processed
- **WHEN** job.id is in _processed_ids (in-memory set)
- **THEN** system skips processing for that job

#### Scenario: Record new job
- **WHEN** job is successfully processed
- **THEN** system adds job_id to _processed_ids (in-memory)

#### Scenario: Atomic file write
- **WHEN** saving processed_jobs.json
- **THEN** use write-to-temp + rename pattern