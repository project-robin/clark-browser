# Copyright 2026 Clark Labs Inc.
# SPDX-License-Identifier: MIT

"""Core launch functions for clark-browser.

Thin wrapper around Playwright that uses the patched Chromium binary.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Literal, TypedDict

from .config import DEFAULT_VIEWPORT, IGNORE_DEFAULT_ARGS, get_default_stealth_args
from .download import ensure_binary

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
    headless: bool,
) -> list[str]:
    """Merge stealth defaults + user args + dedicated params."""
    seen: dict[str, str] = {}

    if stealth_args:
        for a in get_default_stealth_args():
            seen[a.split("=", 1)[0]] = a

    if user_args:
        for a in user_args:
            seen[a.split("=", 1)[0]] = a

    if timezone:
        seen["--fingerprint-timezone"] = f"--fingerprint-timezone={timezone}"
    if locale:
        seen["--lang"] = f"--lang={locale}"
        seen["--fingerprint-locale"] = f"--fingerprint-locale={locale}"

    return list(seen.values())


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
        **kwargs: forwarded to playwright.chromium.launch()
    """
    binary_path = ensure_binary()
    chrome_args = _resolve_args(args, stealth_args, timezone, locale, headless)
    proxy_kwargs = {"proxy": proxy} if proxy else {}

    logger.debug("launch(): headless=%s args=%d", headless, len(chrome_args))

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
    **kwargs: Any,
) -> Any:
    """Async launch(). Returns a Playwright Browser (async API)."""
    binary_path = ensure_binary()
    chrome_args = _resolve_args(args, stealth_args, timezone, locale, headless)
    proxy_kwargs = {"proxy": proxy} if proxy else {}

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
    color_scheme: Literal["light", "dark", "no-preference"] | None = None,
    **kwargs: Any,
) -> Any:
    """Launch + new_context() in one call. Returns BrowserContext."""
    browser = launch(
        headless=headless,
        proxy=proxy,
        args=args,
        stealth_args=stealth_args,
        timezone=timezone,
        locale=locale,
    )
    ctx_kwargs: dict[str, Any] = {}
    if user_agent:
        ctx_kwargs["user_agent"] = user_agent
    if viewport is _VIEWPORT_UNSET:
        ctx_kwargs["viewport"] = DEFAULT_VIEWPORT
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
    color_scheme: Literal["light", "dark", "no-preference"] | None = None,
    **kwargs: Any,
) -> Any:
    """Async launch_context()."""
    browser = await launch_async(
        headless=headless,
        proxy=proxy,
        args=args,
        stealth_args=stealth_args,
        timezone=timezone,
        locale=locale,
    )
    ctx_kwargs: dict[str, Any] = {}
    if user_agent:
        ctx_kwargs["user_agent"] = user_agent
    if viewport is _VIEWPORT_UNSET:
        ctx_kwargs["viewport"] = DEFAULT_VIEWPORT
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
    **kwargs: Any,
) -> Any:
    """Persistent profile: cookies/localStorage survive across runs."""
    binary_path = ensure_binary()
    chrome_args = _resolve_args(args, stealth_args, timezone, locale, headless)
    proxy_kwargs = {"proxy": proxy} if proxy else {}

    ctx_kwargs: dict[str, Any] = {}
    if user_agent:
        ctx_kwargs["user_agent"] = user_agent
    if viewport is _VIEWPORT_UNSET:
        ctx_kwargs["viewport"] = DEFAULT_VIEWPORT
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
    **kwargs: Any,
) -> Any:
    """Async launch_persistent_context()."""
    binary_path = ensure_binary()
    chrome_args = _resolve_args(args, stealth_args, timezone, locale, headless)
    proxy_kwargs = {"proxy": proxy} if proxy else {}

    ctx_kwargs: dict[str, Any] = {}
    if user_agent:
        ctx_kwargs["user_agent"] = user_agent
    if viewport is _VIEWPORT_UNSET:
        ctx_kwargs["viewport"] = DEFAULT_VIEWPORT
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
