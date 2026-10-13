-- Databricks AI Functions on the gold tables (run by the pipeline job after the notices and field reports exist).
-- 1. Resident notices: back-translate every non-English draft and score it against the English draft, so a translation that
--    drifted from the facts is flagged for native-speaker review before it is posted. Nothing is auto-corrected.
CREATE OR REPLACE TABLE workspace.denguesux.gold_notice_checks
COMMENT 'Back-translation check of each non-English resident notice: ai_translate to English, then ai_similarity against the English draft. Low similarity means review before posting; drafts are never changed automatically.' AS
WITH english AS (
  SELECT area_code, notice_text AS english_text, as_of_date FROM workspace.denguesux.gold_resident_notices WHERE language = 'en'
),
others AS (
  SELECT area_code, language, notice_text, as_of_date FROM workspace.denguesux.gold_resident_notices WHERE language <> 'en'
),
checked AS (
  SELECT o.area_code, o.language, o.as_of_date, o.notice_text, e.english_text,
         ai_translate(o.notice_text, 'en') AS back_translation
  FROM others o JOIN english e ON e.area_code = o.area_code
)
SELECT area_code, language, as_of_date, english_text, back_translation,
       round(ai_similarity(back_translation, english_text), 3) AS similarity,
       CASE WHEN ai_similarity(back_translation, english_text) < 0.75 THEN 'review' ELSE 'ok' END AS verdict,
       current_timestamp() AS checked_at
FROM checked;
