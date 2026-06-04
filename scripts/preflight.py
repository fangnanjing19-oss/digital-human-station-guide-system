from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PY_FILES = [
    "app.py",
    "brain.py",
    "config.py",
    "guide_content.py",
    "stt.py",
    "voice.py",
    "scripts/check_secrets.py",
    "scripts/preflight.py",
]


def run_step(label: str, command: list[str]) -> int:
    print(f"\n== {label} ==")
    result = subprocess.run(command, cwd=ROOT, text=True)
    if result.returncode == 0:
        print(f"OK: {label}")
    else:
        print(f"FAILED: {label}")
    return result.returncode


def main() -> int:
    failures = 0

    failures += run_step("Secret scan", [sys.executable, "scripts/check_secrets.py"])
    failures += run_step("Python syntax check", [sys.executable, "-m", "py_compile", *PY_FILES])
    failures += run_step("Git whitespace check", ["git", "diff", "--check"])

    print("\n== API key tracking check ==")
    tracked_secret = subprocess.run(
        ["git", "ls-files", ".streamlit/secrets.toml"],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    if tracked_secret.stdout.strip():
        print("FAILED: .streamlit/secrets.toml is tracked by Git.")
        failures += 1
    else:
        print("OK: .streamlit/secrets.toml is not tracked by Git.")

    print("\n== Git status ==")
    subprocess.run(["git", "status", "--short"], cwd=ROOT, text=True)

    if failures:
        print("\nPreflight failed. Review the messages above before committing.")
        return 1

    print("\nPreflight passed. You can review changes and commit locally when ready.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
