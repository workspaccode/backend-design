import os
import re
import json
from uuid import uuid4
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from bs4 import BeautifulSoup
import uvicorn
import requests
from db import DatabaseManager
from design_system import generate_full_system, generate_flutter_theme, generate_css_variables, generate_json_tokens, generate_figma_script, generate_tailwind_config
from figma_parser import parse_figma_url
from svg_parser import parse_svg
from limits import check_limit

app = FastAPI(title="Brillance API", version="1.0.0")
db = DatabaseManager()


# Enable CORS for frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ComponentTree Schema
class Bounds(BaseModel):
    w: Optional[float] = 120.0
    h: Optional[float] = 44.0

class Styles(BaseModel):
    bg: Optional[str] = "#7C6AF7"
    radius: Optional[int] = 8
    padding: Optional[List[int]] = [12, 24]
    color: Optional[str] = "#ffffff"
    fontSize: Optional[int] = 14

class ComponentNode(BaseModel):
    id: str
    name: str
    type: str  # button | card | navbar | form | input | modal | section | custom
    children: Optional[List[Any]] = []
    styles: Optional[Styles] = Styles()
    variants: Optional[List[str]] = ["default"]
    bounds: Optional[Bounds] = Bounds()
    content: Optional[str] = ""

class GenerateFlutterRequest(BaseModel):
    component_tree: Dict[str, Any]
    options: Optional[Dict[str, Any]] = {"rtl": False, "theme": "material3"}
    user_id: Optional[str] = None

class DesignSystemRequest(BaseModel):
    brand_name: str
    primary_color: str
    logo_url: Optional[str] = None
    style_preset: str  # Minimal | Corporate | SaaS/Dashboard | Mobile App | AI Tool

class ProjectCreate(BaseModel):
    name: str
    description: Optional[str] = ""
    color: Optional[str] = "#7C6AF7"
    user_id: Optional[str] = None

class ParseElementRequest(BaseModel):
    html: str
    context_css: Optional[str] = ""
    project_id: Optional[str] = None

class FigmaUrlRequest(BaseModel):
    figma_url: str
    access_token: str
    project_id: Optional[str] = None

class FigmaFileUpload(BaseModel):
    project_id: Optional[str] = None


# Helper to extract style attributes from raw inline style strings
def parse_inline_styles(style_str: Optional[str]) -> Dict[str, str]:
    if not style_str:
        return {}
    styles = {}
    for pair in style_str.split(';'):
        if ':' in pair:
            key, val = pair.split(':', 1)
            styles[key.strip().lower()] = val.strip()
    return styles

