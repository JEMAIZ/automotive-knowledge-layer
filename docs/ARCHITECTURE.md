# Architecture : couche sémantique et base de connaissances sur les rappels NHTSA

Ce document décrit l'architecture cible du projet, module par module, avec les entrées, les sorties et les effets de bord. Il sépare ce qui existe déjà dans le nouveau dépôt de ce qui reste à reconstruire. Le code de référence est l'ancien dépôt (`main` b38bee5, `banc-v2` a54b0f3).

Statuts utilisés :

- **Reconstruit** : présent dans le nouveau dépôt et testé.
- **À reconstruire** : décrit ici à partir du code de référence, pas encore réécrit.
- **À vérifier** : comportement déduit de la lecture du code, non exécuté.

---

## 1. Vue d'ensemble

```
            ┌──────────────────────────────┐
            │  NHTSA : FLAT_RCL_POST_2010  │  (zip, texte tabulé)
            └──────────────┬───────────────┘
                           │ download / extraction
                           ▼
  ┌─────────────────────────────────────────────────────┐
  │ 1. Ingestion         akl/ingest.py                  │  → raw.recalls
  │ 2. Transformations   sql/staging, sql/marts         │  → staging.*, marts.*
  │ 3. Référentiel       semantic/glossary.yml          │  → marts.dim_component_domain
  │ 4. Couche sémantique semantic/metrics.yml + semantic.py │ → SQL compilé (chiffres)
  │ 5. Base de connaissances akl/kb.py (TF-IDF)         │  → data/kb_index.pkl
  │ 6. Routeur           akl/router.py                  │  → metric | kb | blocked
  │ 7. Garde-fous        akl/guardrails.py              │  (injection, sanitisation)
  │ 8. Évaluation        akl/evaluate.py, bench.py      │  → eval/report*.md
  └─────────────────────────────────────────────────────┘
                           ▲
                           │ CLI : akl/cli.py
                    utilisateur (chiffres ou questions)
```

Le flux se lit de gauche à droite : chaque étape consomme les tables produites par la précédente, et les étapes 4 à 6 ne lisent jamais les données brutes directement.

---

## 2. Stockage

| Artefact | Emplacement | Produit par | Consommé par | Statut |
|---|---|---|---|---|
| Zip NHTSA | `data/FLAT_RCL_POST_2010.zip` | `ingest.download` | `ingest.load` | Reconstruit (sans téléchargement automatique) |
| Texte tabulé | `data/FLAT_RCL_POST_2010.txt` | extraction du zip | `ingest.read_rows` | Reconstruit |
| Base DuckDB | `data/akl.duckdb` | toutes les étapes | couche sémantique, KB, évaluation | Reconstruit (ingestion) |
| Index TF-IDF | `data/kb_index.pkl` | `KnowledgeBase.build` | `KnowledgeBase.load` | À reconstruire |
| Rapports | `eval/report*.md` | `evaluate.run`, `bench.run` | lecture humaine | À reconstruire |

Tout ce qui est dans `data/` est exclu de git. Le fichier `kb_index.pkl` est un pickle : il ne doit jamais être chargé s'il vient d'une source non maîtrisée, car `pickle` peut exécuter du code à la lecture.

---

## 3. Modules

### 3.1 Ingestion : `akl/ingest.py`

**Statut** : Reconstruit.

| | |
|---|---|
| Entrée | Fichier texte tabulé, sans en-tête, encodage cp1252 (supposé) |
| Sortie | Table `raw.recalls`, toutes colonnes en `VARCHAR` |
| Effet de bord | Recrée la table `raw.recalls` à chaque exécution |
| Erreur | `ValueError` si une ligne n'a pas entre 23 et 29 colonnes, avec le numéro de ligne |

Fonctions :

- `read_rows(path)` : lit le fichier, saute les lignes vides, complète chaque ligne à 29 colonnes avec `None`, et remplace les champs vides par `NULL`.
- `load(path, db_path)` : crée le schéma `raw`, puis insère par lots de 10 000 lignes. Retourne le nombre de lignes insérées.

