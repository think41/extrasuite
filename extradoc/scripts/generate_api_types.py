#!/usr/bin/env python3
"""Generate Pydantic v2 models from the Google Docs API discovery document.

Usage:
    cd extradoc
    uv run python scripts/generate_api_types.py

Reads docs/discovery.json and writes src/extradoc/api_types/_generated.py.
"""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

DISCOVERY_PATH = Path(__file__).resolve().parent.parent / "docs" / "discovery.json"
OUTPUT_PATH = (
    Path(__file__).resolve().parent.parent
    / "src"
    / "extradoc"
    / "api_types"
    / "_generated.py"
)


def camel_to_snake(name: str) -> str:
    """Convert camelCase to snake_case."""
    s1 = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
    s2 = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s1)
    return s2.lower()


def make_enum_name(schema_name: str, prop_name: str) -> str:
    """Generate a unique enum class name from schema + property names."""
    suffix = prop_name[0].upper() + prop_name[1:]
    return schema_name + suffix


def topological_sort(schemas: dict[str, dict]) -> list[str]:
    """Sort schema names so dependencies come before dependents."""
    deps: dict[str, set[str]] = defaultdict(set)
    all_names = set(schemas.keys())

    for name, schema in schemas.items():
        for prop in schema.get("properties", {}).values():
            ref = prop.get("$ref")
            if ref and ref in all_names:
                deps[name].add(ref)
            items = prop.get("items", {})
            ref = items.get("$ref")
            if ref and ref in all_names:
                deps[name].add(ref)
            addl = prop.get("additionalProperties", {})
            ref = addl.get("$ref")
            if ref and ref in all_names:
                deps[name].add(ref)

    # Kahn's algorithm
    in_degree = dict.fromkeys(all_names, 0)
    reverse: dict[str, set[str]] = defaultdict(set)
    for name, dep_set in deps.items():
        for dep in dep_set:
            reverse[dep].add(name)

    in_degree = dict.fromkeys(all_names, 0)
    for name, dep_set in deps.items():
        in_degree[name] = len(dep_set)

    queue = sorted(n for n in all_names if in_degree[n] == 0)
    result: list[str] = []
    while queue:
        node = queue.pop(0)
        result.append(node)
        for dependent in sorted(reverse.get(node, [])):
            in_degree[dependent] -= 1
            if in_degree[dependent] == 0:
                queue.append(dependent)

    # Handle cycles (Document -> Tab -> Body -> ... -> Document)
    remaining = all_names - set(result)
    if remaining:
        print(f"Warning: circular deps detected for: {remaining}", file=sys.stderr)
        result.extend(sorted(remaining))

    return result


def collect_enums(
    schemas: dict[str, dict],
) -> tuple[dict[str, tuple[str, list[str]]], dict[tuple[str, str], str]]:
    """Collect all inline enums.

    Returns:
        enums: {enum_class_name: (description, [values])}
        prop_to_enum: {(schema_name, prop_name): enum_class_name}
    """
    enums: dict[str, tuple[str, list[str]]] = {}
    prop_to_enum: dict[tuple[str, str], str] = {}
    values_to_name: dict[tuple[str, ...], str] = {}

    for schema_name, schema in schemas.items():
        for prop_name, prop in schema.get("properties", {}).items():
            if "enum" not in prop:
                continue
            values = prop["enum"]
            desc = prop.get("description", "")
            values_key = tuple(values)

            if values_key in values_to_name:
                enum_name = values_to_name[values_key]
            else:
                enum_name = make_enum_name(schema_name, prop_name)
                enums[enum_name] = (desc, values)
                values_to_name[values_key] = enum_name

            prop_to_enum[(schema_name, prop_name)] = enum_name

    return enums, prop_to_enum


def generate_field_type(
    prop: dict,
    schema_name: str,
    prop_name: str,
    prop_to_enum: dict[tuple[str, str], str],
) -> str:
    """Generate the Python type annotation for a property."""
    key = (schema_name, prop_name)

    if key in prop_to_enum:
        return prop_to_enum[key]

    ref = prop.get("$ref")
    if ref:
        return ref

    ptype = prop.get("type", "")

    if ptype == "string":
        return "str"
    if ptype == "boolean":
        return "bool"
    if ptype == "integer":
        return "int"
    if ptype == "number":
        return "float"

    if ptype == "array":
        items = prop.get("items", {})
        items_ref = items.get("$ref")
        if items_ref:
            return f"list[{items_ref}]"
        items_type = items.get("type", "")
        if items_type == "string":
            return "list[str]"
        if items_type == "integer":
            return "list[int]"
        return "list[Any]"

    if ptype == "object" and "additionalProperties" in prop:
        addl = prop["additionalProperties"]
        addl_ref = addl.get("$ref")
        if addl_ref:
            return f"dict[str, {addl_ref}]"
        return "dict[str, Any]"

    return "Any"


