#!/usr/bin/env python3
"""
Golden CI/CD Generator
======================
One command generates a complete CI/CD pipeline for ANY application on ANY cloud.

Usage:
    python generate_cicd.py                          # generate from cicd.config.yaml
    python generate_cicd.py --config path/to/config  # custom config path
    python generate_cicd.py --detect                 # show auto-detected values only
    python generate_cicd.py --dry-run                # print files without writing
"""

import argparse
import os
import sys
from pathlib import Path

import yaml

# ─────────────────────────────────────────────────────────────────────────────
# Auto-Detection
# ─────────────────────────────────────────────────────────────────────────────

LANGUAGE_SIGNALS = {
    "python":  ["requirements.txt", "setup.py", "pyproject.toml", "Pipfile"],
    "node":    ["package.json"],
    "java":    ["pom.xml", "build.gradle", "build.gradle.kts"],
    "go":      ["go.mod"],
    "dotnet":  [".csproj", ".sln", "*.csproj"],
}

TEST_COMMANDS = {
    "python": "pytest tests/unit/ -v --junitxml=reports/unit-test-results.xml",
    "node":   "npm test -- --ci --reporters=default",
    "java":   "mvn test -B",
    "go":     "go test ./... -v",
    "dotnet": "dotnet test --logger trx",
    "generic":"echo 'No test command configured'",
}

BUILD_SETUP_STEPS = {
    "python": """\
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: pip
      - name: Install dependencies
        run: pip install -r requirements.txt""",

    "node": """\
      - name: Set up Node.js
        uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: npm
      - name: Install dependencies
        run: npm ci""",

    "java": """\
      - name: Set up JDK 21
        uses: actions/setup-java@v4
        with:
          java-version: "21"
          distribution: temurin
          cache: maven""",

    "go": """\
      - name: Set up Go
        uses: actions/setup-go@v5
        with:
          go-version: "1.22"
          cache: true""",

    "dotnet": """\
      - name: Set up .NET
        uses: actions/setup-dotnet@v4
        with:
          dotnet-version: "8.0.x\"""",

    "generic": """\
      - name: Set up build environment
        run: echo "Add your build setup steps here" """,
}


def detect_language(project_root: Path) -> str:
    for lang, signals in LANGUAGE_SIGNALS.items():
        for signal in signals:
            if signal.startswith("*"):
                ext = signal[1:]
                if any(p.suffix == ext for p in project_root.iterdir() if p.is_file()):
                    return lang
            elif (project_root / signal).exists():
                return lang
    return "generic"


# ─────────────────────────────────────────────────────────────────────────────
# Cloud Configuration
# ─────────────────────────────────────────────────────────────────────────────

def resolve_registry_url(cfg: dict) -> str:
    provider = cfg["cloud"]["provider"]
    app_name = cfg["app"]["name"]
    if provider == "aws":
        aws = cfg["cloud"]["aws"]
        return f"{aws['account_id']}.dkr.ecr.{aws['region']}.amazonaws.com/{app_name}"
    elif provider == "gcp":
        gcp = cfg["cloud"]["gcp"]
        if gcp.get("artifact_registry"):
            return f"{gcp['region']}-docker.pkg.dev/{gcp['project_id']}/{app_name}/{app_name}"
        return f"gcr.io/{gcp['project_id']}/{app_name}"
    elif provider == "azure":
        azure = cfg["cloud"]["azure"]
        return f"{azure['registry_name']}.azurecr.io/{app_name}"
    else:
        return cfg["cloud"]["generic"]["registry_url"] + f"/{app_name}"


def registry_login_steps(cfg: dict) -> str:
    provider = cfg["cloud"]["provider"]
    if provider == "aws":
        auth = cfg["cloud"]["aws"].get("auth_method", "oidc")
        if auth == "oidc":
            return """\
      - name: Configure AWS credentials (OIDC)
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ secrets.AWS_ROLE_ARN }}
          aws-region: ${{ secrets.AWS_REGION }}
      - name: Login to Amazon ECR
        id: login-ecr
        uses: aws-actions/amazon-ecr-login@v2"""
        else:
            return """\
      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
          aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          aws-region: ${{ secrets.AWS_REGION }}
      - name: Login to Amazon ECR
        id: login-ecr
        uses: aws-actions/amazon-ecr-login@v2"""

    elif provider == "gcp":
        auth = cfg["cloud"]["gcp"].get("auth_method", "workload_identity")
        if auth == "workload_identity":
            return """\
      - name: Authenticate to Google Cloud (Workload Identity)
        uses: google-github-actions/auth@v2
        with:
          workload_identity_provider: ${{ secrets.GCP_WORKLOAD_IDENTITY_PROVIDER }}
          service_account: ${{ secrets.GCP_SERVICE_ACCOUNT }}
      - name: Configure Docker for GCR/AR
        run: gcloud auth configure-docker ${{ secrets.REGISTRY_URL }} --quiet"""
        else:
            return """\
      - name: Authenticate to Google Cloud (Service Account Key)
        uses: google-github-actions/auth@v2
        with:
          credentials_json: ${{ secrets.GCP_SA_KEY }}
      - name: Configure Docker for GCR/AR
        run: gcloud auth configure-docker ${{ secrets.REGISTRY_URL }} --quiet"""

    elif provider == "azure":
        return """\
      - name: Login to Azure
        uses: azure/login@v2
        with:
          creds: ${{ secrets.AZURE_CREDENTIALS }}
      - name: Login to Azure Container Registry
        uses: azure/docker-login@v1
        with:
          login-server: ${{ secrets.REGISTRY_URL }}
          username: ${{ secrets.REGISTRY_USERNAME }}
          password: ${{ secrets.REGISTRY_PASSWORD }}"""

    else:
        return """\
      - name: Login to container registry
        uses: docker/login-action@v3
        with:
          registry: ${{ secrets.REGISTRY_URL }}
          username: ${{ secrets.REGISTRY_USERNAME }}
          password: ${{ secrets.REGISTRY_PASSWORD }}"""


def kube_auth_steps(cfg: dict) -> str:
    cluster_type = cfg["kubernetes"].get("cluster_type", "generic")
    if cluster_type == "eks":
        return """\
      - name: Configure AWS credentials for EKS
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ secrets.AWS_ROLE_ARN }}
          aws-region: ${{ secrets.AWS_REGION }}
      - name: Update kubeconfig for EKS
        run: aws eks update-kubeconfig --name ${{ secrets.EKS_CLUSTER_NAME }} --region ${{ secrets.AWS_REGION }}"""
    elif cluster_type == "gke":
        return """\
      - name: Authenticate to GKE
        uses: google-github-actions/auth@v2
        with:
          workload_identity_provider: ${{ secrets.GCP_WORKLOAD_IDENTITY_PROVIDER }}
          service_account: ${{ secrets.GCP_SERVICE_ACCOUNT }}
      - name: Get GKE credentials
        uses: google-github-actions/get-gke-credentials@v2
        with:
          cluster_name: ${{ secrets.GKE_CLUSTER_NAME }}
          location: ${{ secrets.GKE_CLUSTER_LOCATION }}"""
    elif cluster_type == "aks":
        return """\
      - name: Login to Azure for AKS
        uses: azure/login@v2
        with:
          creds: ${{ secrets.AZURE_CREDENTIALS }}
      - name: Get AKS credentials
        uses: azure/aks-set-context@v3
        with:
          resource-group: ${{ secrets.AKS_RESOURCE_GROUP }}
          cluster-name: ${{ secrets.AKS_CLUSTER_NAME }}"""
    else:
        return """\
      - name: Configure kubectl
        run: echo "${{ secrets.KUBE_CONFIG }}" | base64 -d > $HOME/.kube/config && chmod 600 $HOME/.kube/config"""


def canary_steps_yaml(cfg: dict) -> str:
    canary = cfg["kubernetes"]["production"]["canary"]
    steps_list = canary.get("steps", [10, 30, 60, 100])
    pause = canary.get("pause_duration", "5m")
    lines = []
    for i, weight in enumerate(steps_list):
        lines.append(f"        - setWeight: {weight}")
        if weight < 100:
            lines.append(f"        - pause: {{duration: {pause}}}")
            lines.append("        - analysis:")
            lines.append("            templates:")
            lines.append("              - templateName: ai-eval-analysis")
    return "\n".join(lines)


def traffic_routing_yaml(cfg: dict) -> str:
    router = cfg["kubernetes"]["production"]["canary"].get("traffic_router", "nginx")
    app = cfg["app"]["name"]
    if router == "nginx":
        return f"""\
      trafficRouting:
        nginx:
          stableIngress: {app}-ingress"""
    elif router == "alb":
        return f"""\
      trafficRouting:
        alb:
          ingress: {app}-ingress
          servicePort: 80"""
    elif router == "istio":
        return f"""\
      trafficRouting:
        istio:
          virtualService:
            name: {app}-vs"""
    return ""


# ─────────────────────────────────────────────────────────────────────────────
# Template Renderer
# ─────────────────────────────────────────────────────────────────────────────

def render(template: str, **subs) -> str:
    result = template
    for key, value in subs.items():
        result = result.replace(f"__{key}__", str(value))
    return result


# ─────────────────────────────────────────────────────────────────────────────
# GitHub Actions Templates
# ─────────────────────────────────────────────────────────────────────────────

