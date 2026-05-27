#!/usr/bin/env python3
# Copyright 2026 Clark Labs Inc. - SPDX: MIT
"""In-container Linux smoke test for the built clark-browser binary.

Talks directly to chromium via the CDP HTTP+WebSocket endpoints. Requires
only the pure-python `websocket-client` package. No agent-browser dependency,
so it runs cleanly inside the build container.

Usage:
    CLARK_BINARY_PATH=/work/build/src/out/Default/headless_shell \
        python3 tests/linux_smoke.py

What it covers:
 1. JS-visible fingerprint vectors (navigator.platform, userAgent,
    hardwareConcurrency, maxTouchPoints, timezone, locale, languages,
    plugins.length, window.chrome, webdriver, UA Client Hints) when launched with
    the selected Linux or Windows font/platform profile.
 2. Network Information values from the configured datacenter profile.
 3. WebGPU is either intentionally unavailable or coherent with WebGL.
 4. Audio fingerprint differential across two seeds.

Exit code is the number of failed assertions; 0 = full pass.
"""
from __future__ import annotations

import json
import threading
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Iterator
from xml.sax.saxutils import escape

try:
    import websocket  # type: ignore  # websocket-client
except ImportError:
    print("ERROR: pip install websocket-client", file=sys.stderr)
    sys.exit(2)

BINARY = os.environ.get("CLARK_BINARY_PATH")
if not BINARY or not Path(BINARY).exists():
    print(f"ERROR: CLARK_BINARY_PATH not set or missing: {BINARY!r}", file=sys.stderr)
    sys.exit(2)

PORT = int(os.environ.get("CLARK_CDP_PORT", "9444"))
PROFILE = Path("/tmp/clark-linux-smoke-profile")
WINDOWS_CORE_FONTS = ("Arial", "Segoe UI", "Calibri")
WINDOWS_FONT_PROBES = {
    "Arial": "12px Arial",
    "Segoe UI": '12px "Segoe UI"',
    "Calibri": "12px Calibri",
}
LINUX_FONT_CANDIDATES = (
    "DejaVu Sans",
    "Liberation Sans",
    "Noto Sans",
    "Ubuntu",
    "Ubuntu Mono",
)
LINUX_FONT_PROBES = {family: f'12px "{family}"' for family in LINUX_FONT_CANDIDATES}
WINDOWS_FONTS_DIR = (os.environ.get("CLARK_WINDOWS_FONTS_DIR") or "").strip()
SMOKE_FONT_PROFILE = os.environ.get(
    "CLARK_SMOKE_FONT_PROFILE",
    "windows" if WINDOWS_FONTS_DIR else "linux",
).strip().lower()


class TrustedPageHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"<!doctype html><title>clark smoke</title>")

    def log_message(self, format: str, *args: object) -> None:
        return


def _next_id(state: dict) -> int:
    state["id"] += 1
    return state["id"]


def cdp_eval(expr: str) -> str:
    """Open a page target, evaluate expression, return JSON-encoded value."""
    with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/list", timeout=5) as r:
        targets = json.loads(r.read())
    page = next((t for t in targets if t.get("type") == "page"), None)
    if not page:
        # Open a fresh blank tab via /json/new.
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/new?about:blank", timeout=5) as r:
            page = json.loads(r.read())
    ws_url = page["webSocketDebuggerUrl"]
    ws = websocket.create_connection(ws_url, timeout=10)
    state = {"id": 0}
    try:
        ws.send(json.dumps({
            "id": _next_id(state),
            "method": "Runtime.evaluate",
            "params": {"expression": expr, "returnByValue": True, "awaitPromise": True},
        }))
        while True:
            msg = json.loads(ws.recv())
            if msg.get("id") == state["id"]:
                if "error" in msg:
                    return f"<error: {msg['error'].get('message', '?')}>"
                r = msg.get("result", {}).get("result", {})
                if "value" in r:
                    return json.dumps(r["value"])
                return json.dumps(r.get("description", "<undefined>"))
    finally:
        ws.close()


def cdp_navigate(url: str) -> None:
    with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/list", timeout=5) as r:
        targets = json.loads(r.read())
    page = next((t for t in targets if t.get("type") == "page"), None)
    if not page:
        return
    ws = websocket.create_connection(page["webSocketDebuggerUrl"], timeout=10)
    try:
        ws.send(json.dumps({"id": 1, "method": "Page.navigate", "params": {"url": url}}))
        ws.recv()
    finally:
        ws.close()


def _arg_value(args: tuple[str, ...], key: str) -> str | None:
    prefix = f"{key}="
    for arg in args:
        if arg.startswith(prefix):
            return arg.split("=", 1)[1]
    return None


