# Brillance API — Backend

FastAPI backend for the Brillance design-to-Flutter platform.

## Tech Stack

- **Python 3.12** + **FastAPI 0.111**
- **SQLite** (via `brillance.db`)
- **BeautifulSoup4** — HTML parsing
- **SvgParser** — SVG to component tree
- **Figma REST API** — Figma file/node import
- **OpenAI API** — AI code generation
- **Stripe** — subscription billing

## Quick Start

```bash
# Install
pip install -r requirements.txt

# Run
uvicorn main:app --reload --port 8000
```

Swagger UI: [http://localhost:8000/docs](http://localhost:8000/docs)

## API Endpoints

### HTML Import
| Method | Path | Description |
|--------|------|-------------|
| POST | `/parse/html` | Parse HTML file into component tree |
| POST | `/parse/html/element` | Parse a single HTML element (from iframe click) |
| POST | `/api/projects/{id}/raw-html` | Save raw HTML for preview |
| GET | `/preview/{id}` | Preview HTML in iframe |

### Figma Import
| Method | Path | Description |
|--------|------|-------------|
| POST | `/parse/figma/url` | Import components from Figma file URL |
| POST | `/parse/figma/file` | Import from uploaded .fig file |

### SVG Import
| Method | Path | Description |
|--------|------|-------------|
| POST | `/parse/svg` | Parse SVG file into component(s) |

### Flutter Code Generation
| Method | Path | Description |
|--------|------|-------------|
| POST | `/generate/flutter` | Generate Flutter widget from component tree |
| POST | `/generate/design-system` | Generate design system tokens + export |

### Project CRUD
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/projects` | List projects |
| POST | `/api/projects` | Create project |
| GET | `/api/projects/{id}` | Get project |
| DELETE | `/api/projects/{id}` | Delete project |
| POST | `/api/projects/{id}/components` | Save parsed component |
| GET | `/api/projects/{id}/components` | List components |
| POST | `/api/projects/{id}/selected-components` | Save selected component to DB |
| GET | `/api/projects/{id}/selected-components` | Get saved components |

### Stripe (Subscription)
| Method | Path | Description |
|--------|------|-------------|
| POST | `/stripe/create-checkout-session` | Create checkout session |
| POST | `/stripe/create-portal-session` | Billing portal |
| POST | `/stripe/webhook` | Stripe webhook |
| GET | `/subscription/{user_id}` | Get subscription status |

## Configuration

Set these as Railway environment variables:

| Variable | Description |
|----------|-------------|
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_KEY` | Supabase anon/service key |
| `OPENAI_API_KEY` | OpenAI API key |
| `STRIPE_SECRET_KEY` | Stripe secret key (sk_test_...) |
| `STRIPE_WEBHOOK_SECRET` | Stripe webhook signing secret |
| `STRIPE_PRO_PRICE_ID` | Stripe Pro price ID |
| `FRONTEND_URL` | Frontend URL (e.g. `https://brillance.pages.dev`) |

## Deployment

```bash
railway login
railway init
railway up
```

Or via **Railway Dashboard** → Connect `workspaccode/backend-design` repo.
Change the `startCommand` in Settings only if not using `railway.json`.
