# Gold contract

Gold is the business contract between the Data and Analytics workspaces. The
`ProductAnalytics_SilverToGold` notebook publishes it from Silver only, into the
`product` schema of the `Gold` lakehouse. The code source of truth is
`src/product_analytics/gold_contract.py`; a test keeps this page in sync.

## Rules

- Star schema: one fact table and four dimensions.
- Tenant-scoped tables start with `tenant_id`, the row-level security column.
- Direct identifiers (`source_user_id`, `display_name`, `email`) and the raw
  `free_text` column never reach Gold. Users are identified by the
  pseudonymous `user_key` only.
- `feedback_text` holds Silver text that already went through the PII step.
  Publication fails if Silver contains text whose `pii_status` is not
  `processed`. Masking is best effort: `processed` does not guarantee that no
  PII remains.
- An unknown `feature_id` stops the run; extend `FEATURE_CATALOG` first.

## Incremental processing

Silver has the Delta Change Data Feed enabled (`BronzeToSilver` sets it).

1. The first run publishes the current Silver snapshot.
2. Later runs read only the Silver changes after the watermark (the last
   processed Silver version). Inserts, updates (including key changes) and
   deletes are applied.
3. A MERGE on the table keys makes every write idempotent: rerunning the same
   changes never duplicates rows.
4. `dim_user` is recomputed only for the users touched by the changes. Users
   without remaining events are removed.
5. The watermark (`Files/product/state/silver-to-gold.json` in Gold) advances
   only after all merges succeed and the fact count matches the Silver snapshot.
   A failed run is simply rerun.
6. When Silver has not changed, the notebook exits without reading or writing
   data.

Recreating Silver (a new Delta table ID) or a watermark ahead of Silver stops
the run for manual review. Gold reads and writes the Data workspace only.

## Tables

### `fact_usage_event`

One row per usage event. Key: `tenant_id`, `event_id`.

| Column | Type | Description |
| --- | --- | --- |
| `tenant_id` | string | Tenant; RLS column. |
| `event_id` | string | Source event ID, unique per tenant. |
| `user_key` | string | Pseudonymous user key. |
| `feature_id` | string | Feature; joins `dim_feature`. |
| `event_date` | date | Event date; joins `dim_date`. |
| `occurred_at` | timestamp | Event timestamp. |
| `event_type` | string | Event type. |
| `duration_seconds` | long | Duration in seconds. |
| `feedback_text` | string | PII-masked free text; null when absent. |
| `has_feedback_text` | boolean | True when the event has free text. |
| `pii_status` | string | `processed` or `not_required`. |
| `silver_version` | long | Silver version from which the row was last published (the snapshot version for the initial load). |

### `dim_user`

Pseudonymous users. Key: `tenant_id`, `user_key`.

| Column | Type | Description |
| --- | --- | --- |
| `tenant_id` | string | Tenant; RLS column. |
| `user_key` | string | Pseudonymous user key. |
| `first_seen_date` | date | First event date. |
| `last_seen_date` | date | Last event date. |
| `event_count` | long | Number of events. |

### `dim_feature`

Versioned reference catalog. Key: `feature_id`.

| Column | Type | Description |
| --- | --- | --- |
| `feature_id` | string | Feature ID. |
| `feature_name` | string | Display name. |
| `feature_category` | string | Category. |

### `dim_tenant`

Registered tenants from `sources_json`. Key: `tenant_id`.

| Column | Type | Description |
| --- | --- | --- |
| `tenant_id` | string | Tenant; RLS column. |

### `dim_date`

Calendar for the event dates seen so far. Key: `date`.

| Column | Type | Description |
| --- | --- | --- |
| `date` | date | Calendar date. |
| `year` | int | Year. |
| `quarter` | int | Quarter (1-4). |
| `month` | int | Month (1-12). |
| `month_name` | string | English month name. |
| `day` | int | Day of month. |
| `day_of_week` | int | ISO day of week (Monday = 1). |
| `day_name` | string | English day name. |
| `iso_week` | int | ISO week number. |
| `is_weekend` | boolean | Saturday or Sunday. |
