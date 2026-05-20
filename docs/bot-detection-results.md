# Live Bot Detection Results

This table records a live detector sweep for release
[`chromium-v148.0.7778.96-stealth1`](https://github.com/clark-labs-inc/clark-browser/releases/tag/chromium-v148.0.7778.96-stealth1).

Run date: 2026-05-20  
Environment: E2B Ubuntu 24.04 sandbox, `agent-browser 0.27.0`  
Binary: GitHub release asset `clark-browser-linux-x64.tar.gz`  
SHA256: `902934003d3183dc13fd254ef14d9286a8b47396414e9f851801479c3b3fb4a9`

The binary was downloaded inside E2B from the GitHub release, hash-verified,
launched as patched `headless_shell`, and driven through the real
`agent-browser --cdp` CLI. Raw captured page text and probe output are stored in
[`reports/bot-detection/2026-05-20-stealth1/results.json`](../reports/bot-detection/2026-05-20-stealth1/results.json).

| Target | Result | Evidence |
|---|---:|---|
| Baseline JS/CDP probe | PASS | `navigator.webdriver=false`, `plugins.length=5`, `platform=Win32`, coherent `1440x900` screen, WebGL `Google Inc. (NVIDIA)` / `ANGLE (...) Direct3D11`; `permissions.query({name:"notifications"})` returned `prompt`. |
| [Cloudflare challenge smoke](https://nowsecure.nl/) | PASS | Loaded `nowsecure.nl` without visible Cloudflare challenge/block text. |
| [SannySoft bot detector](https://bot.sannysoft.com/) | PASS | WebDriver missing, WebDriver Advanced passed, Chrome present, `HEADCHR_UA`, `HEADCHR_CHROME_OBJ`, `HEADCHR_PERMISSIONS`, `HEADCHR_PLUGINS`, and `HEADCHR_IFRAME` all `ok`. |
| [Antoine Vastel headless test](https://arh.antoinevastel.com/bots/areyouheadless) | PASS with `--accept-lang=en-US,en` | Follow-up E2B run used the same released binary and real `agent-browser`; without `--accept-lang` the page returned `You are Chrome headless`, with `--accept-lang=en-US,en` it returned `You are not Chrome headless`. |
| [Incolumitas bot detector](https://bot.incolumitas.com/) | OBSERVED | Page loaded and standard Intoli-style JSON showed `userAgent`, `webDriver`, and `pluginsLength` as `OK`; no stable behavioral score was parsed. `connectionRTT` reported `FAIL`. |
| [Fingerprint Bot Demo](https://botd-demo.fpjs.sh/) | OBSERVED | Demo loaded, but it is an interactive Browserless code runner and did not expose a passive not-bot verdict. |
| [BrowserLeaks Client Hints](https://browserleaks.com/client-hints) | PASS | Windows platform/version, Chromium/Google Chrome brands, and no `HeadlessChrome` in the captured page text. |
| [BrowserLeaks WebGL](https://browserleaks.com/webgl) | PASS | WebGL and WebGL2 supported; page showed Google/NVIDIA ANGLE signals and no SwiftShader/llvmpipe renderer text. |
| [Pixelscan fingerprint check](https://pixelscan.net/) | OBSERVED | Page loaded, but no stable passive pass/fail verdict was exposed in captured text. |
| [CreepJS fingerprint check](https://abrahamjuliot.github.io/creepjs/) | OBSERVED | Page loaded; no single pass/fail verdict. The Headless panel remained visible with `chromium: true`, `like headless: 0%`, and `headless: 0%`. |
| FingerprintJS BotD GitHub Pages demo | UNAVAILABLE | The formerly documented `https://fingerprintjs.github.io/BotD/` public demo returned GitHub Pages 404 during the run. |

## Interpretation

The released binary passes the broad JS-visible checks that matter for Clark's
current E2B + `agent-browser` path: webdriver, plugins, Chrome object,
permissions, UA/UA-CH, screen metrics, and WebGL all stayed coherent in live
public pages.

The Antoine Vastel failure was traced to the HTTP `Accept-Language` request
header, not to a JavaScript-only surface. A Chrome-looking request without
`Accept-Language` is classified as headless by that endpoint; adding
`--accept-lang=en-US,en` makes the same released binary return
`You are not Chrome headless`. CreepJS still keeps a Headless panel visible,
though its captured percentages did not classify the run as fully headless, so
that remains the next browser-source stealth backlog.
