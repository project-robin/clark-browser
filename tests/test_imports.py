# Copyright 2026 Clark Labs Inc.
# SPDX-License-Identifier: MIT

"""Smoke tests that don't require the binary."""
from __future__ import annotations


def test_imports() -> None:
    import clarkbrowser  # noqa: F401
    from clarkbrowser import (  # noqa: F401
        InteractionPacer,
        assess_launch_hygiene,
        ensure_binary,
        launch,
        launch_async,
    )


def test_default_args_have_fingerprint(monkeypatch) -> None:
    from clarkbrowser import get_default_stealth_args
    monkeypatch.delenv("CLARK_FINGERPRINT_PLATFORM", raising=False)
    monkeypatch.delenv("CLARK_FINGERPRINT_FONTS_DIR", raising=False)
    monkeypatch.delenv("CLARK_WINDOWS_FONTS_DIR", raising=False)
    monkeypatch.delenv("CLARK_FINGERPRINT_NETWORK_PROFILE", raising=False)
    monkeypatch.delenv("CLARK_WEBRTC_POLICY", raising=False)
    args = get_default_stealth_args()
    assert any(a.startswith("--fingerprint=") for a in args)


def test_default_args_have_client_hint_identity(monkeypatch) -> None:
    from clarkbrowser import get_default_stealth_args
    monkeypatch.delenv("CLARK_FINGERPRINT_PLATFORM", raising=False)
    monkeypatch.delenv("CLARK_FINGERPRINT_FONTS_DIR", raising=False)
    monkeypatch.delenv("CLARK_WINDOWS_FONTS_DIR", raising=False)
    monkeypatch.delenv("CLARK_FINGERPRINT_NETWORK_PROFILE", raising=False)
    args = get_default_stealth_args()
    assert "--fingerprint-brand=Chrome" in args
    assert any(a.startswith("--fingerprint-brand-version=") for a in args)


def test_linux_default_profile_matches_linux_fonts(monkeypatch) -> None:
    from clarkbrowser import config
    monkeypatch.setattr(config.platform, "system", lambda: "Linux")
    monkeypatch.delenv("CLARK_FINGERPRINT_PLATFORM", raising=False)
    monkeypatch.delenv("CLARK_FINGERPRINT_FONTS_DIR", raising=False)
    monkeypatch.delenv("CLARK_WINDOWS_FONTS_DIR", raising=False)
    monkeypatch.delenv("CLARK_FINGERPRINT_NETWORK_PROFILE", raising=False)

    args = config.get_default_stealth_args()

    assert "--fingerprint-platform=linux" in args
    assert any("X11; Linux x86_64" in a for a in args)
    assert not any(a.startswith("--fingerprint-platform-version=") for a in args)
    assert not any(a.startswith("--fingerprint-fonts-dir=") for a in args)


def test_linux_windows_profile_requires_font_pack(monkeypatch) -> None:
    from clarkbrowser import config
    monkeypatch.setattr(config.platform, "system", lambda: "Linux")
    monkeypatch.delenv("CLARK_FINGERPRINT_PLATFORM", raising=False)
    monkeypatch.delenv("CLARK_FINGERPRINT_FONTS_DIR", raising=False)
    monkeypatch.setenv("CLARK_WINDOWS_FONTS_DIR", "/opt/clark/fonts/windows")
    monkeypatch.delenv("CLARK_FINGERPRINT_NETWORK_PROFILE", raising=False)

    args = config.get_default_stealth_args()

    assert "--fingerprint-platform=windows" in args
    assert "--fingerprint-platform-version=19.0.0" in args
    assert "--fingerprint-fonts-dir=/opt/clark/fonts/windows" in args
    assert any("Windows NT 10.0" in a for a in args)


