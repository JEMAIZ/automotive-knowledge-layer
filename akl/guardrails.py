"""Garde-fous : détection d'injection de prompt dans les questions ET dans les documents
indexés (injection indirecte), et neutralisation du contexte envoyé au modèle.

Détection par motifs : volontairement simple et explicable. En production, on la
complète par un classifieur dédié et des tests adverses réguliers ; un filtre par
motifs seul se contourne (paraphrase, autre langue, encodage).
"""
from __future__ import annotations

import re

INJECTION_PATTERNS = [
    r"ignore (all |any )?(the )?(previous|prior|above) (instructions|rules)",
    r"disregard (all |the )?(previous|prior|above)",
    r"ignore[sz]? (toutes )?les (instructions|consignes|règles) (précédentes|ci-dessus)",
    r"oublie[sz]? (toutes )?(tes|vos|les) (instructions|consignes)",
    r"(reveal|show|print|affiche|révèle|donne)[- ]?(moi )?(le |ton |your |the )?(system|système) ?prompt",
    r"you are now ",
    r"tu es (maintenant|désormais) ",
    # Délimiteurs de prompt explicites uniquement : "WHEEL-END SYSTEM" (texte NHTSA réel)
    # déclenchait l'ancienne règle "END SYSTEM".
    r"(^|[\[#<=*-]{2,}\s*)(BEGIN|END) (SYSTEM|INSTRUCTIONS)( PROMPT)?\b",
    r"<\s*/?\s*(system|script|instructions?)\s*>",
    r"(act|agis) (as|comme) (an? )?(admin|administrat|developer|développeur)",
    # Demande adressée au modèle, pas une description technique ("assembled without filters",
    # "can move without restriction" : faux positifs observés sur les données réelles).
    r"(r[ée]ponds?|answer|respond|agis|act|affiche|donne|show|give|list)\w*\b.{0,40}\b(sans|without) (aucune? )?(restriction|filtre|filter|limitation|censure)s?",
    r"(liste|list|exporte|export|dump)[a-z]* (tous |toutes |all )?(les |the )?(documents?|données|data) (internes?|confidenti|internal)",
]
_RX = [re.compile(p, re.IGNORECASE) for p in INJECTION_PATTERNS]


def detect_injection(text: str | None) -> list[str]:
    if not text:
        return []
    return [rx.pattern for rx in _RX if rx.search(text)]


def sanitize_passage(text: str) -> str:
    """Neutralise les balises et délimiteurs qui pourraient être pris pour des instructions."""
    text = re.sub(r"<[^>]{1,40}>", " ", text)
    text = text.replace("```", " ").replace("<<<", " ").replace(">>>", " ")
    return re.sub(r"\s+", " ", text).strip()
