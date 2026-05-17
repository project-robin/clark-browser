# Spec — patches #40-44: TLS / HTTP fingerprint matches real Chrome

This is the highest-effort category. The TLS ClientHello and HTTP/2
SETTINGS frame are the strongest **non-JS** bot signals — they survive
proxy, survive headless detection, survive everything renderer-side
because they're below the renderer entirely. Cloudflare uses them.
Akamai uses them. Datadome uses them.

## Public idea sources

- **curl-impersonate** (MIT) — the canonical reference for
  patches that make a non-Chrome client emit Chrome's TLS bytes
  exactly: https://github.com/lwthiker/curl-impersonate. Patch
  series under `chrome/patches/` is what we want to port. Targets
  curl + libnghttp2, not Chromium, but the patches show **what bytes
  to emit**.
- **utls** (BSD-2) — Go library that ships pre-built TLS ClientHello
  templates for Chrome, Firefox, Safari, etc.:
  https://github.com/refraction-networking/utls
- **JA3/JA4 spec**: https://github.com/FoxIO-LLC/ja4
- **ja3er.com** and similar fingerprint databases for ground-truth
  Chrome fingerprints by version.

## What we're trying to match

For Chromium 146 (matches the binary we ship) on Linux x64, real Chrome's
ClientHello has:

- **Version**: TLS 1.2 in record header, supported_versions extension
  listing 1.3 and 1.2
- **Cipher list**: GREASE + 17 ciphers in a specific order
- **Extension list**: ~17 extensions in a specific order, with GREASE
  values inserted at positions 1 and last
- **Curves (supported_groups)**: GREASE, X25519, secp256r1, secp384r1
- **Signature algorithms**: specific 8-entry list

The exact bytes change between Chromium releases. We re-capture per
release.

HTTP/2 has its own fingerprint:
- **SETTINGS** frame field order: HEADER_TABLE_SIZE, ENABLE_PUSH,
  MAX_CONCURRENT_STREAMS, INITIAL_WINDOW_SIZE, MAX_HEADER_LIST_SIZE
- **WINDOW_UPDATE** delta increment value
- **PRIORITY** frame presence and weight
- **HPACK dynamic table size**

## Why this is hard in Chromium specifically

Chromium uses BoringSSL, not OpenSSL. The ClientHello assembly in
BoringSSL is largely fixed-order — much less configurable than
upstream Chromium expects of OpenSSL. The good news: BoringSSL's
default ClientHello IS Chrome's. **The bad news** is when we want a
specific seed-driven variation (different Chrome version, different
extension), we have to patch BoringSSL directly.

For most use cases we don't want variation. We want default Chrome
behavior, just without anything that leaks "this is automated". And
default Chrome behavior == default BoringSSL behavior. So patches in
this category may mostly reduce to:

- **Confirm** the default ClientHello matches the targeted Chrome
  version's bytes (write a test).
- **Suppress** any automation-mode tweaks Chromium does in headless
  (e.g., disabling certificate transparency in some modes — known
  signal).

If we want per-seed variation later, we'd cherry-pick utls patches
into BoringSSL — much heavier work.

## Implementation outline (minimum viable)

1. **Test harness first.** Write a tool that captures the ClientHello
   bytes emitted by our build against a local TLS server. Compare to
   captured real-Chrome ClientHello for the same Chromium version.
2. **If equal:** ship; no patches needed in this category for v1.
3. **If unequal:** identify the deltas, patch them in `net/socket/
   ssl_client_socket_impl.cc` and `third_party/boringssl/`.

For HTTP/2:
1. In `net/spdy/spdy_session.cc`, verify SETTINGS frame ordering matches
   Chromium upstream (it should — we inherit it).
2. If headless mode tweaks any of this, undo the tweak.

## Reuse strategy

Rather than write Chromium patches from scratch, **defer this category**
until we measure detection rates with patches #1-#39 in place. If TLS
fingerprint isn't the bottleneck, we save weeks. Detection sites that
care about TLS (Cloudflare, Akamai bot manager) are also the hardest to
test legally — we can only test against demo endpoints we operate.

## Tests

```python
# tests/tls_fingerprint.py
import ssl, socket, hashlib
# Connect using our chromium build to a local TLS endpoint that
# captures ClientHello bytes. Compare hash to known real-Chrome hash.
expected_ja3 = "..."   # real Chrome 146 linux-x64 JA3
expected_ja4 = "t13d1517h2_..."   # real Chrome 146 JA4
captured_ja3 = capture_ja3_from_our_build()
assert captured_ja3 == expected_ja3
```