def test_fingerprint_platform_env_overrides_default(monkeypatch) -> None:
    from clarkbrowser import config
    monkeypatch.setattr(config.platform, "system", lambda: "Linux")
    monkeypatch.setenv("CLARK_FINGERPRINT_PLATFORM", "windows")
    monkeypatch.setenv("CLARK_FINGERPRINT_FONTS_DIR", "/profiles/win-fonts")
    monkeypatch.delenv("CLARK_WINDOWS_FONTS_DIR", raising=False)
    monkeypatch.delenv("CLARK_FINGERPRINT_NETWORK_PROFILE", raising=False)

    args = config.get_default_stealth_args()

    assert "--fingerprint-platform=windows" in args
    assert "--fingerprint-fonts-dir=/profiles/win-fonts" in args


def test_windows_profile_without_fonts_is_rejected(monkeypatch) -> None:
    import pytest
    from clarkbrowser import config
    monkeypatch.setattr(config.platform, "system", lambda: "Linux")
    monkeypatch.setenv("CLARK_FINGERPRINT_PLATFORM", "windows")
    monkeypatch.delenv("CLARK_FINGERPRINT_FONTS_DIR", raising=False)
    monkeypatch.delenv("CLARK_WINDOWS_FONTS_DIR", raising=False)
    monkeypatch.delenv("CLARK_FINGERPRINT_NETWORK_PROFILE", raising=False)

    with pytest.raises(RuntimeError, match="Windows fingerprint profiles require"):
        config.get_default_stealth_args()


def test_user_platform_override_rewrites_matched_identity(monkeypatch) -> None:
    from clarkbrowser import browser, config
    monkeypatch.setattr(config.platform, "system", lambda: "Linux")
    monkeypatch.setattr(browser.host_platform, "system", lambda: "Linux")
    monkeypatch.delenv("CLARK_FINGERPRINT_PLATFORM", raising=False)
    monkeypatch.delenv("CLARK_FINGERPRINT_FONTS_DIR", raising=False)
    monkeypatch.delenv("CLARK_WINDOWS_FONTS_DIR", raising=False)
    monkeypatch.delenv("CLARK_FINGERPRINT_NETWORK_PROFILE", raising=False)

    args = browser._resolve_args(
        ["--fingerprint-platform=windows", "--fingerprint-fonts-dir=/fonts/win"],
        True,
        None,
        None,
        None,
        None,
        None,
        True,
    )

    assert "--fingerprint-platform=windows" in args
    assert "--fingerprint-platform-version=19.0.0" in args
    assert "--fingerprint-fonts-dir=/fonts/win" in args
    assert any("Windows NT 10.0" in a for a in args)
    assert not any("X11; Linux x86_64" in a for a in args)


def test_user_windows_platform_without_fonts_is_rejected(monkeypatch) -> None:
    import pytest
    from clarkbrowser import browser, config
    monkeypatch.setattr(config.platform, "system", lambda: "Linux")
    monkeypatch.setattr(browser.host_platform, "system", lambda: "Linux")
    monkeypatch.delenv("CLARK_FINGERPRINT_PLATFORM", raising=False)
    monkeypatch.delenv("CLARK_FINGERPRINT_FONTS_DIR", raising=False)
    monkeypatch.delenv("CLARK_WINDOWS_FONTS_DIR", raising=False)
    monkeypatch.delenv("CLARK_FINGERPRINT_NETWORK_PROFILE", raising=False)
    monkeypatch.delenv("CLARK_WEBRTC_POLICY", raising=False)

    with pytest.raises(RuntimeError, match="Windows fingerprint profiles require"):
        browser._resolve_args(
            ["--fingerprint-platform=windows"],
            True,
            None,
            None,
            None,
            None,
            None,
            True,
        )


def test_network_profile_env_adds_default_arg(monkeypatch) -> None:
    from clarkbrowser import config
    monkeypatch.setattr(config.platform, "system", lambda: "Linux")
    monkeypatch.delenv("CLARK_FINGERPRINT_PLATFORM", raising=False)
    monkeypatch.delenv("CLARK_FINGERPRINT_FONTS_DIR", raising=False)
    monkeypatch.delenv("CLARK_WINDOWS_FONTS_DIR", raising=False)
    monkeypatch.setenv("CLARK_FINGERPRINT_NETWORK_PROFILE", "mobile")
    monkeypatch.delenv("CLARK_WEBRTC_POLICY", raising=False)

    args = config.get_default_stealth_args()

    assert "--fingerprint-network-profile=mobile" in args


