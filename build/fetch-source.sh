#!/usr/bin/env bash
# Fetch ungoogled-chromium build harness + Chromium 148 source.
# Disk: ~50 GB. Time: 30-60 min on a fast connection.
set -euo pipefail

WORK="${CLARK_WORK_DIR:-$HOME/clark-stealth-build}"
mkdir -p "$WORK"
cd "$WORK"

echo "Work dir: $WORK"

if [[ ! -d depot_tools ]]; then
  git clone --depth=1 \
    https://chromium.googlesource.com/chromium/tools/depot_tools.git
fi

if [[ ! -d ungoogled-chromium-macos ]] && [[ "$(uname)" == "Darwin" ]]; then
  git clone --recurse-submodules --depth=1 \
    https://github.com/ungoogled-software/ungoogled-chromium-macos.git
  cd ungoogled-chromium-macos
elif [[ ! -d ungoogled-chromium-debian ]]; then
  git clone --recurse-submodules --depth=1 \
    https://github.com/ungoogled-software/ungoogled-chromium-debian.git
  cd ungoogled-chromium-debian
fi

if [[ ! -d build/src ]]; then
  echo "Cloning Chromium source — this is the long step..."
  if [[ "$(uname)" == "Darwin" ]]; then
    PYTHON=$(command -v python3.12 || command -v python3.11 || command -v python3)
    "$PYTHON" ungoogled-chromium/utils/clone.py -p mac-arm -o "$PWD/build/src"
  else
    PYTHON=$(command -v python3.12 || command -v python3.11 || command -v python3)
    "$PYTHON" ungoogled-chromium/utils/clone.py -p linux -o "$PWD/build/src"
  fi
fi

echo "Source fetched at: $PWD/build/src"
echo "Next: ./apply-patches.sh"
