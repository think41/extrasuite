"""Generate Google Sheets formula help docs from the exported formulas HTML table."""

from __future__ import annotations

import argparse
import re
import shutil
import textwrap
from dataclasses import dataclass
from html import unescape
from pathlib import Path

ROW_RE = re.compile(r'<tr[^>]*data-category="([^"]+)"[^>]*>(.*?)</tr>', re.S | re.I)
CELL_RE = re.compile(r"<td[^>]*>(.*?)</td>", re.S | re.I)
LINK_RE = re.compile(r'<a[^>]*href="([^"]+)"', re.I)
ANCHOR_RE = re.compile(r"<a\b[^>]*>.*?</a>", re.S | re.I)
TAG_RE = re.compile(r"<[^>]+>")
SUPPORT_ROOT = "https://support.google.com"


@dataclass
class FormulaRecord:
    category: str
    name: str
    syntax: str
    description: str
    url: str


def _strip_html(html: str) -> str:
    text = TAG_RE.sub("", html)
    text = unescape(text).replace("\xa0", " ")
    return " ".join(text.split())


def _absolute_url(url: str) -> str:
    if url.startswith("http://") or url.startswith("https://"):
        return url
    return f"{SUPPORT_ROOT}{url}"


def parse_formula_table(source_path: Path) -> tuple[list[str], dict[str, list[str]], dict[str, FormulaRecord]]:
    text = source_path.read_text("utf-8", errors="ignore")
    categories: list[str] = []
    overview: dict[str, list[str]] = {}
    records: dict[str, FormulaRecord] = {}

    for category, row_html in ROW_RE.findall(text):
        if category not in overview:
            categories.append(category)
            overview[category] = []

        cells = CELL_RE.findall(row_html)
        if len(cells) != 4:
            continue

        name = _strip_html(cells[1]).upper()
        syntax = _strip_html(cells[2])
        description_html = ANCHOR_RE.sub("", cells[3])
        description = _strip_html(description_html)
        url_match = LINK_RE.search(cells[3])
        if not name or url_match is None:
            continue

        url = _absolute_url(url_match.group(1))
        record = FormulaRecord(
            category=category,
            name=name,
            syntax=syntax,
            description=description,
            url=url,
        )

        existing = records.get(name)
        if existing is None:
            records[name] = record
            overview[category].append(name)
            continue

        # The upstream export currently includes `UNIQUE` twice. Keep the
        # original category placement in the overview, but retain the richer
        # syntax/details if a later duplicate is more complete.
        if len(record.syntax) > len(existing.syntax):
            records[name] = FormulaRecord(
                category=existing.category,
                name=name,
                syntax=record.syntax,
                description=record.description,
                url=record.url,
            )

    return categories, overview, records


def _formula_filename(name: str) -> str:
    slug = re.sub(r"[^a-z0-9._-]+", "-", name.lower()).strip("-")
    return f"{slug}.md"


def write_overview(output_dir: Path, categories: list[str], overview: dict[str, list[str]]) -> None:
    parts = ["# Formulas supported by Google Sheets", ""]
    for category in categories:
        names = overview[category]
        if not names:
            continue
        parts.append(f"## {category}")
        parts.append("")
        parts.append(
            textwrap.fill(
                ", ".join(names),
                width=88,
                break_long_words=False,
                break_on_hyphens=False,
            )
        )
        parts.append("")

    (output_dir / "formulas.md").write_text("\n".join(parts).rstrip() + "\n", "utf-8")


def write_formula_docs(output_dir: Path, records: dict[str, FormulaRecord]) -> None:
    formulas_dir = output_dir / "formulas"
    shutil.rmtree(formulas_dir, ignore_errors=True)
    formulas_dir.mkdir(parents=True, exist_ok=True)

    for name in sorted(records):
        record = records[name]
        content = "\n".join(
            [
                f"# {record.name}",
                "",
                record.syntax,
                "",
                record.description,
                "",
                f"To learn more, see {record.url}",
                "",
            ]
        )
        (formulas_dir / _formula_filename(record.name)).write_text(content, "utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_html", type=Path, help="Path to formulas.html")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("client/src/extrasuite/client/help/sheet"),
        help="Sheet help directory to write into",
    )
    args = parser.parse_args()

    categories, overview, records = parse_formula_table(args.source_html)
    write_overview(args.output_dir, categories, overview)
    write_formula_docs(args.output_dir, records)
    print(
        f"Generated {len(records)} formula docs across {len(categories)} categories "
        f"in {args.output_dir}"
    )


if __name__ == "__main__":
    main()
