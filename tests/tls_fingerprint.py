#!/usr/bin/env python3
# Copyright 2026 Clark Labs Inc. - SPDX: MIT
"""TLS ClientHello fingerprint test harness.

Starts a local TLS server that captures the raw ClientHello bytes emitted by
the Clark-stealth Chromium binary, parses them into JA3 and JA4 fingerprints,
and compares against a known real-Chrome baseline for the same Chromium
version.

Usage:
    CLARK_BINARY_PATH=/path/to/chrome python3 tests/tls_fingerprint.py

The test does NOT need network access — the TLS server is local. If the
captured JA3/JA4 matches the expected Chrome baseline, the TLS fingerprint
category (#40-#44) is confirmed as a no-op and no BoringSSL patches are
needed.

If it does NOT match, the test prints the delta (which extensions/ciphers
differ) to guide patching.
"""
from __future__ import annotations

import hashlib
import os
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

HOST = "127.0.0.1"
PORT = 0  # ephemeral
TIMEOUT_SEC = 30

# Expected JA3/JA4 for real Chrome 148 on Linux x64.
# Update these after capturing from a stock Chrome 148 build.
# Format: JA3 = "md5(version,ciphers,extensions,curves,point_formats)"
#         JA4 = "t13d<pre>h2_<md5(suffix)>"
EXPECTED_JA3 = os.environ.get("CLARK_EXPECTED_JA3", "")
EXPECTED_JA4 = os.environ.get("CLARK_EXPECTED_JA4", "")


@dataclass
class ClientHelloCapture:
    raw_bytes: bytes = b""
    record_version: tuple[int, int] = (0, 0)
    handshake_version: tuple[int, int] = (0, 0)
    session_id: bytes = b""
    cipher_suites: list[int] = field(default_factory=list)
    compression_methods: list[int] = field(default_factory=list)
    extensions: list[tuple[int, bytes]] = field(default_factory=list)
    supported_groups: list[int] = field(default_factory=list)
    ec_point_formats: list[int] = field(default_factory=list)
    signature_algorithms: list[int] = field(default_factory=list)
    alpn_protocols: list[str] = field(default_factory=list)


def _gen_self_signed_cert(tmpdir: Path) -> tuple[Path, Path]:
    """Generate a self-signed certificate for the local TLS server."""
    cert_path = tmpdir / "cert.pem"
    key_path = tmpdir / "key.pem"
    subprocess.run(
        [
            "openssl", "req", "-x509", "-newkey", "rsa:2048",
            "-keyout", str(key_path), "-out", str(cert_path),
            "-days", "1", "-nodes",
            "-subj", f"/CN={HOST}",
            "-addext", f"subjectAltName=IP:{HOST}",
        ],
        check=True, capture_output=True,
    )
    return cert_path, key_path


def _parse_client_hello(data: bytes) -> ClientHelloCapture | None:
    """Parse raw TLS record bytes into a ClientHelloCapture."""
    if len(data) < 5:
        return None

    content_type = data[0]
    if content_type != 0x16:  # Handshake
        return None

    record_version = (data[1], data[2])
    record_length = int.from_bytes(data[3:5], "big")
    handshake_data = data[5:5 + record_length]

    if len(handshake_data) < 4:
        return None
    if handshake_data[0] != 0x01:  # ClientHello
        return None

    hello_length = int.from_bytes(handshake_data[1:4], "big")
    hello = handshake_data[4:4 + hello_length]

    if len(hello) < 6:
        return None

    capture = ClientHelloCapture(raw_bytes=data, record_version=record_version)
    idx = 0

    # Legacy version (2 bytes)
    capture.handshake_version = (hello[idx], hello[idx + 1])
    idx += 2

    # Random (32 bytes)
    idx += 32

    # Session ID
    session_id_len = hello[idx]
    idx += 1
    capture.session_id = hello[idx:idx + session_id_len]
    idx += session_id_len

    # Cipher suites
    cipher_len = int.from_bytes(hello[idx:idx + 2], "big")
    idx += 2
    cipher_end = idx + cipher_len
    while idx + 1 < cipher_end:
        cs = int.from_bytes(hello[idx:idx + 2], "big")
        capture.cipher_suites.append(cs)
        idx += 2
    idx = cipher_end

    # Compression methods
    comp_len = hello[idx]
    idx += 1
    capture.compression_methods = list(hello[idx:idx + comp_len])
    idx += comp_len

    # Extensions
    if idx + 2 > len(hello):
        return capture
    ext_total_len = int.from_bytes(hello[idx:idx + 2], "big")
    idx += 2
    ext_end = idx + ext_total_len

    while idx + 4 <= ext_end:
        ext_type = int.from_bytes(hello[idx:idx + 2], "big")
        ext_len = int.from_bytes(hello[idx + 2:idx + 4], "big")
        ext_data = hello[idx + 4:idx + 4 + ext_len]
        capture.extensions.append((ext_type, ext_data))

        # Parse specific extensions
        if ext_type == 0x000A and ext_data:  # supported_groups
            groups_len = int.from_bytes(ext_data[0:2], "big")
            gi = 2
            while gi + 1 < 2 + groups_len:
                capture.supported_groups.append(
                    int.from_bytes(ext_data[gi:gi + 2], "big"))
                gi += 2

        elif ext_type == 0x000B and ext_data:  # ec_point_formats
            pf_len = ext_data[0]
            capture.ec_point_formats = list(ext_data[1:1 + pf_len])

        elif ext_type == 0x000D and ext_data:  # signature_algorithms
            sig_len = int.from_bytes(ext_data[0:2], "big")
            si = 2
            while si + 1 < 2 + sig_len:
                capture.signature_algorithms.append(
                    int.from_bytes(ext_data[si:si + 2], "big"))
                si += 2

        elif ext_type == 0x0010 and ext_data:  # ALPN
            alpn_len = int.from_bytes(ext_data[0:2], "big")
            ai = 2
            while ai < 2 + alpn_len:
                proto_len = ext_data[ai]
                ai += 1
                capture.alpn_protocols.append(
                    ext_data[ai:ai + proto_len].decode("ascii", "replace"))
                ai += proto_len

        idx += 4 + ext_len

    return capture


