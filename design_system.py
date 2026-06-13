import re
import json
import math
from typing import Dict, Any, List, Optional


def hex_to_hsl(hex_color: str) -> tuple:
    hex_color = hex_color.lstrip("#")
    r, g, b = int(hex_color[0:2], 16) / 255.0, int(hex_color[2:4], 16) / 255.0, int(hex_color[4:6], 16) / 255.0
    mx, mn = max(r, g, b), min(r, g, b)
    l = (mx + mn) / 2.0
    if mx == mn:
        return (0, 0, round(l * 100))
    s = (mx - mn) / (1 - abs(2 * l - 1)) if l > 0 else 0
    if mx == r:
        h = ((g - b) / (mx - mn)) % 6
    elif mx == g:
        h = (b - r) / (mx - mn) + 2
    else:
        h = (r - g) / (mx - mn) + 4
    h = round(h * 60)
    return (h if h >= 0 else h + 360, round(s * 100), round(l * 100))


def hsl_to_hex(h: int, s: int, l: int) -> str:
    h, s, l = h / 360.0, s / 100.0, l / 100.0
    c = (1 - abs(2 * l - 1)) * s
    x = c * (1 - abs((h * 6) % 2 - 1))
    m = l - c / 2.0
    if h < 1.0 / 6:
        r, g, b = c, x, 0
    elif h < 2.0 / 6:
        r, g, b = x, c, 0
    elif h < 3.0 / 6:
        r, g, b = 0, c, x
    elif h < 4.0 / 6:
        r, g, b = 0, x, c
    elif h < 5.0 / 6:
        r, g, b = x, 0, c
    else:
        r, g, b = c, 0, x
    return f"#{round((r + m) * 255):02x}{round((g + m) * 255):02x}{round((b + m) * 255):02x}"


PRESETS_CONFIG = {
    "minimal": {
        "saturation_curve": [0.4, 0.55, 0.7, 0.85, 1.0, 1.0, 0.9, 0.8, 0.7, 0.6],
        "lightness_curve": [95, 88, 78, 65, 50, 38, 28, 20, 14, 8],
        "radius_base": 4,
        "shadow_intensity": 0.5,
        "font_display": "Inter",
        "font_body": "Inter",
        "heading_weight": 500,
    },
    "corporate": {
        "saturation_curve": [0.3, 0.45, 0.6, 0.75, 0.9, 0.95, 0.85, 0.75, 0.65, 0.55],
        "lightness_curve": [96, 90, 80, 68, 55, 42, 32, 24, 18, 12],
        "radius_base": 2,
        "shadow_intensity": 0.3,
        "font_display": "Playfair Display",
        "font_body": "Inter",
        "heading_weight": 700,
    },
    "saas": {
        "saturation_curve": [0.5, 0.65, 0.8, 0.95, 1.0, 1.0, 0.95, 0.85, 0.75, 0.65],
        "lightness_curve": [95, 87, 76, 62, 48, 36, 26, 18, 12, 6],
        "radius_base": 8,
        "shadow_intensity": 0.7,
        "font_display": "Inter",
        "font_body": "Inter",
        "heading_weight": 600,
    },
    "mobile": {
        "saturation_curve": [0.6, 0.7, 0.85, 1.0, 1.0, 1.0, 0.95, 0.85, 0.75, 0.65],
        "lightness_curve": [96, 88, 78, 65, 50, 38, 28, 20, 14, 8],
        "radius_base": 12,
        "shadow_intensity": 0.6,
        "font_display": "SF Pro Display",
        "font_body": "SF Pro Text",
        "heading_weight": 700,
    },
    "ai": {
        "saturation_curve": [0.7, 0.8, 0.9, 1.0, 1.0, 1.0, 0.95, 0.9, 0.85, 0.8],
        "lightness_curve": [94, 86, 74, 60, 46, 34, 24, 16, 10, 4],
        "radius_base": 16,
        "shadow_intensity": 0.8,
        "font_display": "Space Grotesk",
        "font_body": "Inter",
        "heading_weight": 600,
    },
}

SCALE_STOPS = [50, 100, 200, 300, 400, 500, 600, 700, 800, 900]


