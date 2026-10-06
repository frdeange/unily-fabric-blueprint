"""Validated runtime configuration; no Fabric access during module import."""

import json
import re
import uuid

LIBRARY_NAME = "ProductAnalytics_Config"
ID_FIELDS = ("data_workspace_id", "vault_workspace_id", "bronze_id", "silver_id", "identity_id")
SETTING_FIELDS = {"sources_json", "pii_policy_version", "pii_model", "allow_synthetic_overwrite"}
FIELDS = set(ID_FIELDS) | SETTING_FIELDS
SCHEMA = "product"
TABLE_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")


def onelake_table(workspace_id, lakehouse_id, table):
    return f"abfss://{workspace_id}@onelake.dfs.fabric.microsoft.com/{lakehouse_id}/Tables/{SCHEMA}/{table}"


def onelake_files(workspace_id, lakehouse_id, path):
    return f"abfss://{workspace_id}@onelake.dfs.fabric.microsoft.com/{lakehouse_id}/Files/{SCHEMA}/{path}"


def validate_config(values):
    if set(values) != FIELDS:
        raise ValueError("Runtime configuration fields do not match the contract")
    config = dict(values)
    for name in ID_FIELDS:
        value = values[name]
        if not isinstance(value, str):
            raise ValueError(f"{name} must be a GUID string")
        value = str(uuid.UUID(value))
        if value.startswith("00000000-"):
            raise ValueError("Example configuration only; bind a real environment before execution")
        config[name] = value
    if len({config[name] for name in ("bronze_id", "silver_id", "identity_id")}) != 3:
        raise ValueError("Bronze, Silver and Identity must be distinct lakehouses")
    # Re-identification data stays in a separate workspace (GDPR Art. 4(5)); see docs/architecture.md.
    if config["data_workspace_id"] == config["vault_workspace_id"]:
        raise ValueError("Data and Vault must be distinct workspaces")
    for name in ("pii_policy_version", "pii_model"):
        if not isinstance(values[name], str) or not values[name].strip():
            raise ValueError(f"{name} must be a nonempty string")
    if type(values["allow_synthetic_overwrite"]) is not bool:
        raise ValueError("allow_synthetic_overwrite must be a Boolean")
    if not isinstance(values["sources_json"], str):
        raise ValueError("sources_json must be a JSON string")
    sources = json.loads(values["sources_json"])
    if not isinstance(sources, list) or not sources:
        raise ValueError("At least one source is required")
    tenants, tables = set(), set()
    for source in sources:
        if not isinstance(source, dict) or set(source) != {"tenant_id", "users_table", "events_table"}:
            raise ValueError("Each source must define tenant_id, users_table and events_table")
        tenant = source["tenant_id"]
        if not isinstance(tenant, str) or not TABLE_NAME.fullmatch(tenant) or tenant in tenants:
            raise ValueError("Source tenant IDs must be unique safe identifiers")
        tenants.add(tenant)
        for name in ("users_table", "events_table"):
            table = source[name]
            if not isinstance(table, str) or not TABLE_NAME.fullmatch(table) or table in tables:
                raise ValueError("Source table names must be unique safe identifiers")
            tables.add(table)
    config["sources"] = sources
    return config


def load_runtime_config(notebook_utils):
    library = notebook_utils.variableLibrary.getLibrary(LIBRARY_NAME)
    values = {name: library.getVariable(name) for name in sorted(FIELDS)}
    return validate_config(values)