Limite connue : l'encodage est supposé cp1252, avec `errors="replace"`. Un caractère mal décodé est remplacé sans alerte.

### 3.2 Configuration : `akl/config.py`

**Statut** : Reconstruit (sous-ensemble).

| Variable | Défaut | Rôle |
|---|---|---|
| `AKL_DATA_DIR` | `<racine>/data` | Dossier des données |
| `AKL_DB_PATH` | `<data>/akl.duckdb` | Base DuckDB |
| `AKL_NHTSA_URL` | URL du zip NHTSA | Source |

La version de référence ajoute `ROLE_CLEARANCE`, qui associe chaque rôle aux niveaux de classification autorisés (voir 3.7), et `MIN_SCORE`, le seuil de refus, défini à 0,15 par défaut. Ce seuil doit être calibré sur le jeu de développement uniquement.

### 3.3 Transformations SQL : `akl/transform.py` et `sql/`

**Statut** : À reconstruire.

| | |
|---|---|
| Entrée | `raw.recalls`, `semantic/glossary.yml` |
| Sortie | `staging.stg_recalls`, `marts.fct_campaign`, `marts.bridge_campaign_vehicle`, `marts.bridge_campaign_component`, `marts.dim_component_domain` |
| Effet de bord | Recrée les schémas et les tables |

Fonctionnement : `transform.run` exécute tous les fichiers `sql/*/*.sql` dans l'ordre de leur nom, puis charge le référentiel dans `marts.dim_component_domain`. Elle affiche la liste des composants absents du référentiel, à ajouter dans `glossary.yml`.

**Staging (`01_stg_recalls.sql`)** : une ligne par campagne, véhicule et composant. Les champs sont typés et nettoyés :

- `campaign_id` ← `campno` ; `make` et `model` en majuscules ; `model_year` converti en entier ;
- `component_root` = la partie avant le `:` de `compname` ;
- `report_received_date` converti depuis `rcdate` au format `AAAAMMJJ` ;
- `do_not_drive` et `park_outside` sont vrais si la valeur vaut `YES` ou `Y`.

**Marts (`02_marts.sql`)** : séparation du grain campagne et des relations plusieurs à plusieurs.

- `fct_campaign` : une ligne par campagne. `potentially_affected` prend le maximum, car le nombre de véhicules est répété sur chaque ligne.
- `bridge_campaign_vehicle` et `bridge_campaign_component` : les relations.

Ce découpage évite un piège classique : sommer le nombre de véhicules sur le fichier brut compte une campagne autant de fois qu'elle a de lignes véhicule ou composant.

### 3.4 Couche sémantique : `akl/semantic.py` et `semantic/metrics.yml`

**Statut** : À reconstruire.

| | |
|---|---|
| Entrée | `MetricQuery` : indicateur, dimensions de regroupement, filtres, ordre, limite |
| Sortie | Requête SQL paramétrée et résultats (colonnes, lignes) |
| Effet de bord | Aucun, connexion en lecture seule |

`SemanticLayer.compile(q)` vérifie que l'indicateur et les dimensions existent dans `metrics.yml`, puis construit une requête unique. Les jointures sont ajoutées seulement si une dimension les demande. Les filtres sont passés en paramètres, jamais concaténés.

Exemple d'appel CLI :

```
akl metric vehicules_concernes --by domaine_composant --show-sql
```

Erreurs : `KeyError` si l'indicateur ou la dimension est inconnu.

### 3.5 Référentiel métier : `semantic/glossary.yml`

**Statut** : À reconstruire.

Chaque domaine (par exemple « freinage ») porte :

- `nhtsa_roots` : les composants NHTSA rattachés au domaine ;
- `synonyms_fr` et `terms_en` : vocabulaire utilisé pour reconnaître le domaine d'une question ;
- `translations` : traductions ciblées de certaines expressions françaises vers le vocabulaire anglais du corpus.

Ce fichier alimente à la fois le filtre de domaine de la couche sémantique et celui de la base de connaissances. Il garantit que deux questions sur le même sujet portent sur le même périmètre.

