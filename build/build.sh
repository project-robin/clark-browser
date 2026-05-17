#!/usr/bin/env bash
# Compile the patched Chromium.
#
# Time: 4-12 hours on first build, 5-30 min on incremental.
# Memory: 32+ GB recommended.
# Disk: ~80 GB output.
set -euo pipefail

WORK="${CLARK_WORK_DIR:-$HOME/clark-stealth-build}"
if [[ "$(uname)" == "Darwin" ]]; then
  UC_DIR="$WORK/ungoogled-chromium-macos"
  ARCH="${ARCH:-arm64}"
else
  UC_DIR="$WORK/ungoogled-chromium-debian"
  ARCH="${ARCH:-x64}"
fi

cd "$UC_DIR"

# Skip clone; assume fetch-source + apply-patches already ran.
./build.sh -d "$ARCH"

echo
echo "Build done. Binary at:"
echo "  $UC_DIR/build/src/out/Default/Chromium.app/Contents/MacOS/Chromium    (macOS)"
echo "  $UC_DIR/build/src/out/Default/chrome                                  (Linux)"
echo
echo "Smoke test:"
echo "  CLARK_BINARY_PATH=<that path> python -m clarkbrowser info"
echo "  CLARK_BINARY_PATH=<that path> python examples/stealth_check.py"