def tpl_ci(s: dict) -> str:
    eval_job = ""
    if s["EVALS_ENABLED"] == "true":
        eval_job = """
  # ── AI Eval Gates ─────────────────────────────────────────
  ai-evals:
    name: AI Eval Gates
    runs-on: ubuntu-latest
    needs: unit-test
    env:
      ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
      EVAL_ENV: ci
    steps:
      - uses: actions/checkout@v4
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: pip
      - name: Install eval dependencies
        run: pip install -r requirements.txt
      - name: Run full eval suite
        run: |
          python evals/run_evals.py \\
            --config evals/thresholds.yaml \\
            --output reports/eval-results.json \\
            --fail-fast true
      - name: Upload eval report
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: eval-report
          path: reports/eval-results.json
      - name: Comment eval results on PR
        if: github.event_name == 'pull_request'
        uses: actions/github-script@v7
        with:
          script: |
            const fs = require('fs');
            const results = JSON.parse(fs.readFileSync('reports/eval-results.json', 'utf8'));
            const passed = results.overall_passed;
            const body = `## ${passed ? '✅' : '❌'} AI Eval Gate Results\\n\\n` +
              `| Check | Score | Threshold | Status |\\n` +
              `|-------|-------|-----------|--------|\\n` +
              results.checks.map(c =>
                `| ${c.name} | ${c.score.toFixed(3)} | ${c.threshold} | ${c.passed ? '✅' : '❌'} |`
              ).join('\\n') +
              `\\n\\n**Overall: ${passed ? 'PASSED' : 'FAILED — build blocked'}**`;
            github.rest.issues.createComment({
              issue_number: context.issue.number,
              owner: context.repo.owner,
              repo: context.repo.repo,
              body
            });
"""
        eval_needs = ", ai-evals"
    else:
        eval_needs = ""

    return render("""# AUTO-GENERATED by generate_cicd.py — do not edit directly.
# Re-generate: python generate_cicd.py
name: CI — Build · Test · Eval · Push

on:
  pull_request:
    branches: [main, develop]
  push:
    branches: [main, develop]

env:
  IMAGE_NAME: __REGISTRY_URL__
  IMAGE_TAG: ${{ github.sha }}

jobs:
  # ── Unit Tests ────────────────────────────────────────────
  unit-test:
    name: Unit Tests
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
__LANG_SETUP__
      - name: Run unit tests
        run: __TEST_CMD__
      - name: Upload test report
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: unit-test-report
          path: reports/

  # ── Docker Build ──────────────────────────────────────────
  docker-build:
    name: Docker Build
    runs-on: ubuntu-latest
    needs: unit-test
    steps:
      - uses: actions/checkout@v4
      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3
      - name: Build image (cache, no push)
        uses: docker/build-push-action@v5
        with:
          context: .
          push: false
          tags: __REGISTRY_URL__:${{ github.sha }}
          cache-from: type=gha
          cache-to: type=gha,mode=max
          outputs: type=docker,dest=/tmp/image.tar
      - name: Upload image artifact
        uses: actions/upload-artifact@v4
        with:
          name: docker-image
          path: /tmp/image.tar
          retention-days: 1

  # ── Security Scan ─────────────────────────────────────────
  security-scan:
    name: Security Scan (Trivy)
    runs-on: ubuntu-latest
    needs: docker-build
    steps:
      - uses: actions/checkout@v4
      - name: Download image
        uses: actions/download-artifact@v4
        with:
          name: docker-image
          path: /tmp
      - name: Load image
        run: docker load --input /tmp/image.tar
      - name: Trivy vulnerability scan
        uses: aquasecurity/trivy-action@master
        with:
          image-ref: __REGISTRY_URL__:${{ github.sha }}
          format: sarif
          output: trivy-results.sarif
          severity: CRITICAL,HIGH
          exit-code: "1"
      - name: Upload Trivy SARIF
        if: always()
        uses: github/codeql-action/upload-sarif@v3
        with:
          sarif_file: trivy-results.sarif
__EVAL_JOB__
  # ── Push Image ────────────────────────────────────────────
  push-image:
    name: Push Docker Image
    runs-on: ubuntu-latest
    needs: [docker-build, security-scan__EVAL_NEEDS__]
    if: github.ref == 'refs/heads/main' || github.ref == 'refs/heads/develop'
    outputs:
      image_tag: ${{ github.sha }}
    steps:
      - uses: actions/checkout@v4
      - name: Download image
        uses: actions/download-artifact@v4
        with:
          name: docker-image
          path: /tmp
      - name: Load image
        run: docker load --input /tmp/image.tar
__REGISTRY_LOGIN__
      - name: Tag and push
        run: |
          docker tag __REGISTRY_URL__:${{ github.sha }} __REGISTRY_URL__:latest
          docker push __REGISTRY_URL__:${{ github.sha }}
          docker push __REGISTRY_URL__:latest

  # ── Update Staging Manifest (GitOps) ─────────────────────
  update-staging-manifest:
    name: Update Staging GitOps Manifest
    runs-on: ubuntu-latest
    needs: push-image
    if: github.ref == 'refs/heads/main'
    steps:
      - name: Checkout GitOps repo
        uses: actions/checkout@v4
        with:
          repository: ${{ secrets.GITOPS_REPO }}
          token: ${{ secrets.GITOPS_TOKEN }}
          path: gitops
      - name: Update image tag
        run: |
          cd gitops
          which kustomize && \\
            (cd k8s/overlays/staging && kustomize edit set image app=__REGISTRY_URL__:${{ github.sha }}) || \\
          sed -i "s|newTag:.*|newTag: ${{ github.sha }}|g" k8s/overlays/staging/kustomization.yaml
      - name: Commit manifest update
        run: |
          cd gitops
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add k8s/overlays/staging/
          git diff --staged --quiet || git commit -m "ci: update staging → ${{ github.sha }}"
          git push
""",
        REGISTRY_URL=s["REGISTRY_URL"],
        LANG_SETUP=s["LANG_SETUP"],
        TEST_CMD=s["TEST_CMD"],
        EVAL_JOB=eval_job,
        EVAL_NEEDS=eval_needs,
        REGISTRY_LOGIN=s["REGISTRY_LOGIN"],
    )


def tpl_cd_staging(s: dict) -> str:
    eval_block = ""
    if s["EVALS_ENABLED"] == "true":
        eval_block = """
  # ── Live AI Evals on Staging ──────────────────────────────
  staging-evals:
    name: Live AI Evals (Staging)
    runs-on: ubuntu-latest
    needs: smoke-tests
    steps:
      - uses: actions/checkout@v4
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: pip
      - name: Install dependencies
        run: pip install -r requirements.txt
      - name: Run live evals against staging
        env:
          AGENT_BASE_URL: ${{ secrets.STAGING_BASE_URL }}
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          EVAL_ENV: staging
        run: |
          python evals/run_evals.py \\
            --config evals/thresholds.yaml \\
            --mode live \\
            --base-url ${{ secrets.STAGING_BASE_URL }} \\
            --output reports/staging-eval-results.json
      - name: Upload staging eval report
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: staging-eval-report
          path: reports/staging-eval-results.json
"""
        approve_needs = "staging-evals"
    else:
        approve_needs = "smoke-tests"

    return render("""# AUTO-GENERATED by generate_cicd.py — do not edit directly.
name: CD — Staging Validation

on:
  workflow_dispatch:
    inputs:
      image_tag:
        description: Image tag to validate
        required: true
  repository_dispatch:
    types: [staging-sync-complete]

jobs:
  # ── Wait for ArgoCD Sync ──────────────────────────────────
  wait-for-sync:
    name: Wait for ArgoCD Staging Sync
    runs-on: ubuntu-latest
    steps:
      - name: Install ArgoCD CLI
        run: |
          curl -sSL -o /usr/local/bin/argocd \\
            https://github.com/argoproj/argo-cd/releases/latest/download/argocd-linux-amd64
          chmod +x /usr/local/bin/argocd
      - name: Login and wait
        run: |
          argocd login ${{ secrets.ARGOCD_SERVER }} \\
            --auth-token ${{ secrets.ARGOCD_TOKEN }} --insecure
          argocd app wait __APP_NAME__-staging --sync --health --timeout 300

  # ── Smoke Tests ───────────────────────────────────────────
  smoke-tests:
    name: Smoke Tests
    runs-on: ubuntu-latest
    needs: wait-for-sync
    steps:
      - uses: actions/checkout@v4
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: pip
      - name: Install dependencies
        run: pip install -r requirements.txt
      - name: Run smoke tests
        env:
          BASE_URL: ${{ secrets.STAGING_BASE_URL }}
        run: pytest tests/smoke/ -v --junitxml=reports/smoke-results.xml
      - name: Upload smoke report
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: smoke-report
          path: reports/smoke-results.xml
__EVAL_BLOCK__
  # ── Manual Approval Gate ──────────────────────────────────
  approve-production:
    name: Gate — Approve Production Promotion
    runs-on: ubuntu-latest
    needs: __APPROVE_NEEDS__
    environment:
      name: production-approval
    steps:
      - run: echo "Staging validated. Awaiting manual approval for production."

  # ── Promote to Production ─────────────────────────────────
  promote-to-production:
    name: Promote to Production (Canary)
    runs-on: ubuntu-latest
    needs: approve-production
    steps:
      - name: Checkout GitOps repo
        uses: actions/checkout@v4
        with:
          repository: ${{ secrets.GITOPS_REPO }}
          token: ${{ secrets.GITOPS_TOKEN }}
          path: gitops
      - name: Copy staging image tag to production overlay
        run: |
          cd gitops
          STAGING_TAG=$(grep 'newTag:' k8s/overlays/staging/kustomization.yaml | awk '{print $2}')
          which kustomize && \\
            (cd k8s/overlays/production && kustomize edit set image app=__REGISTRY_URL__:$STAGING_TAG) || \\
          sed -i "s|newTag:.*|newTag: $STAGING_TAG|g" k8s/overlays/production/kustomization.yaml
      - name: Commit and push
        run: |
          cd gitops
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add k8s/overlays/production/
          git diff --staged --quiet || git commit -m "cd: promote to production canary"
          git push
""",
        APP_NAME=s["APP_NAME"],
        REGISTRY_URL=s["REGISTRY_URL"],
        EVAL_BLOCK=eval_block,
        APPROVE_NEEDS=approve_needs,
    )


