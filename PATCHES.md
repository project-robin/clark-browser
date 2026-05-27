# Patch catalog

49-ish patches grouped by category. "Status" column tracks what's in this
repo as actual code vs spec-only.

## Where to look for each patch's design

| # range | File |
|---|---|
| Shared infrastructure | `patches/000-shared/` (real C++ files) |
| #01-#10 Navigator / JS-surface | `specs/A-navigator.md` |
| #11-#15 Screen / window | `specs/B-screen.md` |
| #16-#21 WebGL | `specs/C-webgl.md` + `data/gpu_pool.json` |
| #22-#25 Canvas / clientRects | `specs/D-canvas-rects.md` + `specs/22-canvas-noise.md` |
| #26-#28 Audio | `specs/E-audio.md` |
| #29-#31 Fonts | `specs/F-fonts.md` |
| #32-#35 Time / locale | `specs/G-time-locale.md` |
| #36-#37 Storage | `specs/H-storage.md` |
| #38-#39 WebRTC | `specs/I-webrtc.md` |
| WebRTC proxy-coherent policy | `clarkbrowser/browser.py` + `specs/I-webrtc.md` |
| #40-#44 TLS / HTTP | `specs/J-tls-http.md` + `specs/40-tls-fingerprint.md` |
| #45-#48 Headless / automation | `specs/K-headless.md` |
| #49 WebGPU | `patches/0049-webgpu-adapter-info-coherent.patch` + `specs/L-webgpu.md` |
| #51 Network Information | `patches/0051-network-information-profile.patch` |
| #18 GPU pool (largest single patch) | `specs/18-webgl-gpu-pool.md` |
| #03 plugin spec | `specs/03-plugins.md` |


Legend:
- 🟢 **Trivial** — write fresh, well-documented, < 30 LOC patch
- 🟡 **Moderate** — write fresh, needs a flag plumbed end-to-end and a
  getter override, ~50-200 LOC
- 🟠 **Public port** — port from open-source project (Brave, curl-impersonate,
  utls, ungoogled-chromium upstream). License header preserved.
- 🔴 **Novel** — needs independent thinking; spec from observable behavior;
  hardest to get right

## A. Navigator / JS-surface (Trivial-Moderate, all fresh)

| # | Patch | Idea source | Category | Status |
|---|---|---|---|---|
| 01 | `navigator.webdriver` → `false` | Web Platform spec; well-known | 🟢 | `patches/0001-...` |
| 02 | `window.chrome` always-bound (even in headless) | Chromium upstream code | 🟢 | `patches/0002-...` |
| 03 | `navigator.plugins` → realistic 5-plugin list | upstream `PluginData` | 🟡 | `patches/0003-...` |
| 04 | `navigator.mimeTypes` consistent with #03 | derived from #03 | 🟡 | spec |
| 05 | `navigator.languages` from `--fingerprint-locale` | upstream existing infra | 🟢 | `patches/0005-...` |
| 06 | `navigator.platform` from `--fingerprint-platform` | well-known UA story | 🟡 | `patches/0006-...` |
| 07 | `navigator.hardwareConcurrency` from CLI | Chromium has `Emulation.set...Override` we adapt | 🟡 | `patches/0006-...` |
| 08 | `navigator.deviceMemory` from CLI | Web Platform Device Memory API | 🟡 | `patches/0008-...` |
| 09 | `navigator.userAgentData` brands/platform from CLI | Sec-CH-UA spec, upstream `embedder_support` | 🟡 | `patches/0007-...` |
| 10 | `Notification.permission` not 'denied' under automation | MDN | 🟢 | `patches/0010-...` |

## B. Screen / Window / DPR (Moderate, all fresh)

