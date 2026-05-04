"""Data models for Email Application Automation."""

from pydantic import BaseModel, Field
from typing import Optional
from pathlib import Path


class SearchConfig(BaseModel):
    """Job search configuration."""
    urls: list[str] = Field(min_length=1, description="List of job search URLs")
    count: int = Field(default=100, ge=1, le=200, description="Max jobs to process")


class CVConfig(BaseModel):
    """CV configuration."""
    path: str = Field(description="Path to CV file (PDF or TXT)")


class GmailConfig(BaseModel):
    """Gmail configuration."""
    draft_only: bool = True
    token_path: str = "data/gmail_token.json"
    credentials_path: str = "credentials.json"


class LLMConfig(BaseModel):
    """LLM provider configuration."""
    provider: str = "local"  # "local" or "openai"
    model: str = "qwen2.5:7b"
    base_url: str = "http://localhost:11434/v1"
    api_key: str = "ollama"


class ApifyConfig(BaseModel):
    """Apify configuration for job scraping."""
    api_token: str = ""
    actor_id: str = "apify/linkedin-jobs-scraper"


class PrivacyConfig(BaseModel):
    """Privacy settings."""
    redact_pii: bool = True


class FilterConfig(BaseModel):
    """Filter configuration."""
    embedding_shortlist_size: int = 20
    llm_fit_threshold: int = 70
    embedding_model: str = "nomic-embed-text"
    scoring_model: str = "llama3.2"


class EmailFinderConfig(BaseModel):
    """Email finder configuration."""
    provider: str = "anymailfinder"
    api_key: str = ""
    categories: list[str] = Field(default_factory=lambda: ["engineering", "hr"])
    max_domain_attempts: int = 3


class Config(BaseModel):
    """Main configuration."""
    search: SearchConfig
    cv: CVConfig
    gmail: GmailConfig
    llm: LLMConfig = Field(default_factory=LLMConfig)
    apify: ApifyConfig = Field(default_factory=ApifyConfig)
    filter: FilterConfig = Field(default_factory=FilterConfig)
    email_finder: EmailFinderConfig = Field(default_factory=EmailFinderConfig)
    privacy: PrivacyConfig = Field(default_factory=PrivacyConfig)
    dry_run: bool = False


class Job(BaseModel):
    """Job listing model."""
    id: str
    title: str
    company: str
    description: str
    url: str
    location: Optional[str] = None
    hiring_manager_name: Optional[str] = None
    requirements: list[str] = Field(default_factory=list)
    posted_date: Optional[str] = None
    accepting_applications: Optional[bool] = None
    rejection_reason: Optional[str] = None
    # Additional fields from Apify
    remote_allowed: Optional[bool] = None
    employment_type: Optional[str] = None
    seniority_level: Optional[str] = None
    company_website: Optional[str] = None


class FilterDecision(BaseModel):
    """LLM filter decision."""
    is_qualified: bool
    is_accepting_applications: bool
    reason: Optional[str] = None


class CVData(BaseModel):
    """Structured CV data from LLM."""
    name: str
    email: str
    phone: str
    location: str
    summary: str
    experience: list[dict]
    skills: str
    education: str


class RunSummary(BaseModel):
    """Run summary statistics."""
    started_at: str
    finished_at: str
    jobs_found: int
    jobs_filtered: int
    jobs_qualified: int
    drafts_created: int
    errors: list[str]
