#!/usr/bin/env bash
# Layer clark patches on top of ungoogled-chromium's patch series.
#
# Run after ./fetch-source.sh has populated $WORK/build/src.
set -euo pipefail

CLARK_REPO="$(cd "$(dirname "$0")/.." && pwd)"
WORK="${CLARK_WORK_DIR:-$HOME/clark-stealth-build}"

if [[ "$(uname)" == "Darwin" ]]; then
  UC_DIR="$WORK/ungoogled-chromium-macos"
else
  UC_DIR="$WORK/ungoogled-chromium-debian"
fi
SRC="$UC_DIR/build/src"

if [[ ! -d "$SRC" ]]; then
  echo "ERROR: Chromium source not found at $SRC. Run fetch-source.sh first." >&2
  exit 2
fi

echo "=== 1. Copy clark patches to ungoogled's patches dir ==="
mkdir -p "$UC_DIR/patches/clark"
cp -v "$CLARK_REPO"/patches/0*.patch "$UC_DIR/patches/clark/"

echo "=== 2. Register in series file ==="
SERIES="$UC_DIR/patches/series"
for p in "$UC_DIR/patches/clark/"0*.patch; do
  name="clark/$(basename "$p")"
  if ! grep -qx "$name" "$SERIES"; then
    echo "$name" >> "$SERIES"
  fi
done

echo "=== 3. Drop shared C++ sources into blink/common/ ==="
COMMON="$SRC/third_party/blink/common"
cp -v "$CLARK_REPO"/patches/000-shared/clark_fingerprint_switches.h "$COMMON/"
cp -v "$CLARK_REPO"/patches/000-shared/clark_fingerprint_switches.cc "$COMMON/"
cp -v "$CLARK_REPO"/patches/000-shared/clark_seed.h "$COMMON/"
cp -v "$CLARK_REPO"/patches/000-shared/clark_seed.cc "$COMMON/"

echo "=== 4. Wire shared sources into third_party/blink/common/BUILD.gn ==="
GN="$COMMON/BUILD.gn"
if ! grep -q "clark_seed" "$GN"; then
  python3 - <<PY
import re
p = "$GN"
s = open(p).read()
old = '''  sources = [
    # NOTE: Please do not add public headers that need to be referenced from
    # outside WebKit, add them in public/common instead.
    "associated_interfaces/associated_interface_provider.cc",'''
new = '''  sources = [
    # NOTE: Please do not add public headers that need to be referenced from
    # outside WebKit, add them in public/common instead.
    "clark_fingerprint_switches.cc",
    "clark_fingerprint_switches.h",
    "clark_seed.cc",
    "clark_seed.h",
    "associated_interfaces/associated_interface_provider.cc",'''
if old in s:
    open(p, 'w').write(s.replace(old, new, 1))
    print("BUILD.gn updated")
else:
    print("WARN: manual edit needed for", p)
PY
fi

echo "=== 5. Drop forwarding headers in chrome/common/ ==="
mkdir -p "$SRC/chrome/common"
cat > "$SRC/chrome/common/clark_fingerprint_switches.h" <<'EOF'
#include "third_party/blink/common/clark_fingerprint_switches.h"
EOF
cat > "$SRC/chrome/common/clark_seed.h" <<'EOF'
#include "third_party/blink/common/clark_seed.h"
EOF

echo "=== 6. Apply via ungoogled-chromium's patches.py ==="
PYTHON=$(command -v python3.12 || command -v python3.11 || command -v python3)
"$PYTHON" "$UC_DIR/ungoogled-chromium/utils/patches.py" apply "$SRC" \
  "$UC_DIR/ungoogled-chromium/patches" "$UC_DIR/patches"

echo
echo "Patches applied. Next: ./build.sh"
