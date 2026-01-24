#!/usr/bin/env python3
"""
Analyze Google Slides API Discovery Document

This script parses the Google Slides API discovery.json file and:
1. Extracts all schemas (objects, requests, responses)
2. Compares with existing documentation
3. Identifies gaps in documentation
4. Generates missing documentation

Usage:
    python scripts/analyze_discovery.py --analyze    # Show analysis report
    python scripts/analyze_discovery.py --generate   # Generate missing docs
"""

import argparse
import json
import re
from pathlib import Path

# Paths
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
DISCOVERY_FILE = PROJECT_ROOT / "docs" / "googleslides" / "reference" / "discovery.json"
OBJECTS_DIR = PROJECT_ROOT / "docs" / "googleslides" / "reference" / "objects"
REQUESTS_DIR = PROJECT_ROOT / "docs" / "googleslides" / "reference" / "requests"


def load_discovery() -> dict:
    """Load the discovery.json file."""
    with DISCOVERY_FILE.open() as f:
        return json.load(f)


def to_kebab_case(name: str) -> str:
    """Convert PascalCase to kebab-case."""
    # Insert hyphen before uppercase letters and lowercase them
    s1 = re.sub(r"(.)([A-Z][a-z]+)", r"\1-\2", name)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1-\2", s1).lower()


