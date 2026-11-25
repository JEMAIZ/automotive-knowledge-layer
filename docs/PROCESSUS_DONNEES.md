# Acquisition et chargement du jeu de données (rappels NHTSA)

Journal de travail, pas à pas. Chaque étape indique la commande lancée, le résultat observé et son statut.

Statuts utilisés :

- **Vérifié** : résultat constaté, avec sa commande.
- **Non vérifié** : hypothèse ou étape pas encore contrôlée.
- **À confirmer** : action probablement faite, mais pas encore confirmée par son auteur.

---

## 0. Règles de ce journal

- Une seule source de données : le fichier plat officiel de la NHTSA.
- Aucune donnée réelle n'est versionnée dans git (`data/` est exclu).
- Chaque chiffre du livre doit renvoyer à une ligne de ce journal.

---

## 1. Le jeu de données

| Élément | Valeur | Statut |
|---|---|---|
| Source | NHTSA (National Highway Traffic Safety Administration, États-Unis) | Vérifié (`akl/config.py`) |
| Fichier | `FLAT_RCL_POST_2010.zip` | Vérifié |
| URL | https://static.nhtsa.gov/odi/ffdd/rcl/FLAT_RCL_POST_2010.zip | Vérifié (`akl/config.py`) |
| Contenu | Rappels de sécurité automobile publiés depuis 2010 | Vérifié (commentaire de `akl/config.py`) |
| Format | Fichier texte tabulé, sans en-tête, encodage supposé cp1252 | Non vérifié |
| Description des colonnes | https://static.nhtsa.gov/odi/ffdd/rcl/RCL.txt | Non vérifié (à télécharger et à comparer) |
| Licence et usage | Données publiques de la NHTSA | Non vérifié (à relire sur le site officiel) |

Une ligne = un enregistrement de rappel. L'identifiant `record_id` est censé être unique.

---

## 2. Itération 0 : tentative échouée

**Commande lancée (PowerShell)** :

```powershell
curl -LO https://static.nhtsa.gov/odi/ffdd/rcl/FLAT_RCL_POST_2010.zip
```

**Résultat** : erreur `Impossible de trouver un paramètre correspondant au nom « LO »`. Sous PowerShell, `curl` est un alias de `Invoke-WebRequest`, qui n'accepte pas `-LO`.

**Correction** : utiliser `curl.exe` (vrai binaire) ou `Invoke-WebRequest -OutFile`.

**Statut** : Vérifié.

---

## 3. Itération 1 : téléchargement du zip

