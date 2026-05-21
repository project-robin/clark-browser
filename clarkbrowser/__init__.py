# Copyright 2026 Clark Labs Inc.
# SPDX-License-Identifier: MIT

"""clark-browser — stealth Chromium for browser automation.

Drop-in replacement for playwright.chromium.launch() that uses our patched
Chromium binary with anti-fingerprinting compiled at the C++ source level.

Quick start:
    from clarkbrowser import launch

    browser = launch()
    page = browser.new_page()
    page.goto("https://bot.sannysoft.com")
    print(page.title())
    browser.close()

See README.md for the full --fingerprint-* CLI surface and detection-site
benchmarks.
"""
from __future__ import annotations

from ._version import __version__
from .browser import (
    launch,
    launch_async,
    launch_context,
    launch_context_async,
    launch_persistent_context,
    launch_persistent_context_async,
)
from .config import (
    DEFAULT_VIEWPORT,
    get_default_stealth_args,
    get_chromium_version,
)
from .download import ensure_binary, binary_info, clear_cache
from .hygiene import (
    LaunchHygieneFinding,
    apply_launch_hygiene,
    assess_launch_hygiene,
)
from .interaction import AsyncInteractionPacer, InteractionPacer

__all__ = [
    "__version__",
    "launch",
    "launch_async",
    "launch_context",
    "launch_context_async",
    "launch_persistent_context",
    "launch_persistent_context_async",
    "DEFAULT_VIEWPORT",
    "get_default_stealth_args",
    "get_chromium_version",
    "ensure_binary",
    "binary_info",
    "clear_cache",
    "LaunchHygieneFinding",
    "apply_launch_hygiene",
    "assess_launch_hygiene",
    "InteractionPacer",
    "AsyncInteractionPacer",
]
