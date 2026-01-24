"""extraslide - Edit Google Slides through SML (Slide Markup Language)."""

from extraslide.client import SlidesClient
from extraslide.gateway import Gateway, GatewayError

__all__ = [
    "Gateway",
    "GatewayError",
    "SlidesClient",
]

__version__ = "0.1.0"