def generate_color_scale(hex_color: str, preset: str = "saas", for_surface: bool = False) -> Dict[str, str]:
    config = PRESETS_CONFIG.get(preset, PRESETS_CONFIG["saas"])
    h, s, l = hex_to_hsl(hex_color)
    scale = {}
    for i, stop in enumerate(SCALE_STOPS):
        if for_surface:
            adj_s = max(0, min(100, round(s * config["saturation_curve"][i] * 0.15)))
            adj_l = config["lightness_curve"][i]
            if stop >= 500:
                adj_l = max(2, config["lightness_curve"][i] - 5 + round((stop - 500) / 400 * 15))
        else:
            adj_s = max(0, min(100, round(s * config["saturation_curve"][i])))
            adj_l = config["lightness_curve"][i]
        scale[str(stop)] = hsl_to_hex(h, adj_s, adj_l)
    return scale


def generate_semantic_colors(preset: str = "saas") -> Dict[str, Dict[str, str]]:
    return {
        "success": generate_color_scale("#4ade80", preset),
        "error": generate_color_scale("#f87171", preset),
        "warning": generate_color_scale("#fbbf24", preset),
        "info": generate_color_scale("#60a5fa", preset),
    }


def generate_typography(preset: str = "saas") -> Dict[str, Any]:
    config = PRESETS_CONFIG.get(preset, PRESETS_CONFIG["saas"])
    return {
        "font_family": {"display": config["font_display"], "body": config["font_body"]},
        "heading_weight": config["heading_weight"],
        "scale": {
            "displayLarge": {"size": 57, "weight": 400, "lineHeight": 64, "letterSpacing": -0.25},
            "displayMedium": {"size": 45, "weight": 400, "lineHeight": 52, "letterSpacing": 0},
            "displaySmall": {"size": 36, "weight": 400, "lineHeight": 44, "letterSpacing": 0},
            "headlineLarge": {"size": 32, "weight": config["heading_weight"], "lineHeight": 40, "letterSpacing": 0},
            "headlineMedium": {"size": 28, "weight": config["heading_weight"], "lineHeight": 36, "letterSpacing": 0},
            "headlineSmall": {"size": 24, "weight": config["heading_weight"], "lineHeight": 32, "letterSpacing": 0},
            "titleLarge": {"size": 22, "weight": 500, "lineHeight": 28, "letterSpacing": 0},
            "titleMedium": {"size": 16, "weight": 500, "lineHeight": 24, "letterSpacing": 0.15},
            "titleSmall": {"size": 14, "weight": 500, "lineHeight": 20, "letterSpacing": 0.1},
            "bodyLarge": {"size": 16, "weight": 400, "lineHeight": 24, "letterSpacing": 0.5},
            "bodyMedium": {"size": 14, "weight": 400, "lineHeight": 20, "letterSpacing": 0.25},
            "bodySmall": {"size": 12, "weight": 400, "lineHeight": 16, "letterSpacing": 0.4},
            "labelLarge": {"size": 14, "weight": 500, "lineHeight": 20, "letterSpacing": 0.1},
            "labelMedium": {"size": 12, "weight": 500, "lineHeight": 16, "letterSpacing": 0.5},
            "labelSmall": {"size": 11, "weight": 500, "lineHeight": 16, "letterSpacing": 0.5},
        },
    }


def generate_shadows(preset: str = "saas") -> List[Dict[str, Any]]:
    intensity = PRESETS_CONFIG.get(preset, PRESETS_CONFIG["saas"])["shadow_intensity"]
    return [
        {"name": "none", "value": "none"},
        {"name": "sm", "value": f"0 1px 2px 0 rgba(0,0,0,{0.05 * intensity:.3f})"},
        {"name": "md", "value": f"0 4px 6px -1px rgba(0,0,0,{0.1 * intensity:.3f})"},
        {"name": "lg", "value": f"0 10px 15px -3px rgba(0,0,0,{0.15 * intensity:.3f})"},
        {"name": "xl", "value": f"0 20px 25px -5px rgba(0,0,0,{0.2 * intensity:.3f})"},
    ]


