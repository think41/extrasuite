"""extraslide - Edit Google Slides through SML (Slide Markup Language)."""

from extraslide.client import SlidesClient, diff_folder, pull_presentation
from extraslide.transport import (
    APIError,
    AuthenticationError,
    GoogleSlidesTransport,
    LocalFileTransport,
    NotFoundError,
    PresentationData,
    Transport,
    TransportError,
)

__all__ = [
    "APIError",
    "AuthenticationError",
    "GoogleSlidesTransport",
    "LocalFileTransport",
    "NotFoundError",
    "PresentationData",
    "SlidesClient",
    "Transport",
    "TransportError",
    "diff_folder",
    "pull_presentation",
]

__version__ = "0.1.0"
