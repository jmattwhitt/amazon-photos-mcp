#!/usr/bin/env python3
"""
Authentication Wizard for Amazon Photos MCP.

This script uses Playwright to open a browser window, allowing you to log into Amazon.
Once logged in, it automatically extracts the required session cookies and saves them
to cookies.json.

Usage:
    uv run scripts/auth_wizard.py
"""

import json
import logging
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("Error: playwright is not installed.")
    print("Please install the optional 'auth' dependencies:")
    print("  uv sync --extra auth")
    print("  uv run playwright install chromium")
    exit(1)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    log = logging.getLogger("auth_wizard")

    log.info("Starting Authentication Wizard...")
    log.info("A browser window will open. Please log into your Amazon account.")
    log.info("Once you reach the Amazon Photos dashboard, the script will capture your cookies.")

    with sync_playwright() as p:
        # Launch browser in non-headless mode so the user can log in
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        )
        page = context.new_page()

        try:
            # Navigate to Amazon Photos
            page.goto("https://www.amazon.com/photos")

            log.info("Waiting for successful login...")
            log.info("Please complete the login process in the browser window.")

            # Wait until we see a common element that indicates we are logged in
            # We can wait for the URL to change to the main drive page or an element to appear
            page.wait_for_url("**/photos*", timeout=300_000)  # 5 minute timeout for login

            # Wait a few seconds for cookies to settle
            page.wait_for_timeout(3000)

            # Get cookies
            playwright_cookies = context.cookies()

            # Extract just the key/value pairs we need, or all of them
            # Amazon typically needs session-id, session-token, ubid-main, x-main, at-main
            cookies_dict = {c["name"]: c["value"] for c in playwright_cookies}

            required_keys = ["session-id", "ubid-main"]
            missing = [k for k in required_keys if k not in cookies_dict]

            if missing:
                log.warning("Logged in, but missing expected cookies: %s", missing)

            # Save to cookies.json
            cookie_path = Path("cookies.json")
            cookie_path.write_text(json.dumps(cookies_dict, indent=2))
            log.info("Successfully extracted cookies and saved to %s", cookie_path.resolve())

        except Exception as e:
            log.error("An error occurred during authentication: %s", e)
        finally:
            browser.close()


if __name__ == "__main__":
    main()