# Shared helper to extract components from HTML
def extract_components_from_html(html_content: str) -> List[ComponentNode]:
    soup = BeautifulSoup(html_content, "html.parser")
    components = []
    
    # 1. Search for Navbars
    navs = soup.find_all(["nav", "header"])
    for i, nav in enumerate(navs):
        if not nav or nav.parent is None:
            continue
        styles = parse_inline_styles(nav.get("style"))
        bg = styles.get("background-color") or styles.get("background") or "#0e0e16"
        components.append(
            ComponentNode(
                id=f"nav-{i}",
                name=nav.get("id") or f"NavBar_{i+1}",
                type="navbar",
                bounds=Bounds(w=320.0, h=56.0),
                styles=Styles(bg=bg, radius=0, padding=[12, 16]),
                content=nav.get_text(strip=True)[:30] or "Brand",
                variants=["default", "sticky"]
            )
        )
        nav.decompose()

    # 2. Search for Buttons
    buttons = soup.find_all(["button", "input"])
    for i, btn in enumerate(buttons):
        if not btn or btn.parent is None:
            continue
        if btn.name == "input" and btn.get("type") not in ["button", "submit", "reset"]:
            continue
        styles = parse_inline_styles(btn.get("style"))
        bg = styles.get("background-color") or styles.get("background") or "#7C6AF7"
        radius = int(re.search(r'\d+', styles.get("border-radius", "8px")).group()) if re.search(r'\d+', styles.get("border-radius", "")) else 8
        color = styles.get("color") or "#ffffff"
        text = btn.get("value") or btn.get_text(strip=True) or "Button"
        components.append(
            ComponentNode(
                id=f"btn-{i}",
                name=btn.get("id") or f"PrimaryButton_{i+1}",
                type="button",
                bounds=Bounds(w=180.0, h=44.0),
                styles=Styles(bg=bg, radius=radius, padding=[10, 20], color=color),
                content=text[:25],
                variants=["default", "hover", "disabled"]
            )
        )
        btn.decompose()

    # 3. Search for Inputs
    inputs = soup.find_all("input")
    for i, inp in enumerate(inputs):
        if not inp or inp.parent is None:
            continue
        styles = parse_inline_styles(inp.get("style"))
        bg = styles.get("background-color") or styles.get("background") or "#1a1a28"
        radius = int(re.search(r'\d+', styles.get("border-radius", "6px")).group()) if re.search(r'\d+', styles.get("border-radius", "")) else 6
        placeholder = inp.get("placeholder") or "Enter text..."
        components.append(
            ComponentNode(
                id=f"input-{i}",
                name=inp.get("id") or f"InputField_{i+1}",
                type="input",
                bounds=Bounds(w=240.0, h=48.0),
                styles=Styles(bg=bg, radius=radius, padding=[12, 14], color="#e8e8f0"),
                content=placeholder[:30],
                variants=["default", "focused", "error"]
            )
        )
        inp.decompose()

    # 4. Search for Cards/Containers
    cards = soup.find_all(class_=re.compile(r"card|container|box|item|wrapper", re.I))
    for i, card in enumerate(cards):
        if not card or card.parent is None:
            continue
        styles = parse_inline_styles(card.get("style"))
        bg = styles.get("background-color") or styles.get("background") or "#16161f"
        radius = int(re.search(r'\d+', styles.get("border-radius", "12px")).group()) if re.search(r'\d+', styles.get("border-radius", "")) else 12
        components.append(
            ComponentNode(
                id=f"card-{i}",
                name=card.get("id") or f"CardComponent_{i+1}",
                type="card",
                bounds=Bounds(w=280.0, h=180.0),
                styles=Styles(bg=bg, radius=radius, padding=[16, 16]),
                content=card.get_text(strip=True)[:40] or "Card content description",
                variants=["default", "elevated", "outlined"]
            )
        )
        card.decompose()

    # Fallback to basic structural divs
    divs = soup.find_all("div")
    if not components and divs:
        for i, div in enumerate(divs[:5]):
            text = div.get_text(strip=True)
            if len(text) > 5:
                components.append(
                    ComponentNode(
                        id=f"custom-{i}",
                        name=f"SectionCard_{i+1}",
                        type="custom",
                        bounds=Bounds(w=300.0, h=120.0),
                        styles=Styles(bg="#111118", radius=10, padding=[14, 14]),
                        content=text[:50],
                        variants=["default"]
                    )
                )

    # Final fallback if HTML is entirely empty/generic
    if not components:
        components = [
            ComponentNode(
                id="btn-fallback",
                name="PrimaryButton",
                type="button",
                bounds=Bounds(w=200.0, h=48.0),
                styles=Styles(bg="#7C6AF7", radius=8, padding=[12, 24], color="#ffffff"),
                content="Get Started",
                variants=["default", "hover", "disabled"]
            ),
            ComponentNode(
                id="card-fallback",
                name="ProductCard",
                type="card",
                bounds=Bounds(w=260.0, h=160.0),
                styles=Styles(bg="#16161f", radius=12, padding=[16, 16], color="#e8e8f0"),
                content="Premium Product details here.",
                variants=["default", "hover"]
            )
        ]

    return components


def extract_single_element(html_snippet: str, context_css: str = "") -> Optional[ComponentNode]:
    soup = BeautifulSoup(html_snippet, "html.parser")
    el = soup.find()
    if not el:
        return None

    css = parse_inline_styles(context_css)
    tag = el.name.lower()

    bg = css.get("background-color") or css.get("background") or "#16161f"
    color = css.get("color") or "#e8e8f0"
    radius_match = re.search(r'(\d+(?:\.\d+)?)', css.get("border-radius", "0"))
    radius = int(float(radius_match.group(1))) if radius_match else 0
    font_size_match = re.search(r'(\d+(?:\.\d+)?)', css.get("font-size", "14"))
    font_size = int(float(font_size_match.group(1))) if font_size_match else 14

    padding_raw = css.get("padding", "0")
    parts = [int(float(v)) for v in re.findall(r'\d+(?:\.\d+)?', padding_raw)]
    padding = parts if parts else [12, 16]
    if len(padding) == 1:
        padding = [padding[0], padding[0]]

    text = el.get_text(strip=True) or el.get("value") or el.get("placeholder") or "Element"

    if tag == "button" or (tag == "input" and el.get("type") in ["button", "submit", "reset"]):
        type_ = "button"
        name = el.get("id") or f"Button_{uuid4().hex[:6]}"
        bounds = Bounds(w=180.0, h=44.0)
        variants = ["default", "hover", "disabled"]
    elif tag == "input":
        type_ = "input"
        name = el.get("id") or f"Input_{uuid4().hex[:6]}"
        bounds = Bounds(w=240.0, h=48.0)
        variants = ["default", "focused", "error"]
    elif tag in ("nav", "header"):
        type_ = "navbar"
        name = el.get("id") or f"NavBar_{uuid4().hex[:6]}"
        bounds = Bounds(w=320.0, h=56.0)
        bg = bg if bg != "#16161f" else "#0e0e16"
        variants = ["default", "sticky"]
    elif re.search(r"card|container|box|item|wrapper", " ".join(el.get("class") or []), re.I):
        type_ = "card"
        name = el.get("id") or f"Card_{uuid4().hex[:6]}"
        bounds = Bounds(w=280.0, h=180.0)
        variants = ["default", "elevated", "outlined"]
    else:
        type_ = "custom"
        name = el.get("id") or f"Section_{uuid4().hex[:6]}"
        bounds = Bounds(w=300.0, h=120.0)
        variants = ["default"]

    return ComponentNode(
        id=f"{type_}-{uuid4().hex[:8]}",
        name=name,
        type=type_,
        bounds=bounds,
        styles=Styles(
            bg=bg,
            radius=radius,
            padding=padding,
            color=color,
            fontSize=font_size,
        ),
        content=text[:50],
        variants=variants,
    )


