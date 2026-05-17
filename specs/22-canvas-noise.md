# Spec — patches #22-25: canvas / clientRects noise

These four (getImageData, measureText, toDataURL, getClientRects) are
**fully addressed by ungoogled-chromium's inherited Brave noise
features**, but with two tweaks:

1. Brave's noise key in upstream is a per-session Brave Shield session
   token. We need to re-key to our `--fingerprint=<seed>` so a fixed seed
   produces a stable fingerprint across launches.
2. Brave's features are off by default in ungoogled-chromium builds;
   we flip the default to on.

## Public idea source

- Brave-Browser source (MPL-2.0), specifically the patches under
  `brave/browser/farbling/` and `brave/renderer/farbling/` in their
  monorepo. Files of interest:
  - `brave/components/brave_shields/common/features.cc` — feature flags
    `kFingerprintingCanvasImageDataNoise`,
    `kFingerprintingCanvasMeasureTextNoise`,
    `kFingerprintingClientRectsNoise`
  - `brave/renderer/brave_content_renderer_client.cc` — wires noise into
    blink renderer
  - `third_party/blink/brave_page_graph/` — actual noise injection in
    `CanvasRenderingContext2D::getImageData()` etc.
- Whole noise design ported from the Princeton "OpenWPM" line of papers
  (Englehardt & Narayanan, 2016), Brave's "Farbling" tech note (2020).

## Behavioral spec

- `getImageData(x,y,w,h)` returns pixel data with sub-LSB per-pixel
  noise: each channel value perturbed by `f(seed, x, y, channel)` mod
  2, deterministic for same `(seed, coords)` tuple.
- `measureText(text).width` returns real value + `g(seed, text)` where
  g is in `[-0.5, +0.5]` pixels.
- `toDataURL()` / `toBlob()` reflect the noised pixels.
- `getBoundingClientRect()` / `getClientRects()` return real values +
  `h(seed, element-stable-id)` where h is in `[-0.5, +0.5]` pixels per
  coordinate.

For all four, **the same seed produces identical output across
launches.** Different seeds produce different output. Empty seed (no
flag) uses upstream Brave session-token semantics (random per launch).

## Implementation outline

1. **Re-key:** in
   `third_party/blink/brave_page_graph/blink_probe_set.h` (or wherever
   ungoogled-chromium's inherited Brave code keys its noise), replace
   the per-session token with:
   ```cpp
   uint64_t clark_noise_seed = ParseSeed(
       base::CommandLine::ForCurrentProcess()
           ->GetSwitchValueASCII("fingerprint"));
   ```
   where `ParseSeed` returns a deterministic 64-bit hash of the seed
   string. Cache on `LocalFrame` or `Document`.

2. **Flip defaults:** in `brave/components/brave_shields/common/features.cc`,
   change `base::FEATURE_DISABLED_BY_DEFAULT` to `_ENABLED_BY_DEFAULT`
   for the three feature flags. Or, if we don't want to touch
   ungoogled-chromium's vendored Brave dir, set the flags via
   `chrome/browser/about_flags.cc` programmatic-default override.

3. **Honor `--fingerprint-noise=false`:** check the CLI flag at noise
   sites; if false, return real value bypassing noise. This matches the
   feature in CloakBrowser's README. (CLI registration in
   clark_fingerprint_switches.{h,cc}.)

## License preservation

Brave's source is MPL-2.0. If we keep their files (just modify them) the
MPL header stays. If we extract noise math into our own file, we cite
Brave as origin and include the MPL header. Either way, no relicensing.

## Tests

```js
// Determinism with seed
ctx1.fillRect(0,0,100,100);
const a = ctx1.getImageData(0,0,100,100).data;
// (relaunch with same seed)
const b = ctx2.getImageData(0,0,100,100).data;
assert(arraysEqual(a, b));

// Noise present (not pixel-identical to a non-stealth Chrome render)
assert(!arraysEqual(a, stockChromeBaseline));

// measureText jitter < 1 px
const w = ctx.measureText("hello world").width;
assert(Math.abs(w - 56) < 1);  // 56 is stock width
```
