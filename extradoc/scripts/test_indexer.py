"""Test the index calculator against real Google Docs."""

import json
from pathlib import Path

from extradoc.indexer import validate_document


def main() -> None:
    golden_dir = Path(__file__).parent.parent / "tests" / "golden"

    for json_file in golden_dir.glob("*.json"):
        print(f"\n{'=' * 60}")
        print(f"Testing: {json_file.name}")
        print("=" * 60)

        document = json.loads(json_file.read_text())
        result = validate_document(document)

        print(f"\nTitle: {document.get('title', 'Unknown')}")
        print(f"Elements checked: {result.total_elements_checked}")

        if result.is_valid:
            print("\n✓ All indexes are correct!")
        else:
            print(f"\n✗ Found {len(result.mismatches)} mismatches:")
            for i, mismatch in enumerate(result.mismatches[:20]):  # Show first 20
                print(f"  {i + 1}. {mismatch}")
            if len(result.mismatches) > 20:
                print(f"  ... and {len(result.mismatches) - 20} more")


if __name__ == "__main__":
    main()