# Parse HTML and extract ComponentTree (Stateless API)
@app.post("/parse/html")
async def parse_html(file: UploadFile = File(...), user_id: Optional[str] = Form(None)):
    if user_id:
        allowed, msg = check_limit(db, user_id, "import")
        if not allowed:
            raise HTTPException(status_code=429, detail=msg)
        db.log_usage(user_id, "import")

    try:
        contents = await file.read()
        html_content = contents.decode("utf-8")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read file: {str(e)}")

    components = extract_components_from_html(html_content)
    return [c.model_dump() for c in components]


@app.post("/parse/html/element")
async def parse_html_element(req: ParseElementRequest):
    component = extract_single_element(req.html, req.context_css)
    if not component:
        raise HTTPException(status_code=400, detail="Could not parse any element from the provided HTML")

    flutter_result = compile_tree_to_flutter(
        tree=component.model_dump(),
        rtl=False,
        theme="material3"
    )

    return {
        "component": component.model_dump(),
        "flutter_code": flutter_result
    }


# --- Figma Parser Routes ---

@app.post("/parse/figma/url")
async def parse_figma_url_endpoint(req: FigmaUrlRequest):
    if req.project_id:
        allowed, msg = check_limit(db, req.project_id, "import")
        if not allowed:
            raise HTTPException(status_code=429, detail=msg)
        db.log_usage(req.project_id, "import")
    try:
        result = parse_figma_url(req.figma_url, req.access_token)
        return result
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except TimeoutError as e:
        raise HTTPException(status_code=504, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Figma parse failed: {str(e)}")


@app.post("/parse/figma/file")
async def parse_figma_file_endpoint(file: UploadFile = File(...), project_id: Optional[str] = Form(None)):
    try:
        contents = await file.read()
        import zipfile, io
        from figma_parser import parse_figma_node

        if not file.filename or not file.filename.lower().endswith(".fig"):
            raise HTTPException(status_code=400, detail="Only .fig files are supported")

        with zipfile.ZipFile(io.BytesIO(contents)) as zf:
            if "document.json" not in zf.namelist():
                raise HTTPException(status_code=400, detail="Invalid .fig file: missing document.json")
            with zf.open("document.json") as doc_file:
                figma_data = json.loads(doc_file.read().decode("utf-8"))

        doc = figma_data.get("document", {})
        pages_raw = doc.get("children", [])
        pages = []
        all_components = []
        total_count = 0

        for page_node in pages_raw:
            page_name = page_node.get("name", "Untitled")
            page_components = []
            for child in page_node.get("children", []):
                result = parse_figma_node(child, page_name)
                if result:
                    page_components.append(result)

            from figma_parser import flatten_components
            flat = flatten_components(page_components)
            pages.append({"page": page_name, "components": flat})
            all_components.extend(flat)
            total_count += len(flat)

        return {
            "file_name": file.filename,
            "file_key": None,
            "pages": pages,
            "components": all_components,
            "total": total_count,
            "styles": {},
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fig file parse failed: {str(e)}")


# --- SVG Parser Route ---

@app.post("/parse/svg")
async def parse_svg_endpoint(file: UploadFile = File(...), user_id: Optional[str] = Form(None)):
    if user_id:
        allowed, msg = check_limit(db, user_id, "import")
        if not allowed:
            raise HTTPException(status_code=429, detail=msg)
        db.log_usage(user_id, "import")

    try:
        contents = await file.read()
        svg_text = contents.decode("utf-8")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read file: {str(e)}")

    if not svg_text.strip().startswith("<svg") and "<svg" not in svg_text[:200]:
        raise HTTPException(status_code=400, detail="File does not appear to be valid SVG")

    components = parse_svg(svg_text)
    return components


# --- Database Persistence Routes ---

@app.get("/api/projects")
async def get_projects():
    return db.get_projects()

@app.post("/api/projects")
async def create_project(project: ProjectCreate):
    try:
        return db.create_project(
            name=project.name,
            description=project.description,
            color=project.color,
            user_id=project.user_id
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/projects/{project_id}")
async def get_project(project_id: str):
    p = db.get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    return p

@app.delete("/api/projects/{project_id}")
async def delete_project(project_id: str):
    success = db.delete_project(project_id)
    if not success:
        raise HTTPException(status_code=404, detail="Project not found or failed to delete")
    return {"success": True}

@app.get("/api/projects/{project_id}/components")
async def get_project_components(project_id: str):
    return db.get_project_components(project_id)

@app.post("/api/projects/{project_id}/selected-components")
async def save_selected_component(project_id: str, req: dict):
    try:
        result = db.save_selected_component(
            project_id=project_id,
            element_html=req.get("element_html", ""),
            flutter_code=req.get("flutter_code", ""),
            component_name=req.get("component_name")
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/projects/{project_id}/selected-components")
async def get_selected_components(project_id: str):
    return db.get_selected_components(project_id)

@app.delete("/api/selected-components/{comp_id}")
async def delete_selected_component(comp_id: str):
    success = db.delete_selected_component(comp_id)
    if not success:
        raise HTTPException(status_code=404, detail="Component not found")
    return {"success": True}

@app.post("/api/projects/{project_id}/components")
async def save_project_components(project_id: str, components: List[Dict[str, Any]]):
    try:
        db.create_components(project_id, components)
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/projects/import-html")
async def import_html(
    file: UploadFile = File(...),
    name: Optional[str] = Form(None),
    description: Optional[str] = Form(""),
    color: Optional[str] = Form("#7C6AF7"),
    user_id: Optional[str] = Form(None)
):
    try:
        contents = await file.read()
        html_content = contents.decode("utf-8")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read file: {str(e)}")

    components = extract_components_from_html(html_content)
    
    # Resolve project name (cleanup filename)
    p_name = name or os.path.splitext(file.filename)[0]
    p_name = p_name.replace("-", " ").replace("_", " ").title()
    
    try:
        # Create Project
        proj = db.create_project(
            name=p_name,
            description=description or f"Imported components from {file.filename}",
            color=color,
            user_id=user_id,
            raw_html=html_content
        )
        
        # Save Components to project
        comp_list = [c.model_dump() for c in components]
        db.create_components(proj["id"], comp_list)
        
        proj["components"] = len(comp_list)
        return proj
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/projects/{project_id}/raw-html")
async def save_raw_html(project_id: str, file: UploadFile = File(...)):
    try:
        contents = await file.read()
        raw_html = contents.decode("utf-8")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read file: {str(e)}")
    
    success = db.update_project_raw_html(project_id, raw_html)
    if not success:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"success": True, "project_id": project_id}


@app.get("/preview/{project_id}")
async def preview_html(project_id: str):
    raw = db.get_project_raw_html(project_id)
    if not raw:
        raise HTTPException(status_code=404, detail="No HTML found for this project")
    
    injection_script = """
<script>
(function() {
  let selectedEl = null;
  
  document.addEventListener('click', function(e) {
    e.preventDefault();
    e.stopPropagation();
    
    const el = e.target;
    const styles = window.getComputedStyle(el);
    
    // Remove previous highlight
    if (selectedEl) {
      selectedEl.style.outline = selectedEl._brillancePrevOutline || 'none';
    }
    
    // Save current outline and highlight
    selectedEl = el;
    el._brillancePrevOutline = el.style.outline;
    el.style.outline = '2px solid #7C6AF7';
    el.style.outlineOffset = '2px';
    
    window.parent.postMessage({
      type: 'ELEMENT_SELECTED',
      html: el.outerHTML,
      tagName: el.tagName,
      computedStyles: {
        color: styles.color,
        backgroundColor: styles.backgroundColor,
        fontSize: styles.fontSize,
        borderRadius: styles.borderRadius,
        padding: styles.padding,
        fontWeight: styles.fontWeight,
      },
      bounds: {
        w: el.offsetWidth,
        h: el.offsetHeight,
      }
    }, '*');
  }, true);
  
  // Also add hover preview cursor
  document.addEventListener('mouseover', function(e) {
    if (e.target !== selectedEl) {
      e.target.style.cursor = 'pointer';
    }
  }, true);
})();
</script>
"""
    
    modified = raw.replace("</body>", f"{injection_script}</body>") if "</body>" in raw else raw + injection_script
    return HTMLResponse(content=modified)


# Temporary HTML storage for CORS-safe iframe previews
_temp_html_storage: Dict[str, str] = {}

@app.post("/serve/html")
async def serve_temp_html(file: UploadFile = File(...)):
    try:
        content = await file.read()
        html_content = content.decode("utf-8")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read file: {str(e)}")
    temp_id = uuid4().hex
    _temp_html_storage[temp_id] = html_content
    return {"preview_url": f"/preview/temp/{temp_id}", "temp_id": temp_id}


@app.get("/preview/temp/{temp_id}")
async def get_temp_preview(temp_id: str):
    html_content = _temp_html_storage.get(temp_id)
    if not html_content:
        raise HTTPException(status_code=404, detail="Temporary HTML not found or expired")

    injection_script = """
<script>
(function() {
  let selectedEl = null;
  document.addEventListener('click', function(e) {
    e.preventDefault(); e.stopPropagation();
    const el = e.target;
    const styles = window.getComputedStyle(el);
    if (selectedEl) {
      selectedEl.style.outline = selectedEl._brillancePrevOutline || 'none';
    }
    selectedEl = el;
    el._brillancePrevOutline = el.style.outline;
    el.style.outline = '2px solid #7C6AF7';
    el.style.outlineOffset = '2px';
    window.parent.postMessage({
      type: 'ELEMENT_SELECTED',
      html: el.outerHTML,
      tagName: el.tagName,
      computedStyles: {
        color: styles.color,
        backgroundColor: styles.backgroundColor,
        fontSize: styles.fontSize,
        borderRadius: styles.borderRadius,
        padding: styles.padding,
        fontWeight: styles.fontWeight,
      },
      bounds: { w: el.offsetWidth, h: el.offsetHeight }
    }, '*');
  }, true);
  document.addEventListener('mouseover', function(e) {
    if (e.target !== selectedEl) e.target.style.cursor = 'pointer';
  }, true);
})();
</script>
"""
    modified = html_content.replace("</body>", f"{injection_script}</body>") if "</body>" in html_content else html_content + injection_script
    return HTMLResponse(content=modified)


# Generate Flutter widget code from ComponentTree
@app.post("/generate/flutter")
async def generate_flutter(request: GenerateFlutterRequest):
    if request.user_id:
        allowed, msg = check_limit(db, request.user_id, "generate")
        if not allowed:
            raise HTTPException(status_code=429, detail=msg)
        db.log_usage(request.user_id, "generate")

    tree = request.component_tree
    options = request.options or {}
    rtl = options.get("rtl", False)
    theme = options.get("theme", "material3")
    
    # Try calling OpenAI / Gemini if environment API keys are available
    openai_key = os.environ.get("OPENAI_API_KEY")
    if openai_key:
        try:
            headers = {
                "Authorization": f"Bearer {openai_key}",
                "Content-Type": "application/json"
            }
            prompt = f"""
            You are an expert Flutter Developer. Generate a highly polished, responsive Flutter widget class using Material 3 guidelines.
            
            Component Name: {tree.get('name', 'CustomWidget')}
            Component Type: {tree.get('type', 'custom')}
            Content: {tree.get('content', '')}
            Styles: {json.dumps(tree.get('styles', {}))}
            Bounds: {json.dumps(tree.get('bounds', {}))}
            RTL Support: {rtl}
            Theme Choice: {theme}
            
            Follow these rules:
            1. Generate StatelessWidget by default, StatefulWidget only if interaction exists.
            2. Use ThemeData tokens: Theme.of(context).colorScheme.primary instead of hardcoded colors where applicable.
            3. Respect sizing, padding, and constraints.
            4. Use const constructors wherever possible.
            5. Support RTL with Directionality widget.
            6. Add doc comments to the widget class.
            7. Return ONLY the code block of the class without markdown markers.
            """
            
            data = {
                "model": "gpt-4o",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.2
            }
            
            response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=data, timeout=8)
            if response.status_code == 200:
                result = response.json()
                code = result["choices"][0]["message"]["content"]
                # Clean up any potential markdown wraps
                code = re.sub(r"^```dart\n|```$", "", code, flags=re.MULTILINE)
                return {"code": code.strip(), "tokens": tree.get("styles", {}), "imports": ["package:flutter/material.dart"]}
        except Exception as e:
            # Fallback to compiler below on API failure
            pass

    # High fidelity rule-based compiler (default fallback)
    code = compile_tree_to_flutter(tree, rtl, theme)
    return {
        "code": code,
        "tokens": tree.get("styles", {}),
        "imports": ["package:flutter/material.dart"]
    }


def compile_tree_to_flutter(tree: Dict[str, Any], rtl: bool, theme: str) -> str:
    name = tree.get("name", "CustomWidget")
    type_ = tree.get("type", "custom")
    content = tree.get("content", "Content")
    styles = tree.get("styles", {})
    bounds = tree.get("bounds", {})
    
    bg = styles.get("bg", "#7C6AF7")
    color = styles.get("color", "#ffffff")
    radius = styles.get("radius", 8)
    padding = styles.get("padding", [12, 24])
    h = bounds.get("h", 48.0)
    w = bounds.get("w", 200.0)

    # Setup colors based on theme tokens
    bg_hex = bg.replace("#", "0xFF") if bg.startswith("#") else "0xFF7C6AF7"
    color_hex = color.replace("#", "0xFF") if color.startswith("#") else "0xFFFFFFFF"
    
    body_widget = ""
    
    if type_ == "button":
        body_widget = f"""ElevatedButton(
        onPressed: () {{}},
        style: ElevatedButton.styleFrom(
          backgroundColor: const Color({bg_hex}),
          foregroundColor: const Color({color_hex}),
          elevation: 2,
          padding: const EdgeInsets.symmetric(
            horizontal: {padding[1] if len(padding) > 1 else padding[0]},
            vertical: {padding[0]},
          ),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular({radius}),
          ),
        ),
        child: const Text('{content}'),
      )"""

    elif type_ == "input":
        body_widget = f"""TextFormField(
        decoration: InputDecoration(
          hintText: '{content}',
          filled: true,
          fillColor: const Color({bg_hex}),
          contentPadding: const EdgeInsets.symmetric(
            horizontal: {padding[1] if len(padding) > 1 else padding[0]},
            vertical: {padding[0]},
          ),
          border: OutlineInputBorder(
            borderRadius: BorderRadius.circular({radius}),
            borderSide: BorderSide.none,
          ),
          enabledBorder: OutlineInputBorder(
            borderRadius: BorderRadius.circular({radius}),
            borderSide: BorderSide(color: Colors.white.withOpacity(0.08)),
          ),
          focusedBorder: OutlineInputBorder(
            borderRadius: BorderRadius.circular({radius}),
            borderSide: const BorderSide(color: Color(0xFF7C6AF7), width: 1.5),
          ),
        ),
        style: const TextStyle(color: Color({color_hex}), fontSize: 14),
      )"""

    elif type_ == "card":
        body_widget = f"""Container(
        width: {w},
        height: {h},
        padding: const EdgeInsets.all({padding[0]}),
        decoration: BoxDecoration(
          color: const Color({bg_hex}),
          borderRadius: BorderRadius.circular({radius}),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withOpacity(0.15),
              blurRadius: 10,
              offset: const Offset(0, 4),
            ),
          ],
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              '{content}',
              style: const TextStyle(
                color: Color({color_hex}),
                fontWeight: FontWeight.bold,
                fontSize: 16,
              ),
            ),
            const SizedBox(height: 8),
            Text(
              'Dynamic parsed component child text details.',
              style: TextStyle(
                color: const Color({color_hex}).withOpacity(0.7),
                fontSize: 13,
              ),
            ),
          ],
        ),
      )"""

    elif type_ == "navbar":
        body_widget = f"""Container(
        height: {h},
        padding: const EdgeInsets.symmetric(horizontal: 16),
        decoration: BoxDecoration(
          color: const Color({bg_hex}),
          border: Border(
            bottom: BorderSide(
              color: Colors.white.withOpacity(0.06),
              width: 1.0,
            ),
          ),
        ),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            const Icon(Icons.menu, color: Colors.white),
            Text(
              '{content}',
              style: const TextStyle(
                color: Colors.white,
                fontWeight: FontWeight.bold,
                fontSize: 18,
              ),
            ),
            const Icon(Icons.notifications_none, color: Colors.white),
          ],
        ),
      )"""

    else:
        # Custom section / fallback
        body_widget = f"""Container(
        width: {w},
        padding: const EdgeInsets.all({padding[0]}),
        decoration: BoxDecoration(
          color: const Color({bg_hex}),
          borderRadius: BorderRadius.circular({radius}),
        ),
        child: Text(
          '{content}',
          style: const TextStyle(color: Color({color_hex}), fontSize: 14),
        ),
      )"""

    # Apply RTL wrapper if specified
    if rtl:
      body_widget = f"""Directionality(
      textDirection: TextDirection.rtl,
      child: {body_widget},
    )"""

    flutter_class = f"""/// {name} widget parsed and generated by Brillance.
///
/// Follows Material 3 guidelines and supports adaptive dimensions.
class {name} extends StatelessWidget {{
  const {name}({{super.key}});

  @override
  Widget build(BuildContext context) {{
    return {body_widget};
  }}
}}"""
    return flutter_class


# Design System Token Generation Engine
@app.post("/generate/design-system")
async def generate_design_system(request: DesignSystemRequest):
    hex_color = request.primary_color.lstrip("#")
    tokens = generate_full_system(
        brand_name=request.brand_name,
        primary_color=f"#{hex_color}",
        preset=request.style_preset,
        dark=False
    )
    return tokens


# Export endpoints
class ExportRequest(BaseModel):
    tokens: Dict[str, Any]

@app.post("/export/theme-dart")
async def export_theme_dart(req: ExportRequest):
    return {"code": generate_flutter_theme(req.tokens)}


@app.post("/export/css-vars")
async def export_css_vars(req: ExportRequest):
    return {"code": generate_css_variables(req.tokens)}


@app.post("/export/json-tokens")
async def export_json_tokens(req: ExportRequest):
    return {"code": generate_json_tokens(req.tokens)}


@app.post("/export/figma-script")
async def export_figma_script(req: ExportRequest):
    return {"code": generate_figma_script(req.tokens)}


@app.post("/export/tailwind-config")
async def export_tailwind_config(req: ExportRequest):
    return {"code": generate_tailwind_config(req.tokens)}


# AI Enhancement
class EnhanceRequest(BaseModel):
    tokens: Dict[str, Any]
    brand_name: str
    primary_color: str
    preset: str

@app.post("/generate/design-system/enhance")
async def enhance_design_system(req: EnhanceRequest):
    openai_key = os.environ.get("OPENAI_API_KEY")
    if not openai_key:
        return {
            "enhancements": {
                "fonts": {"display": "Inter", "body": "Inter"},
                "suggestion": "Enable an OpenAI API key in your environment for AI-powered font recommendations.",
                "contrast_issues": []
            }
        }
    try:
        prompt = f"""You are a design system expert. Review the following design system tokens and suggest improvements.

Brand: {req.brand_name}
Primary Color: {req.primary_color}
Preset: {req.preset}

Current tokens (abbreviated):
{json.dumps(req.tokens, indent=2)[:1000]}

Respond in JSON with this exact structure:
{{
  "fonts": {{"display": "recommended font name", "body": "recommended font name"}},
  "suggestion": "1-2 sentence improvement suggestion",
  "contrast_issues": ["issue1", "issue2"]
}}

Only suggest changes if genuinely needed. Be conservative."""
        
        headers = {"Authorization": f"Bearer {openai_key}", "Content-Type": "application/json"}
        data = {"model": "gpt-4o", "messages": [{"role": "user", "content": prompt}], "temperature": 0.3, "response_format": {"type": "json_object"}}
        response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=data, timeout=15)
        if response.status_code == 200:
            result = response.json()
            return {"enhancements": json.loads(result["choices"][0]["message"]["content"])}
        return {"enhancements": {"fonts": {"display": "Inter", "body": "Inter"}, "suggestion": "AI service unavailable.", "contrast_issues": []}}
    except Exception as e:
        return {"enhancements": {"fonts": {"display": "Inter", "body": "Inter"}, "suggestion": f"AI enhancement error: {str(e)}", "contrast_issues": []}}


# ── Stripe Billing Endpoints ──────────────────────────────────────

import stripe as stripe_lib
stripe_lib.api_key = os.environ.get("STRIPE_SECRET_KEY")

STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET")
STRIPE_PRO_PRICE_ID = os.environ.get("STRIPE_PRO_PRICE_ID")
STRIPE_TEAM_PRICE_ID = os.environ.get("STRIPE_TEAM_PRICE_ID")

class CheckoutRequest(BaseModel):
    user_id: str
    plan: str  # "pro" | "team"
    success_url: str
    cancel_url: str

class PortalRequest(BaseModel):
    user_id: str

@app.post("/stripe/create-checkout")
async def stripe_create_checkout(req: CheckoutRequest):
    if not stripe_lib.api_key:
        raise HTTPException(status_code=400, detail="Stripe not configured — set STRIPE_SECRET_KEY")
    price_id = STRIPE_PRO_PRICE_ID if req.plan == "pro" else STRIPE_TEAM_PRICE_ID
    if not price_id:
        raise HTTPException(status_code=400, detail=f"Price ID not configured for plan: {req.plan}")

    try:
        session = stripe_lib.checkout.Session.create(
            mode="subscription",
            line_items=[{"price": price_id, "quantity": 1}],
            client_reference_id=req.user_id,
            success_url=req.success_url,
            cancel_url=req.cancel_url,
            metadata={"user_id": req.user_id, "plan": req.plan},
        )
        return {"checkout_url": session.url, "session_id": session.id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Stripe checkout failed: {str(e)}")

@app.post("/stripe/webhook")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    if not STRIPE_WEBHOOK_SECRET:
        raise HTTPException(status_code=400, detail="Webhook secret not configured")

    try:
        event = stripe_lib.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except stripe_lib.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    event_type = event["type"]
    data = event["data"]["object"]

    if event_type == "checkout.session.completed":
        user_id = data.get("client_reference_id") or data.get("metadata", {}).get("user_id")
        plan = data.get("metadata", {}).get("plan", "pro")
        if user_id:
            db.set_plan(user_id, plan)
            print(f"Stripe Webhook: User {user_id} upgraded to {plan}")

    elif event_type in ("customer.subscription.updated", "customer.subscription.deleted"):
        metadata = data.get("metadata", {})
        user_id = metadata.get("user_id")
        if event_type == "customer.subscription.deleted" and user_id:
            db.set_plan(user_id, "free")
            print(f"Stripe Webhook: User {user_id} downgraded to free")

    return {"received": True, "type": event_type}

@app.post("/stripe/billing-portal")
async def stripe_billing_portal(req: PortalRequest):
    if not stripe_lib.api_key:
        raise HTTPException(status_code=400, detail="Stripe not configured")

    try:
        # Create or retrieve Stripe customer
        session = stripe_lib.billing_portal.Session.create(
            customer=req.user_id,
            return_url=f"{os.environ.get('FRONTEND_URL', 'http://localhost:5173')}/settings?tab=billing",
        )
        return {"portal_url": session.url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Portal session failed: {str(e)}")

@app.get("/stripe/plan/{user_id}")
async def stripe_plan_status(user_id: str):
    plan = db.get_plan(user_id)
    return {"plan": plan, "status": "active" if plan != "free" else "inactive"}


# ── Usage & API Key Endpoints ─────────────────────────────────────

class LimitCheckRequest(BaseModel):
    user_id: str
    action: str  # 'import' | 'generate'

@app.post("/api/limits/check")
async def api_check_limit(req: LimitCheckRequest):
    allowed, message = check_limit(db, req.user_id, req.action)
    return {"allowed": allowed, "message": message}

@app.get("/api/usage/{user_id}")
async def api_get_usage(user_id: str):
    return db.get_usage_stats(user_id)

@app.get("/api/plan/{user_id}")
async def api_get_plan(user_id: str):
    plan = db.get_plan(user_id)
    limits = db.get_limits(user_id)
    return {"plan": plan, "limits": limits}

class CreateKeyRequest(BaseModel):
    user_id: str

@app.post("/api/keys")
async def api_create_key(req: CreateKeyRequest):
    try:
        result = db.create_api_key(req.user_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/keys/{user_id}")
async def api_list_keys(user_id: str):
    return db.get_api_keys(user_id)

@app.delete("/api/keys/{key_id}")
async def api_delete_key(key_id: str, user_id: str):
    success = db.delete_api_key(key_id, user_id)
    if not success:
        raise HTTPException(status_code=404, detail="Key not found")
    return {"success": True}

@app.post("/api/keys/verify")
async def api_verify_key(req: dict):
    key = req.get("key", "")
    user_id = db.verify_api_key(key)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return {"valid": True, "user_id": user_id}


# Design System Persistence
class DesignSystemSaveRequest(BaseModel):
    project_id: Optional[str] = None
    name: str
    primary_color: str
    preset: str
    tokens: Dict[str, Any]

@app.post("/api/design-systems")
async def save_design_system(req: DesignSystemSaveRequest):
    try:
        result = db.save_design_system(
            project_id=req.project_id,
            name=req.name,
            primary_color=req.primary_color,
            preset=req.preset,
            tokens=req.tokens
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/design-systems")
async def list_design_systems(project_id: Optional[str] = None):
    return db.get_design_systems(project_id)

@app.get("/api/design-systems/{ds_id}")
async def get_design_system(ds_id: str):
    ds = db.get_design_system(ds_id)
    if not ds:
        raise HTTPException(status_code=404, detail="Design system not found")
    return ds

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
