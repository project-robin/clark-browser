# Patches C — WebGL (#16-#21)

Six patches. The big one is #18 (GPU pool selection) — see
`specs/18-webgl-gpu-pool.md` for the full design. This file covers the
sibling patches that consume the same `gpu_pool.json` table.

## Shared input: the GPU pool entry

A single helper resolves at startup (once per process):

```cpp
// chrome/common/clark_gpu_pool.h  (NEW — add to 000-shared)
struct GpuPoolEntry {
  std::string vendor;
  std::string renderer;
  std::string gl_version;
  std::string shading_language_version;
  std::vector<std::string> extensions;
  std::string ua_platform_version;
};

namespace clark::gpu_pool {
const GpuPoolEntry& Selected();  // cached; reads `data/gpu_pool.json`
}
```

Resolution:
1. Filter `entries` by `platforms.includes(--fingerprint-platform)`.
2. Pick `entries[ Hash("webgl-pool") % entries.length ]`.
3. Override individual fields if `--fingerprint-gpu-vendor` /
   `--fingerprint-gpu-renderer` is set.

The JSON is compiled-in via a `grit` resource or loaded from disk at
renderer startup. Recommend compile-in: one less surface, no IPC needed
to share between processes.

## #16 — UNMASKED_VENDOR_WEBGL

**File:** `third_party/blink/renderer/modules/webgl/webgl_rendering_context_base.cc`

**Function:** `WebGLRenderingContextBase::getParameter(GLenum pname)`
case `GL_UNMASKED_VENDOR_WEBGL` (defined by the
`WEBGL_debug_renderer_info` extension).

**Change:**
```cpp
case GL_UNMASKED_VENDOR_WEBGL:
  return WebGLAny(script_state,
                  String::FromUTF8(clark::gpu_pool::Selected().vendor));
```

## #17 — UNMASKED_RENDERER_WEBGL

Same file. `case GL_UNMASKED_RENDERER_WEBGL`. Returns
`clark::gpu_pool::Selected().renderer`.

## #18 — GPU pool table + selection

See `specs/18-webgl-gpu-pool.md`. The full design with effort estimate.

Data file: `data/gpu_pool.json` (already written, needs to be filled in
with real-capture data).

## #19 — WebGL `getParameter` consistency

Same file. These three return values must match the chosen pool entry:

```cpp
case GL_VERSION:
  return WebGLAny(script_state,
      String::FromUTF8(clark::gpu_pool::Selected().gl_version));
case GL_SHADING_LANGUAGE_VERSION:
  return WebGLAny(script_state,
      String::FromUTF8(clark::gpu_pool::Selected().shading_language_version));
case GL_VENDOR:
  // The non-UNMASKED vendor — usually "WebKit" upstream. Leave alone.
  break;
```

## #20 — `getSupportedExtensions` allow-list

Same file. `WebGLRenderingContextBase::getSupportedExtensions()`.

**Change:**
```cpp
Vector<String> WebGLRenderingContextBase::getSupportedExtensions() {
  Vector<String> raw = /* existing query of driver extensions */;
  const auto& allow = clark::gpu_pool::Selected().extensions;
  if (allow.empty()) return raw;
  Vector<String> filtered;
  for (const auto& ext : raw) {
    for (const auto& a : allow) {
      if (ext.Utf8() == a) { filtered.push_back(ext); break; }
    }
  }
  return filtered;
}
```

If `gpu_pool.json` entry has empty `extensions` (TODO entries), no
filtering — driver default flows through. Sites that hash the extension
list will see whatever the real driver reports, which is acceptable
during table buildout.

## #21 — WebGL `readPixels` noise

Same file. `WebGLRenderingContextBase::readPixels(...)` reads pixels from
the GL framebuffer into a typed array.

**Change:** After existing `gl_->ReadPixels(...)` call, if noise enabled,
apply per-pixel deterministic perturbation:

```cpp
if (clark::seed::NoiseEnabled() &&
    type == GL_UNSIGNED_BYTE) {  // skip noise for float/half-float
  uint8_t* p = static_cast<uint8_t*>(pixels);
  size_t n = width * height * 4;  // RGBA8
  for (size_t i = 0; i < n; ++i) {
    // Per-byte noise: at most ±1, deterministic by (seed, i)
    uint64_t h = clark::seed::Hash(
        base::StringPrintf("rp:%zu", i));
    int8_t delta = static_cast<int8_t>(h & 0x1);  // 0 or 1
    if ((h >> 1) & 1) p[i] = std::min<int>(255, p[i] + delta);
    else              p[i] = std::max<int>(0,   p[i] - delta);
  }
}
```

Idea source: Brave's WebGL farbling at
`brave/components/brave_shields/`. Port preserving MPL-2.0 header in
file. Determinism keyed on our seed (`Hash("rp:0")`, `Hash("rp:1")`, ...)
rather than Brave's per-session token.

## Tests

```js
const c = document.createElement('canvas');
const gl = c.getContext('webgl');
const e = gl.getExtension('WEBGL_debug_renderer_info');

// #16 #17
const v = gl.getParameter(e.UNMASKED_VENDOR_WEBGL);
const r = gl.getParameter(e.UNMASKED_RENDERER_WEBGL);
console.assert(v.length > 0);
console.assert(r.length > 0);

// Vendor word in renderer  (#18 coherence)
const vendorWord = v.match(/\(([A-Z]+)\)/)?.[1] || v;
console.assert(r.toLowerCase().includes(vendorWord.toLowerCase()));

// #19
console.assert(gl.getParameter(gl.VERSION).startsWith('WebGL'));

// #20 — extension list is non-empty array of strings
const exts = gl.getSupportedExtensions();
console.assert(Array.isArray(exts) && exts.length > 0);

// #21 — same seed → same pixel readback
// (Tested at the harness level, comparing two launches with same seed.)
```

## Effort

| Patch | Time |
|---|---|
| #16, #17, #19, #20 (single-file string-switch overrides) | 3 days |
| #18 GPU pool table (research + data capture) | 2 weeks |
| #21 readPixels noise (Brave port + license preservation) | 1 week |
| **Total** | **3 weeks** |
