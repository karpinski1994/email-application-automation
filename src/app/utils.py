"""Utilities for Email Application Automation."""

import json
from pathlib import Path
from typing import Any


# Constants
DATA_DIR = Path("data")


def is_cached(path: Path) -> bool:
    """Check if a cache file exists and is not empty."""
    return path.exists() and path.stat().st_size > 0


def save_json(path: Path, data: list | dict) -> None:
    """Save data to JSON file with atomic write (temp + rename)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(".tmp")
    temp_path.write_text(json.dumps(data, indent=2, default=str))
    temp_path.rename(path)


def load_json(path: Path) -> list | dict:
    """Load data from JSON file."""
    return json.loads(path.read_text())


def ensure_data_dir() -> None:
    """Ensure data directory exists."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
