#!/usr/bin/env bash
# Build clark-browser for Linux x86_64 inside the build container.
#
# Mount points (created by run-linux-build.sh on host):
#   /work          — persistent build dir (~80 GB; bind-mount to host)
#   /patches       — read-only clark-browser/patches tree
#   /out           — release artifact (~200 MB clark-browser-linux-x64.tar.gz)
#
# Exit code is the build's exit code. Re-running from a partial state is safe.
set -euo pipefail

WORK="${CLARK_WORK_DIR:-/work}"
PATCHES="/patches"
OUT="/out"
PYTHON=$(command -v python3)
CLARK_BROWSER_TARGET="${CLARK_BROWSER_TARGET:-chrome}"

pip_install() {
  python3 -m pip install --quiet "$@" || \
    python3 -m pip install --quiet --break-system-packages "$@"
}

case "$CLARK_BROWSER_TARGET" in
  headless|headless_shell) CLARK_BROWSER_TARGET="headless_shell" ;;
  chrome) CLARK_BROWSER_TARGET="chrome" ;;
  *)
    echo "[clark-build] unsupported CLARK_BROWSER_TARGET=$CLARK_BROWSER_TARGET" >&2
    echo "[clark-build] supported targets: headless_shell, chrome" >&2
    exit 2
    ;;
esac

# Detect host architecture. The chromium build supports cross-compiling from
# a linux/arm64 host (no Rosetta on Apple Silicon = ~3-5x faster) to a
# linux/x64 target. When HOST_ARCH=arm64
# we set chromium's host_cpu/target_cpu accordingly and use the cipd
# linux-arm64 toolchain channels.
HOST_ARCH="$(uname -m)"
case "$HOST_ARCH" in
  aarch64|arm64) HOST_ARCH="arm64"; CIPD_PLAT="linux-arm64" ;;
  x86_64|amd64)  HOST_ARCH="amd64"; CIPD_PLAT="linux-amd64" ;;
  *) echo "[clark-build] unsupported host arch: $HOST_ARCH" >&2; exit 1 ;;
esac
echo "[clark-build] host arch: $HOST_ARCH (cipd platform: $CIPD_PLAT)"

# When a persistent /work volume moves between arm64 and amd64 containers,
# wipe architecture-specific toolchains so the script re-fetches matching ones.
if [[ -f /work/build/src/buildtools/linux64/gn ]]; then
  GN_FILE="$(file /work/build/src/buildtools/linux64/gn 2>/dev/null || true)"
  RESET_ARCH=0
  if [[ "$HOST_ARCH" == "arm64" && "$GN_FILE" != *"ARM aarch64"* ]]; then
    RESET_ARCH=1
  elif [[ "$HOST_ARCH" == "amd64" && "$GN_FILE" != *"x86-64"* ]]; then
    RESET_ARCH=1
  fi
  if [[ "$RESET_ARCH" == "1" ]]; then
    echo "[clark-build] $HOST_ARCH host detected but cached toolchains differ; resetting..."
    echo "[clark-build] cached gn: $GN_FILE"
    rm -rf /work/build/src/buildtools/linux64
    rm -rf /work/build/src/third_party/llvm-build
    rm -rf /work/build/src/third_party/rust-toolchain
    rm -rf /work/build/src/out/Default
  fi
fi

echo "[clark-build] work=$WORK patches=$PATCHES out=$OUT target=$CLARK_BROWSER_TARGET"
mkdir -p "$WORK" "$OUT"

cd "$WORK"