| # | Patch | Idea source | Category | Status |
|---|---|---|---|---|
| 11 | `screen.width` / `.height` from CLI | CSSOM View spec | 🟡 | `patches/0011-...` |
| 12 | `screen.availWidth` / `.availHeight` ← screen − taskbar | derived | 🟡 | same |
| 13 | `window.outerWidth` / `.outerHeight` consistent | derived | 🟡 | same |
| 14 | `window.devicePixelRatio` consistent with screen | DPR spec | 🟡 | spec |
| 15 | `screen.colorDepth` / `.pixelDepth` = 24 | spec | 🟢 | spec |

## C. WebGL (Moderate-Hard)

| # | Patch | Idea source | Category | Status |
|---|---|---|---|---|
| 16 | `UNMASKED_VENDOR_WEBGL` from `--fingerprint-gpu-vendor` | WebGL `WEBGL_debug_renderer_info` ext | 🟡 | spec |
| 17 | `UNMASKED_RENDERER_WEBGL` from CLI | same | 🟡 | spec |
| 18 | GPU pool selection (real Intel/AMD/NVIDIA pairs) | research: known UA-pair tables in published GPU databases | 🔴 | spec |
| 19 | WebGL `getParameter` consistency: vendor, version, shading-lang | spec | 🟡 | spec |
| 20 | WebGL `getSupportedExtensions` matches real Chrome | spec | 🟡 | spec |
| 21 | WebGL `readPixels` noise (per-seed deterministic) | Brave's `brave_page_graph` patches (MPL-2.0) | 🟠 | spec |

## D. Canvas (Hard — port from Brave)

