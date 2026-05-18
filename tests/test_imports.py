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


def test_default_args_have_client_hint_identity() -> None:
    from clarkbrowser import get_default_stealth_args
    args = get_default_stealth_args()
    assert "--fingerprint-brand=Chrome" in args
    assert any(a.startswith("--fingerprint-brand-version=") for a in args)


def test_version() -> None:
    from clarkbrowser import __version__
    assert isinstance(__version__, str)
    assert __version__.count(".") >= 1


def test_chromium_version() -> None:
    from clarkbrowser import get_chromium_version
    v = get_chromium_version()
    assert v.count(".") == 3  # major.minor.build.patch


def test_linux_binary_path_matches_tarball(monkeypatch) -> None:
    from clarkbrowser import config
    monkeypatch.setattr(config.platform, "system", lambda: "Linux")
    monkeypatch.setattr(config.platform, "machine", lambda: "x86_64")
    assert config.get_binary_path().name == "headless_shell"
