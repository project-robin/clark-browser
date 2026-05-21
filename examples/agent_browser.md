# Using clark-browser with Vercel agent-browser

Vercel [`agent-browser`](https://github.com/vercel-labs/agent-browser) gives AI
agents a CLI for browser control: open pages, take accessibility snapshots,
click stable refs, capture screenshots, run JavaScript, and connect over CDP.

`clark-browser` supplies the Chromium binary. The useful split is:

- `agent-browser` controls the page.
- `clark-browser` controls what browser fingerprint the page sees.

This example uses only the public `clark-browser` package and the public
`agent-browser` CLI.

## Install

```bash
npm install -g agent-browser
agent-browser install

python3 -m pip install clark-browser
clark-browser fetch
```

Inspect the cached browser path:

```bash
clark-browser info
```

## Launch through agent-browser

Resolve the patched Chromium executable:

```bash
export CLARK_BIN="$(
  python3 - <<'PY'
from clarkbrowser import ensure_binary
print(ensure_binary())
PY
)"
```

Set a stable fingerprint for the session:

```bash
export CLARK_UA="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"

export CLARK_ARGS="--no-sandbox,\
--fingerprint=12345,\
--fingerprint-platform=linux,\
--fingerprint-brand=Chrome,\
--fingerprint-brand-version=148.0.0.0,\
--fingerprint-timezone=America/Los_Angeles,\
--fingerprint-locale=en-US,\
--fingerprint-network-profile=datacenter,\
--disable-features=WebGPU,\
--lang=en-US,\
--accept-lang=en-US,en,\
--user-agent=${CLARK_UA}"
```

Close old sessions before changing the executable or args:

```bash
agent-browser close --all
```

Open a page with the clark-browser binary:

```bash
agent-browser \
  --session clark-browser-demo \
  --executable-path "$CLARK_BIN" \
  --args "$CLARK_ARGS" \
  --user-agent "$CLARK_UA" \
  open https://bot.sannysoft.com
```

Drive the page with normal `agent-browser` commands:

```bash
agent-browser --session clark-browser-demo snapshot -i
agent-browser --session clark-browser-demo screenshot ./clark-browser-demo.png
agent-browser --session clark-browser-demo eval "navigator.webdriver"
agent-browser --session clark-browser-demo eval "navigator.plugins.length"
```

Expected smoke-test shape:

- `navigator.webdriver` returns `false`
- `navigator.plugins.length` is non-zero
- `navigator.userAgent` does not contain `HeadlessChrome`
- `navigator.platform`, User-Agent, timezone, locale, and proxy geography are
  consistent

## Environment-variable form

For agents and repeatable scripts, env vars are usually cleaner than long
command lines:

```bash
export AGENT_BROWSER_SESSION=clark-browser-demo
export AGENT_BROWSER_EXECUTABLE_PATH="$CLARK_BIN"
export AGENT_BROWSER_ARGS="$CLARK_ARGS"
export AGENT_BROWSER_USER_AGENT="$CLARK_UA"

agent-browser open https://example.com
agent-browser snapshot -i
agent-browser click @e1
agent-browser screenshot ./example.png
```

## CDP attach form

Use CDP attach when you want to start the Chromium process yourself.

```bash
"$CLARK_BIN" \
  --headless=new \
  --remote-debugging-port=9222 \
  --remote-debugging-address=127.0.0.1 \
  --remote-allow-origins=* \
  --user-data-dir=/tmp/clark-browser-agent-profile \
  --no-sandbox \
  --fingerprint=12345 \
  --fingerprint-platform=linux \
  --fingerprint-brand=Chrome \
  --fingerprint-brand-version=148.0.0.0 \
  --fingerprint-timezone=America/Los_Angeles \
  --fingerprint-locale=en-US \
  --disable-features=WebGPU \
  --lang=en-US \
  --accept-lang=en-US,en \
  --user-agent="$CLARK_UA" \
  about:blank
```

In another shell:

```bash
agent-browser --cdp 9222 open https://bot.sannysoft.com
agent-browser --cdp 9222 snapshot -i
agent-browser --cdp 9222 eval "navigator.webdriver"
```

Keep CDP ports bound to localhost unless you have a separate access-control
layer. Any process that can reach the debugging port can control the browser.

## Practical notes

- Keep one identity stable for a session. Do not rotate fingerprint, timezone,
  language, viewport, and IP between clicks.
- Match proxy geography/type to timezone, locale, and network profile.
- For HTTP proxy sessions, add
  `--force-webrtc-ip-handling-policy=disable_non_proxied_udp` or set
  `CLARK_WEBRTC_POLICY=proxy-coherent` so WebRTC does not expose a different
  non-proxied route.
- For headless sessions, keep WebGPU deliberately disabled
  (`--disable-features=WebGPU`) unless you are explicitly enabling it and using
  the coherent WebGPU adapter-info patch.
- Use a Linux profile on Linux unless you also pass a real Windows font pack via
  `--fingerprint-fonts-dir`; otherwise font enumeration exposes the host.
- Prefer `snapshot -i` and `@ref` clicks for agent workflows.
- Use screenshots for visual confirmation.
- Restart the `agent-browser` session after changing executable path, profile,
  proxy, User-Agent, or fingerprint args.
