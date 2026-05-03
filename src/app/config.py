"""Configuration loading for Email Application Automation."""

import os
import yaml
from pathlib import Path
from dotenv import load_dotenv
from .models import Config


def load_config(config_path: str = "config.yaml") -> Config:
    """Load configuration from YAML file and .env."""
    # Load .env variables
    load_dotenv()
    
    # Load config.yaml
    config_file = Path(config_path)
    if not config_file.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    
    with open(config_file) as f:
        raw = yaml.safe_load(f)
    
    return Config(**raw)


def get_api_key(key: str) -> str:
    """Get API key from environment variable."""
    return os.getenv(key, "")
