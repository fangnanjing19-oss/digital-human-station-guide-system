from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {
    ".git",
    ".git_evidence",
    ".idea",
    "__pycache__",
    "audio_cache",
    "raw_pdfs",
    ".venv",
    "venv",
}
SKIP_SUFFIXES = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".mp3",
    ".pdf",
    ".pyc",
}
SKIP_FILES = {
    Path(".streamlit/secrets.toml"),
}

PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_\-]{20,}"),
    re.compile(r"moonshot-[A-Za-z0-9_\-]{16,}", re.IGNORECASE),
    re.compile(r"(api[_-]?key|secret|token)\s*=\s*[\"'][^\"']{12,}[\"']", re.IGNORECASE),
]
PLACEHOLDER_MARKERS = (
    "你的",
    "your",
    "example",
    "MOONSHOT_API_KEY = \"\"",
)


def should_scan(path: Path) -> bool:
    rel = path.relative_to(ROOT)
    if rel in SKIP_FILES:
        return False
    if any(part in SKIP_DIRS for part in rel.parts):
        return False
    if path.suffix.lower() in SKIP_SUFFIXES:
        return False
    return path.is_file()


def main() -> int:
    hits: list[str] = []
    for path in ROOT.rglob("*"):
        if not should_scan(path):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for line_no, line in enumerate(text.splitlines(), start=1):
            if any(marker.lower() in line.lower() for marker in PLACEHOLDER_MARKERS):
                continue
            if any(pattern.search(line) for pattern in PATTERNS):
                hits.append(f"{path.relative_to(ROOT)}:{line_no}")

    if hits:
        print("Potential secret values found:")
        for hit in hits:
            print(f"- {hit}")
        print("Review these lines before committing.")
        return 1

    print("No obvious API keys or secrets found in scanned project files.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