def _fontconfig_env(fonts_dir: str | None) -> dict[str, str]:
    if not fonts_dir:
        return {}
    config_path = PROFILE / "fontconfig-smoke.conf"
    config_path.write_text(
        '<?xml version="1.0"?>\n'
        '<!DOCTYPE fontconfig SYSTEM "fonts.dtd">\n'
        '<fontconfig>\n'
        '  <include ignore_missing="yes">/etc/fonts/fonts.conf</include>\n'
        f"  <dir>{escape(fonts_dir)}</dir>\n"
        "</fontconfig>\n"
    )
    return {"FONTCONFIG_FILE": os.fspath(config_path)}


@contextmanager
def trusted_local_page() -> Iterator[tuple[str, str]]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), TrustedPageHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    origin = f"http://{host}:{port}"
    try:
        yield f"{origin}/", origin
    finally:
        server.shutdown()
        server.server_close()


@contextmanager
def launch(*args: str) -> Iterator[None]:
    if PROFILE.exists():
        shutil.rmtree(PROFILE)
    PROFILE.mkdir(parents=True)
    cmd = [
        BINARY,
        "--headless=new", "--no-sandbox", "--use-mock-keychain",
        f"--remote-debugging-port={PORT}",
        "--remote-debugging-address=127.0.0.1",
        "--remote-allow-origins=*",
        f"--user-data-dir={PROFILE}",
        "--disable-gpu",
        *args,
        "about:blank",
    ]
    env = os.environ.copy()
    env.update(_fontconfig_env(_arg_value(args, "--fingerprint-fonts-dir")))
    proc = subprocess.Popen(
        cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env
    )
    try:
        for _ in range(40):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/version", timeout=1) as r:
                    if r.status == 200:
                        break
            except Exception:
                time.sleep(0.3)
        else:
            raise RuntimeError("CDP never came up")
        yield
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


failures: list[str] = []
def expect(label: str, actual: str, predicate, expected_desc: str) -> None:
    ok = predicate(actual)
    mark = "PASS" if ok else "FAIL"
    print(f"  [{mark}] {label}: {actual}  (expected: {expected_desc})")
    if not ok:
        failures.append(f"{label}: got {actual!r}, expected {expected_desc}")


def json_ok(actual: str, predicate) -> bool:
    try:
        return bool(predicate(json.loads(actual)))
    except Exception:
        return False


def _font_profile_args(seed: str) -> tuple[list[str], dict[str, str]]:
    if SMOKE_FONT_PROFILE == "windows":
        if not WINDOWS_FONTS_DIR:
            print(
                "ERROR: CLARK_SMOKE_FONT_PROFILE=windows requires "
                "CLARK_WINDOWS_FONTS_DIR",
                file=sys.stderr,
            )
            sys.exit(2)
        return [
            f"--fingerprint={seed}",
            "--fingerprint-platform=windows",
            "--fingerprint-platform-version=19.0.0",
            f"--fingerprint-fonts-dir={WINDOWS_FONTS_DIR}",
            "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/148.0.0.0 Safari/537.36",
        ], {
            "label": "Windows",
            "navigator_platform": "Win32",
            "ua_marker": "Windows NT 10.0",
            "ua_ch_platform": "Windows",
            "ua_ch_platform_version": "19.0.0",
        }
    if SMOKE_FONT_PROFILE != "linux":
        print(
            f"ERROR: unsupported CLARK_SMOKE_FONT_PROFILE={SMOKE_FONT_PROFILE!r}",
            file=sys.stderr,
        )
        sys.exit(2)
    return [
        f"--fingerprint={seed}",
        "--fingerprint-platform=linux",
        "--user-agent=Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/148.0.0.0 Safari/537.36",
    ], {
        "label": "Linux",
        "navigator_platform": "Linux x86_64",
        "ua_marker": "X11; Linux x86_64",
        "ua_ch_platform": "Linux",
        "ua_ch_platform_version": "",
    }


