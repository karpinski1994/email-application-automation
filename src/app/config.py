"""Configuration loading for Email Application Automation."""

import os
import yaml
from pathlib import Path
from dotenv import load_dotenv
from .models import Config


def load_config(config_path: str = "config.yaml") -> Config:
    """Load configuration from YAML file and .env."""
    load_dotenv()
    
    config_file = Path(config_path)
    if not config_file.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    
    with open(config_file) as f:
        raw = yaml.safe_load(f)
    
    if "apify" in raw and "api_token" in raw["apify"]:
        raw["apify"]["api_token"] = os.getenv("APIFY_API_KEY", raw["apify"].get("api_token", ""))
    
    if "email_finder" in raw and "api_key" in raw["email_finder"]:
        raw["email_finder"]["api_key"] = os.getenv("ANYMAILFINDER_API_KEY", raw["email_finder"].get("api_key", ""))
    
    return Config(**raw)


def get_api_key(key: str) -> str:
    """Get API key from environment variable."""
    return os.getenv(key, "")
