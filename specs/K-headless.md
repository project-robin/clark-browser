# Patches K — Headless / Automation removal (#45-#48)

Four patches. All small.

## #45 — UA string in headless mode = full Chrome (not "HeadlessChrome")

See `patches/0045-headless-user-agent.patch`. Specced. Touches
`headless/lib/browser/headless_content_browser_client.cc`.

## #46 — `--enable-automation` removed from default args

**Status:** Done at the wrapper level — Playwright and Puppeteer wrappers
pass `ignoreDefaultArgs: ['--enable-automation']`. No Chromium binary
patch needed.

We can also harden by adding a binary-level filter: if
`--enable-automation` appears on argv, drop it silently in
`content/common/sandbox_init.cc` startup. But this is belt-and-suspenders
— the wrapper already covers it.

## #47 — `cdc_*` globals not injected

**File:** `chrome/browser/devtools/...` or the DevTools agent host.

**Stock behavior:** When DevTools is enabled (CDP open), Chromium
injects `window.cdc_<random>` globals into pages for internal use.
Selenium and ChromeDriver detection sites grep for `cdc_`.

**Change:** Suppress the `cdc_` injection when --remote-debugging-port
is open. The DevTools functionality doesn't actually depend on these
globals — they were a Selenium-era debugging vestige.

**Test:**
```js
const keys = Object.keys(window);
console.assert(!keys.some(k => k.startsWith('cdc_')));
console.assert(!keys.some(k => k.startsWith('__webdriver')));
console.assert(!keys.some(k => k.startsWith('__selenium')));
console.assert(!keys.some(k => k.startsWith('__$webdriverAsync')));
```

## #48 — `permissions.query({name:'notifications'})` consistency

**File:** `third_party/blink/renderer/modules/permissions/permissions.cc`

**Stock headless behavior:** Returns `state === 'denied'` for many
permissions even when nothing has explicitly been denied. Real Chrome
returns `'prompt'` (= "user hasn't decided yet"). Bot detection
literature flags `denied` as suspicious.

**Change:** In headless mode, return `'prompt'` for `notifications`,
`geolocation`, `microphone`, `camera`, `clipboard-read`,
`clipboard-write` unless the user has explicitly denied via policy.

**Test:**
```js
for (const name of ['notifications','geolocation','clipboard-read']) {
  const s = await navigator.permissions.query({name}).then(p=>p.state);
  console.assert(s === 'prompt' || s === 'granted',
    `${name} = ${s}, expected prompt|granted`);
}
```

## Effort

Single-day each. 1 week for the category including test coverage.
