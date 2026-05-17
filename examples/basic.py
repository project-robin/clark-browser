# Copyright 2026 Clark Labs Inc.
# SPDX-License-Identifier: MIT

"""Basic launch + navigate + screenshot."""
from clarkbrowser import launch


def main() -> None:
    browser = launch(headless=True)
    page = browser.new_page()
    page.goto("https://example.com", wait_until="networkidle")
    print("Title:", page.title())
    print("UA:", page.evaluate("navigator.userAgent"))
    page.screenshot(path="example.png")
    browser.close()


if __name__ == "__main__":
    main()
