"""Construit les tables staging/marts à partir des fichiers SQL, puis charge le référentiel
métier (glossary.yml) dans marts.dim_component_domain."""
from __future__ import annotations

from pathlib import Path

import duckdb
import yaml

from akl.config import DB_PATH, SEMANTIC_DIR, SQL_DIR


def load_glossary(path: Path = SEMANTIC_DIR / "glossary.yml") -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))["domains"]


def run(db_path: Path = DB_PATH) -> None:
    con = duckdb.connect(str(db_path))
    for sql_file in sorted(SQL_DIR.glob("*/*.sql"), key=lambda p: p.name):
        con.execute(sql_file.read_text(encoding="utf-8"))
        print(f"OK {sql_file.relative_to(SQL_DIR)}")

    rows = [
        (root, domain, spec["label"])
        for domain, spec in load_glossary().items()
        for root in spec["nhtsa_roots"]
    ]
    con.execute(
        "CREATE OR REPLACE TABLE marts.dim_component_domain "
        "(component_root VARCHAR PRIMARY KEY, domain VARCHAR, domain_label VARCHAR)"
    )
    con.executemany("INSERT INTO marts.dim_component_domain VALUES (?, ?, ?)", rows)

    unmapped = con.execute(
        """SELECT b.component_root, count(DISTINCT b.campaign_id) AS n
           FROM marts.bridge_campaign_component b
           LEFT JOIN marts.dim_component_domain d USING (component_root)
           WHERE d.domain IS NULL GROUP BY 1 ORDER BY n DESC LIMIT 10"""
    ).fetchall()
    if unmapped:
        print("Composants hors référentiel (à ajouter dans glossary.yml) :")
        for root, n in unmapped:
            print(f"  {root!r}: {n} campagnes")
    con.close()


if __name__ == "__main__":
    run()
