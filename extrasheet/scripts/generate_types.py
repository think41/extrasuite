#!/usr/bin/env python3
"""
Generate TypedDict classes from Google Sheets API Discovery Document.

This script parses the Google Sheets API discovery.json file and generates
Python TypedDict classes for all schemas. These types provide static type
checking without runtime overhead.

Usage:
    python scripts/generate_types.py
    python scripts/generate_types.py --output src/extrasheet/api_types.py
"""

from __future__ import annotations

import argparse
import json
import keyword
import re
from pathlib import Path
from typing import Any

# Paths
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
DISCOVERY_FILE = PROJECT_ROOT / "docs" / "googlesheets" / "reference" / "discovery.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "src" / "extrasheet" / "api_types.py"


def load_discovery() -> dict[str, Any]:
    """Load the discovery.json file."""
    with DISCOVERY_FILE.open() as f:
        return json.load(f)


def to_snake_case(name: str) -> str:
    """Convert camelCase to snake_case."""
    s1 = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s1).lower()


def escape_keyword(name: str) -> str:
    """Escape Python keywords."""
    if keyword.iskeyword(name):
        return f"{name}_"
    return name


def get_python_type(prop: dict[str, Any], schemas: dict[str, Any]) -> str:
    """Convert a JSON Schema property to a Python type annotation."""
    if "$ref" in prop:
        ref_name = prop["$ref"]
        return f'"{ref_name}"'

    prop_type = prop.get("type", "any")

    if prop_type == "string":
        if "enum" in prop:
            # Could be a Literal type, but for simplicity use str
            return "str"
        return "str"
    elif prop_type == "integer":
        return "int"
    elif prop_type == "number":
        return "float"
    elif prop_type == "boolean":
        return "bool"
    elif prop_type == "array":
        if "items" in prop:
            item_type = get_python_type(prop["items"], schemas)
            return f"list[{item_type}]"
        return "list[Any]"
    elif prop_type == "object":
        if "additionalProperties" in prop:
            value_type = get_python_type(prop["additionalProperties"], schemas)
            return f"dict[str, {value_type}]"
        return "dict[str, Any]"
    else:
        return "Any"


def generate_enum_comment(prop: dict[str, Any]) -> list[str]:
    """Generate comments for enum values."""
    if "enum" not in prop:
        return []

    comments = []
    enums = prop.get("enum", [])
    enum_descs = prop.get("enumDescriptions", [])

    comments.append("    # Enum values:")
    for i, enum_val in enumerate(enums):
        desc = enum_descs[i] if i < len(enum_descs) else ""
        if desc:
            # Truncate long descriptions
            if len(desc) > 60:
                desc = desc[:57] + "..."
            comments.append(f'    #   "{enum_val}": {desc}')
        else:
            comments.append(f'    #   "{enum_val}"')

    return comments


def generate_typeddict(
    name: str, schema: dict[str, Any], schemas: dict[str, Any]
) -> str:
    """Generate a TypedDict class definition."""
    lines = []

    # Class docstring
    description = schema.get("description", f"Represents a {name} in Google Sheets.")
    lines.append(f'class {name}(TypedDict, total=False):')
    lines.append(f'    """{description}"""')
    lines.append("")

    properties = schema.get("properties", {})

    if not properties:
        lines.append("    pass")
        return "\n".join(lines)

    for prop_name, prop_def in properties.items():
        # Generate property with type annotation
        python_type = get_python_type(prop_def, schemas)
        safe_name = escape_keyword(prop_name)

        # Add property description as comment
        prop_desc = prop_def.get("description", "")
        if prop_desc:
            # Wrap long descriptions
            max_len = 76
            if len(prop_desc) > max_len:
                prop_desc = prop_desc[:max_len - 3] + "..."
            lines.append(f"    # {prop_desc}")

        # Add enum values as comments
        enum_comments = generate_enum_comment(prop_def)
        lines.extend(enum_comments)

        # Add read-only marker
        if prop_def.get("readOnly"):
            lines.append("    # Read-only field")

        # Add deprecated marker
        if prop_def.get("deprecated"):
            lines.append("    # Deprecated")

        lines.append(f"    {safe_name}: {python_type}")
        lines.append("")

    return "\n".join(lines)


