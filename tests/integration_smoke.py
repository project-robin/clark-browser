#!/usr/bin/env python3
# Copyright 2026 Clark Labs Inc. — SPDX: MIT
"""End-to-end smoke test for a built clark-browser binary.

Usage:
    CLARK_BINARY_PATH=/path/to/Chromium python3 tests/integration_smoke.py

What it covers:
 1. JS-visible fingerprint vectors via CDP (navigator.platform, userAgent,
    hardwareConcurrency, maxTouchPoints, timezone, locale, languages,
    plugins.length, window.chrome, screen.{width,height}, webdriver, UA-CH).
 2. HTTP request-header consistency vs. the JS-visible state, by hitting
    httpbin.org/headers.
 3. Audio fingerprint differential: same DynamicsCompressor-based hash
    should differ across two seeds.
 4. Canvas fingerprint differential: toDataURL hash differs across seeds.
 5. WebGL `UNMASKED_{VENDOR,RENDERER}` reflect --fingerprint-gpu-*.
 6. Network Information values from the configured datacenter profile.
 7. WebGPU is either intentionally unavailable or coherent with WebGL.
 8. bot.sannysoft.com test grid passes every check except WebGL (when run
    headless without swiftshader; pass --webgl to enable swiftshader).

Exit code is the number of failed assertions.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import time
from urllib.parse import quote
import urllib.request
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Iterator
from xml.sax.saxutils import escape

import httpx  # type: ignore

BINARY = os.environ.get("CLARK_BINARY_PATH")
if not BINARY:
    print("ERROR: set CLARK_BINARY_PATH to the patched chromium binary", file=sys.stderr)
    sys.exit(2)

AB = os.environ.get("AGENT_BROWSER", shutil.which("agent-browser") or "/tmp/clark-ab/agent-browser")
if not Path(AB).exists():
    print(f"ERROR: agent-browser CLI not found at {AB}. Set AGENT_BROWSER.", file=sys.stderr)
    sys.exit(2)

PORT = int(os.environ.get("CLARK_CDP_PORT", "9333"))
PROFILE = Path("/tmp/clark-smoke-profile")
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


def cdp_eval(expr: str) -> str:
    """Run an expression via agent-browser eval, return the trailing line."""
    # NOTE: do NOT pass --session here. agent-browser's --session flag triggers
    # an auto-launch path that bypasses --cdp and tries the default port 9223.
    out = subprocess.run(
        [AB, "--cdp", str(PORT), "eval", expr],
        capture_output=True, text=True, timeout=30,
    )
    if out.returncode != 0:
        return f"<error: {out.stderr.strip()[:200]}>"
    return out.stdout.strip().splitlines()[-1] if out.stdout.strip() else "<empty>"


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
        f"--user-data-dir={PROFILE}",
        *args,
        "about:blank",
    ]
    env = os.environ.copy()
    env.update(_fontconfig_env(_arg_value(args, "--fingerprint-fonts-dir")))
    proc = subprocess.Popen(
        cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env
    )
    try:
        # Wait for CDP socket.
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
        proc.wait(timeout=10)


failures: list[str] = []
def expect(label: str, actual: str, predicate, expected_desc: str) -> None:
    ok = predicate(actual)
    mark = "PASS" if ok else "FAIL"
    print(f"  [{mark}] {label}: {actual}  (expected: {expected_desc})")
    if not ok:
        failures.append(f"{label}: got {actual!r}, expected {expected_desc}")


def json_ok(actual: str, predicate) -> bool:
    try:
        parsed = json.loads(actual)
        if isinstance(parsed, str):
            parsed = json.loads(parsed)
        return bool(predicate(parsed))
    except Exception:
        return False


def data_html_url(html: str) -> str:
    return "data:text/html;charset=utf-8," + quote(html, safe="")


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
    if "--webgl" in sys.argv:
        args += ["--enable-unsafe-swiftshader", "--use-gl=angle", "--use-angle=swiftshader"]
    else:
        args += ["--disable-gpu"]

    print(f"=== JS-surface vectors (with {profile['label']} fingerprint) ===")
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
            JSON.stringify({
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
            JSON.stringify((() => {{
              const probes = {json.dumps(font_probes)};
              const checks = {{}};
              for (const [family, css] of Object.entries(probes)) {{
                checks[family] = document.fonts.check(css);
              }}
              return checks;
            }})())
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
            JSON.stringify({
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
                return JSON.stringify({
                  supported: false,
                  reason: 'navigator.gpu absent',
                  webglVendor,
                  webglRenderer,
                });
              }
              const adapter = await navigator.gpu.requestAdapter();
              if (!adapter) {
                return JSON.stringify({
                  supported: false,
                  reason: 'requestAdapter null',
                  webglVendor,
                  webglRenderer,
                });
              }
              const info = adapter.info || (
                  adapter.requestAdapterInfo ? await adapter.requestAdapterInfo() : {});
              return JSON.stringify({
                supported: true,
                webglVendor,
                webglRenderer,
                vendor: info.vendor || '',
                architecture: info.architecture || '',
                device: info.device || '',
                description: info.description || '',
              });
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
        subprocess.run([AB, "--cdp", str(PORT), "open", trusted_url],
                       capture_output=True, timeout=30)
        time.sleep(0.5)
        expect("UA-CH secure context", cdp_eval("window.isSecureContext"), lambda v: v == "true", "true")
        ua_ch = cdp_eval("""
            (async () => {
              if (!navigator.userAgentData) return null;
              const high = await navigator.userAgentData.getHighEntropyValues(
                ['platform','platformVersion','architecture','bitness','fullVersionList']);
              return JSON.stringify({
                platform: high.platform,
                platformVersion: high.platformVersion,
                architecture: high.architecture,
                bitness: high.bitness,
                brands: navigator.userAgentData.brands.map(b => b.brand),
                fullBrands: (high.fullVersionList || []).map(b => b.brand),
              });
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

        if "--webgl" in sys.argv:
            webgl = cdp_eval("""
                JSON.stringify((() => {
                  const canvas = document.createElement('canvas');
                  const gl = canvas.getContext('webgl') ||
                      canvas.getContext('experimental-webgl');
                  if (!gl) return {supported: false};
                  const ext = gl.getExtension('WEBGL_debug_renderer_info');
                  return {
                    supported: true,
                    vendor: ext ? gl.getParameter(ext.UNMASKED_VENDOR_WEBGL) : null,
                    renderer: ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : null,
                    version: gl.getParameter(gl.VERSION),
                    shading: gl.getParameter(gl.SHADING_LANGUAGE_VERSION),
                    extensions: gl.getSupportedExtensions() || [],
                  };
                })())
            """)
            expect("WebGL seed fallback = Windows ANGLE", webgl,
                   lambda v: json_ok(v, lambda g:
                       isinstance(g, dict) and
                       g.get("supported") is True and
                       "Google Inc." in str(g.get("vendor")) and
                       "ANGLE (" in str(g.get("renderer")) and
                       "Direct3D11" in str(g.get("renderer")) and
                       "SwiftShader" not in str(g.get("renderer")) and
                       "llvmpipe" not in str(g.get("renderer")) and
                       "Chromium" in str(g.get("version")) and
                       "WEBGL_debug_renderer_info" in g.get("extensions", [])),
                   "seeded Windows ANGLE tuple, not SwiftShader/llvmpipe")

        print("\n=== HTTP UA vs JS UA consistency ===")
        # Drive a real request through the same renderer; httpbin echoes headers.
        subprocess.run([AB, "--cdp", str(PORT), "open", "https://httpbin.org/headers"],
                       capture_output=True, timeout=30)
        time.sleep(2)
        body = cdp_eval("document.body.textContent")
        expect(f"HTTP UA = {profile['label']}", body,
               lambda v: profile["ua_marker"] in v and "Macintosh" not in v,
               f"{profile['ua_marker']} in body, no Macintosh")

        print("\n=== bot.sannysoft.com pass-rate ===")
        subprocess.run([AB, "--cdp", str(PORT), "open", "https://bot.sannysoft.com"],
                       capture_output=True, timeout=30)
        time.sleep(6)
        rows = cdp_eval("""
            Array.from(document.querySelectorAll('table tr')).map(r => {
                const c = r.querySelectorAll('td,th');
                return c.length>=2 ? c[0].textContent.trim()+' | '+c[1].textContent.trim().slice(0,40) : '';
            }).filter(x=>x).join('\\n')
        """)
        expect("bot.sannysoft WebDriver missing", rows, lambda v: "missing (passed)" in v, "missing (passed)")
        expect("bot.sannysoft Chrome present", rows, lambda v: "present (passed)" in v, "present (passed)")
        expect("bot.sannysoft no Headless", rows,
               lambda v: "HEADCHR_UA | ok" in v and
                         "HEADCHR_CHROME_OBJ | ok" in v and
                         "HeadlessChrome" not in v,
               "HEADCHR_UA/HEADCHR_CHROME_OBJ ok, no HeadlessChrome")
        expect("bot.sannysoft notification permission", rows,
               lambda v: "HEADCHR_PERMISSIONS | ok" in v,
               "HEADCHR_PERMISSIONS ok")

        print("\n=== Antoine Vastel headless check ===")
        subprocess.run([AB, "--cdp", str(PORT), "open",
                        "https://arh.antoinevastel.com/bots/areyouheadless"],
                       capture_output=True, timeout=30)
        time.sleep(6)
        vastel = cdp_eval("document.body.innerText")
        expect("antoinevastel not Chrome headless", vastel,
               lambda v: "You are not Chrome headless" in v,
               "You are not Chrome headless")

    # Audio + canvas differential across two seeds — separate launches.
    print("\n=== Audio fingerprint differential (seed 1 vs 42069) ===")
    audio_html = data_html_url("<script>(async()=>{const oc=new OfflineAudioContext(1,5000,44100);const o=oc.createOscillator();o.type='triangle';o.frequency.value=10000;const c=oc.createDynamicsCompressor();c.threshold.value=-50;c.knee.value=40;c.ratio.value=12;c.attack.value=0;c.release.value=0.25;o.connect(c);c.connect(oc.destination);o.start(0);const b=await oc.startRendering();const d=b.getChannelData(0);let s=0;for(let i=0;i<d.length;i++)s+=Math.abs(d[i]);document.title='audio='+s.toFixed(15)})()</script>")
    seeds = []
    for s in ("1", "42069"):
        seed_profile_args, _ = _font_profile_args(s)
        with launch("--disable-gpu", *seed_profile_args):
            time.sleep(0.5)
            subprocess.run([AB, "--cdp", str(PORT), "open", audio_html],
                           capture_output=True, timeout=30)
            time.sleep(2)
            t = cdp_eval("document.title")
            seeds.append(t)
            print(f"  seed={s} {t}")
    expect("audio FP differs across seeds", str(seeds), lambda v: seeds[0] != seeds[1], "two distinct values")

    print("\n=== Canvas fingerprint differential (seed 1 vs 42069) ===")
    canvas_html = data_html_url(
        "<canvas id=c width=240 height=80></canvas><script>"
        "const c=document.getElementById('c');const x=c.getContext('2d');"
        "x.textBaseline='top';x.font='17px Arial';x.fillStyle='#f60';"
        "x.fillRect(0,0,240,80);x.fillStyle='#069';"
        "x.fillText('Clark canvas smoke 123',4,17);"
        "const d=c.toDataURL();let h=2166136261;"
        "for(let i=0;i<d.length;i++){h^=d.charCodeAt(i);h=Math.imul(h,16777619);}"
        "document.title='canvas='+(h>>>0).toString(16)</script>"
    )
    canvas_seeds = []
    for s in ("1", "42069"):
        seed_profile_args, _ = _font_profile_args(s)
        with launch(
            "--disable-gpu",
            *seed_profile_args,
            "--fingerprinting-canvas-measuretext-noise",
            "--fingerprinting-canvas-image-data-noise",
        ):
            time.sleep(0.5)
            subprocess.run([AB, "--cdp", str(PORT), "open", canvas_html],
                           capture_output=True, timeout=30)
            time.sleep(1)
            t = cdp_eval("document.title")
            canvas_seeds.append(t)
            print(f"  seed={s} {t}")
    expect("canvas FP differs across seeds", str(canvas_seeds),
           lambda v: canvas_seeds[0] != canvas_seeds[1], "two distinct values")

    if failures:
        print(f"\n{len(failures)} failures:")
        for f in failures:
            print(f"  - {f}")
        return len(failures)
    print(f"\n[ALL PASSED]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