# GREASE values per RFC 8701
GREASE_VALUES = {
    0x0A0A, 0x1A1A, 0x2A2A, 0x3A3A, 0x4A4A, 0x5A5A, 0x6A6A, 0x7A7A,
    0x8A8A, 0x9A9A, 0xAAAA, 0xBABA, 0xCACA, 0xDADA, 0xEAEA, 0xFAFA,
}


def _is_grease(value: int) -> bool:
    return value in GREASE_VALUES


def compute_ja3(cap: ClientHelloCapture) -> str:
    """Compute the JA3 fingerprint string (pre-hash)."""
    version = f"{cap.handshake_version[0]},{cap.handshake_version[1]}"

    ciphers = "-".join(
        f"{cs:04x}" for cs in cap.cipher_suites if not _is_grease(cs))
    extensions = "-".join(
        f"{et:04x}" for (et, _) in cap.extensions if not _is_grease(et))
    curves = "-".join(
        f"{g:04x}" for g in cap.supported_groups if not _is_grease(g))
    points = "-".join(f"{p:02x}" for p in cap.ec_point_formats)

    ja3_str = f"{version},{ciphers},{extensions},{curves},{points}"
    return ja3_str


def compute_ja3_hash(ja3_str: str) -> str:
    return hashlib.md5(ja3_str.encode()).hexdigest()


def compute_ja4(cap: ClientHelloCapture) -> str:
    """Compute the JA4 fingerprint string (pre-hash)."""
    # JA4 format: t<version>d<cipher_count>h<ext_count>_<alpn>_<hash>
    # Version: 13 for TLS 1.3 (inferred from supported_versions extension)
    has_tls13 = any(et == 0x002B for (et, _) in cap.extensions)
    tls_ver = "13" if has_tls13 else "12"

    cipher_count = len([cs for cs in cap.cipher_suites if not _is_grease(cs)])
    ext_count = len([et for (et, _) in cap.extensions if not _is_grease(et)])

    # SNI present?
    has_sni = any(et == 0x0000 for (et, _) in cap.extensions)
    sni_flag = "d" if has_sni else "i"

    ciphers = ",".join(
        f"{cs:04x}" for cs in sorted(
            [cs for cs in cap.cipher_suites if not _is_grease(cs)]))
    extensions = ",".join(
        f"{et:04x}" for et in sorted(
            [et for (et, _) in cap.extensions if not _is_grease(et)
             and et != 0x0000]))  # exclude SNI

    alpn = cap.alpn_protocols[0] if cap.alpn_protocols else "00"
    if not alpn:
        alpn = "00"

    prefix = f"t{tls_ver}d{cipher_count:02d}{sni_flag}h{ext_count:02d}"
    suffix = f"{ciphers}_{extensions}_{alpn}"
    ja4_hash = hashlib.md5(suffix.encode()).hexdigest()[:12]

    return f"{prefix}h2_{ja4_hash}"


def _start_capture_server(
    cert_path: Path, key_path: Path
) -> tuple[threading.Thread, int, list[bytes]]:
    """Start a TLS server that captures raw ClientHello bytes."""

    captured: list[bytes] = []
    ready = threading.Event()
    actual_port: list[int] = [0]

    def server_loop() -> None:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(str(cert_path), str(key_path))

        raw_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        raw_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        raw_sock.bind((HOST, 0))
        raw_sock.listen(1)
        raw_sock.settimeout(TIMEOUT_SEC)
        actual_port[0] = raw_sock.getsockname()[1]
        ready.set()

        try:
            conn, _ = raw_sock.accept()
            # Read the raw ClientHello record before wrapping in TLS.
            # The browser will send the ClientHello as the first TLS record.
            raw_data = conn.recv(16384)
            if raw_data:
                captured.append(raw_data)
            # Send a minimal TLS alert so the browser doesn't hang.
            try:
                conn.sendall(b"\x15\x03\x03\x00\x02\x02\x28")
            except OSError:
                pass
            conn.close()
        except socket.timeout:
            pass
        finally:
            raw_sock.close()

    t = threading.Thread(target=server_loop, daemon=True)
    t.start()
    ready.wait(timeout=5)
    return t, actual_port[0], captured


