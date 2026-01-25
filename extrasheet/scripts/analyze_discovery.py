#!/usr/bin/env python3
"""
Analyze Google Sheets API Discovery Document

This script parses the Google Sheets API discovery.json file and:
1. Extracts all schemas (objects, requests, responses)
2. Compares with existing documentation
3. Identifies gaps in documentation
4. Generates missing documentation

Usage:
    python scripts/analyze_discovery.py --analyze    # Show analysis report
    python scripts/analyze_discovery.py --generate   # Generate missing docs
    python scripts/analyze_discovery.py --download   # Download fresh discovery.json
"""

import argparse
import json
import re
import urllib.request
from pathlib import Path

# Paths
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
DISCOVERY_FILE = PROJECT_ROOT / "docs" / "googlesheets" / "reference" / "discovery.json"
OBJECTS_DIR = PROJECT_ROOT / "docs" / "googlesheets" / "reference" / "objects"
REQUESTS_DIR = PROJECT_ROOT / "docs" / "googlesheets" / "reference" / "requests"

DISCOVERY_URL = "https://sheets.googleapis.com/$discovery/rest?version=v4"


def download_discovery() -> dict:
    """Download the discovery.json file from Google."""
    print(f"Downloading from {DISCOVERY_URL}...")
    try:
        with urllib.request.urlopen(DISCOVERY_URL) as response:
            data = json.loads(response.read().decode())
            # Save to file
            DISCOVERY_FILE.parent.mkdir(parents=True, exist_ok=True)
            with DISCOVERY_FILE.open("w") as f:
                json.dump(data, f, indent=2)
            print(f"Saved to {DISCOVERY_FILE}")
            return data
    except Exception as e:
        print(f"Failed to download: {e}")
        print("You may need to download manually from a browser.")
        return {}


def load_discovery() -> dict:
    """Load the discovery.json file."""
    if not DISCOVERY_FILE.exists():
        print(f"Discovery file not found at {DISCOVERY_FILE}")
        print("Attempting to download...")
        return download_discovery()
    with DISCOVERY_FILE.open() as f:
        return json.load(f)


def to_kebab_case(name: str) -> str:
    """Convert PascalCase to kebab-case."""
    s1 = re.sub(r"(.)([A-Z][a-z]+)", r"\1-\2", name)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1-\2", s1).lower()


def categorize_schemas(schemas: dict) -> dict:
    """Categorize schemas into requests, responses, and data objects."""
    categories = {
        "requests": {},
        "responses": {},
        "objects": {},
    }

    for name, schema in schemas.items():
        if name.endswith("Request"):
            categories["requests"][name] = schema
        elif name.endswith("Response"):
            categories["responses"][name] = schema
        else:
            categories["objects"][name] = schema

    return categories


def get_existing_docs(directory: Path) -> set[str]:
    """Get list of existing documentation files."""
    if not directory.exists():
        return set()

    docs = set()
    for file in directory.glob("*.md"):
        if file.name != "index.md":
            name = file.stem
            docs.add(name)
    return docs


def schema_name_to_filename(name: str, is_request: bool = False) -> str:
    """Convert schema name to documentation filename."""
    if is_request and name.endswith("Request"):
        name = name[:-7]
    return to_kebab_case(name) + ".md"


def filename_to_schema_name(filename: str, is_request: bool = False) -> str:
    """Convert filename back to schema name."""
    name = filename.replace(".md", "")
    parts = name.split("-")
    pascal_name = "".join(word.capitalize() for word in parts)
    if is_request:
        pascal_name += "Request"
    return pascal_name


