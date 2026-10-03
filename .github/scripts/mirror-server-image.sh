#!/usr/bin/env bash
set -euo pipefail

: "${DOCKER_HUB_USERNAME:?}" "${IMAGE_DIGEST:?}" "${BASE_TAG:?}"
: "${ACR_REGISTRY:?}" "${ACR_NAMESPACE:?}" "${ACR_USERNAME:?}" "${ACR_PASSWORD:?}"
[[ "$IMAGE_DIGEST" =~ ^sha256:[a-f0-9]{64}$ ]] || { echo 'Invalid source digest' >&2; exit 1; }
COPY_TIMEOUT_SECONDS=${COPY_TIMEOUT_SECONDS:-1800}
COPY_ATTEMPTS=${COPY_ATTEMPTS:-2}
AUTH_FILE="${DOCKER_CONFIG:-$HOME/.docker}/config.json"
SOURCE_REPO="docker://${DOCKER_HUB_USERNAME}/trailsnap-server"
DEST_REPO="docker://${ACR_REGISTRY}/${ACR_NAMESPACE}/trailsnap-server"

# Preserve the raw multi-platform manifest when calculating its digest.
manifest_digest() {
  timeout 60s skopeo inspect --raw --authfile "$AUTH_FILE" "$1" | sha256sum | awk '{print "sha256:" $1}'
}

if [[ "${MIRROR_ONLY:-false}" == true ]]; then
  actual=$(manifest_digest "${SOURCE_REPO}:${BASE_TAG}")
  [[ "$actual" == "$IMAGE_DIGEST" ]] || { echo 'Source version does not match requested digest' >&2; exit 1; }
fi

# Keep passwords off command-line arguments and reuse Docker Hub authentication.
printf '%s' "$ACR_PASSWORD" | timeout 60s skopeo login \
  --authfile "$AUTH_FILE" --username "$ACR_USERNAME" --password-stdin "$ACR_REGISTRY"

copy_image() {
  local source=$1 destination=$2 attempt status
  for ((attempt=1; attempt<=COPY_ATTEMPTS; attempt++)); do
    echo "Copy attempt ${attempt}/${COPY_ATTEMPTS}, timeout ${COPY_TIMEOUT_SECONDS}s: ${destination}"
    if timeout "${COPY_TIMEOUT_SECONDS}s" skopeo copy --all --preserve-digests --retry-times 2 \
      --authfile "$AUTH_FILE" "$source" "$destination"; then
      return 0
    else
      status=$?
      echo "Copy failed with exit ${status}" >&2
    fi
    # A new attempt reuses blobs already uploaded, including after timeout (124).
    if ((attempt<COPY_ATTEMPTS)); then sleep 10; fi
  done
  return "$status"
}

copy_image "${SOURCE_REPO}@${IMAGE_DIGEST}" "${DEST_REPO}:${BASE_TAG}"
actual=$(manifest_digest "${DEST_REPO}:${BASE_TAG}")
[[ "$actual" == "$IMAGE_DIGEST" ]] || { echo 'ACR version digest mismatch' >&2; exit 1; }

if [[ -n "${EXTRA_TAG:-}" ]]; then
  # The alias reuses ACR's own blobs rather than transferring from Docker Hub again.
  # Keep its separate budget short so both tags fit within the workflow's budget.
  COPY_TIMEOUT_SECONDS=120
  copy_image "${DEST_REPO}@${IMAGE_DIGEST}" "${DEST_REPO}:${EXTRA_TAG}"
  actual=$(manifest_digest "${DEST_REPO}:${EXTRA_TAG}")
  [[ "$actual" == "$IMAGE_DIGEST" ]] || { echo 'ACR alias digest mismatch' >&2; exit 1; }
fi
echo "ACR publication verified: ${BASE_TAG} ${EXTRA_TAG:-} -> ${IMAGE_DIGEST}"
