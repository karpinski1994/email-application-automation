## Pipeline Steps

| Step | Name | Input | Output | Data File |
|------|------|-------|--------|---------|
| 1 | Parse CV | CV file (PDF/TXT) | cv_text | data/cv_parsed.json |
| 2 | Scrape Jobs | search URLs | list[Job] | data/apify_results.json |
| 3 | Filter Jobs | jobs + cv_text | qualifying + rejected | data/filtered_jobs.json, data/filtered_out_jobs.json |
| 4 | Personalize CV | job + cv_text | PDF | data/cvs/personalized_cv_{job_id}.pdf |
| 5 | Find Email | company | email | data/emails/{job_id}.json |
| 6 | Generate Cover Letter | job + cv_text | letter | data/cover_letters/{job_id}.txt |
| 7 | Create Gmail Draft | email + letter + attachment | draft_id | data/drafts/{job_id}.json |

## ADDED Requirements

### Requirement: Step-based execution
The system SHALL support executing from a specific step using --step flag.

#### Scenario: Start from step 3
- **WHEN** user runs: python -m app run --step=3
- **THEN** system loads data/cv_parsed.json and data/apify_results.json
- **THEN** system starts from step 3 (filter)

#### Scenario: Start from step 5
- **WHEN** user runs: python -m app run --step=5
- **THEN** system loads all previous step data (1-4)
- **THEN** system starts from step 5 (find email)

### Requirement: Skip specific steps
The system SHALL skip specified steps using --skip-steps flag.

#### Scenario: Skip scraping
- **WHEN** user runs: python -m app run --skip-steps=2
- **THEN** system loads data/apify_results.json if exists
- **THEN** system skips step 2 (don't call Apify)

### Requirement: Detect existing data
The system SHALL detect if intermediate data exists and skip API calls.

#### Scenario: CV already parsed
- **WHEN** data/cv_parsed.json exists
- **THEN** load from file instead of parsing CV

#### Scenario: Jobs already scraped
- **WHEN** data/apify_results.json exists AND --step > 2
- **THEN** load from file instead of calling Apify

#### Scenario: Job already filtered
- **WHEN** data/filtered_jobs.json exists AND --step > 3
- **THEN** load from file instead of calling LLM

#### Scenario: CV already personalized
- **WHEN** data/cvs/personalized_cv_{job_id}.pdf exists AND --step > 4
- **THEN** skip PDF generation for that job

#### Scenario: Email already found
- **WHEN** data/emails/{job_id}.json exists AND --step > 5
- **THEN** load from file instead of calling API

#### Scenario: Cover letter already generated
- **WHEN** data/cover_letters/{job_id}.txt exists AND --step > 6
- **THEN** load from file instead of calling LLM

### Requirement: Force rerun
The system SHALL support force rerunning all steps using --rerun flag.

#### Scenario: Clear and rerun
- **WHEN** user runs: python -m app run --rerun
- **THEN** system deletes data/cv_parsed.json, data/apify_results.json, etc.
- **THEN** system starts from step 1 fresh

### Requirement: Dry run mode
The system SHALL skip all external APIs in dry run mode.

#### Scenario: Dry run skips everything
- **WHEN** user runs: python -m app run --dry-run
- **THEN** system does NOT call: Apify, AnyMailFinder, OpenAI/Ollama, Gmail
- **THEN** system logs what it WOULD do
- **THEN** no data files are created/updated