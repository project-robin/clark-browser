# Patches H — Storage / Quota (#36-#37)

Two patches. Small surface, real impact on FingerprintJS vs BrowserScan
trade-off.

## The trade-off

| Setting | FingerprintJS | BrowserScan `notPrivate` |
|---|---|---|
| Real incognito-like quota (~500 MB) | passes | fails (-10 points) |
| Large quota (~5 GB) | may flag as suspicious | passes |
| Per-launch random in [500MB, 5GB] | depends on threshold | depends |

Default of CloakBrowser (per their README): low quota, pass FingerprintJS,
fail BrowserScan. We follow the same default.

## #36 — `navigator.storage.estimate().quota` from CLI

**File:** `third_party/blink/renderer/modules/quota/storage_manager.cc`,
method `StorageManager::estimate()`.

**Change:** If `--fingerprint-storage-quota=<MB>` is set, override the
returned `quota` (and a sensible `usage` like quota * 0.1):

```cpp
StorageEstimate* StorageManager::Estimate(ScriptState* state) {
  auto* est = MakeGarbageCollected<StorageEstimate>();
  auto* cl = base::CommandLine::ForCurrentProcess();
  if (cl->HasSwitch(clark::switches::kFingerprintStorageQuota)) {
    uint64_t mb = 0;
    if (base::StringToUint64(
            cl->GetSwitchValueASCII(
                clark::switches::kFingerprintStorageQuota), &mb)) {
      est->setQuota(mb * 1024ULL * 1024ULL);
      est->setUsage(mb * 1024ULL * 102ULL);  // ~10%
      return est;
    }
  }
  // ...existing path: query QuotaManager...
  return est;
}
```

Default: not set → existing behavior (real quota from QuotaManager,
typically ~500 MB in headless).

## #37 — Non-incognito flag for persistent profiles

**File:** `third_party/blink/renderer/modules/quota/storage_manager.cc`
(or `chrome/browser/profiles/profile_impl.cc`)

**Behavior:** BrowserScan's `notPrivate` check reads a combination of:
- `navigator.storage.estimate().quota` > some threshold (we cover via #36)
- The presence of certain extension-API surfaces only present in
  non-incognito modes

**Patch:** When using `--user-data-dir=<persistent>` (not the default
temp dir), surface a non-incognito-feeling environment:
- `chrome.runtime` (if extension APIs exposed) reports
  `incognito === false`
- `storageBuckets` (legacy webkit API) reports non-incognito limit
  if present

Practical implementation is: ensure the BrowserContext used by a
persistent --user-data-dir launch is `OFF_THE_RECORD=false`. Stock
Chromium does this; we just verify and add a regression test.

## Tests

```js
const e = await navigator.storage.estimate();
console.assert(e.quota > 100_000_000);  // >100 MB

// With --fingerprint-storage-quota=5000
console.assert(e.quota === 5_000 * 1024 * 1024);
```

## Effort

2 days for #36 + tests. #37 is verification + possibly a single-line
patch to fix a missing not-incognito flag.
