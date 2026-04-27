# Codex SEO

Codex SEO is a Codex-first port of [`AgriciDaniel/claude-seo`](https://github.com/AgriciDaniel/claude-seo), synchronized to upstream `main` at `a9cf338` and packaged for Codex skills, Codex agents, and deterministic headless/API execution.

It includes 1 orchestrator skill, 26 specialist workflows, 24 Codex TOML agent profiles, shared `.seo-cache/` artifacts, optional Google/DataForSEO/Firecrawl/image-generation integrations, and Python wrappers for repeatable reports.

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/AgriciDaniel/codex-seo/main/install.sh | bash
```

Windows:

```powershell
irm https://raw.githubusercontent.com/AgriciDaniel/codex-seo/main/install.ps1 | iex
```

Installer overrides:

- `CODEX_SEO_REPO` - fork or local Git path
- `CODEX_SEO_REF` - branch, tag, or commit-ish
- `CODEX_HOME` - alternate Codex home, defaults to `~/.codex`
- `CODEX_SEO_SKIP_PLAYWRIGHT_BROWSER=1` - skip Chromium install
- `CODEX_SEO_PLAYWRIGHT_WITH_DEPS=1` - ask Playwright to install system deps

## Usage

Ask Codex naturally:

- "Audit https://example.com for SEO."
- "Check schema and Core Web Vitals for this URL."
- "Build a local SEO plan for this business."
- "Run a backlink profile summary."

Command-style prompts also work, for example `/seo audit <url>`, `/seo technical <url>`, `/seo google setup`, or `/seo drift history <url>`.

## Skill Surface

Core workflows: audit, page, technical, content, schema, images, sitemap, GEO, performance, visual, plan, programmatic, competitor pages, hreflang, local, maps, Google APIs, backlinks, cluster, SXO, drift, ecommerce, FLOW, DataForSEO, image generation, and Firecrawl.

Codex packaging:

- `skills/seo/SKILL.md` is the canonical orchestrator.
- `skills/seo-*` directories contain specialist workflows.
- `agents/seo-*.toml` contains Codex agent profiles.
- `.codex-plugin/plugin.json` enables plugin-style discovery.
- `scripts/run_skill_workflow.py` and `scripts/run_api_smoke_suite.py` provide deterministic headless execution.

## Verification

```bash
python -m pytest tests/
python scripts/verify_environment.py --json
python scripts/demo_readiness.py --target https://example.com --live-apis --workflows --json
python scripts/run_skill_workflow.py --skill seo-technical https://example.com --json
```

Generated runtime artifacts go to `output/` and `.seo-cache/`; both are ignored by git.

For live demo preparation, see `docs/DEMO-RUNBOOK.md`.

## Credentials

Codex SEO stores new credentials under `~/.config/codex-seo/` and runtime caches under `~/.cache/codex-seo/`. Scripts can read old `~/.config/claude-seo/` and `~/.cache/claude-seo/` files as migration fallbacks, but new writes use Codex paths.

## Attribution

Original project and concept by [AgriciDaniel](https://github.com/AgriciDaniel) in `claude-seo`. This Codex port preserves upstream SEO capabilities and adapts the runtime for Codex skills, TOML agents, cache sharing, and API-safe wrappers.