**Commande de référence** (la forme exacte utilisée n'a pas été conservée ; à confirmer) :

```powershell
curl.exe -L -O https://static.nhtsa.gov/odi/ffdd/rcl/FLAT_RCL_POST_2010.zip
```

**Résultats constatés** (`dir` dans `data\`) :

| Fichier | Date de modification | Taille (octets) |
|---|---|---|
| `FLAT_RCL_POST_2010.zip` | 24/11/2026 13:49 | 15 069 192 |

**Empreinte** (`Get-FileHash .\FLAT_RCL_POST_2010.zip -Algorithm SHA256`) :

```
SHA256 CE12CFA419C81A29B00A4E1E45AB988E2B1433A4FCAD0B6F2BAAF2EE1EB6F3BE
```

**Statut** : Vérifié pour la taille et l'empreinte. La méthode exacte de téléchargement reste à confirmer.

---

## 4. Itération 2 : extraction et comptage

### 4.1 Premier fichier texte trouvé (écarté)

`dir` a montré un fichier `FLAT_RCL_POST_2010.txt` daté du **23/11/2026 08:02**, soit avant le téléchargement du zip. Il ne peut donc pas provenir de ce zip. Il a été mis de côté.

| Fichier | Date | Taille (octets) |
|---|---|---|
| `FLAT_RCL_POST_2010.txt` (ancien) | 23/11/2026 08:02 | 314 235 584 |

**Statut** : Vérifié. Le renommage en `.ancien.txt` était prévu. Son exécution n'est pas confirmée, et la comparaison entre les deux versions n'a pas été faite.

### 4.2 Ré-extraction depuis le zip frais

**Commandes** :

```powershell
Expand-Archive -Path .\FLAT_RCL_POST_2010.zip -DestinationPath . -Force
(Get-Content .\FLAT_RCL_POST_2010.txt | Measure-Object -Line).Lines
```

**Résultat** : `248586` lignes.

**Statut** : Vérifié. Le compte inclut les lignes vides éventuelles. Il sera recoupé avec la base.

---

## 5. Itération 3 : premier module de chargement

**Fichiers créés** (livrés dans `akl-rebuild-premier-module.zip`) :

- `requirements.txt` : `duckdb`, `pyyaml`, `scikit-learn`, `numpy`, `pytest` (versions minimales reprises de l'ancien dépôt).
- `akl/config.py` : chemins et URL.
- `akl/ingest.py` : `read_rows` (lecture tabulée, contrôle du nombre de colonnes entre 23 et 29, complétion à 29) et `load` (chargement par lots de 10 000 dans `raw.recalls`, toutes colonnes en `VARCHAR`).
- `tests/test_ingest.py` : quatre tests.
- `tests/fixtures/FLAT_RCL_sample.txt` : 12 lignes synthétiques.

**Commandes** :

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m pytest -q
```

**Résultats** :

- Première tentative : `No module named pytest`. Cause : `pip install -r requirements.txt` n'avait pas été lancé, le fichier n'étant pas encore dans le dépôt.
- Après installation : paquets installés (`duckdb-2.0.1`, `pytest-9.2.0`, `numpy-2.5.5`, `pyyaml-6.0.4`, `scikit-learn-1.9.1`, `scipy-1.18.1` entre autres).
- `python -m pytest -q` : **4 passed**.

**Statut** : Vérifié (tests sur l'échantillon synthétique, exécutés en local). Les tests n'ont pas encore été lancés sur le vrai fichier.

---

## 6. Itération 4 : chargement du fichier réel

**Commande** :

```powershell
python -c "from pathlib import Path; from akl.ingest import load; print(load(Path('data/FLAT_RCL_POST_2010.txt')))"
```

**Résultat** : la sortie n'est pas recopiée ici. Le contrôle suivant montre que le chargement a bien écrit 248 586 lignes.

**Statut** : Vérifié par le contrôle ci-dessous.

---

## 7. Contrôles après chargement

**Commande** :

```powershell
python -c "import duckdb; con=duckdb.connect('data/akl.duckdb'); print(con.execute('SELECT count(*), count(DISTINCT record_id) FROM raw.recalls').fetchall()); print(con.execute('SELECT record_id, maketxt, modeltxt, yeartxt, rcltypecd FROM raw.recalls LIMIT 3').fetchall())"
```

**Résultats** :

```
[(248586, 248586)]
[('81716', 'K-Z', 'SPORTSMEN', '2003', 'V'), ('81717', 'GEM', 'e2', '2009', 'V'), ('81718', 'GEM', 'e6', '2009', 'V')]
```

**Lecture** :

- 248 586 lignes chargées, égales au nombre de lignes comptées : aucune ligne rejetée.
- 248 586 identifiants distincts : aucun doublon sur `record_id`.
- Les trois lignes d'exemple ont une marque, un modèle, une année et un type `V` (véhicule). Elles sont plausibles, mais je ne les ai pas comparées au site NHTSA.

**Statut** : Vérifié.

**Incident** : la première exécution de cette requête a échoué (`ModuleNotFoundError: No module named 'duckdb'`). Cause : l'environnement virtuel n'était pas activé dans cette nouvelle session. Corrigé en réactivant `.venv`.

---

## 8. Environnement

| Élément | Valeur | Statut |
|---|---|---|
| Système | Windows (PowerShell) | Vérifié |
| Python | Version non relevée (à compléter avec `python --version`) | À confirmer |
| Environnement | `.venv` dans le dossier du dépôt | Vérifié |
| duckdb | 2.0.1 | Vérifié (sortie `pip install`) |
| pytest | 9.2.0 | Vérifié (sortie `pip install`) |

---

## 9. Points ouverts

1. **Schéma** : vérifié contre `RCL.txt` (voir section 11). Le champ 21 est écrit `CONEQUENCE_DEFECT` dans la source ; le code garde `consequence_defect`.
2. **Encodage** : cp1252 supposé, avec `errors="replace"`. Des caractères peuvent être remplacés sans alerte. Il faut compter les remplacements.
3. **Lignes vides** : le compte de 248 586 inclut les lignes vides. Vérifier leur nombre.
4. **Ancien fichier** : confirmer le renommage ou la suppression de `FLAT_RCL_POST_2010.ancien.txt`.
5. **Commande de téléchargement** : confirmer la forme exacte utilisée.
6. **Documentation officielle** : relire les conditions d'utilisation des données de la NHTSA.
7. **Commit** : noter le hash du commit qui contient ce module dans le nouveau dépôt.

---

## 11. Vérification du schéma

**Source** : `RCL.txt`, téléchargé depuis https://static.nhtsa.gov/odi/ffdd/rcl/RCL.txt, dernière mise à jour indiquée par la NHTSA : mai 2025.

**Comparaison** : les 29 champs décrits dans `RCL.txt` (de `RECORD_ID` à `PARK_OUTSIDE`) sont dans le même ordre que `COLUMNS` dans `akl/ingest.py`. Les noms correspondent, à la casse près.

**Comptage des colonnes par ligne** (commande exécutée sur le fichier réel) :

```powershell
Get-Content "C:\...\data\FLAT_RCL_POST_2010.txt" | ForEach-Object { ($_ -split "`t").Count } | Group-Object | Sort-Object Name | Format-Table Name, Count
```

Résultat : 29 colonnes pour 248 586 lignes, aucune autre valeur.

**Conclusion** : le schéma du fichier réel correspond à la documentation de mai 2025. Les champs 28 et 29 sont présents sur toutes les lignes.

**Points non couverts** : l'encodage cp1252 n'est pas indiqué par `RCL.txt` ; il reste supposé. La documentation mentionne une longueur maximale d'enregistrement de 17 108 caractères, non testée ici.

---

## 12. Transformation et contrôle des comptes

**Commande** (dans le dépôt `akl-rebuild`, environnement activé) :

```powershell
python -c "from akl.transform import run; print(run())"
python -c "import duckdb; con=duckdb.connect('data/akl.duckdb'); print(con.execute('SELECT count(*), count(DISTINCT campaign_id) FROM marts.fct_campaign').fetchall()); print(con.execute('SELECT count(*) FROM staging.stg_recalls').fetchall()); print(con.execute('SELECT count(*) FROM raw.recalls WHERE campno IS NULL').fetchall())"
```

**Résultats** :

```
['01_stg_recalls.sql', '02_marts.sql']
[(15424, 15424)]
[(248586,)]
[(0,)]
```

**Lecture** :

- Chaque campagne n'apparaît qu'une fois dans `marts.fct_campaign` : le grain campagne est respecté sur le fichier réel.
- Le staging conserve les 248 586 lignes du fichier, sans perte.
- Aucune ligne n'est exclue faute de numéro de campagne.
- En moyenne, une campagne correspond à environ 16 lignes du fichier (véhicules et composants confondus). Ce rapport n'a pas encore été comparé à une source externe.

**Statut** : Vérifié sur le fichier réel. La cohérence interne est établie ; la justesse des valeurs métier reste à confronter au site de la NHTSA.

---

## 10. Journal synthétique

| # | Date | Action | Résultat | Statut |
|---|---|---|---|---|
| 0 | 24/11/2026 | `curl -LO` sous PowerShell | Erreur (alias `curl`) | Vérifié |
| 1 | 24/11/2026 13:49 | Téléchargement du zip | 15 069 192 octets, SHA-256 `CE12CFA4…` | Vérifié |
| 2 | 24/11/2026 | Extraction et comptage | 248 586 lignes | Vérifié |
| 3 | 24/11/2026 14:10 | Premier module et tests | 4 tests réussis (échantillon) | Vérifié |
| 4 | 24/11/2026 | Chargement du fichier réel | 248 586 lignes chargées | Vérifié |
| 5 | 25/11/2026 | Contrôle `count` et `distinct` | 248 586 / 248 586 | Vérifié |
| 6 | 25/11/2026 | Comparaison de `COLUMNS` avec `RCL.txt` | 29 champs, noms et ordre identiques | Vérifié |
| 7 | 25/11/2026 | Comptage des colonnes par ligne du fichier réel | 29 colonnes pour les 248 586 lignes | Vérifié |
| 8 | 25/11/2026 | Staging et marts sur le fichier réel (`transform.run`) | `01_stg_recalls.sql` et `02_marts.sql` appliqués | Vérifié |
| 9 | 25/11/2026 | Contrôle des comptes après transformation | 15 424 campagnes, 15 424 identifiants distincts ; 248 586 lignes en staging ; 0 ligne sans numéro de campagne | Vérifié |
