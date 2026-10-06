"""Generate notebook code and pipeline definitions from sources without invoking Fabric."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "product_analytics"))
import build_product_analytics
from runtime_config import FIELDS, LIBRARY_NAME

NOTEBOOKS = ROOT / "fabric" / "data" / "product-analytics" / "notebooks"
PIPELINES = ROOT / "fabric" / "data" / "product-analytics" / "pipelines"
# fabric-cicd replaces this placeholder with the target workspace at publication.
DEFAULT_WORKSPACE = "00000000-0000-0000-0000-000000000000"
BOOLEAN_FIELDS = {"allow_synthetic_overwrite"}


def code_sections():
    source = ROOT / "src" / "product_analytics"
    config = (
        (source / "runtime_config.py").read_text(encoding="utf-8")
        + "\nimport notebookutils\n"
        + "CONFIG = load_runtime_config(notebookutils, {name: globals().get(name) for name in FIELDS})\n"
        + 'print("Runtime configuration validated; values are not printed.")\n'
    )
    preflight = (
        (source / "validate_runtime.py").read_text(encoding="utf-8")
        + '\nif type(validate_only) is not bool:\n'
        + '    raise ValueError("validate_only must be a Boolean")\n'
        + 'if validate_only:\n'
        + '    print(json.dumps(validate_runtime(CONFIG, spark), indent=2))\n'
        + '    notebookutils.notebook.exit("Runtime validated; no processing or writes")\n'
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
            ("Read-only runtime validation", preflight),
            ("Phase 1 - Tenant-scoped identity resolution",
             (source / "identity_phase.py").read_text(encoding="utf-8")),
            ("Phase 2 - Event validation and batch reuse",
             (source / "pii_ai_functions.py").read_text(encoding="utf-8") + validation),
            ("Phase 3 - PII extraction and exact-span protection",
             "with audit_failure():\n" + processing),
            ("Phase 4 - Silver publication and summary",
             "with audit_failure():\n" + publication),
        ],
        "ProductAnalytics_SilverToGold": [
            ("Configuration and validation", config),
            ("Gold schema contract", (source / "gold_contract.py").read_text(encoding="utf-8")),
            ("Incremental Gold publication", (source / "gold_phase.py").read_text(encoding="utf-8")),
        ],
    }

DESCRIPTIONS = {
    "Read-only runtime validation": (
        "Set the Boolean notebook parameter `validate_only=true` for a read-only "
        "preflight. Validate Spark imports, input/output schemas, snapshot counts "
        "and stable Delta versions, then exit the entire notebook before processing. "
        "No AI inference, identity updates or audit writes. False continues normal processing."
    ),
    "Configuration and validation": (
        "Pipeline runs pass every `ProductAnalytics_Config` value as a parameter; "
        "interactive runs read the active value set directly. Validate environment "
        "IDs, the source registry and PII settings before any data access. Missing, partial or "
        "example configuration fails explicitly; no fallback is used."
    ),
    "Versioned synthetic fixture": (
        "Define the deterministic English-only A/B/C test fixture. This is test data, "
        "not an ingestion connector. Source table names come from the validated registry."
    ),
    "RAW publication and summary": (
        "Requires the exact A/B/C tenant set. Loads empty Bronze `product` tables once; "
        "replacing existing RAW requires explicit `allow_synthetic_overwrite=true`. "
        "Writes synthetic RAW inputs only; never run as part of deployment."
    ),
    "Phase 1 - Tenant-scoped identity resolution": (
        "Read registered Bronze user tables and write the mapping to the Vault workspace. "
        "Create UUID keys only for new "
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
    "Gold schema contract": (
        "Star schema published to Gold: one fact table and four dimensions. Every tenant-scoped "
        "table carries `tenant_id` for row-level security. Direct identifiers and raw text are "
        "forbidden; `feedback_text` holds only Silver text already protected by the PII step."
    ),
    "Incremental Gold publication": (
        "Read only the Silver changes since the last Gold watermark through the Delta Change "
        "Data Feed; the first run publishes the current Silver snapshot. MERGE on the contract "
        "keys keeps reruns idempotent. Exits without writes when Silver has not changed. "
        "Reads and writes the Data workspace only; never the Vault."
    ),
    "Phase 4 - Silver publication and summary": (
        "Append the validated batch to Silver, verify persisted rows and write the completion "
        "marker to restricted Vault storage. Errors are audited and raised. Publication and "
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
                   "Run through the `ProductAnalytics_Process` or `ProductAnalytics_Demo` "
                   "pipeline, or interactively with cells in order. Deployment never executes "
                   "this notebook.\n"],
    }]
    parameters = ["# Pipelines inject these values from ProductAnalytics_Config; keep None interactively.\n"]
    parameters += [f"{field} = None\n" for field in sorted(FIELDS)]
    if name == "ProductAnalytics_BronzeToSilver":
        parameters.append("validate_only = False\n")
    cells.append({
        "cell_type": "code", "execution_count": None, "id": "run-parameters",
        "metadata": {"tags": ["parameters"], "microsoft": {
            "language": "python", "language_group": "synapse_pyspark"}},
        "outputs": [], "source": parameters,
    })
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


def logical_id(folder):
    return json.loads((folder / ".platform").read_text(encoding="utf-8"))["config"]["logicalId"]


def expression(value, kind):
    return {"value": {"value": value, "type": "Expression"}, "type": kind}


def notebook_activity(name, notebook, depends_on=(), validate_only=None, timeout="0.01:00:00"):
    parameters = {
        field: expression(f"@pipeline().libraryVariables.{field}",
                          "bool" if field in BOOLEAN_FIELDS else "string")
        for field in sorted(FIELDS)
    }
    if validate_only is not None:
        parameters["validate_only"] = expression(f"@bool('{str(validate_only).lower()}')", "bool")
    return {
        "name": name, "type": "TridentNotebook",
        "dependsOn": [{"activity": d, "dependencyConditions": ["Succeeded"]} for d in depends_on],
        "policy": {"timeout": timeout, "retry": 0, "retryIntervalInSeconds": 30,
                   "secureOutput": True, "secureInput": True},
        "typeProperties": {
            "notebookId": logical_id(NOTEBOOKS / f"{notebook}.Notebook"),
            "workspaceId": DEFAULT_WORKSPACE, "parameters": parameters,
        },
    }


def pipelines():
    """Process is the production path; Demo adds the synthetic RAW load for reproduction."""
    library = {
        field: {"type": "Bool" if field in BOOLEAN_FIELDS else "String",
                "variableName": field, "libraryName": LIBRARY_NAME}
        for field in sorted(FIELDS)
    }
    process = [
        notebook_activity("Validate", "ProductAnalytics_BronzeToSilver", validate_only=True),
        notebook_activity("BronzeToSilver", "ProductAnalytics_BronzeToSilver", ("Validate",),
                          validate_only=False, timeout="0.04:00:00"),
        notebook_activity("SilverToGold", "ProductAnalytics_SilverToGold", ("BronzeToSilver",)),
    ]
    demo = [
        notebook_activity("Build", "ProductAnalytics_Build"),
        {
            "name": "Process", "type": "ExecutePipeline",
            "dependsOn": [{"activity": "Build", "dependencyConditions": ["Succeeded"]}],
            "policy": {"secureInput": True},
            "typeProperties": {
                "pipeline": {"referenceName": logical_id(PIPELINES / "ProductAnalytics_Process.DataPipeline"),
                             "type": "PipelineReference"},
                "waitOnCompletion": True,
            },
        },
    ]
    return {name: {"properties": {"activities": activities, "libraryVariables": library}}
            for name, activities in (("ProductAnalytics_Process", process), ("ProductAnalytics_Demo", demo))}


def build(check=False):
    for name, sections in code_sections().items():
        path = NOTEBOOKS / f"{name}.Notebook" / "notebook-content.ipynb"
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
    for name, expected in pipelines().items():
        path = PIPELINES / f"{name}.DataPipeline" / "pipeline-content.json"
        if check:
            if json.loads(path.read_text(encoding="utf-8")) != expected:
                raise ValueError(f"Source and generated pipeline differ: {name}")
        else:
            path.write_text(json.dumps(expected, indent=2) + "\n", encoding="utf-8")
    print("Notebook and pipeline consistency verified." if check else "Notebooks and pipelines rebuilt.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    build(parser.parse_args().check)
