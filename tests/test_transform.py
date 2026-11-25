from pathlib import Path

import duckdb

from akl.ingest import load
from akl.transform import run

FIXTURE = Path(__file__).parent / "fixtures" / "FLAT_RCL_sample.txt"


def _built_db(tmp_path):
    db = tmp_path / "t.duckdb"
    load(FIXTURE, db_path=db)
    applied = run(db_path=db)
    return duckdb.connect(str(db)), applied


def test_staging_applies_and_keeps_every_row(tmp_path):
    con, applied = _built_db(tmp_path)
    assert applied == ["01_stg_recalls.sql", "02_marts.sql"]
    raw = con.execute("SELECT count(*) FROM raw.recalls WHERE campno IS NOT NULL").fetchone()[0]
    stg = con.execute("SELECT count(*) FROM staging.stg_recalls").fetchone()[0]
    con.close()
    assert stg == raw


def test_staging_normalises_text_and_types(tmp_path):
    con, _ = _built_db(tmp_path)
    make, year, root, path, dnd = con.execute(
        "SELECT make, model_year, component_root, component_path, do_not_drive "
        "FROM staging.stg_recalls WHERE record_id = '1'"
    ).fetchone()
    con.close()
    assert make == "ACME"
    assert year == 2020
    assert root == "SERVICE BRAKES, HYDRAULIC"
    assert path == "SERVICE BRAKES, HYDRAULIC:FOUNDATION COMPONENTS"
    assert dnd is False


def test_staging_keeps_do_not_drive_yes(tmp_path):
    con, _ = _built_db(tmp_path)
    flag = con.execute(
        "SELECT do_not_drive FROM staging.stg_recalls WHERE campaign_id = 'TEST22V002' LIMIT 1"
    ).fetchone()[0]
    con.close()
    assert flag is True
