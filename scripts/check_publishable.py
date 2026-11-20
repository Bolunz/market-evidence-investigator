"""Pre-publication check. Run before every push: `python scripts/check_publishable.py`.

Fails if tracked files contain credentials, private data paths, restricted-source references,
or social-media personal identifiers. Exit code 0 = safe to push.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

FORBIDDEN_PATHS = [re.compile(p) for p in (r"(^|/)\.env$", r"(^|/)\.env\.(?!example$)", r"^data/private/",
                                           r"^data/real/", r"^runs/real/", r"^cache/real/")]
FORBIDDEN_CONTENT = {
    "Anthropic API key": re.compile(r"sk-ant-[A-Za-z0-9_\-]{12,}"),
    "API key assignment": re.compile(r"ANTHROPIC_API_KEY\s*=\s*['\"]?[A-Za-z0-9_\-]{12,}"),
    "internal cube reference": re.compile(r"MI_CUBE|CUBE[_ ]Data[_ ]Structure", re.I),
    "licensed panel provider name": re.compile(r"\b(Circana|GfK|NPD Group)\b"),
    "YouTube comment/video URL": re.compile(r"youtube\.com/(watch|channel)|youtu\.be/"),
}
DATA_ONLY = {   # checks applied to data files (csv/json/jsonl) only
    "social handle": re.compile(r"(?<![\w.])@[A-Za-z][A-Za-z0-9_.\-]{2,}"),
}
SKIP = {"scripts/check_publishable.py"}
MAX_BYTES = 10 * 1024 * 1024


def tracked_files() -> list[str]:
    out = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"], cwd=ROOT,
                         capture_output=True, text=True, check=True).stdout
    return [f for f in out.splitlines() if f]


def main() -> int:
    problems = []
    for f in tracked_files():
        if f in SKIP:
            continue
        if any(p.search(f) for p in FORBIDDEN_PATHS):
            problems.append(f"forbidden path staged/tracked: {f}")
            continue
        path = ROOT / f
        if not path.is_file():
            continue
        if path.stat().st_size > MAX_BYTES:
            problems.append(f"file larger than 10 MB: {f}")
        try:
            text = path.read_text(errors="ignore")
        except OSError:
            continue
        for label, pat in FORBIDDEN_CONTENT.items():
            m = pat.search(text)
            if m:
                problems.append(f"{label} in {f}: '{m.group(0)[:40]}'")
        if f.endswith((".csv", ".json", ".jsonl")):
            for label, pat in DATA_ONLY.items():
                m = pat.search(text)
                if m:
                    problems.append(f"{label} in data file {f}: '{m.group(0)}'")
    if problems:
        print("NOT SAFE TO PUBLISH:")
        for p in problems:
            print(" -", p)
        return 1
    print(f"OK: {len(tracked_files())} files checked; no credentials, private data or restricted references found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