### 3.6 Base de connaissances : `akl/kb.py`

**Statut** : À reconstruire.

**Découpage en passages** (`PASSAGE_SPEC`) : chaque campagne produit jusqu'à trois passages, chacun avec sa classification :

| Passage | Classification | Champs |
|---|---|---|
| `defaut_consequence` | `public` | défaut et conséquence, gardés ensemble |
| `reparation` | `apres_vente` | action corrective |
| `notes` | `interne` | notes |

Un passage ne mélange jamais deux classifications. Les classifications sont **simulées** : toutes les données NHTSA sont publiques.

**Entrée et sortie** :

- `KnowledgeBase.build()` : lit `marts.fct_campaign` et les relations, construit les passages, les nettoie avec `sanitize_passage`, marque ceux qui contiennent une injection (`quarantined`), ajuste un TF-IDF, puis sauvegarde l'objet dans `data/kb_index.pkl`.
- `KnowledgeBase.retrieve(query, role, k, domain, make, year)` : applique d'abord le filtre (rôle, quarantaine, domaine, marque, année), puis calcule la similarité, puis dédoublonne les textes identiques. Retourne une liste de `(passage, score)`.

**Ordre des opérations** : le contrôle d'accès est appliqué **avant** le classement. Un passage non autorisé n'entre jamais dans le contexte du modèle, même s'il est le plus pertinent. Filtrer après coup, ou demander au modèle de ne pas citer certains documents, ne protège pas.

**Paramètres du TF-IDF** : `stop_words="english"`, `sublinear_tf=True`, `ngram_range=(1, 2)`. Le corpus est en anglais, et les questions peuvent être en français : le référentiel fait le pont. Limite connue : au sein d'un domaine, le classement reste grossier.

### 3.7 Rôles et droits : `ROLE_CLEARANCE`

**Statut** : À reconstruire.

| Rôle | Classifications accessibles |
|---|---|
| `public` | `public` |
| `apres_vente` | `public`, `apres_vente` |
| `ingenierie` | `public`, `apres_vente`, `interne` |

Un rôle inconnu lève `ValueError`.

### 3.8 Garde-fous : `akl/guardrails.py`

**Statut** : À reconstruire.

| Fonction | Entrée | Sortie |
|---|---|---|
| `detect_injection(text)` | texte | liste des motifs reconnus (vide si aucun) |
| `sanitize_passage(text)` | texte d'un passage | texte sans balises, délimiteurs ni espaces superflus |

La détection repose sur une liste de motifs en français et en anglais. Elle est volontairement simple et explicable, mais elle se contourne par paraphrase, autre langue ou encodage. Un classifieur dédié et des tests adverses réguliers doivent la compléter.

### 3.9 Routeur : `akl/router.py`

**Statut** : À reconstruire.

Le routeur décide, par règles explicites, si une question relève de la couche sémantique (chiffres) ou de la base de connaissances (texte). Il produit un objet `Route` avec un `kind` parmi trois valeurs :

| `kind` | Déclencheur | Traitement |
|---|---|---|
| `blocked` | motif d'injection dans la question | refus immédiat |
| `metric` | mot de comptage (« combien », « nombre », « top »…) | requête de la couche sémantique |
| `kb` | autre cas | recherche dans la base, avec la requête élargie du référentiel |

Extraction des filtres : domaine (par synonymes), marque (par correspondance avec les marques connues, après normalisation des accents), année (format à quatre chiffres).

Piège documenté dans le code : sans normalisation des accents, « caméra » donne le fragment « CAM », qui est aussi une marque NHTSA, et le filtre vide silencieusement les résultats. Liste de mots exclus : `MAKE_STOPWORDS`.

**Génération optionnelle** : `generate(question, passages)` appelle une API compatible OpenAI si `LLM_BASE_URL`, `LLM_API_KEY` et `LLM_MODEL` sont définis. Sans configuration, la fonction renvoie `None`. Le modèle reçoit les extraits entre balises et une consigne qui précise que le contenu est une donnée, jamais une instruction.