def test_network_profile_launch_param_overrides_env(monkeypatch) -> None:
    from clarkbrowser import browser, config
    monkeypatch.setattr(config.platform, "system", lambda: "Linux")
    monkeypatch.delenv("CLARK_FINGERPRINT_PLATFORM", raising=False)
    monkeypatch.delenv("CLARK_FINGERPRINT_FONTS_DIR", raising=False)
    monkeypatch.delenv("CLARK_WINDOWS_FONTS_DIR", raising=False)
    monkeypatch.setenv("CLARK_FINGERPRINT_NETWORK_PROFILE", "mobile")
    monkeypatch.delenv("CLARK_WEBRTC_POLICY", raising=False)

    args = browser._resolve_args(
        [], True, None, None, "datacenter", None, None, True
    )

    assert "--fingerprint-network-profile=datacenter" in args
    assert "--fingerprint-network-profile=mobile" not in args


def test_webrtc_proxy_coherent_policy_adds_chromium_arg(monkeypatch) -> None:
    from clarkbrowser import browser, config
    monkeypatch.setattr(config.platform, "system", lambda: "Linux")
    monkeypatch.delenv("CLARK_FINGERPRINT_PLATFORM", raising=False)
    monkeypatch.delenv("CLARK_FINGERPRINT_FONTS_DIR", raising=False)
    monkeypatch.delenv("CLARK_WINDOWS_FONTS_DIR", raising=False)
    monkeypatch.delenv("CLARK_FINGERPRINT_NETWORK_PROFILE", raising=False)
    monkeypatch.delenv("CLARK_WEBRTC_POLICY", raising=False)

    args = browser._resolve_args(
        [], True, None, None, None, "proxy-coherent", None, True
    )

    assert "--force-webrtc-ip-handling-policy=disable_non_proxied_udp" in args


def test_webrtc_policy_env_is_opt_in(monkeypatch) -> None:
    from clarkbrowser import browser, config
    monkeypatch.setattr(config.platform, "system", lambda: "Linux")
    monkeypatch.delenv("CLARK_FINGERPRINT_PLATFORM", raising=False)
    monkeypatch.delenv("CLARK_FINGERPRINT_FONTS_DIR", raising=False)
    monkeypatch.delenv("CLARK_WINDOWS_FONTS_DIR", raising=False)
    monkeypatch.delenv("CLARK_FINGERPRINT_NETWORK_PROFILE", raising=False)
    monkeypatch.delenv("CLARK_WEBRTC_POLICY", raising=False)

    args = browser._resolve_args([], True, None, None, None, None, None, True)

    assert not any(
        a.startswith("--force-webrtc-ip-handling-policy=") for a in args
    )


def test_webrtc_policy_env_adds_proxy_coherent_arg(monkeypatch) -> None:
    from clarkbrowser import browser, config
    monkeypatch.setattr(config.platform, "system", lambda: "Linux")
    monkeypatch.delenv("CLARK_FINGERPRINT_PLATFORM", raising=False)
    monkeypatch.delenv("CLARK_FINGERPRINT_FONTS_DIR", raising=False)
    monkeypatch.delenv("CLARK_WINDOWS_FONTS_DIR", raising=False)
    monkeypatch.delenv("CLARK_FINGERPRINT_NETWORK_PROFILE", raising=False)
    monkeypatch.setenv("CLARK_WEBRTC_POLICY", "proxy-coherent")

    args = browser._resolve_args([], True, None, None, None, None, None, True)

    assert "--force-webrtc-ip-handling-policy=disable_non_proxied_udp" in args


