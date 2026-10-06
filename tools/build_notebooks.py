"""Generate notebook code from sources without invoking Fabric or the detector."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "product_analytics"))
import build_product_analytics


def code_sections():
    source = ROOT / "src" / "product_analytics"
    config = (
        (source / "runtime_config.py").read_text(encoding="utf-8")
        + "\nimport notebookutils\nCONFIG = load_runtime_config(notebookutils)\n"
        + 'print("Runtime configuration validated; values are not printed.")\n'
    )
    silver = (source / "silver_phase.py").read_text(encoding="utf-8")
    validation, processing, publication = silver.split("with audit_failure():\n")
    generator = build_product_analytics.notebook_source()
    fixture, _ = generator.split(build_product_analytics.SPARK_SOURCE)
    return {
        "ProductAnalytics_Build": [
            ("Configuration and validation", config),
            ("Versioned synthetic fixture", fixture),
            ("RAW publication and summary", build_product_analytics.SPARK_SOURCE),
        ],
        "ProductAnalytics_BronzeToSilver": [
            ("Configuration and validation", config),
            ("Phase 1 - Tenant-scoped identity resolution",
             (source / "identity_phase.py").read_text(encoding="utf-8")),
            ("Phase 2 - Event validation and batch reuse",
             (source / "pii_ai_functions.py").read_text(encoding="utf-8") + validation),
            ("Phase 3 - PII extraction and exact-span protection",
             "with audit_failure():\n" + processing),
            ("Phase 4 - Silver publication and summary",
             "with audit_failure():\n" + publication),
        ],
    }

DESCRIPTIONS = {
    "Configuration and validation": (
        "Read the active values from `ProductAnalytics_Config`. Validate environment "
        "IDs, the source registry and PII settings before any data access. Missing or "
        "example configuration fails explicitly; no fallback is used."
    ),
    "Versioned synthetic fixture": (
        "Define the deterministic English-only A/B/C test fixture. This is test data, "
        "not an ingestion connector. Source table names come from the validated registry."
    ),
    "RAW publication and summary": (
        "Requires explicit `allow_synthetic_overwrite=true` and the exact A/B/C tenant "
        "set before writing. Overwrites synthetic RAW inputs only; never run as part of deployment."
    ),
    "Phase 1 - Tenant-scoped identity resolution": (
        "Read registered user tables and create UUID keys only for new "
        "(tenant_id, source_user_id) pairs. Preserve existing keys. One user namespace "
        "per tenant and a single manually launched writer are supported."
    ),
    "Phase 2 - Event validation and batch reuse": (
        "Read registered event tables, validate schemas and resolve every user against "
        "the mapping. An unchanged completed batch skips inference and publication. "
        "Unresolved users hold the whole batch; populated Silver is not overwritten."
    ),
    "Phase 3 - PII extraction and exact-span protection": (
        "Use Fabric AI Functions to extract literal PII spans, then mask in code. "
        "Preserve null and empty text. Validate the entire staged batch before "
        "publication. `processed` is not a guarantee that text contains no remaining PII."
    ),
    "Phase 4 - Silver publication and summary": (
        "Append the validated batch, verify persisted rows and write the completion "
        "marker to Identity storage. Errors are audited and raised. Publication and "
        "the audit marker are not a single atomic transaction; recovery is manual."
    ),
}


def sources():
    return {name: "\n".join(code for _, code in sections)
            for name, sections in code_sections().items()}


def notebook_cells(name, sections):
    cells = [{
        "cell_type": "markdown", "id": "overview", "metadata": {},
        "source": [f"# {name}\n", "\n",
                   "Run cells in order. Deployment never executes this notebook. "
                   "Use the lab user's runtime identity; Variable Library reads with "
                   "service principals are not currently supported.\n"],
    }]
    for index, (title, code) in enumerate(sections, 1):
        compile(code, f"{name}:{title}", "exec")
        cells.extend([
            {"cell_type": "markdown", "id": f"phase-{index}-description", "metadata": {},
             "source": [f"## {title}\n", "\n", DESCRIPTIONS[title] + "\n"]},
            {"cell_type": "code", "id": f"phase-{index}-code", "execution_count": None,
             "outputs": [], "metadata": {"microsoft": {
                 "language": "python", "language_group": "synapse_pyspark"}},
             "source": code.splitlines(keepends=True)},
        ])
    return cells


def build(check=False):
    for name, sections in code_sections().items():
        path = ROOT / "fabric" / "product-analytics" / "notebooks" / f"{name}.Notebook" / "notebook-content.ipynb"
        notebook = json.loads(path.read_text(encoding="utf-8"))
        expected = notebook_cells(name, sections)
        if check:
            if notebook["cells"] != expected or "dependencies" in notebook["metadata"]:
                raise ValueError(f"Source and generated notebook differ: {name}")
        else:
            notebook["cells"] = expected
            # All data access uses validated absolute paths, not a default lakehouse.
            notebook["metadata"].pop("dependencies", None)
            path.write_text(json.dumps(notebook, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print("Notebook source consistency verified." if check else "Notebook code cells rebuilt.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    build(parser.parse_args().check)
