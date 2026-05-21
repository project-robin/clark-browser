# Copyright 2026 Clark Labs Inc.
# SPDX-License-Identifier: MIT

"""Launch hygiene + paced interaction example."""
from __future__ import annotations

from clarkbrowser import InteractionPacer, assess_launch_hygiene, launch_context


def main() -> None:
    findings = assess_launch_hygiene(["--remote-debugging-port=9222"])
    for finding in findings:
        print(f"Launch hygiene: {finding.code}: {finding.message}")

    context = launch_context(headless=True)
    page = context.new_page()
    pacer = InteractionPacer()

    page.goto("https://example.com", wait_until="domcontentloaded")
    pacer.click(page, "a")
    page.wait_for_load_state("networkidle")

    print("Title:", page.title())
    context.close()


if __name__ == "__main__":
    main()
