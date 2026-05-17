# Patches D — Canvas / ClientRects (#22-#25)

See `specs/22-canvas-noise.md` for the full Brave re-keying strategy.
This file covers the per-vector implementation deltas.

## Discovery first

Before writing any patches, run on a vanilla ungoogled-chromium build:

```bash
out/Default/chrome --headless=new --enable-features=\
FingerprintingCanvasImageDataNoise,FingerprintingCanvasMeasureTextNoise,\
FingerprintingClientRectsNoise \
  --remote-debugging-port=9222
```

Then evaluate the four vectors below and observe whether noise is
already present. If yes, our work is just **re-keying** to our seed.
If no (feature flags didn't activate the noise paths in ungoogled),
we port from upstream Brave.

## #22 — `getImageData` per-pixel noise

**File:** `third_party/blink/renderer/modules/canvas/canvas2d/canvas_rendering_context_2d.cc`
(ungoogled inherits Brave's modifications here)

**Change:** Locate the existing Brave-farbling hook (look for
`fingerprinting_canvas_image_data_noise` in includes). Re-key the noise
function from Brave's per-session token to our seed:

```cpp
// Before
uint64_t noise_key = brave::BraveSessionToken();

// After
uint64_t noise_key = clark::seed::Hash("canvas-image-data");
```

Behavior unchanged otherwise: per-pixel deterministic ±1 perturbation
across RGBA channels.

## #23 — `measureText` width jitter

**File:** same (or
`third_party/blink/renderer/core/html/canvas/text_metrics.cc`)

**Change:** Existing measureText jitter (from Brave) is re-keyed.
Magnitude stays bounded at ±0.5 px.

```cpp
double jitter = static_cast<int64_t>(
    clark::seed::Hash(base::StringPrintf("mt:%s", text.Utf8().c_str()))
    % 1001) / 1000.0 - 0.5;  // [-0.5, +0.5]
width += jitter;
```

## #24 — `toDataURL` / `toBlob` reflect noised pixels

Automatic from #22 — both APIs serialize the canvas's pixel buffer,
which is already noised. No separate patch needed unless tests show
they bypass.

## #25 — `getClientRects` / `getBoundingClientRect` jitter

**File:** `third_party/blink/renderer/core/dom/element.cc` (methods
`getClientRects` and `getBoundingClientRect`)

**Change:** Same pattern — re-key Brave's existing jitter to our seed.

```cpp
double Element::JitteredCoord(double real, const char* axis) const {
  if (!clark::seed::NoiseEnabled()) return real;
  // Stable per-(element, axis) — use element's stable id, e.g., DOM
  // path hash. Avoids changing values across consecutive reads of
  // the same element.
  std::string key = base::StringPrintf(
      "cr:%s:%s", axis, ElementStableId().c_str());
  double jitter = static_cast<int64_t>(
      clark::seed::Hash(key) % 1001) / 1000.0 - 0.5;
  return real + jitter;
}
```

Then in the getters, wrap real coords:

```cpp
rect.set_x(JitteredCoord(real_x, "x"));
rect.set_y(JitteredCoord(real_y, "y"));
// etc.
```

## Honoring `--fingerprint-noise=false`

`clark::seed::NoiseEnabled()` returns false when the flag is set to
`false`/`0`. In that case all four vectors skip jitter and return real
values. The deterministic seed itself stays in effect for other vectors
(plugin enum, screen, etc.).

## Test (same-seed determinism)

```js
// Run twice with identical --fingerprint=<seed>; canvases must hash equal
function hash() {
  const c = document.createElement('canvas');
  c.width = 200; c.height = 50;
  const ctx = c.getContext('2d');
  ctx.font = '18px Arial';
  ctx.fillText('clark-stealth test 🦊', 10, 30);
  return c.toDataURL();
}
console.log(hash());  // compare run-to-run
```

## License

Brave farbling code is MPL-2.0. ungoogled-chromium inherits it
file-by-file. Our changes:
- Stay in those same files → MPL-2.0 header preserved → no relicense
- Cite Brave + ungoogled-chromium upstream commits in patch header
- Cite MPL-2.0 in the patch file's own metadata

If we extract the noise logic into a new file under our control, that
file must carry the MPL-2.0 header per MPL §3.

## Effort

1 week including ungoogled-chromium-state discovery, re-keying, and tests.
