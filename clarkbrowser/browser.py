# Copyright 2026 Clark Labs Inc.
# SPDX-License-Identifier: MIT

"""Core launch functions for clark-browser.

Thin wrapper around Playwright that uses the patched Chromium binary.
"""
from __future__ import annotations

import logging
import os
import platform as host_platform
from typing import Any, Literal, TypedDict

from .config import (
    DEFAULT_VIEWPORT,
    FINGERPRINT_FONTS_DIR_ENV,
    FINGERPRINT_PLATFORM_ENV,
    IGNORE_DEFAULT_ARGS,
    NETWORK_PROFILES,
    PLATFORM_CLIENT_HINT_VERSIONS,
    PLATFORM_USER_AGENTS,
    WEBGPU_DISABLE_FEATURE_SWITCH,
    WEBGPU_ENABLE_FEATURE_SWITCH,
    WEBGPU_FEATURE_NAME,
    WEBGPU_UNSAFE_ENABLE_SWITCH,
    WEBRTC_FORCE_IP_HANDLING_SWITCH,
    WEBRTC_IP_HANDLING_POLICY_SWITCH,
    WEBRTC_POLICY_ENV,
    WEBRTC_PROXY_COHERENT_POLICY,
    WINDOWS_FONTS_DIR_ENV,
    FINGERPRINT_FONTS_DIR_SWITCH,
    get_default_stealth_args,
    get_fingerprint_fonts_dir,
    get_fontconfig_env_for_args,
    get_fingerprint_network_profile,
    get_viewport_from_args,
    normalize_webgpu_policy,
    normalize_webrtc_policy,
    validate_fingerprint_fonts_dir,
)
from .download import ensure_binary
from .hygiene import apply_launch_hygiene

logger = logging.getLogger("clarkbrowser")

# Sentinel — distinguish "not provided" from "explicitly None".
_VIEWPORT_UNSET = object()


class _ProxySettingsRequired(TypedDict):
    server: str


class ProxySettings(_ProxySettingsRequired, total=False):
    bypass: str
    username: str
    password: str


def _resolve_args(
    user_args: list[str] | None,
    stealth_args: bool,
    timezone: str | None,
    locale: str | None,
    network_profile: str | None,
    webrtc_policy: str | None,
    webgpu_policy: str | None,
    headless: bool,
    proxy: str | ProxySettings | None = None,
) -> list[str]:
    """Merge stealth defaults + user args + dedicated params."""
    seen: dict[str, str] = {}
    user_keys: set[str] = set()

    if stealth_args:
        for a in get_default_stealth_args():
            seen[a.split("=", 1)[0]] = a

    if user_args:
        for a in user_args:
            key = a.split("=", 1)[0]
            seen[key] = a
            user_keys.add(key)

    if timezone:
        seen["--fingerprint-timezone"] = f"--fingerprint-timezone={timezone}"
    if locale:
        seen["--lang"] = f"--lang={locale}"
        seen["--fingerprint-locale"] = f"--fingerprint-locale={locale}"
    if network_profile:
        network_profile = network_profile.lower()
        if network_profile not in NETWORK_PROFILES:
            raise RuntimeError(
                f"Unsupported network_profile={network_profile!r}. "
                f"Supported: {', '.join(sorted(NETWORK_PROFILES))}"
            )
        seen["--fingerprint-network-profile"] = (
            f"--fingerprint-network-profile={network_profile}"
        )
    _cohere_webrtc_policy_args(seen, webrtc_policy, proxy)
    _cohere_webgpu_policy_args(seen, webgpu_policy, headless, stealth_args)

    if stealth_args:
        _cohere_platform_args(seen, user_keys)
        _cohere_network_args(seen)

    return list(seen.values())


def _arg_value(args: dict[str, str], key: str) -> str | None:
    arg = args.get(key)
    if not arg or "=" not in arg:
        return None
    return arg.split("=", 1)[1]


