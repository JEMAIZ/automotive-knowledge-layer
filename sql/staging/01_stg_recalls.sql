-- Staging : typage et nettoyage, une ligne = une campagne x véhicule x composant (grain du fichier source)
CREATE SCHEMA IF NOT EXISTS staging;
CREATE OR REPLACE TABLE staging.stg_recalls AS
SELECT
    record_id,
    campno                                             AS campaign_id,
    upper(trim(maketxt))                               AS make,
    upper(trim(modeltxt))                              AS model,
    try_cast(yeartxt AS INTEGER)                       AS model_year,
    upper(trim(compname))                              AS component_path,
    upper(trim(split_part(compname, ':', 1)))          AS component_root,
    trim(mfgname)                                      AS manufacturer,
    rcltypecd                                          AS recall_type,          -- V véhicule, E équipement, T pneus, C siège enfant
    try_cast(potaff AS BIGINT)                         AS potentially_affected, -- niveau CAMPAGNE, répété sur chaque ligne
    try_strptime(rcdate, '%Y%m%d')::DATE               AS report_received_date,
    desc_defect                                        AS defect_text,
    consequence_defect                                 AS consequence_text,
    corrective_action                                  AS remedy_text,
    notes                                              AS notes_text,
    coalesce(upper(trim(do_not_drive)) IN ('YES', 'Y'), false) AS do_not_drive,
    coalesce(upper(trim(park_outside)) IN ('YES', 'Y'), false) AS park_outside
FROM raw.recalls
WHERE campno IS NOT NULL;
