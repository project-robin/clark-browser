# Building clark-browser from source

Most users should `pip install clarkbrowser` and let the binary auto-download.
This directory is for contributors and people who want to verify the build is
reproducible.

## System requirements

| Resource | Minimum | Recommended |
|---|---|---|
| RAM | 32 GB | 64 GB |
| Cores | 8 | 32+ |
| Disk | 200 GB free | 500 GB SSD |
| First build | ~24 h on 8-core | ~6 h on 32-core |
| Incremental | 5–30 min | depends on what changed |

## Prerequisites

### macOS

```bash
brew install python@3.12 ninja coreutils readline node
brew unlink binutils 2>/dev/null || true
xcodebuild -downloadComponent MetalToolchain
pip3 install --break-system-packages --user PySocks httplib2
```

### Linux (Debian/Ubuntu)

```bash
sudo apt install -y python3 python3-pip python3-pysocks python3-httplib2 \
  ninja-build clang lld git build-essential
```

## Build

```bash
export CLARK_WORK_DIR=$HOME/clark-stealth-build   # 80+ GB lives here

./fetch-source.sh       # ~30–60 min, ~17 GB
./apply-patches.sh      # instant
./build.sh              # the long one
```

The build script just calls upstream ungoogled-chromium's `build.sh -d <arch>`,
which runs: `gn gen` → `bootstrap gn` → `ninja chrome chromedriver` →
`sign_and_package_app.sh` (macOS only).

## Local testing

```bash
# Make our wrapper use the freshly built binary
export CLARK_BINARY_PATH="$CLARK_WORK_DIR/ungoogled-chromium-macos/build/src/out/Default/Chromium.app/Contents/MacOS/Chromium"

# Or on Linux:
export CLARK_BINARY_PATH="$CLARK_WORK_DIR/ungoogled-chromium-debian/build/src/out/Default/chrome"

# Run smoke test
python ../examples/stealth_check.py
```

## Common build issues

These come up on first-time Chromium builds; they aren't patch bugs:

- **`StrEnum` import error** in depot_tools: depot_tools needs Python ≥ 3.11.
  Install via Homebrew and put `/opt/homebrew/bin` first in PATH.
- **Missing `tools/gn/build/gen.py`**: copy `uc_staging/gn/*` into `tools/gn/`.
- **Missing `last_commit_position.h`**: write a stub:
  ```c
  #define LAST_COMMIT_POSITION_NUM 2256
  #define LAST_COMMIT_POSITION "2256"
  ```
- **Missing `build/util/LASTCHANGE.committime`**: stub with `$(date +%s)`.
- **Missing `gpu/webgpu/DAWN_VERSION`**: copy the dawn revision from `DEPS`.
- **Missing `gpu/config/gpu_lists_version.h`**: stub:
  ```c
  #define GPU_LISTS_VERSION "0000000000000000000000000000000000000000"
  ```

## macOS run-time issue

Unsigned/ad-hoc-signed dev builds hang on macOS Keychain mutex during browser
startup. Workarounds:

1. Pass `--use-mock-keychain` (default in our `launch()` wrapper).
2. Ad-hoc codesign the bundle:
   ```bash
   codesign --force --deep --sign - /path/to/Chromium.app
   ```

## CI / GitHub Actions

See `.github/workflows/build.yml` (TODO — uses self-hosted runners with build
caching).
