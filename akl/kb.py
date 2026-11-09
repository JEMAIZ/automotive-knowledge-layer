"""Base de connaissances : passages issus des textes de rappel, indexés en TF-IDF.

Choix assumés pour un prototype exécutable hors ligne :
- TF-IDF plutôt qu'embeddings (pas de clé API, résultats reproductibles). Le module
  expose une interface `retrieve` stable : brancher des embeddings ou un RAG géré
  (RAG Engine sur GCP, Bedrock Knowledge Bases sur AWS) ne change pas l'appelant.
- Contrôle d'accès appliqué AVANT le classement (pré-filtrage) : un passage non
  autorisé n'entre jamais dans le contexte du modèle, même s'il est le plus pertinent.
- Passages contenant une tentative d'injection mis en quarantaine à l'indexation.
"""
from __future__ import annotations

import pickle
from dataclasses import dataclass
from pathlib import Path

import duckdb
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

from akl.config import DATA_DIR, DB_PATH, ROLE_CLEARANCE
from akl.guardrails import detect_injection, sanitize_passage

INDEX_PATH = DATA_DIR / "kb_index.pkl"

# Classification SIMULÉE des champs (toutes les données NHTSA sont publiques) :
# elle reproduit la situation d'un client où réparation et notes ne sont pas pour tous.
# Découpage : défaut et conséquence partagent le même niveau d'accès, on les garde dans
# le MÊME passage pour que la cause reste attachée à l'effet. Les frontières de découpage
# suivent les niveaux d'accès : un passage ne mélange jamais deux classifications.
PASSAGE_SPEC = [
    ("defaut_consequence", "public", ("defect_text", "consequence_text")),
    ("reparation", "apres_vente", ("remedy_text",)),
    ("notes", "interne", ("notes_text",)),
]


@dataclass
class Passage:
    passage_id: str
    campaign_id: str
    field: str
    classification: str
    text: str
    manufacturer: str | None
    year: int | None
    domains: tuple[str, ...]
    makes: tuple[str, ...]
    quarantined: bool = False


def build_passages(db_path: Path = DB_PATH) -> list[Passage]:
    con = duckdb.connect(str(db_path), read_only=True)
    rows = con.execute(
        """
        SELECT c.campaign_id, c.manufacturer, year(c.report_received_date),
               c.defect_text, c.consequence_text, c.remedy_text, c.notes_text,
               coalesce(list_distinct(list(d.domain) FILTER (WHERE d.domain IS NOT NULL)), []),
               coalesce(list_distinct(list(v.make)), [])
        FROM marts.fct_campaign c
        LEFT JOIN marts.bridge_campaign_component bc USING (campaign_id)
        LEFT JOIN marts.dim_component_domain d USING (component_root)
        LEFT JOIN marts.bridge_campaign_vehicle v USING (campaign_id)
        GROUP BY ALL
        """
    ).fetchall()
    con.close()
    passages = []
    for cid, mfr, year, defect, conseq, remedy, notes, domains, makes in rows:
        fields = {"defect_text": defect, "consequence_text": conseq, "remedy_text": remedy, "notes_text": notes}
        for label, classification, cols in PASSAGE_SPEC:
            value = " ".join(fields[c] for c in cols if fields[c])
            if not value:
                continue
            passages.append(
                Passage(
                    passage_id=f"{cid}#{label}",
                    campaign_id=cid,
                    field=label,
                    classification=classification,
                    text=sanitize_passage(value),
                    manufacturer=mfr,
                    year=year,
                    domains=tuple(sorted(domains)),
                    makes=tuple(sorted(makes)),
                    quarantined=bool(detect_injection(value)),
                )
            )
    return passages


class KnowledgeBase:
    def __init__(self, passages: list[Passage]):
        self.passages = passages
        self.vectorizer = TfidfVectorizer(stop_words="english", sublinear_tf=True, min_df=1, ngram_range=(1, 2))
        self.matrix = self.vectorizer.fit_transform([p.text for p in passages])

    @classmethod
    def build(cls, db_path: Path = DB_PATH, index_path: Path = INDEX_PATH) -> "KnowledgeBase":
        kb = cls(build_passages(db_path))
        index_path.parent.mkdir(parents=True, exist_ok=True)
        with open(index_path, "wb") as f:
            pickle.dump(kb, f)
        q = sum(p.quarantined for p in kb.passages)
        print(f"{len(kb.passages)} passages indexés, {q} en quarantaine (injection détectée)")
        return kb

    @classmethod
    def load(cls, index_path: Path = INDEX_PATH) -> "KnowledgeBase":
        with open(index_path, "rb") as f:
            return pickle.load(f)

    def retrieve(
        self,
        query: str,
        role: str,
        k: int = 5,
        domain: str | None = None,
        make: str | None = None,
        year: int | None = None,
    ) -> list[tuple[Passage, float]]:
        if role not in ROLE_CLEARANCE:
            raise ValueError(f"Rôle inconnu : {role}")
        allowed = ROLE_CLEARANCE[role]
        mask = np.array(
            [
                p.classification in allowed
                and not p.quarantined
                and (domain is None or domain in p.domains)
                and (make is None or make in p.makes)
                and (year is None or p.year == year)
                for p in self.passages
            ]
        )
        if not mask.any():
            return []
        scores = (self.matrix @ self.vectorizer.transform([query]).T).toarray().ravel()
        scores[~mask] = -1.0
        # Dédoublonnage : des dizaines de campagnes partagent la même phrase de conséquence
        # standard ("loss of lighting can reduce visibility..."). Sans ce filtre, elles
        # occupent tout le top-k et n'apportent qu'une information.
        results, seen = [], set()
        for i in np.argsort(-scores):
            if scores[i] <= 0 or len(results) >= k:
                break
            key = " ".join(self.passages[i].text.lower().split())
            if key in seen:
                continue
            seen.add(key)
            results.append((self.passages[i], float(scores[i])))
        return results
