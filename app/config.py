"""Central configuration — the ONLY place in this project that reads .env.

Rule for the whole codebase: no API key is ever hardcoded, and no other module
calls os.environ directly. Everything goes through here.

Why no python-dotenv: the format we need is `KEY=VALUE`, one per line, with `#`
comments. That is 20 lines of code. A dependency buys nothing here, and every
dependency is one more thing that can break on a beginner's machine.

Exports:
    Settings.api_key      <- DEEPSEEK_API_KEY   (never printed, never logged)
    Settings.base_url     <- DEEPSEEK_BASE_URL  (default https://api.deepseek.com)
    Settings.model        <- DEEPSEEK_MODEL     (default deepseek-chat)
    Settings.stripe_secret_key <- STRIPE_SECRET_KEY (only used to verify a
                                  Checkout Session; never printed or logged)
    Settings.payment_url  <- STRIPE_PAYMENT_URL (optional; a Stripe Payment Link
                                  override, so test mode and live mode can be
                                  switched from .env instead of from code)

Where the values come from, lowest precedence first:

    1. .env                  (local development; git-ignored)
    2. Streamlit secrets     (app/web/* deployed on Streamlit Cloud)
    3. process environment   ($env:DEEPSEEK_API_KEY=... for a one-off run)

Sources 2 and 3 both override .env. That is deliberate: an explicitly configured
runtime must never be silently shadowed by a file left over on disk. In practice
Streamlit also copies secrets into ``os.environ``, so the two upper sources agree
with each other - the st.secrets branch is kept because that mirroring is a
Streamlit implementation detail, and a deployed app that loses its key because a
future version stopped mirroring would be an outage with no error message.

Without source 2 the deployed site still loads; it just silently loses its
DeepSeek key and its Stripe key, so explanations fall back to rule text and no
payment can ever be verified. That is the failure this exists to prevent.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / ".env"

DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-chat"


class ConfigError(RuntimeError):
    """Raised when the project is not configured well enough to call the API."""


def parse_env_file(path: Path) -> dict[str, str]:
    """Read a .env file. Missing file is not an error (returns {})."""
    values: dict[str, str] = {}
    if not path.exists():
        return values

    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.lower().startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        # Strip one layer of matching quotes: KEY="sk-..."
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key.strip()] = value
    return values


@dataclass(frozen=True)
class Settings:
    api_key: str
    base_url: str = DEFAULT_BASE_URL
    model: str = DEFAULT_MODEL
    timeout: float = 60.0
    max_retries: int = 3
    temperature: float = 0.2
    max_workers: int = 4
    # "sk_test_..." while testing, "sk_live_..." once real money moves. Empty
    # means payments cannot be verified, which app/billing.py reports to the
    # customer instead of guessing.
    stripe_secret_key: str = ""
    # A Stripe Payment Link is public: it is meant to be pasted on a page, so
    # this is not a secret. It lives here anyway so that the test-mode link and
    # the live-mode link are one line apart in .env, and nobody has to edit
    # app/site.py (and risk forgetting) on the day the product goes live.
    payment_url: str = ""

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    @property
    def payments_configured(self) -> bool:
        return bool(self.stripe_secret_key)

    @property
    def endpoint(self) -> str:
        base = self.base_url.rstrip("/")
        if base.endswith("/chat/completions"):
            return base
        return f"{base}/chat/completions"

    def describe(self) -> str:
        """Safe one-liner for logs/screens. Contains NO part of the key."""
        if not self.api_key:
            key_state = "missing"
        else:
            key_state = f"set ({len(self.api_key)} chars)"
        pay_state = "set" if self.stripe_secret_key else "missing"
        return (
            f"model={self.model}  endpoint={self.endpoint}  "
            f"key={key_state}  stripe_key={pay_state}  timeout={self.timeout:g}s"
        )


def _float(env: dict[str, str], key: str, default: float) -> float:
    try:
        return float(env[key])
    except (KeyError, TypeError, ValueError):
        return default


def _int(env: dict[str, str], key: str, default: int) -> int:
    try:
        return int(env[key])
    except (KeyError, TypeError, ValueError):
        return default


SECRET_PREFIXES = ("DEEPSEEK_", "STRIPE_")


def parse_streamlit_secrets() -> dict[str, str]:
    """Read Streamlit Cloud secrets, if this process is a Streamlit app.

    Only looks at Streamlit if it is already imported. Importing it here would
    cost every command-line tool a couple of seconds and a "missing
    ScriptRunContext" warning for nothing - and if Streamlit is not imported,
    there are no secrets to read either.

    Deliberately silent about failure too. Two normal situations reach the
    except branch and neither is an error: a local run has no secrets.toml, and
    Streamlit raises its own exception type for the missing file. Both mean
    "there are no secrets, carry on with .env".
    """
    if "streamlit" not in sys.modules:
        return {}
    try:
        store = sys.modules["streamlit"].secrets
        return {key: str(store[key]) for key in store if key.startswith(SECRET_PREFIXES)}
    except Exception:  # noqa: BLE001 - any failure means "no secrets available"
        return {}


def merge_sources(
    file_values: dict[str, str],
    environ: dict[str, str],
    secret_values: dict[str, str],
) -> dict[str, str]:
    """Combine the three sources. Later entries win.

    Split out from get_settings so the precedence rule can be tested without a
    Streamlit runtime or a real secrets file.
    """
    process = {k: v for k, v in environ.items() if k.startswith(SECRET_PREFIXES)}
    return {**file_values, **secret_values, **process}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Load configuration once per process.

    Precedence: process environment > Streamlit secrets > .env. See the module
    docstring for why the upper two exist.
    """
    merged = merge_sources(
        parse_env_file(ENV_FILE), os.environ, parse_streamlit_secrets()
    )

    return Settings(
        api_key=merged.get("DEEPSEEK_API_KEY", "").strip(),
        base_url=(merged.get("DEEPSEEK_BASE_URL") or DEFAULT_BASE_URL).strip(),
        model=(merged.get("DEEPSEEK_MODEL") or DEFAULT_MODEL).strip(),
        timeout=_float(merged, "DEEPSEEK_TIMEOUT", 60.0),
        max_retries=_int(merged, "DEEPSEEK_MAX_RETRIES", 3),
        temperature=_float(merged, "DEEPSEEK_TEMPERATURE", 0.2),
        max_workers=_int(merged, "DEEPSEEK_MAX_WORKERS", 4),
        stripe_secret_key=merged.get("STRIPE_SECRET_KEY", "").strip(),
        payment_url=merged.get("STRIPE_PAYMENT_URL", "").strip(),
    )


def require_settings() -> Settings:
    settings = get_settings()
    if not settings.api_key:
        raise ConfigError(
            "DEEPSEEK_API_KEY is not set.\n"
            f"Open {ENV_FILE} and add a line:\n"
            "    DEEPSEEK_API_KEY=sk-...\n"
            "The rule engine works without it; only explanations need the key."
        )
    return settings
