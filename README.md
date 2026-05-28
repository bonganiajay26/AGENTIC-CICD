# Agentic AI CI/CD — Golden Template

> **One command. Any application. Any cloud. Complete production-grade CI/CD pipeline generated automatically.**

---

## Two ways to use this

### Starting a new project

```bash
git clone https://github.com/bonganiajay26/AGENTIC-CICD.git
cd AGENTIC-CICD
pip install -r requirements-generator.txt
python generate_cicd.py --init
```

### Adding to your existing project

```bash
# From your existing project root — download just the generator
curl -O https://raw.githubusercontent.com/bonganiajay26/AGENTIC-CICD/main/generate_cicd.py
curl -O https://raw.githubusercontent.com/bonganiajay26/AGENTIC-CICD/main/requirements-generator.txt
pip install -r requirements-generator.txt
python generate_cicd.py --init
```

Your existing source code, tests, and config files are **never overwritten**.
See **[INTEGRATE_EXISTING_PROJECT.md](INTEGRATE_EXISTING_PROJECT.md)** for the full guide.

---

The wizard auto-detects your language, builds your cloud registry URL, writes
`cicd.config.yaml`, and generates all 35+ pipeline files in under 3 seconds.

---

## What gets generated (35+ files)

```
.github/workflows/
  ci.yml                  ← Build · Unit test · Security scan · AI eval gates · Push image
  cd-staging.yml          ← Smoke test · Live evals · Manual approval gate · Promote
  cd-production.yml       ← Canary monitor · Auto-promote or auto-rollback

k8s/
  base/                   ← Deployment · Service · HPA · PDB · Ingress · NetworkPolicy
  overlays/staging/       ← Staging overrides (1 replica, debug logging)
  overlays/production/    ← Argo Rollout canary patch

argocd/
  app-staging.yaml        ← Auto-sync · self-heal
  app-production.yaml     ← Manual sync only (safety gate)
  rollout-production.yaml ← Canary: 10% → 30% → 60% → 100%
  analysis-template.yaml  ← Auto-checks: error rate · P99 · AI eval · safety

evals/
  run_evals.py            ← Orchestrator: runs all 7 gates
  thresholds.yaml         ← All thresholds (generated from your config)
  prompt_regression.py    ← Prompt regression gate
  tool_validation.py      ← Tool-call validation gate
  rag_eval.py             ← RAG retrieval gate
  hallucination_check.py  ← Hallucination detection gate
  safety_check.py         ← Safety gate
  latency_cost_gate.py    ← Latency + token cost gate
  datasets/               ← Curated eval datasets (extend for your domain)

monitoring/
  servicemonitor.yaml     ← Prometheus scrape config
  alerting-rules.yaml     ← 5 pre-configured alerts

app/main.py               ← FastAPI skeleton (health + metrics endpoints)
tests/unit/               ← Unit test scaffold
tests/smoke/              ← Smoke test scaffold
Dockerfile                ← Multi-stage, language-specific
Makefile                  ← Convenience commands
scripts/
  bootstrap-argocd.sh     ← One-time cluster setup
  setup-secrets.sh        ← Interactive GitHub secrets setup
```

---

## The AI Eval Gate (what makes this different)

Every PR is blocked from merging until all 7 gates pass:

| Gate | What it checks | Default threshold |
|------|---------------|-------------------|
| Prompt Regression | Agent answers curated questions correctly | ≥ 90% |
| Tool-Call Validation | Correct tool + valid schema on every call | ≥ 95% |
| RAG Retrieval | Retrieval relevance + answer faithfulness | ≥ 85% |
| Hallucination Check | Responses stay grounded in context | ≤ 5% rate |
| Safety Check | Harmful prompts refused, safe prompts answered | ≥ 98% |
| P95 Latency | End-to-end response time | ≤ 15 s |
| Token Cost | Average tokens per request | ≤ 2 000 |

Eval results are posted as a comment on every PR. If any gate fails, the image
is never pushed — the bad change never reaches staging.

---

## Supported languages (auto-detected)

