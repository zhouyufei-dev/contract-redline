"""Configuration comes from the right place, in the right order.

The deployed site has no .env (it is git-ignored), so if the secrets branch of
app/config.py is wrong the site still loads - it just silently loses its API key
and its Stripe key. That failure looks like "explanations are boring" and
"payments never unlock", which is exactly the kind of thing that would survive a
smoke test. So it is tested here instead.

Run:  .\.venv\Scripts\python.exe tools\test_config.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import config  # noqa: E402

passed = 0
failed = 0


def check(label: str, condition: bool, detail: str = "") -> None:
    global passed, failed
    if condition:
        passed += 1
    else:
        failed += 1
        print(f"  FAIL  {label}" + (f"  [{detail}]" if detail else ""))


print("1. precedence")
merged = config.merge_sources(
    file_values={"DEEPSEEK_API_KEY": "from-file", "STRIPE_PAYMENT_URL": "from-file"},
    environ={"DEEPSEEK_API_KEY": "from-env"},
    secret_values={"DEEPSEEK_API_KEY": "from-secret", "STRIPE_SECRET_KEY": "sk_test_secret"},
)
check("process env beats the file", merged["DEEPSEEK_API_KEY"] == "from-env", merged["DEEPSEEK_API_KEY"])
check("secrets fill what the file lacks", merged["STRIPE_SECRET_KEY"] == "sk_test_secret")
check("a file value survives when nothing else sets it",
      merged["STRIPE_PAYMENT_URL"] == "from-file", merged["STRIPE_PAYMENT_URL"])

# The deployed runtime must always win over a .env left on disk: a stale local
# file shadowing a Cloud secret would be invisible and very hard to diagnose.
overlap = config.merge_sources(
    {"STRIPE_SECRET_KEY": "sk_test_from_file"}, {}, {"STRIPE_SECRET_KEY": "sk_test_from_secret"}
)
check("secrets beat the file on the same key",
      overlap["STRIPE_SECRET_KEY"] == "sk_test_from_secret", overlap["STRIPE_SECRET_KEY"])
check("process env beats secrets too",
      config.merge_sources({}, {"DEEPSEEK_API_KEY": "env"}, {"DEEPSEEK_API_KEY": "secret"})
      ["DEEPSEEK_API_KEY"] == "env")

print("2. a deployed site with no .env still gets its keys")
only_secrets = config.merge_sources(
    file_values={},
    environ={},
    secret_values={"DEEPSEEK_API_KEY": "sk-deep", "STRIPE_SECRET_KEY": "sk_test_x"},
)
check("api key arrives from secrets", only_secrets.get("DEEPSEEK_API_KEY") == "sk-deep")
check("stripe key arrives from secrets", only_secrets.get("STRIPE_SECRET_KEY") == "sk_test_x")

print("3. unrelated environment variables are ignored")
merged = config.merge_sources({}, {"PATH": "/usr/bin", "DEEPSEEK_API_KEY": "k"}, {})
check("PATH is not copied in", "PATH" not in merged, str(merged))
check("only the two prefixes pass", set(merged) == {"DEEPSEEK_API_KEY"}, str(set(merged)))

print("4. a missing secrets file is not an error")
check("no streamlit imported -> no secrets, no crash", config.parse_streamlit_secrets() == {})

print("5. secrets are read when Streamlit is running")
import types  # noqa: E402


class _FakeSecrets(dict):
    """Looks like streamlit's Secrets: iterable, subscriptable, no .get order."""


fake = types.ModuleType("streamlit")
fake.secrets = _FakeSecrets({"DEEPSEEK_API_KEY": "sk-deep", "STRIPE_SECRET_KEY": "sk_test_y",
                            "SOMETHING_ELSE": "ignore-me"})
sys.modules["streamlit"] = fake
try:
    got = config.parse_streamlit_secrets()
    check("secret api key is read", got.get("DEEPSEEK_API_KEY") == "sk-deep", str(got))
    check("secret stripe key is read", got.get("STRIPE_SECRET_KEY") == "sk_test_y", str(got))
    check("unrelated secrets are not copied", "SOMETHING_ELSE" not in got, str(got))
finally:
    sys.modules.pop("streamlit", None)

print("6. the real settings still load")
settings = config.get_settings()
check("settings object builds", isinstance(settings, config.Settings))
check("describe() leaks no key material", "sk-" not in settings.describe(), settings.describe())
check("describe() reports stripe presence", "stripe_key=" in settings.describe(), settings.describe())

print()
print(f"{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
