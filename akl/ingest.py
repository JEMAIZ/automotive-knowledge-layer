"""Ingestion du fichier plat NHTSA des rappels dans DuckDB (table raw.recalls).

Le fichier est tabulé, sans en-tête. L'ordre des colonnes suit RCL.txt (NHTSA).
Vérifiez-le contre la documentation officielle si la NHTSA fait évoluer le format :
le chargement échoue explicitement si le nombre de colonnes est inattendu.
"""
from __future__ import annotations

import csv

import sys
import urllib.request
import zipfile
from pathlib import Path

import duckdb

from akl.config import DATA_DIR, DB_PATH, NHTSA_RECALLS_URL

COLUMNS = [
    "record_id", "campno", "maketxt", "modeltxt", "yeartxt", "mfgcampno",
    "compname", "mfgname", "bgman", "endman", "rcltypecd", "potaff", "odate",
    "influenced_by", "mfgtxt", "rcdate", "datea", "rpno", "fmvss",
    "desc_defect", "consequence_defect", "corrective_action", "notes",
    "rcl_cmpt_id", "mfr_comp_name", "mfr_comp_desc", "mfr_comp_ptno",
    "do_not_drive", "park_outside",
]
MIN_COLUMNS = 23  # jusqu'à "notes" : les colonnes suivantes ont été ajoutées plus tard


def download(url: str = NHTSA_RECALLS_URL, dest_dir: Path = DATA_DIR) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    zip_path = dest_dir / Path(url).name
    if not zip_path.exists():
        print(f"Téléchargement {url} ...")
        urllib.request.urlretrieve(url, zip_path)
    with zipfile.ZipFile(zip_path) as zf:
        txt = [n for n in zf.namelist() if n.lower().endswith(".txt")][0]
        zf.extract(txt, dest_dir)
    return dest_dir / txt


def read_rows(path: Path):
    with open(path, encoding="cp1252", errors="replace", newline="") as f:
        reader = csv.reader(f, delimiter="\t", quoting=csv.QUOTE_NONE)
        for lineno, row in enumerate(reader, 1):
            if not row or all(not c.strip() for c in row):
                continue
            if len(row) < MIN_COLUMNS or len(row) > len(COLUMNS):
                raise ValueError(
                    f"Ligne {lineno}: {len(row)} colonnes, attendu {MIN_COLUMNS}-{len(COLUMNS)}. "
                    "Le format NHTSA a peut-être changé : vérifiez RCL.txt."
                )
            yield [c.strip() or None for c in row] + [None] * (len(COLUMNS) - len(row))


def load(path: Path, db_path: Path = DB_PATH) -> int:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = db_path.parent / "_raw_recalls.csv"
    n = 0
    # Écriture en flux : la mémoire reste faible même sur le fichier complet.
    with open(tmp, "w", encoding="utf-8", newline="") as out:
        writer = csv.writer(out)
        writer.writerow(COLUMNS)
        for row in read_rows(path):
            writer.writerow(row)
            n += 1
    con = duckdb.connect(str(db_path))
    con.execute("CREATE SCHEMA IF NOT EXISTS raw")
    con.execute(
        "CREATE OR REPLACE TABLE raw.recalls AS SELECT * FROM read_csv(?, header=true, all_varchar=true)",
        [str(tmp)],
    )
    con.close()
    tmp.unlink()
    print(f"{n} lignes chargées dans raw.recalls ({db_path})")
    return n


if __name__ == "__main__":
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else download()
    load(src)
