#!/usr/bin/env python3
"""
Google Slides Skill - Verify Presentation Access

Usage: venv/bin/python verify_access.py <presentation_url>

Exit codes:
  0 - Success (presentation info printed to stdout)
  1 - Authentication error
  2 - Presentation not found or not shared
  3 - API not enabled
  4 - Rate limit exceeded
  5 - Invalid URL format
  6 - Other API error

Prerequisites: Run checks.py first to set up the environment.
"""

import contextlib
import json
import re
import ssl
import sys
import urllib.error
import urllib.request

from credentials import CredentialsManager

try:
    import certifi

    SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    SSL_CONTEXT = ssl.create_default_context()


def extract_presentation_id(url):
    """Extract presentation ID from URL. Returns (id, error_msg)."""
    if not url.startswith("http"):
        # Assume it's already an ID
        return url, None

    # Expected: https://docs.google.com/presentation/d/PRESENTATION_ID/...
    pattern = r"/presentation/d/([a-zA-Z0-9_-]+)"
    match = re.search(pattern, url)
    if match:
        return match.group(1), None

    return (
        None,
        f"Invalid Google Slides URL format.\n\nExpected: https://docs.google.com/presentation/d/PRESENTATION_ID/edit\nGot: {url}",
    )


def main():
    if len(sys.argv) < 2:
        print(
            "Usage: venv/bin/python verify_access.py <presentation_url>",
            file=sys.stderr,
        )
        print("\nExample:", file=sys.stderr)
        print(
            "  venv/bin/python verify_access.py https://docs.google.com/presentation/d/abc123/edit",
            file=sys.stderr,
        )
        sys.exit(1)

    url = sys.argv[1]
    presentation_id, error = extract_presentation_id(url)
    if error:
        print(error, file=sys.stderr)
        sys.exit(5)

    # Authenticate via ExtraSuite
    try:
        manager = CredentialsManager()
        token = manager.get_token()
        access_token = token.access_token
    except Exception as e:
        print(
            f"""Authentication failed.

Error: {e}

Please try again. If the problem persists, check:
- Your internet connection
- The ExtraSuite server is accessible""",
            file=sys.stderr,
        )
        sys.exit(1)

    client_email = token.service_account_email or "your service account"

    # Fetch presentation metadata
    api_url = f"https://slides.googleapis.com/v1/presentations/{presentation_id}"
    req = urllib.request.Request(
        api_url,
        headers={"Authorization": f"Bearer {access_token}"},
        method="GET",
    )

    try:
        with urllib.request.urlopen(req, timeout=60, context=SSL_CONTEXT) as response:
            presentation = json.loads(response.read().decode("utf-8"))

        # Success - print presentation info
        title = presentation.get("title", "Untitled")
        slides = presentation.get("slides", [])
        print(f"Presentation: {title}")
        print(f"Slides: {len(slides)}")
        sys.exit(0)

    except urllib.error.HTTPError as e:
        error_body = ""
        with contextlib.suppress(Exception):
            error_body = e.read().decode("utf-8")

        pres_url = f"https://docs.google.com/presentation/d/{presentation_id}/edit"

        if e.code == 404:
            print(
                f"""Presentation (ID: {presentation_id}) not found.

The presentation does not exist or has been deleted.

Please verify:
- The URL is correct
- The presentation has not been deleted""",
                file=sys.stderr,
            )
            sys.exit(2)

        elif e.code == 403:
            # Check for API not enabled
            api_not_enabled_patterns = [
                "PERMISSION_DENIED",
                "accessNotConfigured",
                "has not been used in project",
                "API has not been used",
                "is disabled",
                "Enable it by visiting",
            ]
            is_api_not_enabled = any(pattern in error_body for pattern in api_not_enabled_patterns)

            if is_api_not_enabled:
                print(
                    """Google Slides API is not enabled for the service account's project.

This is a server-side configuration issue. Please contact the administrator
of the ExtraSuite server.""",
                    file=sys.stderr,
                )
                sys.exit(3)

            # Generic 403 - likely not shared
            print(
                f"""Presentation (ID: {presentation_id}) - Access forbidden.

To fix this:
1. Open the presentation: {pres_url}
2. Click the "Share" button (top right)
3. In the "Add people" field, enter: {client_email}
4. Select role: Editor (or Viewer if read-only access is sufficient)
5. Click "Send"

Then run this command again.""",
                file=sys.stderr,
            )
            sys.exit(2)

        elif e.code == 429:
            print(
                """Rate limit exceeded.

Google Slides API has usage quotas. Please wait 1-2 minutes and try again.""",
                file=sys.stderr,
            )
            sys.exit(4)

        else:
            print(
                f"""Presentation (ID: {presentation_id}) - Unable to access.

Error: HTTP {e.code}: {error_body}

Possible fixes:
1. Ensure the presentation is shared with: {client_email}
2. Verify the URL is correct: {pres_url}

Then run this command again.""",
                file=sys.stderr,
            )
            sys.exit(6)

    except urllib.error.URLError as e:
        print(
            f"""Network error while accessing Google Slides API.

Error: {e}

Please check your internet connection and try again.""",
            file=sys.stderr,
        )
        sys.exit(6)

    except Exception as e:
        pres_url = f"https://docs.google.com/presentation/d/{presentation_id}/edit"
        print(
            f"""Presentation (ID: {presentation_id}) - Unable to access.

Error: {type(e).__name__}: {e}

Possible fixes:
1. Ensure the presentation is shared with: {client_email}
2. Verify the URL is correct: {pres_url}

Then run this command again.""",
            file=sys.stderr,
        )
        sys.exit(6)


if __name__ == "__main__":
    main()
