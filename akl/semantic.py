"""Moteur minimal de couche sémantique : compile (indicateur, dimensions, filtres) en SQL
à partir de semantic/metrics.yml. Aucune requête n'est écrite à la main par l'appelant."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import duckdb
import yaml

from akl.config import DB_PATH, SEMANTIC_DIR

JOINS = {
    "vehicle": "JOIN marts.bridge_campaign_vehicle v ON v.campaign_id = c.campaign_id",
    "component": (
        "JOIN marts.bridge_campaign_component bc ON bc.campaign_id = c.campaign_id "
        "JOIN marts.dim_component_domain d ON d.component_root = bc.component_root"
    ),
}


@dataclass
class MetricQuery:
    metric: str
    group_by: list[str] = field(default_factory=list)
    filters: dict[str, object] = field(default_factory=dict)
    order_desc: bool = True
    limit: int | None = 20


class SemanticLayer:
    def __init__(self, spec_path: Path = SEMANTIC_DIR / "metrics.yml", db_path: Path = DB_PATH):
        spec = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
        self.metrics = spec["metrics"]
        self.dimensions = spec["dimensions"]
        self.db_path = db_path

    def compile(self, q: MetricQuery) -> tuple[str, list]:
        if q.metric not in self.metrics:
            raise KeyError(f"Indicateur inconnu : {q.metric}. Disponibles : {list(self.metrics)}")
        used = list(dict.fromkeys(q.group_by + list(q.filters)))
        for d in used:
            if d not in self.dimensions:
                raise KeyError(f"Dimension inconnue : {d}. Disponibles : {list(self.dimensions)}")

        joins = list(dict.fromkeys(self.dimensions[d]["join"] for d in used if "join" in self.dimensions[d]))
        dim_cols = [f"{self.dimensions[d]['sql']} AS {d}" for d in q.group_by]
        where, params = [], []
        for d, value in q.filters.items():
            where.append(f"{self.dimensions[d]['sql']} = ?")
            params.append(value)

        base_cols = ", ".join(
            ["c.campaign_id", "c.potentially_affected", "c.do_not_drive"] + dim_cols
        )
        sql = f"WITH base AS (SELECT DISTINCT {base_cols} FROM marts.fct_campaign c "
        sql += " ".join(JOINS[j] for j in joins)
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += ")\n"
        select = ", ".join(q.group_by + [f"{self.metrics[q.metric]['sql']} AS {q.metric}"])
        sql += f"SELECT {select} FROM base"
        if q.group_by:
            sql += " GROUP BY " + ", ".join(q.group_by)
            sql += f" ORDER BY {q.metric} {'DESC' if q.order_desc else 'ASC'}"
            if q.limit:
                sql += f" LIMIT {int(q.limit)}"
        return sql, params

    def query(self, q: MetricQuery):
        sql, params = self.compile(q)
        con = duckdb.connect(str(self.db_path), read_only=True)
        try:
            cur = con.execute(sql, params)
            cols = [c[0] for c in cur.description]
            return cols, cur.fetchall()
        finally:
            con.close()
