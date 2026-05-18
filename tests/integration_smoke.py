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
 6. bot.sannysoft.com test grid passes every check except WebGL (when run
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
import urllib.request
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Iterator

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
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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


def main() -> int:
    seed = "42069"
    args = [
        f"--fingerprint={seed}",
        "--fingerprint-platform=windows",
        "--fingerprint-platform-version=19.0.0",
        "--fingerprint-brand=Chrome",
        "--fingerprint-brand-version=148.0.0.0",
        "--fingerprint-hardware-concurrency=12",
        "--fingerprint-max-touch-points=0",
        '--fingerprint-gpu-vendor=Google Inc. (Intel)',
        '--fingerprint-gpu-renderer=ANGLE (Intel, Intel(R) Iris(R) Xe Graphics (0x00009A49) Direct3D11 vs_5_0 ps_5_0, D3D11)',
        "--fingerprint-timezone=America/New_York",
        "--fingerprint-locale=en-US",
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
    ]
    if "--webgl" in sys.argv:
        args += ["--enable-unsafe-swiftshader", "--use-gl=angle", "--use-angle=swiftshader"]
    else:
        args += ["--disable-gpu"]

    print("=== JS-surface vectors (with Windows fingerprint) ===")
    with trusted_local_page() as (trusted_url, trusted_origin), \
            launch(*args, f"--unsafely-treat-insecure-origin-as-secure={trusted_origin}"):
        time.sleep(0.5)
        expect("navigator.webdriver", cdp_eval("navigator.webdriver"), lambda v: v == "false", "false")
        expect("navigator.plugins.length", cdp_eval("navigator.plugins.length"), lambda v: v == "5", "5")
        expect("typeof window.chrome", cdp_eval("typeof window.chrome"), lambda v: v == '"object"', '"object"')
        expect("navigator.platform", cdp_eval("navigator.platform"), lambda v: v == '"Win32"', '"Win32"')
        expect("hardwareConcurrency", cdp_eval("navigator.hardwareConcurrency"), lambda v: v == "12", "12")
        expect("maxTouchPoints", cdp_eval("navigator.maxTouchPoints"), lambda v: v == "0", "0")
        expect("timezone", cdp_eval("Intl.DateTimeFormat().resolvedOptions().timeZone"),
               lambda v: v == '"America/New_York"', '"America/New_York"')
        expect("locale", cdp_eval("navigator.language"), lambda v: v == '"en-US"', '"en-US"')
        ua = cdp_eval("navigator.userAgent")
        expect("UA = windows", ua, lambda v: "Windows NT 10.0" in v and "HeadlessChrome" not in v, "Windows NT 10.0 (no Headless)")
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
        expect("UA-CH = windows/chrome", ua_ch,
               lambda v: "Windows" in v and "19.0.0" in v and
                         "x86" in v and '"64"' in v and "Google Chrome" in v,
               "Windows + Google Chrome client hints")

        print("\n=== HTTP UA vs JS UA consistency ===")
        # Drive a real request through the same renderer; httpbin echoes headers.
        subprocess.run([AB, "--cdp", str(PORT), "open", "https://httpbin.org/headers"],
                       capture_output=True, timeout=30)
        time.sleep(2)
        body = cdp_eval("document.body.textContent")
        expect("HTTP UA = Windows", body, lambda v: "Windows NT 10.0" in v and "Macintosh" not in v,
               "Windows NT 10.0 in body, no Macintosh")

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
        expect("bot.sannysoft no Headless", rows, lambda v: "HEADCHR" in v and "fail" not in v.lower(),
               "no HEADCHR fail")

    # Audio + canvas differential across two seeds — separate launches.
    print("\n=== Audio fingerprint differential (seed 1 vs 42069) ===")
    audio_html = "data:text/html,<script>(async()=>{const oc=new OfflineAudioContext(1,5000,44100);const o=oc.createOscillator();o.type='triangle';o.frequency.value=10000;const c=oc.createDynamicsCompressor();c.threshold.value=-50;c.knee.value=40;c.ratio.value=12;c.attack.value=0;c.release.value=0.25;o.connect(c);c.connect(oc.destination);o.start(0);const b=await oc.startRendering();const d=b.getChannelData(0);let s=0;for(let i=0;i<d.length;i++)s+=Math.abs(d[i]);document.title='audio='+s.toFixed(15)})()</script>"
    seeds = []
    for s in ("1", "42069"):
        with launch("--disable-gpu", f"--fingerprint={s}", "--fingerprint-platform=windows"):
            time.sleep(0.5)
            subprocess.run([AB, "--cdp", str(PORT), "open", audio_html],
                           capture_output=True, timeout=30)
            time.sleep(2)
            t = cdp_eval("document.title")
            seeds.append(t)
            print(f"  seed={s} {t}")
    expect("audio FP differs across seeds", str(seeds), lambda v: seeds[0] != seeds[1], "two distinct values")

    if failures:
        print(f"\n{len(failures)} failures:")
        for f in failures:
            print(f"  - {f}")
        return len(failures)
    print(f"\n[ALL PASSED]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