def _needs_any_import(schemas: dict[str, dict]) -> bool:
    """Check if Any is used in any generated type annotation."""
    for schema in schemas.values():
        for prop in schema.get("properties", {}).values():
            ptype = prop.get("type", "")
            if ptype == "array":
                items = prop.get("items", {})
                if not items.get("$ref") and items.get("type") not in (
                    "string",
                    "integer",
                ):
                    return True
            if ptype == "object" and "additionalProperties" in prop:
                addl = prop["additionalProperties"]
                if not addl.get("$ref"):
                    return True
            if not prop.get("$ref") and not ptype and "enum" not in prop:
                return True
    return False


def generate_code(schemas: dict[str, dict]) -> str:
    """Generate the full Python module source."""
    enums, prop_to_enum = collect_enums(schemas)
    sorted_names = topological_sort(schemas)
    needs_any = _needs_any_import(schemas)

    lines: list[str] = []

    # Module header
    lines.append('"""Google Docs API types - auto-generated from discovery.json.')
    lines.append("")
    lines.append("Do not edit manually. Regenerate with:")
    lines.append("    cd extradoc")
    lines.append("    uv run python scripts/generate_api_types.py")
    lines.append('"""')
    lines.append("")
    lines.append("from __future__ import annotations")
    lines.append("")
    lines.append("import sys")
    lines.append("")
    lines.append("if sys.version_info >= (3, 11):")
    lines.append("    from enum import StrEnum")
    lines.append("else:")
    lines.append("    from enum import Enum")
    lines.append("")
    lines.append("    class StrEnum(str, Enum):")
    lines.append('        """Backport of StrEnum for Python 3.10."""')
    lines.append("")
    lines.append("        pass")
    lines.append("")
    if needs_any:
        lines.append("from typing import Any")
    lines.append("")
    lines.append("from pydantic import BaseModel, ConfigDict, Field")
    lines.append("")
    lines.append("")

    # Generate enums (sorted by name for stability)
    for enum_name in sorted(enums.keys()):
        desc, values = enums[enum_name]
        lines.append(f"class {enum_name}(StrEnum):")
        if desc:
            short_desc = desc.split(".")[0] + "." if "." in desc else desc
            if len(short_desc) > 80:
                short_desc = short_desc[:77] + "..."
            lines.append(f'    """{short_desc}"""')
        lines.append("")
        for val in values:
            lines.append(f'    {val} = "{val}"')
        lines.append("")
        lines.append("")

    # Generate models
    for schema_name in sorted_names:
        schema = schemas[schema_name]
        props = schema.get("properties", {})
        desc = schema.get("description", "")

        lines.append(f"class {schema_name}(BaseModel):")
        if desc:
            lines.append(f'    """{desc}"""')
        lines.append("")
        lines.append(
            '    model_config = ConfigDict(populate_by_name=True, extra="allow")'
        )
        lines.append("")

        if not props:
            lines.append("    pass")
            lines.append("")
            lines.append("")
            continue

        for prop_name in sorted(props.keys()):
            prop = props[prop_name]
            snake_name = camel_to_snake(prop_name)
            field_type = generate_field_type(prop, schema_name, prop_name, prop_to_enum)

            field_args: list[str] = ["None"]
            if snake_name != prop_name:
                field_args.append(f'alias="{prop_name}"')

            field_str = f"Field({', '.join(field_args)})"
            lines.append(f"    {snake_name}: {field_type} | None = {field_str}")

        lines.append("")
        lines.append("")

    return "\n".join(lines)


def main() -> None:
    with DISCOVERY_PATH.open() as f:
        discovery = json.load(f)

    schemas = discovery["schemas"]
    print(f"Found {len(schemas)} schemas")

    code = generate_code(schemas)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w") as f:
        f.write(code)

    print(f"Generated {OUTPUT_PATH}")
    print(f"  {code.count('class ')} classes")
    print(f"  {len(code.splitlines())} lines")


if __name__ == "__main__":
    main()
