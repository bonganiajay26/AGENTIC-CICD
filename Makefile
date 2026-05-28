.PHONY: generate detect dry-run build run test lint bootstrap secrets

## Regenerate all CI/CD files from cicd.config.yaml
generate:
	python generate_cicd.py

## Show auto-detected values without generating
detect:
	python generate_cicd.py --detect

## Show what would be generated without writing files
dry-run:
	python generate_cicd.py --dry-run

## Build Docker image locally
build:
	docker build -t my-app:local .

## Run app locally
run:
	docker run --rm -p 8080:8080 my-app:local

## Run unit tests
test:
	pytest tests/unit/ -v

## Run smoke tests against local app
smoke:
	BASE_URL=http://localhost:8080 pytest tests/smoke/ -v

## Run full AI eval suite (CI mode)
evals:
	python evals/run_evals.py --config evals/thresholds.yaml

## Bootstrap ArgoCD + Argo Rollouts in current cluster
bootstrap:
	bash scripts/bootstrap-argocd.sh

## Interactive GitHub secrets setup helper
secrets:
	bash scripts/setup-secrets.sh

## Install generator dependency
install:
	pip install -r requirements-generator.txt
