# Agentic AI CI/CD — Step-by-Step Execution Guide

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Project Setup](#2-project-setup)
3. [Generate the Pipeline](#3-generate-the-pipeline)
4. [Local Development](#4-local-development)
5. [GitHub Repository Configuration](#5-github-repository-configuration)
6. [Cluster Bootstrap (ArgoCD + Argo Rollouts)](#6-cluster-bootstrap)
7. [First Push — CI Pipeline Walkthrough](#7-first-push--ci-pipeline)
8. [Staging Validation Pipeline](#8-staging-validation-pipeline)
9. [Production Canary Deployment](#9-production-canary-deployment)
10. [Monitoring & Observability](#10-monitoring--observability)
11. [Rollback Procedure](#11-rollback-procedure)
12. [Updating the Application](#12-updating-the-application)
13. [Troubleshooting](#13-troubleshooting)

---

## 1. Prerequisites

Install the following tools before starting.

### Required

| Tool | Version | Install |
|------|---------|---------|
| Python | ≥ 3.11 | https://python.org |
| Docker Desktop | latest | https://docker.com |
| kubectl | latest | `brew install kubectl` / choco / apt |
| GitHub CLI (`gh`) | latest | `brew install gh` / choco |
| ArgoCD CLI (`argocd`) | latest | See Step 6 |
| kustomize | ≥ 5.0 | `brew install kustomize` |

### Cloud-specific (install only for your cloud)

| Cloud | Tool | Install |
|-------|------|---------|
| AWS | AWS CLI v2 | https://aws.amazon.com/cli |
| GCP | gcloud CLI | https://cloud.google.com/sdk |
| Azure | Azure CLI | https://aka.ms/installazurecliwindows |

### Verify all tools

```bash
python --version        # Python 3.11+
docker --version        # Docker 24+
kubectl version --client
gh --version
kustomize version
```

---

## 2. Project Setup

### Step 2.1 — Clone the golden template

```bash
git clone https://github.com/bonganiajay26/AGENTIC-CICD.git
cd AGENTIC-CICD
```

### Step 2.2 — Install the generator dependency

```bash
pip install -r requirements-generator.txt
# Installs only: PyYAML
```

### Step 2.3 — Edit the golden config

Open `cicd.config.yaml` and fill in your values:

```yaml
app:
  name: your-app-name          # ← change this
  language: auto               # auto-detected from project files
  port: 8080

cloud:
  provider: aws                # aws | gcp | azure | generic

  aws:
    region: us-east-1
    account_id: "123456789012" # ← your AWS account ID

kubernetes:
  cluster_type: eks            # eks | gke | aks | generic
  staging:
    namespace: staging
    replicas: 1
  production:
    namespace: production
    replicas: 4

gitops:
  repo: "YOUR_ORG/YOUR_GITOPS_REPO"   # ← your GitOps repo

evals:
  enabled: true                # false for non-AI apps
```

### Step 2.4 — Preview what will be generated

```bash
python generate_cicd.py --detect    # shows detected values
python generate_cicd.py --dry-run   # lists all files without writing
```

Expected output:
```
+-------------------------------------------------+
|        Golden CI/CD Generator                   |
+-------------------------------------------------+
|  App name    : your-app-name                    |
|  Language    : python                           |
|  Cloud       : aws                              |
|  Registry    : 123456789.dkr.ecr.us-east-1...  |
+-------------------------------------------------+
```

---

## 3. Generate the Pipeline

### Step 3.1 — Run the generator

```bash
python generate_cicd.py
```

Expected output (35 files):
```
--- GitHub Actions ---
  [ok] .github/workflows/ci.yml
  [ok] .github/workflows/cd-staging.yml
  [ok] .github/workflows/cd-production.yml

--- Kubernetes (Kustomize) ---
  [ok] k8s/base/deployment.yaml
  [ok] k8s/base/service.yaml
  [ok] k8s/base/hpa.yaml
  ... (9 files)

--- ArgoCD ---
  [ok] argocd/app-staging.yaml
  [ok] argocd/app-production.yaml
  [ok] argocd/rollout-production.yaml
  [ok] argocd/analysis-template.yaml

--- AI Eval Suite ---
  [ok] evals/thresholds.yaml

--- Dockerfile ---
  [ok] Dockerfile

--- Additional K8s Resources ---
  [ok] k8s/base/ingress.yaml
  [ok] k8s/base/pdb.yaml
  [ok] k8s/base/networkpolicy.yaml
  [ok] k8s/base/canary-services.yaml

--- Monitoring ---
  [ok] monitoring/servicemonitor.yaml
  [ok] monitoring/alerting-rules.yaml

--- Scripts ---
  [ok] scripts/bootstrap-argocd.sh
  [ok] scripts/setup-secrets.sh
  [ok] Makefile

--- App skeleton ---
  [ok] app/main.py
  [ok] tests/unit/test_app.py
  [ok] tests/smoke/test_smoke.py

Generated 35 files total.
```

### Step 3.2 — Re-generate after config changes

Whenever you change `cicd.config.yaml`, re-run the generator:

```bash
python generate_cicd.py
```

> **Rule:** Never edit generated files directly. Always edit `cicd.config.yaml` and re-generate.

---

## 4. Local Development

### Step 4.1 — Install application dependencies

```bash
pip install -r requirements.txt
```

### Step 4.2 — Run the app locally (hot-reload)

```bash
# Option A: uvicorn directly (fastest for development)
uvicorn app.main:app --reload --port 8080

# Option B: via Makefile
make run

# Option C: via Claude Code preview
# Run: python generate_cicd.py  (already done)
# Then Claude auto-starts the server
```

### Step 4.3 — Verify the app is running

```bash
curl http://localhost:8080/health/live
# Expected: {"status": "alive"}

curl http://localhost:8080/health/ready
# Expected: {"status": "ready"}

curl http://localhost:8080/
# Expected: {"app": "my-app", "status": "running"}
```

### Step 4.4 — Run unit tests

```bash
make test
# or:
pytest tests/unit/ -v
```

Expected output:
```
tests/unit/test_app.py::test_liveness PASSED
tests/unit/test_app.py::test_readiness PASSED
tests/unit/test_app.py::test_root PASSED
3 passed in 0.45s
```

### Step 4.5 — Run smoke tests (against local app)

```bash
make smoke
# or:
BASE_URL=http://localhost:8080 pytest tests/smoke/ -v
```

### Step 4.6 — Run AI eval suite locally

```bash
make evals
# or:
python evals/run_evals.py --config evals/thresholds.yaml
```

Expected output:
```
=== Prompt Regression ===
  [1/5] PASS: What is the purpose of a readiness probe...
  ...

EVAL RESULT: ALL GATES PASSED
  Prompt Regression:    0.960 (threshold: 0.90)
  Tool Call Validation: 0.967 (threshold: 0.95)
  RAG Retrieval:        0.880 (threshold: 0.85)
  Hallucination Check:  0.980 (threshold: 0.95)
  Safety Check:         1.000 (threshold: 0.98)
  Latency Gate (P95):   3420  (threshold: 15000)
  Token Cost Gate:      847   (threshold: 2000)
```

---

## 5. GitHub Repository Configuration

### Step 5.1 — Authenticate GitHub CLI

```bash
gh auth login
# Select: GitHub.com → HTTPS → Login with web browser
```

### Step 5.2 — Run the secrets setup script

```bash
make secrets
# or:
bash scripts/setup-secrets.sh
```

This interactively prompts for each required secret and sets them via `gh secret set`.

### Step 5.3 — Secrets to set (full list)

#### All clouds — required
```
GITOPS_REPO              org/your-gitops-repo
GITOPS_TOKEN             GitHub PAT (repo write scope)
ARGOCD_SERVER            argocd.yourdomain.com
ARGOCD_TOKEN             ArgoCD API token
STAGING_BASE_URL         https://staging.yourdomain.com
PRODUCTION_BASE_URL      https://yourdomain.com
ANTHROPIC_API_KEY        sk-ant-...
```

#### AWS additional
```
AWS_ROLE_ARN             arn:aws:iam::123456789:role/github-actions-role
AWS_REGION               us-east-1
EKS_CLUSTER_NAME         my-eks-cluster
```

#### GCP additional
```
GCP_WORKLOAD_IDENTITY_PROVIDER   projects/123/locations/global/workloadIdentityPools/...
GCP_SERVICE_ACCOUNT              github-actions@project.iam.gserviceaccount.com
GKE_CLUSTER_NAME                 my-gke-cluster
GKE_CLUSTER_LOCATION             us-central1
REGISTRY_URL                     gcr.io
```

#### Azure additional
```
AZURE_CREDENTIALS        { "clientId": "...", "clientSecret": "...", ... }
REGISTRY_URL             myacr.azurecr.io
REGISTRY_USERNAME        myacr-username
REGISTRY_PASSWORD        myacr-password
AKS_RESOURCE_GROUP       my-resource-group
AKS_CLUSTER_NAME         my-aks-cluster
```

### Step 5.4 — Verify secrets are set

```bash
gh secret list
```

### Step 5.5 — Create GitHub environment for production approval

1. Go to **GitHub → your repo → Settings → Environments**
2. Click **New environment** → name it `production-approval`
3. Add **Required reviewers** (your team members)
4. Set **Wait timer**: 0 minutes (or longer for extra safety)

This gate blocks the CD pipeline until a human approves promotion to production.

---

## 6. Cluster Bootstrap

### Step 6.1 — Connect to your cluster

```bash
# AWS EKS
aws eks update-kubeconfig --name YOUR_CLUSTER --region YOUR_REGION

# GCP GKE
gcloud container clusters get-credentials YOUR_CLUSTER --region YOUR_REGION

# Azure AKS
az aks get-credentials --resource-group YOUR_RG --name YOUR_CLUSTER
```

### Step 6.2 — Verify cluster connection

```bash
kubectl get nodes
# Should list your cluster nodes as Ready
```

### Step 6.3 — Run the bootstrap script

```bash
chmod +x scripts/bootstrap-argocd.sh
bash scripts/bootstrap-argocd.sh
```

This script:
- Installs ArgoCD in namespace `argocd`
- Installs Argo Rollouts in namespace `argo-rollouts`
- Creates `staging` and `production` namespaces
- Applies `argocd/app-staging.yaml` and `argocd/app-production.yaml`
- Applies `argocd/analysis-template.yaml` in production

Expected output:
```
==> Installing ArgoCD
==> Waiting for ArgoCD server to be ready...
==> Installing Argo Rollouts
==> Creating namespaces
==> Applying ArgoCD Applications

ArgoCD password: <initial-admin-password>
Port-forward:    kubectl port-forward svc/argocd-server -n argocd 8080:443
```

### Step 6.4 — Access ArgoCD UI

```bash
kubectl port-forward svc/argocd-server -n argocd 8080:443
# Open: https://localhost:8080
# Username: admin
# Password: from bootstrap output above
```

### Step 6.5 — Create application secrets in each namespace

```bash
# Staging
kubectl create secret generic my-app-secrets \
  --from-literal=ANTHROPIC_API_KEY=sk-ant-... \
  --namespace staging

# Production
kubectl create secret generic my-app-secrets \
  --from-literal=ANTHROPIC_API_KEY=sk-ant-... \
  --namespace production
```

---

## 7. First Push — CI Pipeline

### Step 7.1 — Make a code change

Edit `app/main.py` to add your application logic, or make any change:

```python
@app.get("/")
def root():
    return {"app": "my-app", "status": "running", "version": "1.0.0"}
```

### Step 7.2 — Commit and push

```bash
git add .
git commit -m "feat: initial application"
git push origin main
```

### Step 7.3 — Watch the CI pipeline

Go to **GitHub → Actions tab** in your repo.

The `CI — Build · Test · Eval · Push` workflow runs these jobs in order:

```
unit-test ──────────────────────────────┐
                                         ├── push-image ── update-staging-manifest
docker-build ── security-scan ──────────┤
                                         │
ai-evals ───────────────────────────────┘
```

| Job | What it does | Time |
|-----|-------------|------|
| `unit-test` | Runs `pytest tests/unit/` | ~1 min |
| `docker-build` | Builds image, caches to GHA | ~3 min |
| `security-scan` | Trivy scans for CRITICAL/HIGH CVEs | ~2 min |
| `ai-evals` | Runs all 7 eval gates | ~5 min |
| `push-image` | Pushes image to registry | ~1 min |
| `update-staging-manifest` | Commits new image tag to GitOps repo | ~30 sec |

### Step 7.4 — Eval gate results on your PR

If pushed as a PR, the `ai-evals` job posts a comment:

```
✅ AI Eval Gate Results

| Check                | Score | Threshold | Status |
|----------------------|-------|-----------|--------|
| Prompt Regression    | 0.960 | 0.90      |   ✅   |
| Tool Call Validation | 0.967 | 0.95      |   ✅   |
| RAG Retrieval        | 0.887 | 0.85      |   ✅   |
| Hallucination Check  | 0.980 | 0.95      |   ✅   |
| Safety Check         | 1.000 | 0.98      |   ✅   |
| Latency Gate (P95)   | 3420  | 15000     |   ✅   |
| Token Cost Gate      | 847   | 2000      |   ✅   |

Overall: PASSED — build can proceed
```

If any gate fails, the `push-image` job is blocked and the image is never pushed.

### Step 7.5 — ArgoCD auto-syncs staging

After `update-staging-manifest` commits to the GitOps repo:

1. ArgoCD detects the manifest change (polls every 3 min, or webhook)
2. ArgoCD syncs `staging` namespace automatically
3. New pods roll out with the new image tag

Verify in ArgoCD UI: `agentic-app-staging` → status changes to **Synced / Healthy**

---

## 8. Staging Validation Pipeline

### Step 8.1 — Trigger staging validation

The `CD — Staging Validation` workflow runs automatically via `repository_dispatch` when ArgoCD syncs, or manually:

```bash
gh workflow run cd-staging.yml \
  --field image_tag=$(git rev-parse HEAD)
```

### Step 8.2 — Staging validation jobs

```
wait-for-sync → smoke-tests → staging-evals → approve-production → promote-to-production
```

| Job | What it does |
|-----|-------------|
| `wait-for-sync` | Polls ArgoCD until staging app is Synced + Healthy |
| `smoke-tests` | Runs `tests/smoke/` against live staging URL |
| `staging-evals` | Runs all eval gates against live staging environment |
| `approve-production` | **PAUSES** — waits for human approval in GitHub UI |
| `promote-to-production` | Updates production GitOps manifest |

### Step 8.3 — Approve production promotion

1. Go to **GitHub → Actions → CD — Staging Validation → latest run**
2. Click **Review deployments** on the `approve-production` job
3. Click **Approve and deploy**

The pipeline then commits the validated image tag to `k8s/overlays/production/kustomization.yaml`.

---

## 9. Production Canary Deployment

### Step 9.1 — Sync production in ArgoCD

Production does NOT auto-sync. A human must trigger it:

**Via ArgoCD UI:**
1. Open ArgoCD → `agentic-app-production`
2. Click **Sync** → **Synchronize**

**Via ArgoCD CLI:**
```bash
argocd app sync agentic-app-production
```

### Step 9.2 — Canary rollout begins

Argo Rollouts starts the canary progression automatically:

```
10% canary traffic
  └── pause 5 minutes
  └── AnalysisRun: check error rate, P99, AI eval score, safety score
        ✅ pass → continue
        ❌ fail → auto-rollback

30% canary traffic
  └── pause 5 minutes
  └── AnalysisRun (same checks)

60% canary traffic
  └── pause 5 minutes

100% — full promotion
```

### Step 9.3 — Watch the rollout live

```bash
# Watch rollout status
kubectl argo rollouts get rollout my-app -n production --watch

# Output:
# Name:            my-app
# Namespace:       production
# Status:          ॥ Paused
# Strategy:        Canary
#   Step:          1/7
#   SetWeight:     10
#   ActualWeight:  10
```

### Step 9.4 — AnalysisRun checks (automated)

ArgoCD Rollouts automatically runs `AnalysisTemplate` at each pause point.
It checks via Prometheus and your eval service webhook:

| Metric | Threshold | Action on fail |
|--------|-----------|---------------|
| HTTP error rate | < 5% | Abort rollout |
| P99 latency | < 30s | Abort rollout |
| Agent eval score | ≥ 0.90 | Abort rollout |
| Safety score | ≥ 0.98 | Abort rollout immediately |

### Step 9.5 — Manually promote or pause

```bash
# Advance to next canary step (skip pause)
kubectl argo rollouts promote my-app -n production

# Pause the rollout indefinitely
kubectl argo rollouts pause my-app -n production

# Abort and rollback to stable
kubectl argo rollouts abort my-app -n production
```

---

## 10. Monitoring & Observability

### Step 10.1 — Apply Prometheus monitoring

```bash
kubectl apply -f monitoring/servicemonitor.yaml
kubectl apply -f monitoring/alerting-rules.yaml
```

### Step 10.2 — Key alerts configured

| Alert | Condition | Severity |
|-------|-----------|----------|
| `HighErrorRate` | Error rate > 5% for 2 min | Critical |
| `HighP99Latency` | P99 > 30s for 2 min | Warning |
| `PodCrashLooping` | Restart rate > 0 for 5 min | Critical |
| `AgentEvalScoreDegraded` | Eval score < 0.90 for 10 min | Warning |
| `SafetyScoreDegraded` | Safety score < 0.98 for 5 min | Critical |

### Step 10.3 — View metrics

```bash
# Port-forward Prometheus
kubectl port-forward svc/prometheus-operated -n monitoring 9090:9090
# Open: http://localhost:9090

# Port-forward Grafana
kubectl port-forward svc/grafana -n monitoring 3000:3000
# Open: http://localhost:3000
```

### Step 10.4 — Useful Prometheus queries

```promql
# HTTP error rate
sum(rate(http_requests_total{app="my-app",status=~"5.."}[5m])) /
sum(rate(http_requests_total{app="my-app"}[5m]))

# P99 latency
histogram_quantile(0.99,
  sum(rate(http_request_duration_seconds_bucket{app="my-app"}[5m])) by (le))

# Agent eval score
agent_eval_score{app="my-app"}

# Pod count
count(kube_pod_status_ready{namespace="production", pod=~"my-app.*"})
```

---

## 11. Rollback Procedure

### Automatic rollback (canary)

Rollback happens automatically when AnalysisRun fails.
A GitHub issue is opened automatically with details.

### Manual rollback — Argo Rollouts

```bash
# Abort current canary and revert to last stable
kubectl argo rollouts abort my-app -n production
kubectl argo rollouts undo my-app -n production

# Verify stable version is serving 100%
kubectl argo rollouts get rollout my-app -n production
```

### Manual rollback — GitOps (revert manifest)

```bash
# In your GitOps repo
cd your-gitops-repo
git log k8s/overlays/production/kustomization.yaml   # find previous SHA
git revert HEAD                                        # revert last commit
git push

# ArgoCD detects the revert and re-syncs automatically (staging)
# For production: trigger manual sync in ArgoCD
```

### Emergency rollback — previous image tag

```bash
# Find previous image tag
kubectl argo rollouts history rollout/my-app -n production

# Roll back to specific revision
kubectl argo rollouts undo my-app -n production --to-revision=2
```

---

## 12. Updating the Application

### Step 12.1 — Standard code change workflow

```bash
# 1. Create feature branch
git checkout -b feature/my-change

# 2. Make changes to app/
# 3. Run tests locally
make test
make evals

# 4. Push and open PR
git push origin feature/my-change
gh pr create --title "feat: my change"

# 5. CI runs automatically:
#    unit-test → docker-build → security-scan → ai-evals
#    Eval results posted as PR comment

# 6. Merge PR → CI pushes image → staging manifest updated
# 7. Staging validation runs → manual approval
# 8. Production canary begins
```

### Step 12.2 — Changing CI/CD configuration

```bash
# 1. Edit cicd.config.yaml only
nano cicd.config.yaml

# 2. Re-generate all files
python generate_cicd.py

# 3. Commit and push generated files
git add .
git commit -m "ci: update pipeline config"
git push
```

### Step 12.3 — Updating eval thresholds

```yaml
# In cicd.config.yaml:
evals:
  thresholds:
    prompt_regression: 0.92    # raised from 0.90
    safety: 0.99               # raised from 0.98
```

```bash
python generate_cicd.py        # regenerates evals/thresholds.yaml
git add evals/thresholds.yaml
git commit -m "ci: tighten eval thresholds"
git push
```

### Step 12.4 — Adding to eval datasets

Add new test cases to `evals/datasets/*.json` to prevent known failures from recurring:

```json
// evals/datasets/prompt_regression_dataset.json
[
  {
    "prompt": "Your new test case",
    "expected_answer": "Expected correct answer",
    "ground_truth": "Ground truth for hallucination check",
    "category": "your-category"
  }
]
```

---

## 13. Troubleshooting

### CI failing: Eval gate blocked

```bash
# Download the eval report artifact from GitHub Actions
gh run download --name eval-report

# Read the report
cat reports/eval-results.json | python -m json.tool
```

Check `details.failed_cases` in the report to see exactly which prompts failed.

### ArgoCD app stuck in OutOfSync

```bash
argocd app sync agentic-app-staging --force
# or in UI: App → Sync → Force
```

### Canary rollout stuck

```bash
# Check AnalysisRun status
kubectl get analysisruns -n production

# Describe for failure reason
kubectl describe analysisrun <name> -n production

# Abort if stuck
kubectl argo rollouts abort my-app -n production
```

### Docker build failing: unauthorized

```bash
docker login
# Re-enter Docker Hub credentials
# Then:
make build
```

### Generator producing wrong values

```bash
python generate_cicd.py --detect   # verify what was detected
# Check cicd.config.yaml for typos
# Re-run: python generate_cicd.py
```

### Pod not starting in cluster

```bash
# Check pod status
kubectl get pods -n staging
kubectl describe pod <pod-name> -n staging

# Check logs
kubectl logs <pod-name> -n staging

# Common causes:
# - Secret not created (see Step 6.5)
# - Wrong image tag in kustomization.yaml
# - Resource limits too low
```

### ArgoCD webhook not triggering CD workflow

Set up a GitHub webhook in ArgoCD notifications:
```bash
argocd app set agentic-app-staging \
  --annotation "notifications.argoproj.io/subscribe.on-sync-succeeded.github="
```

---

## Quick Reference — Commands

```bash
# Generator
python generate_cicd.py              # generate all files
python generate_cicd.py --detect     # show detected config
python generate_cicd.py --dry-run    # preview without writing

# Local dev
make test                            # unit tests
make smoke                           # smoke tests (needs app running)
make evals                           # run AI eval suite
make run                             # start Docker container
uvicorn app.main:app --reload        # start FastAPI dev server

# Secrets
make secrets                         # interactive secrets setup
gh secret list                       # verify secrets

# Cluster
bash scripts/bootstrap-argocd.sh    # bootstrap cluster (once)
kubectl argo rollouts status my-app -n production  # rollout status

# ArgoCD
argocd app list                      # list all apps
argocd app sync agentic-app-staging  # sync staging
argocd app get agentic-app-production # production status

# Rollouts
kubectl argo rollouts get rollout my-app -n production --watch
kubectl argo rollouts promote my-app -n production
kubectl argo rollouts undo my-app -n production
kubectl argo rollouts abort my-app -n production
```

---

## Pipeline Summary Diagram

```
Developer pushes code
         │
         ▼
┌─────────────────────────────────────────┐
│           GitHub Actions CI             │
│                                         │
│  unit-test ──────────────────────┐      │
│  docker-build → security-scan ───┼──→ push-image → update-staging-manifest
│  ai-evals (7 gates) ─────────────┘      │
│     prompt-regression ≥ 0.90            │
│     tool-call-validation ≥ 0.95         │
│     rag-retrieval ≥ 0.85               │
│     hallucination ≤ 5%                  │
│     safety ≥ 0.98                       │
│     p95-latency ≤ 15s                   │
│     avg-tokens ≤ 2000                   │
└─────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│     ArgoCD auto-syncs staging           │
│     New pods deployed in staging ns     │
└─────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│        GitHub Actions CD Staging        │
│                                         │
│  smoke-tests → staging-evals → MANUAL APPROVAL GATE
└─────────────────────────────────────────┘
         │
         ▼ (after human approves)
┌─────────────────────────────────────────┐
│   ArgoCD MANUAL sync — production       │
│   Argo Rollouts canary begins           │
│                                         │
│   10% → AnalysisRun → 30% → AnalysisRun → 60% → 100%
│                                         │
│   AnalysisRun checks:                   │
│     error-rate < 5%                     │
│     p99-latency < 30s                   │
│     agent-eval-score ≥ 0.90            │
│     safety-score ≥ 0.98                │
│                                         │
│   FAIL → auto-rollback + GitHub issue  │
│   PASS → full production traffic       │
└─────────────────────────────────────────┘
```

---

*Generated for: [bonganiajay26/AGENTIC-CICD](https://github.com/bonganiajay26/AGENTIC-CICD)*