def test_user_webrtc_policy_arg_wins(monkeypatch) -> None:
    from clarkbrowser import browser, config
    monkeypatch.setattr(config.platform, "system", lambda: "Linux")
    monkeypatch.delenv("CLARK_FINGERPRINT_PLATFORM", raising=False)
    monkeypatch.delenv("CLARK_FINGERPRINT_FONTS_DIR", raising=False)
    monkeypatch.delenv("CLARK_WINDOWS_FONTS_DIR", raising=False)
    monkeypatch.delenv("CLARK_FINGERPRINT_NETWORK_PROFILE", raising=False)
    monkeypatch.setenv("CLARK_WEBRTC_POLICY", "proxy-coherent")

    args = browser._resolve_args(
        ["--force-webrtc-ip-handling-policy=default"],
        True,
        None,
        None,
        None,
        None,
        None,
        True,
    )

    assert "--force-webrtc-ip-handling-policy=default" in args
    assert "--force-webrtc-ip-handling-policy=disable_non_proxied_udp" not in args


def test_invalid_webrtc_policy_is_rejected(monkeypatch) -> None:
    import pytest
    from clarkbrowser import browser, config
    monkeypatch.setattr(config.platform, "system", lambda: "Linux")
    monkeypatch.delenv("CLARK_FINGERPRINT_PLATFORM", raising=False)
    monkeypatch.delenv("CLARK_FINGERPRINT_FONTS_DIR", raising=False)
    monkeypatch.delenv("CLARK_WINDOWS_FONTS_DIR", raising=False)
    monkeypatch.delenv("CLARK_FINGERPRINT_NETWORK_PROFILE", raising=False)
    monkeypatch.delenv("CLARK_WEBRTC_POLICY", raising=False)

    with pytest.raises(RuntimeError, match="Unsupported WebRTC policy"):
        browser._resolve_args([], True, None, None, None, "leaky", None, True)


def test_headless_webgpu_defaults_to_deliberately_disabled(monkeypatch) -> None:
    from clarkbrowser import browser, config
    monkeypatch.setattr(config.platform, "system", lambda: "Linux")
    monkeypatch.delenv("CLARK_FINGERPRINT_PLATFORM", raising=False)
    monkeypatch.delenv("CLARK_FINGERPRINT_FONTS_DIR", raising=False)
    monkeypatch.delenv("CLARK_WINDOWS_FONTS_DIR", raising=False)
    monkeypatch.delenv("CLARK_FINGERPRINT_NETWORK_PROFILE", raising=False)
    monkeypatch.delenv("CLARK_WEBGPU_POLICY", raising=False)

    args = browser._resolve_args([], True, None, None, None, None, None, True)

    assert "--disable-features=WebGPU" in args


def test_headed_webgpu_default_does_not_disable(monkeypatch) -> None:
    from clarkbrowser import browser, config
    monkeypatch.setattr(config.platform, "system", lambda: "Linux")
    monkeypatch.delenv("CLARK_FINGERPRINT_PLATFORM", raising=False)
    monkeypatch.delenv("CLARK_FINGERPRINT_FONTS_DIR", raising=False)
    monkeypatch.delenv("CLARK_WINDOWS_FONTS_DIR", raising=False)
    monkeypatch.delenv("CLARK_FINGERPRINT_NETWORK_PROFILE", raising=False)
    monkeypatch.delenv("CLARK_WEBGPU_POLICY", raising=False)

    args = browser._resolve_args([], True, None, None, None, None, None, False)

    assert "--disable-features=WebGPU" not in args


def test_webgpu_default_respects_stealth_args_false(monkeypatch) -> None:
    from clarkbrowser import browser, config
    monkeypatch.setattr(config.platform, "system", lambda: "Linux")
    monkeypatch.delenv("CLARK_FINGERPRINT_PLATFORM", raising=False)
    monkeypatch.delenv("CLARK_FINGERPRINT_FONTS_DIR", raising=False)
    monkeypatch.delenv("CLARK_WINDOWS_FONTS_DIR", raising=False)
    monkeypatch.delenv("CLARK_FINGERPRINT_NETWORK_PROFILE", raising=False)
    monkeypatch.delenv("CLARK_WEBGPU_POLICY", raising=False)

    args = browser._resolve_args([], False, None, None, None, None, None, True)

    assert "--disable-features=WebGPU" not in args


