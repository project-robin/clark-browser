# Patches B — Screen / Window / DPR (#11-#15)

Five patches that touch screen and window dimension getters. All five
share the same patch site (`Screen` and `LocalDOMWindow` in blink) and
the same input infrastructure (`clark::seed::Screen()`,
`clark::seed::TaskbarHeight()`). Group commit recommended.

## #11 — `screen.width` / `screen.height`

**File:** `third_party/blink/renderer/core/frame/screen.cc`

**Change:** `Screen::width()` and `Screen::height()` return
`clark::seed::Screen().width` / `.height` if either of
`--fingerprint-screen-width` or `--fingerprint-screen-height` are set,
or always (deterministic seed default).

Existing implementation reads from `ChromeClient::GetScreenInfo()`.

**Test:**
```js
// Launch with --fingerprint-screen-width=1920 --fingerprint-screen-height=1080
assert.equal(screen.width, 1920);
assert.equal(screen.height, 1080);
```

## #12 — `screen.availWidth` / `screen.availHeight`

Same file. `availHeight` derives from `height - TaskbarHeight()`.
`availWidth` equals `width` (Chromium convention; taskbar is bottom-only).

**Edge:** On macOS, the taskbar is the top menu bar (which equals our
"taskbar" in this model). Setting `--fingerprint-platform=macos`
auto-picks `TaskbarHeight()=95`.

## #13 — `window.outerWidth` / `window.outerHeight`

**File:** `third_party/blink/renderer/core/frame/local_dom_window.cc`

**Change:** `LocalDOMWindow::outerWidth()` returns
`min(screen.availWidth, innerWidth + chrome_chrome_width)` where
`chrome_chrome_width=0` is typical. Practical effect: outerWidth ==
availWidth when window is maximized, which is the common case for
automated browsers.

`outerHeight` similar: `min(availHeight, innerHeight + chrome_ui_height)`.
For a maximized window, `chrome_ui_height ≈ 85` (tabs + address bar).

We use those defaults if `--fingerprint-screen-*` are set; otherwise the
real window dimensions flow through.

**Test:**
```js
// In a maximized headless window with --fingerprint-screen-width=1920
assert(window.outerWidth >= window.innerWidth);
assert(window.outerWidth <= 1920);
```

## #14 — `window.devicePixelRatio`

**File:** `third_party/blink/renderer/core/frame/local_frame_view.cc`
(or `LocalDOMWindow::devicePixelRatio()` getter, whichever owns this).

**Change:** Default DPR keyed by `--fingerprint-platform`:
- windows → 1.0 (most common; Windows scaling lives at OS level, not DPR)
- macos → 2.0 (retina default)
- linux → 1.0

Override with `--fingerprint-dpr` if needed (NOT in our switch list yet
— add to `000-shared/` if we end up needing it).

## #15 — `screen.colorDepth` / `screen.pixelDepth`

Same file as #11. Both return 24 (matches every modern desktop). No
flag needed — just hardcode 24 in the override.

## Implementation outline (single patch combining 11-15)

```cpp
// third_party/blink/renderer/core/frame/screen.cc

#include "chrome/common/clark_fingerprint_switches.h"
#include "chrome/common/clark_seed.h"

namespace blink {

int Screen::width() const {
  return clark::seed::Screen().width;
}

int Screen::height() const {
  return clark::seed::Screen().height;
}

int Screen::availWidth() const {
  return width();
}

int Screen::availHeight() const {
  uint32_t bar = clark::seed::TaskbarHeight();
  int h = height();
  return h > static_cast<int>(bar) ? h - bar : h;
}

unsigned Screen::colorDepth() const { return 24; }
unsigned Screen::pixelDepth() const { return 24; }

}  // namespace blink
```

## Risks

- Some sites check that `outerWidth >= innerWidth` AND that
  `availHeight + taskbar == height`. Our patches preserve these
  invariants but verify in tests.
- DPR mismatch with screen size is a tell — make sure DPR default
  (#14) is coherent with platform default.

## Effort

3 days for the screen.cc patch + tests, half a day for #14 (different
file). Group as 1 commit.
