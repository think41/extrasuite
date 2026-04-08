"""
CLI for extradocx.

Usage::

    python -m extradocx <input.docx> [--output-dir DIR] [--json] [--markdown]

Outputs:
  <basename>.ast.json   — full-fidelity AST JSON
  <basename>.md         — GFM markdown
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from extradocx import DocxParser, to_json, to_markdown


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="extradocx",
        description="Convert a Microsoft Word .docx to GFM Markdown via an AST.",
    )
    parser.add_argument("docx", metavar="INPUT.docx", help="Path to the .docx file")
    parser.add_argument(
        "--output-dir",
        "-o",
        default=None,
        help="Directory for output files (default: same dir as INPUT.docx)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        default=True,
        help="Write AST as JSON (default: on)",
    )
    parser.add_argument(
        "--no-json",
        dest="json",
        action="store_false",
        help="Disable JSON output",
    )
    parser.add_argument(
        "--markdown",
        action="store_true",
        default=True,
        help="Write GFM markdown (default: on)",
    )
    parser.add_argument(
        "--no-markdown",
        dest="markdown",
        action="store_false",
        help="Disable markdown output",
    )
    args = parser.parse_args(argv)

    docx_path = Path(args.docx)
    if not docx_path.exists():
        print(f"error: file not found: {docx_path}", file=sys.stderr)
        return 1
    if not docx_path.suffix.lower() == ".docx":
        print(f"warning: file doesn't have .docx extension: {docx_path}", file=sys.stderr)

    out_dir = Path(args.output_dir) if args.output_dir else docx_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = docx_path.stem

    print(f"Parsing {docx_path} …", flush=True)
    doc = DocxParser(docx_path).parse()

    if args.json:
        json_path = out_dir / f"{stem}.ast.json"
        json_str = to_json(doc)
        json_path.write_text(json_str, encoding="utf-8")
        print(f"  AST JSON → {json_path}  ({len(json_str):,} bytes)")

    if args.markdown:
        md_path = out_dir / f"{stem}.md"
        md_str = to_markdown(doc)
        md_path.write_text(md_str, encoding="utf-8")
        print(f"  Markdown → {md_path}  ({len(md_str):,} bytes)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
