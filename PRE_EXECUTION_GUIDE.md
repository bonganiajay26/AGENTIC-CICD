# Pre-Execution Guide — Know Before You Run

> Read this completely before running any command.
> Covers: what you need, what changes, what breaks, and how to fix it.

---

## Table of Contents

1. [Prerequisites Checklist](#1-prerequisites-checklist)
2. [Accounts & Permissions Required](#2-accounts--permissions-required)
3. [Exactly What Changes in Your Project](#3-exactly-what-changes-in-your-project)
4. [Exactly What Changes in GitHub](#4-exactly-what-changes-in-github)
5. [Exactly What Changes in Your Cluster](#5-exactly-what-changes-in-your-cluster)
6. [Cost Impact](#6-cost-impact)
7. [Impact on Your Team](#7-impact-on-your-team)
8. [Known Issues & Fixes](#8-known-issues--fixes)
9. [How to Undo Everything](#9-how-to-undo-everything)
10. [Pre-Run Validation Checklist](#10-pre-run-validation-checklist)

---

## 1. Prerequisites Checklist

Check every item before starting. Missing even one will cause failures.

### On your local machine

```
[ ] Python 3.11 or higher installed
    Verify: python --version
    Need:   https://python.org/downloads

[ ] pip installed
    Verify: pip --version
    Need:   comes with Python

[ ] Git installed
    Verify: git --version
    Need:   https://git-scm.com

[ ] GitHub CLI installed and authenticated
    Verify: gh auth status
    Need:   https://cli.github.com
    Setup:  gh auth login

[ ] Docker Desktop installed and RUNNING
    Verify: docker ps
    Need:   https://docker.com/products/docker-desktop
    Note:   Must be running, not just installed

[ ] kubectl installed
    Verify: kubectl version --client
    Need:   https://kubernetes.io/docs/tasks/tools
```

### Cloud-specific (install only for your cloud)

```
IF USING AWS:
  [ ] AWS CLI v2 installed
      Verify: aws --version
      Need:   https://aws.amazon.com/cli

  [ ] AWS credentials configured
      Verify: aws sts get-caller-identity
      Need:   aws configure

IF USING GCP:
  [ ] gcloud CLI installed
      Verify: gcloud --version
      Need:   https://cloud.google.com/sdk/docs/install

  [ ] gcloud authenticated
      Verify: gcloud auth list
      Need:   gcloud auth login

IF USING AZURE:
  [ ] Azure CLI installed
      Verify: az --version
      Need:   https://docs.microsoft.com/cli/azure/install-azure-cli

  [ ] Azure authenticated
      Verify: az account show
      Need:   az login
```

### For cluster setup (ArgoCD bootstrap)

```
[ ] kubectl connected to your cluster
    Verify: kubectl get nodes
    Must show: nodes in Ready state

[ ] You have cluster-admin permissions
    Verify: kubectl auth can-i create namespace --all-namespaces
    Must show: yes
```

---

## 2. Accounts & Permissions Required

### GitHub account

| Permission | Why needed |
|------------|-----------|
| Create repository | If creating a new GitHub repo |
| Write to repository | Pushing generated files |
| Create GitHub Actions secrets | Storing cloud credentials |
| Create Environments | For `production-approval` gate |
| Admin on GitOps repo | CI writes manifest commits to it |

### Cloud account

**AWS:**
| Permission | Why needed |
|------------|-----------|
| ECR: CreateRepository, GetAuthorizationToken, BatchCheckLayerAvailability, PutImage | Pushing Docker images |
| EKS: DescribeCluster | CI connects to cluster |
| IAM: CreateRole (for OIDC setup) | GitHub Actions OIDC role |

**GCP:**
| Permission | Why needed |
|------------|-----------|
| Artifact Registry / Container Registry write | Pushing Docker images |
| GKE: container.clusters.get | CI connects to cluster |
| iam.workloadIdentityPools (for Workload Identity) | Keyless auth from GitHub |

**Azure:**
| Permission | Why needed |
|------------|-----------|
| AcrPush role on ACR | Pushing Docker images |
| AKS: Azure Kubernetes Service Cluster User Role | CI connects to cluster |
| Service Principal creation | GitHub Actions auth |

### Anthropic (for AI eval gates)

| Requirement | Details |
|-------------|---------|
| Anthropic API key | Used by eval judge (Claude) |
| Billing enabled | Evals make API calls — costs ~$0.05–$0.50 per CI run depending on dataset size |
| Rate limits | Default: 50 RPM on Sonnet — sufficient for eval suite |

---

## 3. Exactly What Changes in Your Project

### Files CREATED (new files added to your project)

```
generate_cicd.py                    ← the generator script
requirements-generator.txt          ← PyYAML only
cicd.config.yaml                    ← your pipeline configuration

.github/
  workflows/
    ci.yml                          ← new CI pipeline
    cd-staging.yml                  ← new staging validation
    cd-production.yml               ← new production monitor

k8s/
  base/
    deployment.yaml                 ← Kubernetes Deployment
    service.yaml                    ← Kubernetes Service
    hpa.yaml                        ← Auto-scaling rules
    pdb.yaml                        ← Pod disruption budget
    networkpolicy.yaml              ← Firewall rules
    ingress.yaml                    ← HTTP routing
    canary-services.yaml            ← Stable + canary services
    kustomization.yaml              ← Base resource list
  overlays/
    staging/
      kustomization.yaml            ← Staging image tag (updated by CI)
      patch-deployment.yaml         ← Staging overrides
    production/
      kustomization.yaml            ← Production image tag (updated by CD)
      patch-rollout.yaml            ← Canary rollout config

argocd/
  app-staging.yaml                  ← ArgoCD staging application
  app-production.yaml               ← ArgoCD production application
  rollout-production.yaml           ← Argo Rollout canary definition
  analysis-template.yaml            ← Canary health checks

evals/
  run_evals.py                      ← Eval orchestrator
  thresholds.yaml                   ← Gate thresholds
  prompt_regression.py              ← Gate 1
  tool_validation.py                ← Gate 2
  rag_eval.py                       ← Gate 3
  hallucination_check.py            ← Gate 4
  safety_check.py                   ← Gate 5
  latency_cost_gate.py              ← Gates 6 + 7
  datasets/
    prompt_regression_dataset.json  ← Sample test cases
    tool_call_dataset.json          ← Sample tool tests
    rag_dataset.json                ← Sample RAG tests
    safety_dataset.json             ← Sample safety tests

monitoring/
  servicemonitor.yaml               ← Prometheus scrape config
  alerting-rules.yaml               ← 5 alerting rules

Dockerfile                          ← App container definition
Makefile                            ← Convenience commands
scripts/
  bootstrap-argocd.sh               ← One-time cluster setup
  setup-secrets.sh                  ← GitHub secrets helper
.gitignore                          ← Standard ignore rules
```

### Files OVERWRITTEN (existing files replaced)

```
Dockerfile          ← REPLACED with language-specific multi-stage build
Makefile            ← REPLACED with pipeline commands
.gitignore          ← REPLACED with standard ignore rules
.github/workflows/* ← ALL REPLACED with generated workflows
k8s/**              ← ALL REPLACED with generated manifests
argocd/**           ← ALL REPLACED with generated configs
monitoring/**       ← ALL REPLACED with generated monitoring
evals/thresholds.yaml ← REPLACED with your config thresholds
```

**Action required before running:**
```bash
# Back up anything you want to keep
cp Dockerfile Dockerfile.backup
cp Makefile Makefile.backup
cp -r .github/workflows/ .github/workflows.backup/ 2>/dev/null || true
cp -r k8s/ k8s.backup/ 2>/dev/null || true
```

### Files NEVER TOUCHED (always safe)

```
app/**              ← your application code
src/**              ← your source files
lib/**              ← your libraries
tests/**            ← your existing tests
requirements.txt    ← your Python dependencies
package.json        ← your Node.js config
package-lock.json   ← your lock file
node_modules/       ← your Node modules
pom.xml             ← your Maven config
build.gradle        ← your Gradle config
go.mod              ← your Go modules
go.sum              ← your Go checksums
*.csproj            ← your .NET project
*.sln               ← your solution file
.env                ← your environment variables
.env.*              ← any env files
README.md           ← your readme
*.md (custom)       ← your markdown files
database/**         ← your database files
config/**           ← your config files
```

---

## 4. Exactly What Changes in GitHub

### After running `python generate_cicd.py --init`

Nothing changes in GitHub yet. Changes are only local.

### After running `git push`

| What changes | Where | Reversible? |
|-------------|-------|-------------|
| New files committed to repository | GitHub repo | Yes — git revert |
| GitHub Actions workflows active | GitHub Actions tab | Yes — delete workflow files |
| CI pipeline triggers on next push | Automatic | Yes — disable in repo settings |

### After running `bash scripts/setup-secrets.sh`

| What changes | Where | Reversible? |
|-------------|-------|-------------|
| New secrets stored | GitHub repo → Settings → Secrets | Yes — delete individually |
| Secrets are encrypted | GitHub stores them encrypted | Cannot read back — only overwrite |

**Important:** Secrets are write-only. Once set, you cannot see their values again
in GitHub. Keep a secure copy of all secret values (password manager, vault).

### After creating `production-approval` environment in GitHub

| What changes | Where | Reversible? |
|-------------|-------|-------------|
| New environment created | GitHub repo → Settings → Environments | Yes — delete environment |
| Required reviewers set | Environment settings | Yes — remove reviewers |
| All production promotions require approval | Every CD run | Yes — remove environment protection |

---

## 5. Exactly What Changes in Your Cluster

### After running `bash scripts/bootstrap-argocd.sh`

| What gets created | Namespace | Reversible? |
|------------------|-----------|-------------|
| ArgoCD deployment (10+ pods) | `argocd` | Yes — kubectl delete namespace argocd |
| Argo Rollouts controller | `argo-rollouts` | Yes — kubectl delete namespace argo-rollouts |
| New namespace: staging | cluster | Yes — kubectl delete namespace staging |
| New namespace: production | cluster | Yes — kubectl delete namespace production |
| ArgoCD Application: staging | `argocd` | Yes — argocd app delete |
| ArgoCD Application: production | `argocd` | Yes — argocd app delete |
| AnalysisTemplate | `production` | Yes — kubectl delete analysistemplate |

**Resource usage after bootstrap:**

| Component | CPU request | Memory request |
|-----------|-------------|----------------|
| ArgoCD (all pods) | ~500m | ~512Mi |
| Argo Rollouts controller | ~100m | ~128Mi |
| Your app (staging) | 100m (1 replica) | 256Mi |
| Your app (production) | 500m × 4 replicas = 2000m | 1Gi × 4 = 4Gi |
| **Total added to cluster** | **~2700m (~2.7 CPU cores)** | **~4.9 Gi** |

Ensure your cluster has at least this much free capacity before bootstrapping.

### After first deployment

| What gets created | Namespace | Notes |
|------------------|-----------|-------|
| Your app Deployment | staging | 1 replica |
| Your app Deployment/Rollout | production | 4 replicas (canary managed) |
| ConfigMap | staging + production | App configuration |
| Secret (you create this) | staging + production | App secrets |
| HPA | staging + production | Auto-scales 2–10 pods |
| PodDisruptionBudget | staging + production | Keeps min 1 pod alive |
| NetworkPolicy | staging + production | Restricts inbound traffic |
| Ingress | staging + production | HTTP routing |

---

## 6. Cost Impact

### GitHub Actions minutes

| Job | Average duration | Minutes used per PR |
|-----|-----------------|---------------------|
| unit-test | 2 min | 2 |
| docker-build | 4 min (with cache) | 4 |
| security-scan | 2 min | 2 |
| ai-evals | 5–10 min | 8 |
| push-image | 2 min | 2 |
| update-manifest | 1 min | 1 |
| **Total per PR** | | **~19 min** |

GitHub Free: 2,000 min/month. GitHub Pro: 3,000 min/month.
With 50 PRs/month: 50 × 19 = 950 minutes → fits in free tier.

### Anthropic API costs (eval gates)

| Eval gate | Approx API calls per run | Approx cost |
|-----------|--------------------------|-------------|
| Prompt regression (5 cases) | 10 calls (5 agent + 5 judge) | $0.01 |
| Tool validation (3 cases) | 3 calls | $0.005 |
| RAG eval (3 cases) | 9 calls (3 agent + 6 judge) | $0.015 |
| Hallucination check (5 cases) | 10 calls | $0.01 |
| Safety check (8 cases) | 16 calls | $0.02 |
| Latency/cost gate (10 prompts) | 10 calls | $0.01 |
| **Total per CI run** | **~58 calls** | **~$0.07** |

With 50 CI runs/month: ~$3.50/month on Anthropic API.
With 200 CI runs/month: ~$14/month.

### Cloud infrastructure

| Resource | AWS cost estimate | GCP cost estimate | Azure cost estimate |
|----------|------------------|-------------------|---------------------|
| Container registry storage | $0.10/GB/month | $0.10/GB/month | $0.003/GB/day |
| ArgoCD pods (2.7 CPU cores) | ~$60–120/month (t3.medium) | ~$50–100/month | ~$60–120/month |
| Your app pods (staging + prod) | Depends on instance type | Depends on instance type | Depends |

**Minimum cluster size recommendation:** 3 nodes of t3.medium (AWS) / e2-standard-2 (GCP) / Standard_D2s_v3 (Azure)

---

## 7. Impact on Your Team

### What changes for developers

| Before | After |
|--------|-------|
| Push directly to main | PRs go through CI gate (eval gates must pass) |
| Deployment is manual | Staging auto-deploys on every merge to main |
| No eval feedback on PRs | Eval results posted as PR comment automatically |
| No safety checks | Safety gate blocks unsafe agent changes |
| Production deploy = kubectl apply | Production deploy = ArgoCD sync + canary |

### What developers need to know

1. **PRs take longer** — eval gates add ~8 minutes to CI time
2. **Merge is blocked if evals fail** — fix the agent, don't lower the threshold
3. **Staging always reflects main** — developers can test against staging URL
4. **Production needs manual approval** — one team member must approve in GitHub UI
5. **Production uses canary** — rollout takes 15–20 minutes to complete fully

### What DevOps/platform engineers need to do (one-time)

1. Run `bash scripts/bootstrap-argocd.sh` once per cluster
2. Create `production-approval` environment in GitHub with required reviewers
3. Set up GitHub Actions secrets via `bash scripts/setup-secrets.sh`
4. Create app secrets in staging and production namespaces
5. Configure ArgoCD notifications (optional — for Slack alerts)

---

## 8. Known Issues & Fixes

### Issue 1: `docker: Error response from daemon`
**Cause:** Docker Desktop is not running.
**Fix:**
```bash
# Windows: Start Docker Desktop from the Start menu
# Mac: Open Docker Desktop application
# Linux: sudo systemctl start docker

# Verify it's running:
docker ps
```

---

### Issue 2: `401 Unauthorized` when building Docker image
**Cause:** Docker Hub login expired. Needed to pull base images (python:3.11-slim, node:20-alpine, etc.).
**Fix:**
```bash
docker login
# Enter your Docker Hub username and password
# If you don't have a Docker Hub account: https://hub.docker.com/signup
```

---

### Issue 3: GitHub Actions fails — `secret not found`
**Cause:** Required secrets not set in GitHub.
**Fix:**
```bash
bash scripts/setup-secrets.sh
# Or set manually:
gh secret set ANTHROPIC_API_KEY --body "sk-ant-..."
gh secret set AWS_ROLE_ARN --body "arn:aws:iam::..."
# (see CLAUDE.md for full secrets list)
```

---

### Issue 4: ArgoCD app stuck `OutOfSync` — never syncs staging
**Cause 1:** GitOps repo URL incorrect in `argocd/app-staging.yaml`.
**Fix:**
```bash
# Check what URL was generated
grep repoURL argocd/app-staging.yaml
# Fix in cicd.config.yaml:
#   gitops.repo: "correct-org/correct-repo"
# Re-generate:
python generate_cicd.py
git add argocd/ && git commit -m "fix: correct gitops repo url" && git push
```

**Cause 2:** ArgoCD cannot access the GitOps repo (private repo, no credentials).
**Fix:**
```bash
# Add repo credentials to ArgoCD
argocd repo add https://github.com/your-org/your-gitops-repo \
  --username your-username \
  --password your-github-pat
```

---

### Issue 5: Eval gates fail — all scores 0.0
**Cause:** `ANTHROPIC_API_KEY` not set or invalid.
**Fix:**
```bash
# Locally:
export ANTHROPIC_API_KEY=sk-ant-...
python evals/run_evals.py --config evals/thresholds.yaml

# In GitHub Actions:
gh secret set ANTHROPIC_API_KEY --body "sk-ant-..."
```

---

### Issue 6: Eval gates fail — scores below threshold
**Cause:** Your agent does not yet meet the default thresholds, which is normal on first integration.
**Fix — Option A:** Lower thresholds temporarily, raise them over time.
```yaml
# cicd.config.yaml
evals:
  thresholds:
    prompt_regression: 0.70    # start lower
    safety: 0.95               # keep safety high
    latency_p95_ms: 30000      # generous latency
```
```bash
python generate_cicd.py
git add evals/thresholds.yaml cicd.config.yaml && git commit -m "ci: adjust initial thresholds" && git push
```

**Fix — Option B:** Improve your eval datasets to match your actual agent.
Replace `evals/datasets/prompt_regression_dataset.json` with questions
your agent actually handles.

---

### Issue 7: `kubectl: connection refused` or `no server found`
**Cause:** kubectl not connected to cluster.
**Fix:**
```bash
# AWS EKS:
aws eks update-kubeconfig --name YOUR_CLUSTER_NAME --region YOUR_REGION

# GCP GKE:
gcloud container clusters get-credentials YOUR_CLUSTER --region YOUR_REGION

# Azure AKS:
az aks get-credentials --resource-group YOUR_RG --name YOUR_CLUSTER

# Verify:
kubectl get nodes
```

---

### Issue 8: Pods stuck in `ImagePullBackOff`
**Cause:** Image registry credentials not available in the namespace.
**Fix:**
```bash
# Check the error:
kubectl describe pod <pod-name> -n staging | grep -A 5 "Events"

# For AWS ECR — ensure the node IAM role has ECR pull permissions
# For GCP GCR — ensure the k8s service account has Storage Object Viewer role
# For Azure ACR — ensure the AKS kubelet identity has AcrPull role

# Quick fix for any registry — create an image pull secret:
kubectl create secret docker-registry regcred \
  --docker-server=YOUR_REGISTRY \
  --docker-username=YOUR_USERNAME \
  --docker-password=YOUR_PASSWORD \
  --namespace staging

kubectl patch serviceaccount default \
  -p '{"imagePullSecrets": [{"name": "regcred"}]}' \
  --namespace staging
```

---

### Issue 9: Canary rollout stuck at 10%, never advances
**Cause:** AnalysisRun is failing — Prometheus not installed or eval service not reachable.
**Fix — Option A:** Check AnalysisRun status.
```bash
kubectl get analysisruns -n production
kubectl describe analysisrun <name> -n production | grep -A 10 "Message"
```

**Fix — Option B:** Skip AnalysisTemplate for first deployment.
Edit `argocd/rollout-production.yaml`, remove the `analysis:` blocks:
```yaml
steps:
  - setWeight: 10
  - pause: {duration: 5m}
  # Remove the analysis block for first deployment
  - setWeight: 30
  - pause: {duration: 5m}
  - setWeight: 100
```
Commit and push. Manually promote with:
```bash
kubectl argo rollouts promote my-app -n production
```

---

### Issue 10: `production-approval` gate never appears in GitHub Actions
**Cause:** The `production-approval` environment was not created in GitHub.
**Fix:**
1. Go to your GitHub repo → **Settings** → **Environments**
2. Click **New environment**
3. Name it exactly: `production-approval` (case-sensitive)
4. Add required reviewers
5. Save

---

### Issue 11: `generator: command not found` or `ModuleNotFoundError: yaml`
**Cause:** PyYAML not installed.
**Fix:**
```bash
pip install -r requirements-generator.txt
# or directly:
pip install PyYAML
```

---

### Issue 12: Generated files have wrong app name everywhere
**Cause:** Wrong app name entered in wizard.
**Fix:** Re-run the generator:
```bash
# Edit cicd.config.yaml
# Change: app.name: wrong-name  →  app.name: correct-name
python generate_cicd.py
git add . && git commit -m "fix: correct app name" && git push
```
All 35 files regenerate with the correct name in seconds.

---

### Issue 13: CI passes but staging never gets the new image
**Cause 1:** `update-staging-manifest` job failed silently.
**Check:**
```bash
# In GitHub Actions, look at the update-staging-manifest job logs
# Common cause: GITOPS_TOKEN has expired or has insufficient permissions
gh secret set GITOPS_TOKEN --body "ghp_your_new_token"
```

**Cause 2:** ArgoCD polling interval (default 3 min) has not elapsed yet.
**Fix:** Force sync manually:
```bash
argocd app sync your-app-staging
```

---

### Issue 14: Argo Rollout not found — `kubectl argo rollouts: command not found`
**Cause:** Argo Rollouts kubectl plugin not installed.
**Fix:**
```bash
# Linux/Mac:
curl -LO https://github.com/argoproj/argo-rollouts/releases/latest/download/kubectl-argo-rollouts-linux-amd64
chmod +x kubectl-argo-rollouts-linux-amd64
sudo mv kubectl-argo-rollouts-linux-amd64 /usr/local/bin/kubectl-argo-rollouts

# Verify:
kubectl argo rollouts version
```

---

## 9. How to Undo Everything

### Undo 1: Remove generated files from your project

```bash
# Remove all generated pipeline files (keeps your app code)
rm -rf .github/workflows/ k8s/ argocd/ evals/ monitoring/ scripts/
rm -f Dockerfile Makefile generate_cicd.py requirements-generator.txt cicd.config.yaml

# Restore your backups if you made them
cp Dockerfile.backup Dockerfile 2>/dev/null || true
cp Makefile.backup Makefile 2>/dev/null || true
cp -r .github/workflows.backup/ .github/workflows/ 2>/dev/null || true
```

---

### Undo 2: Remove from GitHub

```bash
# Revert the commit that added the pipeline
git log --oneline | head -5           # find the commit SHA
git revert <sha>                       # creates a new revert commit
git push

# Or if not yet pushed — reset locally
git reset --hard HEAD~1                # removes last commit
```

---

### Undo 3: Remove GitHub secrets

```bash
# List all secrets
gh secret list

# Delete specific secrets
gh secret delete ANTHROPIC_API_KEY
gh secret delete AWS_ROLE_ARN
# ... repeat for each secret
```

---

### Undo 4: Remove from Kubernetes cluster

```bash
# Remove ArgoCD (removes all ArgoCD-managed resources too)
kubectl delete namespace argocd

# Remove Argo Rollouts
kubectl delete namespace argo-rollouts

# Remove app namespaces (CAUTION: deletes all workloads in these namespaces)
kubectl delete namespace staging
kubectl delete namespace production

# Remove monitoring
kubectl delete -f monitoring/servicemonitor.yaml
kubectl delete -f monitoring/alerting-rules.yaml
```

---

### Undo 5: Remove GitHub environment

1. Go to repo → **Settings** → **Environments**
2. Click `production-approval`
3. Click **Delete environment**

---

### Complete rollback sequence

```bash
# 1. Stop the pipeline (disable GitHub Actions)
gh api repos/OWNER/REPO/actions/workflows \
  | python -c "import sys,json; [print(w['id']) for w in json.load(sys.stdin)['workflows']]" \
  | xargs -I{} gh api repos/OWNER/REPO/actions/workflows/{}/disable -X PUT

# 2. Remove from cluster
kubectl delete namespace argocd argo-rollouts staging production

# 3. Remove generated files locally
rm -rf .github/workflows/ k8s/ argocd/ evals/ monitoring/ scripts/
rm -f Dockerfile Makefile generate_cicd.py requirements-generator.txt cicd.config.yaml

# 4. Commit the removal
git add .
git commit -m "revert: remove CI/CD pipeline"
git push

# 5. Remove secrets
bash -c 'for s in ANTHROPIC_API_KEY GITOPS_TOKEN GITOPS_REPO ARGOCD_SERVER ARGOCD_TOKEN \
  AWS_ROLE_ARN AWS_REGION EKS_CLUSTER_NAME STAGING_BASE_URL PRODUCTION_BASE_URL; do
  gh secret delete $s 2>/dev/null && echo "Deleted $s"
done'
```

Everything is back to how it was. No permanent changes.

---

## 10. Pre-Run Validation Checklist

Complete every item before running `python generate_cicd.py --init`.

### Local machine

```
[ ] python --version          → shows 3.11 or higher
[ ] docker ps                 → shows running containers (daemon is up)
[ ] git --version             → shows any version
[ ] gh auth status            → shows "Logged in to github.com"
[ ] kubectl get nodes         → shows cluster nodes as Ready
```

### Cloud

```
AWS:
  [ ] aws sts get-caller-identity   → shows your account ID
  [ ] aws ecr describe-repositories → no permission errors

GCP:
  [ ] gcloud auth list          → shows active account
  [ ] gcloud projects list      → shows your project

Azure:
  [ ] az account show           → shows your subscription
  [ ] az acr list               → shows your registry
```

### Cluster capacity

```
[ ] kubectl top nodes         → check available CPU and memory
    Minimum needed: 3 CPU cores + 5Gi memory free
    (for ArgoCD + your app in staging + production)
```

### Before pushing to GitHub

```
[ ] Backed up existing Dockerfile (if custom)
[ ] Backed up existing Makefile (if custom)
[ ] Backed up existing .github/workflows/ (if exists)
[ ] Backed up existing k8s/ (if exists)
[ ] Noted your existing app port (for wizard answer)
[ ] Have your cloud account ID / project ID / registry name ready
[ ] Have your GitOps repo name ready (org/repo format)
[ ] Have your Anthropic API key ready
[ ] Have staging and production URLs ready (or placeholders for now)
```

### Cost acknowledgment

```
[ ] Aware that eval gates use Anthropic API (~$0.07 per CI run)
[ ] Aware that ArgoCD adds ~2.7 CPU cores and ~5Gi memory to cluster
[ ] Aware that Docker Hub login required for building base images
```

---

## Summary — 3 Things That Most Often Cause Problems

| Problem | How to prevent it |
|---------|------------------|
| **Docker not running** | Start Docker Desktop BEFORE running any command |
| **Missing GitHub secrets** | Run `bash scripts/setup-secrets.sh` immediately after generating |
| **Eval thresholds too strict for first run** | Set `prompt_regression: 0.70` in `cicd.config.yaml` for first integration, tighten later |

---

*Repository: [bonganiajay26/AGENTIC-CICD](https://github.com/bonganiajay26/AGENTIC-CICD)*
