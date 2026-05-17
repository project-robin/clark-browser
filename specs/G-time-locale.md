# Patches G — Time / Locale (#32-#35)

Four patches. #32 (timezone) is already specced in
`patches/0032-fingerprint-timezone-cli.patch`. #33, #34 fall out
automatically from #32. #35 (locale) plumbing is mostly upstream's
`--lang` mechanism.

## #32 — `--fingerprint-timezone` → ICU default zone

See `patches/0032-fingerprint-timezone-cli.patch`.

Hook in renderer startup, set ICU default zone before V8 isolate
creation. Verified against `Intl.DateTimeFormat`, `Date.toString`, and
`new Date().getTimezoneOffset()`.

## #33 — `Intl.DateTimeFormat().resolvedOptions().timeZone`

Automatic from #32 — Intl reads from ICU's default zone.

**Verification only:**
```js
// Launch with --fingerprint-timezone=Asia/Tokyo
const tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
assert.equal(tz, "Asia/Tokyo");
```

If not equal, V8 may have cached zone at isolate-creation time —
verify our hook fires BEFORE isolate creation, not just before page
load.

## #34 — `Date.toString()` includes spoofed timezone abbreviation

Automatic from #32 — Date.toString uses ICU's default zone for the
abbreviation (e.g., "JST" for Asia/Tokyo).

## #35 — `--fingerprint-locale` → `Intl.*` + `navigator.languages`

**Strategy:** This patch is mostly forwarding logic. Upstream Chromium
already has a `--lang` flag that drives `navigator.languages`,
`Accept-Language` headers, and `Intl.*` defaults. We add
`--fingerprint-locale` as an alternative front-end.

**Files touched:**
- `chrome/browser/chrome_content_browser_client.cc` — in
  `ChromeContentBrowserClient::OverrideUserAgent` adjacent code, also
  copy `--fingerprint-locale` to `--lang` if `--lang` is unset.
- `services/network/public/cpp/network_switches.h` — declare we
  consume both.

**Behavior:**
```bash
chrome --fingerprint-locale=de-DE   # works
chrome --lang=de-DE                 # also works (upstream)
chrome --fingerprint-locale=de-DE --lang=en-US  # --lang wins, log warning
```

**Test:**
```js
assert.equal(navigator.language, "de-DE");
assert.deepEqual(navigator.languages, ["de-DE", "de"]);
assert.equal(new Intl.NumberFormat().resolvedOptions().locale, "de-DE");
assert.equal(new Intl.Collator().resolvedOptions().locale, "de-DE");
```

## Open question: Accept-Language header

`--lang=de-DE` causes the network stack to send
`Accept-Language: de-DE,de;q=0.9`. We want the same from
`--fingerprint-locale`. Since #35 forwards to `--lang`, this is
automatic — but verify with `curl -v` from the patched build against a
local echo server.

## Effort

3 days total. #32 + #35 each ~1 day; #33/#34 are verification only.
