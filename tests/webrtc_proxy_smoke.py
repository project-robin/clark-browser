#!/usr/bin/env python3
# Copyright 2026 Clark Labs Inc. - SPDX: MIT
"""Runtime smoke for proxy-coherent WebRTC routing.

This test launches the Python wrapper with a real HTTP proxy setting, gathers
ICE candidates through RTCPeerConnection, and checks that proxy-coherent mode
does not expose private LAN IPs or a direct public STUN route.

Usage:
    CLARK_BINARY_PATH=/path/to/chrome python3 tests/webrtc_proxy_smoke.py
"""
from __future__ import annotations

import ipaddress
import json
import os
import sys
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Iterator

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

TEST_ORIGIN = "http://webrtc-smoke.invalid"
STUN_URL = os.environ.get("CLARK_WEBRTC_STUN_URL", "stun:stun.l.google.com:19302")
TIMEOUT_MS = int(os.environ.get("CLARK_WEBRTC_GATHER_TIMEOUT_MS", "7000"))
COMMON_ARGS = [
    "--disable-gpu",
    f"--unsafely-treat-insecure-origin-as-secure={TEST_ORIGIN}",
]


class ProxyHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:
        self.server.proxy_hits += 1  # type: ignore[attr-defined]
        body = (
            b"<!doctype html><meta charset=utf-8><title>webrtc smoke</title>"
            b"<body>webrtc smoke</body>"
        )
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def do_CONNECT(self) -> None:
        self.server.proxy_connects += 1  # type: ignore[attr-defined]
        self.send_error(502, "CONNECT is not supported by this smoke proxy")

    def log_message(self, format: str, *args: object) -> None:
        return


@contextmanager
def local_http_proxy() -> Iterator[tuple[str, ThreadingHTTPServer]]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), ProxyHandler)
    server.proxy_hits = 0  # type: ignore[attr-defined]
    server.proxy_connects = 0  # type: ignore[attr-defined]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        yield f"http://{host}:{port}", server
    finally:
        server.shutdown()
        server.server_close()


def gather_ice_candidates(page: Any) -> dict[str, Any]:
    return page.evaluate(
        """async ({stunUrl, timeoutMs}) => {
          if (typeof RTCPeerConnection === 'undefined') {
            return {
              supported: false,
              reason: 'unsupported',
              candidates: [],
              candidateDetails: [],
              errors: ['RTCPeerConnection is undefined'],
            };
          }

          const pc = new RTCPeerConnection({
            iceServers: stunUrl ? [{urls: stunUrl}] : [],
          });
          const candidates = [];
          const candidateDetails = [];
          const errors = [];
          const started = performance.now();

          pc.onicecandidate = event => {
            if (!event.candidate) {
              return;
            }
            const c = event.candidate;
            candidates.push(c.candidate);
            candidateDetails.push({
              candidate: c.candidate,
              address: c.address || null,
              relatedAddress: c.relatedAddress || null,
              port: c.port || null,
              protocol: c.protocol || null,
              type: c.type || null,
            });
          };
          pc.onicecandidateerror = event => {
            errors.push({
              url: event.url || null,
              errorCode: event.errorCode || null,
              errorText: event.errorText || null,
            });
          };

          pc.createDataChannel('clark-webrtc-smoke');
          const complete = new Promise(resolve => {
            pc.onicegatheringstatechange = () => {
              if (pc.iceGatheringState === 'complete') {
                resolve('complete');
              }
            };
          });
          await pc.setLocalDescription(await pc.createOffer());
          const reason = await Promise.race([
            complete,
            new Promise(resolve => setTimeout(() => resolve('timeout'), timeoutMs)),
          ]);
          pc.close();

          return {
            supported: true,
            reason,
            candidates,
            candidateDetails,
            errors,
            elapsedMs: Math.round(performance.now() - started),
          };
        }""",
        {"stunUrl": STUN_URL, "timeoutMs": TIMEOUT_MS},
    )


def run_case(
    label: str,
    proxy_url: str,
    webrtc_policy: str | None,
) -> dict[str, Any]:
    from clarkbrowser import launch_context

    context = launch_context(
        headless=True,
        proxy={"server": proxy_url, "bypass": ""},
        args=COMMON_ARGS,
        webrtc_policy=webrtc_policy,
    )
    try:
        page = context.new_page()
        page.goto(TEST_ORIGIN, wait_until="domcontentloaded", timeout=30000)
        result = gather_ice_candidates(page)
        result["label"] = label
        return result
    finally:
        context.close()


def candidate_type(detail: dict[str, Any]) -> str | None:
    if detail.get("type"):
        return str(detail["type"])
    candidate = str(detail.get("candidate") or "")
    parts = candidate.split()
    if "typ" in parts:
        index = parts.index("typ")
        if index + 1 < len(parts):
            return parts[index + 1]
    return None


