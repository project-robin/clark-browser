# Copyright 2026 Clark Labs Inc.
# SPDX-License-Identifier: MIT

"""Stealth defaults and platform detection for clark-browser."""
from __future__ import annotations

import os
import platform
import random
from pathlib import Path

from ._version import __version__

# ---------------------------------------------------------------------------
# Chromium version shipped with this release of clark-browser.
# Updated when we rebase against a newer upstream + ungoogled-chromium tag.
# ---------------------------------------------------------------------------
CHROMIUM_VERSION = "148.0.7778.96"

PLATFORM_CHROMIUM_VERSIONS: dict[str, str] = {
    "linux-x64": CHROMIUM_VERSION,
    "darwin-arm64": CHROMIUM_VERSION,
    "darwin-x64": CHROMIUM_VERSION,
}

# Playwright default args we suppress — they leak automation signals.
IGNORE_DEFAULT_ARGS = ["--enable-automation", "--enable-unsafe-swiftshader"]

# Default viewport — realistic maximized Chrome on 1080p.
DEFAULT_VIEWPORT = {"width": 1920, "height": 947}


# UA strings matched to --fingerprint-platform. Chromium reads the HTTP
# User-Agent from the browser process at request time, not from
# navigator.userAgent — so we MUST pass --user-agent on the command line too,
# otherwise the HTTP header and the JS string disagree (a textbook
# bot-detection signal). The patched binary still rewrites
# navigator.userAgent based on --fingerprint-platform; we just match.
_CHROMIUM_BROWSER_VERSION = CHROMIUM_VERSION.split(".")[0] + ".0.0.0"
PLATFORM_USER_AGENTS: dict[str, str] = {
    "windows": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        f"Chrome/{_CHROMIUM_BROWSER_VERSION} Safari/537.36"
    ),
    "macos": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        f"Chrome/{_CHROMIUM_BROWSER_VERSION} Safari/537.36"
    ),
    "linux": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        f"Chrome/{_CHROMIUM_BROWSER_VERSION} Safari/537.36"
    ),
}


def get_default_stealth_args() -> list[str]:
    """Stealth flags applied automatically by launch() unless stealth_args=False.

    The patched binary auto-generates the rest from --fingerprint=<seed>.
    """
    seed = random.randint(10000, 99999)
    system = platform.system()

    if system == "Darwin":
        fp_platform = "macos"
    else:
        # Linux: present as Windows for broader cluster blending.
        fp_platform = "windows"

    return [
        "--no-sandbox",
        f"--fingerprint={seed}",
        f"--fingerprint-platform={fp_platform}",
        f"--user-agent={PLATFORM_USER_AGENTS[fp_platform]}",
        # macOS needs this to avoid hanging on Keychain mutex in unsigned dev builds.
        # No effect on Linux.
        "--use-mock-keychain",
    ]


# ---------------------------------------------------------------------------
# Platform detection
# ---------------------------------------------------------------------------
SUPPORTED_PLATFORMS: dict[tuple[str, str], str] = {
    ("Linux", "x86_64"): "linux-x64",
    ("Darwin", "arm64"): "darwin-arm64",
    ("Darwin", "x86_64"): "darwin-x64",
}

AVAILABLE_PLATFORMS: set[str] = set(PLATFORM_CHROMIUM_VERSIONS.keys())


def get_chromium_version() -> str:
    return PLATFORM_CHROMIUM_VERSIONS.get(get_platform_tag(), CHROMIUM_VERSION)


def get_platform_tag() -> str:
    system = platform.system()
    machine = platform.machine()
    tag = SUPPORTED_PLATFORMS.get((system, machine))
    if tag is None:
        raise RuntimeError(
            f"Unsupported platform: {system} {machine}. "
            f"Supported: {', '.join(f'{s}-{m}' for (s, m) in SUPPORTED_PLATFORMS)}"
        )
    return tag


def get_cache_dir() -> Path:
    """Override with CLARK_CACHE_DIR env var. Default: ~/.clarkbrowser/."""
    custom = os.environ.get("CLARK_CACHE_DIR")
    if custom:
        return Path(custom)
    return Path.home() / ".clarkbrowser"


def get_binary_dir(version: str | None = None) -> Path:
    v = version or get_chromium_version()
    return get_cache_dir() / f"chromium-{v}"


def get_binary_path(version: str | None = None) -> Path:
    binary_dir = get_binary_dir(version)
    if platform.system() == "Darwin":
        return binary_dir / "Chromium.app" / "Contents" / "MacOS" / "Chromium"
    return binary_dir / "chrome"


def get_local_binary_override() -> str | None:
    """Skip download — use a locally built clark-stealth-chromium binary."""
    return os.environ.get("CLARK_BINARY_PATH")


# ---------------------------------------------------------------------------
# Download URLs (GitHub Releases)
# ---------------------------------------------------------------------------
DOWNLOAD_BASE_URL = os.environ.get(
    "CLARK_DOWNLOAD_URL",
    "https://github.com/clark-labs-inc/clark-browser/releases/download",
)


def get_archive_ext() -> str:
    return ".tar.gz"


def get_archive_name(tag: str | None = None) -> str:
    t = tag or get_platform_tag()
    return f"clark-browser-{t}{get_archive_ext()}"


def get_download_url(version: str | None = None) -> str:
    v = version or get_chromium_version()
    return f"{DOWNLOAD_BASE_URL}/chromium-v{v}/{get_archive_name()}"