def analyze_documentation_gaps(categories: dict) -> dict:
    """Analyze gaps between discovery.json schemas and existing docs."""
    existing_objects = get_existing_docs(OBJECTS_DIR)
    existing_requests = get_existing_docs(REQUESTS_DIR)

    existing_object_schemas = {
        filename_to_schema_name(f + ".md", is_request=False) for f in existing_objects
    }
    existing_request_schemas = {
        filename_to_schema_name(f + ".md", is_request=True) for f in existing_requests
    }

    object_schemas = set(categories["objects"].keys())
    request_schemas = set(categories["requests"].keys())

    missing_objects = object_schemas - existing_object_schemas
    documented_objects = object_schemas & existing_object_schemas

    missing_requests = request_schemas - existing_request_schemas
    documented_requests = request_schemas & existing_request_schemas

    return {
        "objects": {
            "total": len(object_schemas),
            "documented": len(documented_objects),
            "missing": sorted(missing_objects),
            "documented_list": sorted(documented_objects),
        },
        "requests": {
            "total": len(request_schemas),
            "documented": len(documented_requests),
            "missing": sorted(missing_requests),
            "documented_list": sorted(documented_requests),
        },
        "responses": {
            "total": len(categories["responses"]),
            "schemas": sorted(categories["responses"].keys()),
        },
    }


def get_type_string(prop: dict) -> str:
    """Get a human-readable type string from a schema property."""
    if "$ref" in prop:
        return f"[{prop['$ref']}]"
    if "type" in prop:
        t = prop["type"]
        if t == "array":
            if "items" in prop:
                item_type = get_type_string(prop["items"])
                return f"array of {item_type}"
            return "array"
        if t == "object":
            if "additionalProperties" in prop:
                return f"map<string, {get_type_string(prop['additionalProperties'])}>"
            return "object"
        return t
    if "enum" in prop:
        return "enum"
    return "any"


def format_description(desc: str, max_length: int = 100) -> str:
    """Format description for table display."""
    if not desc:
        return ""
    desc = " ".join(desc.split())
    if len(desc) > max_length:
        return desc[: max_length - 3] + "..."
    return desc


def generate_object_doc(name: str, schema: dict, _all_schemas: dict) -> str:
    """Generate markdown documentation for a data object."""
    doc = f"# {name}\n\n"

    desc = schema.get("description", f"A {name} object in the Google Sheets API.")
    doc += f"{desc}\n\n"

    doc += "## Schema\n\n"
    doc += "```json\n{\n"

    properties = schema.get("properties", {})
    prop_lines = []
    for prop_name, prop_def in properties.items():
        type_str = get_type_string(prop_def)
        prop_lines.append(f'  "{prop_name}": {type_str}')
    doc += ",\n".join(prop_lines)
    doc += "\n}\n```\n\n"

    if properties:
        doc += "## Properties\n\n"
        doc += "| Property | Type | Description |\n"
        doc += "|----------|------|-------------|\n"

        for prop_name, prop_def in properties.items():
            type_str = get_type_string(prop_def)
            prop_desc = format_description(prop_def.get("description", ""))
            doc += f"| `{prop_name}` | {type_str} | {prop_desc} |\n"
        doc += "\n"

    for prop_name, prop_def in properties.items():
        if "enum" in prop_def:
            doc += f"### {prop_name} Values\n\n"
            doc += "| Value | Description |\n"
            doc += "|-------|-------------|\n"
            enums = prop_def.get("enum", [])
            enum_descs = prop_def.get("enumDescriptions", [])
            for i, enum_val in enumerate(enums):
                enum_desc = enum_descs[i] if i < len(enum_descs) else ""
                doc += f"| `{enum_val}` | {format_description(enum_desc)} |\n"
            doc += "\n"

    refs = set()
    for prop_def in properties.values():
        if "$ref" in prop_def:
            refs.add(prop_def["$ref"])
        if "items" in prop_def and "$ref" in prop_def["items"]:
            refs.add(prop_def["items"]["$ref"])

    if refs:
        doc += "## Related Objects\n\n"
        for ref in sorted(refs):
            ref_file = to_kebab_case(ref) + ".md"
            doc += f"- [{ref}](./{ref_file})\n"
        doc += "\n"

    return doc