def test_webgpu_coherent_policy_keeps_webgpu_available(monkeypatch) -> None:
    from clarkbrowser import browser, config
    monkeypatch.setattr(config.platform, "system", lambda: "Linux")
    monkeypatch.delenv("CLARK_FINGERPRINT_PLATFORM", raising=False)
    monkeypatch.delenv("CLARK_FINGERPRINT_FONTS_DIR", raising=False)
    monkeypatch.delenv("CLARK_WINDOWS_FONTS_DIR", raising=False)
    monkeypatch.delenv("CLARK_FINGERPRINT_NETWORK_PROFILE", raising=False)
    monkeypatch.setenv("CLARK_WEBGPU_POLICY", "coherent")

    args = browser._resolve_args([], True, None, None, None, None, None, True)

    assert "--disable-features=WebGPU" not in args


def test_user_webgpu_feature_arg_wins(monkeypatch) -> None:
    from clarkbrowser import browser, config
    monkeypatch.setattr(config.platform, "system", lambda: "Linux")
    monkeypatch.delenv("CLARK_FINGERPRINT_PLATFORM", raising=False)
    monkeypatch.delenv("CLARK_FINGERPRINT_FONTS_DIR", raising=False)
    monkeypatch.delenv("CLARK_WINDOWS_FONTS_DIR", raising=False)
    monkeypatch.delenv("CLARK_FINGERPRINT_NETWORK_PROFILE", raising=False)
    monkeypatch.setenv("CLARK_WEBGPU_POLICY", "disabled")

    args = browser._resolve_args(
        ["--enable-features=WebGPU"], True, None, None, None, None, None, True
    )

    assert "--enable-features=WebGPU" in args
    assert "--disable-features=WebGPU" not in args


def test_webgpu_disabled_policy_merges_disable_features(monkeypatch) -> None:
    from clarkbrowser import browser, config
    monkeypatch.setattr(config.platform, "system", lambda: "Linux")
    monkeypatch.delenv("CLARK_FINGERPRINT_PLATFORM", raising=False)
    monkeypatch.delenv("CLARK_FINGERPRINT_FONTS_DIR", raising=False)
    monkeypatch.delenv("CLARK_WINDOWS_FONTS_DIR", raising=False)
    monkeypatch.delenv("CLARK_FINGERPRINT_NETWORK_PROFILE", raising=False)
    monkeypatch.delenv("CLARK_WEBGPU_POLICY", raising=False)

    args = browser._resolve_args(
        ["--disable-features=Foo"], True, None, None, None, None, "disabled", True
    )

    assert "--disable-features=Foo,WebGPU" in args


def test_invalid_webgpu_policy_is_rejected(monkeypatch) -> None:
    import pytest
    from clarkbrowser import browser, config
    monkeypatch.setattr(config.platform, "system", lambda: "Linux")
    monkeypatch.delenv("CLARK_FINGERPRINT_PLATFORM", raising=False)
    monkeypatch.delenv("CLARK_FINGERPRINT_FONTS_DIR", raising=False)
    monkeypatch.delenv("CLARK_WINDOWS_FONTS_DIR", raising=False)
    monkeypatch.delenv("CLARK_FINGERPRINT_NETWORK_PROFILE", raising=False)
    monkeypatch.delenv("CLARK_WEBGPU_POLICY", raising=False)

    with pytest.raises(RuntimeError, match="Unsupported WebGPU policy"):
        browser._resolve_args([], True, None, None, None, None, "leaky", True)


def test_launch_hygiene_flags_devtools_and_public_cdp() -> None:
    from clarkbrowser import assess_launch_hygiene

    findings = assess_launch_hygiene(
        [
            "--enable-automation",
            "--remote-debugging-port=9222",
            "--remote-debugging-address=0.0.0.0",
            "--remote-allow-origins=*",
        ],
        {"devtools": True},
    )

    codes = {finding.code for finding in findings}
    assert "enable-automation" in codes
    assert "devtools-kwarg" in codes
    assert "remote-debugging-public-address" in codes
    assert "remote-allow-origins-wildcard" in codes


