"""
Loads an OpenAPI 3.0 YAML spec from a local path or a GitHub (raw) URL,
and extracts a flat field list + a context string for the LLM.
"""

from pathlib import Path

import httpx
import yaml


def fetch_spec(source: str) -> dict:
    if source.startswith(("http://", "https://")):
        r = httpx.get(source, timeout=15, follow_redirects=True)
        r.raise_for_status()
        return yaml.safe_load(r.text)
    return yaml.safe_load(Path(source).read_text(encoding="utf-8"))


def _resolve_ref(ref: str, components: dict) -> dict:
    # handles '#/components/schemas/Foo'
    parts = ref.lstrip("#/").split("/")
    node = {"components": components}
    for part in parts:
        node = node[part]
    return node


def _flatten(schema: dict, components: dict, prefix: str = "", parent_required: set | None = None) -> list[dict]:
    if parent_required is None:
        parent_required = set()

    # resolve $ref
    if "$ref" in schema:
        schema = _resolve_ref(schema["$ref"], components)

    # unwrap allOf
    if "allOf" in schema:
        rows = []
        for sub in schema["allOf"]:
            rows.extend(_flatten(sub, components, prefix, parent_required))
        return rows

    rows = []
    props = schema.get("properties", {})
    own_required: set = set(schema.get("required", []))

    for name, prop in props.items():
        path = f"{prefix}.{name}" if prefix else name
        is_required = name in own_required

        if "$ref" in prop:
            prop = _resolve_ref(prop["$ref"], components)

        ptype = prop.get("type", "")
        nullable = prop.get("nullable", False) or (isinstance(ptype, list) and "null" in ptype)

        if ptype == "object" or "properties" in prop or "allOf" in prop:
            rows.extend(_flatten(prop, components, path))
        elif ptype == "array":
            items = prop.get("items", {})
            if "$ref" in items:
                items = _resolve_ref(items["$ref"], components)
            if items.get("type") == "object" or "properties" in items or "allOf" in items:
                rows.extend(_flatten(items, components, f"{path}[]"))
            else:
                rows.append(_make_row(f"{path}[]", items, is_required,
                                      override_description=prop.get("description")))
        else:
            rows.append(_make_row(path, prop, is_required))

    return rows


def _make_row(path: str, prop: dict, required: bool, override_description: str | None = None) -> dict:
    ptype = prop.get("type", "")
    if isinstance(ptype, list):
        type_str = " | ".join(t for t in ptype if t != "null")
    else:
        type_str = ptype

    nullable = prop.get("nullable", False) or (isinstance(prop.get("type"), list) and "null" in prop.get("type", []))
    enum     = prop.get("enum", [])
    notes_parts = []
    if nullable:
        notes_parts.append("Nullable")
    if enum:
        notes_parts.append("One of: " + ", ".join(str(e) for e in enum))
    if prop.get("format"):
        notes_parts.append(f"Format: {prop['format']}")

    example = prop.get("example", "")
    if example is None:
        example = ""

    return {
        "field_path":   path,
        "display_name": path.split(".")[-1].strip("[]").replace("_", " ").title(),
        "description":  override_description or prop.get("description", ""),
        "data_type":    type_str,
        "example":      str(example),
        "required":     "Yes" if required else "No",
        "notes":        "; ".join(notes_parts),
    }


def parse_spec(source: str) -> tuple[list[dict], str]:
    """
    Returns (fields, context_string).

    `source` can be:
      - A local file path:      "apis/orders/api-specification.yml"
      - A raw GitHub URL:       "https://raw.githubusercontent.com/org/repo/main/api-specification.yml"
    """
    spec       = fetch_spec(source)
    components = spec.get("components", {})
    info       = spec.get("info", {})

    # Extract fields from 2xx response schemas
    fields: list[dict] = []
    seen_refs: set[str] = set()

    for path_item in spec.get("paths", {}).values():
        for method, operation in path_item.items():
            if method not in ("get", "post", "put", "patch", "delete"):
                continue
            for status, response in operation.get("responses", {}).items():
                if not str(status).startswith("2"):
                    continue
                for media in response.get("content", {}).values():
                    schema = media.get("schema", {})
                    ref    = schema.get("$ref", "")
                    if ref and ref in seen_refs:
                        continue
                    if ref:
                        seen_refs.add(ref)
                    fields.extend(_flatten(schema, components))

    # Fallback: parse all component schemas if paths yielded nothing
    if not fields:
        for name, schema in components.get("schemas", {}).items():
            fields.extend(_flatten(schema, components))

    # Build LLM context: pass the full YAML (LLMs handle it well)
    context = (
        f"API: {info.get('title', 'Unknown')} v{info.get('version', '')}\n"
        f"{info.get('description', '')}\n\n"
        f"Full OpenAPI Specification:\n```yaml\n"
        f"{yaml.dump(spec, default_flow_style=False, allow_unicode=True, sort_keys=False)}"
        f"```"
    )

    return fields, context