def generate_request_doc(name: str, schema: dict, _all_schemas: dict) -> str:
    """Generate markdown documentation for a request type."""
    doc = f"# {name}\n\n"

    desc = schema.get(
        "description", f"Request to perform a {name.replace('Request', '')} operation."
    )
    doc += f"{desc}\n\n"

    doc += "## Schema\n\n"

    request_key = name[0].lower() + name[1:].replace("Request", "")

    doc += "```json\n{\n"
    doc += f'  "{request_key}": {{\n'

    properties = schema.get("properties", {})
    prop_lines = []
    for prop_name, prop_def in properties.items():
        type_str = get_type_string(prop_def)
        prop_lines.append(f'    "{prop_name}": {type_str}')
    doc += ",\n".join(prop_lines)
    doc += "\n  }\n}\n```\n\n"

    if properties:
        doc += "## Properties\n\n"
        doc += "| Property | Type | Required | Description |\n"
        doc += "|----------|------|----------|-------------|\n"

        required_props = set(schema.get("required", []))
        for prop_name, prop_def in properties.items():
            type_str = get_type_string(prop_def)
            prop_desc = format_description(prop_def.get("description", ""))
            required = "Yes" if prop_name in required_props else "No"
            doc += f"| `{prop_name}` | {type_str} | {required} | {prop_desc} |\n"
        doc += "\n"

    doc += "## Example\n\n"
    doc += "```json\n"
    doc += "{\n"
    doc += '  "requests": [\n'
    doc += "    {\n"
    doc += f'      "{request_key}": {{\n'
    doc += "        // Properties here\n"
    doc += "      }\n"
    doc += "    }\n"
    doc += "  ]\n"
    doc += "}\n"
    doc += "```\n\n"

    refs = set()
    for prop_def in properties.values():
        if "$ref" in prop_def:
            refs.add(prop_def["$ref"])
        if "items" in prop_def and "$ref" in prop_def["items"]:
            refs.add(prop_def["items"]["$ref"])

    if refs:
        doc += "## Related Objects\n\n"
        for ref in sorted(refs):
            ref_file = to_kebab_case(ref) + ".md"
            doc += f"- [{ref}](../objects/{ref_file})\n"
        doc += "\n"

    return doc


def generate_index_objects(categories: dict) -> str:
    """Generate index.md for objects directory."""
    doc = "# Google Sheets API Objects\n\n"
    doc += "This section documents the data objects used in the Google Sheets API.\n\n"

    # Group objects by category
    core_objects = [
        "Spreadsheet",
        "SpreadsheetProperties",
        "Sheet",
        "SheetProperties",
        "GridData",
        "RowData",
        "CellData",
    ]
    cell_objects = [
        "ExtendedValue",
        "ErrorValue",
        "CellFormat",
        "TextFormat",
        "NumberFormat",
        "Color",
        "ColorStyle",
    ]
    grid_objects = [
        "GridRange",
        "GridCoordinate",
        "GridProperties",
        "DimensionRange",
        "DimensionProperties",
    ]
    chart_objects = [
        "EmbeddedChart",
        "ChartSpec",
        "BasicChartSpec",
        "PieChartSpec",
        "ChartData",
        "BasicChartSeries",
    ]
    pivot_objects = [
        "PivotTable",
        "PivotGroup",
        "PivotValue",
        "PivotGroupRule",
    ]
    conditional_objects = [
        "ConditionalFormatRule",
        "BooleanRule",
        "BooleanCondition",
        "GradientRule",
    ]

    all_objects = set(categories["objects"].keys())

    def write_section(title: str, objects: list[str]) -> str:
        s = f"## {title}\n\n"
        for obj in sorted(objects):
            if obj in all_objects:
                s += f"- [{obj}](./{to_kebab_case(obj)}.md)\n"
        s += "\n"
        return s

    doc += write_section("Core Objects", core_objects)
    doc += write_section("Cell Objects", cell_objects)
    doc += write_section("Grid Objects", grid_objects)
    doc += write_section("Chart Objects", chart_objects)
    doc += write_section("Pivot Table Objects", pivot_objects)
    doc += write_section("Conditional Formatting", conditional_objects)

    categorized = (
        set(core_objects)
        | set(cell_objects)
        | set(grid_objects)
        | set(chart_objects)
        | set(pivot_objects)
        | set(conditional_objects)
    )
    remaining = all_objects - categorized
    if remaining:
        doc += "## Other Objects\n\n"
        for obj in sorted(remaining):
            doc += f"- [{obj}](./{to_kebab_case(obj)}.md)\n"
        doc += "\n"

    return doc


