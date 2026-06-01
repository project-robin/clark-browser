#!/usr/bin/env bash
# Build clark-browser for macOS arm64 on a native macOS host.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
WORK="${CLARK_WORK_DIR:-$HOME/clark-browser-build}"
OUT="${CLARK_OUT_DIR:-$REPO/dist}"
PATCHES="${CLARK_PATCHES_DIR:-$REPO/patches}"
UC_TAG="${CLARK_UC_TAG:-148.0.7778.96-1}"
TARGET_CPU="${CLARK_TARGET_CPU:-arm64}"
NINJA_JOBS="${CLARK_NINJA_JOBS:-$(sysctl -n hw.ncpu 2>/dev/null || echo 8)}"
PYTHON="${CLARK_PYTHON:-}"

if [[ -z "$PYTHON" ]]; then
  for candidate in \
    python3.13 python3.12 python3.11 \
    /usr/local/bin/python3.13 /usr/local/bin/python3.12 /usr/local/bin/python3.11 \
    /Library/Frameworks/Python.framework/Versions/3.13/bin/python3.13 \
    /Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12 \
    /Library/Frameworks/Python.framework/Versions/3.11/bin/python3.11 \
    python3; do
    if command -v "$candidate" >/dev/null 2>&1 || [[ -x "$candidate" ]]; then
      PYTHON="$(command -v "$candidate")"
      if [[ -z "$PYTHON" ]]; then
        PYTHON="$candidate"
      fi
      break
    fi
  done
fi
if [[ -z "$PYTHON" ]]; then
  echo "[clark-mac-build] python 3.11+ is required" >&2
  exit 2
fi
"$PYTHON" - <<'PY'
import sys
if sys.version_info < (3, 11):
    raise SystemExit(
        f"python 3.11+ required for depot_tools; got {sys.version.split()[0]}"
    )
PY
echo "[clark-mac-build] python=$("$PYTHON" -c 'import sys; print(sys.executable, sys.version.split()[0])')"
export PATH="$(dirname "$PYTHON"):$PATH"

# lld treats the default /usr/local/lib search path as fatal when it is absent
# on bare Command Line Tools-only EC2 macOS images.
if [[ ! -d /usr/local/lib ]]; then
  if [[ -w /usr/local ]]; then
    mkdir -p /usr/local/lib
  elif command -v sudo >/dev/null 2>&1; then
    sudo mkdir -p /usr/local/lib
  fi
fi

mkdir -p "$WORK" "$OUT"
cd "$WORK"

"$PYTHON" - <<'PY'
import importlib.util
import subprocess
import sys

missing = [
    package
    for package, module in (("httplib2", "httplib2"), ("PySocks", "socks"))
    if importlib.util.find_spec(module) is None
]
if missing:
    try:
        import pip  # noqa: F401
    except Exception:
        subprocess.check_call([sys.executable, "-m", "ensurepip", "--user"])
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--user", *missing])
PY

if [[ ! -d ungoogled-chromium ]]; then
  git clone --depth=1 --branch "$UC_TAG" \
    https://github.com/ungoogled-software/ungoogled-chromium.git
fi

"$PYTHON" - <<'PY'
from pathlib import Path
p = Path("ungoogled-chromium/utils/clone.py")
s = p.read_text()
s = s.replace("target_os = ['unix'];", "target_os = ['mac'];")
s = s.replace("target_cpu = ['x64'];", "target_cpu = ['arm64'];")
p.write_text(s)
PY

if [[ ! -d build/src/chrome ]]; then
  "$PYTHON" ungoogled-chromium/utils/clone.py -p mac-arm -o "$WORK/build/src"
elif [[ ! -f build/src/third_party/skia/BUILD.gn ]] \
    || [[ ! -f build/src/v8/gni/v8.gni ]]; then
  echo "[clark-mac-build] incomplete Chromium checkout; recloning"
  rm -rf build/src
  "$PYTHON" ungoogled-chromium/utils/clone.py -p mac-arm -o "$WORK/build/src"
fi

