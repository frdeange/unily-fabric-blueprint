# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   },
# META   "dependencies": {
# META     "lakehouse": {
# META       "default_lakehouse": "855ff1ba-b776-4395-ac21-f7ad68e48cb8",
# META       "default_lakehouse_name": "Silver",
# META       "default_lakehouse_workspace_id": "12b0784b-e31a-44a7-b625-e70be871bde2",
# META       "known_lakehouses": [
# META         {
# META           "id": "855ff1ba-b776-4395-ac21-f7ad68e48cb8"
# META         },
# META         {
# META           "id": "a9c5e7b9-0f60-46b0-8c8c-ff208409adc2"
# META         }
# META       ]
# META     }
# META   }
# META }

# CELL ********************

# Consolidate the three isolated raw sources only at the Silver boundary.
from functools import reduce
from pyspark.sql import functions as F

frames = []
for tenant in ("tenant_a", "tenant_b", "tenant_c"):
    df = spark.read.table(f"Bronze.bronze_tickets_{tenant}")
    assert df.filter(F.col("tenant_id").isNull() | (F.col("tenant_id") != tenant)).count() == 0
    frames.append(df)
bronze_df = reduce(lambda a, b: a.unionByName(b), frames)
assert bronze_df.groupBy("tenant_id", "source_system", "ticket_id").count().filter("count != 1").count() == 0

silver_df = (
    bronze_df
    .withColumn("opened_at", F.to_timestamp("opened_at"))
    .withColumn("closed_at", F.to_timestamp("closed_at"))
    .withColumn("sla_hours", F.col("sla_hours").cast("int"))
    .withColumn("mttr_hours", F.col("mttr_hours").cast("double"))
    .withColumn("customer_email_hash", F.sha2(F.col("customer_email"), 256))
    .withColumn("tenant_customer_key", F.sha2(F.concat_ws("|", "tenant_id", "source_system", "customer_email"), 256))
    .withColumn("customer_display_name", F.concat(F.col("customer_first_name"), F.lit(" "), F.col("customer_last_name")))
    .withColumn("contains_pii", F.lit(True))
    .select(
        "tenant_id", "source_system", "source_file", "ingest_batch_id", "ingested_at",
        "ticket_id", "customer_display_name", "customer_email", "customer_email_hash", "tenant_customer_key",
        "opened_at", "closed_at", "priority", "category", "agent_group",
        "sla_hours", "mttr_hours", "status", "contains_pii"
    )
)

assert silver_df.filter(F.col("opened_at").isNull()).count() == 0
assert silver_df.filter((F.col("status") == "In Progress") & F.col("closed_at").isNotNull()).count() == 0
assert silver_df.filter((F.col("status") != "In Progress") & F.col("closed_at").isNull()).count() == 0
assert silver_df.filter(F.col("closed_at") < F.col("opened_at")).count() == 0
assert silver_df.count() == 2000
silver_df.write.mode("overwrite").option("overwriteSchema", "true").format("delta").saveAsTable("silver_tickets")

print(f"Silver rows: {silver_df.count()}")
silver_df.printSchema()

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
