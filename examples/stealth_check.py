# Copyright 2026 Clark Labs Inc.
# SPDX-License-Identifier: MIT

"""Smoke test confirming the main JS-visible patches are firing.

Useful for a first-launch sanity check after `pip install clark-browser`.
Prints a JSON report and exits non-zero if a core check fails.
"""
from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from clarkbrowser import launch


CORE_CHECKS: dict[str, tuple[str, Callable[[Any], bool], str]] = {
    "navigator.webdriver": (
        "navigator.webdriver",
        lambda value: value is False,
        "false",
    ),
    "navigator.plugins.length": (
        "navigator.plugins.length",
        lambda value: isinstance(value, int) and value >= 5,
        ">= 5",
    ),
    "typeof window.chrome": (
        "typeof window.chrome",
        lambda value: value == "object",
        '"object"',
    ),
    "navigator.userAgent": (
        "navigator.userAgent",
        lambda value: isinstance(value, str) and "HeadlessChrome" not in value,
        "no HeadlessChrome token",
    ),
    "screen.colorDepth": (
        "screen.colorDepth",
        lambda value: value == 24,
        "24",
    ),
}


SIGNALS = {
    "navigator.hardwareConcurrency": "navigator.hardwareConcurrency",
    "navigator.deviceMemory": "navigator.deviceMemory",
    "navigator.platform": "navigator.platform",
    "navigator.languages": "Array.from(navigator.languages || [])",
    "Intl timezone": "Intl.DateTimeFormat().resolvedOptions().timeZone",
    "Network Information": """
        (() => {
            const c = navigator.connection;
            if (!c) return null;
            return {
                effectiveType: c.effectiveType,
                rtt: c.rtt,
                downlink: c.downlink,
                saveData: c.saveData,
            };
        })()
    """,
    "WebGL renderer (UNMASKED_RENDERER_WEBGL)": """
        (() => {
            const c = document.createElement('canvas');
            const gl = c.getContext('webgl');
            if (!gl) return null;
            const ext = gl.getExtension('WEBGL_debug_renderer_info');
            if (!ext) return null;
            return gl.getParameter(ext.UNMASKED_RENDERER_WEBGL);
        })()
    """,
    "WebGL vendor (UNMASKED_VENDOR_WEBGL)": """
        (() => {
            const c = document.createElement('canvas');
            const gl = c.getContext('webgl');
            if (!gl) return null;
            const ext = gl.getExtension('WEBGL_debug_renderer_info');
            if (!ext) return null;
            return gl.getParameter(ext.UNMASKED_VENDOR_WEBGL);
        })()
    """,
    "WebGPU profile": """
        (async () => {
            if (!navigator.gpu) {
                return {supported: false, reason: 'navigator.gpu absent'};
            }
            const adapter = await navigator.gpu.requestAdapter();
            if (!adapter) {
                return {supported: false, reason: 'requestAdapter null'};
            }
            const info = adapter.info || (
                adapter.requestAdapterInfo ? await adapter.requestAdapterInfo() : {});
            return {
                supported: true,
                vendor: info.vendor || '',
                architecture: info.architecture || '',
                device: info.device || '',
                description: info.description || '',
            };
        })()
    """,
    "UA Client Hints": """
        (async () => {
            if (!navigator.userAgentData) return null;
            const high = await navigator.userAgentData.getHighEntropyValues([
                'platform', 'platformVersion', 'architecture', 'bitness',
                'fullVersionList'
            ]);
            return {
                brands: navigator.userAgentData.brands,
                platform: high.platform,
                platformVersion: high.platformVersion,
                architecture: high.architecture,
                bitness: high.bitness,
                fullVersionList: high.fullVersionList,
            };
        })()
    """,
}


def main() -> None:
    browser = launch(
        args=["--fingerprint=42069"],
        timezone="America/Los_Angeles",
        locale="en-US",
        network_profile="datacenter",
    )
    try:
        page = browser.new_page()
        page.goto("about:blank")

        checks: dict[str, dict[str, Any]] = {}
        failures = []
        for name, (expr, predicate, expected) in CORE_CHECKS.items():
            try:
                value = page.evaluate(expr)
            except Exception as e:
                value = f"ERROR: {e}"
            ok = predicate(value)
            checks[name] = {"ok": ok, "value": value, "expected": expected}
            if not ok:
                failures.append(name)

        signals = {}
        for name, expr in SIGNALS.items():
            try:
                signals[name] = page.evaluate(expr)
            except Exception as e:
                signals[name] = f"ERROR: {e}"

        report = {"checks": checks, "signals": signals}
        print(json.dumps(report, indent=2, default=str))
        if failures:
            raise SystemExit(f"failed checks: {', '.join(failures)}")
    finally:
        browser.close()


if __name__ == "__main__":
    main()
