.PHONY: install build eval test demo
install:
	pip install -r requirements.txt
build:       ## Télécharge les rappels NHTSA, construit la couche sémantique et l'index
	python -m akl.cli build
eval:        ## Rapport d'évaluation sur les données réelles -> eval/report.md
	python -m akl.cli eval
test:        ## Tests sur le jeu synthétique
	python -m pytest -q
demo:        ## Démo hors ligne sur le jeu synthétique
	AKL_DATA_DIR=/tmp/akl-demo python -m akl.cli build tests/fixtures/FLAT_RCL_sample.txt
	AKL_DATA_DIR=/tmp/akl-demo python -m akl.cli metric vehicules_concernes --by domaine_composant --show-sql
	AKL_DATA_DIR=/tmp/akl-demo python -m akl.cli ask "Pourquoi la caméra de recul ne s'affiche pas ?" --role apres_vente