# Stage 1: clone ungoogled-chromium pinned to the macOS-variant ref. We pin
# explicitly to the 148.0.7778.96-1 tag so the upstream submodule revision
# can't drift back to 120.x (which is what ungoogled-chromium-debian's
# current submodule pin points at — and which is incompatible with our
# patch line numbers).
UC_TAG="${CLARK_UC_TAG:-148.0.7778.96-1}"
if [[ ! -d ungoogled-chromium ]]; then
  echo "[clark-build] Cloning ungoogled-chromium @ ${UC_TAG}..."
  git clone --depth=1 --branch "$UC_TAG" \
    https://github.com/ungoogled-software/ungoogled-chromium.git || \
  git clone https://github.com/ungoogled-software/ungoogled-chromium.git
  (cd ungoogled-chromium && git checkout "$UC_TAG" 2>/dev/null || true)
fi

# Defang clone.py: comment out the gsutil submodule update step. With
# --depth=1 git can only fetch HEAD, but clone.py pins specific commits,
# so the submodule update always fails or hangs on the httplib2 fetch.
# The chromium build itself never invokes gsutil; the bundled copy is
# only needed if you want to run cloud storage commands manually.
# The clone.py gsutil submodule patch is a Rosetta workaround. On native
# Linux hosts (EC2, GitHub Actions) the recursive submodule update runs
# fine and gives gsutil its bundled Python deps. Set CLARK_NO_CLONE_PATCH=1
# in the environment to skip the patch.
if [[ "${CLARK_NO_CLONE_PATCH:-0}" != "1" ]] && ! grep -q 'CLARK_PATCHED_GSUTIL_SKIP' ungoogled-chromium/utils/clone.py; then
  echo "[clark-build] Patching clone.py to skip gsutil submodule update..."
  python3 - <<'PYEOF'
import re
from pathlib import Path
p = Path('ungoogled-chromium/utils/clone.py')
text = p.read_text()
# The original chunk is a multi-line run(...) call ending in a closing
# `)` line. Commenting only the first line orphans `cwd=gsupath,` and
# breaks Python parsing — replace the whole call with pass().
pattern = re.compile(
    r"run\(\[\s*'git',\s*'submodule',\s*'update',\s*'--init',\s*'--recursive'.*?\)",
    re.DOTALL,
)
m = pattern.search(text)
assert m, "clone.py shape changed; cannot patch"
text = text[:m.start()] + (
    "pass  # CLARK_PATCHED_GSUTIL_SKIP: skipped recursive submodule fetch.\n"
    "    # The original `git submodule update --init --recursive --depth=1`\n"
    "    # against pinned commits hangs on httplib2; the chromium build\n"
    "    # never invokes gsutil so this step is unneeded."
) + text[m.end():]
p.write_text(text)
PYEOF
fi

# Stage 2: fetch chromium source via clone.py -----------------------------------
if [[ ! -d build/src/chrome ]]; then
  echo "[clark-build] Cloning Chromium source (this is the 30-60 min step)..."
  mkdir -p build
  if ! "$PYTHON" ungoogled-chromium/utils/clone.py -p linux -o "$PWD/build/src"; then
    if [[ ! -d build/src/chrome ]]; then
      echo "[clark-build] clone.py failed before Chromium source was available" >&2
      exit 2
    fi
    echo "[clark-build] clone.py failed after source checkout; continuing to recovery sync..."
  fi
fi