def test_launch_hygiene_strict_policy_rejects_findings(monkeypatch) -> None:
    import pytest
    from clarkbrowser.hygiene import apply_launch_hygiene

    class Logger:
        def warning(self, *args) -> None:
            raise AssertionError("strict policy should raise before warning")

    monkeypatch.setenv("CLARK_LAUNCH_HYGIENE", "strict")

    with pytest.raises(RuntimeError, match="Clark launch hygiene failed"):
        apply_launch_hygiene(Logger(), ["--enable-automation"], {})


def test_launch_hygiene_off_policy_suppresses_findings(monkeypatch) -> None:
    from clarkbrowser.hygiene import apply_launch_hygiene

    class Logger:
        def warning(self, *args) -> None:
            raise AssertionError("off policy should not warn")

    monkeypatch.setenv("CLARK_LAUNCH_HYGIENE", "off")

    assert apply_launch_hygiene(Logger(), ["--enable-automation"], {}) == []


def test_interaction_pacer_enforces_min_interval() -> None:
    from clarkbrowser import InteractionPacer

    now = 0.0
    slept: list[float] = []

    def clock() -> float:
        return now

    def sleep(seconds: float) -> None:
        nonlocal now
        slept.append(seconds)
        now += seconds

    pacer = InteractionPacer(
        min_interval_ms=250,
        jitter_ms=0,
        same_target_cooldown_ms=0,
        now_fn=clock,
        sleep_fn=sleep,
    )

    assert pacer.wait("first") == 0
    assert pacer.wait("second") == 0.25
    assert slept == [0.25]


def test_interaction_pacer_same_target_cooldown_wins() -> None:
    from clarkbrowser import InteractionPacer

    now = 0.0
    slept: list[float] = []

    def clock() -> float:
        return now

    def sleep(seconds: float) -> None:
        nonlocal now
        slept.append(seconds)
        now += seconds

    pacer = InteractionPacer(
        min_interval_ms=100,
        jitter_ms=0,
        same_target_cooldown_ms=600,
        now_fn=clock,
        sleep_fn=sleep,
    )

    pacer.wait("button")
    assert pacer.wait("button") == 0.6
    assert slept == [0.6]


def test_version() -> None:
    from clarkbrowser import __version__
    assert isinstance(__version__, str)
    assert __version__.count(".") >= 1


def test_chromium_version() -> None:
    from clarkbrowser import get_chromium_version
    v = get_chromium_version()
    assert v.count(".") == 3  # major.minor.build.patch


def test_download_url_uses_current_stealth_release(monkeypatch) -> None:
    from clarkbrowser import config
    monkeypatch.setattr(config.platform, "system", lambda: "Linux")
    monkeypatch.setattr(config.platform, "machine", lambda: "x86_64")
    assert (
        config.get_download_url()
        == "https://github.com/clark-labs-inc/clark-browser/releases/download/"
        "chromium-v148.0.7778.96-stealth3/clark-browser-linux-x64.tar.gz"
    )


def test_linux_binary_path_prefers_chrome_tarball(monkeypatch) -> None:
    from clarkbrowser import config
    monkeypatch.setattr(config.platform, "system", lambda: "Linux")
    monkeypatch.setattr(config.platform, "machine", lambda: "x86_64")
    assert config.get_binary_path().name == "chrome"


def test_linux_binary_path_keeps_headless_fallback(monkeypatch, tmp_path) -> None:
    from clarkbrowser import config
    monkeypatch.setattr(config.platform, "system", lambda: "Linux")
    monkeypatch.setattr(config.platform, "machine", lambda: "x86_64")
    monkeypatch.setenv("CLARK_CACHE_DIR", str(tmp_path))
    binary_dir = config.get_binary_dir()
    binary_dir.mkdir(parents=True)
    (binary_dir / "headless_shell").touch()
    assert config.get_binary_path().name == "headless_shell"
