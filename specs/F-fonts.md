# Patches F — Fonts (#29-#31)

Three patches addressing the **font enumeration / rendering** fingerprint
surface. This is the patch group most likely to need filesystem prep
outside the binary itself (fonts need to be installed on the host /
container for the patch to have something to load).

## The fingerprint surface

Two main signals:

1. **`document.fonts.check()`** — JS asks "do you have Arial?". A Linux
   container without `fonts-liberation` says "no" to a long list of
   Windows fonts. Real Windows machines say "yes".
2. **Hidden-canvas font enumeration** — render the same string in 100
   different `font-family` declarations and hash each output. Each missing
   font silently falls back to a default, producing a recognizable
   "small font set" hash.

ungoogled-chromium already exposes
`FingerprintingClientRectsNoise` and related features that jitter
returned bounding boxes — that addresses (2) PARTIALLY but doesn't make
missing fonts appear.

## #29 — `--fingerprint-fonts-dir` plumbing into FontCache

**File:** `third_party/blink/renderer/platform/fonts/font_cache.cc`,
and per-platform impls (`font_cache_linux.cc`, `font_cache_mac.cc`,
`font_cache_win.cc`).

**Change:** Add a search path early in the cache's resolver. If the
flag is set, FontCache scans that dir first when resolving family-name
→ font file. Existing fontconfig (Linux) / DirectWrite (Win) / CoreText
(Mac) paths follow as fallbacks.

```cpp
void FontCache::InitializeClarkFontPath() {
  auto* cl = base::CommandLine::ForCurrentProcess();
  std::string dir = cl->GetSwitchValueASCII(
      clark::switches::kFingerprintFontsDir);
  if (dir.empty()) return;
  // Linux: register the dir with FreeType / fontconfig
  // Win:   AddFontResourceEx for each .ttf file
  // Mac:   CTFontManagerRegisterFontsForURL for each .ttf
  // ...platform-specific code...
}
```

Called from `FontCache::Init()`.

## #30 — `document.fonts.check()` returns realistic per-platform set

**File:** `third_party/blink/renderer/core/css/font_face_set_document.cc`

**Change:** This patch is mostly a function of #29 — if the fonts dir
contains a Windows font set, `check()` returns the right answers
automatically.

The patch site is the place to add a safety net: if
`--fingerprint-platform=windows` is set but no fonts-dir is provided,
log a warning at startup. (Otherwise the user gets confused why
detection still fails on font checks.)

## #31 — Hidden-canvas font enumeration

**File:** `third_party/blink/renderer/platform/fonts/font_selector.cc`

**Change:** When resolving a font-family that's not present, return
NULL (existing behavior) — the canvas falls back to default. The patch
adds: if the requested family is in the "expected for this platform"
set (e.g. Arial on Windows) and FontCache doesn't have it, **synthesize
a stand-in** rather than fall back.

This is the messy patch. Stand-in generation:
- Use the closest-metric font available
- Adjust em-size to match the expected font's expected metrics

The simpler alternative is to **require the fonts dir to be populated**
and not patch this — i.e., make #29 the actual fix and treat #31 as
documentation: "if you don't ship fonts, you'll fail font fingerprint
checks. Here's how to populate them."

## What we ship to populate the dir

Recommended fonts-dir contents for Windows-spoof (Linux host):

```
/var/lib/clark-stealth/fonts/windows/
├── arial.ttf, arialbd.ttf, ariali.ttf, arialbi.ttf
├── calibri.ttf, calibrib.ttf, calibrii.ttf, calibrili.ttf
├── cambria.ttc, cambriab.ttf
├── consola.ttf, consolab.ttf, consolai.ttf
├── georgia.ttf, georgiab.ttf, georgiai.ttf
├── tahoma.ttf, tahomabd.ttf
├── times.ttf, timesbd.ttf, timesi.ttf
├── trebuc.ttf, trebucbd.ttf
├── verdana.ttf, verdanab.ttf
└── segoeui.ttf, seguibold.ttf
```

Licensing constraint: **Microsoft does not freely redistribute these.**
Options:
- Have customers install via their licensed Windows VM
- Use look-alike free alternatives (Liberation Sans for Arial, etc.) —
  CHEAPER but distinct enough that detection sites can fingerprint the
  Liberation glyphs
- Ship a `--fingerprint-platform=linux` profile and use Linux Mesa font
  set (no licensing issue, narrower target

## Effort

| Patch | Time |
|---|---|
| #29 FontCache plumbing (3 platforms) | 1 week |
| #30 verification | 1 day |
| #31 hidden-canvas synthesizer (or doc-only) | 1 week (or 1 day) |
| Fonts-dir packaging strategy | 3 days |
| **Total** | **2 weeks** with synth, **1 week** without |
