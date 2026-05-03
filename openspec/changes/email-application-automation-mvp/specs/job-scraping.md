## ADDED Requirements

### Requirement: Job scraping from configured URLs
The system SHALL scrape job listings from URLs configured in config.yaml using the Apify API.

#### Scenario: Successful scrape
- **WHEN** user configures search.urls in config.yaml
- **THEN** system scrapes jobs from each URL and returns list of Job objects

#### Scenario: Apify API failure
- **WHEN** Apify API returns error
- **THEN** system logs error and continues to next URL

### Requirement: Parse CV from file
The system SHALL parse CV from PDF or TXT file specified in config.yaml.

#### Scenario: PDF parsing
- **WHEN** CV file is PDF
- **THEN** system extracts text using pdfplumber

#### Scenario: TXT parsing
- **WHEN** CV file is TXT
- **THEN** system reads text directly from file

#### Scenario: Unsupported format
- **WHEN** CV file format is not PDF or TXT
- **THEN** system raises ValueError with unsupported format message

### Requirement: Skip scraping if data exists
The system SHALL skip Apify API call if data/apify_results.json already exists.

#### Scenario: Skip existing scraped data
- **WHEN** data/apify_results.json exists AND not --rerun
- **THEN** load from file instead of calling Apify API
- **THEN** saves API credits

### Requirement: Skip CV parsing if data exists
The system SHALL skip CV parsing if data/cv_parsed.json already exists.

#### Scenario: Skip existing parsed CV
- **WHEN** data/cv_parsed.json exists AND not --rerun
- **THEN** load from file instead of parsing CV file