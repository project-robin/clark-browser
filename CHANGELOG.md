# Changelog

## Unreleased

- Added `patches/0007-user-agent-client-hints-from-cli.patch` so
  `navigator.userAgentData` / UA Client Hints follow
  `--fingerprint-platform`, `--fingerprint-platform-version`,
  `--fingerprint-brand`, and `--fingerprint-brand-version` instead of leaking
  the host identity when `--user-agent` is set.
- The Python launcher now passes a Chrome UA-CH brand/version and a coherent
  platform version for the default stealth profile.
- Fixed Linux auto-download resolution to look for the packaged
  `headless_shell` binary after extracting the release tarball.
- Linux release tarballs now include the headless resource packs, runtime
  helper libraries, and a `chrome` launcher that execs `headless_shell`,
  preserving compatibility with older wrappers.
- The Linux Docker build runner now defaults to host memory and keeps
  `CLARK_LINUX_BUILD_MEMORY` as an opt-in cap for constrained local builds.

## 0.2.0 — fingerprint plumbing fixes + audio noise (May 2026)

Major audit pass after the 0.1.0 patches were verified end-to-end against
`bot.sannysoft.com` and via the `agent-browser` CLI driving the patched
binary over CDP. Most of the changes below fix patches that were *present*
in 0.1.0 but did not actually fire at runtime because the patch site was
unreachable from the JS-visible code path.

### Verified end-to-end (this release)

| Fingerprint vector                    | Source              | Per-seed |
|--------------------------------------|---------------------|----------|
| `navigator.webdriver`                 | always `false`      |          |
| `navigator.plugins.length`            | always `5`          |          |
| `typeof window.chrome`                | always `"object"`   |          |
| `navigator.platform`                  | `--fingerprint-platform` |     |
| `navigator.userAgent`                 | matched-platform UA |          |
| `navigator.hardwareConcurrency`       | `--fingerprint-hardware-concurrency` or seed |     |
| `navigator.maxTouchPoints`            | `--fingerprint-max-touch-points` |          |
| `screen.{width,height,avail*}`        | seed-derived from a coherent pool | ✓        |
| WebGL `UNMASKED_{VENDOR,RENDERER}_WEBGL` | `--fingerprint-gpu-{vendor,renderer}` | ✓ |
| Canvas `toDataURL` hash               | inaudible per-pixel jitter | ✓     |
| `getBoundingClientRect` widths        | sub-pixel jitter    | ✓        |
| `Intl.DateTimeFormat().resolvedOptions().timeZone` | `--fingerprint-timezone` | |
| `navigator.language` / `languages`    | `--fingerprint-locale` |          |
| `OfflineAudioContext` sum-of-abs hash | tiny per-sample noise | ✓        |
| `HeadlessChrome` token in UA          | stripped            |          |

`bot.sannysoft.com` reports a 100% pass with all checks (`WebDriver`,
`Plugins`, `HEADCHR_*`, `PHANTOM_*`, `SELENIUM_DRIVER`, `CHR_BATTERY`,
`CHR_MEMORY`, `TRANSPARENT_PIXEL`, and so on) when the binary is launched
with a Windows fingerprint and swiftshader-WebGL enabled.

### Patches that were silently dead in 0.1.0 (now fixed)

- **`navigator.platform`** — patch was on `NavigatorID::platform`, but the
  actual JS-visible call goes through `NavigatorBase::platform` which
  short-circuits to `GetReducedNavigatorPlatform()` (a hard-coded host
  string). Moved override to `NavigatorBase`. See
  `patches/0006-navigator-platform-hwc-ua-from-cli.patch`.
- **`navigator.hardwareConcurrency`** — patch was on
  `NavigatorConcurrentHardware`. `NavigatorBase::hardwareConcurrency`
  short-circuits to a hard-coded `2` when `kReducedSystemInfo` is enabled
  (which we enable in patch 0019). Moved override to `NavigatorBase`.
- **`--fingerprint-timezone`** — patch only called
  `icu::TimeZone::adoptDefault(...)` from `RenderThreadImpl::Init`, which
  successfully changed ICU's default but did NOT invalidate V8's
  `ICUTimezoneCache`, so `Intl.DateTimeFormat().resolvedOptions().timeZone`
  kept returning the host zone. Now plumbs through a new
  `blink::ClarkSetTimeZoneOverride` public function that wraps
  `TimeZoneController::SetTimeZoneOverride` and intentionally leaks the
  RAII handle so the override survives the renderer's lifetime.
- **`--fingerprint-*` switches not reaching renderer** — Chromium's
  `RenderProcessHostImpl::AppendRendererCommandLine` only propagates
  switches that are explicitly listed in `kSwitchNames[]`. New patch
  `0050-renderer-arg-whitelist-fingerprint.patch` adds every
  `clark::switches::kFingerprint*` to that list.

### New patches in this release

- `0006-navigator-platform-hwc-ua-from-cli.patch` (replaces dead 0006/0007)
- `0009-navigator-max-touch-points-from-cli.patch`
- `0026-audio-fingerprint-noise.patch` — seed-derived per-sample jitter on
  the `AudioBuffer::getChannelData` v8-binding entry path. Hooks ONLY the
  `ExceptionState` overload (the no-exception-state overload is also called
  internally by `SharedAudioBuffer` setup BEFORE the audio thread fills the
  buffer; hooking it there would latch "already noised" on an empty buffer
  and the renderer would overwrite our changes).
- `0032-fingerprint-timezone-cli.patch` — rewritten with the
  `ClarkSetTimeZoneOverride` bridge approach (see above).
- `0050-renderer-arg-whitelist-fingerprint.patch` — propagate all
  `--fingerprint-*` switches to renderer/worker processes.

### Build infrastructure

- `build/Dockerfile.linux` + `build/build-linux.sh` +
  `build/run-linux-build.sh` — reproducible Linux x86_64 build harness.
  Pins `ungoogled-chromium` to tag `148.0.7778.96-1` (the macOS variant's
  ref) to avoid the stale 120.x submodule pin in
  `ungoogled-chromium-debian`.

### Known gaps (deferred to 0.3.0)

- Audio noise covers only `AudioBuffer::getChannelData` and `copyFromChannel`.
  `AnalyserNode.getFloatFrequencyData()` and `MediaStreamAudioSourceNode`
  routes are not yet perturbed.
- Font enumeration (patch series #29-#31) still uses host fonts. Bundling
  a target-platform font set and gating through `--fingerprint-fonts-dir`
  is specified but not implemented.
- TLS / ClientHello fingerprint (#40-#44) not patched. Requires BoringSSL
  customization (or an external utls-style proxy) to alter JA3/JA4.
- WebGPU adapter info (#49) follows the same pattern as WebGL — not yet
  wired.

## 0.1.0 — initial release (May 2026)

First public release.

### Patched Chromium

- Base: **ungoogled-chromium 148.0.7778.96**
- 18 source-level patches integrated; 31 more specified for follow-up
  (see PATCHES.md)
- Build verified end-to-end on macOS arm64

### Python wrapper

- `launch()`, `launch_async()`, `launch_context()`,
  `launch_persistent_context()` mirroring Playwright's API
- Auto-download from GitHub Releases (override with `CLARK_BINARY_PATH`)
- `--use-mock-keychain` baked into default args for unsigned macOS dev builds
