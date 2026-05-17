# Security policy

## Reporting a vulnerability

Send security reports to **security@clarklabs.ai** (or open a private
security advisory on GitHub if you prefer).

Please **do not** file a public issue for sandbox-escape or RCE-class bugs in
the patched Chromium binary, or for vulnerabilities in the wrapper code that
could let a malicious profile escalate. We'll respond within 72 hours.

## Scope

In scope:

- Wrapper code in `clarkbrowser/` (Python), `js/` (when present), `bin/`
- Build scripts under `build/`
- Patch files under `patches/` — including unintended security regressions
  vs upstream Chromium / ungoogled-chromium
- The packaged binary distributed via GitHub Releases

Out of scope:

- Vulnerabilities present in upstream Chromium that are *not* introduced by
  our patches — please report those to https://www.chromium.org/Home/chromium-security/
- General Chromium fingerprint-detection findings (the project's whole goal
  is anti-fingerprint; if you have a public detection technique that defeats
  our patches, please file a normal issue — that's a feature gap, not a
  vulnerability)

## Disclosure timeline

- 72h: acknowledgement
- 14d: triage + reproduction
- 30d: fix landed in main + advisory drafted
- 90d (or sooner if exploited in the wild): public disclosure

## Hall of fame

Reporters who responsibly disclose receive credit in `CHANGELOG.md` and the
GitHub Security Advisory unless they prefer anonymity.
