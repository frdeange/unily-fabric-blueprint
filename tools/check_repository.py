"""Enforce a small repository allowlist and reject common credential artifacts."""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALLOWED_ROOT_FILES = {"README.md", ".gitignore", ".pre-commit-config.yaml", "requirements-dev.txt", "requirements-deploy.txt"}
ALLOWED_DIRECTORIES = {"src", "tests", "tools", "fabric", ".github", "config", "docs"}
PATTERNS = [
    re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}\b"),
    re.compile(r"(?i)AccountKey=[A-Za-z0-9+/]{20,}"),
]
EXCLUDED = {".git", "__pycache__", ".venv", ".pytest_cache"}
GUID = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I)
# Example logical IDs plus fabric-cicd's workspace placeholder in pipeline references.
EXAMPLE_GUIDS = {f"00000000-0000-4000-8000-{i:012d}" for i in range(1, 20)} | {"00000000-0000-0000-0000-000000000000"}

EXPECTED_ITEMS = {
    Path("data") / "product-analytics" / "notebooks" / f"{name}.Notebook"
    for name in ("ProductAnalytics_Build", "ProductAnalytics_BronzeToSilver", "ProductAnalytics_SilverToGold")
} | {
    Path("data") / "product-analytics" / "pipelines" / f"{name}.DataPipeline"
    for name in ("ProductAnalytics_SilverPipeline", "ProductAnalytics_GoldPipeline", "ProductAnalytics_Demo")
} | {
    Path("data") / "product-analytics" / "variable-libraries" / "ProductAnalytics_Config.VariableLibrary",
    Path("vault") / "shared" / "lakehouses" / "Identity.Lakehouse",
} | {Path("data") / "shared" / "lakehouses" / f"{name}.Lakehouse" for name in ("Bronze", "Silver", "Gold")} | {
    Path("analytics") / "product-analytics" / "semantic-models" / "ProductAnalytics_Safe.SemanticModel",
    Path("analytics") / "product-analytics" / "data-agents" / "ProductAnalytics_Safe_Agent.DataAgent",
}


def check_fabric_scope(root):
    fabric = root / "fabric"
    items = {path.parent.relative_to(fabric) for path in fabric.rglob(".platform")}
    if items != EXPECTED_ITEMS:
        raise ValueError("Unexpected Fabric deployment scope")
    for path in fabric.rglob("*"):
        if path.is_file():
            relative = path.relative_to(fabric)
            if not any(item in relative.parents for item in EXPECTED_ITEMS):
                raise ValueError(f"File outside allowed Fabric items: {relative}")


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
                if cell.get("attachments"):
                    raise ValueError(f"Notebook attachments detected: {relative}")
    check_fabric_scope(ROOT)
    print("Repository scope and basic credential/output guards passed.")


if __name__ == "__main__":
    main()