def _cohere_platform_args(args: dict[str, str], user_keys: set[str]) -> None:
    fp_platform = _arg_value(args, "--fingerprint-platform")
    if fp_platform not in PLATFORM_USER_AGENTS:
        return

    if "--user-agent" not in user_keys:
        args["--user-agent"] = f"--user-agent={PLATFORM_USER_AGENTS[fp_platform]}"

    if "--fingerprint-platform-version" not in user_keys:
        version = PLATFORM_CLIENT_HINT_VERSIONS[fp_platform]
        if version:
            args["--fingerprint-platform-version"] = (
                f"--fingerprint-platform-version={version}"
            )
        else:
            args.pop("--fingerprint-platform-version", None)

    if "--fingerprint-fonts-dir" not in user_keys:
        fonts_dir = get_fingerprint_fonts_dir(fp_platform)
        if fonts_dir:
            args["--fingerprint-fonts-dir"] = f"--fingerprint-fonts-dir={fonts_dir}"
    else:
        fonts_dir = _arg_value(args, FINGERPRINT_FONTS_DIR_SWITCH)
        if fonts_dir:
            args[FINGERPRINT_FONTS_DIR_SWITCH] = (
                f"{FINGERPRINT_FONTS_DIR_SWITCH}="
                f"{validate_fingerprint_fonts_dir(fonts_dir, fp_platform)}"
            )

    if (
        fp_platform == "windows"
        and host_platform.system() != "Windows"
        and FINGERPRINT_FONTS_DIR_SWITCH not in args
    ):
        raise RuntimeError(
            "Windows fingerprint profiles require a configured font directory "
            f"on this host. Set {WINDOWS_FONTS_DIR_ENV}, "
            f"{FINGERPRINT_FONTS_DIR_ENV}, or pass "
            "--fingerprint-fonts-dir. Use "
            f"{FINGERPRINT_PLATFORM_ENV}=linux for the default Linux profile."
        )


def _cohere_browser_env(args: list[str], kwargs: dict[str, Any]) -> dict[str, Any]:
    font_env = get_fontconfig_env_for_args(args)
    if not font_env:
        return kwargs

    launch_kwargs = dict(kwargs)
    user_env = launch_kwargs.get("env")
    env = os.environ.copy()
    env.update(font_env)
    if user_env:
        env.update(user_env)
    launch_kwargs["env"] = env
    return launch_kwargs


def _cohere_network_args(args: dict[str, str]) -> None:
    if "--fingerprint-network-profile" in args:
        return
    profile = get_fingerprint_network_profile()
    if profile:
        args["--fingerprint-network-profile"] = (
            f"--fingerprint-network-profile={profile}"
        )


def _cohere_webrtc_policy_args(
    args: dict[str, str],
    webrtc_policy: str | None,
    proxy: str | ProxySettings | None = None,
) -> None:
    if (
        WEBRTC_FORCE_IP_HANDLING_SWITCH in args
        or WEBRTC_IP_HANDLING_POLICY_SWITCH in args
    ):
        return

    policy = normalize_webrtc_policy(webrtc_policy)
    if policy:
        args[WEBRTC_FORCE_IP_HANDLING_SWITCH] = (
            f"{WEBRTC_FORCE_IP_HANDLING_SWITCH}={policy}"
        )
        args[WEBRTC_IP_HANDLING_POLICY_SWITCH] = (
            f"{WEBRTC_IP_HANDLING_POLICY_SWITCH}={policy}"
        )
        return

    # No explicit policy from param or env. When a proxy is configured,
    # default to proxy-coherent so WebRTC does not leak the host IP outside
    # the proxy tunnel — a common bot-detection signal.
    if proxy and not os.environ.get(WEBRTC_POLICY_ENV):
        args[WEBRTC_FORCE_IP_HANDLING_SWITCH] = (
            f"{WEBRTC_FORCE_IP_HANDLING_SWITCH}={WEBRTC_PROXY_COHERENT_POLICY}"
        )
        args[WEBRTC_IP_HANDLING_POLICY_SWITCH] = (
            f"{WEBRTC_IP_HANDLING_POLICY_SWITCH}={WEBRTC_PROXY_COHERENT_POLICY}"
        )


def _feature_switch_has(args: dict[str, str], switch: str, feature: str) -> bool:
    value = _arg_value(args, switch)
    if not value:
        return False
    return feature.lower() in {item.strip().lower() for item in value.split(",")}


