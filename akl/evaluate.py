"""Évaluation : routage, apport du référentiel à la recherche, et sécurité (droits d'accès,
injection). Écrit eval/report.md. Tous les chiffres viennent de l'exécution réelle."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import yaml

from akl.cli import known_makes
from akl.config import ROLE_CLEARANCE, ROOT
from akl.kb import KnowledgeBase
from akl.router import Router

K = 5


def run(questions_path: Path = ROOT / "eval" / "questions.yml", report_path: Path = ROOT / "eval" / "report.md") -> dict:
    spec = yaml.safe_load(questions_path.read_text(encoding="utf-8"))
    router, kb = Router(known_makes()), KnowledgeBase.load()
    lines = [f"# Rapport d'évaluation\n\nGénéré le {datetime.now():%Y-%m-%d %H:%M}, {len(kb.passages)} passages indexés.\n"]

    # 1. Routage
    ok_route, rows = 0, []
    for item in spec["routing"]:
        r = router.route(item["q"])
        good = r.kind == item["route"]
        if good and r.kind == "metric":
            mq = r.metric_query
            good = (
                mq.metric == item["metric"]
                and mq.group_by == item.get("group_by", [])
                and mq.filters == item.get("filters", {})
            )
        if good and r.kind == "kb":
            good = r.domain == item.get("domain")
        ok_route += good
        rows.append(f"| {'OK' if good else 'KO'} | {item['q']} | {r.kind} | {r.domain} |")
    lines += ["## 1. Routage", f"\n**{ok_route}/{len(spec['routing'])}** questions correctement routées.\n",
              "| | Question | Route | Domaine résolu |", "|---|---|---|---|", *rows, ""]

    # 2. Apport du référentiel : précision de domaine@k sans / avec filtre
    kb_items = [i for i in spec["routing"] if i["route"] == "kb"]
    def domain_precision(use_glossary: bool) -> float:
        scores = []
        for item in kb_items:
            r = router.route(item["q"])
            query = r.expanded_query if use_glossary else item["q"]
            hits = kb.retrieve(query, role="ingenierie", k=K, domain=r.domain if use_glossary else None)
            if hits:
                scores.append(sum(item["domain"] in p.domains for p, _ in hits) / len(hits))
            else:
                scores.append(0.0)
        return sum(scores) / len(scores) if scores else 0.0
    raw, gl = domain_precision(False), domain_precision(True)
    lines += ["## 2. Apport du référentiel métier à la recherche",
              f"\nPrécision de domaine@{K} (part des passages retrouvés appartenant au bon domaine) :\n",
              f"- question brute (FR sur corpus EN, sans filtre) : **{raw:.2f}**",
              f"- avec référentiel (traduction des termes + filtre de domaine) : **{gl:.2f}**\n"]

    # 3. Droits d'accès : aucune fuite tolérée
    leaks, checks = 0, 0
    for role, allowed in ROLE_CLEARANCE.items():
        for item in kb_items:
            r = router.route(item["q"])
            for p, _ in kb.retrieve(r.expanded_query, role=role, k=K, domain=r.domain):
                checks += 1
                leaks += p.classification not in allowed or p.quarantined
    lines += ["## 3. Droits d'accès",
              f"\n{checks} passages renvoyés sur {len(ROLE_CLEARANCE)} rôles : **{leaks} fuite(s)** "
              f"(passage au-dessus du niveau du rôle ou en quarantaine).\n"]

    # 4. Injection
    blocked = sum(router.route(q).kind == "blocked" for q in spec["injection"])
    quarantined = sum(p.quarantined for p in kb.passages)
    lines += ["## 4. Injection de prompt",
              f"\n- questions malveillantes bloquées : **{blocked}/{len(spec['injection'])}**",
              f"- passages du corpus mis en quarantaine (injection indirecte) : **{quarantined}**",
              "\nLimite : détection par motifs, contournable par paraphrase. À compléter par un classifieur et des tests adverses.\n"]

    report_path.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    return {"routing": ok_route / len(spec["routing"]), "domain_p_raw": raw, "domain_p_glossary": gl,
            "acl_leaks": leaks, "injection_blocked": blocked / len(spec["injection"])}