SPACING_SCALE = [0, 4, 8, 12, 16, 20, 24, 32, 40, 48, 64]
RADIUS_SCALE = {
    "none": 0,
    "sm": 4,
    "md": 8,
    "lg": 12,
    "xl": 16,
    "full": 9999,
}


def generate_components(primary_scale: Dict[str, str], preset: str = "saas") -> Dict[str, Any]:
    p500 = primary_scale.get("500", "#7C6AF7")
    p50 = primary_scale.get("50", "#f3f0ff")
    p900 = primary_scale.get("900", "#3b2a7a")
    radius_base = PRESETS_CONFIG.get(preset, PRESETS_CONFIG["saas"])["radius_base"]
    return {
        "button": {
            "primary": {"bg": p500, "color": "#ffffff", "radius": radius_base, "padding": "12px 24px"},
            "secondary": {"bg": p50, "color": p900, "radius": radius_base, "padding": "12px 24px"},
            "ghost": {"bg": "transparent", "color": p500, "radius": radius_base, "padding": "12px 24px"},
        },
        "card": {
            "bg": "#ffffff", "radius": radius_base * 1.5, "padding": 16,
            "border": f"1px solid {primary_scale.get('200', '#e8e2fe')}",
            "shadow": f"0 4px 6px -1px rgba(0,0,0,0.1)",
        },
        "input": {
            "bg": "#ffffff", "radius": radius_base, "padding": "10px 14px",
            "border": f"1px solid {primary_scale.get('300', '#d2c6fe')}",
            "focus": f"2px solid {p500}",
        },
        "badge": {
            "bg": p50, "color": p900, "radius": radius_base * 2, "padding": "2px 8px",
            "fontSize": 12,
        },
    }


def get_surfaces(hex_color: str, preset: str = "saas", dark: bool = False) -> Dict[str, str]:
    _, s, l = hex_to_hsl(hex_color)
    config = PRESETS_CONFIG.get(preset, PRESETS_CONFIG["saas"])
    if dark:
        return {
            "background": "#0a0a0f",
            "surface": "#12121a",
            "surfaceVariant": "#1a1a28",
            "overlay": "rgba(0,0,0,0.4)",
            "inverseSurface": "#e8e8f0",
        }
    adjust_l = max(0, min(100, l + 40))
    adjust_s = max(0, min(100, s * 0.15))
    surface_base = hsl_to_hex(round(hex_to_hsl(hex_color)[0]), round(adjust_s), round(adjust_l))
    return {
        "background": "#f8f8fc",
        "surface": surface_base,
        "surfaceVariant": "#f0f0f8",
        "overlay": "rgba(0,0,0,0.1)",
        "inverseSurface": "#12121a",
    }


def generate_full_system(brand_name: str, primary_color: str, preset: str = "saas", dark: bool = False) -> Dict[str, Any]:
    primary_scale = generate_color_scale(primary_color, preset)
    h, s, l = hex_to_hsl(primary_color)
    secondary_h = (h + 30) % 360
    secondary_color = hsl_to_hex(secondary_h, s, l)
    secondary_scale = generate_color_scale(secondary_color, preset)
    neutral_scale = generate_color_scale("#64748b", preset)

    return {
        "brand_name": brand_name,
        "primary_color": primary_color,
        "style_preset": preset,
        "dark_mode": dark,
        "colors": {
            "primary": primary_scale,
            "secondary": secondary_scale,
            "neutral": neutral_scale,
            "semantic": generate_semantic_colors(preset),
            "surface": get_surfaces(primary_color, preset, dark),
        },
        "typography": generate_typography(preset),
        "spacing": SPACING_SCALE,
        "radius": RADIUS_SCALE,
        "shadows": generate_shadows(preset),
        "components": generate_components(primary_scale, preset),
    }