def categorize_schemas(schemas: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Categorize schemas by type."""
    categories: dict[str, dict[str, Any]] = {
        "requests": {},
        "responses": {},
        "core": {},  # Core objects like Spreadsheet, Sheet, CellData
        "charts": {},  # Chart-related
        "formatting": {},  # Formatting-related
        "features": {},  # Features like pivot tables, filters
        "data_sources": {},  # Data source related
        "other": {},
    }

    core_names = {
        "Spreadsheet",
        "SpreadsheetProperties",
        "Sheet",
        "SheetProperties",
        "GridProperties",
        "GridData",
        "GridRange",
        "GridCoordinate",
        "RowData",
        "CellData",
        "CellFormat",
        "ExtendedValue",
        "ErrorValue",
        "NamedRange",
        "DimensionProperties",
        "DimensionRange",
        "DimensionGroup",
    }

    chart_keywords = {"Chart", "Series", "Axis", "Domain", "Candlestick", "Histogram", "Pie", "Bubble", "Treemap", "Waterfall", "Scorecard", "Org"}
    formatting_keywords = {"Format", "Color", "Border", "Style", "Padding", "TextFormat", "NumberFormat"}
    feature_keywords = {"Pivot", "Filter", "Slicer", "Table", "Banded", "Conditional", "Validation", "Protected", "Merge"}
    data_source_keywords = {"DataSource", "BigQuery", "Looker"}

    for name, schema in schemas.items():
        if name.endswith("Request"):
            categories["requests"][name] = schema
        elif name.endswith("Response"):
            categories["responses"][name] = schema
        elif name in core_names:
            categories["core"][name] = schema
        elif any(kw in name for kw in chart_keywords):
            categories["charts"][name] = schema
        elif any(kw in name for kw in formatting_keywords):
            categories["formatting"][name] = schema
        elif any(kw in name for kw in feature_keywords):
            categories["features"][name] = schema
        elif any(kw in name for kw in data_source_keywords):
            categories["data_sources"][name] = schema
        else:
            categories["other"][name] = schema

    return categories


def build_dependency_order(schemas: dict[str, Any]) -> list[str]:
    """Build a dependency-ordered list of schema names.

    Ensures that referenced types are defined before they are used.
    """
    # Build dependency graph
    dependencies: dict[str, set[str]] = {}
    for name, schema in schemas.items():
        deps: set[str] = set()
        properties = schema.get("properties", {})
        for prop in properties.values():
            if "$ref" in prop:
                deps.add(prop["$ref"])
            elif "items" in prop and "$ref" in prop["items"]:
                deps.add(prop["items"]["$ref"])
            elif "additionalProperties" in prop and "$ref" in prop["additionalProperties"]:
                deps.add(prop["additionalProperties"]["$ref"])
        dependencies[name] = deps

    # Topological sort with cycle detection
    ordered: list[str] = []
    visited: set[str] = set()
    temp_visited: set[str] = set()

    def visit(name: str) -> None:
        if name in temp_visited:
            # Cycle detected - using forward references handles this
            return
        if name in visited:
            return
        if name not in schemas:
            # External reference
            return

        temp_visited.add(name)
        for dep in dependencies.get(name, set()):
            visit(dep)
        temp_visited.remove(name)
        visited.add(name)
        ordered.append(name)

    for name in schemas:
        visit(name)

    return ordered


def generate_types_file(schemas: dict[str, Any]) -> str:
    """Generate the complete types file content."""
    lines = [
        '"""',
        "Google Sheets API Types",
        "",
        "Auto-generated from Google Sheets API v4 discovery document.",
        "Do not edit manually - run scripts/generate_types.py instead.",
        "",
        "These TypedDict classes provide static type checking for Google Sheets API",
        "request and response objects without runtime overhead.",
        '"""',
        "",
        "from __future__ import annotations",
        "",
        "from typing import Any, TypedDict",
        "",
        "",
        "# =============================================================================",
        "# Google Sheets API Types",
        "# =============================================================================",
        "",
    ]

    # Categorize schemas
    categories = categorize_schemas(schemas)

    # Build dependency order
    ordered = build_dependency_order(schemas)

    # Generate types in dependency order with section headers
    section_order = [
        ("core", "Core Objects"),
        ("formatting", "Formatting"),
        ("charts", "Charts"),
        ("features", "Features (Pivot Tables, Filters, etc.)"),
        ("data_sources", "Data Sources"),
        ("other", "Other Objects"),
        ("requests", "Requests"),
        ("responses", "Responses"),
    ]

    generated: set[str] = set()

    for section_key, section_title in section_order:
        section_schemas = categories.get(section_key, {})
        if not section_schemas:
            continue

        lines.append("")
        lines.append(f"# {'=' * 77}")
        lines.append(f"# {section_title}")
        lines.append(f"# {'=' * 77}")
        lines.append("")

        # Generate in dependency order within section
        for name in ordered:
            if name in section_schemas and name not in generated:
                lines.append(generate_typeddict(name, section_schemas[name], schemas))
                lines.append("")
                lines.append("")
                generated.add(name)

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate TypedDict classes from Google Sheets API discovery document"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Output file path (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print output instead of writing to file",
    )
    args = parser.parse_args()

    print("Loading discovery.json...")
    discovery = load_discovery()
    schemas = discovery.get("schemas", {})
    print(f"Found {len(schemas)} schemas")

    print("Generating types...")
    content = generate_types_file(schemas)

    if args.dry_run:
        print("\n" + "=" * 70)
        print("Generated content:")
        print("=" * 70)
        # Print just first 200 lines for preview
        preview_lines = content.split("\n")[:200]
        print("\n".join(preview_lines))
        if len(content.split("\n")) > 200:
            print(f"\n... ({len(content.split(chr(10)))} total lines)")
    else:
        # Ensure output directory exists
        args.output.parent.mkdir(parents=True, exist_ok=True)

        with args.output.open("w") as f:
            f.write(content)
        print(f"Written to {args.output}")
        print(f"Total lines: {len(content.split(chr(10)))}")


if __name__ == "__main__":
    main()