# Stage 2b: recover from a partial clone where gclient sync didn't fully
# materialise third_party/*. Detect by checking if a known third_party dir
# (angle's dotfile_settings.gni) is missing, then re-run gclient sync with
# FULL history (not --no-history; that mode requires every pinned commit to
# be reachable at depth=1, which several DEPS pins aren't).
if [[ ! -f build/src/third_party/angle/dotfile_settings.gni ]] \
   || [[ ! -f build/src/v8/gni/v8.gni ]] \
   || [[ ! -f build/src/third_party/skia/BUILD.gn ]] \
   || [[ ! -f build/src/third_party/node/node_modules/lit-html/directives/repeat.d.ts ]]; then
  echo "[clark-build] Recovering missing chromium DEPS via gclient sync..."
  # Reset main src to a clean state so gclient sync can checkout pinned commits
  # without complaining about local patch changes from a previous run.
  (cd build/src && git checkout -- . 2>/dev/null && git clean -fdx -e uc_staging -e .clark-applied -e .ungoogled-applied 2>/dev/null) || true
  find build/src -path '*/.git/index.lock' -delete 2>/dev/null || true
  rm -f build/src/.clark-applied/* build/src/.ungoogled-applied 2>/dev/null || true
  cat > build/src/uc_staging/.gclient <<GCEOF
solutions = [
  {
    "name": "${PWD}/build/src",
    "url": "https://chromium.googlesource.com/chromium/src.git",
    "managed": False,
    "custom_deps": {
      "${PWD}/build/src/third_party/angle/third_party/VK-GL-CTS/src": None,
    },
    "custom_vars": {
      "checkout_configuration": "small",
      "non_git_source": "False",
    },
  },
];
target_os = ['unix'];
target_os_only = True;
target_cpu = ['x64'];
target_cpu_only = True;
GCEOF
  # depot_tools needs cipd bootstrapped AND on PATH for gclient's package
  # fetcher to work. DEPOT_TOOLS_UPDATE=0 stops gclient from trying to
  # git-pull its own repo (which would conflict with our clone.py patch).
  DT="$PWD/build/src/uc_staging/depot_tools"
  bash "$DT/cipd_bin_setup.sh"
  export PATH="$DT:$PATH"
  # depot_tools' bundled gsutil path is brittle under Python 3.12 because its
  # vendored dependency set still imports removed stdlib modules. Use an
  # isolated venv-backed gsutil instead, but keep depot_tools/gclient otherwise.
  GSUTIL_VENV="$WORK/.clark-gsutil-venv"
  if [[ ! -x "$GSUTIL_VENV/bin/gsutil" ]]; then
    "$PYTHON" -m venv "$GSUTIL_VENV"
    "$GSUTIL_VENV/bin/python" -m pip install --quiet "gsutil==5.35"
  fi
  SYSTEM_GSUTIL="$GSUTIL_VENV/bin/gsutil"
  python3 - "$DT/download_from_google_storage.py" "$SYSTEM_GSUTIL" <<'PY'
import pathlib
import re
import sys

path = pathlib.Path(sys.argv[1])
system_gsutil = sys.argv[2]
text = path.read_text()
text = re.sub(
    r"GSUTIL_DEFAULT_PATH = os\.path\.join\([^\n]+\n\s+'gsutil\.py'\)",
    f"GSUTIL_DEFAULT_PATH = {system_gsutil!r}",
    text,
    count=1,
)
text = text.replace("cmd = [self.VPYTHON3, self.path]", "cmd = [self.path]")
path.write_text(text)
print(f"download_from_google_storage.py: GSUTIL_DEFAULT_PATH={system_gsutil}, direct_exec=True")
PY
  # `--jobs=2` keeps us under chromium.googlesource.com's rate limit
  # (429 starts around 8+ concurrent fetches from one IP). Retry loop
  # backs off so transient 429s don't kill the build.
  GCLIENT_OK=0
  for attempt in 1 2 3 4 5; do
    find build/src -path '*/.git/index.lock' -delete 2>/dev/null || true
    if (cd build/src/uc_staging && \
         DEPOT_TOOLS_UPDATE=0 PYTHONDONTWRITEBYTECODE=1 \
         PATH="$DT:$PATH" \
         ./depot_tools/gclient sync -f -D -R --nohooks --sysroot=None \
                                    --jobs=2); then
      GCLIENT_OK=1
      break
    fi
    sleep_for=$((attempt * 30))
    echo "[clark-build] gclient sync attempt $attempt failed; sleeping ${sleep_for}s..."
    sleep "$sleep_for"
  done
  if [[ "$GCLIENT_OK" != "1" ]]; then
    echo "[clark-build] gclient sync failed after retries" >&2
    exit 3
  fi
fi

