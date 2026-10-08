# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   },
# META   "dependencies": {
# META     "lakehouse": {
# META       "default_lakehouse": "b495b98d-4148-4401-abbb-603b81a0f65b",
# META       "default_lakehouse_name": "Gold",
# META       "default_lakehouse_workspace_id": "12b0784b-e31a-44a7-b625-e70be871bde2",
# META       "known_lakehouses": [
# META         {
# META           "id": "b495b98d-4148-4401-abbb-603b81a0f65b"
# META         },
# META         {
# META           "id": "855ff1ba-b776-4395-ac21-f7ad68e48cb8"
# META         }
# META       ]
# META     }
# META   }
# META }

# CELL ********************

# Gold: simplified Kimball star (dim_customer, dim_agent_group, fact_tickets)
# Cross-lakehouse read: Silver is attached as a secondary lakehouse, addressed as "Silver.<table>"
# Default lakehouse for this notebook is Gold (writes land here)

from pyspark.sql import functions as F
from pyspark.sql.window import Window

silver = spark.read.table("Silver.silver_tickets")

dim_customer = (
    silver.select("tenant_id", "tenant_customer_key", "customer_email_hash", "customer_display_name", "customer_email")
    .distinct()
    .withColumn("customer_key", F.row_number().over(Window.orderBy("customer_email_hash", "tenant_id")))
)
assert dim_customer.groupBy("tenant_id", "tenant_customer_key").count().filter("count != 1").count() == 0
dim_customer.write.mode("overwrite").option("overwriteSchema", "true").format("delta").saveAsTable("gold_dim_customer")
spark.createDataFrame(
    [("tenant_a", "InventaEmpresa1", "ES"), ("tenant_b", "InventaEmpresa2", "UK"), ("tenant_c", "InventaEmpresa3", "DE")],
    "tenant_id string, tenant_name string, region string",
).write.mode("overwrite").format("delta").saveAsTable("gold_dim_tenant")

dim_agent_group = (
    silver.select("agent_group").distinct()
    .withColumn("agent_group_key", F.row_number().over(Window.orderBy("agent_group")))
)
dim_agent_group.write.mode("overwrite").format("delta").saveAsTable("gold_dim_agent_group")

fact_tickets = (
    silver.join(dim_customer.select("tenant_id", "tenant_customer_key", "customer_key"),
                on=["tenant_id", "tenant_customer_key"], how="left")
    .join(dim_agent_group, on="agent_group", how="left")
    .select(
        "tenant_id", "source_system", "ticket_id", "customer_key", "agent_group_key", "opened_at", "closed_at",
        "priority", "category", "sla_hours", "mttr_hours", "status",
        (F.col("mttr_hours") > F.col("sla_hours")).alias("sla_breached"),
    )
)
assert fact_tickets.count() == 2000
assert fact_tickets.filter(F.col("customer_key").isNull() | F.col("agent_group_key").isNull()).count() == 0
fact_tickets.write.mode("overwrite").option("overwriteSchema", "true").format("delta").saveAsTable("gold_fact_tickets")

print(f"Gold fact rows: {fact_tickets.count()}")
breach_rate = fact_tickets.filter("sla_breached = true").count() / fact_tickets.count()
print(f"SLA breach rate: {breach_rate:.1%}")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# Quick sanity summary for the deployment log / demo evidence
# category/priority exist in both gold_fact_tickets and silver_tickets (secondary lakehouse),
# so they must be qualified (f.category / f.priority) to avoid an ambiguous-reference error.
summary_df = spark.sql(
    """
    SELECT f.category AS category, f.priority AS priority,
           COUNT(*) AS tickets,
           ROUND(AVG(f.mttr_hours), 2) AS avg_mttr_hours,
           SUM(CASE WHEN f.mttr_hours > f.sla_hours THEN 1 ELSE 0 END) AS sla_breaches
    FROM gold_fact_tickets f
    GROUP BY f.category, f.priority
    ORDER BY tickets DESC
    """
)
pandas_summary = summary_df.toPandas()
print(pandas_summary)

import json
evidence = {
    "synthetic_only": True,
    "support_tickets": fact_tickets.count(),
    "per_tenant": [r.asDict() for r in fact_tickets.groupBy("tenant_id").count().collect()],
    "open_cases": fact_tickets.filter("status = 'In Progress' AND closed_at IS NULL").count(),
    "unknown_resolution_sla": fact_tickets.filter("status = 'In Progress' AND sla_breached IS NULL").count(),
    "bronze_sources": ["bronze_tickets_tenant_a", "bronze_tickets_tenant_b", "bronze_tickets_tenant_c"],
    "silver_common_table": "silver_tickets",
}
assert evidence["open_cases"] == 395
assert evidence["unknown_resolution_sla"] == 395
spark.createDataFrame([(json.dumps(evidence),)], "value string").coalesce(1).write.mode("overwrite").text(
    "Files/validation/support_tenant_ingestion")
print(json.dumps(evidence, indent=2))

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
