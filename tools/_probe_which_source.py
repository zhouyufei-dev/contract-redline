"""Why did the throwaway secret win over .env? Find out, without printing keys."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import config

print("ENV_FILE      :", config.ENV_FILE, "exists:", config.ENV_FILE.exists())
file_values = config.parse_env_file(config.ENV_FILE)
print("keys in .env  :", sorted(file_values))
print("api key length in .env:", len(file_values.get("DEEPSEEK_API_KEY", "")))
print()
print("process env has DEEPSEEK_API_KEY:", "DEEPSEEK_API_KEY" in os.environ)
print("process env has STRIPE_SECRET_KEY:", "STRIPE_SECRET_KEY" in os.environ)
print()
print("PROJECT_ROOT  :", config.PROJECT_ROOT)
print("cwd           :", Path.cwd())