def generate_index_requests(categories: dict) -> str:
    """Generate index.md for requests directory."""
    doc = "# Google Sheets API Requests\n\n"
    doc += "This section documents the request types used with the `batchUpdate` API.\n\n"
    doc += "## Usage\n\n"
    doc += "All requests are sent via the `spreadsheets.batchUpdate` endpoint:\n\n"
    doc += "```json\n"
    doc += "POST https://sheets.googleapis.com/v4/spreadsheets/{spreadsheetId}:batchUpdate\n\n"
    doc += "{\n"
    doc += '  "requests": [\n'
    doc += "    { /* request 1 */ },\n"
    doc += "    { /* request 2 */ }\n"
    doc += "  ]\n"
    doc += "}\n"
    doc += "```\n\n"

    # Group requests by category
    add_requests = [r for r in categories["requests"] if r.startswith("Add")]
    update_requests = [r for r in categories["requests"] if r.startswith("Update")]
    delete_requests = [r for r in categories["requests"] if r.startswith("Delete")]
    set_requests = [r for r in categories["requests"] if r.startswith("Set")]

    excluded_requests = {"Request", "BatchUpdateSpreadsheetRequest"}
    other_requests = [
        r
        for r in categories["requests"]
        if r not in excluded_requests
        and not any(
            r.startswith(prefix)
            for prefix in ["Add", "Update", "Delete", "Set", "Batch"]
        )
    ]

    def write_section(title: str, requests: list[str]) -> str:
        if not requests:
            return ""
        s = f"## {title}\n\n"
        for req in sorted(requests):
            filename = schema_name_to_filename(req, is_request=True)
            s += f"- [{req}](./{filename})\n"
        s += "\n"
        return s

    doc += write_section("Add Requests", add_requests)
    doc += write_section("Update Requests", update_requests)
    doc += write_section("Delete Requests", delete_requests)
    doc += write_section("Set Requests", set_requests)
    doc += write_section("Other Requests", other_requests)

    return doc


def print_analysis_report(gaps: dict) -> None:
    """Print a formatted analysis report."""
    print("=" * 70)
    print("GOOGLE SHEETS API DOCUMENTATION ANALYSIS")
    print("=" * 70)
    print()

    print("DATA OBJECTS")
    print("-" * 40)
    print(f"Total in discovery.json: {gaps['objects']['total']}")
    print(f"Currently documented:    {gaps['objects']['documented']}")
    print(f"Missing documentation:   {len(gaps['objects']['missing'])}")
    print()

    if gaps["objects"]["missing"]:
        print("Missing objects (first 20):")
        for name in gaps["objects"]["missing"][:20]:
            print(f"  ✗ {name}")
        if len(gaps["objects"]["missing"]) > 20:
            print(f"  ... and {len(gaps['objects']['missing']) - 20} more")
        print()

    print("REQUESTS")
    print("-" * 40)
    print(f"Total in discovery.json: {gaps['requests']['total']}")
    print(f"Currently documented:    {gaps['requests']['documented']}")
    print(f"Missing documentation:   {len(gaps['requests']['missing'])}")
    print()

    if gaps["requests"]["missing"]:
        print("Missing requests (first 20):")
        for name in gaps["requests"]["missing"][:20]:
            print(f"  ✗ {name}")
        if len(gaps["requests"]["missing"]) > 20:
            print(f"  ... and {len(gaps['requests']['missing']) - 20} more")
        print()

    print("RESPONSES")
    print("-" * 40)
    print(f"Total in discovery.json: {gaps['responses']['total']}")
    print()

    total_missing = len(gaps["objects"]["missing"]) + len(gaps["requests"]["missing"])
    total_documented = gaps["objects"]["documented"] + gaps["requests"]["documented"]
    total_schemas = gaps["objects"]["total"] + gaps["requests"]["total"]

    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Total schemas (objects + requests): {total_schemas}")
    print(f"Currently documented:               {total_documented}")
    print(f"Missing documentation:              {total_missing}")
    if total_schemas > 0:
        print(
            f"Documentation coverage:             {total_documented / total_schemas * 100:.1f}%"
        )
    print()


