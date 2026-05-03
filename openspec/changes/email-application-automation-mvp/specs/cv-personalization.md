## ADDED Requirements

### Requirement: Generate personalized CV
The system SHALL generate personalized CV PDF using Pydantic AI structured JSON output mapped to HTML template.

#### Scenario: Successful CV generation
- **WHEN** Pydantic AI returns CVData
- **THEN** system renders HTML template and converts to PDF via weasyprint

#### Scenario: Invalid JSON response
- **WHEN** Pydantic AI returns invalid JSON
- **THEN** system logs error and job is skipped

#### Scenario: PDF conversion failure
- **WHEN** weasyprint fails to generate PDF
- **THEN** system logs error and job is skipped

### Requirement: Skip CV personalization if PDF exists
The system SHALL skip LLM CV generation if data/cvs/personalized_cv_{job_id}.pdf already exists.

#### Scenario: Skip existing personalized CV
- **WHEN** data/cvs/personalized_cv_{job_id}.pdf exists
- **THEN** skip PDF generation for that job
- **THEN** saves LLM credits