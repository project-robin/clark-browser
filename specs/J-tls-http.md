# Patches J — TLS / HTTP fingerprint (#40-#44)

Five patches. **Defer this whole category until measured.** See
`specs/40-tls-fingerprint.md` for the rationale. Below: implementation
notes if/when we decide to go.

## Why defer

BoringSSL's default ClientHello IS Chrome's ClientHello (they're built
together). Same for HTTP/2 SETTINGS. Unless ungoogled-chromium has
made non-default changes here (and as far as we know it hasn't), we
inherit Chrome's TLS/HTTP fingerprint for free.

**Action:** Before any patch in this category, run:

```bash
# Build vanilla ungoogled
./build/fetch-ungoogled.sh && build vanilla
# Capture our ClientHello against a tcpdump-equipped local TLS server
out/Default/chrome --headless=new https://local.test:8443/ping
# Hash it; compare to real Chrome's
```

If the hash matches real Chrome 146 → patches #40-44 are no-ops. Ship
without them.

If the hash differs → identify the delta and patch the specific
extension that's off.

## #40-#41 — TLS ClientHello extension/cipher order

**Files:**
- `third_party/boringssl/src/ssl/ssl_lib.cc`
- `third_party/boringssl/src/ssl/extensions.cc`

**Approach:** BoringSSL builds extensions in a fixed order defined in
`extensions.cc`. The order is real Chrome's order (by construction).
If a patch is needed, it's likely to remove a debug-only extension that
ungoogled-chromium may have left enabled, or to add one Chrome ships
that ungoogled stripped.

**Reference:** curl-impersonate's
`chrome/patches/curl-impersonate-chrome.patch` — copy the deltas it
applies to libcurl's BoringSSL fork into our build.

## #42 — TLS GREASE values present

Stock Chrome inserts GREASE (Generate Random Extensions And Sustain
Extensibility) values at specific positions in the ClientHello
extension list and supported_groups. BoringSSL's default ClientHello
includes GREASE in those positions — verify via tcpdump capture.

## #43 — HTTP/2 SETTINGS frame field order

**File:** `net/spdy/spdy_session.cc`, function `SendInitialSettings()`.

Chrome's order:
```
HEADER_TABLE_SIZE         (id 1)
ENABLE_PUSH               (id 2)  (sometimes omitted)
MAX_CONCURRENT_STREAMS    (id 3)
INITIAL_WINDOW_SIZE       (id 4)
MAX_HEADER_LIST_SIZE      (id 6)
```

Akamai builds its HTTP/2 fingerprint from this order. Patches here are
verification + regression tests against real Chrome's setting order.

## #44 — HTTP/2 WINDOW_UPDATE / PRIORITY frames

Same file. Real Chrome sends an immediate WINDOW_UPDATE after the
initial SETTINGS, incrementing the connection-level window by
~15 MB - 65535. Detection: bots often skip this. Verify our build
sends it.

## Test harness (the most important deliverable in this category)

Write `tests/tls_fingerprint.py` that:

1. Starts a local TLS server with `cryptography` library, captures
   raw ClientHello bytes
2. Connects from our built chrome via headless mode
3. Computes JA3 and JA4 hashes
4. Compares against captured real-Chrome hashes for the same Chromium
   version

If hashes match → category is done, ship. If they don't → bisect to
which extension/cipher/order differs and patch ONLY that.

## Effort

| Item | Time |
|---|---|
| Test harness with captured real-Chrome baseline | 1 week |
| Bisect to find delta (if any) | varies, 0-2 weeks |
| Patches per delta found | 0.5-1 week each |
| **Total upper bound** | **4 weeks** |
| **Realistic mode (no patches needed beyond test harness)** | **1 week** |
