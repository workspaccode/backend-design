import re
import json
import requests
import math
from uuid import uuid4
from typing import Dict, Any, List, Optional


FIGMA_API_BASE = "https://api.figma.com/v1"


def extract_file_key(figma_url: str) -> Optional[str]:
    patterns = [
        r'figma\.com/file/([a-zA-Z0-9]+)',
        r'figma\.com/design/([a-zA-Z0-9]+)',
        r'figma\.com/proto/([a-zA-Z0-9]+)',
    ]
    for p in patterns:
        m = re.search(p, figma_url)
        if m:
            return m.group(1)
    return None


def fetch_figma_file(file_key: str, access_token: str) -> Optional[dict]:
    headers = {"X-Figma-Token": access_token}
    try:
        # Get full document in one call to avoid rate limits
        resp = requests.get(f"{FIGMA_API_BASE}/files/{file_key}", headers=headers, timeout=30)
        if resp.status_code == 200:
            return resp.json()
        elif resp.status_code == 403:
            raise PermissionError("Invalid Figma access token")
        elif resp.status_code == 404:
            raise FileNotFoundError("Figma file not found")
        else:
            raise Exception(f"Figma API error: {resp.status_code} - {resp.text[:200]}")
    except requests.Timeout:
        raise TimeoutError("Figma API request timed out")


FigmaNode = Dict[str, Any]


def rgba_to_hex(r: float, g: float, b: float, a: float = 1.0) -> str:
    return f"#{round(r * 255):02x}{round(g * 255):02x}{round(b * 255):02x}"


def extract_fill_color(node: FigmaNode) -> Optional[str]:
    fills = node.get("fills") or node.get("fillOverride") or []
    solid = next((f for f in fills if f.get("type") == "SOLID" and f.get("opacity", 1) > 0), None)
    if solid:
        c = solid["color"]
        return rgba_to_hex(c["r"], c["g"], c["b"], solid.get("opacity", 1))
    return None


def extract_text_color(node: FigmaNode) -> Optional[str]:
    # Check text fills first
    fills = node.get("fills") or []
    for f in fills:
        if f.get("type") == "SOLID" and f.get("visible", True):
            c = f["color"]
            return rgba_to_hex(c["r"], c["g"], c["b"])
    return "#e8e8f0"


def extract_corner_radius(node: FigmaNode) -> int:
    return node.get("cornerRadius") or node.get("rectangleCornerRadii", [0])[0] or 0


def extract_padding(node: FigmaNode) -> List[int]:
    pt = node.get("paddingTop") or node.get("itemSpacing", 0) or 0
    pr = node.get("paddingRight") or pt
    pb = node.get("paddingBottom") or pt
    pl = node.get("paddingLeft") or pt
    return [int(max(pt, pb, 0)), int(max(pl, pr, 0))]


def extract_effects(node: FigmaNode) -> List[Dict[str, Any]]:
    effects = node.get("effects") or []
    result = []
    for e in effects:
        if e.get("type") == "DROP_SHADOW":
            result.append({
                "type": "drop-shadow",
                "offsetX": e.get("offset", {}).get("x", 0),
                "offsetY": e.get("offset", {}).get("y", 0),
                "radius": e.get("radius", 0),
                "color": rgba_to_hex(
                    e.get("color", {}).get("r", 0),
                    e.get("color", {}).get("g", 0),
                    e.get("color", {}).get("b", 0),
                    e.get("color", {}).get("a", 0.5),
                ),
            })
    return result


def extract_font_size(node: FigmaNode) -> int:
    style = node.get("style") or {}
    return round(style.get("fontSize", 14))


def extract_font_weight(node: FigmaNode) -> int:
    style = node.get("style") or {}
    # Figma uses fontPostScriptName; map common names to weights
    fw = style.get("fontWeight", 400)
    return fw if isinstance(fw, (int, float)) else 400


def map_figma_type(figma_type: str, name: str = "") -> str:
    mapping = {
        "COMPONENT": "component",
        "COMPONENT_SET": "component_set",
        "FRAME": "container",
        "TEXT": "text",
        "RECTANGLE": "shape",
        "ELLIPSE": "shape",
        "GROUP": "group",
        "INSTANCE": "instance",
        "VECTOR": "icon",
        "IMAGE": "image",
        "LINE": "divider",
        "SLICE": "slice",
    }
    mt = mapping.get(figma_type, "custom")

    # Heuristic overrides based on name
    name_lower = name.lower()
    if mt in ("container", "shape") and any(k in name_lower for k in ["button", "btn", "cta"]):
        return "button"
    if mt in ("container", "shape") and any(k in name_lower for k in ["card", "tile", "item"]):
        return "card"
    if mt == "text" and any(k in name_lower for k in ["input", "field", "search"]):
        return "input"
    if any(k in name_lower for k in ["nav", "header", "toolbar"]):
        return "navbar"

    return mt


def extract_variants(node: FigmaNode) -> List[str]:
    variant_props = node.get("variantProperties", {}) or {}
    return list(variant_props.values()) if variant_props else ["default"]


