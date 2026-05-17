#!/usr/bin/env bash
# Driver: build clark-browser Linux x86_64 inside a Docker container,
# with a persistent volume so partial progress survives container restarts.
#
# Usage: ./build/run-linux-build.sh [foreground|background]
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/.." && pwd)"

WORK_VOL="${CLARK_LINUX_BUILD_VOL:-clark-browser-linux-build}"
OUT_DIR="${CLARK_LINUX_BUILD_OUT:-$REPO/dist}"
IMAGE="${CLARK_LINUX_BUILD_IMAGE:-clark-browser-linux-build:latest}"
MODE="${1:-foreground}"

mkdir -p "$OUT_DIR"

echo "[run-linux-build] Building image $IMAGE..."
docker build -t "$IMAGE" -f "$HERE/Dockerfile.linux" "$HERE"

echo "[run-linux-build] Ensuring named volume $WORK_VOL exists..."
docker volume create "$WORK_VOL" >/dev/null

CONTAINER_NAME="${CLARK_LINUX_BUILD_CONTAINER:-clark-browser-linux-build}"
docker rm -f "$CONTAINER_NAME" 2>/dev/null || true

CMD=(docker run --name "$CONTAINER_NAME"
  --platform linux/amd64
  -v "$WORK_VOL":/work
  -v "$REPO/patches":/patches:ro
  -v "$HERE/build-linux.sh":/usr/local/bin/build-linux.sh:ro
  -v "$OUT_DIR":/out
  -e "CLARK_WORK_DIR=/work"
  --memory=32g
  --cpus="$(sysctl -n hw.ncpu 2>/dev/null || echo 16)"
  "$IMAGE"
  bash /usr/local/bin/build-linux.sh
)

if [[ "$MODE" == "background" ]]; then
  echo "[run-linux-build] Starting container in background. Tail logs with:"
  echo "  docker logs -f $CONTAINER_NAME"
  exec "${CMD[@]}" -d >/dev/null
else
  exec "${CMD[@]}"
fi
