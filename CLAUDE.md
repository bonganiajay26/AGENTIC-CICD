# Agentic AI — Golden CI/CD Template

A **single-command generator** that produces a complete, cloud-native CI/CD pipeline
for any application on any cloud. Edit one file, run one command, get everything.

---

## Quickstart (3 steps)

```bash
# 1. Install generator dependency (PyYAML only)
pip install -r requirements-generator.txt

# 2. Edit the golden config — the ONLY file you touch
#    Set your app name, cloud provider, registry, thresholds
nano cicd.config.yaml

# 3. Generate everything
python generate_cicd.py
```

That's it. Commit and push to main — the pipeline starts automatically.

---

## What gets generated

```
.github/workflows/
  ci.yml                  Build → Test → Security scan → AI eval gates → Push → GitOps update
  cd-staging.yml          Smoke tests → Live evals → Manual approval → Promote to production
  cd-production.yml       Canary monitor → Promote 100% or auto-rollback

k8s/
  base/                   Deployment · Service · HPA · ConfigMap (Kustomize base)
  overlays/staging/       1 replica · debug logging · staging resources
  overlays/production/    Argo Rollout canary patch · production resources

argocd/
  app-staging.yaml        Auto-sync · prune · self-heal
  app-production.yaml     Manual sync only (safety gate)
  rollout-production.yaml Canary steps with AnalysisTemplate gates
  analysis-template.yaml  Error rate · P99 latency · AI eval score · Safety score

evals/
  thresholds.yaml         Generated from cicd.config.yaml thresholds
  (all eval scripts)      Shared across CI and staging

Dockerfile                Multi-stage, language-specific (auto-detected)
scripts/bootstrap-argocd.sh  One-time cluster setup
```

---

## Supported languages (auto-detected)

| Language | Detection signal | Dockerfile base |
|----------|-----------------|-----------------|
| Python   | `requirements.txt`, `pyproject.toml` | `python:3.11-slim` multi-stage |
| Node.js  | `package.json` | `node:20-alpine` multi-stage |
| Java     | `pom.xml`, `build.gradle` | `maven:3.9` → `temurin:21-jre` |
| Go       | `go.mod` | `golang:1.22` → `distroless/static` |
| .NET     | `*.csproj` | `dotnet/sdk:8.0` → `dotnet/aspnet:8.0` |
| Generic  | fallback | `ubuntu:22.04` |

---

## Supported clouds

| Cloud | Registry auto-built from | Auth method |
|-------|--------------------------|-------------|
| AWS   | `account_id.dkr.ecr.region.amazonaws.com/app` | OIDC role or access key |
| GCP   | `gcr.io/project_id/app` or Artifact Registry | Workload Identity or SA key |
| Azure | `registryname.azurecr.io/app` | Service Principal (`AZURE_CREDENTIALS`) |
| Generic | `registry_url/app` | Username + password |

---

## Pipeline flow

```
PR opened
  ├── Unit tests  (language-specific command)
  ├── Docker build (cached, not pushed yet)
  ├── Trivy security scan (blocks on CRITICAL/HIGH CVEs)
  └── AI Eval Gates ──────────────────────────── GATE (blocks merge)
        ✓ Prompt regression    ≥ threshold
        ✓ Tool call validation ≥ threshold
        ✓ RAG retrieval        ≥ threshold
        ✓ Hallucination rate   ≤ threshold
        ✓ Safety score         ≥ threshold
        ✓ P95 latency          ≤ threshold
        ✓ Avg token cost       ≤ threshold

Push to main (all gates pass)
  └── Push image to registry (cloud-specific auth)
  └── Update k8s/overlays/staging/ (GitOps commit)
  └── ArgoCD auto-syncs → staging namespace

Staging validation
  └── Smoke tests
  └── Live AI evals against staging env ─────── GATE
  └── Manual approval (GitHub environment protection)
  └── Promote: update k8s/overlays/production/

Production (ArgoCD + Argo Rollouts)
  └── Manual sync in ArgoCD UI/CLI
  └── Canary: 10% → analysis → 30% → analysis → 60% → 100%
  └── AnalysisTemplate: error rate + P99 + AI eval + safety
  └── Auto-rollback if any analysis fails
  └── GitHub issue created on rollback
```

---

## Re-generating after config changes

```bash
python generate_cicd.py             # regenerate all files
python generate_cicd.py --detect    # show what would be detected/used
python generate_cicd.py --dry-run   # show file list without writing
```

---

## GitHub Actions secrets required

### All clouds
| Secret | Value |
|--------|-------|
| `GITOPS_REPO` | `org/repo` of GitOps manifest repo |
| `GITOPS_TOKEN` | GitHub PAT with write access to GitOps repo |
| `ARGOCD_SERVER` | ArgoCD server hostname |
| `ARGOCD_TOKEN` | ArgoCD API token |
| `STAGING_BASE_URL` | Staging environment base URL |
| `PRODUCTION_BASE_URL` | Production environment base URL |
| `ANTHROPIC_API_KEY` | For AI eval judge calls |

### AWS additional
| Secret | Value |
|--------|-------|
| `AWS_ROLE_ARN` | IAM role ARN (OIDC) |
| `AWS_REGION` | e.g. `us-east-1` |
| `EKS_CLUSTER_NAME` | EKS cluster name |

### GCP additional
| Secret | Value |
|--------|-------|
| `GCP_WORKLOAD_IDENTITY_PROVIDER` | WIF provider resource name |
| `GCP_SERVICE_ACCOUNT` | Service account email |
| `GKE_CLUSTER_NAME` | GKE cluster name |
| `GKE_CLUSTER_LOCATION` | Region or zone |
| `REGISTRY_URL` | GCR/AR hostname |

### Azure additional
| Secret | Value |
|--------|-------|
| `AZURE_CREDENTIALS` | Service principal JSON |
| `REGISTRY_URL` | `<name>.azurecr.io` |
| `REGISTRY_USERNAME` | ACR username |
| `REGISTRY_PASSWORD` | ACR password |
| `AKS_RESOURCE_GROUP` | Resource group name |
| `AKS_CLUSTER_NAME` | AKS cluster name |

### Generic additional
| Secret | Value |
|--------|-------|
| `REGISTRY_URL` | Registry hostname |
| `REGISTRY_USERNAME` | Registry username |
| `REGISTRY_PASSWORD` | Registry password |
| `KUBE_CONFIG` | Base64-encoded kubeconfig |

---

## First-time cluster bootstrap

```bash
chmod +x scripts/bootstrap-argocd.sh
./scripts/bootstrap-argocd.sh
```

Installs ArgoCD, Argo Rollouts, creates namespaces, applies ArgoCD Applications and AnalysisTemplates.

---

## Tuning eval gates

All thresholds live in `cicd.config.yaml` under `evals.thresholds`. After changing, re-run:
```bash
python generate_cicd.py
```

To disable evals entirely (non-AI apps):
```yaml
evals:
  enabled: false
```

---

## Extending eval datasets

Add cases to `evals/datasets/*.json`. Backfill production failures here to prevent regressions recurring.

---

## Key design decisions

- **`__PLACEHOLDER__` substitution** — avoids conflicts with `${{`, `${}`, `{}` in YAML/shell
- **All templates embedded in `generate_cicd.py`** — one file to version, one file to share
- **Cloud auth is conditional per provider** — no cloud-specific code in generated files
- **Evals run in CI before push** — a bad model change is caught before the image is even published
- **Production = manual ArgoCD sync only** — no auto-sync to production; human must approve
