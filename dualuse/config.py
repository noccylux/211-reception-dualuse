"""Secrets and settings, read from the environment and from `.env` at the repository root."""

import os
from collections.abc import MutableMapping
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent.parent


def load_env(path: Path, environ: MutableMapping[str, str] = os.environ) -> None:
    """Fill settings that are missing or empty from `.env`; a non-empty real variable wins.

    load_dotenv treats an empty variable as set. WSLENV forwards a Windows variable that the
    launching process lacks as an empty one, which would hide the key in `.env`.
    """
    for name, value in dotenv_values(path).items():
        if value and not environ.get(name):
            environ[name] = value


load_env(ROOT / ".env")


def require(name: str) -> str:
    """Return a required setting, or fail with a message naming the missing variable."""
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{name} is not set; add it to .env (see .env.example)")
    return value
