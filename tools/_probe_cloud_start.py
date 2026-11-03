"""Start the app the way a host would: from an unrelated working directory.

Streamlit Community Cloud runs the main file by path, not from the repo root.
Locally everything works because the shell is already in the repo, which hides a
missing `import app` path entry until deploy day. This starts the real server
from C:\\Windows\\Temp (or the OS temp dir), waits for it, fetches the page, and
reports the HTTP status plus whether the log contains a traceback.

Uses port 8599 and a temp dir, so it does not disturb the server on 8501.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PORT = 8599

cmd = [
    str(ROOT / ".venv" / "Scripts" / "streamlit.exe"),
    "run",
    str(ROOT / "app" / "web" / "streamlit_app.py"),
    "--server.headless",
    "true",
    "--server.port",
    str(PORT),
    "--browser.gatherUsageStats",
    "false",
]

log_path = Path(tempfile.gettempdir()) / "cr_cloud_sim.log"
with open(log_path, "w", encoding="utf-8", errors="replace") as log:
    proc = subprocess.Popen(
        cmd,
        cwd=tempfile.gettempdir(),  # deliberately NOT the repo root
        stdout=log,
        stderr=subprocess.STDOUT,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )

status = None
try:
    deadline = time.time() + 90
    while time.time() < deadline:
        if proc.poll() is not None:
            break
        try:
            with urllib.request.urlopen(f"http://localhost:{PORT}/", timeout=5) as response:
                status = response.status
                body = response.read().decode("utf-8", "replace")
                break
        except (urllib.error.URLError, ConnectionError, TimeoutError):
            time.sleep(2)
finally:
    proc.terminate()
    try:
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        proc.kill()

text = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""
print("working directory :", tempfile.gettempdir())
print("http status       :", status)
print("module error      :", "No module named 'app'" in text or "ModuleNotFoundError" in text)
print("traceback in log  :", "Traceback (most recent call last)" in text)
print("page served html  :", bool(status == 200 and "streamlit" in body.lower()))

if "ModuleNotFoundError" in text:
    for line in text.splitlines():
        if "Error" in line:
            print("  ", line.strip()[:160])

ok = status == 200 and "ModuleNotFoundError" not in text
print("\n" + ("READY: starts from any directory" if ok else "PROBLEM: see the log above"))
print("log:", log_path)
sys.exit(0 if ok else 1)
