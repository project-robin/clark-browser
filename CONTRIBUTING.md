# Contributing to clark-browser

Thanks for your interest in clark-browser. This project is maintained by
[Clark Labs Inc.](https://clarklabs.ai/) and is open to outside contributions.

## Quick links

- **Bug reports / feature requests**: file an issue with a minimal repro
- **New patches**: read `METHODOLOGY.md` before opening a PR — every patch
  must be written from public sources only (W3C / Chromium / Brave-MPL /
  curl-impersonate / utls), and the PR header must declare the source
- **Wrapper code (Python/JS/scripts)**: standard PR flow

## Local development

```bash
git clone https://github.com/clark-labs-inc/clark-browser
cd clark-browser
python3 -m venv .venv && source .venv/bin/activate
pip install -e .[dev]
pytest tests/
```

For full Chromium rebuilds against your patch changes, see [`build/README.md`](./build/README.md).

## Adding a stealth patch

1. Find the detection vector. Document where real Chrome and stock Chromium
   diverge on the JS-visible behavior. Cite the W3C / WHATWG spec.
2. Locate the Chromium source file. Use `chromium.googlesource.com` to find
   the function. Pin against the version in `clarkbrowser/config.py`.
3. Write the patch. Update an in-tree file (with a real `git diff`) or add
   a new file under `patches/000-shared/`.
4. Add header credit:
   ```
   # clark-browser — Copyright YEAR Clark Labs Inc. — MIT
   # Patch NNNN — short description
   # Source verified against: <upstream URL>
   # Idea source: <W3C spec / public reference>
   # Clean room: written from <public sources>. Proprietary stealth-browser
   #             binaries not consulted.
   ```
5. Add or update an entry in `PATCHES.md` and `CHANGELOG.md`.
6. Build, run `examples/stealth_check.py` confirming the vector behaves as
   expected. Paste the eval output into the PR description.

## Clean-room methodology

We do **not** reverse-engineer proprietary stealth-browser binaries. See
[`METHODOLOGY.md`](./METHODOLOGY.md) for the full set of rules. PRs that
appear to derive from such binaries will be rejected.

## Acceptable use

clark-browser is intended for:

- Automated testing of web applications you own or have permission to test
- Web scraping of public data within sites' terms of service
- Security research and bot-detection research
- Building agent-based products that browse the web on behalf of their users

You are responsible for how you use it. clark-browser does not condone or
support:

- Unauthorized access to financial, healthcare, or government systems
- Credential stuffing or brute-force authentication attempts
- Account creation abuse or any activity that violates a target site's
  terms or applicable law in your jurisdiction

## License

By contributing, you agree your contribution is licensed under the project's
MIT License, and that Clark Labs Inc. may distribute it as part of
clark-browser.