| # | Patch | Idea source | Category | Status |
|---|---|---|---|---|
| 22 | `getImageData` per-pixel noise | Brave `kFingerprintingCanvasImageDataNoise` (MPL-2.0) | 🟠 | spec |
| 23 | `measureText` width perturbation | Brave `kFingerprintingCanvasMeasureTextNoise` | 🟠 | spec |
| 24 | `toDataURL` / `toBlob` noise (consistent w/ #22) | Brave | 🟠 | spec |
| 25 | `getClientRects` / `getBoundingClientRect` jitter | Brave `kFingerprintingClientRectsNoise` | 🟠 | spec |

Note: ungoogled-chromium **already incorporates** the Brave canvas/audio/rects
noise features via flags inherited at build time. Patches 22-25 may
collapse to **enabling and re-keying** existing features — see specs.

## E. Audio (Hard — port from Brave)

| # | Patch | Idea source | Category | Status |
|---|---|---|---|---|
| 26 | AudioContext output noise (deterministic per seed) | Brave audio farbling (MPL-2.0) | 🟠 | spec |
| 27 | AnalyserNode output noise | Brave | 🟠 | spec |
| 28 | AudioBuffer.getChannelData noise | Brave | 🟠 | spec |

## F. Fonts (Moderate — fresh, but needs filesystem prep)

| # | Patch | Idea source | Category | Status |
|---|---|---|---|---|
| 29 | `--fingerprint-fonts-dir` plumbing → blink::FontCache | Chromium FontCache | 🟡 | spec |
| 30 | `document.fonts.check()` returns realistic Win/Mac font set | FontFaceSet spec | 🟡 | spec |
| 31 | Hidden-canvas font enumeration matches platform | research | 🟡 | spec |

## G. Time / Locale (Trivial-Moderate)

| # | Patch | Idea source | Category | Status |
|---|---|---|---|---|
| 32 | `--fingerprint-timezone` → ICU default zone | ICU `TimeZone::setDefault` | 🟡 | `patches/0032-...` |
| 33 | `Intl.DateTimeFormat().resolvedOptions().timeZone` matches | ICU | 🟢 | derived from #32 |
| 34 | `Date.toString()` timezone matches | derived | 🟢 | derived |
| 35 | `--fingerprint-locale` → `--lang` + `Intl.*` | upstream `--lang` | 🟢 | derived from #05 |

## H. Storage / Quota (Trivial)

| # | Patch | Idea source | Category | Status |
|---|---|---|---|---|
| 36 | `navigator.storage.estimate()` from `--fingerprint-storage-quota` | Storage spec | 🟢 | spec |
| 37 | Non-incognito storage flag (don't trip BrowserScan `notPrivate`) | published BrowserScan check | 🟡 | spec |

## I. WebRTC (Hard — needs webrtc/ work)

| # | Patch | Idea source | Category | Status |
|---|---|---|---|---|
| policy | opt-in proxy-coherent WebRTC route policy | RFC 8828 + Chromium IP handling policy | 🟢 | launcher + smoke |
| 38 | `--fingerprint-webrtc-ip` replaces ICE host candidate | webrtc `BasicNetworkManager` upstream | 🟠 | spec |
| 39 | mDNS host-candidate enabled (consistent with real Chrome) | RFC 8835 | 🟢 | spec |

## J. TLS / HTTP (Hard — port from curl-impersonate/utls)

| # | Patch | Idea source | Category | Status |
|---|---|---|---|---|
| 40 | TLS ClientHello extension order = real Chrome | curl-impersonate `chrome/` (MIT) | 🟠 | spec |
| 41 | TLS cipher list = real Chrome | curl-impersonate | 🟠 | spec |
| 42 | TLS GREASE values present | curl-impersonate | 🟠 | spec |
| 43 | HTTP/2 SETTINGS frame order = real Chrome | curl-impersonate `http2/` | 🟠 | spec |
| 44 | HTTP/2 WINDOW_UPDATE / PRIORITY = real Chrome | curl-impersonate | 🟠 | spec |

## K. Headless removal (Trivial)

| # | Patch | Idea source | Category | Status |
|---|---|---|---|---|
| 45 | UA in headless mode = full Chrome (no "HeadlessChrome") | upstream UA infra | 🟢 | `patches/0045-...` |
| 46 | `--enable-automation` removed from default args | Playwright config | 🟢 | already done via wrapper |
| 47 | `cdc_` globals not injected | DevTools binding | 🟢 | spec |
| 48 | `window.navigator.permissions.query({name:'notifications'})` consistency | Permissions spec | 🟡 | spec |

## L. WebGPU / Modern (Trivial)

| # | Patch | Idea source | Category | Status |
|---|---|---|---|---|
| 49 | `GPUAdapterInfo` consistent with WebGL GPU pool when WebGPU is enabled | WebGPU spec | 🟡 | `patches/0049-...` |

## M. Network Information (Trivial-Moderate)

| # | Patch | Idea source | Category | Status |
|---|---|---|---|---|
| 51 | `navigator.connection.{rtt,downlink,effectiveType}` from a seed/profile | Network Information spec + Chromium upstream | 🟡 | `patches/0051-...` |

## Build-order / dependency notes

- Patches 32-35 (time/locale) depend on #32 landing the CLI plumbing first.
- Patches 11-15 (screen/window) share a single CLI struct; group commit.
- Patches 22-25 (canvas) may all be served by enabling and re-keying
  ungoogled-chromium's existing Brave-derived features — spec out the
  re-keying first before writing new canvas patches.
- Patches 40-44 (TLS/HTTP) are the highest-risk; consider deferring until
  the rest land and measure detection delta.

## Estimated effort

| Category | Patches | Senior-Chromium-engineer time |
|---|---|---|
| A Navigator | 10 | 2 weeks |
| B Screen | 5 | 1 week |
| C WebGL | 6 | 3 weeks (incl. GPU pool research) |
| D Canvas (re-key existing) | 4 | 1 week |
| E Audio (port Brave) | 3 | 1 week |
| F Fonts | 3 | 2 weeks |
| G Time/Locale | 4 | 1 week |
| H Storage | 2 | 3 days |
| I WebRTC | 2 | 1 week |
| J TLS/HTTP | 5 | 4 weeks (highest risk, may need libcurl-style approach) |
| K Headless | 4 | 1 week |
| L WebGPU | 1 | 3 days |
| | **49** | **~17 weeks** (~4 months) |

Per-Chromium-release rebase (every 4-6 weeks): ~3-5 days.
