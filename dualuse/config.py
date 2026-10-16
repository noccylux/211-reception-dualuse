"""Secrets and settings, read from the environment and from `.env` at the repository root."""

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def require(name: str) -> str:
    """Return a required setting, or fail with a message naming the missing variable."""
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{name} is not set; add it to .env (see .env.example)")
    return value