# Stage 3: apply ungoogled patches ----------------------------------------------
# `patch --batch` answers "skip" to all prompts (file not found / hunk fails).
# `set +e` so a few skip-able patches don't abort the whole series — we log
# them as warnings and keep going. ungoogled patch series isn't perfectly
# aligned with the upstream tag; a handful are renames that already happened
# upstream and don't need to apply.
if [[ ! -f build/src/.ungoogled-applied ]]; then
  echo "[clark-build] Resetting source tree to clean state..."
  (cd build/src && git checkout -- . 2>/dev/null && git clean -fd 2>/dev/null) || true
  echo "[clark-build] Applying ungoogled-chromium patch series..."
  cd build/src
  set +e
  failed=()
  for p in $(cat ../../ungoogled-chromium/patches/series); do
    if ! patch -p1 --batch --forward --no-backup-if-mismatch -F3 \
        < "../../ungoogled-chromium/patches/$p" > /tmp/patch.log 2>&1; then
      failed+=("$p")
      echo "[clark-build]   WARN: ungoogled patch failed: $p"
      head -5 /tmp/patch.log | sed 's/^/[clark-build]     /'
    fi
  done
  set -e
  echo "[clark-build] ungoogled series done; ${#failed[@]} patch(es) skipped"
  touch .ungoogled-applied
  cd ../..
fi

# Stage 4: apply clark patches --------------------------------------------------
# Clark patches with actual diff content MUST apply (these are our own).
# Spec-only patches (no `diff --git` block) are intentionally inert
# placeholders for future work — skip them with a note.
echo "[clark-build] Applying clark-browser patch series..."
cd build/src
for p in "$PATCHES"/0*.patch; do
  name=$(basename "$p")
  if [[ -f ".clark-applied/$name.done" ]]; then continue; fi
  if ! grep -q '^diff --git' "$p"; then
    echo "[clark-build]   $name (spec-only; skipping)"
    mkdir -p .clark-applied && touch ".clark-applied/$name.done"
    continue
  fi
  echo "[clark-build]   $name"
  if patch -p1 --batch --forward --no-backup-if-mismatch -F3 < "$p"; then
    mkdir -p .clark-applied && touch ".clark-applied/$name.done"
  else
    echo "[clark-build] FAILED to apply clark patch: $name" >&2
    exit 2
  fi
done

# Stage 5: drop in the 000-shared headers + sources -----------------------------
if [[ -d "$PATCHES/000-shared" ]]; then
  echo "[clark-build] Copying 000-shared files into source tree..."
  cp -fv "$PATCHES/000-shared/clark_fingerprint_switches.h" \
    third_party/blink/common/ 2>/dev/null || true
  cp -fv "$PATCHES/000-shared/clark_fingerprint_switches.cc" \
    third_party/blink/common/ 2>/dev/null || true
  cp -fv "$PATCHES/000-shared/clark_seed.h" \
    third_party/blink/common/ 2>/dev/null || true
  cp -fv "$PATCHES/000-shared/clark_seed.cc" \
    third_party/blink/common/ 2>/dev/null || true
  # Some patches include via the older "chrome/common/clark_seed.h" path.
  # Mirror just the header there so #includes resolve; the .cc still
  # compiles in third_party/blink/common via that target's BUILD.gn.
  mkdir -p chrome/common
  cp -fv "$PATCHES/000-shared/clark_seed.h" chrome/common/ 2>/dev/null || true
  cp -fv "$PATCHES/000-shared/clark_fingerprint_switches.h" \
    chrome/common/ 2>/dev/null || true

  # Wire the .cc files into third_party/blink/common/BUILD.gn so they
  # actually get compiled and linked into blink_common (which everything
  # transitively links). Without this, the .cc files just sit in the tree
  # and ld.lld fails with "undefined symbol: clark::seed::*" at link time.
  GN_FILE=third_party/blink/common/BUILD.gn
  if ! grep -q "clark_seed.cc" "$GN_FILE"; then
    python3 - <<'PY'
