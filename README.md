# automotive-knowledge-layer

Prototype d'une couche sémantique et d'une base de connaissances construites sur les mêmes données : les rappels de sécurité automobile publiés par la NHTSA.

Le projet relie les indicateurs (nombre de rappels, véhicules concernés, par composant) et le texte des rappels (défaut, conséquence, réparation) à un référentiel métier commun, avec des garde-fous dès la conception.

## Statut

Reconstruction en cours. Modules présents : ingestion, configuration, transformation de staging. Les marts, la couche sémantique, la base de connaissances, le routeur et l'évaluation sont à reconstruire. Le journal de chaque étape est dans `docs/PROCESSUS_DONNEES.md`, et l'architecture cible dans `docs/ARCHITECTURE.md`.

## Données

Fichier plat officiel NHTSA, rappels depuis 2010 : https://static.nhtsa.gov/odi/ffdd/rcl/FLAT_RCL_POST_2010.zip

Les données ne sont pas versionnées. Place le zip et son contenu extrait dans `data/` (ignoré par git).

## Installation

```
python -m venv .venv
.\.venv\Scripts\Activate.ps1      # Windows PowerShell
pip install -r requirements.txt
```

## Tests

```
python -m pytest -q
```

Les tests utilisent un échantillon synthétique (`tests/fixtures/FLAT_RCL_sample.txt`). Ils vérifient le comportement du code, pas la conformité aux données réelles.

## Chargement du fichier réel

```
python -c "from pathlib import Path; from akl.ingest import load; print(load(Path('data/FLAT_RCL_POST_2010.txt')))"
```

## Limites connues

- Le format des colonnes n'est pas encore confronté à la documentation officielle `RCL.txt`.
- L'encodage est supposé cp1252.
- Les classifications d'accès (public, après-vente, interne) sont simulées : toutes les données NHTSA sont publiques.