cd "$WORK/build/src"
export PATH="$WORK/build/src/uc_staging/depot_tools:$PATH"
GN_BIN="$WORK/build/src/buildtools/mac/gn"
NINJA_BIN="$WORK/build/src/third_party/ninja/ninja"
if [[ ! -x "$GN_BIN" ]]; then
  mkdir -p "$WORK/build/src/buildtools/mac"
  printf "gn/gn/mac-arm64 git_revision:6e8dcdebbadf4f8aa75e6a4b6e0bdf89dce1513a\n" \
    > /tmp/clark-gn.ensure
  "$WORK/build/src/uc_staging/depot_tools/cipd" ensure \
    -root "$WORK/build/src/buildtools/mac" \
    -ensure-file /tmp/clark-gn.ensure
fi
if [[ ! -x "$NINJA_BIN" ]]; then
  mkdir -p "$WORK/build/src/third_party/ninja"
  printf "infra/3pp/tools/ninja/mac-arm64 version:3@1.12.1.chromium.4\n" \
    > /tmp/clark-ninja.ensure
  "$WORK/build/src/uc_staging/depot_tools/cipd" ensure \
    -root "$WORK/build/src/third_party/ninja" \
    -ensure-file /tmp/clark-ninja.ensure
fi
if [[ ! -f "$WORK/build/src/third_party/rust-toolchain/VERSION" ]]; then
  rust_archive="/tmp/clark-rust-toolchain-mac-arm64.tar.xz"
  rust_url="https://storage.googleapis.com/chromium-browser-clang/Mac_arm64/rust-toolchain-6f54d591c3116ee7f8ce9321ddeca286810cc142-7-llvmorg-23-init-5669-g8a0be0bc.tar.xz"
  curl -L -o "$rust_archive" "$rust_url"
  echo "e2e19684f31b653ce9238f6303aec22576085528c294757a7157d4ab5e1926dc  $rust_archive" \
    | shasum -a 256 -c -
  rm -rf "$WORK/build/src/third_party/rust-toolchain"
  mkdir -p "$WORK/build/src/third_party/rust-toolchain"
  tar -xf "$rust_archive" -C "$WORK/build/src/third_party/rust-toolchain"
fi
LLVM_DIR="$WORK/build/src/third_party/llvm-build/Release+Asserts"
if [[ ! -f "$LLVM_DIR/cr_build_revision" ]]; then
  clang_archive="/tmp/clark-clang-mac-arm64.tar.xz"
  clang_url="https://storage.googleapis.com/chromium-browser-clang/Mac_arm64/clang-llvmorg-23-init-5669-g8a0be0bc-4.tar.xz"
  curl -L -o "$clang_archive" "$clang_url"
  echo "84c08af500d1695d2bc378e58bde7e697847597e8e35d0d35f00c603c0c7021b  $clang_archive" \
    | shasum -a 256 -c -
  rm -rf "$LLVM_DIR"
  mkdir -p "$LLVM_DIR"
  tar -xf "$clang_archive" -C "$LLVM_DIR"
fi
if [[ ! -x "$LLVM_DIR/bin/llvm-objdump" ]]; then
  objdump_archive="/tmp/clark-llvmobjdump-mac-arm64.tar.xz"
  objdump_url="https://storage.googleapis.com/chromium-browser-clang/Mac_arm64/llvmobjdump-llvmorg-23-init-5669-g8a0be0bc-4.tar.xz"
  curl -L -o "$objdump_archive" "$objdump_url"
  echo "8e48488827c82749bc75e7bcd4209d9d780dfe45fa8cd29f96b3a8dbcd9213b9  $objdump_archive" \
    | shasum -a 256 -c -
  tar -xf "$objdump_archive" -C "$LLVM_DIR"
fi
NODE_DIR="$WORK/build/src/third_party/node/mac_arm64"
if [[ ! -x "$NODE_DIR/node-darwin-arm64/bin/node" ]]; then
  node_archive="/tmp/clark-node-darwin-arm64.tar.gz"
  node_url="https://storage.googleapis.com/chromium-nodejs/6661e9b9bd7df6b45daf506c82d06d303597cb27"
  curl -L -o "$node_archive" "$node_url"
  echo "b1be502d1635330ebf51d85f8d32a0d3dd92b35c6700def56ae6f903906ea825  $node_archive" \
    | shasum -a 256 -c -
  rm -rf "$NODE_DIR"
  mkdir -p "$NODE_DIR"
  tar -xzf "$node_archive" -C "$NODE_DIR"