**Fonction `answer(question, role, router, layer, kb, k, min_score)`** : point d'entrée unique. Retourne un dictionnaire dont `route` vaut `metric`, `kb`, `refus` ou `blocked` :

- `metric` : requête SQL, paramètres, colonnes et lignes ;
- `refus` : aucun passage n'atteint le seuil `min_score` ; le modèle n'est pas appelé ;
- `kb` : filtres appliqués, passages (identifiant, classification, score, extrait de 300 caractères), et réponse générée si un LLM est configuré.

### 3.10 Interface : `akl/cli.py`

**Statut** : À reconstruire.

| Commande | Effet | Sortie |
|---|---|---|
| `akl build [source]` | ingestion, transformations, index | comptes affichés |
| `akl metric <indicateur> [--by …] [--where k=v] [--show-sql]` | requête sémantique | tableau texte |
| `akl ask "<question>" [--role …] [-k N]` | routage et réponse | JSON |
| `akl eval` | évaluation sur le jeu de développement | `eval/report.md` |
| `akl eval2 [--min-score x]` | banc sur les jeux tenus à part | `eval/report_v2.md` |
| `akl label "<question>" [--grep …]` | aide à l'annotation de passages | liste |

Il n'existe **aucune API HTTP ni interface graphique**. La CLI est le seul point d'entrée.

### 3.11 Évaluation : `akl/evaluate.py`, `akl/bench.py`, `eval/`

**Statut** : À reconstruire.

Deux niveaux, à ne jamais confondre :

- **Jeu de développement** (`eval/questions.yml`) : sert à régler le routeur, le glossaire et le seuil. Les résultats mesurés dessus ne sont **pas** indépendants.
- **Jeux tenus à part** (`eval/v2/`) : `heldout.yml` (routage), `relevance.yml` (pertinence par passage), `unanswerable.yml` (questions sans réponse), `injections.yml` (injections reformulées), `planted.yml` (documents piégés). Ils ne doivent servir qu'à la mesure finale, une fois les seuils fixés.

Règle : le seuil de refus se calibre sur le jeu de développement, jamais sur les jeux tenus à part.

Point de vigilance : `evaluate.py` importe `known_makes` depuis `cli.py`. C'est une dépendance inverse (l'évaluation dépend de l'interface). Dans le nouveau dépôt, cette fonction devrait vivre dans un module de données.

---

## 4. Ordre de construction (de A à Z)

```
akl build
 ├─ ingest.download()        zip NHTSA → data/
 ├─ ingest.load()            texte → raw.recalls
 ├─ transform.run()          sql/*  → staging, marts ; glossary → dim_component_domain
 └─ KnowledgeBase.build()    marts → passages → TF-IDF → kb_index.pkl

Question utilisateur
 └─ answer()
     ├─ Router.route()       injection ? → blocked
     │                       comptage ?  → metric → SemanticLayer.compile() → DuckDB
     │                       sinon       → kb → KnowledgeBase.retrieve() → seuil → refus | passages (+ generate())
```

---

## 5. Points d'attention pour la reconstruction

1. **Le fichier de référence `eval/report.md` n'existe pas dans le dépôt.** Les chiffres qui le citent ne sont pas vérifiables depuis le dépôt.
2. **La classification des passages est simulée.** Le livre doit le dire explicitement, à chaque endroit où elle sert à démontrer un contrôle d'accès.
3. **La détection d'injection par motifs se contourne.** Les tests adverses doivent être rapportés comme tels, avec leur taux de réussite.
4. **Le seuil de refus est un paramètre de calibrage.** Sa valeur doit être justifiée par le jeu de développement, et sa mesure finale faite sur les jeux tenus à part.
5. **Le pickle `kb_index.pkl`** ne doit être lu que depuis un fichier produit localement.
6. **Dépendance inverse** : `evaluate.py` → `cli.py`. À corriger lors de la réécriture.
7. **Un seul point d'entrée : la CLI.** Toute affirmation sur une API ou une interface doit être retirée du livre, tant qu'elle n'existe pas.
