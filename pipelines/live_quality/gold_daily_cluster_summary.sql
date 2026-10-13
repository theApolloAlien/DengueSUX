-- Day-by-day national cluster picture and the change since the previous saved day.
CREATE OR REFRESH MATERIALIZED VIEW gold_daily_cluster_summary (
  CONSTRAINT totals_consistent EXPECT (people >= clusters)
)
COMMENT 'Active clusters, people in clusters and large (10+) clusters per saved day, with day-on-day change.'
AS
WITH daily AS (
  SELECT snapshot_date, count(*) AS clusters, sum(people) AS people, sum(CASE WHEN people >= 10 THEN 1 ELSE 0 END) AS large_clusters,
         max(people) AS largest_cluster
  FROM silver_cluster_snapshots
  GROUP BY snapshot_date
)
SELECT *, people - lag(people) OVER (PARTITION BY 1 ORDER BY snapshot_date) AS people_change,
       datediff(snapshot_date, lag(snapshot_date) OVER (PARTITION BY 1 ORDER BY snapshot_date)) AS days_since_previous
FROM daily;
