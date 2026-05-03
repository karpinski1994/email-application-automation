## ADDED Requirements

### Requirement: Filter jobs by qualification match
The system SHALL evaluate if candidate's CV matches job requirements using Pydantic AI structured output with AsyncOpenAI client.

#### Scenario: Qualified candidate
- **WHEN** LLM evaluates candidate as meeting requirements
- **THEN** job is added to qualifying list

#### Scenario: Not qualified
- **WHEN** LLM evaluates candidate as not meeting requirements
- **THEN** job is added to rejected list with reason populated to rejection_reason field

### Requirement: Filter jobs by accepting status
The system SHALL evaluate if job is still accepting applications using Pydantic AI structured output.

#### Scenario: Still accepting
- **WHEN** LLM determines job is accepting applications
- **THEN** job proceeds to next step

#### Scenario: No longer accepting
- **WHEN** LLM determines job is not accepting applications
- **THEN** job is rejected with "not accepting" reason

### Requirement: Use AsyncOpenAI client
The system SHALL use AsyncOpenAI client for all LLM calls in async context.

#### Scenario: Async LLM call
- **WHEN** filter_jobs() is called with await
- **THEN** client.chat.completions.create() is called asynchronously

### Requirement: Skip filter if data exists
The system SHALL skip LLM filtering if data/filtered_jobs.json already exists.

#### Scenario: Skip existing filtered data
- **WHEN** data/filtered_jobs.json exists AND not --rerun
- **THEN** load from file instead of calling LLM
- **THEN** saves API credits (filtering uses LLM)