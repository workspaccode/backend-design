import re
from uuid import uuid4
from typing import List, Dict, Any, Optional
from xml.etree import ElementTree as ET

TYPE_COLORS = {
    "button": "#7C6AF7",
    "card": "#10b981",
    "navbar": "#f59e0b",
    "input": "#3b82f6",
    "modal": "#ef4444",
    "form": "#8b5cf6",
    "section": "#6b7280",
    "custom": "#6b6b8a",
}

def _rgb_to_hex(r: int, g: int, b: int) -> str:
    return f"#{r:02x}{g:02x}{b:02x}"

def _parse_color(value: str) -> str:
    value = value.strip()
    if value.startswith("#"):
        return value[:7]
    m = re.match(r"rgb\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)", value)
    if m:
        return _rgb_to_hex(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return None

def _get_component_type(element: ET.Element) -> str:
    tag = element.tag.split("}")[-1] if "}" in element.tag else element.tag
    eid = (element.get("id") or "").lower()
    classes = (element.get("class") or "").lower()

    if re.search(r"btn|button|cta|action", eid + classes):
        return "button"
    if re.search(r"card|tile|panel|box|container", eid + classes):
        return "card"
    if re.search(r"nav|header|menu|toolbar", eid + classes):
        return "navbar"
    if re.search(r"input|field|search|form", eid + classes):
        return "input"

    if tag in ("rect", "circle", "ellipse", "path"):
        w = _parse_length(element.get("width", "0"))
        h = _parse_length(element.get("height", "0"))
        if w >= 150 and h >= 80:
            return "card"
        if 30 <= h <= 60 and w <= 300:
            return "button"
        return "custom"

    if tag == "text":
        return "custom"

    return "custom"

def _parse_length(val: str) -> float:
    try:
        return float(val.rstrip("px%").strip())
    except (ValueError, AttributeError):
        return 0.0

def _extract_fill(element: ET.Element, svg_ns: str) -> Optional[str]:
    fill = element.get("fill")
    if fill and fill != "none":
        hex_color = _parse_color(fill)
        if hex_color:
            return hex_color
    style = element.get("style", "")
    m = re.search(r"fill:\s*([^;]+)", style)
    if m:
        hex_color = _parse_color(m.group(1))
        if hex_color:
            return hex_color
    return None

def _get_text_content(element: ET.Element) -> str:
    parts = []
    for el in element.iter():
        tag = el.tag.split("}")[-1] if "}" in el.tag else el.tag
        if tag == "text" and el.text:
            parts.append(el.text.strip())
    return " ".join(parts) if parts else ""

def parse_svg(svg_content: str) -> List[Dict[str, Any]]:
    try:
        root = ET.fromstring(svg_content)
    except ET.ParseError as e:
        return _fallback_parse(svg_content)

    svg_ns = ""
    if root.tag.startswith("{"):
        svg_ns = root.tag.split("}")[0][1:]

    components = []

    viewbox = root.get("viewBox", "")
    vb_parts = viewbox.split()
    svg_w = _parse_length(vb_parts[2]) if len(vb_parts) > 2 else _parse_length(root.get("width", "400"))
    svg_h = _parse_length(vb_parts[3]) if len(vb_parts) > 3 else _parse_length(root.get("height", "400"))

    top_level_groups = []
    for child in root:
        tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
        if tag == "g":
            top_level_groups.append(child)

    if not top_level_groups:
        top_level_groups = [root]

    for group in top_level_groups:
        group_id = group.get("id", "")
        comp_type = _get_component_type(group)
        fill = _extract_fill(group)
        text = _get_text_content(group)

        g_styles = {}

        for el in group.iter():
            tag = el.tag.split("}")[-1] if "}" in el.tag else el.tag
            if tag in ("rect", "circle", "ellipse", "path"):
                el_fill = _extract_fill(el)
                if el_fill and not fill:
                    fill = el_fill
            if tag == "rect":
                rx = _parse_length(el.get("rx", "0"))
                if rx:
                    g_styles["radius"] = int(rx)

        padding = [16, 24] if comp_type in ("card", "navbar") else [12, 20]

        c = {
            "id": f"svg-{comp_type}-{uuid4().hex[:6]}",
            "name": group_id or f"{comp_type.capitalize()}_{uuid4().hex[:6]}",
            "type": comp_type,
            "styles": {
                "bg": fill or TYPE_COLORS.get(comp_type, "#16161f"),
                "color": "#ffffff",
                "radius": g_styles.get("radius", 8),
                "padding": padding,
                "fontSize": 14,
            },
            "bounds": {"w": min(svg_w, 400.0), "h": min(svg_h, 300.0)},
            "content": text or f"{comp_type.capitalize()} from SVG",
            "variants": ["default"],
        }
        components.append(c)

    if not components:
        components = _fallback_parse(svg_content)

    return components


def _fallback_parse(svg_text: str) -> List[Dict[str, Any]]:
    components = []

    rects = re.findall(r"<rect\s[^>]*>", svg_text, re.I)
    for i, rect in enumerate(rects):
        wm = re.search(r'width="([^"]+)"', rect)
        hm = re.search(r'height="([^"]+)"', rect)
        fm = re.search(r'fill="([^"]+)"', rect)
        rm = re.search(r'rx="([^"]+)"', rect)

        w = float(wm.group(1)) if wm else 200
        h = float(hm.group(1)) if hm else 120
        fill = fm.group(1) if fm else "#7C6AF7"
        radius = int(float(rm.group(1))) if rm else 8

        if fill.startswith("#"):
            fill = fill[:7]

        comp_type = "button" if (30 <= h <= 60 and w <= 300) else "card" if (h >= 80 and w >= 150) else "custom"

        components.append({
            "id": f"svg-rect-{i}",
            "name": f"Rect_{i+1}",
            "type": comp_type,
            "styles": {
                "bg": fill,
                "color": "#ffffff",
                "radius": radius,
                "padding": [12, 24] if comp_type == "button" else [16, 24],
                "fontSize": 14,
            },
            "bounds": {"w": w, "h": h},
            "content": f"{comp_type.capitalize()} SVG element",
            "variants": ["default"],
        })

    texts = re.findall(r"<text[^>]*>([^<]+)</text>", svg_text)
    text_content = " ".join(t.strip() for t in texts if t.strip())

    circles = re.findall(r"<circle\s[^>]*>", svg_text, re.I)
    for circle in circles:
        fm = re.search(r'fill="([^"]+)"', circle)
        fill = fm.group(1) if fm else "#10b981"
        if fill.startswith("#"):
            fill = fill[:7]
        components.append({
            "id": f"svg-circle-{uuid4().hex[:4]}",
            "name": "Avatar",
            "type": "custom",
            "styles": {"bg": fill, "color": "#ffffff", "radius": 999, "padding": [8, 8], "fontSize": 14},
            "bounds": {"w": 48.0, "h": 48.0},
            "content": "Avatar",
            "variants": ["default"],
        })

    if text_content and not any(c["type"] == "custom" for c in components):
        components.append({
            "id": f"svg-text-{uuid4().hex[:4]}",
            "name": "TextBlock",
            "type": "custom",
            "styles": {"bg": "transparent", "color": "#e8e8f0", "radius": 0, "padding": [8, 8], "fontSize": 16},
            "bounds": {"w": 300.0, "h": 40.0},
            "content": text_content[:60],
            "variants": ["default"],
        })

    if not components:
        components = [
            {
                "id": f"svg-default-{uuid4().hex[:6]}",
                "name": "SVGElement",
                "type": "custom",
                "styles": {"bg": "#16161f", "color": "#ffffff", "radius": 8, "padding": [12, 24], "fontSize": 14},
                "bounds": {"w": 200.0, "h": 200.0},
                "content": "SVG Graphic",
                "variants": ["default"],
            }
        ]

    return components
