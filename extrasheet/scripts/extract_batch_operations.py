#!/usr/bin/env python3
"""
Extract all batchUpdate operations from Google Sheets API discovery.json.

This script parses the discovery.json file and extracts:
1. All request types that can be passed to batchUpdate
2. Their parameters and field definitions
3. Organizes them by category for easier analysis

Usage:
    python scripts/extract_batch_operations.py
"""

import json
from collections import defaultdict
from pathlib import Path


def load_discovery() -> dict:
    """Load the discovery.json file."""
    discovery_path = Path(__file__).parent.parent / "docs" / "discovery.json"
    with discovery_path.open() as f:
        return json.load(f)


def extract_request_types(discovery: dict) -> list[str]:
    """
    Extract all request types from the Request schema.

    The Request schema has oneOf with all possible request types.
    """
    schemas = discovery.get("schemas", {})
    request_schema = schemas.get("Request", {})
    properties = request_schema.get("properties", {})

    request_types = []
    for prop_name, prop_def in properties.items():
        if "$ref" in prop_def:
            request_types.append(prop_name)

    return sorted(request_types)


def get_schema_details(discovery: dict, schema_name: str) -> dict:
    """Get the full schema definition for a request type."""
    schemas = discovery.get("schemas", {})
    return schemas.get(schema_name, {})


def resolve_ref(discovery: dict, ref: str) -> dict:
    """Resolve a $ref to its schema."""
    schema_name = ref.replace("#/schemas/", "")
    return discovery.get("schemas", {}).get(schema_name, {})


def flatten_schema(
    discovery: dict, schema: dict, depth: int = 0, max_depth: int = 3
) -> dict:
    """
    Flatten a schema to show its fields and their types.
    Limited depth to avoid infinite recursion.
    """
    if depth > max_depth:
        return {"_truncated": True}

    result = {}

    if "$ref" in schema:
        resolved = resolve_ref(discovery, schema["$ref"])
        return flatten_schema(discovery, resolved, depth, max_depth)

    if "properties" in schema:
        for prop_name, prop_def in schema["properties"].items():
            if "$ref" in prop_def:
                ref_name = prop_def["$ref"].replace("#/schemas/", "")
                resolved = resolve_ref(discovery, prop_def["$ref"])
                if resolved.get("type") == "object" and "properties" in resolved:
                    result[prop_name] = {
                        "_type": ref_name,
                        "_fields": flatten_schema(
                            discovery, resolved, depth + 1, max_depth
                        ),
                    }
                else:
                    result[prop_name] = {"_type": ref_name}
            elif "type" in prop_def:
                if prop_def["type"] == "array" and "items" in prop_def:
                    items = prop_def["items"]
                    if "$ref" in items:
                        ref_name = items["$ref"].replace("#/schemas/", "")
                        result[prop_name] = {"_type": f"array<{ref_name}>"}
                    else:
                        result[prop_name] = {
                            "_type": f"array<{items.get('type', 'any')}>"
                        }
                else:
                    result[prop_name] = {"_type": prop_def["type"]}
            else:
                result[prop_name] = {"_type": "any"}

    return result


def categorize_operations(request_types: list[str]) -> dict[str, list[str]]:
    """Categorize operations by their primary function."""
    categories = defaultdict(list)

    # Define categories based on operation name patterns
    for op in request_types:
        op_lower = op.lower()

        if "cell" in op_lower or "values" in op_lower:
            categories["Cell Data"].append(op)
        elif "sheet" in op_lower and (
            "add" in op_lower or "delete" in op_lower or "duplicate" in op_lower
        ):
            categories["Sheet Management"].append(op)
        elif "sheet" in op_lower:
            categories["Sheet Properties"].append(op)
        elif "row" in op_lower or "column" in op_lower or "dimension" in op_lower:
            categories["Rows & Columns"].append(op)
        elif "format" in op_lower or "border" in op_lower or "merge" in op_lower:
            categories["Formatting"].append(op)
        elif "chart" in op_lower:
            categories["Charts"].append(op)
        elif "filter" in op_lower:
            categories["Filters"].append(op)
        elif "pivot" in op_lower:
            categories["Pivot Tables"].append(op)
        elif "conditional" in op_lower:
            categories["Conditional Formatting"].append(op)
        elif "namedrange" in op_lower:
            categories["Named Ranges"].append(op)
        elif "protected" in op_lower:
            categories["Protection"].append(op)
        elif "banded" in op_lower:
            categories["Banded Ranges"].append(op)
        elif "slicer" in op_lower:
            categories["Slicers"].append(op)
        elif "datasource" in op_lower:
            categories["Data Sources"].append(op)
        elif "developer" in op_lower or "metadata" in op_lower:
            categories["Developer Metadata"].append(op)
        elif "embed" in op_lower:
            categories["Embedded Objects"].append(op)
        elif "find" in op_lower or "replace" in op_lower:
            categories["Find & Replace"].append(op)
        elif "copy" in op_lower or "paste" in op_lower or "cut" in op_lower:
            categories["Copy & Paste"].append(op)
        elif "sort" in op_lower:
            categories["Sorting"].append(op)
        elif "group" in op_lower:
            categories["Grouping"].append(op)
        elif "spreadsheet" in op_lower:
            categories["Spreadsheet Properties"].append(op)
        elif "table" in op_lower:
            categories["Tables"].append(op)
        elif "text" in op_lower:
            categories["Text Operations"].append(op)
        elif "trim" in op_lower:
            categories["Data Cleanup"].append(op)
        elif "refresh" in op_lower:
            categories["Refresh"].append(op)
        else:
            categories["Other"].append(op)

    return dict(categories)


def main():
    """Main function to extract and display batch operations."""
    discovery = load_discovery()

    # Extract all request types
    request_types = extract_request_types(discovery)

    print("=" * 80)
    print("GOOGLE SHEETS BATCHUPDATE OPERATIONS")
    print("=" * 80)
    print(f"\nTotal operations: {len(request_types)}\n")

    # Categorize operations
    categories = categorize_operations(request_types)

    # Output categorized operations
    output = {
        "total_operations": len(request_types),
        "categories": {},
        "operations": {},
    }

    for category, ops in sorted(categories.items()):
        print(f"\n## {category} ({len(ops)} operations)")
        print("-" * 60)
        output["categories"][category] = ops

        for op in ops:
            # Get the request schema name (e.g., "updateCells" -> "UpdateCellsRequest")
            schema_name = op[0].upper() + op[1:] + "Request"
            schema = get_schema_details(discovery, schema_name)

            description = schema.get("description", "No description")
            # Truncate long descriptions
            if len(description) > 200:
                description = description[:200] + "..."

            print(f"\n### {op}")
            print(f"    {description}")

            # Get field summary
            fields = flatten_schema(discovery, schema, depth=0, max_depth=2)
            if fields:
                print("    Fields:")
                for field_name, field_info in fields.items():
                    field_type = field_info.get("_type", "unknown")
                    print(f"      - {field_name}: {field_type}")

            output["operations"][op] = {
                "schema": schema_name,
                "description": schema.get("description", ""),
                "fields": fields,
            }

    # Write JSON output
    output_path = Path(__file__).parent.parent / "docs" / "batch_operations.json"
    with output_path.open("w") as f:
        json.dump(output, f, indent=2)

    print(f"\n\n{'=' * 80}")
    print(f"JSON output written to: {output_path}")
    print(f"{'=' * 80}")


if __name__ == "__main__":
    main()
