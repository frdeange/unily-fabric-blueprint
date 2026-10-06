"""Enforce a small repository allowlist and reject common credential artifacts."""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALLOWED_ROOT_FILES = {"README.md", ".gitignore"}
ALLOWED_DIRECTORIES = {"src", "tests", "tools", "fabric", ".github"}
PATTERNS = [
    re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}\b"),
    re.compile(r"(?i)AccountKey=[A-Za-z0-9+/]{20,}"),
]
EXCLUDED = {".git", "__pycache__", ".venv", ".pytest_cache"}
GUID = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I)
EXAMPLE_GUIDS = {f"00000000-0000-4000-8000-{i:012d}" for i in range(1, 8)}


def main():
    for path in ROOT.rglob("*"):
        relative = path.relative_to(ROOT)
        if any(part in EXCLUDED for part in relative.parts) or not path.is_file():
            continue
        if len(relative.parts) == 1:
            if relative.name not in ALLOWED_ROOT_FILES:
                raise ValueError(f"Unexpected root file: {relative}")
        elif relative.parts[0] not in ALLOWED_DIRECTORIES:
            raise ValueError(f"Unexpected directory: {relative}")
        if any(word in path.name.lower() for word in ("password", "credential", "evidence")):
            raise ValueError(f"Sensitive artifact filename: {relative}")
        text = path.read_text(encoding="utf-8")
        if any(value.lower() not in EXAMPLE_GUIDS for value in GUID.findall(text)):
            raise ValueError(f"Non-example identifier detected: {relative}")
        if any(pattern.search(text) for pattern in PATTERNS):
            raise ValueError(f"Potential credential detected: {relative}")
        if path.suffix == ".ipynb":
            notebook = json.loads(text)
            for cell in notebook["cells"]:
                if cell.get("outputs") or cell.get("execution_count") is not None:
                    raise ValueError(f"Notebook execution output detected: {relative}")
    items = {p.name for p in (ROOT / "fabric").iterdir()}
    if items != {"ProductAnalytics_Build.Notebook", "ProductAnalytics_BronzeToSilver.Notebook"}:
        raise ValueError("Unexpected Fabric deployment scope")
    print("Repository scope and basic credential/output guards passed.")


if __name__ == "__main__":
    main()
