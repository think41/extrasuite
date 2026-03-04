"""Extra per-tab XML files for round-trip fidelity.

These files store document-level metadata that doesn't fit in document.xml
or styles.xml: DocumentStyle, NamedStyles, InlineObjects, PositionedObjects,
and NamedRanges.

Each is stored as a single XML element with JSON-encoded content, since these
types have deeply nested structures that would be complex to represent in XML.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from xml.etree.ElementTree import Element, fromstring

from ._utils import element_to_string


@dataclass
class DocStyleXml:
    """Per-tab docstyle.xml — wraps DocumentStyle as JSON."""

    data: dict[str, Any]

    def to_xml_string(self) -> str:
        root = Element("docstyle")
        root.text = json.dumps(self.data, separators=(",", ":"))
        return element_to_string(root)

    @classmethod
    def from_xml_string(cls, xml: str) -> DocStyleXml:
        root = fromstring(xml)
        data = json.loads(root.text or "{}")
        return cls(data=data)


@dataclass
class NamedStylesXml:
    """Per-tab namedstyles.xml — wraps NamedStyles as JSON."""

    data: dict[str, Any]

    def to_xml_string(self) -> str:
        root = Element("namedstyles")
        root.text = json.dumps(self.data, separators=(",", ":"))
        return element_to_string(root)

    @classmethod
    def from_xml_string(cls, xml: str) -> NamedStylesXml:
        root = fromstring(xml)
        data = json.loads(root.text or "{}")
        return cls(data=data)


@dataclass
class InlineObjectsXml:
    """Per-tab objects.xml — wraps inlineObjects dict as JSON."""

    data: dict[str, Any]

    def to_xml_string(self) -> str:
        root = Element("inlineObjects")
        root.text = json.dumps(self.data, separators=(",", ":"))
        return element_to_string(root)

    @classmethod
    def from_xml_string(cls, xml: str) -> InlineObjectsXml:
        root = fromstring(xml)
        data = json.loads(root.text or "{}")
        return cls(data=data)


@dataclass
class PositionedObjectsXml:
    """Per-tab positionedObjects.xml — wraps positionedObjects dict as JSON."""

    data: dict[str, Any]

    def to_xml_string(self) -> str:
        root = Element("positionedObjects")
        root.text = json.dumps(self.data, separators=(",", ":"))
        return element_to_string(root)

    @classmethod
    def from_xml_string(cls, xml: str) -> PositionedObjectsXml:
        root = fromstring(xml)
        data = json.loads(root.text or "{}")
        return cls(data=data)


@dataclass
class NamedRangesXml:
    """Per-tab namedranges.xml — wraps namedRanges dict as JSON."""

    data: dict[str, Any]

    def to_xml_string(self) -> str:
        root = Element("namedRanges")
        root.text = json.dumps(self.data, separators=(",", ":"))
        return element_to_string(root)

    @classmethod
    def from_xml_string(cls, xml: str) -> NamedRangesXml:
        root = fromstring(xml)
        data = json.loads(root.text or "{}")
        return cls(data=data)
