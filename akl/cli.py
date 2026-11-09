"""Point d'entrée : python -m akl.cli <commande>

  build [fichier.txt]          ingestion (téléchargement NHTSA si aucun fichier) + transformation + index
  metric <indicateur> [--by dim ...] [--where dim=valeur ...]
  ask "<question>" [--role public|apres_vente|ingenierie]
  eval                         jeu d'évaluation + tests de sécurité -> eval/report.md
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import duckdb

from akl import ingest, transform
from akl.config import DB_PATH, ROLE_CLEARANCE
from akl.kb import KnowledgeBase
from akl.router import Router, answer
from akl.semantic import MetricQuery, SemanticLayer


def known_makes() -> set[str]:
    con = duckdb.connect(str(DB_PATH), read_only=True)
    makes = {r[0] for r in con.execute("SELECT DISTINCT make FROM marts.bridge_campaign_vehicle WHERE make IS NOT NULL").fetchall()}
    con.close()
    return makes


def main(argv=None):
    p = argparse.ArgumentParser(prog="akl")
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build"); b.add_argument("source", nargs="?")
    m = sub.add_parser("metric"); m.add_argument("metric")
    m.add_argument("--by", nargs="*", default=[]); m.add_argument("--where", nargs="*", default=[])
    m.add_argument("--show-sql", action="store_true")
    a = sub.add_parser("ask"); a.add_argument("question")
    a.add_argument("--role", default="public", choices=sorted(ROLE_CLEARANCE)); a.add_argument("-k", type=int, default=5)
    sub.add_parser("eval")
    args = p.parse_args(argv)

    if args.cmd == "build":
        src = Path(args.source) if args.source else ingest.download()
        ingest.load(src)
        transform.run()
        KnowledgeBase.build()
    elif args.cmd == "metric":
        filters = {}
        for w in args.where:
            k, v = w.split("=", 1)
            filters[k] = int(v) if v.isdigit() else v
        layer = SemanticLayer()
        q = MetricQuery(args.metric, args.by, filters)
        if args.show_sql:
            print(layer.compile(q)[0], "\n")
        cols, rows = layer.query(q)
        print(" | ".join(cols))
        for r in rows:
            print(" | ".join(str(x) for x in r))
    elif args.cmd == "ask":
        res = answer(args.question, args.role, Router(known_makes()), SemanticLayer(), KnowledgeBase.load(), args.k)
        print(json.dumps(res, ensure_ascii=False, indent=2, default=str))
    elif args.cmd == "eval":
        from akl.evaluate import run
        run()


if __name__ == "__main__":
    main()