def _append_feature(args: dict[str, str], switch: str, feature: str) -> None:
    value = _arg_value(args, switch)
    if not value:
        args[switch] = f"{switch}={feature}"
        return
    features = [item.strip() for item in value.split(",") if item.strip()]
    if feature.lower() not in {item.lower() for item in features}:
        features.append(feature)
    args[switch] = f"{switch}={','.join(features)}"


def _cohere_webgpu_policy_args(
    args: dict[str, str],
    webgpu_policy: str | None,
    headless: bool,
    stealth_args: bool,
) -> None:
    if (
        WEBGPU_UNSAFE_ENABLE_SWITCH in args
        or _feature_switch_has(args, WEBGPU_ENABLE_FEATURE_SWITCH, WEBGPU_FEATURE_NAME)
        or _feature_switch_has(args, WEBGPU_DISABLE_FEATURE_SWITCH, WEBGPU_FEATURE_NAME)
    ):
        return

    policy = normalize_webgpu_policy(webgpu_policy)
    if policy is None and not stealth_args:
        return
    if policy is None:
        policy = "headless-off"

    if policy == "disabled" or (policy == "headless-off" and headless):
        _append_feature(args, WEBGPU_DISABLE_FEATURE_SWITCH, WEBGPU_FEATURE_NAME)


def _import_sync_playwright():
    from playwright.sync_api import sync_playwright
    return sync_playwright


def _import_async_playwright():
    from playwright.async_api import async_playwright
    return async_playwright


def launch(
    headless: bool = True,
    proxy: str | ProxySettings | None = None,
    args: list[str] | None = None,
    stealth_args: bool = True,
    timezone: str | None = None,
    locale: str | None = None,
    network_profile: str | None = None,
    webrtc_policy: str | None = None,
    webgpu_policy: str | None = None,
    **kwargs: Any,
) -> Any:
    """Launch stealth Chromium. Returns a Playwright Browser.

    Args:
        headless: run in headless mode (default True)
        proxy: proxy URL string or Playwright proxy dict
        args: additional Chromium CLI args
        stealth_args: include default stealth fingerprint args (default True)
        timezone: IANA timezone (sets --fingerprint-timezone)
        locale: BCP 47 locale (sets --lang + --fingerprint-locale)
        network_profile: desktop, residential, datacenter, mobile, or slow
        webrtc_policy: proxy-coherent, public-only, default, or off
        webgpu_policy: headless-off, disabled, or coherent
        **kwargs: forwarded to playwright.chromium.launch()
    """
    binary_path = ensure_binary()
    chrome_args = _resolve_args(
        args,
        stealth_args,
        timezone,
        locale,
        network_profile,
        webrtc_policy,
        webgpu_policy,
        headless,
        proxy,
    )
    proxy_kwargs = {"proxy": proxy} if proxy else {}
    kwargs = _cohere_browser_env(chrome_args, kwargs)

    logger.debug("launch(): headless=%s args=%d", headless, len(chrome_args))
    apply_launch_hygiene(logger, chrome_args, kwargs)

    pw = _import_sync_playwright()().start()
    browser = pw.chromium.launch(
        executable_path=binary_path,
        headless=headless,
        args=chrome_args,
        ignore_default_args=IGNORE_DEFAULT_ARGS,
        **proxy_kwargs,
        **kwargs,
    )
    _patch_close(browser, pw.stop)
    return browser


async def launch_async(
    headless: bool = True,
    proxy: str | ProxySettings | None = None,
    args: list[str] | None = None,
    stealth_args: bool = True,
    timezone: str | None = None,
    locale: str | None = None,
    network_profile: str | None = None,
    webrtc_policy: str | None = None,
    webgpu_policy: str | None = None,
    **kwargs: Any,
) -> Any:
    """Async launch(). Returns a Playwright Browser (async API)."""
    binary_path = ensure_binary()
    chrome_args = _resolve_args(
        args,
        stealth_args,
        timezone,
        locale,
        network_profile,
        webrtc_policy,
        webgpu_policy,
        headless,
        proxy,
    )
    proxy_kwargs = {"proxy": proxy} if proxy else {}
    kwargs = _cohere_browser_env(chrome_args, kwargs)
    apply_launch_hygiene(logger, chrome_args, kwargs)

    pw = await _import_async_playwright()().start()
    browser = await pw.chromium.launch(
        executable_path=binary_path,
        headless=headless,
        args=chrome_args,
        ignore_default_args=IGNORE_DEFAULT_ARGS,
        **proxy_kwargs,
        **kwargs,
    )
    _patch_close_async(browser, pw.stop)
    return browser