import re, pathlib
p = pathlib.Path("third_party/blink/common/BUILD.gn")
s = p.read_text()
# Find the first `sources = [` block and insert clark sources right after.
needle = 'sources = ['
i = s.find(needle)
if i < 0:
    raise SystemExit("BUILD.gn: no sources = [ block found")
# Skip to end of that line
nl = s.find('\n', i)
inject = (
    '\n    "clark_fingerprint_switches.cc",'
    '\n    "clark_fingerprint_switches.h",'
    '\n    "clark_seed.cc",'
    '\n    "clark_seed.h",'
)
p.write_text(s[:nl] + inject + s[nl:])
print("BUILD.gn: clark sources wired into blink_common target")
PY
  fi
fi
cd ../..

# Stage 6: build ----------------------------------------------------------------
echo "[clark-build] Building (this is the multi-hour step)..."
cd build/src
mkdir -p out/Default
if [[ "$CLARK_BROWSER_TARGET" == "headless_shell" ]]; then
  cat > out/Default/args.gn <<'GNEOF'
import("//build/args/headless.gn")
GNEOF
else
  : > out/Default/args.gn
fi
cat >> out/Default/args.gn <<'GNEOF'
is_debug = false
# Keep official_build true to avoid pulling in devtools-frontend bundling
# (which needs esbuild that our nohooks gclient sync didn't fetch). Disable
# ThinLTO explicitly — that's the dominant slow step under Rosetta on Apple
# Silicon. is_official_build=true normally implies LTO; we override.
is_official_build = true
use_thin_lto = false
thin_lto_enable_optimizations = false
# CFI requires ThinLTO; disable both together. CFI is exploit-mitigation
# hardening, irrelevant to fingerprint stealth in a container.
is_cfi = false
symbol_level = 0
blink_symbol_level = 0
v8_symbol_level = 0
enable_nacl = false
enable_remoting = false
proprietary_codecs = true
ffmpeg_branding = "Chrome"
treat_warnings_as_errors = false
GNEOF
# Inject host_cpu/target_cpu/use_sysroot based on the actual host. When
# cross-compiling arm64-host -> x64-target we need use_sysroot=true so
# chromium fetches the right amd64 sysroot via install-sysroot.py.
if [[ "$HOST_ARCH" == "arm64" ]]; then
  cat >> out/Default/args.gn <<'GNEOF'
host_cpu = "arm64"
target_cpu = "x64"
v8_target_cpu = "x64"
use_sysroot = true
GNEOF
else
  cat >> out/Default/args.gn <<'GNEOF'
# clone.py runs gclient with `--nohooks`, so the sysroot tarball isn't
# downloaded. Use the host glibc instead.
use_sysroot = false
GNEOF
fi
cat >> out/Default/args.gn <<'GNEOF'
# Disable safe_browsing entirely so the ungoogled fix-pruned-binaries patch
# (which removes safe_browsing sources but doesn't always apply cleanly on
# tip-of-148) doesn't break the gn build graph.
safe_browsing_mode = 0
# Disable PGO (profile-guided optimization). PGO profiles are downloaded by
# tools/update_pgo_profiles.py — which we skipped to keep the toolchain
# fetch focused. Without profiles, gn gen fails in build/config/compiler/pgo.
chrome_pgo_phase = 0
GNEOF

# Chromium 148 needs gn ≥ 2300. Ubuntu's `generate-ninja` package ships an
# older gn that rejects modern .gn syntax (exec_script_allowlist), so we
# fetch the cipd-pinned binary matching DEPS' gn_version. Note: pwd here is
# build/src after `cd build/src` above.
DT="$PWD/uc_staging/depot_tools"
GN_REV=$(grep "'gn_version'" "$PWD/DEPS" | sed -E "s/.*git_revision:([a-f0-9]+).*/\1/" | head -1)
echo "[clark-build] Ensuring gn pin git_revision:$GN_REV is installed..."
if [[ ! -x buildtools/linux64/gn ]]; then
  mkdir -p buildtools/linux64
  "$DT/cipd" install "gn/gn/${CIPD_PLAT}" "git_revision:$GN_REV" \
    -root buildtools/linux64 2>&1 | tail -3
