#!/usr/bin/env bash
# Update Kustomize image tag in a given overlay.
# Usage: ./scripts/update-manifests.sh <overlay> <image> <tag>
#   overlay: staging | production
#   image:   full registry path, e.g. 123.dkr.ecr.us-east-1.amazonaws.com/my-app
#   tag:     git SHA or semver

set -euo pipefail

OVERLAY="${1:?Usage: $0 <overlay> <image> <tag>}"
IMAGE="${2:?}"
TAG="${3:?}"

MANIFEST_DIR="k8s/overlays/${OVERLAY}/kustomization.yaml"

if [[ ! -f "$MANIFEST_DIR" ]]; then
  echo "ERROR: $MANIFEST_DIR not found" >&2
  exit 1
fi

# Use kustomize CLI if available, else fall back to sed
if command -v kustomize &>/dev/null; then
  (cd "k8s/overlays/${OVERLAY}" && kustomize edit set image "app=${IMAGE}:${TAG}")
  echo "Updated ${OVERLAY} image to ${IMAGE}:${TAG} via kustomize"
else
  sed -i "s|newTag:.*|newTag: ${TAG}|g" "$MANIFEST_DIR"
  sed -i "s|newName:.*|newName: ${IMAGE}|g" "$MANIFEST_DIR"
  echo "Updated ${OVERLAY} image to ${IMAGE}:${TAG} via sed"
fi