fi
NODE_MODULES_DIR="$WORK/build/src/third_party/node/node_modules"
if [[ ! -f "$NODE_MODULES_DIR/lit-html/directives/repeat.d.ts" ]]; then
  node_modules_archive="/tmp/clark-node-modules.tar.gz"
  node_modules_url="https://storage.googleapis.com/chromium-nodejs/6c15205ac08a854251151c1fbeb8978d2ca5a022"
  curl -L -o "$node_modules_archive" "$node_modules_url"
  echo "2ca9e4b10119399283bf9e9da695cd747491921f77063d54729afcbeb304e6aa  $node_modules_archive" \
    | shasum -a 256 -c -
  rm -rf "$NODE_MODULES_DIR"
  mkdir -p "$NODE_MODULES_DIR"
  tar -xzf "$node_modules_archive" -C "$NODE_MODULES_DIR"
fi
DSYMUTIL="$WORK/build/src/tools/clang/dsymutil/bin/dsymutil"
DSYMUTIL_SHA1="$WORK/build/src/tools/clang/dsymutil/bin/dsymutil.arm64.sha1"
if [[ ! -x "$DSYMUTIL" ]]; then
  dsym_hash="$(tr -d '[:space:]' < "$DSYMUTIL_SHA1")"
  curl -L -o "$DSYMUTIL" "https://storage.googleapis.com/chromium-browser-clang/$dsym_hash"
  echo "$dsym_hash  $DSYMUTIL" | shasum -a 1 -c -
  chmod +x "$DSYMUTIL"
fi

if [[ ! -f .ungoogled-applied ]]; then
  set +e
  failed=()
  for patch_name in $(cat "$WORK/ungoogled-chromium/patches/series"); do
    patch_file="$WORK/ungoogled-chromium/patches/$patch_name"
    if ! patch -p1 --batch --forward --no-backup-if-mismatch -F3 \
        < "$patch_file" > /tmp/uc-patch.log 2>&1; then
      failed+=("$patch_name")
      echo "[clark-mac-build] WARN: ungoogled patch skipped: $patch_name"
      head -5 /tmp/uc-patch.log | sed 's/^/[clark-mac-build]   /'
    fi
  done
  set -e
  echo "[clark-mac-build] ungoogled series done; ${#failed[@]} patch(es) skipped"
  touch .ungoogled-applied
fi

mkdir -p .clark-applied
for patch_file in "$PATCHES"/0*.patch; do
  name="$(basename "$patch_file")"
  if [[ -f ".clark-applied/$name.done" ]]; then
    continue
  fi
  if ! grep -q '^diff --git' "$patch_file"; then
    echo "[clark-mac-build] $name (spec-only; skipping)"
    touch ".clark-applied/$name.done"
    continue
  fi
  echo "[clark-mac-build] $name"
  if [[ "$name" == "0016-webgl-vendor-renderer-from-cli.patch" ]]; then
    git checkout -- third_party/blink/renderer/modules/webgl/webgl_rendering_context_base.cc
    rm -f third_party/blink/renderer/modules/webgl/webgl_rendering_context_base.cc.rej
  fi
  if ! patch -p1 --batch --forward --no-backup-if-mismatch -F3 < "$patch_file"; then
    if [[ "$name" == "0006-navigator-platform-hwc-ua-from-cli.patch" ]]; then
      echo "[clark-mac-build] repairing $name hardwareConcurrency hunk"
      "$PYTHON" - <<'PY'
from pathlib import Path

p = Path("third_party/blink/renderer/core/execution_context/navigator_base.cc")
s = p.read_text()
if "clark-stealth #13" not in s:
    needle = "unsigned int NavigatorBase::hardwareConcurrency() const {\n"
    block = """  // clark-stealth #13: --fingerprint-hardware-concurrency takes precedence,
  // followed by seed-derived value, then reduced/probed values.
  auto* cl = base::CommandLine::ForCurrentProcess();
  if (cl->HasSwitch(clark::switches::kFingerprintHardwareConcurrency)) {
    unsigned int v = 0;
    if (base::StringToUint(
            cl->GetSwitchValueASCII(
                clark::switches::kFingerprintHardwareConcurrency),
            &v) &&
        v > 0 && v <= 256) {
      return v;
    }
  }
  if (cl->HasSwitch(clark::switches::kFingerprint)) {
    return clark::seed::HardwareConcurrency();
  }
"""
    if needle not in s:
        raise SystemExit("navigator_base.cc: hardwareConcurrency entry not found")
    p.write_text(s.replace(needle, needle + block, 1))