fi
GN_BIN="$PWD/buildtools/linux64/gn"
"$GN_BIN" --version

# Stub gclient_args.gni — normally written by `gclient sync` runhooks
# (which we skip via --nohooks). Defaults match the standard chromium
# linux build profile. Always re-write so newly-required keys get picked up.
cat > build/config/gclient_args.gni <<'GNIEOF'
# Stubbed by clark-browser build-linux.sh because gclient ran with --nohooks.
checkout_android = false
checkout_android_prebuilts_build_tools = false
checkout_android_native_support = false
checkout_chromium_autofill_test_dependencies = false
checkout_chromium_internal_resources = false
checkout_clusterfuzz_data = false
checkout_chromevox_dependencies = false
checkout_clang_coverage_tools = false
checkout_clang_tidy = false
checkout_clangd = false
checkout_copybara = false
checkout_cros_internal = false
checkout_fuchsia = false
checkout_fuchsia_for_arm64_host = false
checkout_fuchsia_internal = false
checkout_glic = false
checkout_glic_e2e_tests = false
checkout_glic_internal = false
checkout_ios = false
checkout_ios_webkit = false
checkout_libaom_testdata = false
checkout_libvpx_testdata = false
checkout_lottie_proprietary_tests = false
checkout_mac_sdk = false
checkout_mutter = false
checkout_nacl = false
checkout_openxr = false
checkout_oculus_sdk = false
checkout_optimization_profiles = false
checkout_pgo_profiles = false
checkout_remoteexec = false
checkout_rts_model = false
checkout_src_internal = false
checkout_telemetry_dependencies = false
checkout_test_data = false
checkout_traffic_annotation_tools = false
checkout_webp_dirs = false
build_with_chromium = true
cros_boards = ""
cros_boards_with_qemu_images = ""
generate_location_tags = true
non_git_source = false
GNIEOF

# Stub LASTCHANGE files written by hooks too.
if [[ ! -f build/util/LASTCHANGE ]]; then
  echo "LASTCHANGE=$(date +%Y-%m-%dT%H:%M:%S)-stub" > build/util/LASTCHANGE
  date +%s > build/util/LASTCHANGE.committime
fi

# Run only the essential gclient hooks that gn gen / ninja actually need.
# Full `gclient runhooks` pulls ~10 GB including PGO profiles, sysroots, etc.
echo "[clark-build] Fetching prebuilt toolchains (rust, clang, llvm)..."
[[ -f third_party/rust-toolchain/VERSION ]] || python3 tools/rust/update_rust.py
[[ -d third_party/llvm-build/Release+Asserts/bin ]] || \
  python3 tools/clang/scripts/update.py
# Prebuilt node bundled with chromium build (used by mojo bindings codegen).
# update_node_binaries is a bash script not python — invoke via bash.
[[ -x third_party/node/linux/node-linux-x64/bin/node ]] || \
  bash third_party/node/update_node_binaries

# gperf (used by Blink to generate CSS at-rule descriptor tables).
[[ -x third_party/gperf/cipd/bin/gperf ]] || \
  "$DT/cipd" install "infra/3pp/tools/gperf/${CIPD_PLAT}" "version:3@3.2" \
    -root third_party/gperf/cipd 2>&1 | tail -3

# DAWN_VERSION / dawn_commit_hash.h — normally written by a clone.py post-step.
mkdir -p gpu/webgpu
if [[ ! -f gpu/webgpu/DAWN_VERSION ]]; then
  python3 build/util/lastchange.py \
    -m DAWN_COMMIT_HASH \
    -s third_party/dawn \
    --revision gpu/webgpu/DAWN_VERSION \
    --header gpu/webgpu/dawn_commit_hash.h
