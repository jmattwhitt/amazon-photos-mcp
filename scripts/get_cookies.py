"""
Automatically extract Amazon Photos cookies from your browser and save them
to the MCP config file.

Usage:
    uv run --extra scripts python scripts/get_cookies.py [--browser chrome|edge|firefox|brave]
    uv run --extra scripts python scripts/get_cookies.py --manual

Chrome 127+ and Edge 130+ use app-bound encryption that rookie-rs cannot
decrypt -- even with administrator privileges. Use Firefox (recommended) or
--manual mode for these browsers.

Requires: rookiepy (installed via `uv add --optional scripts rookiepy`)
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

CONFIG_DIR = Path.home() / ".config" / "amazon-photos-mcp"
COOKIE_FILE = CONFIG_DIR / "cookies.json"

REQUIRED_COOKIES = {"ubid-main", "at-main", "session-id"}
AMAZON_DOMAINS = {".amazon.com", "amazon.com", ".www.amazon.com"}

BROWSERS = ["firefox", "chrome", "edge", "brave", "opera", "chromium", "vivaldi", "librewolf"]

# Firefox stores cookies in plain SQLite -- no encryption, no admin needed.
# Chrome 127+ / Edge 130+ app-bound encryption is NOT supported by rookie-rs
# even with admin rights (upstream bugs #84, #95).

APP_BOUND_MSG = "appbound"   # substring rookiepy puts in the error message


def _extract_from_browser(browser_name: str) -> dict[str, str]:
    """Extract Amazon cookies from a specific browser. Raises on failure."""
    try:
        import rookiepy
    except ImportError:
        print("ERROR: rookiepy not installed. Run:")
        print("  uv add --optional scripts rookiepy")
        sys.exit(1)

    fn = getattr(rookiepy, browser_name, None)
    if fn is None:
        raise ValueError(f"Browser '{browser_name}' not supported.")

    raw = fn(["amazon.com"])

    cookies: dict[str, str] = {}
    for c in raw:
        host = c.get("host", "")
        name = c.get("name", "")
        value = c.get("value", "")
        if any(host.endswith(d) for d in AMAZON_DOMAINS) and name in REQUIRED_COOKIES and value:
            cookies[name] = value
    return cookies


def _try_all_browsers(preferred: str | None) -> tuple[str, dict[str, str]]:
    """Try browsers in order. Prints app-bound advice when blocked, falls
    through to manual-fallback when all browsers fail."""
    order = BROWSERS[:]
    if preferred:
        order = [preferred] + [b for b in order if b != preferred]

    app_bound_browsers: list[str] = []
    other_errors: list[str] = []

    for browser in order:
        try:
            cookies = _extract_from_browser(browser)
            if cookies:
                return browser, cookies
        except Exception as e:
            msg = str(e).lower()
            if APP_BOUND_MSG in msg:
                app_bound_browsers.append(browser)
            else:
                other_errors.append(f"  {browser}: {e}")

    # --- App-bound encryption: clear advice instead of exit code 2 ---
    if app_bound_browsers:
        _print_app_bound_advice(app_bound_browsers)

    # --- Other errors (or nothing found) ---
    if other_errors:
        print("\nCould not extract Amazon cookies from any browser:")
        for e in other_errors:
            print(e)

    _print_manual_fallback()
    sys.exit(1)


def _print_app_bound_advice(browsers: list[str]) -> None:
    """Explain the rookie-rs app-bound encryption limitation."""
    names = ", ".join(browsers)
    print(f"\n{names} uses app-bound cookie encryption (Chrome 127+ / Edge 130+).")
    print("rookie-rs (the underlying Rust library) cannot decrypt these cookies --")
    print("even with administrator privileges. This is a known upstream limitation:")
    print("  https://github.com/thewh1teagle/rookie/issues/84")
    print("  https://github.com/thewh1teagle/rookie/issues/95")
    print()
    print("Two options:")
    print("  1. Install Firefox, sign in to amazon.com, then re-run this script.")
    print("     Firefox stores cookies in plain SQLite -- no encryption, no admin needed.")
    print("  2. Use --manual mode to paste cookies from Chrome/Edge DevTools:")
    print("     uv run --extra scripts python scripts/get_cookies.py --manual")


def _manual_mode() -> None:
    """Interactive manual cookie entry from browser DevTools."""
    print("\nManual Cookie Entry")
    print("=" * 50)
    print()
    print("1. Open https://www.amazon.com/photos in your browser and sign in.")
    print("2. Press F12 to open DevTools.")
    print("3. Go to Application tab > Cookies > https://www.amazon.com")
    print("4. Copy the VALUE for each cookie below.")
    print("   (Press Enter to skip optional cookies.)")
    print()
    print("Required cookies:")
    for k in sorted(REQUIRED_COOKIES):
        print(f"  {k}")
    print()

    cookies: dict[str, str] = {}
    for key in sorted(REQUIRED_COOKIES):
        value = input(f"  {key}: ").strip()
        if value:
            cookies[key] = value

    missing = REQUIRED_COOKIES - set(cookies.keys())
    if missing:
        print(f"\nERROR: Missing cookies: {', '.join(sorted(missing))}")
        sys.exit(1)

    _validate(cookies)
    _write(cookies)
    print(f"\nCookies saved to {COOKIE_FILE}")


def _print_manual_fallback() -> None:
    print("\n--- Manual fallback ---")
    print("1. Open https://www.amazon.com/photos in your browser and sign in.")
    print("2. Press F12 > Application tab > Cookies > https://www.amazon.com")
    print("3. Copy the values for: ubid-main, at-main, session-id")
    print(f"4. Create: {COOKIE_FILE}")
    print('   Contents: {"ubid-main":"...", "at-main":"...", "session-id":"..."}')
    print("\nOr use --manual for interactive prompts:")
    print("  uv run --extra scripts python scripts/get_cookies.py --manual")


def _validate(cookies: dict[str, str]) -> None:
    missing = REQUIRED_COOKIES - set(cookies.keys())
    empty = {k for k, v in cookies.items() if k in REQUIRED_COOKIES and not v.strip()}
    problems = missing | empty
    if problems:
        print(f"\nWARNING: Missing or empty cookies: {', '.join(sorted(problems))}")
        print("Make sure you are signed in to amazon.com in your browser.")
        if missing == REQUIRED_COOKIES:
            sys.exit(1)


def _write(cookies: dict[str, str]) -> None:
    """Write cookies.json including both hyphen and underscore variants."""
    output = dict(cookies)
    # amazon_photos library needs underscore variants for TLD detection
    for hyphen, underscore in [("ubid-main", "ubid_main"), ("at-main", "at_main")]:
        if hyphen in output:
            output[underscore] = output[hyphen]

    try:
        from amazon_photos_mcp.crypto import save_encrypted_cookies

        save_encrypted_cookies(COOKIE_FILE, output)
        print(f"Cookies saved (encrypted) to {COOKIE_FILE}")
    except ImportError:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        COOKIE_FILE.write_text(json.dumps(output, indent=2))
        print(f"Cookies saved (plaintext) to {COOKIE_FILE}")
        try:
            import stat
            COOKIE_FILE.chmod(stat.S_IRUSR | stat.S_IWUSR)
        except Exception:
            pass  # Windows may not honor Unix perms -- not fatal


def main() -> None:
    # Force UTF-8 stdout on Windows so any stray non-ASCII doesn't crash cp1252
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="Extract Amazon cookies from your browser and save to MCP config."
    )
    parser.add_argument(
        "--browser",
        choices=BROWSERS,
        default=None,
        help="Specific browser to try first (default: tries Chrome then Edge then others).",
    )
    parser.add_argument(
        "--show",
        action="store_true",
        help="Print first 12 chars of each saved cookie value (for debugging).",
    )
    parser.add_argument(
        "--manual",
        action="store_true",
        help="Skip browser extraction; enter cookie values from DevTools interactively.",
    )
    args = parser.parse_args()

    print("Amazon Photos MCP -- Cookie Extractor")
    print("=" * 42)

    # --manual mode: skip browser extraction entirely
    if args.manual:
        if COOKIE_FILE.exists():
            age_h = (time.time() - COOKIE_FILE.stat().st_mtime) / 3600
            print(f"\nExisting cookies found ({age_h:.0f}h old) at:\n  {COOKIE_FILE}")
            answer = input("Overwrite? [y/N] ").strip().lower()
            if answer not in ("y", "yes"):
                print("Aborted -- existing cookies kept.")
                sys.exit(0)
        _manual_mode()
        if args.show and COOKIE_FILE.exists():
            cookies = json.loads(COOKIE_FILE.read_text())
            print("\nValues (truncated):")
            for k in sorted(cookies):
                v = cookies[k]
                print(f"  {k}: {v[:12]}...")
        print("\nDone. To activate:")
        print("  * If Claude Code is open: call the 'refresh_client' MCP tool")
        print("  * Otherwise: restart Claude Code")
        return

    # Warn if existing cookies are present
    if COOKIE_FILE.exists():
        age_h = (time.time() - COOKIE_FILE.stat().st_mtime) / 3600
        print(f"\nExisting cookies found ({age_h:.0f}h old) at:\n  {COOKIE_FILE}")
        answer = input("Overwrite? [y/N] ").strip().lower()
        if answer not in ("y", "yes"):
            print("Aborted -- existing cookies kept.")
            sys.exit(0)

    print("\nSearching browser cookie stores...")
    browser_used, cookies = _try_all_browsers(preferred=args.browser)
    print(f"  Found cookies in: {browser_used}")

    _validate(cookies)

    found = sorted(cookies.keys() & REQUIRED_COOKIES)
    print(f"  Extracted: {', '.join(found)}")

    _write(cookies)
    print(f"\nSaved to:\n  {COOKIE_FILE}")

    if args.show:
        print("\nValues (truncated):")
        for k in sorted(cookies):
            v = cookies[k]
            print(f"  {k}: {v[:12]}...")

    print("\nDone. To activate:")
    print("  * Claude Code open: call the 'refresh_client' MCP tool")
    print("  * Otherwise: restart Claude Code")
    print("\nCookies will expire in ~72h. Re-run this script when they do.")


if __name__ == "__main__":
    main()
