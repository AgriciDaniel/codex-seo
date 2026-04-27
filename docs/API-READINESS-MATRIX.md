# API Readiness Matrix

Last verified: April 27, 2026

This matrix distinguishes between:

- `Native script`: the underlying analyzer/generator the skill uses
- `Workflow wrapper`: the standardized machine-facing command in `scripts/run_skill_workflow.py`
- `Smoke status`: whether the non-interactive smoke suite completed successfully through the wrapper

## Standard API Command Shape

```bash
python scripts/run_skill_workflow.py --skill <skill-name> <target> --json
```

Full-suite validation:

```bash
python scripts/run_api_smoke_suite.py https://www.python.org --json
```

## Matrix

| Skill | Native Script | Wrapper Status | Smoke Status | Notes |
|------|------|------|------|------|
| `seo` | none | Routes via specialist wrappers / `seo-audit` | not separately tested | Orchestrator remains routing logic, not a standalone execution unit |
| `seo-audit` | `scripts/run_headless_audit.py` | complete | pass | Full headless pipeline, premium HTML/PDF supported |
| `seo-backlinks` | `scripts/backlinks_auth.py` + optional Common Crawl/Moz/Bing helpers | complete | pass | Detects available backlink tier and returns setup guidance when premium credentials are absent |
| `seo-cluster` | instruction-led with optional SERP/DataForSEO evidence | complete | pass | Wrapper records requested cluster context and marks specialist skill ready for evidence collection |
| `seo-page` | none previously | complete | pass | Now standardized through wrapper orchestration |
| `seo-technical` | `scripts/analyze_technical.py` | complete | pass | Wrapper adds deterministic report and cache write |
| `seo-content` | `scripts/analyze_content.py` | complete | pass | Wrapper adds deterministic report and cache write |
| `seo-schema` | `scripts/analyze_schema.py` | complete | pass | Wrapper writes report, summary, and generated JSON-LD |
| `seo-images` | `scripts/analyze_images.py` | complete | pass | Wrapper adds deterministic report and cache write |
| `seo-sitemap` | `scripts/analyze_sitemap.py` | complete | pass | Wrapper adds deterministic report and root cache write |
| `seo-geo` | `scripts/analyze_geo.py` | complete | pass | Wrapper adds deterministic report and cache write |
| `seo-dataforseo` | DataForSEO MCP + `scripts/dataforseo_costs.py` | complete | pass | Returns `mcp_configured` when Codex settings include sanitized DataForSEO credentials; otherwise structured setup guidance |
| `seo-drift` | `scripts/drift_history.py` | complete | pass | Returns baseline history or `no_baseline` with deterministic next steps |
| `seo-ecommerce` | instruction-led with optional DataForSEO Merchant data | complete | pass | Static product-page workflow is ready; marketplace intelligence depends on optional provider data |
| `seo-firecrawl` | Firecrawl MCP | complete | pass | Returns `mcp_configured` when Firecrawl is configured; otherwise structured `setup_required` fallback |
| `seo-flow` | FLOW prompt/reference system | complete | pass | Instruction-ready wrapper records FLOW request context for Codex execution |
| `seo-google` | `scripts/google_auth.py` plus Google API helpers | complete | pass | Detects Google credential tier and returns setup guidance when credentials are absent |
| `seo-performance` | `scripts/analyze_performance.py` | complete | pass | Wrapper adds report, summary, cache, and Lighthouse payload artifact |
| `seo-visual` | `scripts/analyze_visual.py` + `scripts/capture_screenshot.py` | complete | pass | Degrades gracefully if Playwright is unavailable |
| `seo-image-gen` | nanobanana MCP + Gemini image generation helpers | complete | pass | Returns `mcp_configured` when Codex settings include sanitized Gemini key; actual generation requires MCP runtime loaded |
| `seo-local` | instruction-led with optional GBP/maps/citation providers | complete | pass | Wrapper records local SEO request context and optional integration needs |
| `seo-maps` | DataForSEO MCP + optional maps providers | complete | pass | Limited free-tier workflow is available; DataForSEO config enables richer maps intelligence |
| `seo-plan` | `scripts/generate_seo_plan.py` | complete | pass | Native script already writes strategy artifacts and cache |
| `seo-programmatic` | `scripts/analyze_programmatic.py` | complete | pass | Wrapper adds deterministic report and cache write |
| `seo-competitor-pages` | `scripts/generate_competitor_pages.py` | complete | pass | Wrapper adds report, schema artifact, and cache write |
| `seo-hreflang` | `scripts/analyze_hreflang.py` | complete | pass | Wrapper adds deterministic report and root cache write |
| `seo-sxo` | instruction-led with optional SERP intent review | complete | pass | Wrapper records SXO request context for specialist execution |

## Current Caveats

- Many native analyzers still primarily emit JSON to stdout; the wrapper is what standardizes reports, cache writes, and environment verification.
- `seo` remains an orchestration/router skill, so API consumers should call either `seo-audit` or an explicit specialist workflow instead of expecting a dedicated `seo` execution script.
- Premium PDF generation depends on Playwright Chromium being available.
- Performance data uses PageSpeed data when available and deterministic heuristics otherwise; the data source is labeled in artifacts.
