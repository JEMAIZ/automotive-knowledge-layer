from pathlib import Path

import duckdb

from akl.ingest import load
from akl.transform import run

FIXTURE = Path(__file__).parent / "fixtures" / "FLAT_RCL_sample.txt"


def _built_db(tmp_path):
    db = tmp_path / "t.duckdb"
    load(FIXTURE, db_path=db)
    run(db_path=db)
    return duckdb.connect(str(db))


def test_one_row_per_campaign(tmp_path):
    con = _built_db(tmp_path)
    total, distinct = con.execute(
        "SELECT count(*), count(DISTINCT campaign_id) FROM marts.fct_campaign"
    ).fetchone()
    source = con.execute(
        "SELECT count(DISTINCT campno) FROM raw.recalls WHERE campno IS NOT NULL"
    ).fetchone()[0]
    con.close()
    assert total == distinct == source == 8


def test_potentially_affected_is_not_summed_over_lines(tmp_path):
    # TEST22V001 apparaît sur trois lignes (une par véhicule ou composant), chacune avec 1000.
    # Une somme sur les lignes donnerait 3000 ; la valeur correcte au niveau campagne est 1000.
    con = _built_db(tmp_path)
    lines = con.execute(
        "SELECT count(*) FROM staging.stg_recalls WHERE campaign_id = 'TEST22V001'"
    ).fetchone()[0]
    value = con.execute(
        "SELECT potentially_affected FROM marts.fct_campaign WHERE campaign_id = 'TEST22V001'"
    ).fetchone()[0]
    con.close()
    assert lines == 3
    assert value == 1000


def test_do_not_drive_flag_reaches_marts(tmp_path):
    con = _built_db(tmp_path)
    flag = con.execute(
        "SELECT do_not_drive FROM marts.fct_campaign WHERE campaign_id = 'TEST22V002'"
    ).fetchone()[0]
    con.close()
    assert flag is True


def test_every_campaign_has_a_vehicle_link(tmp_path):
    con = _built_db(tmp_path)
    orphans = con.execute(
        """SELECT count(*) FROM marts.fct_campaign c
           LEFT JOIN marts.bridge_campaign_vehicle v USING (campaign_id)
           WHERE v.campaign_id IS NULL"""
    ).fetchone()[0]
    con.close()
    assert orphans == 0