def tpl_cd_production(s: dict) -> str:
    rollback_issue = ""
    if s["ROLLBACK_ISSUES"] == "true":
        rollback_issue = """
      - name: Open GitHub issue on rollback
        uses: actions/github-script@v7
        with:
          script: |
            github.rest.issues.create({
              owner: context.repo.owner,
              repo: context.repo.repo,
              title: '🚨 Production rollback — canary eval failure',
              body: `## Production Rollback\\n\\nCanary failed eval gates and was rolled back automatically.\\n\\n**Run:** ${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}`,
              labels: ['production', 'rollback', 'incident']
            });"""

    return render("""# AUTO-GENERATED by generate_cicd.py — do not edit directly.
name: CD — Production Canary Monitor & Rollback

on:
  repository_dispatch:
    types: [production-rollout-started]
  workflow_dispatch:
    inputs:
      action:
        description: Canary action
        type: choice
        options: [monitor, promote, rollback]
        default: monitor

jobs:
  # ── Monitor Canary ────────────────────────────────────────
  monitor-canary:
    name: Monitor Canary Health
    runs-on: ubuntu-latest
    if: github.event.inputs.action != 'rollback'
    outputs:
      canary_healthy: ${{ steps.health.outputs.healthy }}
    steps:
      - uses: actions/checkout@v4
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: pip
      - name: Install dependencies
        run: pip install -r requirements.txt
__KUBE_AUTH__
      - name: Check Argo Rollout status
        run: |
          kubectl argo rollouts status __APP_NAME__ --namespace __PROD_NS__ --timeout 60s || true
      - name: Sample eval on canary traffic
        id: health
        env:
          AGENT_BASE_URL: ${{ secrets.PRODUCTION_BASE_URL }}
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          EVAL_ENV: production-canary
        run: |
          python evals/run_evals.py \\
            --config evals/thresholds.yaml \\
            --mode live \\
            --sample-rate 0.1 \\
            --base-url ${{ secrets.PRODUCTION_BASE_URL }} \\
            --output reports/canary-eval-results.json
          HEALTHY=$(python -c "import json; r=json.load(open('reports/canary-eval-results.json')); print('true' if r['overall_passed'] else 'false')")
          echo "healthy=$HEALTHY" >> $GITHUB_OUTPUT
      - name: Upload canary eval report
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: canary-eval-report
          path: reports/canary-eval-results.json

  # ── Promote ───────────────────────────────────────────────
  promote-canary:
    name: Promote Canary to 100%
    runs-on: ubuntu-latest
    needs: monitor-canary
    if: needs.monitor-canary.outputs.canary_healthy == 'true' && github.event.inputs.action != 'rollback'
    steps:
__KUBE_AUTH__
      - name: Promote rollout
        run: kubectl argo rollouts promote __APP_NAME__ --namespace __PROD_NS__

  # ── Rollback ──────────────────────────────────────────────
  rollback:
    name: Rollback Production
    runs-on: ubuntu-latest
    needs: monitor-canary
    if: needs.monitor-canary.outputs.canary_healthy == 'false' || github.event.inputs.action == 'rollback'
    steps:
__KUBE_AUTH__
      - name: Abort and rollback canary
        run: |
          kubectl argo rollouts abort __APP_NAME__ --namespace __PROD_NS__
          kubectl argo rollouts undo __APP_NAME__ --namespace __PROD_NS__
      - name: Annotate rollback failure
        run: echo "::error::Canary eval gates failed — rolled back to stable."
__ROLLBACK_ISSUE__
""",
        APP_NAME=s["APP_NAME"],
        PROD_NS=s["PROD_NS"],
        KUBE_AUTH=s["KUBE_AUTH"],
        ROLLBACK_ISSUE=rollback_issue,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Kubernetes Templates
# ─────────────────────────────────────────────────────────────────────────────

def tpl_k8s_base_deployment(s: dict) -> str:
    return render("""# AUTO-GENERATED by generate_cicd.py
apiVersion: apps/v1
kind: Deployment
metadata:
  name: __APP_NAME__
  labels:
    app: __APP_NAME__
spec:
  replicas: 2
  selector:
    matchLabels:
      app: __APP_NAME__
  template:
    metadata:
      labels:
        app: __APP_NAME__
      annotations:
        prometheus.io/scrape: "true"
        prometheus.io/port: "__APP_PORT__"
        prometheus.io/path: "/metrics"
    spec:
      terminationGracePeriodSeconds: 60
      containers:
        - name: app
          image: app:latest
          imagePullPolicy: Always
          ports:
            - name: http
              containerPort: __APP_PORT__
          envFrom:
            - configMapRef:
                name: __APP_NAME__-config
            - secretRef:
                name: __APP_NAME__-secrets
          resources:
            requests:
              cpu: 250m
              memory: 512Mi
            limits:
              cpu: 1000m
              memory: 2Gi
          livenessProbe:
            httpGet:
              path: __HEALTH_PATH__/live
              port: http
            initialDelaySeconds: 30
            periodSeconds: 15
          readinessProbe:
            httpGet:
              path: __HEALTH_PATH__/ready
              port: http
            initialDelaySeconds: 10
            periodSeconds: 10
          lifecycle:
            preStop:
              exec:
                command: ["/bin/sh", "-c", "sleep 10"]
      affinity:
        podAntiAffinity:
          preferredDuringSchedulingIgnoredDuringExecution:
            - weight: 100
              podAffinityTerm:
                labelSelector:
                  matchExpressions:
                    - key: app
                      operator: In
                      values: [__APP_NAME__]
                topologyKey: kubernetes.io/hostname
""", **s)


def tpl_k8s_base_service(s: dict) -> str:
    return render("""# AUTO-GENERATED by generate_cicd.py
apiVersion: v1
kind: Service
metadata:
  name: __APP_NAME__
  labels:
    app: __APP_NAME__
spec:
  selector:
    app: __APP_NAME__
  ports:
    - name: http
      port: 80
      targetPort: http
  type: ClusterIP
""", **s)


def tpl_k8s_base_hpa(s: dict) -> str:
    return render("""# AUTO-GENERATED by generate_cicd.py
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: __APP_NAME__
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: __APP_NAME__
  minReplicas: 2
  maxReplicas: 10
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
    - type: Resource
      resource:
        name: memory
        target:
          type: Utilization
          averageUtilization: 80
  behavior:
    scaleDown:
      stabilizationWindowSeconds: 300
    scaleUp:
      stabilizationWindowSeconds: 60
""", **s)


def tpl_k8s_base_configmap(s: dict) -> str:
    return render("""# AUTO-GENERATED by generate_cicd.py
apiVersion: v1
kind: ConfigMap
metadata:
  name: __APP_NAME__-config
data:
  APP_ENV: base
  APP_PORT: "__APP_PORT__"
  LOG_LEVEL: INFO
  TRACING_ENABLED: "true"
  METRICS_ENABLED: "true"
  FEEDBACK_COLLECTION_ENABLED: "true"
  FEEDBACK_SAMPLE_RATE: "0.1"
""", **s)


def tpl_k8s_base_kustomization(s: dict) -> str:
    return render("""# AUTO-GENERATED by generate_cicd.py
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

resources:
  - deployment.yaml
  - service.yaml
  - canary-services.yaml
  - hpa.yaml
  - pdb.yaml
  - configmap.yaml
  - networkpolicy.yaml
  - ingress.yaml

commonLabels:
  app: __APP_NAME__
  managed-by: argocd
""", **s)


def tpl_k8s_staging_kustomization(s: dict) -> str:
    return render("""# AUTO-GENERATED by generate_cicd.py
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

namespace: __STAGING_NS__

bases:
  - ../../base

namePrefix: staging-

images:
  - name: app
    newName: __REGISTRY_URL__
    newTag: latest

patches:
  - path: patch-deployment.yaml

configMapGenerator:
  - name: __APP_NAME__-config
    behavior: merge
    literals:
      - APP_ENV=staging
      - LOG_LEVEL=DEBUG
""", **s)


def tpl_k8s_staging_patch(s: dict) -> str:
    return render("""# AUTO-GENERATED by generate_cicd.py
apiVersion: apps/v1
kind: Deployment
metadata:
  name: __APP_NAME__
spec:
  replicas: __STAGING_REPLICAS__
  template:
    spec:
      containers:
        - name: app
          resources:
            requests:
              cpu: __STAGING_CPU_REQ__
              memory: __STAGING_MEM_REQ__
            limits:
              cpu: __STAGING_CPU_LIM__
              memory: __STAGING_MEM_LIM__
""", **s)


def tpl_k8s_production_kustomization(s: dict) -> str:
    return render("""# AUTO-GENERATED by generate_cicd.py
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

namespace: __PROD_NS__

bases:
  - ../../base

images:
  - name: app
    newName: __REGISTRY_URL__
    newTag: latest

patches:
  - path: patch-rollout.yaml

configMapGenerator:
  - name: __APP_NAME__-config
    behavior: merge
    literals:
      - APP_ENV=production
      - LOG_LEVEL=INFO
""", **s)


def tpl_k8s_production_rollout_patch(s: dict) -> str:
    return render("""# AUTO-GENERATED by generate_cicd.py
# Replaces Deployment with Argo Rollout for canary support
apiVersion: argoproj.io/v1alpha1
kind: Rollout
metadata:
  name: __APP_NAME__
spec:
  replicas: __PROD_REPLICAS__
  selector:
    matchLabels:
      app: __APP_NAME__
  template:
    spec:
      containers:
        - name: app
          resources:
            requests:
              cpu: __PROD_CPU_REQ__
              memory: __PROD_MEM_REQ__
            limits:
              cpu: __PROD_CPU_LIM__
              memory: __PROD_MEM_LIM__
  strategy:
    canary:
      canaryService: __APP_NAME__-canary
      stableService: __APP_NAME__-stable
__TRAFFIC_ROUTING__
      steps:
__CANARY_STEPS__
      canaryMetadata:
        labels:
          version: canary
      stableMetadata:
        labels:
          version: stable
""", **s)


# ─────────────────────────────────────────────────────────────────────────────
# ArgoCD Templates
# ─────────────────────────────────────────────────────────────────────────────

def tpl_argocd_staging(s: dict) -> str:
    sync_policy = """
    automated:
      prune: true
      selfHeal: true
      allowEmpty: false""" if s["STAGING_AUTO_SYNC"] == "true" else ""

    return render("""# AUTO-GENERATED by generate_cicd.py
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: __APP_NAME__-staging
  namespace: argocd
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  project: default
  source:
    repoURL: https://github.com/__GITOPS_REPO__
    targetRevision: __GITOPS_BRANCH__
    path: k8s/overlays/staging
  destination:
    server: https://kubernetes.default.svc
    namespace: __STAGING_NS__
  syncPolicy:
__SYNC_POLICY__
    syncOptions:
      - CreateNamespace=true
      - PrunePropagationPolicy=foreground
    retry:
      limit: 3
      backoff:
        duration: 10s
        factor: 2
        maxDuration: 3m
  revisionHistoryLimit: 5
""",
        SYNC_POLICY=sync_policy,
        **s,
    )


def tpl_argocd_production(s: dict) -> str:
    return render("""# AUTO-GENERATED by generate_cicd.py
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: __APP_NAME__-production
  namespace: argocd
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  project: default
  source:
    repoURL: https://github.com/__GITOPS_REPO__
    targetRevision: __GITOPS_BRANCH__
    path: k8s/overlays/production
  destination:
    server: https://kubernetes.default.svc
    namespace: __PROD_NS__
  syncPolicy:
    syncOptions:
      - CreateNamespace=true
      - PrunePropagationPolicy=foreground
    retry:
      limit: 2
      backoff:
        duration: 30s
        factor: 2
        maxDuration: 5m
  ignoreDifferences:
    - group: argoproj.io
      kind: Rollout
      jsonPointers:
        - /spec/replicas
  revisionHistoryLimit: 10
""", **s)


def tpl_argocd_rollout(s: dict) -> str:
    return render("""# AUTO-GENERATED by generate_cicd.py
apiVersion: argoproj.io/v1alpha1
kind: Rollout
metadata:
  name: __APP_NAME__
  namespace: __PROD_NS__
spec:
  replicas: __PROD_REPLICAS__
  revisionHistoryLimit: 3
  selector:
    matchLabels:
      app: __APP_NAME__
  template:
    metadata:
      labels:
        app: __APP_NAME__
        version: stable
    spec:
      terminationGracePeriodSeconds: 60
      containers:
        - name: app
          image: app:latest
          imagePullPolicy: Always
          ports:
            - name: http
              containerPort: __APP_PORT__
          envFrom:
            - configMapRef:
                name: __APP_NAME__-config
            - secretRef:
                name: __APP_NAME__-secrets
          resources:
            requests:
              cpu: __PROD_CPU_REQ__
              memory: __PROD_MEM_REQ__
            limits:
              cpu: __PROD_CPU_LIM__
              memory: __PROD_MEM_LIM__
          livenessProbe:
            httpGet:
              path: __HEALTH_PATH__/live
              port: http
            initialDelaySeconds: 30
            periodSeconds: 15
          readinessProbe:
            httpGet:
              path: __HEALTH_PATH__/ready
              port: http
            initialDelaySeconds: 10
            periodSeconds: 10
  strategy:
    canary:
      canaryService: __APP_NAME__-canary
      stableService: __APP_NAME__-stable
__TRAFFIC_ROUTING__
      steps:
__CANARY_STEPS__
      canaryMetadata:
        labels:
          version: canary
      stableMetadata:
        labels:
          version: stable
""", **s)


def tpl_argocd_analysis(s: dict) -> str:
    return render("""# AUTO-GENERATED by generate_cicd.py
---
apiVersion: argoproj.io/v1alpha1
kind: AnalysisTemplate
metadata:
  name: ai-eval-analysis
  namespace: __PROD_NS__
spec:
  args:
    - name: service-name
  metrics:
    - name: error-rate
      interval: 2m
      count: 3
      successCondition: result[0] < 0.05
      failureLimit: 1
      provider:
        prometheus:
          address: http://prometheus.monitoring.svc.cluster.local:9090
          query: |
            sum(rate(http_requests_total{service="{{args.service-name}}",status=~"5.."}[2m])) /
            sum(rate(http_requests_total{service="{{args.service-name}}"}[2m]))

    - name: p99-latency-seconds
      interval: 2m
      count: 3
      successCondition: result[0] < 30.0
      failureLimit: 1
      provider:
        prometheus:
          address: http://prometheus.monitoring.svc.cluster.local:9090
          query: |
            histogram_quantile(0.99,
              sum(rate(http_request_duration_seconds_bucket{service="{{args.service-name}}"}[2m])) by (le))

    - name: agent-eval-score
      interval: 5m
      count: 2
      successCondition: result.score >= __EVAL_AGENT_THRESHOLD__
      failureLimit: 1
      provider:
        web:
          url: http://eval-service.monitoring.svc.cluster.local:8080/canary-eval
          method: POST
          headers:
            - key: Content-Type
              value: application/json
          body: |
            {"service": "{{args.service-name}}", "sample_rate": 0.1}
          jsonPath: "{$.data[0]}"

    - name: safety-score
      interval: 5m
      count: 2
      successCondition: result.safety_score >= __EVAL_SAFETY_THRESHOLD__
      failureLimit: 0
      provider:
        web:
          url: http://eval-service.monitoring.svc.cluster.local:8080/safety-eval
          method: POST
          headers:
            - key: Content-Type
              value: application/json
          body: |
            {"service": "{{args.service-name}}"}
          jsonPath: "{$.data[0]}"
""", **s)


# ─────────────────────────────────────────────────────────────────────────────
# Evals thresholds template
# ─────────────────────────────────────────────────────────────────────────────

def tpl_thresholds(s: dict) -> str:
    return render("""# AUTO-GENERATED by generate_cicd.py — edit cicd.config.yaml to change thresholds
thresholds:
  prompt_regression:
    min_score: __THRESH_PROMPT__
  tool_call_validation:
    min_score: __THRESH_TOOL__
  rag_retrieval:
    min_score: __THRESH_RAG__
  hallucination:
    max_rate: __THRESH_HALL__
  safety:
    min_score: __THRESH_SAFETY__
  latency:
    p95_ms: __THRESH_LAT_P95__
    p99_ms: __THRESH_LAT_P99__
  token_cost:
    max_avg_tokens: __THRESH_TOKENS__
    max_cost_per_1k: 0.10

datasets:
  prompt_regression: evals/datasets/prompt_regression_dataset.json
  tool_calls: evals/datasets/tool_call_dataset.json
  rag: evals/datasets/rag_dataset.json
  safety: evals/datasets/safety_dataset.json

judge_model: __JUDGE_MODEL__
""", **s)


# ─────────────────────────────────────────────────────────────────────────────
# Bootstrap script template
# ─────────────────────────────────────────────────────────────────────────────

def tpl_bootstrap(s: dict) -> str:
    return render("""#!/usr/bin/env bash
# AUTO-GENERATED by generate_cicd.py
# Bootstrap ArgoCD + Argo Rollouts. Run once per cluster.
set -euo pipefail

ARGOCD_VERSION="${ARGOCD_VERSION:-v2.13.0}"
ARGO_ROLLOUTS_VERSION="${ARGO_ROLLOUTS_VERSION:-v1.7.0}"

echo "==> Installing ArgoCD"
kubectl create namespace argocd --dry-run=client -o yaml | kubectl apply -f -
kubectl apply -n argocd \\
  -f "https://raw.githubusercontent.com/argoproj/argo-cd/${ARGOCD_VERSION}/manifests/install.yaml"
kubectl rollout status deployment/argocd-server -n argocd --timeout=180s

echo "==> Installing Argo Rollouts"
kubectl create namespace argo-rollouts --dry-run=client -o yaml | kubectl apply -f -
kubectl apply -n argo-rollouts \\
  -f "https://github.com/argoproj/argo-rollouts/releases/download/${ARGO_ROLLOUTS_VERSION}/install.yaml"

echo "==> Creating namespaces"
kubectl create namespace __STAGING_NS__ --dry-run=client -o yaml | kubectl apply -f -
kubectl create namespace __PROD_NS__ --dry-run=client -o yaml | kubectl apply -f -

echo "==> Applying ArgoCD Applications"
kubectl apply -f argocd/app-staging.yaml
kubectl apply -f argocd/app-production.yaml
kubectl apply -f argocd/analysis-template.yaml -n __PROD_NS__

echo ""
echo "ArgoCD password: $(kubectl get secret argocd-initial-admin-secret -n argocd -o jsonpath='{.data.password}' | base64 -d)"
echo "Port-forward:    kubectl port-forward svc/argocd-server -n argocd 8080:443"
""", **s)


# ─────────────────────────────────────────────────────────────────────────────
# Dockerfile Templates (per language)
# ─────────────────────────────────────────────────────────────────────────────

DOCKERFILES = {
    "python": """\
# AUTO-GENERATED by generate_cicd.py
FROM python:3.11-slim AS builder
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends build-essential && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.11-slim AS runtime
WORKDIR /app
RUN groupadd -r appuser && useradd -r -g appuser appuser
COPY --from=builder /install /usr/local
COPY --chown=appuser:appuser . .
USER appuser
EXPOSE __APP_PORT__
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
CMD ["python", "-m", "app.main"]
""",

    "node": """\
# AUTO-GENERATED by generate_cicd.py
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci --only=production

FROM node:20-alpine AS runtime
WORKDIR /app
RUN addgroup -S appgroup && adduser -S appuser -G appgroup
COPY --from=builder /app/node_modules ./node_modules
COPY --chown=appuser:appgroup . .
USER appuser
EXPOSE __APP_PORT__
CMD ["node", "src/index.js"]
""",

    "java": """\
# AUTO-GENERATED by generate_cicd.py
FROM maven:3.9-eclipse-temurin-21 AS builder
WORKDIR /app
COPY pom.xml .
RUN mvn dependency:go-offline -B
COPY src ./src
RUN mvn package -DskipTests -B

FROM eclipse-temurin:21-jre-alpine AS runtime
WORKDIR /app
RUN addgroup -S appgroup && adduser -S appuser -G appgroup
COPY --from=builder /app/target/*.jar app.jar
USER appuser
EXPOSE __APP_PORT__
ENTRYPOINT ["java", "-jar", "app.jar"]
""",

    "go": """\
# AUTO-GENERATED by generate_cicd.py
FROM golang:1.22-alpine AS builder
WORKDIR /app
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -ldflags="-w -s" -o app ./cmd/main.go

FROM gcr.io/distroless/static:nonroot AS runtime
WORKDIR /app
COPY --from=builder /app/app .
EXPOSE __APP_PORT__
ENTRYPOINT ["/app/app"]
""",

    "dotnet": """\
# AUTO-GENERATED by generate_cicd.py
FROM mcr.microsoft.com/dotnet/sdk:8.0 AS builder
WORKDIR /app
COPY *.csproj .
RUN dotnet restore
COPY . .
RUN dotnet publish -c Release -o /out

FROM mcr.microsoft.com/dotnet/aspnet:8.0 AS runtime
WORKDIR /app
RUN useradd -r appuser
COPY --from=builder /out .
USER appuser
EXPOSE __APP_PORT__
ENTRYPOINT ["dotnet", "app.dll"]
""",

    "generic": """\
# AUTO-GENERATED by generate_cicd.py
# Replace with your application's build steps
FROM ubuntu:22.04 AS runtime
WORKDIR /app
COPY . .
EXPOSE __APP_PORT__
CMD ["./entrypoint.sh"]
""",
}


# ─────────────────────────────────────────────────────────────────────────────
# Additional K8s Resources
# ─────────────────────────────────────────────────────────────────────────────

def tpl_k8s_ingress(s: dict) -> str:
    return render("""# AUTO-GENERATED by generate_cicd.py
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: __APP_NAME__
  annotations:
    nginx.ingress.kubernetes.io/rewrite-target: /
    nginx.ingress.kubernetes.io/proxy-body-size: "10m"
    nginx.ingress.kubernetes.io/proxy-read-timeout: "60"
spec:
  ingressClassName: nginx
  rules:
    - host: __APP_NAME__.example.com    # replace with your domain
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: __APP_NAME__
                port:
                  name: http
  tls:
    - hosts:
        - __APP_NAME__.example.com
      secretName: __APP_NAME__-tls
""", **s)


def tpl_k8s_pdb(s: dict) -> str:
    return render("""# AUTO-GENERATED by generate_cicd.py
# Ensures at least 1 pod stays up during node drains / rolling updates
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: __APP_NAME__
spec:
  minAvailable: 1
  selector:
    matchLabels:
      app: __APP_NAME__
""", **s)


def tpl_k8s_network_policy(s: dict) -> str:
    return render("""# AUTO-GENERATED by generate_cicd.py
# Allow inbound HTTP only from ingress controller; allow all egress
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: __APP_NAME__
spec:
  podSelector:
    matchLabels:
      app: __APP_NAME__
  policyTypes:
    - Ingress
    - Egress
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: ingress-nginx
      ports:
        - protocol: TCP
          port: __APP_PORT__
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: monitoring
      ports:
        - protocol: TCP
          port: 9090
  egress:
    - {}    # allow all outbound (DNS, external APIs, etc.)
""", **s)


def tpl_k8s_canary_services(s: dict) -> str:
    return render("""# AUTO-GENERATED by generate_cicd.py
# Argo Rollouts requires a stable + canary Service pair
---
apiVersion: v1
kind: Service
metadata:
  name: __APP_NAME__-stable
  labels:
    app: __APP_NAME__
    role: stable
spec:
  selector:
    app: __APP_NAME__
  ports:
    - name: http
      port: 80
      targetPort: http
  type: ClusterIP
---
apiVersion: v1
kind: Service
metadata:
  name: __APP_NAME__-canary
  labels:
    app: __APP_NAME__
    role: canary
spec:
  selector:
    app: __APP_NAME__
  ports:
    - name: http
      port: 80
      targetPort: http
  type: ClusterIP
""", **s)


# ─────────────────────────────────────────────────────────────────────────────
# Monitoring Templates
# ─────────────────────────────────────────────────────────────────────────────

def tpl_monitoring_servicemonitor(s: dict) -> str:
    return render("""# AUTO-GENERATED by generate_cicd.py
# Prometheus operator ServiceMonitor — scrapes /metrics on port 9090
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: __APP_NAME__
  namespace: monitoring
  labels:
    release: prometheus
spec:
  namespaceSelector:
    matchNames:
      - __PROD_NS__
      - __STAGING_NS__
  selector:
    matchLabels:
      app: __APP_NAME__
  endpoints:
    - port: metrics
      path: /metrics
      interval: 30s
      scrapeTimeout: 10s
""", **s)


def tpl_monitoring_alerts(s: dict) -> str:
    return render("""# AUTO-GENERATED by generate_cicd.py
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: __APP_NAME__-alerts
  namespace: monitoring
  labels:
    release: prometheus
spec:
  groups:
    - name: __APP_NAME__.availability
      rules:
        - alert: HighErrorRate
          expr: |
            sum(rate(http_requests_total{app="__APP_NAME__",status=~"5.."}[5m])) /
            sum(rate(http_requests_total{app="__APP_NAME__"}[5m])) > 0.05
          for: 2m
          labels:
            severity: critical
          annotations:
            summary: "High error rate on __APP_NAME__"
            description: "Error rate > 5% for 2 minutes."

        - alert: HighP99Latency
          expr: |
            histogram_quantile(0.99,
              sum(rate(http_request_duration_seconds_bucket{app="__APP_NAME__"}[5m])) by (le)) > 30
          for: 2m
          labels:
            severity: warning
          annotations:
            summary: "High P99 latency on __APP_NAME__"
            description: "P99 latency > 30s for 2 minutes."

        - alert: PodCrashLooping
          expr: |
            rate(kube_pod_container_status_restarts_total{
              namespace=~"__PROD_NS__|__STAGING_NS__",
              pod=~"__APP_NAME__.*"
            }[15m]) * 60 * 5 > 0
          for: 5m
          labels:
            severity: critical
          annotations:
            summary: "__APP_NAME__ pod is crash-looping"

        - alert: AgentEvalScoreDegraded
          expr: |
            agent_eval_score{app="__APP_NAME__"} < __EVAL_AGENT_THRESHOLD__
          for: 10m
          labels:
            severity: warning
          annotations:
            summary: "Agent eval score below threshold"
            description: "Eval score has been below __EVAL_AGENT_THRESHOLD__ for 10 minutes."

        - alert: SafetyScoreDegraded
          expr: |
            agent_safety_score{app="__APP_NAME__"} < __EVAL_SAFETY_THRESHOLD__
          for: 5m
          labels:
            severity: critical
          annotations:
            summary: "Safety score below threshold — immediate attention required"
""", **s)


# ─────────────────────────────────────────────────────────────────────────────
# Application Skeleton (written only if files don't already exist)
# ─────────────────────────────────────────────────────────────────────────────

APP_SKELETON_PYTHON = """\
# AUTO-GENERATED by generate_cicd.py — replace with your application code
from fastapi import FastAPI
from fastapi.responses import JSONResponse

app = FastAPI(title="__APP_NAME__")


@app.get("/health/live")
def liveness():
    return {"status": "alive"}


@app.get("/health/ready")
def readiness():
    # Add real dependency checks here (DB, cache, etc.)
    return {"status": "ready"}


@app.get("/metrics")
def metrics():
    # Replace with prometheus_client exposition
    return {"requests_total": 0}


@app.get("/")
def root():
    return {"app": "__APP_NAME__", "status": "running"}
"""

APP_SKELETON_NODE = """\
// AUTO-GENERATED by generate_cicd.py — replace with your application code
const express = require('express');
const app = express();
const PORT = process.env.PORT || __APP_PORT__;

app.get('/health/live',  (_, res) => res.json({ status: 'alive' }));
app.get('/health/ready', (_, res) => res.json({ status: 'ready' }));
app.get('/metrics',      (_, res) => res.send('# HELP requests_total Total requests\\n'));
app.get('/',             (_, res) => res.json({ app: '__APP_NAME__', status: 'running' }));

app.listen(PORT, () => console.log(`__APP_NAME__ listening on :${PORT}`));
"""

UNIT_TEST_PYTHON = """\
# AUTO-GENERATED by generate_cicd.py — replace with real tests
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_liveness():
    r = client.get("/health/live")
    assert r.status_code == 200
    assert r.json()["status"] == "alive"


def test_readiness():
    r = client.get("/health/ready")
    assert r.status_code == 200


def test_root():
    r = client.get("/")
    assert r.status_code == 200
"""

SMOKE_TEST_PYTHON = """\
# AUTO-GENERATED by generate_cicd.py — smoke tests run against live staging/production
import os
import pytest
import httpx

BASE_URL = os.environ.get("BASE_URL", "http://localhost:__APP_PORT__")


def test_liveness():
    r = httpx.get(f"{BASE_URL}/health/live", timeout=10)
    assert r.status_code == 200, f"Liveness probe failed: {r.text}"


def test_readiness():
    r = httpx.get(f"{BASE_URL}/health/ready", timeout=10)
    assert r.status_code == 200, f"Readiness probe failed: {r.text}"


def test_root_responds():
    r = httpx.get(f"{BASE_URL}/", timeout=10)
    assert r.status_code < 500, f"Root endpoint returned 5xx: {r.text}"
"""


# ─────────────────────────────────────────────────────────────────────────────
# Makefile Template
# ─────────────────────────────────────────────────────────────────────────────

def tpl_makefile(s: dict) -> str:
    return render(""".PHONY: generate detect dry-run build run test lint bootstrap secrets

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
	docker build -t __APP_NAME__:local .

## Run app locally
run:
	docker run --rm -p __APP_PORT__:__APP_PORT__ __APP_NAME__:local

## Run unit tests
test:
	pytest tests/unit/ -v

## Run smoke tests against local app
smoke:
	BASE_URL=http://localhost:__APP_PORT__ pytest tests/smoke/ -v

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
""", **s)


# ─────────────────────────────────────────────────────────────────────────────
# Secrets Setup Script
# ─────────────────────────────────────────────────────────────────────────────

def tpl_setup_secrets(s: dict) -> str:
    return render("""#!/usr/bin/env bash
# AUTO-GENERATED by generate_cicd.py
# Interactive helper to set GitHub Actions secrets for this pipeline.
# Requires: gh (GitHub CLI), already authenticated.

set -euo pipefail

REPO="${GITHUB_REPO:-$(gh repo view --json nameWithOwner -q .nameWithOwner)}"
echo "Setting secrets for: $REPO"
echo ""

set_secret() {
    local name="$1"
    local prompt="$2"
    local default="${3:-}"
    if [ -n "$default" ]; then
        read -r -p "  $name [$prompt] (default: $default): " val
        val="${val:-$default}"
    else
        read -r -s -p "  $name [$prompt]: " val
        echo
    fi
    if [ -n "$val" ]; then
        echo "$val" | gh secret set "$name" --repo "$REPO"
        echo "  -> $name set."
    else
        echo "  -> $name skipped."
    fi
}

echo "=== GitOps ==="
set_secret GITOPS_REPO     "org/repo for manifest updates"   "__GITOPS_REPO__"
set_secret GITOPS_TOKEN    "GitHub PAT with repo write access"

echo ""
echo "=== ArgoCD ==="
set_secret ARGOCD_SERVER   "ArgoCD server hostname"
set_secret ARGOCD_TOKEN    "ArgoCD API token"

echo ""
echo "=== Environment URLs ==="
set_secret STAGING_BASE_URL    "Staging base URL"
set_secret PRODUCTION_BASE_URL "Production base URL"

echo ""
echo "=== AI Evals ==="
set_secret ANTHROPIC_API_KEY   "Anthropic API key for eval judge"

echo ""
echo "=== Cloud: __CLOUD__ ==="
""" + _cloud_secret_prompts(s) + """
echo ""
echo "All secrets configured. Run 'gh secret list --repo $REPO' to verify."
""", **s)


def _cloud_secret_prompts(s: dict) -> str:
    cloud = s["CLOUD"]
    if cloud == "aws":
        return """\
set_secret AWS_ROLE_ARN     "IAM role ARN for OIDC auth"
set_secret AWS_REGION       "AWS region"          "us-east-1"
set_secret EKS_CLUSTER_NAME "EKS cluster name"
"""
    elif cloud == "gcp":
        return """\
set_secret GCP_WORKLOAD_IDENTITY_PROVIDER "Workload Identity provider resource name"
set_secret GCP_SERVICE_ACCOUNT            "Service account email"
set_secret GKE_CLUSTER_NAME              "GKE cluster name"
set_secret GKE_CLUSTER_LOCATION          "GKE cluster location (region or zone)"
set_secret REGISTRY_URL                  "GCR/AR hostname"
"""
    elif cloud == "azure":
        return """\
set_secret AZURE_CREDENTIALS  "Service principal JSON"
set_secret REGISTRY_URL       "ACR login server"
set_secret REGISTRY_USERNAME  "ACR username"
set_secret REGISTRY_PASSWORD  "ACR password"
set_secret AKS_RESOURCE_GROUP "AKS resource group"
set_secret AKS_CLUSTER_NAME   "AKS cluster name"
"""
    else:
        return """\
set_secret REGISTRY_URL      "Container registry hostname"
set_secret REGISTRY_USERNAME "Registry username"
set_secret REGISTRY_PASSWORD "Registry password"
set_secret KUBE_CONFIG       "Base64-encoded kubeconfig"
"""


# ─────────────────────────────────────────────────────────────────────────────
# Generator Orchestrator
# ─────────────────────────────────────────────────────────────────────────────

class CICDGenerator:
    def __init__(self, cfg: dict, output_dir: Path, dry_run: bool = False):
        self.cfg = cfg
        self.output_dir = output_dir
        self.dry_run = dry_run
        self.files_written: list[str] = []

        # Resolve derived values
        app = cfg["app"]
        k8s = cfg["kubernetes"]
        evals = cfg.get("evals", {})
        gitops = cfg.get("gitops", {})
        argocd = cfg.get("argocd", {})
        notif = cfg.get("notifications", {})

        language = app.get("language", "auto")
        if language == "auto":
            language = detect_language(output_dir)
            print(f"  Auto-detected language: {language}")

        registry_url = resolve_registry_url(cfg)
        test_cmd = app.get("test_command") or TEST_COMMANDS.get(language, TEST_COMMANDS["generic"])

        # Build substitution dict — all __PLACEHOLDER__ keys
        self.s = {
            "APP_NAME":           app["name"],
            "APP_PORT":           str(app.get("port", 8080)),
            "HEALTH_PATH":        app.get("health_path", "/health"),
            "LANGUAGE":           language,
            "REGISTRY_URL":       registry_url,
            "CLOUD":              cfg["cloud"]["provider"],
            "STAGING_NS":         k8s["staging"]["namespace"],
            "PROD_NS":            k8s["production"]["namespace"],
            "STAGING_REPLICAS":   str(k8s["staging"].get("replicas", 1)),
            "PROD_REPLICAS":      str(k8s["production"].get("replicas", 4)),
            "STAGING_CPU_REQ":    k8s["staging"].get("cpu_request", "100m"),
            "STAGING_CPU_LIM":    k8s["staging"].get("cpu_limit", "500m"),
            "STAGING_MEM_REQ":    k8s["staging"].get("memory_request", "256Mi"),
            "STAGING_MEM_LIM":    k8s["staging"].get("memory_limit", "1Gi"),
            "PROD_CPU_REQ":       k8s["production"].get("cpu_request", "500m"),
            "PROD_CPU_LIM":       k8s["production"].get("cpu_limit", "2000m"),
            "PROD_MEM_REQ":       k8s["production"].get("memory_request", "1Gi"),
            "PROD_MEM_LIM":       k8s["production"].get("memory_limit", "4Gi"),
            "GITOPS_REPO":        gitops.get("repo", "YOUR_ORG/YOUR_GITOPS_REPO"),
            "GITOPS_BRANCH":      gitops.get("branch", "main"),
            "STAGING_AUTO_SYNC":  str(argocd.get("staging_auto_sync", True)).lower(),
            "EVALS_ENABLED":      str(evals.get("enabled", True)).lower(),
            "JUDGE_MODEL":        evals.get("judge_model", "claude-sonnet-4-6"),
            "LANG_SETUP":         BUILD_SETUP_STEPS.get(language, BUILD_SETUP_STEPS["generic"]),
            "TEST_CMD":           test_cmd,
            "REGISTRY_LOGIN":     registry_login_steps(cfg),
            "KUBE_AUTH":          kube_auth_steps(cfg),
            "CANARY_STEPS":       canary_steps_yaml(cfg),
            "TRAFFIC_ROUTING":    traffic_routing_yaml(cfg),
            "ROLLBACK_ISSUES":    str(notif.get("github_issues_on_rollback", True)).lower(),
            # Eval thresholds
            "THRESH_PROMPT":      str(evals.get("thresholds", {}).get("prompt_regression", 0.90)),
            "THRESH_TOOL":        str(evals.get("thresholds", {}).get("tool_call_validation", 0.95)),
            "THRESH_RAG":         str(evals.get("thresholds", {}).get("rag_retrieval", 0.85)),
            "THRESH_HALL":        str(evals.get("thresholds", {}).get("hallucination_max", 0.05)),
            "THRESH_SAFETY":      str(evals.get("thresholds", {}).get("safety", 0.98)),
            "THRESH_LAT_P95":     str(evals.get("thresholds", {}).get("latency_p95_ms", 15000)),
            "THRESH_LAT_P99":     str(evals.get("thresholds", {}).get("latency_p99_ms", 30000)),
            "THRESH_TOKENS":      str(evals.get("thresholds", {}).get("avg_tokens", 2000)),
            "EVAL_AGENT_THRESHOLD": str(evals.get("thresholds", {}).get("prompt_regression", 0.90)),
            "EVAL_SAFETY_THRESHOLD": str(evals.get("thresholds", {}).get("safety", 0.98)),
        }

    def write(self, rel_path: str, content: str):
        full_path = self.output_dir / rel_path
        if self.dry_run:
            print(f"  [DRY-RUN] Would write: {rel_path}")
            self.files_written.append(rel_path)
            return
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content, encoding="utf-8")
        self.files_written.append(rel_path)
        print(f"  [ok] {rel_path}")

    def write_if_missing(self, rel_path: str, content: str):
        """Write only if file doesn't already exist — protects user code."""
        full_path = self.output_dir / rel_path
        if full_path.exists() and not self.dry_run:
            print(f"  [skip] {rel_path}  (already exists)")
            return
        tag = "[DRY-RUN, would create if missing]" if self.dry_run else ""
        if self.dry_run:
            print(f"  [DRY-RUN] Would create (if missing): {rel_path}")
            self.files_written.append(rel_path)
            return
        self.write(rel_path, content)

    def generate(self):
        s = self.s
        print("\n--- GitHub Actions ---")
        self.write(".github/workflows/ci.yml",            tpl_ci(s))
        self.write(".github/workflows/cd-staging.yml",    tpl_cd_staging(s))
        self.write(".github/workflows/cd-production.yml", tpl_cd_production(s))

        print("\n--- Kubernetes (Kustomize) ---")
        self.write("k8s/base/deployment.yaml",            tpl_k8s_base_deployment(s))
        self.write("k8s/base/service.yaml",               tpl_k8s_base_service(s))
        self.write("k8s/base/hpa.yaml",                   tpl_k8s_base_hpa(s))
        self.write("k8s/base/configmap.yaml",             tpl_k8s_base_configmap(s))
        self.write("k8s/base/kustomization.yaml",         tpl_k8s_base_kustomization(s))
        self.write("k8s/overlays/staging/kustomization.yaml",     tpl_k8s_staging_kustomization(s))
        self.write("k8s/overlays/staging/patch-deployment.yaml",  tpl_k8s_staging_patch(s))
        self.write("k8s/overlays/production/kustomization.yaml",  tpl_k8s_production_kustomization(s))
        self.write("k8s/overlays/production/patch-rollout.yaml",  tpl_k8s_production_rollout_patch(s))

        print("\n--- ArgoCD ---")
        self.write("argocd/app-staging.yaml",         tpl_argocd_staging(s))
        self.write("argocd/app-production.yaml",      tpl_argocd_production(s))
        self.write("argocd/rollout-production.yaml",  tpl_argocd_rollout(s))
        self.write("argocd/analysis-template.yaml",   tpl_argocd_analysis(s))

        if s["EVALS_ENABLED"] == "true":
            print("\n--- AI Eval Suite ---")
            self.write("evals/thresholds.yaml", tpl_thresholds(s))

        print("\n--- Dockerfile ---")
        dockerfile = DOCKERFILES.get(s["LANGUAGE"], DOCKERFILES["generic"])
        self.write("Dockerfile", render(dockerfile, APP_PORT=s["APP_PORT"]))

        print("\n--- Additional K8s Resources ---")
        self.write("k8s/base/ingress.yaml",          tpl_k8s_ingress(s))
        self.write("k8s/base/pdb.yaml",               tpl_k8s_pdb(s))
        self.write("k8s/base/networkpolicy.yaml",     tpl_k8s_network_policy(s))
        self.write("k8s/base/canary-services.yaml",   tpl_k8s_canary_services(s))

        print("\n--- Monitoring ---")
        self.write("monitoring/servicemonitor.yaml",  tpl_monitoring_servicemonitor(s))
        self.write("monitoring/alerting-rules.yaml",  tpl_monitoring_alerts(s))

        print("\n--- Scripts ---")
        self.write("scripts/bootstrap-argocd.sh", tpl_bootstrap(s))
        self.write("scripts/setup-secrets.sh",    tpl_setup_secrets(s))
        self.write("Makefile",                    tpl_makefile(s))

        print("\n--- App skeleton (skipped if files exist) ---")
        if s["LANGUAGE"] == "python":
            self.write_if_missing("app/__init__.py", "")
            self.write_if_missing("app/main.py",
                render(APP_SKELETON_PYTHON, APP_NAME=s["APP_NAME"]))
            self.write_if_missing("tests/__init__.py", "")
            self.write_if_missing("tests/unit/__init__.py", "")
            self.write_if_missing("tests/unit/test_app.py",
                render(UNIT_TEST_PYTHON, APP_NAME=s["APP_NAME"]))
            self.write_if_missing("tests/smoke/__init__.py", "")
            self.write_if_missing("tests/smoke/test_smoke.py",
                render(SMOKE_TEST_PYTHON, APP_NAME=s["APP_NAME"], APP_PORT=s["APP_PORT"]))
        elif s["LANGUAGE"] == "node":
            self.write_if_missing("src/index.js",
                render(APP_SKELETON_NODE, APP_NAME=s["APP_NAME"], APP_PORT_=s["APP_PORT"]))

        self.write(".gitignore", """\
__pycache__/
*.py[cod]
.venv/
venv/
reports/
.env
.env.*
secrets.yaml
*-secret.yaml
*.pem
*.key
.DS_Store
.kube/
kubeconfig
node_modules/
target/
build/
dist/
""")
        print()
        print(f"Generated {len(self.files_written)} files total.")


