-- One row per active NEA cluster per daily snapshot, from the immutable Auto Loader envelopes.
CREATE OR REFRESH MATERIALIZED VIEW silver_cluster_snapshots (
  CONSTRAINT cluster_id_present  EXPECT (cluster_id IS NOT NULL) ON VIOLATION FAIL UPDATE,
  CONSTRAINT people_not_negative EXPECT (people >= 0) ON VIOLATION FAIL UPDATE,
  CONSTRAINT locality_present    EXPECT (locality IS NOT NULL AND length(locality) > 0),
  CONSTRAINT footprint_present   EXPECT (shape_area > 0)
)
COMMENT 'Active dengue clusters on each saved day (people = cases since the cluster started). The only source of cluster history: data.gov.sg keeps no past versions.'
AS
SELECT
  CAST(snapshot_date AS DATE) AS snapshot_date,
  f.properties.OBJECTID AS cluster_id,
  trim(f.properties.LOCALITY) AS locality,
  CAST(f.properties.CASE_SIZE AS INT) AS people,
  CAST(f.properties.`SHAPE.AREA` AS DOUBLE) AS shape_area,
  to_timestamp(f.properties.FMEL_UPD_D, 'yyyyMMddHHmmss') AS source_updated_at,
  raw_sha256, retrieved_at_utc
FROM (
  SELECT snapshot_date, raw_sha256, retrieved_at_utc,
         from_json(payload, 'STRUCT<features: ARRAY<STRUCT<properties: STRUCT<OBJECTID: STRING, LOCALITY: STRING, CASE_SIZE: STRING, FMEL_UPD_D: STRING, `SHAPE.AREA`: STRING>>>>') AS body
  FROM workspace.denguesux.bronze_live_clusters
) LATERAL VIEW explode(body.features) t AS f;
