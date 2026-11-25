"""Construit les schémas staging puis marts à partir de raw.recalls.

Les fichiers SQL sont exécutés dans l'ordre : d'abord sql/staging/, puis sql/marts/,
chacun dans l'ordre de son nom. Le référentiel métier (glossary.yml) sera ajouté
dans une étape ultérieure, avec ses propres tests.
"""
from __future__ import annotations

from pathlib import Path

import duckdb

from akl.config import DB_PATH, SQL_DIR


def run(db_path: Path = DB_PATH, sql_dir: Path = SQL_DIR) -> list[str]:
    """Exécute les fichiers SQL et retourne la liste des fichiers appliqués, dans l'ordre."""
    con = duckdb.connect(str(db_path))
    applied = []
    try:
        for layer in ("staging", "marts"):
            for sql_file in sorted((sql_dir / layer).glob("*.sql"), key=lambda p: p.name):
                con.execute(sql_file.read_text(encoding="utf-8"))
                applied.append(sql_file.name)
    finally:
        con.close()
    return applied