def categorize_schemas(schemas: dict) -> dict:
    """Categorize schemas into requests, responses, and data objects."""
    categories = {
        "requests": {},  # Schemas ending with 'Request'
        "responses": {},  # Schemas ending with 'Response'
        "objects": {},  # Everything else (data objects)
        "enums": {},  # Enum types found in schemas
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
            # Convert filename to schema name
            name = file.stem  # e.g., 'create-shape' -> 'CreateShape'
            docs.add(name)
    return docs


def schema_name_to_filename(name: str, is_request: bool = False) -> str:
    """Convert schema name to documentation filename.

    For requests, removes 'Request' suffix to match existing convention:
    - CreateShapeRequest -> create-shape.md
    - DeleteObjectRequest -> delete-object.md
    """
    if is_request and name.endswith("Request"):
        name = name[:-7]  # Remove 'Request' suffix
    return to_kebab_case(name) + ".md"


def filename_to_schema_name(filename: str, is_request: bool = False) -> str:
    """Convert filename back to schema name (approximate).

    For requests, adds 'Request' suffix:
    - create-shape -> CreateShapeRequest
    """
    # Remove .md extension
    name = filename.replace(".md", "")
    # Convert kebab-case to PascalCase
    parts = name.split("-")
    pascal_name = "".join(word.capitalize() for word in parts)
    if is_request:
        pascal_name += "Request"
    return pascal_name


def analyze_documentation_gaps(categories: dict) -> dict:
    """Analyze gaps between discovery.json schemas and existing docs."""
    existing_objects = get_existing_docs(OBJECTS_DIR)
    existing_requests = get_existing_docs(REQUESTS_DIR)

    # Map existing files to expected schema names
    # For objects: affine-transform -> AffineTransform
    existing_object_schemas = {
        filename_to_schema_name(f + ".md", is_request=False) for f in existing_objects
    }
    # For requests: create-shape -> CreateShapeRequest
    existing_request_schemas = {
        filename_to_schema_name(f + ".md", is_request=True) for f in existing_requests
    }

    # Find gaps
    object_schemas = set(categories["objects"].keys())
    request_schemas = set(categories["requests"].keys())

    # Direct matching for objects
    missing_objects = object_schemas - existing_object_schemas
    documented_objects = object_schemas & existing_object_schemas

    # Direct matching for requests
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
    # Remove newlines and extra whitespace
    desc = " ".join(desc.split())
    if len(desc) > max_length:
        return desc[: max_length - 3] + "..."
    return desc


def generate_object_doc(name: str, schema: dict, _all_schemas: dict) -> str:
    """Generate markdown documentation for a data object.

    Args:
        name: Schema name
        schema: Schema definition
        _all_schemas: All schemas (reserved for future cross-reference features)
    """
    doc = f"# {name}\n\n"

    # Description
    desc = schema.get("description", f"A {name} object in the Google Slides API.")
    doc += f"{desc}\n\n"

    # Schema
    doc += "## Schema\n\n"
    doc += "```json\n{\n"

    properties = schema.get("properties", {})
    prop_lines = []
    for prop_name, prop_def in properties.items():
        type_str = get_type_string(prop_def)
        prop_lines.append(f'  "{prop_name}": {type_str}')
    doc += ",\n".join(prop_lines)
    doc += "\n}\n```\n\n"

    # Properties table
    if properties:
        doc += "## Properties\n\n"
        doc += "| Property | Type | Description |\n"
        doc += "|----------|------|-------------|\n"

        for prop_name, prop_def in properties.items():
            type_str = get_type_string(prop_def)
            prop_desc = format_description(prop_def.get("description", ""))
            doc += f"| `{prop_name}` | {type_str} | {prop_desc} |\n"
        doc += "\n"

    # Enum values if this schema has enums
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

    # Related objects
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
    """Generate markdown documentation for a request type.

    Args:
        name: Schema name
        schema: Schema definition
        _all_schemas: All schemas (reserved for future cross-reference features)
    """
    doc = f"# {name}\n\n"

    # Description
    desc = schema.get(
        "description", f"Request to perform a {name.replace('Request', '')} operation."
    )
    doc += f"{desc}\n\n"

    # Schema
    doc += "## Schema\n\n"

    # Get the request key name (e.g., 'createShape' for CreateShapeRequest)
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

    # Properties table
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

    # Enum values
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

    # Example
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

    # Related objects
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
    doc = "# Google Slides API Objects\n\n"
    doc += "This section documents the data objects used in the Google Slides API.\n\n"

    # Group objects by category
    core_objects = ["Presentation", "Page", "PageElement", "Shape", "TextContent"]
    page_elements = [
        "Shape",
        "Image",
        "Video",
        "Line",
        "Table",
        "SheetsChart",
        "Group",
        "WordArt",
        "SpeakerSpotlight",
    ]
    text_objects = [
        "TextContent",
        "TextElement",
        "TextRun",
        "ParagraphMarker",
        "ParagraphStyle",
        "TextStyle",
        "AutoText",
        "Bullet",
        "List",
        "NestingLevel",
    ]
    style_objects = [
        "SolidFill",
        "OpaqueColor",
        "OptionalColor",
        "RgbColor",
        "Shadow",
        "Outline",
        "OutlineFill",
        "LineFill",
        "Recolor",
        "ColorStop",
        "ColorScheme",
        "ThemeColorPair",
    ]
    transform_objects = ["AffineTransform", "Size", "Dimension", "CropProperties"]
    properties_objects = [
        "ShapeProperties",
        "ImageProperties",
        "VideoProperties",
        "LineProperties",
        "TableCellProperties",
        "TableRowProperties",
        "TableColumnProperties",
        "SheetsChartProperties",
        "SpeakerSpotlightProperties",
        "PageProperties",
        "PageBackgroundFill",
        "ShapeBackgroundFill",
        "TableCellBackgroundFill",
        "StretchedPictureFill",
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
    doc += write_section("Page Elements", page_elements)
    doc += write_section("Text Objects", text_objects)
    doc += write_section("Style Objects", style_objects)
    doc += write_section("Transform & Dimension", transform_objects)
    doc += write_section("Properties Objects", properties_objects)

    # Remaining objects
    categorized = (
        set(core_objects)
        | set(page_elements)
        | set(text_objects)
        | set(style_objects)
        | set(transform_objects)
        | set(properties_objects)
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
    doc = "# Google Slides API Requests\n\n"
    doc += (
        "This section documents the request types used with the `batchUpdate` API.\n\n"
    )
    doc += "## Usage\n\n"
    doc += "All requests are sent via the `presentations.batchUpdate` endpoint:\n\n"
    doc += "```json\n"
    doc += "POST https://slides.googleapis.com/v1/presentations/{presentationId}:batchUpdate\n\n"
    doc += "{\n"
    doc += '  "requests": [\n'
    doc += "    { /* request 1 */ },\n"
    doc += "    { /* request 2 */ }\n"
    doc += "  ]\n"
    doc += "}\n"
    doc += "```\n\n"

    # Group requests by category
    create_requests = [r for r in categories["requests"] if r.startswith("Create")]
    update_requests = [r for r in categories["requests"] if r.startswith("Update")]
    delete_requests = [r for r in categories["requests"] if r.startswith("Delete")]
    insert_requests = [r for r in categories["requests"] if r.startswith("Insert")]
    replace_requests = [r for r in categories["requests"] if r.startswith("Replace")]
    # Exclude meta-types (Request, BatchUpdatePresentationRequest) from listings
    excluded_requests = {"Request", "BatchUpdatePresentationRequest"}
    other_requests = [
        r
        for r in categories["requests"]
        if r not in excluded_requests
        and not any(
            r.startswith(prefix)
            for prefix in ["Create", "Update", "Delete", "Insert", "Replace", "Batch"]
        )
    ]

    def write_section(title: str, requests: list[str]) -> str:
        if not requests:
            return ""
        s = f"## {title}\n\n"
        for req in sorted(requests):
            # Use schema_name_to_filename to get correct format (without 'Request' suffix)
            filename = schema_name_to_filename(req, is_request=True)
            s += f"- [{req}](./{filename})\n"
        s += "\n"
        return s

    doc += write_section("Create Requests", create_requests)
    doc += write_section("Update Requests", update_requests)
    doc += write_section("Delete Requests", delete_requests)
    doc += write_section("Insert Requests", insert_requests)
    doc += write_section("Replace Requests", replace_requests)
    doc += write_section("Other Requests", other_requests)

    return doc


def print_analysis_report(gaps: dict) -> None:
    """Print a formatted analysis report."""
    print("=" * 70)
    print("GOOGLE SLIDES API DOCUMENTATION ANALYSIS")
    print("=" * 70)
    print()

    print("DATA OBJECTS")
    print("-" * 40)
    print(f"Total in discovery.json: {gaps['objects']['total']}")
    print(f"Currently documented:    {gaps['objects']['documented']}")
    print(f"Missing documentation:   {len(gaps['objects']['missing'])}")
    print()

    if gaps["objects"]["documented_list"]:
        print("Documented objects:")
        for name in gaps["objects"]["documented_list"]:
            print(f"  ✓ {name}")
        print()

    if gaps["objects"]["missing"]:
        print("Missing objects:")
        for name in gaps["objects"]["missing"]:
            print(f"  ✗ {name}")
        print()

    print("REQUESTS")
    print("-" * 40)
    print(f"Total in discovery.json: {gaps['requests']['total']}")
    print(f"Currently documented:    {gaps['requests']['documented']}")
    print(f"Missing documentation:   {len(gaps['requests']['missing'])}")
    print()

    if gaps["requests"]["documented_list"]:
        print("Documented requests:")
        for name in gaps["requests"]["documented_list"]:
            print(f"  ✓ {name}")
        print()

    if gaps["requests"]["missing"]:
        print("Missing requests:")
        for name in gaps["requests"]["missing"]:
            print(f"  ✗ {name}")
        print()

    print("RESPONSES")
    print("-" * 40)
    print(f"Total in discovery.json: {gaps['responses']['total']}")
    print("(Responses are typically not documented separately)")
    print()

    # Summary
    total_missing = len(gaps["objects"]["missing"]) + len(gaps["requests"]["missing"])
    total_documented = gaps["objects"]["documented"] + gaps["requests"]["documented"]
    total_schemas = gaps["objects"]["total"] + gaps["requests"]["total"]

    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Total schemas (objects + requests): {total_schemas}")
    print(f"Currently documented:               {total_documented}")
    print(f"Missing documentation:              {total_missing}")
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

    # Generate missing object docs
    print("\nGenerating object documentation...")
    for name in gaps["objects"]["missing"]:
        schema = categories["objects"][name]
        doc_content = generate_object_doc(name, schema, all_schemas)
        filename = OBJECTS_DIR / schema_name_to_filename(name, is_request=False)

        if dry_run:
            print(f"  Would create: {filename}")
        else:
            with filename.open("w") as f:
                f.write(doc_content)
            print(f"  Created: {filename}")

    # Generate missing request docs
    print("\nGenerating request documentation...")
    for name in gaps["requests"]["missing"]:
        if name in ["Request", "BatchUpdatePresentationRequest"]:
            # Skip meta-request types
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

    # Generate/update index files
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
        description="Analyze Google Slides API Discovery Document"
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
        "--dry-run",
        action="store_true",
        help="Show what would be generated without creating files",
    )
    args = parser.parse_args()

    # Default to analyze if no args provided
    if not args.analyze and not args.generate:
        args.analyze = True

    # Load and parse discovery document
    print("Loading discovery.json...")
    discovery = load_discovery()
    schemas = discovery.get("schemas", {})
    print(f"Found {len(schemas)} schemas\n")

    # Categorize schemas
    categories = categorize_schemas(schemas)
    print(f"Objects:   {len(categories['objects'])}")
    print(f"Requests:  {len(categories['requests'])}")
    print(f"Responses: {len(categories['responses'])}")
    print()

    # Analyze gaps
    gaps = analyze_documentation_gaps(categories)

    if args.analyze:
        print_analysis_report(gaps)

    if args.generate:
        generate_documentation(categories, gaps, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