rej = p.with_suffix(p.suffix + ".rej")
if rej.exists():
    rej.unlink()
PY
    elif [[ "$name" == "0016-webgl-vendor-renderer-from-cli.patch" ]]; then
      echo "[clark-mac-build] repairing $name extension filter hunk"
      "$PYTHON" - <<'PY'
from pathlib import Path

p = Path("third_party/blink/renderer/modules/webgl/webgl_rendering_context_base.cc")
s = p.read_text()
if "if (!ExtensionSupportedAndAllowed(tracker))" not in s:
    old = """  for (ExtensionTracker* tracker : extensions_) {
    if (ExtensionSupportedAndAllowed(tracker)) {
      result.push_back(tracker->ExtensionName());
    }
  }
"""
    new = """  for (ExtensionTracker* tracker : extensions_) {
    if (!ExtensionSupportedAndAllowed(tracker))
      continue;

    String name = tracker->ExtensionName();
    if (!clark_fingerprint) {
      result.push_back(name);
      continue;
    }

    const std::string name_utf8 = name.Utf8();
    for (const char* allowed : kRealChromeExts) {
      if (name_utf8 == allowed) {
        result.push_back(name);
        break;
      }
    }
  }
"""
    if old not in s:
        raise SystemExit("webgl_rendering_context_base.cc: extension loop not found")
    p.write_text(s.replace(old, new, 1))
rej = p.with_suffix(p.suffix + ".rej")
if rej.exists():
    rej.unlink()
PY
    elif [[ "$name" == "0050-renderer-arg-whitelist-fingerprint.patch" ]]; then
      echo "[clark-mac-build] accepting already-applied $name hunks"
      "$PYTHON" - <<'PY'
from pathlib import Path

p = Path("content/browser/renderer_host/render_process_host_impl.cc")
s = p.read_text()
required = [
    '#include "third_party/blink/common/clark_fingerprint_switches.h"',
    '#include "components/ungoogled/ungoogled_switches.h"',
    "clark::switches::kFingerprintNoise",
    "switches::kFingerprintingClientRectsNoise",
    "switches::kFingerprintingCanvasMeasureTextNoise",
    "switches::kFingerprintingCanvasImageDataNoise",
]
missing = [item for item in required if item not in s]
if missing:
    raise SystemExit("render_process_host_impl.cc missing: " + ", ".join(missing))
rej = p.with_suffix(p.suffix + ".rej")
if rej.exists():
    rej.unlink()
PY
    else
      exit 1
    fi
  fi
  touch ".clark-applied/$name.done"
done

if [[ -d "$PATCHES/000-shared" ]]; then
  cp -fv "$PATCHES/000-shared/clark_fingerprint_switches.h" third_party/blink/common/
  cp -fv "$PATCHES/000-shared/clark_fingerprint_switches.cc" third_party/blink/common/
  cp -fv "$PATCHES/000-shared/clark_seed.h" third_party/blink/common/
  cp -fv "$PATCHES/000-shared/clark_seed.cc" third_party/blink/common/
  mkdir -p chrome/common
  cp -fv "$PATCHES/000-shared/clark_seed.h" chrome/common/
  cp -fv "$PATCHES/000-shared/clark_fingerprint_switches.h" chrome/common/
  if ! grep -q "clark_seed.cc" third_party/blink/common/BUILD.gn; then
    "$PYTHON" - <<'PY'
from pathlib import Path
p = Path("third_party/blink/common/BUILD.gn")
s = p.read_text()
needle = "sources = ["
i = s.find(needle)
if i < 0:
    raise SystemExit("BUILD.gn: no sources = [ block found")
