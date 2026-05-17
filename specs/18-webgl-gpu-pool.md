# Spec — patch #18: WebGL GPU pool (real Intel/AMD/NVIDIA pairs)

This is the highest-effort patch in category C. It's not about a single
flag — it's about having a **table** of believable
`(UNMASKED_VENDOR_WEBGL, UNMASKED_RENDERER_WEBGL, GL_VERSION,
SHADING_LANGUAGE_VERSION, getSupportedExtensions list)` tuples that real
Chrome reports on real hardware, and selecting one deterministically
from the fingerprint seed.

## Why a table

Detection sites cross-check vendor against renderer string against
extension list. "Intel Inc." + "NVIDIA GeForce RTX 3080" is a $0 fail.
"NVIDIA Corporation" + "ANGLE (NVIDIA GeForce RTX 3080 Direct3D11
vs_5_0 ps_5_0)" with the correct ANGLE extension subset is the kind of
thing real Chrome on real hardware actually reports.

## Public idea sources

- WebGL `WEBGL_debug_renderer_info` extension spec
- ANGLE project source (BSD-3) — defines how Chromium wraps GPU drivers
  on Windows (D3D11 backend) and Linux (GL backend).
- Public WebGL fingerprint databases:
  - `https://browserleaks.com/webgl` aggregates reported strings
  - `https://webglreport.com/` publishes raw output per device
  - Academic: "Picasso: Lightweight Device Class Fingerprinting for Web
    Clients" (Sanchez-Rola et al., 2018)
- Chromium's own `gpu/config/gpu_info_collector.{h,cc}` shows what fields
  ANGLE populates.

## Table sketch

A YAML / JSON table shipped under `chrome/browser/clark_fingerprint/
gpu_pool.json` (compiled into the binary or read at startup). Sample
rows (illustrative — needs to be filled out from real-device captures):

```yaml
- key: intel-iris-xe-win
  vendor: "Google Inc. (Intel)"
  renderer: "ANGLE (Intel, Intel(R) Iris(R) Xe Graphics (0x00009A49) Direct3D11 vs_5_0 ps_5_0, D3D11)"
  version: "WebGL 1.0 (OpenGL ES 2.0 Chromium)"
  shading_language: "WebGL GLSL ES 1.0 (OpenGL ES GLSL ES 1.0 Chromium)"
  extensions: [<curated ANGLE/D3D11 ext list>]
  platforms: [windows]

- key: nvidia-rtx-4070-win
  vendor: "Google Inc. (NVIDIA)"
  renderer: "ANGLE (NVIDIA, NVIDIA GeForce RTX 4070 (0x00002786) Direct3D11 vs_5_0 ps_5_0, D3D11)"
  version: "WebGL 1.0 (OpenGL ES 2.0 Chromium)"
  shading_language: "WebGL GLSL ES 1.0 (OpenGL ES GLSL ES 1.0 Chromium)"
  extensions: [...]
  platforms: [windows]

- key: amd-radeon-rx-7600-win
  vendor: "Google Inc. (AMD)"
  renderer: "ANGLE (AMD, AMD Radeon RX 7600 Direct3D11 vs_5_0 ps_5_0, D3D11)"
  ...

- key: apple-m2
  vendor: "Apple Inc."
  renderer: "Apple GPU"
  version: "WebGL 1.0"
  shading_language: "WebGL GLSL ES 1.0"
  extensions: [<curated Metal-backed ext list>]
  platforms: [macos]
```

Table populated from real-device WebGL reports. **Each row must come from
a real machine you or a contributor own**; do NOT scrape browserleaks
without permission.

## Selection algorithm

```
seed = base::CommandLine::GetSwitchValueASCII("fingerprint")
platform = base::CommandLine::GetSwitchValueASCII("fingerprint-platform")
candidates = gpu_pool.filter(row => row.platforms.includes(platform))
chosen = candidates[hash(seed) % candidates.length]
```

Same seed → same row. Different seed → may be different row.

## Implementation outline

Hook into `gpu::GPUInfo` reporting before it reaches the renderer's
WebGL `GetExtensions` / `GetParameter` calls. Two patch points:

1. `gpu/config/gpu_info_collector.cc` — where ANGLE-reported vendor /
   renderer is captured. Replace with row.vendor / row.renderer.
2. `third_party/blink/renderer/modules/webgl/webgl_rendering_context_base.cc`
   — `getParameter(UNMASKED_*_WEBGL)` reads from GPUInfo which we
   already substituted in #1.

Extensions list overlay: in `WebGLRenderingContextBase::getSupportedExtensions`,
filter the actual driver-supported extensions against `row.extensions`
allow-list before returning.

## What this does NOT cover (separate patches)

- WebGL readPixels noise (#21)
- WebGL canvas → image fingerprint (#21 + #22)
- WebGPU adapter info — different code path, addressed by #49

## Risks

- The substituted vendor/renderer must be plausible **and** consistent
  with the rest of the fingerprint. If we say `--fingerprint-platform=macos`
  and the WebGL renderer is "NVIDIA GeForce", we've defeated the point.
  Table organization by platform tag is required.
- Extension list must match what real cards report — too many or too
  few is a tell. This is the patient research part. Budget 2-3 weeks
  to get a defensible 10-row table.

## Tests

```js
const gl = document.createElement('canvas').getContext('webgl');
const ext = gl.getExtension('WEBGL_debug_renderer_info');
const v = gl.getParameter(ext.UNMASKED_VENDOR_WEBGL);
const r = gl.getParameter(ext.UNMASKED_RENDERER_WEBGL);
// 1) values come from gpu_pool.json
// 2) v + r form a coherent pair (same vendor word in both)
// 3) same seed → same pair (run twice, compare)
// 4) extensions list is a subset of real-card report for that pair
```
