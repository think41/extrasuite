#!/usr/bin/env python3
"""Manual authentication flow test script.

Guides tester through auth scenarios with minimal prompts.
Only asks for input when user action is required.
"""

from __future__ import annotations

import argparse
import json
import os
import stat
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from extrasuite_client import ExtraSuiteClient

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
BOLD = "\033[1m"
RESET = "\033[0m"

TOKEN_CACHE_PATH = Path.home() / ".config" / "extrasuite" / "token.json"


def header(text: str) -> None:
    print(f"\n{BOLD}{BLUE}=== {text} ==={RESET}\n")


def info(text: str) -> None:
    print(f"  {text}")


def success(text: str) -> None:
    print(f"  {GREEN}✓ {text}{RESET}")


def fail(text: str) -> None:
    print(f"  {RED}✗ {text}{RESET}")


def prompt(message: str) -> None:
    input(f"\n{YELLOW}→ {message}{RESET}")


def delete_token_cache() -> None:
    if TOKEN_CACHE_PATH.exists():
        TOKEN_CACHE_PATH.unlink()


def expire_token_cache() -> bool:
    if not TOKEN_CACHE_PATH.exists():
        return False
    data = json.loads(TOKEN_CACHE_PATH.read_text())
    data["expires_at"] = time.time() - 3600
    TOKEN_CACHE_PATH.write_text(json.dumps(data, indent=2))
    return True


def get_token(server_url: str) -> bool:
    try:
        client = ExtraSuiteClient(server_url=server_url)
        token = client.get_token()
        return bool(token)
    except Exception as e:
        fail(str(e))
        return False


def check_permissions() -> tuple[bool, bool]:
    """Returns (file_ok, dir_ok)."""
    if not TOKEN_CACHE_PATH.exists():
        return False, False
    file_perms = stat.S_IMODE(os.stat(TOKEN_CACHE_PATH).st_mode)
    dir_perms = stat.S_IMODE(os.stat(TOKEN_CACHE_PATH.parent).st_mode)
    return file_perms == 0o600, dir_perms == 0o700


def scenario_1(server_url: str) -> bool:
    """No token - first time auth."""
    header("Scenario 1: First-time Auth (no cached token)")
    delete_token_cache()
    info("Token cache deleted. Browser will open.")

    if get_token(server_url):
        success("Authentication successful")
        return True
    else:
        fail("Authentication failed")
        return False


def scenario_2(server_url: str) -> bool:
    """Cached token - no browser."""
    header("Scenario 2: Cached Token (browser should NOT open)")

    if not TOKEN_CACHE_PATH.exists():
        fail("No cached token - run scenario 1 first")
        return False

    info("Using cached token...")
    if get_token(server_url):
        success("Returned cached token without browser")
        return True
    else:
        fail("Failed to use cached token")
        return False


def scenario_3(server_url: str) -> bool:
    """Expired token - re-auth."""
    header("Scenario 3: Expired Token (re-authentication)")

    if not expire_token_cache():
        fail("No cached token to expire - run scenario 1 first")
        return False

    info("Token expired. Browser will open for re-auth.")

    if get_token(server_url):
        success("Re-authentication successful")
        return True
    else:
        fail("Re-authentication failed")
        return False


def scenario_4(server_url: str) -> bool:
    """No session - full OAuth."""
    header("Scenario 4: No Server Session (full Google OAuth)")

    prompt("Clear cookies for extrasuite.think41.com in your browser, then press Enter...")

    delete_token_cache()
    info("Token cache deleted. Browser will open for full OAuth flow.")

    if get_token(server_url):
        success("Full OAuth flow successful")
        return True
    else:
        fail("Full OAuth flow failed")
        return False


def scenario_5(server_url: str) -> bool:
    """New user - SA creation."""
    header("Scenario 5: New User (service account creation)")

    prompt("Delete your user record from Firestore 'users' collection, then press Enter...")

    delete_token_cache()
    info("Token cache deleted. Browser will open. Server will create new SA.")

    if get_token(server_url):
        success("New user flow successful")
        return True
    else:
        fail("New user flow failed")
        return False


def scenario_6(server_url: str) -> bool:
    """Security checks."""
    header("Scenario 6: Security Verification")

    if not TOKEN_CACHE_PATH.exists():
        fail("No token cache - run scenario 1 first")
        return False

    file_ok, dir_ok = check_permissions()

    if file_ok:
        success("Token file permissions: 0600")
    else:
        fail("Token file permissions incorrect")

    if dir_ok:
        success("Directory permissions: 0700")
    else:
        fail("Directory permissions incorrect")

    return file_ok and dir_ok


def main() -> int:
    parser = argparse.ArgumentParser(description="Auth flow tests")
    parser.add_argument("--server", required=True, help="Server URL")
    parser.add_argument("--scenario", type=int, choices=[1, 2, 3, 4, 5, 6], help="Run specific scenario")
    args = parser.parse_args()

    scenarios = {
        1: scenario_1,
        2: scenario_2,
        3: scenario_3,
        4: scenario_4,
        5: scenario_5,
        6: scenario_6,
    }

    if args.scenario:
        to_run = [args.scenario]
    else:
        to_run = [1, 2, 3, 4, 5, 6]

    results = {}
    for num in to_run:
        try:
            results[num] = scenarios[num](args.server)
        except KeyboardInterrupt:
            print(f"\n{YELLOW}Interrupted{RESET}")
            results[num] = False
            break
        except Exception as e:
            fail(f"Exception: {e}")
            results[num] = False

    # Summary
    header("Results")
    for num, passed in results.items():
        status = f"{GREEN}PASS{RESET}" if passed else f"{RED}FAIL{RESET}"
        print(f"  Scenario {num}: {status}")

    passed = sum(1 for v in results.values() if v)
    print(f"\n  {BOLD}{passed}/{len(results)} passed{RESET}")

    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
