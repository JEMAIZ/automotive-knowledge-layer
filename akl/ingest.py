"""Ingestion du fichier plat NHTSA des rappels dans DuckDB (table raw.recalls).

Le fichier est tabulé, sans en-tête. L'ordre des colonnes doit être vérifié
contre RCL.txt avant toute ingestion. Le chargement échoue explicitement si le
nombre de colonnes d'une ligne sort de la plage attendue.
"""
from __future__ import annotations

import csv
from pathlib import Path

import duckdb

from akl.config import DB_PATH

COLUMNS = [
    "record_id", "campno", "maketxt", "modeltxt", "yeartxt", "mfgcampno",
    "compname", "mfgname", "bgman", "endman", "rcltypecd", "potaff", "odate",
    "influenced_by", "mfgtxt", "rcdate", "datea", "rpno", "fmvss",
    "desc_defect", "consequence_defect", "corrective_action", "notes",
    "rcl_cmpt_id", "mfr_comp_name", "mfr_comp_desc", "mfr_comp_ptno",
    "do_not_drive", "park_outside",
]
MIN_COLUMNS = 23  # jusqu'à "notes" ; les colonnes suivantes ont été ajoutées plus tard
BATCH_SIZE = 10_000


def read_rows(path: Path):
    """Lit le fichier ligne à ligne et complète chaque ligne à la largeur de COLUMNS."""
    with open(path, encoding="cp1252", errors="replace", newline="") as f:
        reader = csv.reader(f, delimiter="\t", quoting=csv.QUOTE_NONE)
        for lineno, row in enumerate(reader, 1):
            if not row or all(not c.strip() for c in row):
                continue
            if len(row) < MIN_COLUMNS or len(row) > len(COLUMNS):
                raise ValueError(
                    f"Ligne {lineno} : {len(row)} colonnes, attendu {MIN_COLUMNS} à {len(COLUMNS)}. "
                    "Le format NHTSA a peut-être changé : vérifiez RCL.txt."
                )
            values = [c.strip() or None for c in row]
            yield values + [None] * (len(COLUMNS) - len(values))


def load(path: Path, db_path: Path = DB_PATH) -> int:
    """Charge le fichier dans raw.recalls. Toutes les colonnes sont en VARCHAR : aucun typage ici."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(db_path))
    con.execute("CREATE SCHEMA IF NOT EXISTS raw")
    cols_sql = ", ".join(f'"{c}" VARCHAR' for c in COLUMNS)
    con.execute(f"CREATE OR REPLACE TABLE raw.recalls ({cols_sql})")
    placeholders = ",".join("?" * len(COLUMNS))
    insert = f"INSERT INTO raw.recalls VALUES ({placeholders})"

    n, batch = 0, []
    for row in read_rows(path):
        batch.append(row)
        n += 1
        if len(batch) >= BATCH_SIZE:
            con.executemany(insert, batch)
            batch.clear()
    if batch:
        con.executemany(insert, batch)
    con.close()
    return n
