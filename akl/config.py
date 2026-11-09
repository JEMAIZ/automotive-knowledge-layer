"""Chemins et paramètres du projet."""
from pathlib import Path
import os

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("AKL_DATA_DIR", ROOT / "data"))
DB_PATH = Path(os.getenv("AKL_DB_PATH", DATA_DIR / "akl.duckdb"))
SQL_DIR = ROOT / "sql"
SEMANTIC_DIR = ROOT / "semantic"

# Fichier plat officiel NHTSA (rappels depuis 2010). Description des colonnes :
# https://static.nhtsa.gov/odi/ffdd/rcl/RCL.txt
NHTSA_RECALLS_URL = os.getenv(
    "AKL_NHTSA_URL", "https://static.nhtsa.gov/odi/ffdd/rcl/FLAT_RCL_POST_2010.zip"
)

# Rôles -> niveaux de classification autorisés (contrôle d'accès simulé, voir README).
ROLE_CLEARANCE = {
    "public": {"public"},
    "apres_vente": {"public", "apres_vente"},
    "ingenierie": {"public", "apres_vente", "interne"},
}
