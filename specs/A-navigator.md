# Patches A — Navigator / JS-surface (#01-#10)

Ten patches that touch various `navigator.*` and `window.chrome` getters
in blink. Each is small in isolation; they share the
`clark_fingerprint_switches.h` / `clark_seed.h` infrastructure from
`000-shared/`.

## #01 — `navigator.webdriver` → false

**File:** `patches/0001-navigator-webdriver-false.patch` (already a real diff).

Already specced. No additional notes.

## #02 — `window.chrome` always-bound

**File:** `third_party/blink/renderer/bindings/core/v8/v8_initializer.cc`
(historically), or look in `chrome/renderer/loadtimes_extension_bindings.cc`
for the modern path. The exact registration point is the install of the
`ChromeRuntime` private template into the main world.

**Change (sketch):**
```cpp
// Existing condition gates the install behind isolate-readiness AND
// a feature flag. Drop the feature-flag gate so it installs in headless
// mode too. The legacy chrome.loadTimes() and chrome.csi() stubs are
// already defined in this file; just always-install them.
```

**Test:**
```js
console.assert(typeof window.chrome === 'object');
console.assert(typeof window.chrome.loadTimes === 'function');
console.assert(typeof window.chrome.csi === 'function');
console.assert(typeof window.chrome.loadTimes() === 'object');
```

## #03 — `navigator.plugins` → 5-tuple

See `specs/03-plugins.md` for the full plugin tuple. Implementation in
`third_party/blink/renderer/core/page/plugin_data.cc`.

## #04 — `navigator.mimeTypes` consistent with #03

Falls out automatically from #03 — the `MimeTypeArray` is computed from
PluginData. No separate patch needed unless tests reveal an
inconsistency.

## #05 — `navigator.languages` from `--fingerprint-locale`

**File:** `third_party/blink/renderer/core/frame/navigator_language.cc`
(class `NavigatorLanguage`).

**Change:** Override `Languages()` to:
1. If `--fingerprint-locale` is set, return `[locale, locale-base]`
   (e.g. for `en-US`, return `["en-US", "en"]`).
2. Otherwise, fall through to existing behavior (which already reads
   `--lang`).

Chromium already reads `--lang` for this — the patch just adds our
extra switch as an alternate input.

**Test:**
```js
// Launch with --fingerprint-locale=de-DE
assert.deepEqual(navigator.languages, ["de-DE", "de"]);
assert.equal(navigator.language, "de-DE");
```

## #06 — `navigator.platform` from `--fingerprint-platform`

**File:** `third_party/blink/renderer/core/frame/navigator_id.cc`

**Change:** `NavigatorID::platform()` returns a platform-appropriate
string keyed on `--fingerprint-platform`:
- windows → "Win32"
- macos → "MacIntel"
- linux → "Linux x86_64"

Default (no flag): existing host-derived value.

**Test:**
```js
// Launch with --fingerprint-platform=windows on Linux host
assert.equal(navigator.platform, "Win32");
```

## #07 — `navigator.hardwareConcurrency`

Already specced in `patches/0007-hardware-concurrency-from-cli.patch`.

Uses `clark::seed::HardwareConcurrency()` from `000-shared/`. Patch site:
`third_party/blink/renderer/core/frame/navigator_concurrent_hardware.cc`,
class `NavigatorConcurrentHardware`, method `hardwareConcurrency()`.

## #08 — `navigator.deviceMemory`

**File:** `third_party/blink/renderer/core/frame/navigator_device_memory.cc`

**Change:** Method `deviceMemory()` returns `clark::seed::DeviceMemoryGB()`
instead of the existing `ApproximatedDeviceMemory()`.

Existing implementation buckets the real RAM to one of {0.25, 0.5, 1, 2,
4, 8}; our seed-derived helper picks from {4.0, 8.0} (sensible defaults).

**Test:**
```js
// Launch with --fingerprint-device-memory=4
assert.equal(navigator.deviceMemory, 4);
```

## #09 — `navigator.userAgentData` brands & platform

**File:** `components/embedder_support/user_agent_utils.cc`, function
`GetUserAgentMetadata()`.

**Change:** This already builds a `blink::UserAgentMetadata` struct.
Plumb our switches into it:
- `metadata.brand_version_list` from `--fingerprint-brand` /
  `--fingerprint-brand-version`. Default: derive from chrome version.
- `metadata.platform` from `--fingerprint-platform` ("Windows" / "macOS"
  / "Linux").
- `metadata.platform_version` from `--fingerprint-platform-version`.

**Test:**
```js
const ua = await navigator.userAgentData.getHighEntropyValues(
  ['brands', 'platform', 'platformVersion']);
assert.equal(ua.platform, "Windows");
assert(ua.brands.some(b => b.brand === "Chrome"));
```

## #10 — `Notification.permission` consistent under automation

**File:** `third_party/blink/renderer/modules/notifications/notification.cc`

**Stock behavior:** When `--enable-automation` is set, headless mode
reports `Notification.permission === "denied"`. Real Chrome would say
"default" until the user grants/denies.

**Change:** Since we remove `--enable-automation` from the default args
(wrapper-level, already done), and headless-mode-permission is the only
remaining source of this signal, override the headless-permission path
to return `"default"` instead of `"denied"`.

**Test:**
```js
assert.equal(Notification.permission, "default");
const p = await navigator.permissions.query({name: 'notifications'});
assert.equal(p.state, "prompt");
```

## Build order

- 000-shared must land first.
- After 000-shared: #01, #02, #03, #06, #07, #08, #10 can land
  independently in any order.
- #04 is automatic from #03.
- #05 depends on `--lang` being honored — verify upstream behavior;
  patch is a delta on top.
- #09 touches a shared file (`user_agent_utils.cc`) — coordinate with
  patch #45 (headless UA) to avoid conflict.

## Combined effort estimate

| Phase | Time |
|---|---|
| Patch the 7 standalone navigator files | 1 week |
| #09 (UA Client Hints — shared file complexity) | 3 days |
| #03 (plugin enumeration — tricky surface) | 4 days |
| Tests for all 10 | 3 days |
| **Total** | **2 weeks** for one Chromium-fluent engineer |
