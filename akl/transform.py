"""Construit les tables du schéma staging à partir de raw.recalls.

Les fichiers SQL sont exécutés dans l'ordre de leur nom. Les marts et le référentiel
seront ajoutés dans une étape ultérieure, avec leurs propres tests.
"""
from __future__ import annotations

from pathlib import Path

import duckdb

from akl.config import DB_PATH, SQL_DIR


def run(db_path: Path = DB_PATH, sql_dir: Path = SQL_DIR) -> list[str]:
    """Exécute les fichiers SQL de staging et retourne la liste des fichiers appliqués."""
    con = duckdb.connect(str(db_path))
    applied = []
    try:
        for sql_file in sorted((sql_dir / "staging").glob("*.sql"), key=lambda p: p.name):
            con.execute(sql_file.read_text(encoding="utf-8"))
            applied.append(sql_file.name)
    finally:
        con.close()
    return applied
