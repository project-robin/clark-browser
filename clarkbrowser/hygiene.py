# Copyright 2026 Clark Labs Inc.
# SPDX-License-Identifier: MIT

"""Launch hygiene checks for Clark-driven browser sessions."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

LAUNCH_HYGIENE_ENV = "CLARK_LAUNCH_HYGIENE"
LAUNCH_HYGIENE_POLICIES = {"warn", "strict", "off"}

_LOOPBACK_ADDRESSES = {"127.0.0.1", "localhost", "::1", "[::1]"}


@dataclass(frozen=True)
class LaunchHygieneFinding:
    """A launch option that can create avoidable automation/debugging signals."""

    code: str
    level: str
    message: str
    option: str | None = None


def _split_arg(arg: str) -> tuple[str, str | None]:
    key, sep, value = arg.partition("=")
    return key, value if sep else None


def _arg_value(args: Sequence[str], key: str) -> str | None:
    for arg in reversed(args):
        arg_key, value = _split_arg(arg)
        if arg_key == key:
            return value
    return None


def _has_arg(args: Sequence[str], key: str) -> bool:
    return any(_split_arg(arg)[0] == key for arg in args)


def assess_launch_hygiene(
    args: Sequence[str] | None = None,
    kwargs: Mapping[str, Any] | None = None,
) -> list[LaunchHygieneFinding]:
    """Return warnings for launch options that are noisy in automated runs.

    These checks do not hide or bypass anything. They catch accidental launch
    settings that make test automation brittle, unsafe, or easy to misdiagnose:
    re-enabling Chrome automation switches, opening DevTools, and exposing CDP
    beyond a local loopback interface.
    """

    launch_args = list(args or [])
    launch_kwargs = dict(kwargs or {})
    findings: list[LaunchHygieneFinding] = []

    if _has_arg(launch_args, "--enable-automation"):
        findings.append(
            LaunchHygieneFinding(
                code="enable-automation",
                level="warning",
                option="--enable-automation",
                message=(
                    "user args re-enable Chrome's automation switch; leave it "
                    "out unless a local debugger explicitly needs it"
                ),
            )
        )

    if _has_arg(launch_args, "--auto-open-devtools-for-tabs") or _has_arg(
        launch_args, "--devtools"
    ):
        findings.append(
            LaunchHygieneFinding(
                code="devtools-open",
                level="warning",
                option="--auto-open-devtools-for-tabs",
                message=(
                    "DevTools is configured to open with the page; keep "
                    "DevTools closed for normal automation and only enable it "
                    "during local debugging"
                ),
            )
        )

    if launch_kwargs.get("devtools") is True:
        findings.append(
            LaunchHygieneFinding(
                code="devtools-kwarg",
                level="warning",
                option="devtools=True",
                message=(
                    "Playwright devtools=True opens DevTools for the page; use "
                    "it only for interactive local debugging"
                ),
            )
        )

    remote_port = _arg_value(launch_args, "--remote-debugging-port")
    remote_address = _arg_value(launch_args, "--remote-debugging-address")
    remote_origins = _arg_value(launch_args, "--remote-allow-origins")

    if remote_address and remote_address.strip().lower() not in _LOOPBACK_ADDRESSES:
        findings.append(
            LaunchHygieneFinding(
                code="remote-debugging-public-address",
                level="warning",
                option="--remote-debugging-address",
                message=(
                    "CDP is bound outside loopback; bind "
                    "--remote-debugging-address=127.0.0.1 for local automation"
                ),
            )
        )
    elif remote_port and not remote_address:
        findings.append(
            LaunchHygieneFinding(
                code="remote-debugging-implicit-address",
                level="warning",
                option="--remote-debugging-port",
                message=(
                    "CDP port is enabled without an explicit loopback address; "
                    "add --remote-debugging-address=127.0.0.1"
                ),
            )
        )

    if remote_origins and remote_origins.strip() == "*":
        findings.append(
            LaunchHygieneFinding(
                code="remote-allow-origins-wildcard",
                level="warning",
                option="--remote-allow-origins=*",
                message=(
                    "CDP accepts any origin; restrict this in shared or "
                    "long-running environments"
                ),
            )
        )

    return findings


def get_launch_hygiene_policy() -> str:
    """Return warn, strict, or off for launch hygiene findings."""

    value = os.environ.get(LAUNCH_HYGIENE_ENV, "warn").strip().lower()
    if value in LAUNCH_HYGIENE_POLICIES:
        return value
    supported = ", ".join(sorted(LAUNCH_HYGIENE_POLICIES))
    raise RuntimeError(
        f"Unsupported {LAUNCH_HYGIENE_ENV}={value!r}. Supported: {supported}"
    )


def apply_launch_hygiene(
    logger: Any,
    args: Sequence[str] | None = None,
    kwargs: Mapping[str, Any] | None = None,
) -> list[LaunchHygieneFinding]:
    """Warn or fail for risky launch options, based on CLARK_LAUNCH_HYGIENE."""

    policy = get_launch_hygiene_policy()
    if policy == "off":
        return []

    findings = assess_launch_hygiene(args, kwargs)
    if not findings:
        return []

    if policy == "strict":
        details = "; ".join(
            f"{finding.code}: {finding.message}" for finding in findings
        )
        raise RuntimeError(f"Clark launch hygiene failed: {details}")

    for finding in findings:
        logger.warning("Clark launch hygiene [%s]: %s", finding.code, finding.message)
    return findings
