"""Check that each API key in .env authenticates, with one cheap read-only call per service.

Run: bash scripts/uv-run.sh python scripts/check_keys.py
Exits non-zero if any key that is set fails. Unset keys are listed, not tested.
"""

import os
import sys

import anthropic
import httpx
from retell import Retell

from dualuse import config  # noqa: F401  (loads .env)


def check_anthropic(key: str) -> None:
    anthropic.Anthropic(api_key=key).models.list(limit=1)


def check_retell(key: str) -> None:
    Retell(api_key=key).agent.list()


def check_terminal49(key: str) -> None:
    httpx.get(
        "https://api.terminal49.com/v2/shipments",
        headers={"Authorization": f"Token {key}", "Content-Type": "application/vnd.api+json"},
        timeout=15,
    ).raise_for_status()


def check_openrouter(key: str) -> None:
    # Reads the key's own record; spends no credits.
    httpx.get("https://openrouter.ai/api/v1/key", headers={"Authorization": f"Bearer {key}"}, timeout=15).raise_for_status()


CHECKS = {
    "ANTHROPIC_API_KEY": check_anthropic,
    "RETELL_API_KEY": check_retell,
    "TERMINAL49_API_KEY": check_terminal49,
    "OPENROUTER_API_KEY": check_openrouter,
}

failed = False
for name, check in CHECKS.items():
    key = os.environ.get(name)
    if not key:
        print(f"{name}: not set")
        continue
    try:
        check(key)
    except Exception as error:  # report every service, then fail
        failed = True
        print(f"{name}: FAILED ({type(error).__name__}: {error})")
    else:
        print(f"{name}: ok")
sys.exit(1 if failed else 0)
