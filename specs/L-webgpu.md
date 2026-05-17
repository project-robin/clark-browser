# Patches L — WebGPU (#49)

One patch. Modern detection sites (CreepJS, late-2026 FingerprintJS
release) check WebGPU adapter info as a redundant signal alongside
WebGL.

## #49 — `navigator.gpu.requestAdapter()` consistent with WebGL pool

**File:** `third_party/dawn/src/dawn/native/Adapter.cpp`
(or `Adapter::APIRequestDevice` / the place where adapter info is
materialized into JS-visible properties).

**Surface:** `GPUAdapter.requestAdapterInfo()` returns:
- `vendor`: "intel", "amd", "nvidia", "apple", "qualcomm", ""
- `architecture`: e.g. "rdna3", "ampere", "turing"
- `device`: e.g. "RTX 4070"
- `description`: human-readable

**Change:** Read the same `clark::gpu_pool::Selected()` entry that WebGL
patches (C category) use. Map:
- `vendor` ← lowercased word from pool entry's vendor field
- `architecture` ← compile-time table; map renderer string to known arch
- `device` ← extracted from renderer string
- `description` ← renderer string verbatim

If the chosen pool entry is software (mesa-llvmpipe), report vendor =
"" and architecture = "" (matches real software adapters).

**Test:**
```js
if (!navigator.gpu) {
  // WebGPU disabled in headless? — confirm and skip
  return;
}
const adapter = await navigator.gpu.requestAdapter();
const info = await adapter.requestAdapterInfo();
console.assert(info.vendor === 'nvidia' || info.vendor === 'intel' ||
               info.vendor === 'amd' || info.vendor === 'apple' ||
               info.vendor === '');
// Coherence: vendor must match the WebGL pool entry's vendor
const gl = document.createElement('canvas').getContext('webgl');
const e = gl.getExtension('WEBGL_debug_renderer_info');
const webglVendor = gl.getParameter(e.UNMASKED_VENDOR_WEBGL).toLowerCase();
console.assert(webglVendor.includes(info.vendor) ||
               info.vendor === '' /* software */);
```

## Effort

3 days. Most of the work is the renderer-string → architecture mapping
table, which is a small JSON keyed off the same `data/gpu_pool.json`.