nl = s.find("\n", i)
inject = (
    '\n    "clark_fingerprint_switches.cc",'
    '\n    "clark_fingerprint_switches.h",'
    '\n    "clark_seed.cc",'
    '\n    "clark_seed.h",'
)
p.write_text(s[:nl] + inject + s[nl:])
PY
  fi
fi

"$PYTHON" - <<'PY'
from pathlib import Path

p = Path("build/config/apple/sdk_info.py")
s = p.read_text()
if "clark-browser: tolerate Command Line Tools-only AWS macOS builders" not in s:
    old = """  lines = subprocess.check_output(['xcodebuild',
                                   '-version']).decode('UTF-8').splitlines()
  version_verbatim = lines[0].split()[-1]
  settings['xcode_version'] = FormatVersion(version_verbatim)
  settings['xcode_version_int'] = int(settings['xcode_version'], 10)
  settings['xcode_version_verbatim'] = version_verbatim
  settings['xcode_build'] = lines[-1].split()[-1]
"""
    new = """  try:
    lines = subprocess.check_output(['xcodebuild',
                                     '-version']).decode('UTF-8').splitlines()
  except (subprocess.CalledProcessError, FileNotFoundError):
    # clark-browser: tolerate Command Line Tools-only AWS macOS builders.
    version_verbatim = '16.4'
    settings['xcode_version'] = FormatVersion(version_verbatim)
    settings['xcode_version_int'] = int(settings['xcode_version'], 10)
    settings['xcode_version_verbatim'] = version_verbatim
    settings['xcode_build'] = '16F6'
    return
  version_verbatim = lines[0].split()[-1]
  settings['xcode_version'] = FormatVersion(version_verbatim)
  settings['xcode_version_int'] = int(settings['xcode_version'], 10)
  settings['xcode_version_verbatim'] = version_verbatim
  settings['xcode_build'] = lines[-1].split()[-1]
"""
    if old not in s:
        raise SystemExit("sdk_info.py xcodebuild probe block not found")
    p.write_text(s.replace(old, new, 1))
PY

"$PYTHON" - <<'PY'
from pathlib import Path

p = Path("build/mac/find_sdk.py")
s = p.read_text()
if "clark-browser: fall back to Command Line Tools SDK" not in s:
    old = """  if not os.path.isdir(sdk_dir):
    raise SdkError('Install Xcode, launch it, accept the license ' +
      'agreement, and run `sudo xcode-select -s /path/to/Xcode.app` ' +
      'to continue.')
"""
    new = """  if not os.path.isdir(sdk_dir):
    # clark-browser: fall back to Command Line Tools SDK on AWS macOS builders.
    sdk_path = subprocess.check_output(
        ['xcrun', '--sdk', 'macosx', '--show-sdk-path']).decode('UTF-8').strip()
    best_sdk = subprocess.check_output(
        ['xcrun', '--sdk', 'macosx', '--show-sdk-version']).decode('UTF-8').strip()
    if parse_version(best_sdk) < parse_version(min_sdk_version):
      raise Exception(f'No {min_sdk_version}+ SDK found at {sdk_path}')
    if options.print_sdk_path:
      print(sdk_path)
    if options.print_bin_path:
      clang = subprocess.check_output(
          ['xcrun', '--sdk', 'macosx', '--find', 'clang']).decode('UTF-8').strip()
      print(os.path.dirname(clang) + os.sep)
    if options.print_sdk_build:
      print(subprocess.check_output(
          ['xcrun', '--sdk', 'macosx', '--show-sdk-build-version']
      ).decode('UTF-8').strip())
    print(best_sdk)
    return 0
"""
    if old not in s:
        raise SystemExit("find_sdk.py Xcode error block not found")
    p.write_text(s.replace(old, new, 1))
PY

"$PYTHON" - <<'PY'
from pathlib import Path

p = Path("chrome/test/BUILD.gn")
s = p.read_text()
marker = (
    "      # clark-browser: safe_browsing_mode=0 leaves these Mac test deps "
    "undefined.\n"
)
old = (
    '      "//chrome/common/safe_browsing:archive_analyzer_results",\n'
    '      "//chrome/common/safe_browsing:disk_image_type_sniffer_mac",\n'
)
if marker not in s:
    if old not in s:
        raise SystemExit("chrome/test/BUILD.gn safe browsing Mac deps not found")
    p.write_text(s.replace(old, marker, 1))
