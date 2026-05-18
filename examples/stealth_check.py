# Copyright 2026 Clark Labs Inc.
# SPDX-License-Identifier: MIT

"""Smoke test confirming the patches are firing.

Runs the same checks the project's CI exercises. Useful for first-launch
sanity-check after `pip install clarkbrowser`.
"""
from __future__ import annotations

import json

from clarkbrowser import launch


CHECKS = {
    "navigator.webdriver === false": "navigator.webdriver",
    "navigator.plugins.length >= 5": "navigator.plugins.length",
    "typeof window.chrome === 'object'": "typeof window.chrome",
    "navigator.hardwareConcurrency": "navigator.hardwareConcurrency",
    "navigator.deviceMemory": "navigator.deviceMemory",
    "screen.colorDepth === 24": "screen.colorDepth",
    "WebGL renderer (UNMASKED_RENDERER_WEBGL)": """
        (() => {
            const c = document.createElement('canvas');
            const gl = c.getContext('webgl');
            const ext = gl.getExtension('WEBGL_debug_renderer_info');
            return gl.getParameter(ext.UNMASKED_RENDERER_WEBGL);
        })()
    """,
    "WebGL vendor (UNMASKED_VENDOR_WEBGL)": """
        (() => {
            const c = document.createElement('canvas');
            const gl = c.getContext('webgl');
            const ext = gl.getExtension('WEBGL_debug_renderer_info');
            return gl.getParameter(ext.UNMASKED_VENDOR_WEBGL);
        })()
    """,
    "Intl timezone": "Intl.DateTimeFormat().resolvedOptions().timeZone",
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
    browser = launch(args=["--fingerprint=42069"])
    page = browser.new_page()
    page.goto("about:blank")

    results = {}
    for name, expr in CHECKS.items():
        try:
            results[name] = page.evaluate(expr)
        except Exception as e:
            results[name] = f"ERROR: {e}"

    print(json.dumps(results, indent=2, default=str))
    browser.close()


if __name__ == "__main__":
    main()
