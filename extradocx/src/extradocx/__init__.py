"""
extradocx — experimental DOCX → GFM Markdown AST converter.

Proof-of-concept for bidirectional DOCX ↔ Markdown transformation via an
intermediate AST that:
  - Represents GFM markdown structure (headings, lists, tables, …)
  - Preserves text at run granularity (bold, italic, … per TextRun node)
  - Points every node back to the source DOCX XML via XPath

Usage::

    from extradocx import DocxParser, to_json, to_markdown

    parser = DocxParser("report.docx")
    doc = parser.parse()

    json_str = to_json(doc)        # full-fidelity JSON with XPath pointers
    md_str = to_markdown(doc)      # GFM markdown
"""

from extradocx.parser import DocxParser
from extradocx.serializers import to_json, to_markdown

__all__ = ["DocxParser", "to_json", "to_markdown"]
