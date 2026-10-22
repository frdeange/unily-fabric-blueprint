export const USAGE_CONNECTION = 'productanalytics';

export const adoptionQueries = {
  totals: `EVALUATE
TOPN(1001,
  SUMMARIZECOLUMNS(
    dim_tenant[tenant_id], dim_date[year], dim_date[month],
    "Events", [Events], "ActiveUsers", [Active users],
    "AvgDuration", [Average duration (s)]
  ),
  dim_tenant[tenant_id], ASC, dim_date[year], ASC, dim_date[month], ASC
)
ORDER BY dim_tenant[tenant_id], dim_date[year], dim_date[month]`,
  features: `EVALUATE
TOPN(5001,
  SUMMARIZECOLUMNS(
    dim_tenant[tenant_id], dim_date[year], dim_date[month],
    dim_feature[feature_name], dim_feature[feature_category],
    "Events", [Events], "ActiveUsers", [Active users],
    "AvgDuration", [Average duration (s)]
  ),
  dim_tenant[tenant_id], ASC, dim_date[year], ASC, dim_date[month], ASC,
  dim_feature[feature_name], ASC, dim_feature[feature_category], ASC
)
ORDER BY dim_tenant[tenant_id], dim_date[year], dim_date[month],
  dim_feature[feature_name], dim_feature[feature_category]`,
} as const;