def _launch_browser_to_url(url: str) -> None:
    """Launch the Clark-stealth Chromium binary to navigate to a URL."""
    from clarkbrowser.config import get_binary_path, get_local_binary_override

    binary = get_local_binary_override() or str(get_binary_path())
    if not Path(binary).exists():
        raise FileNotFoundError(f"Chrome binary not found: {binary}")

    env = dict(os.environ)
    # Ignore cert errors for our self-signed local server.
    args = [
        binary,
        "--headless=new",
        "--no-sandbox",
        "--disable-gpu",
        "--ignore-certificate-errors",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-features=NetworkService,UseChromeOSDirectVideoDecoder",
        "--timeout=10",
        url,
    ]
    subprocess.run(args, timeout=TIMEOUT_SEC, capture_output=True, env=env)


def run_test() -> int:
    """Run the TLS fingerprint capture and comparison."""
    print("[tls-fp] Starting local TLS ClientHello capture server...")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        cert_path, key_path = _gen_self_signed_cert(tmpdir_path)

        t, port, captured = _start_capture_server(cert_path, key_path)
        url = f"https://{HOST}:{port}/"

        print(f"[tls-fp] Server listening on {url}")
        print("[tls-fp] Launching browser to trigger TLS handshake...")

        try:
            _launch_browser_to_url(url)
        except subprocess.TimeoutExpired:
            print("[tls-fp] Browser timed out (non-fatal for capture)")
        except FileNotFoundError as e:
            print(f"[tls-fp] FAIL: {e}")
            return 1

        t.join(timeout=10)

        if not captured:
            print("[tls-fp] FAIL: no ClientHello captured")
            return 1

        cap = _parse_client_hello(captured[0])
        if not cap:
            print("[tls-fp] FAIL: could not parse ClientHello")
            return 1

        ja3_str = compute_ja3(cap)
        ja3_hash = compute_ja3_hash(ja3_str)
        ja4 = compute_ja4(cap)

        print(f"\n[tls-fp] Record version:      {cap.record_version[0]:x}.{cap.record_version[1]:x}")
        print(f"[tls-fp] Handshake version:   {cap.handshake_version[0]:x}.{cap.handshake_version[1]:x}")
        print(f"[tls-fp] Cipher suites:       {len(cap.cipher_suites)}")
        print(f"[tls-fp] Extensions:          {len(cap.extensions)}")
        print(f"[tls-fp] Supported groups:    {len(cap.supported_groups)}")
        print(f"[tls-fp] EC point formats:    {len(cap.ec_point_formats)}")
        print(f"[tls-fp] ALPN protocols:      {cap.alpn_protocols}")
        print(f"[tls-fp] Signature algorithms: {len(cap.signature_algorithms)}")
        print()
        print(f"[tls-fp] JA3 string: {ja3_str}")
        print(f"[tls-fp] JA3 hash:   {ja3_hash}")
        print(f"[tls-fp] JA4:        {ja4}")

        # Print cipher list
        print(f"\n[tls-fp] Cipher list:")
        for cs in cap.cipher_suites:
            grease = " (GREASE)" if _is_grease(cs) else ""
            print(f"  0x{cs:04x}{grease}")

        # Print extension list
        print(f"\n[tls-fp] Extension list:")
        for et, ed in cap.extensions:
            grease = " (GREASE)" if _is_grease(et) else ""
            print(f"  0x{et:04x} ({len(ed)} bytes){grease}")

        # Compare against expected
        ok = True
        if EXPECTED_JA3:
            if ja3_hash == EXPECTED_JA3:
                print(f"\n[tls-fp] PASS: JA3 matches expected Chrome baseline")
            else:
                print(f"\n[tls-fp] DELTA: JA3={ja3_hash} expected={EXPECTED_JA3}")
                ok = False
        else:
            print(f"\n[tls-fp] (no expected JA3 baseline set — capture only)")

        if EXPECTED_JA4:
            if ja4 == EXPECTED_JA4:
                print(f"[tls-fp] PASS: JA4 matches expected Chrome baseline")
            else:
                print(f"[tls-fp] DELTA: JA4={ja4} expected={EXPECTED_JA4}")
                ok = False
        else:
            print(f"[tls-fp] (no expected JA4 baseline set — capture only)")

        if ok:
            print("\n[tls-fp] DONE: TLS fingerprint captured successfully")
            return 0
        else:
            print("\n[tls-fp] FAIL: TLS fingerprint does not match Chrome baseline")
            return 1


if __name__ == "__main__":
    sys.exit(run_test())
