"""
Google Slides Utility Library

Functions that extend extraslide with additional capabilities:
- open_presentation(): Get SlidesClient with automatic ExtraSuite authentication
- get_thumbnail(): Download a slide thumbnail image (expensive - use sparingly)
- get_service_account_email(): Get the service account email for sharing instructions

For SML-based editing, use extraslide directly:
- client.pull(url, path): Download presentation as SML
- client.diff(original, edited): Preview changes
- client.apply(url, original, edited): Apply changes
"""

import json
import ssl
import urllib.request
from pathlib import Path

from credentials import CredentialsManager
from extraslide import SlidesClient

try:
    import certifi

    SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    SSL_CONTEXT = ssl.create_default_context()

TOKEN_CACHE_PATH = Path.home() / ".config" / "extrasuite" / "token.json"
GATEWAY_CONFIG_PATH = Path.home() / ".config" / "extrasuite" / "gateway.json"


def _get_gateway_url():
    """Get the gateway URL from configuration."""
    if GATEWAY_CONFIG_PATH.exists():
        try:
            data = json.loads(GATEWAY_CONFIG_PATH.read_text())
            return data.get("EXTRASUITE_SERVER_URL")
        except (json.JSONDecodeError, OSError):
            pass
    return None


def open_presentation(url):
    """
    Create a SlidesClient configured for the given presentation URL.

    Uses ExtraSuite for automatic authentication.

    Args:
        url: Full Google Slides URL

    Returns:
        tuple: (SlidesClient, presentation_id)

    Example:
        client, pres_id = open_presentation("https://docs.google.com/presentation/d/abc123/edit")
        client.pull(url, "presentation.sml")
    """
    gateway_url = _get_gateway_url()
    if not gateway_url:
        raise ValueError(
            "No gateway URL configured. "
            "Install skills via the ExtraSuite website to configure gateway.json."
        )

    client = SlidesClient(gateway_url=gateway_url)
    pres_id = client._extract_presentation_id(url)
    return client, pres_id


def get_thumbnail(url, page_id, output_path=None, mime_type="PNG"):
    """
    Download a thumbnail image for a specific slide.

    WARNING: This is an expensive operation that counts against API quotas.
    Only use when the user reports formatting issues and you need to see
    how a slide actually looks.

    Args:
        url: Full Google Slides URL
        page_id: The objectId of the slide/page (from SML id attribute)
        output_path: Where to save the image (optional, defaults to {page_id}.png)
        mime_type: Image format - "PNG" (default) or "JPEG"

    Returns:
        dict with:
            - content_url: The temporary URL of the thumbnail
            - width: Thumbnail width in pixels
            - height: Thumbnail height in pixels
            - saved_to: Local path if output_path was provided

    Example:
        # Get thumbnail for slide with id="g12345678"
        result = get_thumbnail(
            "https://docs.google.com/presentation/d/abc123/edit",
            "g12345678",
            "slide_preview.png"
        )
        print(f"Saved to: {result['saved_to']}")
    """
    # Get credentials
    manager = CredentialsManager()
    token = manager.get_token()

    # Extract presentation ID
    client = SlidesClient(gateway_url=_get_gateway_url() or "")
    pres_id = client._extract_presentation_id(url)

    # Build thumbnail URL
    api_url = f"https://slides.googleapis.com/v1/presentations/{pres_id}/pages/{page_id}/thumbnail"
    if mime_type.upper() == "JPEG":
        api_url += "?thumbnailProperties.mimeType=JPEG"

    req = urllib.request.Request(
        api_url,
        headers={"Authorization": f"Bearer {token.access_token}"},
        method="GET",
    )

    with urllib.request.urlopen(req, timeout=60, context=SSL_CONTEXT) as response:
        data = json.loads(response.read().decode("utf-8"))

    result = {
        "content_url": data.get("contentUrl"),
        "width": data.get("width"),
        "height": data.get("height"),
    }

    # Download the image if output_path provided
    if output_path and result["content_url"]:
        img_req = urllib.request.Request(result["content_url"])
        with urllib.request.urlopen(img_req, timeout=60, context=SSL_CONTEXT) as img_response:
            img_data = img_response.read()

        output_file = Path(output_path)
        output_file.write_bytes(img_data)
        result["saved_to"] = str(output_file.resolve())

    return result


def get_service_account_email():
    """
    Get the service account email for sharing instructions.

    Reads from the cached token file created by ExtraSuite.
    Returns None if no token is cached.
    """
    if not TOKEN_CACHE_PATH.exists():
        return None

    try:
        with open(TOKEN_CACHE_PATH) as f:
            token_data = json.load(f)
        return token_data.get("service_account_email")
    except (json.JSONDecodeError, KeyError):
        return None


def list_slides(url):
    """
    List all slides in a presentation with their IDs and titles.

    Args:
        url: Full Google Slides URL

    Returns:
        list of dicts with slide info: id, index, title (if available)

    Example:
        slides = list_slides("https://docs.google.com/presentation/d/abc123/edit")
        for slide in slides:
            print(f"Slide {slide['index']}: {slide['id']}")
    """
    # Get credentials
    manager = CredentialsManager()
    token = manager.get_token()

    # Extract presentation ID
    gateway_url = _get_gateway_url() or ""
    client = SlidesClient(gateway_url=gateway_url)
    pres_id = client._extract_presentation_id(url)

    # Fetch presentation
    api_url = f"https://slides.googleapis.com/v1/presentations/{pres_id}"
    req = urllib.request.Request(
        api_url,
        headers={"Authorization": f"Bearer {token.access_token}"},
        method="GET",
    )

    with urllib.request.urlopen(req, timeout=60, context=SSL_CONTEXT) as response:
        data = json.loads(response.read().decode("utf-8"))

    slides = []
    for i, slide in enumerate(data.get("slides", [])):
        slide_info = {
            "id": slide.get("objectId"),
            "index": i + 1,
        }
        # Try to extract title from title placeholder
        for element in slide.get("pageElements", []):
            shape = element.get("shape", {})
            placeholder = shape.get("placeholder", {})
            if placeholder.get("type") == "TITLE":
                text_content = shape.get("text", {})
                text_elements = text_content.get("textElements", [])
                title_parts = []
                for te in text_elements:
                    text_run = te.get("textRun", {})
                    content = text_run.get("content", "")
                    if content.strip():
                        title_parts.append(content.strip())
                if title_parts:
                    slide_info["title"] = " ".join(title_parts)
                break
        slides.append(slide_info)

    return slides
