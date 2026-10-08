"""Environment naming convention shared by provisioning and deployment (docs/architecture.md)."""

ENVIRONMENTS = ("dev", "test", "prod")
LAYERS = ("data", "analytics", "vault")


def workspace_name(layer, environment):
    if layer not in LAYERS or environment not in ENVIRONMENTS:
        raise ValueError("Unknown layer or environment")
    return f"Unily-{layer.capitalize()}-{environment.capitalize()}"


def workspace_names(environment):
    return {layer: workspace_name(layer, environment) for layer in LAYERS}


def gold_connection_name(environment):
    """Connection the Analytics semantic models use to read Gold."""
    if environment not in ENVIRONMENTS:
        raise ValueError("Unknown environment")
    return f"conn-unily-analytics-{environment}-gold-onelake"
