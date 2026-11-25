from pathlib import Path

import duckdb
import pytest

from akl.ingest import COLUMNS, load, read_rows

FIXTURE = Path(__file__).parent / "fixtures" / "FLAT_RCL_sample.txt"


def test_rows_are_padded_to_full_width():
    rows = list(read_rows(FIXTURE))
    assert rows, "le fichier de test ne doit pas être vide"
    assert all(len(r) == len(COLUMNS) for r in rows)


def test_empty_fields_become_null():
    first = next(read_rows(FIXTURE))
    assert first[COLUMNS.index("record_id")] == "1"
    assert first[COLUMNS.index("yeartxt")] == "2020"
    assert first[COLUMNS.index("modeltxt")] == "A1"
    assert first[COLUMNS.index("mfgtxt")] is None


def test_load_writes_every_row(tmp_path):
    expected = len(list(read_rows(FIXTURE)))
    db = tmp_path / "test.duckdb"
    n = load(FIXTURE, db_path=db)
    assert n == expected
    con = duckdb.connect(str(db))
    count = con.execute("SELECT count(*) FROM raw.recalls").fetchone()[0]
    con.close()
    assert count == expected


def test_unexpected_format_fails_explicitly(tmp_path):
    bad = tmp_path / "bad.txt"
    bad.write_text("a\tb\tc\n", encoding="utf-8")
    with pytest.raises(ValueError, match="colonnes"):
        list(read_rows(bad))
