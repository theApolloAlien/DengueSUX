-- Databricks AI Functions on the gold tables (run by the pipeline job).
-- Field-report notes: classify each optional note into a theme and keep only the theme (the note itself stays private).
CREATE OR REPLACE TABLE workspace.denguesux.gold_field_report_themes
COMMENT 'One row per field report that carried a note: the note classified into an operational theme by ai_classify. The note text is never copied here.' AS
SELECT report_id, area_code, CAST(reported_at AS DATE) AS reported_on, place_type, outcome,
       ai_classify(note, ARRAY('stagnant water', 'blocked drain or gutter', 'litter or containers', 'access problem', 'other')) AS theme
FROM workspace.denguesux.field_reports
WHERE note IS NOT NULL AND length(trim(note)) > 0;