def launch_context(
    headless: bool = True,
    proxy: str | ProxySettings | None = None,
    args: list[str] | None = None,
    stealth_args: bool = True,
    user_agent: str | None = None,
    viewport: dict | None = _VIEWPORT_UNSET,  # type: ignore[assignment]
    locale: str | None = None,
    timezone: str | None = None,
    network_profile: str | None = None,
    webrtc_policy: str | None = None,
    webgpu_policy: str | None = None,
    color_scheme: Literal["light", "dark", "no-preference"] | None = None,
    **kwargs: Any,
) -> Any:
    """Launch + new_context() in one call. Returns BrowserContext."""
    chrome_args = _resolve_args(
        args,
        stealth_args,
        timezone,
        locale,
        network_profile,
        webrtc_policy,
        webgpu_policy,
        headless,
        proxy,
    )
    browser = launch(
        headless=headless,
        proxy=proxy,
        args=chrome_args,
        stealth_args=False,
    )
    ctx_kwargs: dict[str, Any] = {}
    if user_agent:
        ctx_kwargs["user_agent"] = user_agent
    if viewport is _VIEWPORT_UNSET:
        ctx_kwargs["viewport"] = get_viewport_from_args(chrome_args)
    elif viewport is None:
        ctx_kwargs["no_viewport"] = True
    else:
        ctx_kwargs["viewport"] = viewport
    if color_scheme:
        ctx_kwargs["color_scheme"] = color_scheme
    ctx_kwargs.update(kwargs)

    try:
        context = browser.new_context(**ctx_kwargs)
    except Exception:
        browser.close()
        raise
    _patch_close(context, browser.close)
    return context


async def launch_context_async(
    headless: bool = True,
    proxy: str | ProxySettings | None = None,
    args: list[str] | None = None,
    stealth_args: bool = True,
    user_agent: str | None = None,
    viewport: dict | None = _VIEWPORT_UNSET,  # type: ignore[assignment]
    locale: str | None = None,
    timezone: str | None = None,
    network_profile: str | None = None,
    webrtc_policy: str | None = None,
    webgpu_policy: str | None = None,
    color_scheme: Literal["light", "dark", "no-preference"] | None = None,
    **kwargs: Any,
) -> Any:
    """Async launch_context()."""
    chrome_args = _resolve_args(
        args,
        stealth_args,
        timezone,
        locale,
        network_profile,
        webrtc_policy,
        webgpu_policy,
        headless,
        proxy,
    )
    browser = await launch_async(
        headless=headless,
        proxy=proxy,
        args=chrome_args,
        stealth_args=False,
    )
    ctx_kwargs: dict[str, Any] = {}
    if user_agent:
        ctx_kwargs["user_agent"] = user_agent
    if viewport is _VIEWPORT_UNSET:
        ctx_kwargs["viewport"] = get_viewport_from_args(chrome_args)
    elif viewport is None:
        ctx_kwargs["no_viewport"] = True
    else:
        ctx_kwargs["viewport"] = viewport
    if color_scheme:
        ctx_kwargs["color_scheme"] = color_scheme
    ctx_kwargs.update(kwargs)

    try:
        context = await browser.new_context(**ctx_kwargs)
    except BaseException:
        try:
            await browser.close()
        except BaseException:
            pass
        raise
    _patch_close_async(context, browser.close)
    return context


