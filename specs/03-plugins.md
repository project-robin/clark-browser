# Spec — patch #03: navigator.plugins

## Goal

`navigator.plugins.length` returns 5 (matches real Chrome). Plugin entries
have valid name/filename/description strings consistent with a real Chrome
install. `navigator.mimeTypes.length` is consistent with the plugin list.

## Public idea sources

- Live Chrome inspection on macOS 14 / Win 11 / Ubuntu 22 — every recent
  Chrome version (since ~94) returns the same 5-plugin "PDF viewer
  bundle":
  ```
  PDF Viewer            internal-pdf-viewer
  Chrome PDF Viewer     internal-pdf-viewer
  Chromium PDF Viewer   internal-pdf-viewer
  Microsoft Edge PDF Viewer  internal-pdf-viewer
  WebKit built-in PDF   internal-pdf-viewer
  ```
- W3C Web Platform `PluginArray` and `MimeTypeArray` interfaces
- Upstream `third_party/blink/renderer/core/page/plugin_data.cc`

## Why the default ships empty for headless

In headless, no plugin host process is spun up, so `PluginData` is empty.
Real Chrome populates from the actual PluginService. For our purposes we
fake the canonical 5-plugin list at the blink layer.

## Implementation outline

In `PluginData::RefreshBrowserSidePluginCache` (or equivalent renderer-side
plugin-info plumbing for the Chromium version we're pinned to), if
`--fingerprint-platform` is set OR we're in headless mode:

```cpp
// clark-stealth: synthesize PDF-viewer 5-tuple matching real Chrome
plugins_ = {
  MakePdfPlugin("PDF Viewer", "internal-pdf-viewer"),
  MakePdfPlugin("Chrome PDF Viewer", "internal-pdf-viewer"),
  MakePdfPlugin("Chromium PDF Viewer", "internal-pdf-viewer"),
  MakePdfPlugin("Microsoft Edge PDF Viewer", "internal-pdf-viewer"),
  MakePdfPlugin("WebKit built-in PDF", "internal-pdf-viewer"),
};
```

`MakePdfPlugin` populates:
- name (per row above)
- filename: `"internal-pdf-viewer"`
- description: `"Portable Document Format"`
- one MimeType entry: type=`application/pdf`, suffixes=`pdf`,
  description=`"Portable Document Format"`

`navigator.mimeTypes` is derived from the plugin list automatically by
the existing PluginData → MimeTypeArray code in blink, so we don't need
a separate mimeType patch.

## Edge cases

- `--disable-plugins` flag still honored; if set, return empty array.
- Each plugin's `.item(i)` and named-property access must work.
- `[Symbol.iterator]` on PluginArray must enumerate all 5.

## Tests

```js
console.assert(navigator.plugins.length === 5);
console.assert(navigator.plugins[0].name === "PDF Viewer");
console.assert(navigator.mimeTypes.length >= 1);
console.assert(navigator.mimeTypes["application/pdf"].enabledPlugin);
```

## Public reference plugins seen on live Chrome

Verified by visiting `chrome://flags` → `about://components` and
running `JSON.stringify([...navigator.plugins].map(p=>p.name))` in
real Chrome 146 on macOS 14 (May 2026):

```
["PDF Viewer","Chrome PDF Viewer","Chromium PDF Viewer","Microsoft Edge PDF Viewer","WebKit built-in PDF"]
```

(Re-verify when rebasing to a newer Chromium release.)
