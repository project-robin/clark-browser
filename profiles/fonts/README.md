# Clark Font Profile Packs

Clark does not redistribute commercial operating-system fonts. A font profile
pack is a directory that the launcher can validate and expose to Linux Chromium
through Fontconfig while also passing `--fingerprint-fonts-dir` for detector
audits and future native FontCache plumbing.

## Linux Profile

Use the Linux profile when the browser should look like a Linux desktop:

```bash
export CLARK_FINGERPRINT_PLATFORM=linux
export CLARK_LINUX_FONTS_DIR=/usr/share/fonts
```

Recommended Linux families:

- DejaVu Sans
- Liberation Sans
- Noto Sans
- Noto Color Emoji
- Ubuntu
- Ubuntu Mono

The launcher defaults to `--fingerprint-platform=linux` on Linux hosts unless a
valid Windows font pack is configured.

## Windows Profile

Use a Windows profile from Linux only with licensed Windows fonts:

```bash
export CLARK_WINDOWS_FONTS_DIR=/var/lib/clark-browser/fonts/windows
```

Minimum required families for Clark's launcher validation and smoke tests:

- Arial
- Calibri
- Segoe UI

Recommended additional families:

- Cambria
- Consolas
- Georgia
- Tahoma
- Times New Roman
- Trebuchet MS
- Verdana

Typical filenames include:

```text
arial.ttf
calibri.ttf
segoeui.ttf
times.ttf
verdana.ttf
tahoma.ttf
consola.ttf
cambria.ttc
```

If `CLARK_FINGERPRINT_PLATFORM=windows` is set on a non-Windows host without a
valid Windows font pack, the launcher fails before starting Chromium. This is
intentional: a Windows UA/Win32 profile with a tiny Linux font set is a strong
fingerprint.

## Smoke Testing

The Linux smoke defaults to the Linux font profile. To verify a Windows pack:

```bash
CLARK_WINDOWS_FONTS_DIR=/var/lib/clark-browser/fonts/windows \
CLARK_SMOKE_FONT_PROFILE=windows \
CLARK_BINARY_PATH=/path/to/chrome \
python3 tests/linux_smoke.py
```

The smoke checks `document.fonts.check()` for Arial, Segoe UI, and Calibri in a
Windows profile, and for common Linux UI families in the Linux profile.
