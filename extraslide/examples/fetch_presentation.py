#!/usr/bin/env python3
"""Fetch a Google Slides presentation as JSON and save it."""

import json
import sys
from pathlib import Path

# Add src to path for development
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from gslidesx import SlidesClient


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python fetch_presentation.py <gateway_url> [presentation_url]")
        print("\nExample:")
        print("  python fetch_presentation.py https://gateway.example.com")
        return 1

    gateway_url = sys.argv[1]
    presentation_url = (
        sys.argv[2]
        if len(sys.argv) > 2
        else "https://docs.google.com/presentation/d/1IKB5XEh3ZAyhjYDmXft3K4wKjm43X9m6t-mcwsE_WvY/edit"
    )

    client = SlidesClient(gateway_url=gateway_url)

    print(f"Fetching presentation from: {presentation_url}")
    presentation_json = client.fetch_json(presentation_url)

    # Extract presentation ID for filename
    presentation_id = client._extract_presentation_id(presentation_url)
    output_path = Path(__file__).parent / "json" / f"{presentation_id}.json"

    output_path.write_text(json.dumps(presentation_json, indent=2))
    print(f"Saved to: {output_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
