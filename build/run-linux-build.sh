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
BUILD_PLATFORM="${CLARK_LINUX_BUILD_PLATFORM:-linux/amd64}"
MODE="${1:-foreground}"
CPU_COUNT="$(sysctl -n hw.ncpu 2>/dev/null || nproc 2>/dev/null || echo 16)"
MEMORY_LIMIT="${CLARK_LINUX_BUILD_MEMORY:-}"

mkdir -p "$OUT_DIR"

echo "[run-linux-build] Building image $IMAGE for $BUILD_PLATFORM..."
docker build --platform "$BUILD_PLATFORM" -t "$IMAGE" -f "$HERE/Dockerfile.linux" "$HERE"

echo "[run-linux-build] Ensuring named volume $WORK_VOL exists..."
docker volume create "$WORK_VOL" >/dev/null
if [[ -n "$MEMORY_LIMIT" ]]; then
  echo "[run-linux-build] Container resources: cpus=$CPU_COUNT memory=$MEMORY_LIMIT"
else
  echo "[run-linux-build] Container resources: cpus=$CPU_COUNT memory=host"
fi

CONTAINER_NAME="${CLARK_LINUX_BUILD_CONTAINER:-clark-browser-linux-build}"
docker rm -f "$CONTAINER_NAME" 2>/dev/null || true

CMD=(docker run --name "$CONTAINER_NAME"
  --platform "$BUILD_PLATFORM"
  -v "$WORK_VOL":/work
  -v "$REPO":/work/clark-browser:ro
  -v "$REPO/patches":/patches:ro
  -v "$HERE/build-linux.sh":/usr/local/bin/build-linux.sh:ro
  -v "$OUT_DIR":/out
  -e "CLARK_WORK_DIR=/work"
  -e "CLARK_BROWSER_TARGET=${CLARK_BROWSER_TARGET:-chrome}"
)
if [[ -n "$MEMORY_LIMIT" ]]; then
  CMD+=(--memory="$MEMORY_LIMIT")
fi
if [[ "$MODE" == "background" ]]; then
  CMD+=(-d)
fi
CMD+=(--cpus="$CPU_COUNT" "$IMAGE" bash /usr/local/bin/build-linux.sh)

if [[ "$MODE" == "background" ]]; then
  echo "[run-linux-build] Starting container in background. Tail logs with:"
  echo "  docker logs -f $CONTAINER_NAME"
  exec "${CMD[@]}" >/dev/null
else
  exec "${CMD[@]}"
fi