# ─────────────────────────────────────────────────────────────────────────────
# Interactive Setup Wizard
# ─────────────────────────────────────────────────────────────────────────────

def ask(prompt: str, default: str = "") -> str:
    hint = f" [{default}]" if default else ""
    try:
        val = input(f"  {prompt}{hint}: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        sys.exit(0)
    return val if val else default


def ask_choice(prompt: str, options: list[tuple[str, str]], default: int = 1) -> str:
    print(f"\n  {prompt}")
    for i, (key, label) in enumerate(options, 1):
        marker = " (default)" if i == default else ""
        print(f"    {i}. {label}{marker}")
    while True:
        raw = ask("Select", str(default))
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return options[int(raw) - 1][0]
        print(f"  Enter a number between 1 and {len(options)}")


def ask_yn(prompt: str, default: bool = True) -> bool:
    hint = "Y/n" if default else "y/N"
    val = ask(f"{prompt} [{hint}]").lower()
    if not val:
        return default
    return val.startswith("y")


def wizard(output_dir: Path, config_path: Path) -> dict:
    """Interactive wizard that builds cicd.config.yaml from user answers."""

    print("\n" + "=" * 53)
    print("  Golden CI/CD Generator — Interactive Setup")
    print("=" * 53)
    print("  Press Enter to accept defaults.\n")

    # ── App ───────────────────────────────────────────────
    print("--- App Configuration ---")
    default_name = output_dir.name.lower().replace(" ", "-").replace("_", "-")
    app_name     = ask("App name", default_name)
    detected_lang = detect_language(output_dir)
    lang_input   = ask(f"Language (python/node/java/go/dotnet/generic)", detected_lang)
    language     = lang_input if lang_input in LANGUAGE_SIGNALS else detected_lang
    port         = ask("Container port", "8080")
    health_path  = ask("Health check path", "/health")

    # ── Cloud ─────────────────────────────────────────────
    cloud = ask_choice("Cloud provider", [
        ("aws",     "AWS   (ECR + EKS)"),
        ("gcp",     "GCP   (GCR / Artifact Registry + GKE)"),
        ("azure",   "Azure (ACR + AKS)"),
        ("generic", "Generic (any registry + kubeconfig)"),
    ])

    cloud_section: dict = {}

    if cloud == "aws":
        print("\n--- AWS Configuration ---")
        account_id  = ask("AWS Account ID")
        region      = ask("AWS Region", "us-east-1")
        auth_method = ask_choice("Auth method", [
            ("oidc",       "OIDC role (recommended — no long-lived keys)"),
            ("access_key", "Access Key + Secret"),
        ])
        cloud_section = {"aws": {"region": region, "account_id": account_id, "auth_method": auth_method}}

    elif cloud == "gcp":
        print("\n--- GCP Configuration ---")
        project_id  = ask("GCP Project ID")
        region      = ask("GCP Region", "us-central1")
        auth_method = ask_choice("Auth method", [
            ("workload_identity", "Workload Identity Federation (recommended)"),
            ("service_account_key", "Service Account JSON key"),
        ])
        use_ar = ask_yn("Use Artifact Registry instead of GCR?", False)
        cloud_section = {"gcp": {"project_id": project_id, "region": region,
                                  "auth_method": auth_method, "artifact_registry": use_ar}}

    elif cloud == "azure":
        print("\n--- Azure Configuration ---")
        registry_name = ask("ACR registry name (without .azurecr.io)")
        cloud_section = {"azure": {"registry_name": registry_name}}

    else:
        print("\n--- Generic Registry ---")
        registry_url = ask("Registry URL (e.g. registry.example.com)")
        cloud_section = {"generic": {"registry_url": registry_url}}

    # ── Kubernetes ────────────────────────────────────────
    print("\n--- Kubernetes ---")
    cluster_map = {"aws": "eks", "gcp": "gke", "azure": "aks", "generic": "generic"}
    cluster_default = cluster_map.get(cloud, "generic")
    cluster_type = ask_choice("Cluster type", [
        ("eks",     "EKS   (AWS)"),
        ("gke",     "GKE   (GCP)"),
        ("aks",     "AKS   (Azure)"),
        ("generic", "Generic (any kubeconfig)"),
    ], default=["eks","gke","aks","generic"].index(cluster_default) + 1)

    staging_ns = ask("Staging namespace", "staging")
    prod_ns    = ask("Production namespace", "production")
    staging_replicas = ask("Staging replicas", "1")
    prod_replicas    = ask("Production replicas", "4")

    # ── GitOps ────────────────────────────────────────────
    print("\n--- GitOps ---")
    gitops_repo   = ask("GitOps repo (org/repo — can be this same repo)")
    gitops_branch = ask("GitOps branch", "main")

    # ── AI Evals ─────────────────────────────────────────
    print("\n--- AI Eval Gates ---")
    evals_enabled = ask_yn("Enable AI eval gates?", True)
    judge_model   = "claude-sonnet-4-6"
    if evals_enabled:
        judge_model = ask("Judge model", "claude-sonnet-4-6")

    # ── Summary ───────────────────────────────────────────
    registry_preview = {
        "aws":     f"{cloud_section.get('aws',{}).get('account_id','?')}.dkr.ecr.{cloud_section.get('aws',{}).get('region','?')}.amazonaws.com/{app_name}",
        "gcp":     f"gcr.io/{cloud_section.get('gcp',{}).get('project_id','?')}/{app_name}",
        "azure":   f"{cloud_section.get('azure',{}).get('registry_name','?')}.azurecr.io/{app_name}",
        "generic": f"{cloud_section.get('generic',{}).get('registry_url','?')}/{app_name}",
    }.get(cloud, "")

    print("\n" + "-" * 53)
    print("  Configuration Summary")
    print("-" * 53)
    print(f"  App name    : {app_name}")
    print(f"  Language    : {language}")
    print(f"  Port        : {port}")
    print(f"  Cloud       : {cloud}")
    print(f"  Registry    : {registry_preview[:48]}")
    print(f"  Cluster     : {cluster_type}")
    print(f"  Staging ns  : {staging_ns}")
    print(f"  Prod ns     : {prod_ns}")
    print(f"  GitOps repo : {gitops_repo}")
    print(f"  Evals       : {'enabled' if evals_enabled else 'disabled'}")
    print("-" * 53)

    if not ask_yn("\n  Generate CI/CD pipeline now?", True):
        print("  Aborted. Edit cicd.config.yaml manually and re-run.")
        sys.exit(0)

    # ── Build config dict ─────────────────────────────────
    cfg = {
        "app": {
            "name": app_name,
            "language": language,
            "port": int(port),
            "health_path": health_path,
            "test_command": "",
        },
        "cloud": {"provider": cloud, **cloud_section},
        "kubernetes": {
            "cluster_type": cluster_type,
            "staging": {
                "namespace": staging_ns,
                "replicas": int(staging_replicas),
                "cpu_request": "100m", "cpu_limit": "500m",
                "memory_request": "256Mi", "memory_limit": "1Gi",
            },
            "production": {
                "namespace": prod_ns,
                "replicas": int(prod_replicas),
                "cpu_request": "500m", "cpu_limit": "2000m",
                "memory_request": "1Gi", "memory_limit": "4Gi",
                "canary": {"enabled": True, "steps": [10, 30, 60, 100],
                           "pause_duration": "5m", "traffic_router": "nginx"},
            },
        },
        "gitops": {"repo": gitops_repo, "branch": gitops_branch},
        "argocd": {"staging_auto_sync": True, "production_auto_sync": False},
        "evals": {
            "enabled": evals_enabled,
            "judge_model": judge_model,
            "thresholds": {
                "prompt_regression": 0.90,
                "tool_call_validation": 0.95,
                "rag_retrieval": 0.85,
                "hallucination_max": 0.05,
                "safety": 0.98,
                "latency_p95_ms": 15000,
                "latency_p99_ms": 30000,
                "avg_tokens": 2000,
            },
        },
        "notifications": {"slack_webhook": False, "github_issues_on_rollback": True},
    }

    # Write cicd.config.yaml
    with open(config_path, "w") as f:
        yaml.dump(cfg, f, default_flow_style=False, sort_keys=False)
    print(f"\n  [ok] cicd.config.yaml written.")

    return cfg


# ─────────────────────────────────────────────────────────────────────────────
# Entry Point
# ─────────────────────────────────────────────────────────────────────────────

def print_banner(cfg: dict, output_dir: Path):
    language = cfg["app"].get("language", "auto")
    if language == "auto":
        language = detect_language(output_dir)
    registry_url = resolve_registry_url(cfg)
    SEP = "+" + "-" * 49 + "+"
    def row(label, value):
        print(f"|  {label:<12}: {str(value)[:33]:<33}|")
    print(SEP)
    print("|        Golden CI/CD Generator                   |")
    print(SEP)
    row("App name",   cfg["app"]["name"])
    row("Language",   language)
    row("Cloud",      cfg["cloud"]["provider"])
    row("Registry",   registry_url[:33])
    row("K8s type",   cfg["kubernetes"].get("cluster_type", "generic"))
    row("Evals",      "enabled" if cfg.get("evals", {}).get("enabled", True) else "disabled")
    row("Output dir", str(output_dir)[:33])
    print(SEP)


def print_next_steps(app_name: str):
    print("\nNext steps:")
    print("  1. bash scripts/setup-secrets.sh    <- configure GitHub secrets")
    print("  2. bash scripts/bootstrap-argocd.sh <- install ArgoCD + Argo Rollouts")
    print("  3. git add . && git commit -m 'ci: add pipeline' && git push")
    print(f"\n  Full guide: EXECUTION_GUIDE.md")
    print(f"  Repo:       https://github.com/bonganiajay26/AGENTIC-CICD")


def main():
    parser = argparse.ArgumentParser(
        description="Golden CI/CD Generator — any app, any cloud.",
        epilog="Run without flags to generate from cicd.config.yaml. "
               "Use --init for interactive setup wizard.",
    )
    parser.add_argument("--config",  default="cicd.config.yaml", help="Config file path")
    parser.add_argument("--output",  default=".", help="Output directory")
    parser.add_argument("--init",    action="store_true", help="Interactive setup wizard")
    parser.add_argument("--detect",  action="store_true", help="Show detected values and exit")
    parser.add_argument("--dry-run", action="store_true", help="Preview files without writing")
    args = parser.parse_args()

    output_dir  = Path(args.output).resolve()
    config_path = Path(args.config)

    # ── --init: run wizard, write config, then generate ───
    if args.init:
        cfg = wizard(output_dir, config_path)
        print_banner(cfg, output_dir)
        print("\nGenerating CI/CD pipeline files...")
        gen = CICDGenerator(cfg, output_dir, dry_run=False)
        gen.generate()
        print_next_steps(cfg["app"]["name"])
        return

    # ── load existing config ───────────────────────────────
    if not config_path.exists():
        print(
            f"\nNo cicd.config.yaml found.\n"
            f"Run the interactive wizard:  python generate_cicd.py --init\n"
            f"Or copy cicd.config.yaml template and edit it manually.",
            file=sys.stderr,
        )
        sys.exit(1)

    with open(config_path) as f:
        cfg = yaml.safe_load(f)

    print_banner(cfg, output_dir)

    if args.detect:
        return

    print("\nGenerating CI/CD pipeline files...")
    gen = CICDGenerator(cfg, output_dir, dry_run=args.dry_run)
    gen.generate()

    prefix = "[DRY-RUN] " if args.dry_run else ""
    print(f"{prefix}Generated {len(gen.files_written)} files.")
    if not args.dry_run:
        print_next_steps(cfg["app"]["name"])


if __name__ == "__main__":
    main()
