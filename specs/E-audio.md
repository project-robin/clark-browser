# Patches E — Audio (#26-#28)

Three patches. Like the canvas noise patches in D, these are
**Brave-farbling ports re-keyed to our seed**.

## What gets noised

Detection sites compute a "fingerprint" by feeding an oscillator
through an AudioContext destination, reading the output buffer (or its
hash), and comparing to known-stock-Chrome outputs. Real users vary by
hardware DSP path — bots don't. Brave's farbling adds sub-LSB noise to
the audio buffer that breaks the hash while staying inaudible.

## #26 — `AudioContext` destination output

**File:** `third_party/blink/renderer/modules/webaudio/audio_destination.cc`
(ungoogled inherits Brave modifications here)

**Change:** Re-key from Brave session token to
`clark::seed::Hash("audio-dest")`. Noise floor stays at ~1e-7 — well
below audible threshold but breaks bit-identical hashing.

```cpp
// In the per-buffer-fill hook
if (clark::seed::NoiseEnabled()) {
  uint64_t k = clark::seed::Hash("audio-dest");
  for (size_t i = 0; i < frames; ++i) {
    // Tiny deterministic perturbation keyed on (k, i)
    uint64_t h = SipHash24(k_key, &i, sizeof(i)) ^ k;
    float delta = static_cast<float>(static_cast<int32_t>(h & 0xFFFF)
                                     - 32768) * 1e-12f;
    buffer[i] += delta;
  }
}
```

## #27 — `AnalyserNode` output

**File:** `third_party/blink/renderer/modules/webaudio/analyser_node.cc`

**Change:** `getFloatFrequencyData` and `getByteFrequencyData` add the
same per-bin noise pattern. Re-keyed identically.

Some detection sites read AnalyserNode directly (not the destination),
so this is a separate hook.

## #28 — `AudioBuffer.getChannelData`

**File:** `third_party/blink/renderer/modules/webaudio/audio_buffer.cc`

**Change:** `getChannelData()` returns a typed array. If buffer was
filled via decoding or oscillator, noise has already been applied at
#26/#27. This patch handles the case where a site fills a buffer
synthetically and reads it back — without this hook, the round-trip
is bit-identical, giving the bot away. Add a noise pass on read.

## License

Same as canvas (D): MPL-2.0 from Brave, headers preserved.

## Test

```js
const ctx = new OfflineAudioContext(1, 5000, 44100);
const osc = ctx.createOscillator();
const comp = ctx.createDynamicsCompressor();
osc.connect(comp); comp.connect(ctx.destination);
osc.start(0);
const buf = await ctx.startRendering();
const data = buf.getChannelData(0);
// Hash data; compare across same-seed runs (must match) and stock-Chrome
// baseline (must differ).
```

## Effort

1 week. Plumbing is identical to canvas patches; main work is finding
the three hook sites in current ungoogled-chromium and verifying the
noise stays inaudible (a regression test that plays back through a
headphone codec and measures audible artifacts).
