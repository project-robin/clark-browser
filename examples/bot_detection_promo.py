# Copyright 2026 Clark Labs Inc.
# SPDX-License-Identifier: MIT

"""Generate promo media from a real clark-browser bot-detection run.

The script launches clarkbrowser, visits SannySoft's public antibot check,
asserts the core automation signals pass, and writes MP4 + GIF assets to
the repo's promo/ directory.

For local source builds, point CLARK_BINARY_PATH at the patched Chromium:

    CLARK_BINARY_PATH=/path/to/Chromium python examples/bot_detection_promo.py
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from clarkbrowser import launch_context


ROOT = Path(__file__).resolve().parents[1]
TARGET_URL = "https://bot.sannysoft.com/"
OUT_DIR = ROOT / "promo"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=TARGET_URL)
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    parser.add_argument("--name", default="clark-browser-bot-check")
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=800)
    parser.add_argument("--gif-width", type=int, default=760)
    parser.add_argument("--fingerprint", default="42424")
    parser.add_argument("--timeout-ms", type=int, default=90_000)
    parser.add_argument("--keep-webm", action="store_true")
    return parser.parse_args()


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def require_ffmpeg() -> None:
    if shutil.which("ffmpeg") is None:
        raise SystemExit("ffmpeg is required to write MP4 and GIF outputs")


def collect_core_signals(page: Any) -> dict[str, Any]:
    return page.evaluate(
        """() => ({
            webdriver: navigator.webdriver,
            plugins: navigator.plugins.length,
            chromeObject: typeof window.chrome,
            userAgent: navigator.userAgent,
            platform: navigator.platform,
            languages: Array.from(navigator.languages || []),
        })"""
    )


def assert_detection_page_passed(page: Any) -> dict[str, Any]:
    body = page.locator("body").inner_text(timeout=10_000)
    signals = collect_core_signals(page)

    required_text = [
        "missing (passed)",
        "WebDriver Advanced\tpassed",
        "present (passed)",
        "PHANTOM_UA\tok",
        "HEADCHR_UA\tok",
        "HEADCHR_CHROME_OBJ\tok",
        "HEADCHR_PLUGINS\tok",
    ]
    missing = [text for text in required_text if text not in body]

    failures = []
    if signals["webdriver"] is not False:
        failures.append(f"navigator.webdriver={signals['webdriver']!r}")
    if signals["plugins"] < 5:
        failures.append(f"navigator.plugins.length={signals['plugins']!r}")
    if signals["chromeObject"] != "object":
        failures.append(f"typeof window.chrome={signals['chromeObject']!r}")
    if "HeadlessChrome" in signals["userAgent"]:
        failures.append("user agent contains HeadlessChrome")
    if "\tfailed" in body.lower() or "failed:" in body.lower():
        failures.append("SannySoft page reported a failed row")
    if missing:
        failures.append("missing expected page text: " + ", ".join(missing))

    result = {
        "url": page.url,
        "title": page.title(),
        "signals": signals,
        "required_text_found": required_text,
    }
    if failures:
        result["failures"] = failures
        raise RuntimeError(json.dumps(result, indent=2))
    return result


def record_visit(args: argparse.Namespace, video_dir: Path) -> tuple[Path, dict[str, Any]]:
    context = launch_context(
        headless=True,
        viewport={"width": args.width, "height": args.height},
        record_video_dir=str(video_dir),
        record_video_size={"width": args.width, "height": args.height},
        args=[
            f"--fingerprint={args.fingerprint}",
            "--fingerprint-platform=windows",
        ],
    )
    page = context.new_page()
    page.goto(args.url, wait_until="networkidle", timeout=args.timeout_ms)
    page.wait_for_timeout(3_000)

    result = assert_detection_page_passed(page)

    page.evaluate("window.scrollTo(0, 0)")
    page.wait_for_timeout(1_000)
    for y in (360, 720, 1080, 0):
        page.evaluate(f"window.scrollTo({{top: {y}, behavior: 'smooth'}})")
        page.wait_for_timeout(1_400)

    video = page.video
    if video is None:
        raise RuntimeError("Playwright did not produce a page video")
    page.close()
    webm = Path(video.path())
    context.close()
    return webm, result


def convert_video(webm: Path, mp4: Path, gif: Path, gif_width: int) -> None:
    mp4.parent.mkdir(parents=True, exist_ok=True)
    run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(webm),
            "-movflags",
            "+faststart",
            "-pix_fmt",
            "yuv420p",
            "-vf",
            "fps=30",
            str(mp4),
        ]
    )

    with tempfile.TemporaryDirectory() as td:
        palette = Path(td) / "palette.png"
        run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(mp4),
                "-vf",
                f"fps=10,scale={gif_width}:-1:flags=lanczos,palettegen",
                str(palette),
            ]
        )
        run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(mp4),
                "-i",
                str(palette),
                "-filter_complex",
                f"fps=10,scale={gif_width}:-1:flags=lanczos[x];[x][1:v]paletteuse",
                str(gif),
            ]
        )


def main() -> None:
    args = parse_args()
    require_ffmpeg()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    mp4 = args.out_dir / f"{args.name}.mp4"
    gif = args.out_dir / f"{args.name}.gif"
    result_json = args.out_dir / f"{args.name}.json"

    with tempfile.TemporaryDirectory() as td:
        webm, result = record_visit(args, Path(td))
        convert_video(webm, mp4, gif, args.gif_width)
        if args.keep_webm:
            shutil.copy2(webm, args.out_dir / f"{args.name}.webm")

    result_json.write_text(json.dumps(result, indent=2) + "\n")
    print(f"Wrote {mp4}")
    print(f"Wrote {gif}")
    print(f"Wrote {result_json}")


if __name__ == "__main__":
    main()