def get_bounds(node: FigmaNode) -> Dict[str, float]:
    bb = node.get("absoluteBoundingBox") or {}
    return {
        "w": bb.get("width", 200),
        "h": bb.get("height", 44),
    }


def get_text_content(node: FigmaNode) -> str:
    text_data = node.get("characters") or ""
    return text_data[:60] if text_data else ""


def parse_figma_node(node: FigmaNode, parent_name: str = "") -> Optional[Dict[str, Any]]:
    node_type = node.get("type", "")
    name = node.get("name", "")
    visible = node.get("visible", True)

    if not visible or node_type in ("DOCUMENT", "CANVAS"):
        children = node.get("children", [])
        parsed_children = [parse_figma_node(c, name) for c in children]
        parsed_children = [c for c in parsed_children if c]
        if node_type == "CANVAS":
            return {"page": name, "components": parsed_children}
        return None

    if node_type == "COMPONENT_SET":
        children = node.get("children", [])
        parsed_children = [parse_figma_node(c, name) for c in children]
        parsed_children = [c for c in parsed_children if c]
        return {
            "id": node.get("id", uuid4().hex[:12]),
            "name": name,
            "type": "component_set",
            "children": parsed_children,
            "variants": extract_variants(node),
            "bounds": get_bounds(node),
            "styles": {
                "bg": extract_fill_color(node),
                "radius": extract_corner_radius(node),
                "padding": extract_padding(node),
            },
            "content": name,
        }

    children = node.get("children", [])
    parsed_children = [parse_figma_node(c, name) for c in children]
    parsed_children = [c for c in parsed_children if c]

    bb = node.get("absoluteBoundingBox") or {}
    mapped_type = map_figma_type(node_type, name)

    component = {
        "id": node.get("id", uuid4().hex[:12]),
        "name": name,
        "type": mapped_type,
        "source": "figma",
        "bounds": get_bounds(node),
        "styles": {
            "bg": extract_fill_color(node),
            "color": extract_text_color(node) if node_type == "TEXT" else None,
            "fontSize": extract_font_size(node) if node_type == "TEXT" else None,
            "fontWeight": extract_font_weight(node) if node_type == "TEXT" else None,
            "radius": extract_corner_radius(node),
            "padding": extract_padding(node),
            "width": bb.get("width"),
            "height": bb.get("height"),
            "effects": extract_effects(node),
        },
        "content": get_text_content(node) or name,
        "children": parsed_children if parsed_children else [],
        "variants": extract_variants(node),
    }

    # Clean up empty/None styles
    component["styles"] = {k: v for k, v in component["styles"].items() if v is not None and v != []}

    return component


def extract_file_styles(figma_data: dict) -> Dict[str, Any]:
    styles_raw = figma_data.get("styles") or {}
    style_defs = figma_data.get("styleDefinitions") or {}
    result = {"colors": {}, "typography": {}, "effects": {}}
    for sid, s in styles_raw.items():
        stype = s.get("styleType", "")
        name = s.get("name", "")
        if stype == "FILL":
            result["colors"][name] = f"#{s.get('description', '')}"
        elif stype == "TEXT":
            result["typography"][name] = {}
        elif stype == "EFFECT":
            result["effects"][name] = {}
    return result


def parse_figma_url(figma_url: str, access_token: str) -> Dict[str, Any]:
    file_key = extract_file_key(figma_url)
    if not file_key:
        raise ValueError("Invalid Figma URL format. Expected: https://www.figma.com/file/KEY/...")

    data = fetch_figma_file(file_key, access_token)
    if not data:
        raise Exception("Failed to fetch Figma file")

    doc = data.get("document", {})
    if not doc or doc.get("type") != "DOCUMENT":
        raise Exception("Invalid Figma document")

    pages_raw = doc.get("children", [])
    pages = []
    all_components = []
    total_count = 0

    for page_node in pages_raw:
        page_name = page_node.get("name", "Untitled")
        page_components = []
        for child in page_node.get("children", []):
            result = parse_figma_node(child)
            if result and "components" in result:
                page_components.append(result)
            elif result:
                page_components.append(result)

        flat = flatten_components(page_components)
        page_entry = {"page": page_name, "components": flat}
        pages.append(page_entry)
        all_components.extend(flat)
        total_count += len(flat)

    file_styles = extract_file_styles(data)
    file_name = data.get("name", "Untitled")

    return {
        "file_name": file_name,
        "file_key": file_key,
        "pages": pages,
        "components": all_components,
        "total": total_count,
        "styles": file_styles,
    }


def flatten_components(components: List, depth: int = 0) -> List:
    if depth > 5:
        return []
    result = []
    for c in components:
        if isinstance(c, dict):
            if c.get("type") in ("component_set", "container", "component", "group"):
                children = c.pop("children", [])
                cleaned = {k: v for k, v in c.items() if v != [] and v is not None}
                result.append(cleaned)
                if children:
                    result.extend(flatten_components(children, depth + 1))
            else:
                cleaned = {k: v for k, v in c.items() if v != [] and v is not None}
                result.append(cleaned)
    return result
