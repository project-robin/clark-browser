# Copyright 2026 Clark Labs Inc.
# SPDX-License-Identifier: MIT

"""Smoke tests that don't require the binary."""
from __future__ import annotations


def test_imports() -> None:
    import clarkbrowser  # noqa: F401
    from clarkbrowser import launch, launch_async, ensure_binary  # noqa: F401


def test_default_args_have_fingerprint() -> None:
    from clarkbrowser import get_default_stealth_args
    args = get_default_stealth_args()
    assert any(a.startswith("--fingerprint=") for a in args)


def test_version() -> None:
    from clarkbrowser import __version__
    assert isinstance(__version__, str)
    assert __version__.count(".") >= 1


def test_chromium_version() -> None:
    from clarkbrowser import get_chromium_version
    v = get_chromium_version()
    assert v.count(".") == 3  # major.minor.build.patch