fi
# skia_commit_hash.h - same pattern.
if [[ ! -f gpu/config/gpu_lists_version.h ]]; then
  printf '#define GPU_LISTS_VERSION "0000000000000000000000000000000000000000"\n' \
    > gpu/config/gpu_lists_version.h
fi
# LASTCHANGE files used by build/util/version.py.
[[ -f build/util/LASTCHANGE ]] || \
  echo "LASTCHANGE=$(date +%Y-%m-%dT%H:%M:%S)-stub" > build/util/LASTCHANGE
[[ -f build/util/LASTCHANGE.committime ]] || date +%s > build/util/LASTCHANGE.committime
# Skia commit hash header — chromium #include "skia/ext/skia_commit_hash.h"
# expects it under skia/ext/, not skia/.
if [[ ! -f skia/ext/skia_commit_hash.h ]]; then
  mkdir -p skia/ext
  printf '#define SKIA_COMMIT_HASH "0000000000000000000000000000000000000000"\n' \
    > skia/ext/skia_commit_hash.h
fi
# Keep the legacy path too in case something still includes it.
if [[ ! -f skia/skia_commit_hash.h ]]; then
  mkdir -p skia
  printf '#define SKIA_COMMIT_HASH "0000000000000000000000000000000000000000"\n' \
    > skia/skia_commit_hash.h
fi

# Install chromium's full set of Linux build deps via its bundled script.
# Run once per image; idempotent — apt skips already-installed packages.
if [[ ! -f /tmp/.clark-build-deps-installed ]]; then
  echo "[clark-build] Running chromium install-build-deps.sh..."
  yes | bash build/install-build-deps.sh \
    --no-prompt --no-chromeos-fonts --no-nacl --no-arm 2>&1 | tail -8 || true
  touch /tmp/.clark-build-deps-installed
fi
if [[ ! -f buildtools/linux64/clang-format ]]; then
  CF_REV=$(grep "'clang-format'" "$PWD/buildtools/DEPS" 2>/dev/null \
    | sed -E "s/.*git_revision:([a-f0-9]+).*/\1/" | head -1 || true)
  if [[ -n "$CF_REV" && "$CF_REV" =~ ^[a-f0-9]+$ ]]; then
    "$DT/cipd" install "fuchsia/third_party/clang-format/${CIPD_PLAT}" \
      "git_revision:$CF_REV" -root buildtools/linux64 2>&1 | tail -3 || true
  fi
fi

# Cross-compile sysroot: when host=arm64 target=x64, fetch the debian
# bookworm amd64 sysroot so chromium's compile/link finds amd64 libc and
# system headers. install-sysroot.py is idempotent — skips if already
# installed. (The Sysroot is what we build *against*, not what we run on.)
if [[ "$HOST_ARCH" == "arm64" ]]; then
  echo "[clark-build] Installing amd64 sysroot for cross-compile..."
  python3 build/linux/sysroot_scripts/install-sysroot.py --arch=amd64 2>&1 | tail -5 || true
  python3 build/linux/sysroot_scripts/install-sysroot.py --arch=arm64 2>&1 | tail -5 || true
  # Chromium 148 only declares x64-host -> arm64-target v8 cross toolchains.
  # We need the reverse for arm64-host -> x64-target. Append our declaration
  # idempotently (grep guard).
  if ! grep -q "clang_arm64_v8_x64" build/toolchain/linux/BUILD.gn; then
    cat >> build/toolchain/linux/BUILD.gn <<'GNEOF'

# clark-browser: arm64-host -> x64-target cross-compile v8 host toolchain.
clang_v8_toolchain("clang_arm64_v8_x64") {
  toolchain_args = {
    current_cpu = "arm64"
    v8_current_cpu = "x64"
  }
}
GNEOF
    echo "[clark-build] Added clang_arm64_v8_x64 toolchain to build/toolchain/linux/BUILD.gn"
  fi