def main() -> int:
    seed = "42069"
    profile_args, profile = _font_profile_args(seed)
    args = [
        *profile_args,
        "--fingerprint-brand=Chrome",
        "--fingerprint-brand-version=148.0.0.0",
        "--fingerprint-hardware-concurrency=12",
        "--fingerprint-max-touch-points=0",
        "--fingerprint-timezone=America/New_York",
        "--fingerprint-locale=en-US",
        "--fingerprint-network-profile=datacenter",
        "--accept-lang=en-US,en",
        "--disable-features=WebGPU",
        "--fingerprinting-client-rects-noise",
        "--fingerprinting-canvas-measuretext-noise",
        "--fingerprinting-canvas-image-data-noise",
    ]

    print(f"=== JS-surface vectors ({profile['label']} fingerprint) ===")
    with trusted_local_page() as (trusted_url, trusted_origin), \
            launch(*args, f"--unsafely-treat-insecure-origin-as-secure={trusted_origin}"):
        time.sleep(0.5)
        expect("navigator.webdriver", cdp_eval("navigator.webdriver"), lambda v: v == "false", "false")
        expect("navigator.plugins.length", cdp_eval("navigator.plugins.length"), lambda v: v == "5", "5")
        expect("typeof window.chrome", cdp_eval("typeof window.chrome"), lambda v: v == '"object"', '"object"')
        expect("navigator.platform", cdp_eval("navigator.platform"),
               lambda v: v == json.dumps(profile["navigator_platform"]),
               json.dumps(profile["navigator_platform"]))
        expect("hardwareConcurrency", cdp_eval("navigator.hardwareConcurrency"), lambda v: v == "12", "12")
        expect("maxTouchPoints", cdp_eval("navigator.maxTouchPoints"), lambda v: v == "0", "0")
        screen_state = cdp_eval("""
            ({
              width: screen.width,
              height: screen.height,
              availWidth: screen.availWidth,
              availHeight: screen.availHeight,
              colorDepth: screen.colorDepth,
              pixelDepth: screen.pixelDepth,
              outerWidth: window.outerWidth,
              outerHeight: window.outerHeight,
              devicePixelRatio: window.devicePixelRatio,
            })
        """)
        expect("screen/window coherent", screen_state,
               lambda v: json_ok(v, lambda s:
                   isinstance(s, dict) and
                   s.get("width", 0) > 0 and
                   s.get("height", 0) > 0 and
                   s.get("availWidth") == s.get("width") and
                   0 <= s.get("height", 0) - s.get("availHeight", 0) <= 200 and
                   s.get("outerWidth") == s.get("width") and
                   s.get("outerHeight") == s.get("availHeight") and
                   s.get("colorDepth") == 24 and
                   s.get("pixelDepth") == 24 and
                   s.get("devicePixelRatio") == 1),
               "positive desktop screen, matching outer size, 24-bit depth, DPR 1")
        expect("timezone", cdp_eval("Intl.DateTimeFormat().resolvedOptions().timeZone"),
               lambda v: v == '"America/New_York"', '"America/New_York"')
        expect("locale", cdp_eval("navigator.language"), lambda v: v == '"en-US"', '"en-US"')
        expect("Notification.permission", cdp_eval("Notification.permission"),
               lambda v: v == '"default"', '"default"')
        expect("permissions.query notifications", cdp_eval("""
            (async () => {
              return (await navigator.permissions.query({name: 'notifications'})).state;
            })()
        """), lambda v: v == '"prompt"', '"prompt"')
        font_probes = {**WINDOWS_FONT_PROBES, **LINUX_FONT_PROBES}
        font_state = cdp_eval(f"""
            (() => {{
              const probes = {json.dumps(font_probes)};
              const checks = {{}};
              for (const [family, css] of Object.entries(probes)) {{
                checks[family] = document.fonts.check(css);
              }}
              return checks;
            }})()
        """)
        if SMOKE_FONT_PROFILE == "windows":
            expect("Windows font pack", font_state,
                   lambda v: json_ok(v, lambda fonts:
                       all(fonts.get(family) is True
                           for family in WINDOWS_CORE_FONTS)),
                   "Arial, Segoe UI, and Calibri present")
        else:
            expect("Linux font profile", font_state,
                   lambda v: json_ok(v, lambda fonts:
                       any(fonts.get(family) is True
                           for family in LINUX_FONT_CANDIDATES)),
                   "at least one common Linux UI font present")
        network_state = cdp_eval("""
            ({
              effectiveType: navigator.connection.effectiveType,
              rtt: navigator.connection.rtt,
              downlink: navigator.connection.downlink,
              saveData: navigator.connection.saveData,
            })
        """)
        expect("navigator.connection datacenter profile", network_state,
               lambda v: json_ok(v, lambda n:
                   isinstance(n, dict) and
                   n.get("effectiveType") == "4g" and
                   isinstance(n.get("rtt"), int) and
                   10 <= n.get("rtt") <= 65 and
                   isinstance(n.get("downlink"), (int, float)) and
                   30 <= n.get("downlink") <= 120 and
                   n.get("saveData") is False),
               "4g, rtt 10-65ms, downlink 30-120Mbps, saveData false")
        webgpu_state = cdp_eval("""
            (async () => {
              const canvas = document.createElement('canvas');
              const gl = canvas.getContext('webgl') ||
                  canvas.getContext('experimental-webgl');
              const ext = gl && gl.getExtension('WEBGL_debug_renderer_info');
              const webglVendor = ext ? gl.getParameter(ext.UNMASKED_VENDOR_WEBGL) : '';
              const webglRenderer = ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : '';
              if (!navigator.gpu) {
                return {
                  supported: false,
                  reason: 'navigator.gpu absent',
                  webglVendor,
                  webglRenderer,
                };
              }
              const adapter = await navigator.gpu.requestAdapter();
              if (!adapter) {
                return {
                  supported: false,
                  reason: 'requestAdapter null',
                  webglVendor,
                  webglRenderer,
                };
              }
              const info = adapter.info || (
                  adapter.requestAdapterInfo ? await adapter.requestAdapterInfo() : {});
              return {
                supported: true,
                webglVendor,
                webglRenderer,
                vendor: info.vendor || '',
                architecture: info.architecture || '',
                device: info.device || '',
                description: info.description || '',
              };
            })()
        """)
        expect("WebGPU coherent or intentionally unavailable", webgpu_state,
               lambda v: json_ok(v, lambda g:
                   isinstance(g, dict) and (
                       g.get("supported") is False or (
                           g.get("supported") is True and
                           (
                               not g.get("vendor") or
                               str(g.get("vendor")).lower() in (
                                   str(g.get("webglVendor", "")) + " " +
                                   str(g.get("webglRenderer", ""))
                               ).lower()
                           ) and
                           isinstance(g.get("description"), str)
                       )
                   )),
               "unsupported with reason, or WebGPU vendor/description matches WebGL")
        ua = cdp_eval("navigator.userAgent")
        expect(f"UA = {profile['label'].lower()}", ua,
               lambda v: profile["ua_marker"] in v and "HeadlessChrome" not in v,
               f"{profile['ua_marker']} (no Headless)")
        cdp_navigate(trusted_url)
        time.sleep(0.5)
        expect("UA-CH secure context", cdp_eval("window.isSecureContext"), lambda v: v == "true", "true")
        ua_ch = cdp_eval("""
            (async () => {
              if (!navigator.userAgentData) return null;
              const high = await navigator.userAgentData.getHighEntropyValues(
                ['platform','platformVersion','architecture','bitness','fullVersionList']);
              return {
                platform: high.platform,
                platformVersion: high.platformVersion,
                architecture: high.architecture,
                bitness: high.bitness,
                brands: navigator.userAgentData.brands.map(b => b.brand),
                fullBrands: (high.fullVersionList || []).map(b => b.brand),
              };
            })()
        """)
        expect(f"UA-CH = {profile['label'].lower()}/chrome", ua_ch,
               lambda v: json_ok(v, lambda high:
                   isinstance(high, dict) and
                   high.get("platform") == profile["ua_ch_platform"] and
                   high.get("platformVersion") ==
                   profile["ua_ch_platform_version"] and
                   high.get("architecture") == "x86" and
                   high.get("bitness") == "64" and
                   "Google Chrome" in high.get("brands", []) and
                   "Google Chrome" in high.get("fullBrands", [])),
               f"{profile['label']} + Google Chrome client hints")

    print("\n=== Audio fingerprint differential (seed 1 vs 42069) ===")
    audio_html = (
        "data:text/html,<script>(async()=>{const oc=new OfflineAudioContext(1,5000,44100);"
        "const o=oc.createOscillator();o.type='triangle';o.frequency.value=10000;"
        "const c=oc.createDynamicsCompressor();c.threshold.value=-50;c.knee.value=40;"
        "c.ratio.value=12;c.attack.value=0;c.release.value=0.25;o.connect(c);"
        "c.connect(oc.destination);o.start(0);const b=await oc.startRendering();"
        "const d=b.getChannelData(0);let s=0;for(let i=0;i<d.length;i++)s+=Math.abs(d[i]);"
        "document.title='audio='+s.toFixed(15)})()</script>"
    )
    seeds = []
    for s in ("1", "42069"):
        seed_profile_args, _ = _font_profile_args(s)
        with launch(*seed_profile_args):
            time.sleep(0.5)
            cdp_navigate(audio_html)
            time.sleep(2)
            t = cdp_eval("document.title")
            seeds.append(t)
            print(f"  seed={s} {t}")
    expect("audio FP differs across seeds", str(seeds), lambda v: seeds[0] != seeds[1],
           "two distinct values")

    if failures:
        print(f"\n{len(failures)} failures:")
        for f in failures:
            print(f"  - {f}")
        return len(failures)
    print("\n[ALL PASSED]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
