"""Serde module: Document ↔ folder of files (XML or markdown).

Protocol:
    class Serde:
        serialize(bundle, folder) -> None
        deserialize(folder) -> DeserializeResult

Implementations:
    XmlSerde      -- extradoc.serde.xml.XmlSerde
    MarkdownSerde -- extradoc.serde.markdown.MarkdownSerde
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from ._models import IndexXml, TabFiles, TabXml
from ._styles import StylesXml

if TYPE_CHECKING:
    from pathlib import Path

    from extradoc.comments._types import DocumentWithComments


@dataclass
class DeserializeResult:
    """Result of deserializing a folder."""

    base: DocumentWithComments
    desired: DocumentWithComments


@runtime_checkable
class Serde(Protocol):
    """Interface for serialize / deserialize implementations."""

    def serialize(self, bundle: DocumentWithComments, folder: Path) -> None:
        """Write a DocumentWithComments to a folder.

        Writes content files, .pristine/document.zip, and any internal
        state needed for a future deserialize round-trip.

        Args:
            bundle: The DocumentWithComments to serialize
            folder: Root directory to write into
        """
        ...

    def deserialize(self, folder: Path) -> DeserializeResult:
        """Read a folder and return both the base and desired documents.

        Base is reconstructed from internal state written by serialize.
        Desired reflects the user's edits merged onto base.

        Args:
            folder: Path to the document folder

        Returns:
            DeserializeResult with base and desired DocumentWithComments
        """
        ...


__all__ = [
    "DeserializeResult",
    "IndexXml",
    "Serde",
    "StylesXml",
    "TabFiles",
    "TabXml",
]