fi

"$GN_BIN" gen out/Default
echo "[clark-build] Ninja target: $CLARK_BROWSER_TARGET"
ninja -C out/Default -j "$(nproc)" "$CLARK_BROWSER_TARGET"

# Stage 7: package --------------------------------------------------------------
echo "[clark-build] Packaging..."
cd out/Default
if [[ "$CLARK_BROWSER_TARGET" == "headless_shell" ]]; then
  # Backward-compatible launcher for callers that expect a Chrome-like name.
  cat > chrome <<'SHEOF'
#!/bin/sh
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec "$HERE/headless_shell" "$@"
SHEOF
  chmod +x chrome
else
  # Backward-compatible launcher for older wrapper code and manual scripts
  # that still point at the historical headless_shell path.
  cat > headless_shell <<'SHEOF'
#!/bin/sh
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec "$HERE/chrome" "$@"
SHEOF
  chmod +x headless_shell
fi

PACKAGE_FILES=()
add_package_file() {
  local path="$1"
  if [[ -e "$path" ]]; then
    local existing
    for existing in "${PACKAGE_FILES[@]}"; do
      if [[ "$existing" == "$path" ]]; then
        return
      fi
    done
    PACKAGE_FILES+=("$path")
  fi
}
add_package_glob() {
  local pattern="$1"
  local match
  shopt -s nullglob
  for match in $pattern; do
    add_package_file "$match"
  done
  shopt -u nullglob
}

add_package_file chrome
add_package_file headless_shell
for optional in \
  chrome_crashpad_handler \
  chrome_sandbox \
  headless_command_resources.pak \
  headless_lib_data.pak \
  headless_lib_strings.pak \
  resources.pak \
  chrome_100_percent.pak \
  chrome_200_percent.pak \
  libEGL.so \
  libGLESv2.so \
  libvulkan.so.1 \
  libvk_swiftshader.so \
  vk_swiftshader_icd.json \
  v8_context_snapshot.bin \
  snapshot_blob.bin \
  icudtl.dat \
  locales; do
  if [[ -e "$optional" ]]; then
    add_package_file "$optional"
  fi
done
add_package_glob "*.bin"
add_package_glob "*.json"
add_package_glob "*.pak"
add_package_glob "*.so"
add_package_glob "*.so.*"

tar -czf "$OUT/clark-browser-linux-x64.tar.gz" "${PACKAGE_FILES[@]}"
echo "[clark-build] Done. Artifact: $OUT/clark-browser-linux-x64.tar.gz"
ls -lh "$OUT/clark-browser-linux-x64.tar.gz"

# Stage 8: in-container smoke test ---------------------------------------------
# Run linux_smoke.py against the freshly-built binary. Talks CDP directly via
# websocket-client; no agent-browser dep. Failure here is a hard fail — the
# binary must pass before we publish.
cd "$WORK/build/src"
if [[ "${CLARK_SKIP_SMOKE:-0}" != "1" ]]; then
  echo "[clark-build] Stage 8: in-container smoke test"
  pip_install websocket-client 2>&1 | tail -3 || true
  SMOKE_SCRIPT="$WORK/clark-browser/tests/linux_smoke.py"
  if [[ -f "$SMOKE_SCRIPT" ]]; then
    CLARK_BINARY_PATH="$WORK/build/src/out/Default/$CLARK_BROWSER_TARGET" \
      python3 "$SMOKE_SCRIPT" || {
        echo "[clark-build] SMOKE FAILED — binary at $WORK/build/src/out/Default/$CLARK_BROWSER_TARGET"
        exit 1
      }
    echo "[clark-build] Smoke passed."
  else
    echo "[clark-build] linux_smoke.py not mounted at $SMOKE_SCRIPT; skipping."
  fi
fi