PY

"$PYTHON" - <<'PY'
from pathlib import Path

p = Path("third_party/angle/src/libANGLE/renderer/metal/metal_backend.gni")
s = p.read_text()
marker = "# clark-browser: CLT-only AWS macOS builders do not include xcrun metal.\n"
old = (
    "metal_internal_shader_compilation_supported =\n"
    "    angle_has_build && !is_ios && target_os == host_os\n"
)
new = marker + "metal_internal_shader_compilation_supported = false\n"
if marker not in s:
    if old not in s:
        raise SystemExit("ANGLE Metal shader compilation setting not found")
    p.write_text(s.replace(old, new, 1))
PY

"$PYTHON" - <<'PY'
from pathlib import Path

p = Path("chrome/browser/chrome_content_browser_client.cc")
s = p.read_text()
if "clark-browser: guard ScreenAI sandbox path" not in s:
    include = '#include "chrome/browser/screen_ai/screen_ai_install_state.h"\n'
    replacement = (
        '#include "services/screen_ai/buildflags/buildflags.h"\n'
        "#if BUILDFLAG(ENABLE_SCREEN_AI_SERVICE)\n"
        '#include "chrome/browser/screen_ai/screen_ai_install_state.h"\n'
        "#endif\n"
    )
    if include not in s:
        raise SystemExit("screen_ai_install_state include not found")
    s = s.replace(include, replacement, 1)
    old = """  if (sandbox_type == sandbox::mojom::Sandbox::kScreenAI) {
    // ScreenAI service needs read access to ScreenAI component binary path to
    // load it.
    base::FilePath screen_ai_binary_path =
        screen_ai::ScreenAIInstallState::GetInstance()
            ->get_component_binary_path();
    if (screen_ai_binary_path.empty()) {
      VLOG(1) << "Screen AI component not found.";
      return false;
    }
    return serializer->SetParameter(
        sandbox::policy::kParamScreenAiComponentPath,
        screen_ai_binary_path.value());
  }
"""
    new = """#if BUILDFLAG(ENABLE_SCREEN_AI_SERVICE)
  // clark-browser: guard ScreenAI sandbox path when the service is disabled.
  if (sandbox_type == sandbox::mojom::Sandbox::kScreenAI) {
    // ScreenAI service needs read access to ScreenAI component binary path to
    // load it.
    base::FilePath screen_ai_binary_path =
        screen_ai::ScreenAIInstallState::GetInstance()
            ->get_component_binary_path();
    if (screen_ai_binary_path.empty()) {
      VLOG(1) << "Screen AI component not found.";
      return false;
    }
    return serializer->SetParameter(
        sandbox::policy::kParamScreenAiComponentPath,
        screen_ai_binary_path.value());
  }
#endif
"""
    if old not in s:
        raise SystemExit("ScreenAI sandbox branch not found")
    p.write_text(s.replace(old, new, 1))
PY

mkdir -p out/Default
cat > out/Default/args.gn <<GNEOF
is_debug = false
is_official_build = true
use_thin_lto = false
thin_lto_enable_optimizations = false
is_cfi = false
symbol_level = 0
blink_symbol_level = 0
v8_symbol_level = 0
target_cpu = "$TARGET_CPU"
enable_nacl = false
enable_remoting = false
proprietary_codecs = true
ffmpeg_branding = "Chrome"
treat_warnings_as_errors = false
safe_browsing_mode = 0
chrome_pgo_phase = 0
GNEOF

"$GN_BIN" gen out/Default
"$NINJA_BIN" -C out/Default -j "$NINJA_JOBS" chrome

APP="out/Default/Chromium.app"
if [[ ! -x "$APP/Contents/MacOS/Chromium" ]]; then
  echo "[clark-mac-build] missing built app at $APP" >&2
  exit 2
fi
codesign --force --deep --sign - "$APP" || true

tar -C out/Default -czf "$OUT/clark-browser-darwin-arm64.tar.gz" Chromium.app
shasum -a 256 "$OUT/clark-browser-darwin-arm64.tar.gz"