def candidate_addresses(detail: dict[str, Any]) -> list[ipaddress._BaseAddress]:
    values: list[str] = []
    for key in ("address", "relatedAddress"):
        value = detail.get(key)
        if value:
            values.append(str(value))

    parts = str(detail.get("candidate") or "").split()
    if len(parts) > 4:
        values.append(parts[4])
    if "raddr" in parts:
        index = parts.index("raddr")
        if index + 1 < len(parts):
            values.append(parts[index + 1])

    addresses: list[ipaddress._BaseAddress] = []
    for value in values:
        cleaned = value.strip("[]")
        if not cleaned or cleaned.endswith(".local"):
            continue
        try:
            address = ipaddress.ip_address(cleaned)
        except ValueError:
            continue
        if address.is_unspecified:
            continue
        if address not in addresses:
            addresses.append(address)
    return addresses


def allowed_public_ips() -> set[ipaddress._BaseAddress]:
    raw = os.environ.get("CLARK_WEBRTC_ALLOWED_PUBLIC_IPS", "")
    allowed: set[ipaddress._BaseAddress] = set()
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        allowed.add(ipaddress.ip_address(item))
    return allowed


def require_raw_candidates() -> bool:
    return os.environ.get("CLARK_WEBRTC_REQUIRE_RAW_CANDIDATES", "").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def find_route_leaks(result: dict[str, Any]) -> list[str]:
    allowed = allowed_public_ips()
    leaks: list[str] = []
    for detail in result.get("candidateDetails") or []:
        detail_type = candidate_type(detail)
        addresses = candidate_addresses(detail)
        for address in addresses:
            if address in allowed:
                continue
            if not address.is_global:
                leaks.append(f"private/local IP {address} in {detail_type} candidate")
            else:
                leaks.append(f"non-proxy public IP {address} in {detail_type} candidate")
        if detail_type in {"srflx", "prflx"} and not any(
            address.is_global and address in allowed for address in addresses
        ):
            leaks.append(f"direct {detail_type} candidate present")
    return leaks


def expect(
    failures: list[str],
    label: str,
    condition: bool,
    detail: str,
) -> None:
    if condition:
        print(f"PASS {label}: {detail}")
    else:
        print(f"FAIL {label}: {detail}")
        failures.append(label)


def summarize(result: dict[str, Any]) -> str:
    details = result.get("candidateDetails") or []
    types = sorted({candidate_type(detail) or "unknown" for detail in details})
    return json.dumps(
        {
            "label": result.get("label"),
            "reason": result.get("reason"),
            "candidateCount": len(result.get("candidates") or []),
            "types": types,
            "errors": result.get("errors") or [],
        },
        sort_keys=True,
    )


def main() -> int:
    binary = os.environ.get("CLARK_BINARY_PATH")
    if not binary or not Path(binary).exists():
        print(
            f"ERROR: CLARK_BINARY_PATH not set or missing: {binary!r}",
            file=sys.stderr,
        )
        return 2

    failures: list[str] = []
    with local_http_proxy() as (proxy_url, proxy_server):
        raw = run_case("default/raw", proxy_url, None)
        raw_hits = proxy_server.proxy_hits  # type: ignore[attr-defined]
        coherent = run_case("proxy-coherent", proxy_url, "proxy-coherent")
        coherent_hits = proxy_server.proxy_hits - raw_hits  # type: ignore[attr-defined]

    print(f"RAW {summarize(raw)}")
    print(f"PROXY_COHERENT {summarize(coherent)}")

    expect(
        failures,
        "raw proxy used",
        raw_hits > 0,
        f"HTTP page loaded through local proxy ({raw_hits} hits)",
    )
    expect(
        failures,
        "proxy-coherent proxy used",
        coherent_hits > 0,
        f"HTTP page loaded through local proxy ({coherent_hits} hits)",
    )
    expect(
        failures,
        "raw RTCPeerConnection supported",
        raw.get("supported") is True,
        "default/raw mode executed RTCPeerConnection",
    )
    raw_candidate_count = len(raw.get("candidates") or [])
    if raw_candidate_count > 0:
        print(
            "PASS raw ICE control candidates: "
            f"default/raw mode gathered {raw_candidate_count} ICE candidate(s)"
        )
    elif require_raw_candidates():
        print("FAIL raw ICE control candidates: default/raw mode gathered none")
        failures.append("raw ICE control candidates")
    else:
        print(
            "WARN raw ICE control candidates: default/raw mode gathered none "
            "(set CLARK_WEBRTC_REQUIRE_RAW_CANDIDATES=1 to make this fatal)"
        )
    expect(
        failures,
        "proxy-coherent RTCPeerConnection supported",
        coherent.get("supported") is True,
        "proxy-coherent mode executed RTCPeerConnection",
    )

    coherent_leaks = find_route_leaks(coherent)
    expect(
        failures,
        "proxy-coherent no route leaks",
        not coherent_leaks,
        "no private/local IPs and no direct public STUN route"
        if not coherent_leaks else "; ".join(coherent_leaks),
    )

    raw_leaks = find_route_leaks(raw)
    if raw_leaks:
        print("CONTROL raw route leaks observed: " + "; ".join(raw_leaks))
    else:
        print("CONTROL raw route leaks not observed in this environment")

    return len(failures)


if __name__ == "__main__":
    sys.exit(main())
