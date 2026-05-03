## ADDED Requirements

### Requirement: Process multiple jobs with configurable parallelism
The system SHALL process multiple jobs with asyncio semaphore, with concurrency limited based on LLM provider.

**CORRECTED:** Local Ollama = Semaphore(1) (sequential), OpenAI = Semaphore(5) (parallel)

#### Scenario: Local LLM - sequential
- **WHEN** llm.provider is "local"
- **THEN** use Semaphore(1) - runs sequentially due to VRAM limits

#### Scenario: Cloud LLM - parallel
- **WHEN** llm.provider is "openai"
- **THEN** use Semaphore(5) - runs in parallel

#### Scenario: Progress reporting
- **WHEN** processing jobs
- **THEN** display progress bar with rich.progress

### Requirement: Wrap blocking calls
The system SHALL use asyncio.to_thread() for CPU-bound operations to avoid blocking the event loop.

#### Scenario: WeasyPrint PDF generation
- **WHEN** generating PDF with weasyprint
- **THEN** wrap in asyncio.to_thread() to avoid blocking event loop