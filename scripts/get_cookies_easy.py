"""
Easy Amazon Photos cookie extraction using Playwright.

Opens a browser, you sign in to Amazon, press Enter, and cookies
are saved automatically. No copy-paste, no Firefox install, no
Chrome encryption issues.

Usage:
   uv run --extra scripts python scripts/get_cookies_easy.py

First run installs Chromium automatically if needed.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.sync_api import BrowserContext

CONFIG_DIR = Path.home() / ".config" / "amazon-photos-mcp"
COOKIE_FILE = CONFIG_DIR / "cookies.json"
REQUIRED_COOKIES = {"ubid-main", "at-main", "session-id"}


def _extract_cookies(context: BrowserContext) -> dict[str, str]:
    """Extract required Amazon cookies from the browser context."""
    cookies: dict[str, str] = {}
    for c in context.cookies():
        if c["name"] in REQUIRED_COOKIES and c.get("value"):
            cookies[c["name"]] = c["value"]
    return cookies


def main() -> None:
    # Force UTF-8 output on Windows
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        import io

        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

    print("Amazon Photos MCP -- Easy Cookie Setup")
    print("=" * 42)
    print()

    # Try playwright import
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Playwright not installed. Run:")
        print("  uv add --optional scripts playwright")
        print("  playwright install chromium")
        sys.exit(1)

    # Warn if existing cookies
    if COOKIE_FILE.exists():
        age_h = (time.time() - COOKIE_FILE.stat().st_mtime) / 3600
        print(f"Existing cookies found ({age_h:.0f}h old).")
        answer = input("Overwrite? [y/N] ").strip().lower()
        if answer not in ("y", "yes"):
            print("Keeping existing cookies.")
            return
        print()

    print("A browser window will open to amazon.com/photos.")
    print("Sign in if needed, then press Enter in THIS terminal.")
    print()

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
        )
        context = browser.new_context()
        page = context.new_page()

        try:
            # Navigate and wait for user sign-in
            page.goto("https://www.amazon.com/photos", wait_until="domcontentloaded")
            print("Browser opened. ", end="")

            # Check if already signed in (cookies present before user interaction)
            cookies = _extract_cookies(context)
            if set(cookies.keys()) == REQUIRED_COOKIES:
                print("Already signed in -- no action needed.")
            else:
                print("Sign in to Amazon, then press Enter in this terminal...", flush=True)

            # Wait for user (blocks; Ctrl+C to abort if stuck)
            try:
                input()
            except EOFError:
                pass

            # Extract cookies
            cookies = _extract_cookies(context)
            missing = REQUIRED_COOKIES - set(cookies.keys())

            # Retry if missing
            if missing:
                print(f"\nMissing cookies: {', '.join(sorted(missing))}")
                print("Make sure you're signed in to amazon.com/photos.")
                retry = input("Try again? [Y/n] ").strip().lower()
                if retry in ("", "y", "yes"):
                    page.goto("https://www.amazon.com/photos")
                    print("Check that you're signed in, then press Enter...")
                    try:
                        input()
                    except EOFError:
                        pass
                    cookies = _extract_cookies(context)
                    missing = REQUIRED_COOKIES - set(cookies.keys())
                    if missing:
                        print(f"Still missing: {', '.join(sorted(missing))}")
                        print("Run the script again when you're signed in.")
                        return
                else:
                    return

            if not cookies:
                print("No Amazon cookies found. Exiting.")
                return

        finally:
            browser.close()

    # Save
    # Add underscore variants for library compatibility
    output = dict(cookies)
    for hyphen, underscore in [("ubid-main", "ubid_main"), ("at-main", "at_main")]:
        if hyphen in output:
            output[underscore] = output[hyphen]

    try:
        from amazon_photos_mcp.crypto import save_encrypted_cookies

        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        save_encrypted_cookies(COOKIE_FILE, output)
        print(f"Cookies saved (encrypted) to {COOKIE_FILE}")
    except ImportError:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        COOKIE_FILE.write_text(json.dumps(output, indent=2))
        print(f"\nCookies saved to {COOKIE_FILE}")
    print("Values (truncated):")
    for k in sorted(cookies):
        print(f"  {k}: {cookies[k][:8]}...")
    print()
    print("Done. In Claude Code, call refresh_client to activate.")
    print("Cookies expire after ~72 hours. Re-run this script when they do.")


if __name__ == "__main__":
    main()
