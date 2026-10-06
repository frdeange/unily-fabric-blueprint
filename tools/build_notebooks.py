"""Generate notebook code from sources without invoking Fabric or the detector."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "product_analytics"))
import build_product_analytics


def sources():
    source = ROOT / "src" / "product_analytics"
    return {
        "ProductAnalytics_Build": build_product_analytics.notebook_source(),
        "ProductAnalytics_BronzeToSilver": (
            "# Phase 1: Create or reuse tenant-scoped pseudonymous identities.\n"
            + (source / "identity_phase.py").read_text(encoding="utf-8")
            + "\n# Phase 2: Transform events and protect free text before Silver publication.\n"
            + (source / "pii_ai_functions.py").read_text(encoding="utf-8")
            + (source / "silver_phase.py").read_text(encoding="utf-8")
        ),
    }


def build(check=False):
    for name, source in sources().items():
        compile(source, name, "exec")
        path = ROOT / "fabric" / "product-analytics" / "notebooks" / f"{name}.Notebook" / "notebook-content.ipynb"
        notebook = json.loads(path.read_text(encoding="utf-8"))
        cells = [cell for cell in notebook["cells"] if cell["cell_type"] == "code"]
        if len(cells) != 1:
            raise ValueError("Baseline builder expects one code cell per notebook")
        cell = cells[0]
        if check:
            if "".join(cell["source"]) != source:
                raise ValueError(f"Source and generated notebook differ: {name}")
        else:
            cell["source"] = source.splitlines(keepends=True)
            cell["execution_count"] = None
            cell["outputs"] = []
            path.write_text(json.dumps(notebook, indent=1) + "\n", encoding="utf-8")
    print("Notebook source consistency verified." if check else "Notebook code cells rebuilt.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    build(parser.parse_args().check)
