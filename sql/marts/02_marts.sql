-- Marts : on sépare le grain CAMPAGNE (faits, textes) des relations N-N (véhicules, composants).
-- Sans cette séparation, sommer potentially_affected sur le fichier brut compte une campagne
-- autant de fois qu'elle a de lignes véhicule/composant : c'est le piège classique qu'une
-- couche sémantique doit neutraliser.
CREATE SCHEMA IF NOT EXISTS marts;

CREATE OR REPLACE TABLE marts.fct_campaign AS
SELECT
    campaign_id,
    any_value(manufacturer)            AS manufacturer,
    any_value(recall_type)             AS recall_type,
    min(report_received_date)          AS report_received_date,
    max(potentially_affected)          AS potentially_affected,
    bool_or(do_not_drive)              AS do_not_drive,
    bool_or(park_outside)              AS park_outside,
    any_value(defect_text)             AS defect_text,
    any_value(consequence_text)        AS consequence_text,
    any_value(remedy_text)             AS remedy_text,
    any_value(notes_text)              AS notes_text
FROM staging.stg_recalls
GROUP BY campaign_id;

CREATE OR REPLACE TABLE marts.bridge_campaign_vehicle AS
SELECT DISTINCT campaign_id, make, model, model_year
FROM staging.stg_recalls;

CREATE OR REPLACE TABLE marts.bridge_campaign_component AS
SELECT DISTINCT campaign_id, component_root, component_path
FROM staging.stg_recalls
WHERE component_root IS NOT NULL;