| Language | Detected by | Dockerfile base |
|----------|-------------|-----------------|
| Python | `requirements.txt`, `pyproject.toml` | `python:3.11-slim` multi-stage |
| Node.js | `package.json` | `node:20-alpine` multi-stage |
| Java | `pom.xml`, `build.gradle` | `maven:3.9` → `temurin:21-jre` |
| Go | `go.mod` | `golang:1.22` → `distroless/static` |
| .NET | `*.csproj` | `dotnet/sdk:8.0` → `dotnet/aspnet:8.0` |
| Generic | fallback | `ubuntu:22.04` |

---

## Supported clouds

| Cloud | Registry auto-built | Auth |
|-------|--------------------|----- |
| **AWS** | `<account>.dkr.ecr.<region>.amazonaws.com/<app>` | OIDC role or access key |
| **GCP** | `gcr.io/<project>/<app>` or Artifact Registry | Workload Identity or SA key |
| **Azure** | `<name>.azurecr.io/<app>` | Service Principal |
| **Generic** | `<registry>/<app>` | Username + password |

---

## Pipeline flow

```
PR pushed
  ├─ unit-test
  ├─ docker-build ──► security-scan (Trivy)
  └─ ai-evals (7 gates) ─────────── GATE: blocks merge if any fail
          │
          ▼ (all pass)
  push-image ──► update staging manifest (GitOps commit)
          │
          ▼
  ArgoCD auto-syncs staging
          │
          ▼
  CD Staging: smoke-tests ──► live evals ──► MANUAL APPROVAL
          │
          ▼ (human approves)
  Update production manifest (GitOps commit)
          │
          ▼
  ArgoCD manual sync ──► Argo Rollouts canary
          │
          10% ──► AnalysisRun ──► 30% ──► AnalysisRun ──► 60% ──► 100%
          │                               │
          │  (error rate · P99 · eval)    └─► FAIL: auto-rollback + GitHub issue
          ▼
  Full production traffic
```

---

## Re-generate after any change

```bash
# Change something in cicd.config.yaml
nano cicd.config.yaml

# Re-generate — all 35 files updated in seconds
python generate_cicd.py
```

---

## Common commands

```bash
# Setup
python generate_cicd.py --init      # interactive wizard (first time)
python generate_cicd.py             # re-generate from cicd.config.yaml
python generate_cicd.py --detect    # show what would be used
python generate_cicd.py --dry-run   # preview file list without writing

# Development
make test                           # unit tests
make smoke                          # smoke tests against running app
make evals                          # full AI eval suite
make build                          # docker build
make run                            # docker run

# Infrastructure
make secrets                        # set GitHub Actions secrets interactively
make bootstrap                      # install ArgoCD + Argo Rollouts in cluster
```

---

## Step-by-step execution

See **[EXECUTION_GUIDE.md](EXECUTION_GUIDE.md)** for a complete walkthrough covering:

1. Prerequisites
2. Project setup
3. Generating the pipeline
4. Local development
5. GitHub secrets configuration
6. Cluster bootstrap
7. CI pipeline walkthrough
8. Staging validation
9. Production canary deployment
10. Monitoring & observability
11. Rollback procedures
12. Updating the application
13. Troubleshooting

---

## Use as a GitHub Template

Click **"Use this template"** on GitHub to create your own copy, then run:

```bash
pip install -r requirements-generator.txt
python generate_cicd.py --init
```

---

## Documentation

| Guide | What it covers |
|-------|---------------|
| [PRE_EXECUTION_GUIDE.md](PRE_EXECUTION_GUIDE.md) | **Read this first** — prerequisites checklist, what changes, cost impact, known issues & fixes, full undo guide |
| [INTEGRATE_EXISTING_PROJECT.md](INTEGRATE_EXISTING_PROJECT.md) | **Existing project** — 3 integration methods, safe vs overwritten files, per-language walkthroughs |
| [EXECUTION_GUIDE.md](EXECUTION_GUIDE.md) | **Step-by-step execution** — generate → local dev → secrets → cluster bootstrap → CI → staging → production canary → rollback |
| [HOW_IT_WORKS.md](HOW_IT_WORKS.md) | **Deep dive** — every component explained, full data-flow diagram, design decisions |
| [CLAUDE.md](CLAUDE.md) | **Quick reference** — all commands, secrets list, re-generate workflow |

---

## Repository

**GitHub:** [bonganiajay26/AGENTIC-CICD](https://github.com/bonganiajay26/AGENTIC-CICD)
