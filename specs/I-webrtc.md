# Patches I — WebRTC (#38-#39)

Two patches. #38 is technically the hardest non-TLS patch — touches
webrtc third-party code in a way that's specific to ICE candidate
enumeration.

## The fingerprint surface

WebRTC peer connections enumerate "host" ICE candidates by querying
the OS for local network interfaces. A site can collect these via:

```js
const pc = new RTCPeerConnection({iceServers: []});
pc.createDataChannel('');
pc.onicecandidate = e => console.log(e.candidate?.address);
pc.createOffer().then(o => pc.setLocalDescription(o));
```

This leaks:
- The host's real LAN IP (often a 10.x or 192.168.x — recognizable
  as a Docker bridge / VPN / corp net)
- mDNS-obfuscated UUID for the same (still observable as a stable
  identifier across visits)

Even through a proxy at the HTTP layer, WebRTC ICE happens at a lower
layer and bypasses the proxy by default.

## Proxy-coherent launcher policy

Clark exposes an opt-in proxy-coherent mode without waiting for the deeper
#38 ICE-candidate replacement patch:

- Python API: `webrtc_policy="proxy-coherent"`
- Env var: `CLARK_WEBRTC_POLICY=proxy-coherent`
- Chromium switch:
  `--force-webrtc-ip-handling-policy=disable_non_proxied_udp`

Chromium maps `disable_non_proxied_udp` to disabling non-proxied UDP in Blink's
WebRTC port allocator. With an HTTP proxy, that prevents WebRTC/STUN from
taking a different direct route than the page's HTTP traffic; if UDP proxying is
not available, WebRTC falls back to proxied TCP. This matches RFC 8828's Mode 4
framing: forcing proxy use trades media quality for route/privacy coherence.

This mode remains opt-in because many real WebRTC applications depend on direct
UDP. It is separate from #38: proxy-coherent mode constrains routing, while
`--fingerprint-webrtc-ip` is still the future explicit candidate spoofing patch.

## #38 — `--fingerprint-webrtc-ip` replaces ICE host candidate

**File:** `third_party/webrtc/rtc_base/network.cc`, class
`BasicNetworkManager`, method `CreateNetworks` (or equivalent — names
shift between webrtc versions).

**Change:**
```cpp
void BasicNetworkManager::CreateNetworks(...) {
  // ...existing enumeration via SIOCGIFADDR / getifaddrs / etc...

  auto* cl = base::CommandLine::ForCurrentProcess();
  if (cl->HasSwitch(clark::switches::kFingerprintWebrtcIp)) {
    std::string ip = cl->GetSwitchValueASCII(
        clark::switches::kFingerprintWebrtcIp);
    // Replace ALL host candidates with a single network whose primary
    // IP is the spoofed IP. mDNS path is automatically disabled because
    // we have a public-looking IP now.
    networks->clear();
    auto net = std::make_unique<Network>(
        "clark-stealth", "clark-stealth",
        rtc::IPAddress::FromString(ip), 32, ADAPTER_TYPE_ETHERNET);
    networks->push_back(std::move(net));
  }
}
```

**Edge:** Some sites trigger an ICE timeout if NO host candidates are
available. Verify our replacement still allows successful candidate
gathering to complete.

## #39 — mDNS host-candidate consistency

Real Chrome enables mDNS host candidates by default — a host candidate
looks like `abc123-uuid.local` instead of `192.168.1.7`. Detection
sites that see a raw IP (192.168.1.7) instead of an mDNS UUID infer
"this browser has mDNS disabled, which is unusual."

**File:** `third_party/blink/renderer/modules/peerconnection/peer_connection_dependency_factory.cc`

**Change:** Ensure mDNS-host-name policy is `kRequireRTCConfigurationFlag`
or `kAllow` (depending on Chromium version), matching real Chrome
default. This is the existing default in stock builds; the patch is
a verification + regression test, not a change. If we find ungoogled
flipped it, restore the default.

Patch only fires when `--fingerprint-webrtc-ip` is NOT set — when set,
#38 returns a public-looking IP and mDNS isn't useful.

## Tests

```js
const pc = new RTCPeerConnection({iceServers: []});
pc.createDataChannel('');
const candidates = [];
pc.onicecandidate = e => {
  if (e.candidate) candidates.push(e.candidate);
};
await pc.setLocalDescription(await pc.createOffer());
await new Promise(r => setTimeout(r, 2000));

// Default (no --fingerprint-webrtc-ip): candidates contain `.local`
// host candidates (mDNS).
assert(candidates.some(c => c.address?.endsWith('.local')));

// With --fingerprint-webrtc-ip=203.0.113.42:
//   - host candidate is 203.0.113.42 (not .local, not 10.x)
//   - no internal IP leaked
assert.equal(candidates[0].address, '203.0.113.42');
assert(!candidates.some(c => c.address?.match(/^(10\.|192\.168\.|172\.16\.)/)));
```

## Risks

- Some VPN / corp-NAT setups break with a spoofed host candidate. Make
  sure --fingerprint-webrtc-ip is opt-in, not on by default. Default
  remains: real enumeration with mDNS.

## Effort

1 week for #38 (the webrtc/ patch is tricky — need to handle multi-IP
machines, IPv6, dual-stack). #39 is half a day verification.
