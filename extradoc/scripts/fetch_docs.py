"""Script to fetch Google Docs and save raw JSON locally."""

import asyncio
import json
from pathlib import Path

import keyring

from extradoc.transport import GoogleDocsTransport


def get_token() -> str:
    """Read token from OS keyring."""
    token_json = keyring.get_password("extrasuite", "token")
    if not token_json:
        raise ValueError(
            "No token found in keyring. Run 'extrasheet pull' first to authenticate."
        )
    token_data = json.loads(token_json)
    return token_data["access_token"]


async def fetch_document(document_id: str, output_dir: Path) -> None:
    """Fetch a document and save the raw JSON."""
    token = get_token()

    # Create transport and fetch
    transport = GoogleDocsTransport(access_token=token)
    try:
        doc = await transport.get_document(document_id)

        # Save raw JSON
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = output_dir / f"{document_id}.json"
        output_file.write_text(json.dumps(doc.raw, indent=2))
        print(f"Saved: {output_file}")

    finally:
        await transport.close()


async def main() -> None:
    # Document IDs from the URLs
    doc_ids = [
        "1arcBS-A_LqbvrstLAADAjCZj4kvTlqmQ0ztFNfyAEyc",
        "1tlHGpgjoibP0eVXRvCGSmkqrLATrXYTo7dUnmV7x01o",
    ]

    output_dir = Path(__file__).parent.parent / "tests" / "golden"

    for doc_id in doc_ids:
        print(f"Fetching {doc_id}...")
        await fetch_document(doc_id, output_dir)


if __name__ == "__main__":
    asyncio.run(main())