def launch_persistent_context(
    user_data_dir: str | os.PathLike,
    headless: bool = True,
    proxy: str | ProxySettings | None = None,
    args: list[str] | None = None,
    stealth_args: bool = True,
    user_agent: str | None = None,
    viewport: dict | None = _VIEWPORT_UNSET,  # type: ignore[assignment]
    locale: str | None = None,
    timezone: str | None = None,
    network_profile: str | None = None,
    webrtc_policy: str | None = None,
    webgpu_policy: str | None = None,
    **kwargs: Any,
) -> Any:
    """Persistent profile: cookies/localStorage survive across runs."""
    binary_path = ensure_binary()
    chrome_args = _resolve_args(
        args,
        stealth_args,
        timezone,
        locale,
        network_profile,
        webrtc_policy,
        webgpu_policy,
        headless,
        proxy,
    )
    proxy_kwargs = {"proxy": proxy} if proxy else {}
    kwargs = _cohere_browser_env(chrome_args, kwargs)
    apply_launch_hygiene(logger, chrome_args, kwargs)

    ctx_kwargs: dict[str, Any] = {}
    if user_agent:
        ctx_kwargs["user_agent"] = user_agent
    if viewport is _VIEWPORT_UNSET:
        ctx_kwargs["viewport"] = get_viewport_from_args(chrome_args)
    elif viewport is None:
        ctx_kwargs["no_viewport"] = True
    else:
        ctx_kwargs["viewport"] = viewport
    ctx_kwargs.update(kwargs)

    pw = _import_sync_playwright()().start()
    context = pw.chromium.launch_persistent_context(
        user_data_dir=os.fspath(user_data_dir),
        executable_path=binary_path,
        headless=headless,
        args=chrome_args,
        ignore_default_args=IGNORE_DEFAULT_ARGS,
        **proxy_kwargs,
        **ctx_kwargs,
    )
    _patch_close(context, pw.stop)
    return context


async def launch_persistent_context_async(
    user_data_dir: str | os.PathLike,
    headless: bool = True,
    proxy: str | ProxySettings | None = None,
    args: list[str] | None = None,
    stealth_args: bool = True,
    user_agent: str | None = None,
    viewport: dict | None = _VIEWPORT_UNSET,  # type: ignore[assignment]
    locale: str | None = None,
    timezone: str | None = None,
    network_profile: str | None = None,
    webrtc_policy: str | None = None,
    webgpu_policy: str | None = None,
    **kwargs: Any,
) -> Any:
    """Async launch_persistent_context()."""
    binary_path = ensure_binary()
    chrome_args = _resolve_args(
        args,
        stealth_args,
        timezone,
        locale,
        network_profile,
        webrtc_policy,
        webgpu_policy,
        headless,
        proxy,
    )
    proxy_kwargs = {"proxy": proxy} if proxy else {}
    kwargs = _cohere_browser_env(chrome_args, kwargs)
    apply_launch_hygiene(logger, chrome_args, kwargs)

    ctx_kwargs: dict[str, Any] = {}
    if user_agent:
        ctx_kwargs["user_agent"] = user_agent
    if viewport is _VIEWPORT_UNSET:
        ctx_kwargs["viewport"] = get_viewport_from_args(chrome_args)
    elif viewport is None:
        ctx_kwargs["no_viewport"] = True
    else:
        ctx_kwargs["viewport"] = viewport
    ctx_kwargs.update(kwargs)

    pw = await _import_async_playwright()().start()
    context = await pw.chromium.launch_persistent_context(
        user_data_dir=os.fspath(user_data_dir),
        executable_path=binary_path,
        headless=headless,
        args=chrome_args,
        ignore_default_args=IGNORE_DEFAULT_ARGS,
        **proxy_kwargs,
        **ctx_kwargs,
    )
    _patch_close_async(context, pw.stop)
    return context


# ---------------------------------------------------------------------------
# Close-wrapping so .close() also tears down the Playwright instance
# ---------------------------------------------------------------------------


def _patch_close(target: Any, stop_fn) -> None:
    original = target.close

    def _close():
        try:
            original()
        finally:
            stop_fn()

    target.close = _close


def _patch_close_async(target: Any, stop_fn) -> None:
    original = target.close

    async def _close():
        try:
            await original()
        finally:
            await stop_fn()

    target.close = _close