def generate_documentation(categories: dict, gaps: dict, dry_run: bool = False) -> None:
    """Generate missing documentation files."""
    all_schemas = {
        **categories["objects"],
        **categories["requests"],
        **categories["responses"],
    }

    # Ensure directories exist
    if not dry_run:
        OBJECTS_DIR.mkdir(parents=True, exist_ok=True)
        REQUESTS_DIR.mkdir(parents=True, exist_ok=True)

    print("\nGenerating object documentation...")
    for name in gaps["objects"]["missing"][:10]:  # Limit to first 10
        schema = categories["objects"][name]
        doc_content = generate_object_doc(name, schema, all_schemas)
        filename = OBJECTS_DIR / schema_name_to_filename(name, is_request=False)

        if dry_run:
            print(f"  Would create: {filename}")
        else:
            with filename.open("w") as f:
                f.write(doc_content)
            print(f"  Created: {filename}")

    print("\nGenerating request documentation...")
    for name in gaps["requests"]["missing"][:10]:  # Limit to first 10
        if name in ["Request", "BatchUpdateSpreadsheetRequest"]:
            continue
        schema = categories["requests"][name]
        doc_content = generate_request_doc(name, schema, all_schemas)
        filename = REQUESTS_DIR / schema_name_to_filename(name, is_request=True)

        if dry_run:
            print(f"  Would create: {filename}")
        else:
            with filename.open("w") as f:
                f.write(doc_content)
            print(f"  Created: {filename}")

    print("\nGenerating index files...")

    objects_index = generate_index_objects(categories)
    objects_index_file = OBJECTS_DIR / "index.md"
    if dry_run:
        print(f"  Would update: {objects_index_file}")
    else:
        with objects_index_file.open("w") as f:
            f.write(objects_index)
        print(f"  Updated: {objects_index_file}")

    requests_index = generate_index_requests(categories)
    requests_index_file = REQUESTS_DIR / "index.md"
    if dry_run:
        print(f"  Would update: {requests_index_file}")
    else:
        with requests_index_file.open("w") as f:
            f.write(requests_index)
        print(f"  Updated: {requests_index_file}")


def main():
    parser = argparse.ArgumentParser(
        description="Analyze Google Sheets API Discovery Document"
    )
    parser.add_argument(
        "--analyze",
        action="store_true",
        help="Show analysis report of documentation gaps",
    )
    parser.add_argument(
        "--generate",
        action="store_true",
        help="Generate missing documentation",
    )
    parser.add_argument(
        "--download",
        action="store_true",
        help="Download fresh discovery.json from Google",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be generated without creating files",
    )
    args = parser.parse_args()

    if args.download:
        download_discovery()
        return

    if not args.analyze and not args.generate:
        args.analyze = True

    print("Loading discovery.json...")
    discovery = load_discovery()
    if not discovery:
        print("Failed to load discovery document.")
        return

    schemas = discovery.get("schemas", {})
    print(f"Found {len(schemas)} schemas\n")

    categories = categorize_schemas(schemas)
    print(f"Objects:   {len(categories['objects'])}")
    print(f"Requests:  {len(categories['requests'])}")
    print(f"Responses: {len(categories['responses'])}")
    print()

    gaps = analyze_documentation_gaps(categories)

    if args.analyze:
        print_analysis_report(gaps)

    if args.generate:
        generate_documentation(categories, gaps, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
