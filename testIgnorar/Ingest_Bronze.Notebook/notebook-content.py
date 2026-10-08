# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   },
# META   "dependencies": {
# META     "lakehouse": {
# META       "default_lakehouse": "a9c5e7b9-0f60-46b0-8c8c-ff208409adc2",
# META       "default_lakehouse_name": "Bronze",
# META       "default_lakehouse_workspace_id": "12b0784b-e31a-44a7-b625-e70be871bde2",
# META       "known_lakehouses": [
# META         {
# META           "id": "a9c5e7b9-0f60-46b0-8c8c-ff208409adc2"
# META         }
# META       ]
# META     }
# META   }
# META }

# CELL ********************

# Each connector's trusted configuration supplies tenant_id; preserve raw fields.
from pyspark.sql import functions as F
TENANTS = [("tenant_a", "InventaEmpresa1", "ES"), ("tenant_b", "InventaEmpresa2", "UK"), ("tenant_c", "InventaEmpresa3", "DE")]
total = 0
for tenant_id, _, _ in TENANTS:
    source_file = f"Files/landing/{tenant_id}/support/tickets.csv"
    raw = spark.read.option("header", "true").csv(source_file)
    raw = (raw.withColumn("tenant_id", F.lit(tenant_id))
           .withColumn("source_system", F.lit("servicenow"))
           .withColumn("source_file", F.lit(source_file))
           .withColumn("ingest_batch_id", F.lit("synthetic-support-v2"))
           .withColumn("ingested_at", F.current_timestamp()))
    assert raw.filter(F.col("ticket_id").isNull()).count() == 0
    raw.write.mode("overwrite").option("overwriteSchema", "true").format("delta").saveAsTable(
        f"bronze_tickets_{tenant_id}")
    count = spark.read.table(f"bronze_tickets_{tenant_id}").count()
    assert count == (667 if tenant_id != "tenant_c" else 666)
    total += count
    print(f"{tenant_id}: {count} Bronze tickets")
assert total == 2000

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