def generate_flutter_theme(tokens: Dict[str, Any]) -> str:
    c = tokens["colors"]
    p = c["primary"]
    s = c["secondary"]
    sem = c["semantic"]
    surf = c["surface"]
    typo = tokens["typography"]
    comp = tokens["components"]
    brand = tokens["brand_name"]
    is_dark = tokens.get("dark_mode", False)
    brightness = "Brightness.dark" if is_dark else "Brightness.light"
    bg = surf["background"]
    sf = surf["surface"]
    sfv = surf["surfaceVariant"]

    lines = [f"/// {brand} ThemeData — Material 3 Design Tokens",
             f"/// Generated by Brillance ({tokens['style_preset']} preset)",
             f"/// Dark mode: {str(is_dark).lower()}",
             "",
             "import 'package:flutter/material.dart';",
             "",
             f"final ThemeData {brand.lower().replace(' ', '_')}_theme = ThemeData(",
             "  useMaterial3: true,",
             f"  brightness: {brightness},",
             "  colorScheme: ColorScheme(",
             f"    primary: const Color(0xFF{p['500'].lstrip('#')}),",
             f"    onPrimary: const Color(0xFFFFFFFF),",
             f"    primaryContainer: const Color(0xFF{p['100'].lstrip('#')}),",
             f"    onPrimaryContainer: const Color(0xFF{p['900'].lstrip('#')}),",
             f"    secondary: const Color(0xFF{s['500'].lstrip('#')}),",
             f"    onSecondary: const Color(0xFFFFFFFF),",
             f"    secondaryContainer: const Color(0xFF{s['100'].lstrip('#')}),",
             f"    onSecondaryContainer: const Color(0xFF{s['900'].lstrip('#')}),",
             f"    error: const Color(0xFF{sem['error']['500'].lstrip('#')}),",
             f"    onError: const Color(0xFFFFFFFF),",
             f"    errorContainer: const Color(0xFF{sem['error']['100'].lstrip('#')}),",
             f"    onErrorContainer: const Color(0xFF{sem['error']['900'].lstrip('#')}),",
             f"    surface: const Color(0xFF{sf.lstrip('#')}),",
             f"    onSurface: const Color(0xFF{'e8e8f0' if is_dark else '12121a'}),",
             f"    surfaceContainerHighest: const Color(0xFF{sfv.lstrip('#')}),",
             f"    outline: const Color(0xFF{p['300'].lstrip('#')}),",
             f"    outlineVariant: const Color(0xFF{p['200'].lstrip('#')}),",
             "    brightness: brightness,",
             "  ),"]

    lines.append("  textTheme: TextTheme(")
    for name, val in typo["scale"].items():
        key = name[0].lower() + name[1:]
        lines.append(f"    {key}: TextStyle(")
        lines.append(f"      fontSize: {val['size']},")
        lines.append(f"      fontWeight: FontWeight.w{val['weight']},")
        lines.append(f"      height: {val['lineHeight'] / val['size']:.2f},")
        lines.append(f"      letterSpacing: {val['letterSpacing']},")
        lines.append("    ),")
    lines.append("  ),")

    radius = tokens["radius"]["md"]
    lines.append("  cardTheme: CardTheme(")
    lines.append(f"    color: const Color(0xFF{sf.lstrip('#')}),")
    lines.append(f"    surfaceTintColor: const Color(0xFF{p['500'].lstrip('#')}),")
    lines.append(f"    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular({radius})),")
    lines.append("  ),")

    btn = comp["button"]["primary"]
    lines.append("  elevatedButtonTheme: ElevatedButtonThemeData(")
    lines.append("    style: ElevatedButton.styleFrom(")
    lines.append(f"      backgroundColor: const Color(0xFF{btn['bg'].lstrip('#')}),")
    lines.append(f"      foregroundColor: const Color(0xFF{btn['color'].lstrip('#')}),")
    lines.append(f"      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular({btn['radius']})),")
    lines.append("    ),")
    lines.append("  ),")

    lines.append(");")
    return "\n".join(lines)


