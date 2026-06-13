import os
import sqlite3
import json
import uuid
import io
from typing import List, Dict, Any, Optional
import requests
from urllib.parse import urljoin

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.env'))
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'))

class DatabaseManager:
    def __init__(self, db_path: str = "brillance.db"):
        # Look for env vars in environment
        self.supabase_url = os.environ.get("SUPABASE_URL") or os.environ.get("VITE_SUPABASE_URL")
        self.supabase_key = os.environ.get("SUPABASE_KEY") or os.environ.get("VITE_SUPABASE_ANON_KEY")
        self.use_supabase = bool(self.supabase_url and self.supabase_key)
        
        # In Windows, we make sure db_path is in the backend/ folder
        script_dir = os.path.dirname(os.path.abspath(__file__))
        self.db_path = os.path.join(script_dir, db_path)
        
        if self.use_supabase:
            print("DatabaseManager: [CLOUD] Connected to Supabase DB via PostgREST Client")
            self.supabase_url = self.supabase_url.rstrip('/')
            self.base_url = f"{self.supabase_url}/rest/v1"
            self.headers = {
                "apikey": self.supabase_key,
                "Authorization": f"Bearer {self.supabase_key}",
                "Content-Type": "application/json",
                "Prefer": "return=representation"
            }
        else:
            print(f"DatabaseManager: [LOCAL] Connected to SQLite database ({self.db_path})")
            self._init_sqlite()

    def _init_sqlite(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Create projects table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            color TEXT DEFAULT '#7C6AF7',
            components_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            user_id TEXT
        )
        """)
        
        # Migration: add raw_html column if missing
        try:
            cursor.execute("ALTER TABLE projects ADD COLUMN raw_html TEXT")
        except sqlite3.OperationalError:
            pass  # column already exists
        
        # Create components table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS components (
            id TEXT PRIMARY KEY,
            project_id TEXT,
            name TEXT NOT NULL,
            type TEXT NOT NULL,
            styles TEXT, -- JSON String
            bounds TEXT, -- JSON String
            content TEXT,
            variants TEXT, -- JSON String
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
        )
        """)
        # Migration: add source and figma_url columns
        try:
            cursor.execute("ALTER TABLE components ADD COLUMN source TEXT DEFAULT 'html'")
        except sqlite3.OperationalError:
            pass
        try:
            cursor.execute("ALTER TABLE components ADD COLUMN figma_url TEXT")
        except sqlite3.OperationalError:
            pass
        try:
            cursor.execute("ALTER TABLE components ADD COLUMN page_name TEXT")
        except sqlite3.OperationalError:
            pass

        conn.commit()
        conn.close()
        
        self._init_selected_components()
        self._init_design_systems()
        self._init_usage_tracking()

    def _init_usage_tracking(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS usage_logs (
            id TEXT PRIMARY KEY,
            user_id TEXT,
            action TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS api_keys (
            id TEXT PRIMARY KEY,
            user_id TEXT,
            key_hash TEXT UNIQUE,
            key_prefix TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_used_at TIMESTAMP
        )
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_plans (
            user_id TEXT PRIMARY KEY,
            plan TEXT DEFAULT 'free',
            plan_expires_at TIMESTAMP
        )
        """)
        # Migration: add api_key_hash column to projects for incoming API key auth
        try:
            cursor.execute("ALTER TABLE projects ADD COLUMN api_key_hash TEXT")
        except sqlite3.OperationalError:
            pass
        conn.commit()
        conn.close()

    def _init_design_systems(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS design_systems (
            id TEXT PRIMARY KEY,
            project_id TEXT,
            name TEXT NOT NULL,
            primary_color TEXT,
            preset TEXT,
            tokens TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
        )
        """)
        conn.commit()
        conn.close()

    def _init_selected_components(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS selected_components (
            id TEXT PRIMARY KEY,
            project_id TEXT,
            element_html TEXT NOT NULL,
            flutter_code TEXT,
            component_name TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
        )
        """)
        conn.commit()
        conn.close()

    def get_projects(self) -> List[Dict[str, Any]]:
        if self.use_supabase:
            try:
                url = f"{self.base_url}/projects?select=*"
                res = requests.get(url, headers=self.headers, timeout=10)
                if res.status_code == 200:
                    projects = res.json()
                    # Re-map components key for frontend compatibility
                    for p in projects:
                        p["components"] = p.get("components_count", 0)
                    return projects
                else:
                    print(f"Supabase GET projects error: {res.status_code} - {res.text}")
                    return []
            except Exception as e:
                print(f"Supabase GET projects exception: {str(e)}")
                return []
        else:
            try:
                conn = sqlite3.connect(self.db_path)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM projects ORDER BY created_at DESC")
                rows = cursor.fetchall()
                projects = []
                for r in rows:
                    p = dict(r)
                    cursor.execute("SELECT COUNT(*) FROM components WHERE project_id = ?", (p["id"],))
                    count = cursor.fetchone()[0]
                    p["components"] = count
                    projects.append(p)
                conn.close()
                return projects
            except Exception as e:
                print(f"SQLite GET projects exception: {str(e)}")
                return []

    def get_project(self, project_id: str) -> Optional[Dict[str, Any]]:
        if self.use_supabase:
            try:
                url = f"{self.base_url}/projects?id=eq.{project_id}&select=*"
                res = requests.get(url, headers=self.headers, timeout=10)
                if res.status_code == 200 and res.json():
                    p = res.json()[0]
                    p["components"] = p.get("components_count", 0)
                    return p
                return None
            except Exception as e:
                print(f"Supabase GET project exception: {str(e)}")
                return None
        else:
            try:
                conn = sqlite3.connect(self.db_path)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM projects WHERE id = ?", (project_id,))
                row = cursor.fetchone()
                if row:
                    p = dict(row)
                    cursor.execute("SELECT COUNT(*) FROM components WHERE project_id = ?", (project_id,))
                    count = cursor.fetchone()[0]
                    p["components"] = count
                    conn.close()
                    return p
                conn.close()
                return None
            except Exception as e:
                print(f"SQLite GET project exception: {str(e)}")
                return None

    def create_project(self, name: str, description: str = "", color: str = "#7C6AF7", user_id: str = None, raw_html: str = None) -> Dict[str, Any]:
        project_id = str(uuid.uuid4())
        project_data = {
            "id": project_id,
            "name": name,
            "description": description,
            "color": color,
            "components_count": 0,
            "raw_html": raw_html,
            "user_id": user_id
        }
        
        if self.use_supabase:
            try:
                url = f"{self.base_url}/projects"
                res = requests.post(url, headers=self.headers, json=project_data, timeout=10)
                if res.status_code in [200, 201]:
                    inserted = res.json()[0] if res.json() else project_data
                    inserted["components"] = inserted.get("components_count", 0)
                    return inserted
                else:
                    raise Exception(f"Supabase POST project error: {res.status_code} - {res.text}")
            except Exception as e:
                print(f"Supabase CREATE project exception: {str(e)}")
                raise e
        else:
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO projects (id, name, description, color, components_count, raw_html, user_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (project_id, name, description, color, 0, raw_html, user_id))
                conn.commit()
                conn.close()
                project_data["components"] = 0
                return project_data
            except Exception as e:
                print(f"SQLite CREATE project exception: {str(e)}")
                raise e

    def delete_project(self, project_id: str) -> bool:
        if self.use_supabase:
            try:
                # PostgREST cascade handles components if foreign key has ON DELETE CASCADE
                url = f"{self.base_url}/projects?id=eq.{project_id}"
                res = requests.delete(url, headers=self.headers, timeout=10)
                return res.status_code in [200, 204]
            except Exception as e:
                print(f"Supabase DELETE project exception: {str(e)}")
                return False
        else:
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute("DELETE FROM components WHERE project_id = ?", (project_id,))
                cursor.execute("DELETE FROM projects WHERE id = ?", (project_id,))
                conn.commit()
                conn.close()
                return True
            except Exception as e:
                print(f"SQLite DELETE project exception: {str(e)}")
                return False

    def save_selected_component(self, project_id: str, element_html: str, flutter_code: str, component_name: str = None) -> Dict[str, Any]:
        comp_id = str(uuid.uuid4())
        record = {
            "id": comp_id,
            "project_id": project_id,
            "element_html": element_html,
            "flutter_code": flutter_code,
            "component_name": component_name or f"Component_{comp_id[:8]}",
        }
        if self.use_supabase:
            try:
                url = f"{self.base_url}/selected_components"
                res = requests.post(url, headers=self.headers, json=record, timeout=10)
                if res.status_code in [200, 201]:
                    return res.json()[0] if res.json() else record
                raise Exception(f"Supabase POST error: {res.status_code}")
            except Exception as e:
                print(f"Supabase save selected component exception: {str(e)}")
                raise e
        else:
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO selected_components (id, project_id, element_html, flutter_code, component_name)
                    VALUES (?, ?, ?, ?, ?)
                """, (comp_id, project_id, element_html, flutter_code, record["component_name"]))
                conn.commit()
                conn.close()
                return record
            except Exception as e:
                print(f"SQLite save selected component exception: {str(e)}")
                raise e

    def get_selected_components(self, project_id: str) -> List[Dict[str, Any]]:
        if self.use_supabase:
            try:
                url = f"{self.base_url}/selected_components?project_id=eq.{project_id}&select=*&order=created_at.desc"
                res = requests.get(url, headers=self.headers, timeout=10)
                if res.status_code == 200:
                    return res.json()
                return []
            except Exception as e:
                print(f"Supabase GET selected components exception: {str(e)}")
                return []
        else:
            try:
                conn = sqlite3.connect(self.db_path)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM selected_components WHERE project_id = ? ORDER BY created_at DESC", (project_id,))
                rows = cursor.fetchall()
                conn.close()
                return [dict(r) for r in rows]
            except Exception as e:
                print(f"SQLite GET selected components exception: {str(e)}")
                return []

    def save_design_system(self, project_id: str, name: str, primary_color: str, preset: str, tokens: dict) -> Dict[str, Any]:
        ds_id = str(uuid.uuid4())
        record = {
            "id": ds_id, "project_id": project_id, "name": name,
            "primary_color": primary_color, "preset": preset,
            "tokens": json.dumps(tokens) if not self.use_supabase else tokens,
        }
        if self.use_supabase:
            try:
                url = f"{self.base_url}/design_systems"
                res = requests.post(url, headers=self.headers, json=record, timeout=10)
                if res.status_code in [200, 201]:
                    return res.json()[0] if res.json() else record
                raise Exception(f"Supabase POST error: {res.status_code}")
            except Exception as e:
                print(f"Supabase save design system exception: {str(e)}")
                raise e
        else:
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO design_systems (id, project_id, name, primary_color, preset, tokens)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (ds_id, project_id, name, primary_color, preset, record["tokens"]))
                conn.commit()
                conn.close()
                return record
            except Exception as e:
                print(f"SQLite save design system exception: {str(e)}")
                raise e

    def get_design_systems(self, project_id: str = None) -> List[Dict[str, Any]]:
        if self.use_supabase:
            try:
                url = f"{self.base_url}/design_systems?select=*&order=created_at.desc"
                if project_id:
                    url = f"{self.base_url}/design_systems?project_id=eq.{project_id}&select=*&order=created_at.desc"
                res = requests.get(url, headers=self.headers, timeout=10)
                if res.status_code == 200:
                    return res.json()
                return []
            except Exception as e:
                print(f"Supabase GET design systems exception: {str(e)}")
                return []
        else:
            try:
                conn = sqlite3.connect(self.db_path)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                if project_id:
                    cursor.execute("SELECT * FROM design_systems WHERE project_id = ? ORDER BY created_at DESC", (project_id,))
                else:
                    cursor.execute("SELECT * FROM design_systems ORDER BY created_at DESC")
                rows = cursor.fetchall()
                conn.close()
                result = []
                for r in rows:
                    d = dict(r)
                    if isinstance(d.get("tokens"), str):
                        try:
                            d["tokens"] = json.loads(d["tokens"])
                        except: pass
                    result.append(d)
                return result
            except Exception as e:
                print(f"SQLite GET design systems exception: {str(e)}")
                return []

    def get_design_system(self, ds_id: str) -> Optional[Dict[str, Any]]:
        if self.use_supabase:
            try:
                url = f"{self.base_url}/design_systems?id=eq.{ds_id}&select=*"
                res = requests.get(url, headers=self.headers, timeout=10)
                if res.status_code == 200 and res.json():
                    return res.json()[0]
                return None
            except Exception as e:
                print(f"Supabase GET design system exception: {str(e)}")
                return None
        else:
            try:
                conn = sqlite3.connect(self.db_path)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM design_systems WHERE id = ?", (ds_id,))
                row = cursor.fetchone()
                conn.close()
                if row:
                    d = dict(row)
                    if isinstance(d.get("tokens"), str):
                        try:
                            d["tokens"] = json.loads(d["tokens"])
                        except: pass
                    return d
                return None
            except Exception as e:
                print(f"SQLite GET design system exception: {str(e)}")
                return None

    def delete_selected_component(self, comp_id: str) -> bool:
        if self.use_supabase:
            try:
                url = f"{self.base_url}/selected_components?id=eq.{comp_id}"
                res = requests.delete(url, headers=self.headers, timeout=10)
                return res.status_code in [200, 204]
            except Exception as e:
                print(f"Supabase DELETE selected component exception: {str(e)}")
                return False
        else:
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute("DELETE FROM selected_components WHERE id = ?", (comp_id,))
                conn.commit()
                conn.close()
                return True
            except Exception as e:
                print(f"SQLite DELETE selected component exception: {str(e)}")
                return False

    def get_project_components(self, project_id: str) -> List[Dict[str, Any]]:
        if self.use_supabase:
            try:
                url = f"{self.base_url}/components?project_id=eq.{project_id}&select=*"
                res = requests.get(url, headers=self.headers, timeout=10)
                if res.status_code == 200:
                    components = res.json()
                    for c in components:
                        if isinstance(c.get("styles"), str):
                            try:
                                c["styles"] = json.loads(c["styles"])
                            except:
                                pass
                        if isinstance(c.get("bounds"), str):
                            try:
                                c["bounds"] = json.loads(c["bounds"])
                            except:
                                pass
                        if isinstance(c.get("variants"), str):
                            try:
                                c["variants"] = json.loads(c["variants"])
                            except:
                                pass
                    return components
                else:
                    print(f"Supabase GET components error: {res.status_code} - {res.text}")
                    return []
            except Exception as e:
                print(f"Supabase GET components exception: {str(e)}")
                return []
        else:
            try:
                conn = sqlite3.connect(self.db_path)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM components WHERE project_id = ?", (project_id,))
                rows = cursor.fetchall()
                components = []
                for r in rows:
                    c = dict(r)
                    c["styles"] = json.loads(c["styles"]) if c["styles"] else {}
                    c["bounds"] = json.loads(c["bounds"]) if c["bounds"] else {}
                    c["variants"] = json.loads(c["variants"]) if c["variants"] else []
                    c["source"] = c.get("source", "html")
                    components.append(c)
                conn.close()
                return components
            except Exception as e:
                print(f"SQLite GET components exception: {str(e)}")
                return []

    def create_components(self, project_id: str, components: List[Dict[str, Any]]):
        if not components:
            return
            
        formatted_components = []
        for i, c in enumerate(components):
            c_id = c.get("id") or f"{c.get('type', 'comp')}-{i}-{str(uuid.uuid4())[:8]}"
            
            db_c = {
                "id": c_id,
                "project_id": project_id,
                "name": c.get("name", f"Component_{i+1}"),
                "type": c.get("type", "custom"),
                "content": c.get("content", ""),
                "source": c.get("source", "html"),
                "figma_url": c.get("figma_url"),
                "page_name": c.get("page_name"),
            }
            
            if self.use_supabase:
                db_c["styles"] = c.get("styles") or {}
                db_c["bounds"] = c.get("bounds") or {}
                db_c["variants"] = c.get("variants") or []
            else:
                db_c["styles"] = json.dumps(c.get("styles") or {})
                db_c["bounds"] = json.dumps(c.get("bounds") or {})
                db_c["variants"] = json.dumps(c.get("variants") or [])
                
            formatted_components.append(db_c)
            
        if self.use_supabase:
            try:
                # Bulk insert components to Supabase
                url = f"{self.base_url}/components"
                res = requests.post(url, headers=self.headers, json=formatted_components, timeout=10)
                if res.status_code not in [200, 201, 204]:
                    print(f"Supabase POST components error: {res.status_code} - {res.text}")
                
                # Sync project components count
                res_count = requests.get(f"{self.base_url}/components?project_id=eq.{project_id}&select=id", headers=self.headers, timeout=10)
                if res_count.status_code == 200:
                    count = len(res_count.json())
                    requests.patch(f"{self.base_url}/projects?id=eq.{project_id}", headers=self.headers, json={"components_count": count}, timeout=10)
            except Exception as e:
                print(f"Supabase CREATE components exception: {str(e)}")
        else:
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                for c in formatted_components:
                    cursor.execute("""
                    INSERT OR REPLACE INTO components (id, project_id, name, type, styles, bounds, content, variants, source, figma_url, page_name)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (c["id"], c["project_id"], c["name"], c["type"], c["styles"], c["bounds"], c["content"], c["variants"], c["source"], c["figma_url"], c["page_name"]))
                
                cursor.execute("SELECT COUNT(*) FROM components WHERE project_id = ?", (project_id,))
                count = cursor.fetchone()[0]
                cursor.execute("UPDATE projects SET components_count = ? WHERE id = ?", (count, project_id))
                
                conn.commit()
                conn.close()
            except Exception as e:
                print(f"SQLite CREATE components exception: {str(e)}")

    # ── Usage Tracking ────────────────────────────────────────────────

    FREE_LIMITS = {"imports_per_month": 3, "ai_generations_per_day": 10, "saved_components": 50, "design_systems": 3}
    PRO_LIMITS = {"imports_per_month": -1, "ai_generations_per_day": 500, "saved_components": -1, "design_systems": -1}

    def get_plan(self, user_id: str) -> str:
        if self.use_supabase:
            try:
                url = f"{self.base_url}/user_plans?user_id=eq.{user_id}&select=plan"
                res = requests.get(url, headers=self.headers, timeout=5)
                if res.status_code == 200 and res.json():
                    return res.json()[0].get("plan", "free")
                return "free"
            except: return "free"
        else:
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute("SELECT plan FROM user_plans WHERE user_id = ?", (user_id,))
                row = cursor.fetchone()
                conn.close()
                return row[0] if row else "free"
            except: return "free"

    def set_plan(self, user_id: str, plan: str):
        if self.use_supabase:
            try:
                url = f"{self.base_url}/user_plans?user_id=eq.{user_id}"
                res = requests.get(url, headers=self.headers, timeout=5)
                if res.status_code == 200 and res.json():
                    requests.patch(url, headers=self.headers, json={"plan": plan}, timeout=5)
                else:
                    requests.post(f"{self.base_url}/user_plans", headers=self.headers, json={"user_id": user_id, "plan": plan}, timeout=5)
            except: pass
        else:
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute("INSERT OR REPLACE INTO user_plans (user_id, plan) VALUES (?, ?)", (user_id, plan))
                conn.commit()
                conn.close()
            except: pass

    def get_limits(self, user_id: str) -> dict:
        plan = self.get_plan(user_id)
        return self.PRO_LIMITS if plan == "pro" else self.FREE_LIMITS

    def log_usage(self, user_id: str, action: str):
        log_id = str(uuid.uuid4())
        if self.use_supabase:
            try:
                url = f"{self.base_url}/usage_logs"
                requests.post(url, headers=self.headers, json={"id": log_id, "user_id": user_id, "action": action}, timeout=5)
            except: pass
        else:
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute("INSERT INTO usage_logs (id, user_id, action) VALUES (?, ?, ?)", (log_id, user_id, action))
                conn.commit()
                conn.close()
            except: pass

    def get_usage_stats(self, user_id: str) -> dict:
        now = __import__('datetime').datetime.now()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        if self.use_supabase:
            try:
                imports = requests.get(
                    f"{self.base_url}/usage_logs?user_id=eq.{user_id}&action=eq.import&created_at=gte.{month_start.isoformat()}&select=id",
                    headers=self.headers, timeout=5
                )
                gens = requests.get(
                    f"{self.base_url}/usage_logs?user_id=eq.{user_id}&action=eq.generate&created_at=gte.{today_start.isoformat()}&select=id",
                    headers=self.headers, timeout=5
                )
                import_count = len(imports.json()) if imports.status_code == 200 else 0
                gen_count = len(gens.json()) if gens.status_code == 200 else 0
            except:
                import_count = gen_count = 0
        else:
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM usage_logs WHERE user_id = ? AND action = 'import' AND created_at >= ?",
                               (user_id, month_start.isoformat()))
                import_count = cursor.fetchone()[0]
                cursor.execute("SELECT COUNT(*) FROM usage_logs WHERE user_id = ? AND action = 'generate' AND created_at >= ?",
                               (user_id, today_start.isoformat()))
                gen_count = cursor.fetchone()[0]
                conn.close()
            except:
                import_count = gen_count = 0

        plan = self.get_plan(user_id)
        limits = self.get_limits(user_id)
        return {
            "plan": plan,
            "imports_this_month": import_count,
            "imports_limit": limits["imports_per_month"],
            "generations_today": gen_count,
            "generations_limit": limits["ai_generations_per_day"],
            "reset_date": (now.replace(day=1) + __import__('datetime').timedelta(days=32)).replace(day=1).strftime("%B %d, %Y"),
        }

    # ── API Keys ──────────────────────────────────────────────────────

    def create_api_key(self, user_id: str) -> dict:
        import hashlib
        key_id = uuid.uuid4().hex[:12]
        secret = f"brk_live_{uuid.uuid4().hex}{uuid.uuid4().hex[:12]}"
        key_hash = hashlib.sha256(secret.encode()).hexdigest()
        key_prefix = f"brk_live_{key_id}"

        if self.use_supabase:
            try:
                url = f"{self.base_url}/api_keys"
                res = requests.post(url, headers=self.headers, json={
                    "id": str(uuid.uuid4()), "user_id": user_id,
                    "key_hash": key_hash, "key_prefix": key_prefix
                }, timeout=5)
                if res.status_code not in (200, 201):
                    raise Exception("Failed to save API key")
            except: raise
        else:
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute("INSERT INTO api_keys (id, user_id, key_hash, key_prefix) VALUES (?, ?, ?, ?)",
                               (str(uuid.uuid4()), user_id, key_hash, key_prefix))
                conn.commit()
                conn.close()
            except: raise

        return {"prefix": key_prefix, "full_key": secret}

    def get_api_keys(self, user_id: str) -> list:
        if self.use_supabase:
            try:
                url = f"{self.base_url}/api_keys?user_id=eq.{user_id}&select=*&order=created_at.desc"
                res = requests.get(url, headers=self.headers, timeout=5)
                return res.json() if res.status_code == 200 else []
            except: return []
        else:
            try:
                conn = sqlite3.connect(self.db_path)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("SELECT id, key_prefix, created_at, last_used_at FROM api_keys WHERE user_id = ? ORDER BY created_at DESC", (user_id,))
                rows = cursor.fetchall()
                conn.close()
                return [dict(r) for r in rows]
            except: return []

    def delete_api_key(self, key_id: str, user_id: str) -> bool:
        if self.use_supabase:
            try:
                url = f"{self.base_url}/api_keys?id=eq.{key_id}&user_id=eq.{user_id}"
                res = requests.delete(url, headers=self.headers, timeout=5)
                return res.status_code in (200, 204)
            except: return False
        else:
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute("DELETE FROM api_keys WHERE id = ? AND user_id = ?", (key_id, user_id))
                conn.commit()
                conn.close()
                return True
            except: return False

    def verify_api_key(self, key: str) -> Optional[str]:
        import hashlib
        key_hash = hashlib.sha256(key.encode()).hexdigest()
        if self.use_supabase:
            try:
                url = f"{self.base_url}/api_keys?key_hash=eq.{key_hash}&select=user_id"
                res = requests.get(url, headers=self.headers, timeout=5)
                if res.status_code == 200 and res.json():
                    return res.json()[0]["user_id"]
                return None
            except: return None
        else:
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute("SELECT user_id FROM api_keys WHERE key_hash = ?", (key_hash,))
                row = cursor.fetchone()
                conn.close()
                return row[0] if row else None
            except: return None

    # ── Supabase Storage ──────────────────────────────────────────────

    def _storage_headers(self):
        return {
            "apikey": self.supabase_key,
            "Authorization": f"Bearer {self.supabase_key}",
        }

    def storage_upload(self, bucket: str, path: str, data: bytes, content_type: str = "text/html") -> Optional[str]:
        if not self.use_supabase:
            return None
        try:
            url = f"{self.supabase_url}/storage/v1/object/{bucket}/{path}"
            headers = self._storage_headers()
            headers["Content-Type"] = content_type
            res = requests.put(url, headers=headers, data=data, timeout=30)
            if res.status_code in (200, 201):
                return f"{self.supabase_url}/storage/v1/object/public/{bucket}/{path}"
            print(f"Storage upload error: {res.status_code} - {res.text}")
            return None
        except Exception as e:
            print(f"Storage upload exception: {str(e)}")
            return None

    def storage_download(self, bucket: str, path: str) -> Optional[bytes]:
        if not self.use_supabase:
            return None
        try:
            url = f"{self.supabase_url}/storage/v1/object/{bucket}/{path}"
            headers = self._storage_headers()
            res = requests.get(url, headers=headers, timeout=30)
            if res.status_code == 200:
                return res.content
            return None
        except Exception as e:
            print(f"Storage download exception: {str(e)}")
            return None

    def storage_delete(self, bucket: str, path: str) -> bool:
        if not self.use_supabase:
            return False
        try:
            url = f"{self.supabase_url}/storage/v1/object/{bucket}/{path}"
            headers = self._storage_headers()
            res = requests.delete(url, headers=headers, timeout=15)
            return res.status_code in (200, 204)
        except Exception as e:
            print(f"Storage delete exception: {str(e)}")
            return False

    def storage_ensure_bucket(self, bucket: str) -> bool:
        if not self.use_supabase:
            return False
        try:
            url = f"{self.supabase_url}/storage/v1/bucket"
            headers = self._storage_headers()
            headers["Content-Type"] = "application/json"
            # Check if bucket exists
            res = requests.get(url, headers=headers, timeout=10)
            if res.status_code == 200:
                existing = [b["name"] for b in res.json()]
                if bucket in existing:
                    return True
            # Create bucket
            res2 = requests.post(url, headers=headers, json={"name": bucket, "public": True}, timeout=10)
            if res2.status_code in (200, 201):
                return True
            print(f"Storage ensure bucket error: {res2.status_code} - {res2.text}")
            return False
        except Exception as e:
            print(f"Storage ensure bucket exception: {str(e)}")
            return False

    def update_project_raw_html(self, project_id: str, raw_html: str) -> bool:
        if self.use_supabase:
            try:
                # Store raw HTML in Storage bucket
                self.storage_ensure_bucket("html-previews")
                path = f"{project_id}/index.html"
                url = self.storage_upload("html-previews", path, raw_html.encode("utf-8"))
                # Save Storage reference URL in the project row
                if url:
                    api_url = f"{self.base_url}/projects?id=eq.{project_id}"
                    res = requests.patch(api_url, headers=self.headers, json={"raw_html": url}, timeout=10)
                    return res.status_code in (200, 204)
                return False
            except Exception as e:
                print(f"Supabase UPDATE raw_html exception: {str(e)}")
                return False
        else:
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute("UPDATE projects SET raw_html = ? WHERE id = ?", (raw_html, project_id))
                conn.commit()
                conn.close()
                return True
            except Exception as e:
                print(f"SQLite UPDATE raw_html exception: {str(e)}")
                return False

    def get_project_raw_html(self, project_id: str) -> Optional[str]:
        if self.use_supabase:
            try:
                url = f"{self.base_url}/projects?id=eq.{project_id}&select=raw_html"
                res = requests.get(url, headers=self.headers, timeout=10)
                if res.status_code == 200 and res.json():
                    raw_html_ref = res.json()[0].get("raw_html")
                    if not raw_html_ref:
                        return None
                    # If it's a Storage URL, fetch the content
                    if raw_html_ref.startswith("http"):
                        file_res = requests.get(raw_html_ref, timeout=15)
                        if file_res.status_code == 200:
                            return file_res.text
                    return raw_html_ref
                return None
            except Exception as e:
                print(f"Supabase GET raw_html exception: {str(e)}")
                return None
        else:
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute("SELECT raw_html FROM projects WHERE id = ?", (project_id,))
                row = cursor.fetchone()
                conn.close()
                return row[0] if row else None
            except Exception as e:
                print(f"SQLite GET raw_html exception: {str(e)}")
                return None
