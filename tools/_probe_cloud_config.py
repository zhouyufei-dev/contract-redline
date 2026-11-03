"""Simulate the deployed environment: no .env, keys only in Streamlit secrets.

Writes a throwaway .streamlit/secrets.toml with obviously fake values, imports
streamlit the way the web app does, and asks app/config.py what it sees. Deletes
the file afterwards whether or not the check passes - the real file is
git-ignored, but leaving a fake one behind would be confusing.

Nothing here touches .env and nothing prints a real key.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

SECRETS = ROOT / ".streamlit" / "secrets.toml"
if SECRETS.exists():
    print("a real secrets.toml exists here - refusing to overwrite it")
    sys.exit(2)

SECRETS.write_text(
    'DEEPSEEK_API_KEY = "sk-fake-for-the-check"\n'
    'STRIPE_SECRET_KEY = "sk_test_fake_for_the_check"\n'
    'STRIPE_PAYMENT_URL = "https://buy.stripe.com/test_fake"\n',
    encoding="utf-8",
)

try:
    import streamlit  # noqa: F401 - the web app imports this too

    from app import config

    file_values = config.parse_env_file(config.ENV_FILE)
    secret_values = config.parse_streamlit_secrets()
    process_values = {k: v for k, v in os.environ.items() if k.startswith(config.SECRET_PREFIXES)}
    print("  from .env   :", len(file_values.get("DEEPSEEK_API_KEY", "")), "chars")
    print("  from secrets:", len(secret_values.get("DEEPSEEK_API_KEY", "")), "chars")
    print("  from environ:", len(process_values.get("DEEPSEEK_API_KEY", "")), "chars")

    config.get_settings.cache_clear()
    settings = config.get_settings()

    print("no .env in play, secrets.toml present:")
    print("  api key  :", "read" if settings.api_key == "sk-fake-for-the-check" else f"WRONG ({len(settings.api_key)} chars)")
    print("  stripe   :", "read" if settings.stripe_secret_key == "sk_test_fake_for_the_check" else "WRONG")
    print("  pay link :", settings.payment_url)
    print("  describe :", settings.describe())

    ok = (
        settings.api_key == "sk-fake-for-the-check"
        and settings.stripe_secret_key == "sk_test_fake_for_the_check"
        and settings.payment_url == "https://buy.stripe.com/test_fake"
    )
    print("\n" + ("READY: the deployed shape resolves its keys" if ok else "PROBLEM"))
finally:
    SECRETS.unlink(missing_ok=True)
    print("throwaway secrets.toml removed")

sys.exit(0 if ok else 1)