def generate_css_variables(tokens: Dict[str, Any]) -> str:
    c = tokens["colors"]
    typo = tokens["typography"]
    lines = [f"/* {tokens['brand_name']} Design Tokens */",
             f"/* Generated by Brillance ({tokens['style_preset']} preset) */",
             f"/* Dark mode: {str(tokens.get('dark_mode', False)).lower()} */",
             "",
             ":root {"]

    for name, scale in [("primary", c["primary"]), ("secondary", c["secondary"]), ("neutral", c["neutral"])]:
        for stop, val in scale.items():
            lines.append(f"  --color-{name}-{stop}: {val};")

    for sem_name, scale in c["semantic"].items():
        for stop, val in scale.items():
            lines.append(f"  --color-{sem_name}-{stop}: {val};")

    for name, val in c["surface"].items():
        css_name = re.sub(r'([A-Z])', r'-\1', name).lower()
        lines.append(f"  --surface-{css_name}: {val};")

    lines.append("")
    for name, val in tokens["radius"].items():
        lines.append(f"  --radius-{name}: {val}px;")
    lines.append("")
    for i, val in enumerate(tokens["spacing"]):
        lines.append(f"  --spacing-{i}: {val}px;")
    lines.append("")
    for shadow in tokens["shadows"]:
        lines.append(f"  --shadow-{shadow['name']}: {shadow['value']};")

    lines.append("")
    lines.append(f"  --font-display: '{typo['font_family']['display']}';")
    lines.append(f"  --font-body: '{typo['font_family']['body']}';")
    lines.append("}")
    return "\n".join(lines)


def generate_json_tokens(tokens: Dict[str, Any]) -> str:
    out = {
        "brand": tokens["brand_name"],
        "preset": tokens["style_preset"],
        "dark": tokens.get("dark_mode", False),
        "colors": tokens["colors"],
        "typography": tokens["typography"],
        "spacing": {f"spacing-{i}": v for i, v in enumerate(tokens["spacing"])},
        "borderRadius": tokens["radius"],
        "shadow": tokens["shadows"],
        "components": tokens["components"],
    }
    return json.dumps(out, indent=2)


def generate_figma_script(tokens: Dict[str, Any]) -> str:
    c = tokens["colors"]
    lines = [f"// {tokens['brand_name']} — Figma Local Variables Script",
             "// Paste into Figma Dev Console (Cmd+Opt+I / Ctrl+Shift+I)",
             "// Make sure you have a 'Brillance' variable collection selected",
             "",
             "const collection = figma.variables.createVariableCollection('Brillance');",
             "const modeId = collection.modes[0].modeId;",
             ""]

    for name, scale in [("primary", c["primary"]), ("secondary", c["secondary"]), ("neutral", c["neutral"])]:
        for stop, val in scale.items():
            r, g, b = int(val[1:3], 16), int(val[3:5], 16), int(val[5:7], 16)
            lines.append(f"const v_{name}_{stop} = collection.createVariable('{name}/{stop}', 'COLOR', '0x{val[1:]}');")
            lines.append(f"v_{name}_{stop}.setValueForMode(modeId, {{r: {r}, g: {g}, b: {b}, a: 1}});")

    return "\n".join(lines)


def generate_tailwind_config(tokens: Dict[str, Any]) -> str:
    c = tokens["colors"]
    lines = [f"// {tokens['brand_name']} — Tailwind CSS Config",
             "// Generated by Brillance Design System Generator",
             "",
             "module.exports = {",
             "  theme: {",
             "    extend: {",
             "      colors: {"]

    for name, scale in [("primary", c["primary"]), ("secondary", c["secondary"]), ("neutral", c["neutral"])]:
        lines.append(f"        {name}: {{")
        for stop, val in scale.items():
            lines.append(f"          '{stop}': '{val}',")
        lines.append("        },")

    lines.append("        success: {")
    for stop, val in c["semantic"]["success"].items():
        lines.append(f"          '{stop}': '{val}',")
    lines.append("        },")
    lines.append("        error: {")
    for stop, val in c["semantic"]["error"].items():
        lines.append(f"          '{stop}': '{val}',")
    lines.append("        },")
    lines.append("        warning: {")
    for stop, val in c["semantic"]["warning"].items():
        lines.append(f"          '{stop}': '{val}',")
    lines.append("        },")
    lines.append("        info: {")
    for stop, val in c["semantic"]["info"].items():
        lines.append(f"          '{stop}': '{val}',")
    lines.append("        },")

    lines.extend(["      },", "      borderRadius: {"])
    for name, val in tokens["radius"].items():
        lines.append(f"        {name}: '{val}px',")
    lines.extend(["      },", "    },", "  },", "};"])
    return "\n".join(lines)
