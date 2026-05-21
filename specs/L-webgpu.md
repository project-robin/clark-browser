# Patches L — WebGPU (#49)

One patch. Modern detection sites such as CreepJS check WebGPU adapter info as
a redundant signal alongside WebGL.

## Policy: unsupported is a deliberate profile

Headless builds often expose no usable WebGPU adapter. That is acceptable only
when it is a deliberate profile decision, not an accidental mismatch beside a
high-confidence WebGL GPU.

Launcher behavior:
- Default headless profile: add `--disable-features=WebGPU`.
- Opt in to WebGPU coherence: `webgpu_policy="coherent"` or
  `CLARK_WEBGPU_POLICY=coherent`.
- Explicit user WebGPU switches win, e.g. `--enable-features=WebGPU` or
  `--enable-unsafe-webgpu`.

This keeps CreepJS-style `webgpu: unsupported` captures explainable as part of a
headless/no-accelerated-adapter profile. If a user enables WebGPU, #49 below
keeps adapter info in the same GPU family as WebGL.

## #49 — `navigator.gpu.requestAdapter()` consistent with WebGL pool

**File:** `third_party/blink/renderer/modules/webgpu/gpu_adapter.cc`

**Surface:** `GPUAdapter.info` and `GPUDevice.adapterInfo` expose
`GPUAdapterInfo`:
- `vendor`: normalized identifier such as `intel`, `amd`, `nvidia`, `apple`, or
  `""`
- `architecture`: normalized GPU family/class such as `ampere`, `rdna3`, `xe`,
  `apple-m2`, or `""`
- `device`: vendor-specific device identifier such as `0x2503`, or `""`
- `description`: human-readable adapter description

**Change:** Read the same seed-selected GPU tuple that WebGL patches (C
category) use. The current patch keeps a matching compile-time table keyed with
the same `clark::seed::Hash("webgl-pool")`; when #18 centralizes the GPU pool,
both patches should call that shared helper. Map:
- `vendor` ← lowercased word from pool entry's vendor field
- `architecture` ← compile-time table; map renderer string to known arch
- `device` ← normalized PCI/device id extracted from renderer string when known
- `description` ← device name from the same renderer/pool tuple

If the chosen pool entry is software (mesa-llvmpipe), report vendor =
"" and architecture = "" (matches real software adapters).

**Test:**
```js
if (!navigator.gpu) {
  // Headless-off profile: absence is deliberate.
  return {supported: false};
}
const adapter = await navigator.gpu.requestAdapter();
if (!adapter) return {supported: false};
const info = adapter.info || await adapter.requestAdapterInfo();
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

Implemented in `patches/0049-webgpu-adapter-info-coherent.patch`. Remaining
work is live validation against a rebuilt binary with WebGPU explicitly enabled.
