# Architecture

Codex SEO is a local Codex skill suite with plugin metadata, specialist skills, TOML agents, deterministic Python runners, and optional MCP/API integrations.

## Layout

- `.codex-plugin/plugin.json` exposes the suite to Codex plugin discovery.
- `skills/seo/SKILL.md` is the canonical orchestrator.
- `skills/seo-*` contains specialist workflows.
- `skills/seo/references/shared-data-cache.md` defines `.seo-cache/` contracts.
- `agents/seo-*.toml` provides Codex agent profiles for parallel audit slices.
- `scripts/` contains deterministic wrappers, fetch/parse helpers, Google/API utilities, drift monitoring, and report generators.
- `extensions/` contains optional setup helpers for DataForSEO, Firecrawl, and image generation.

## Runtime Flow

1. Route natural-language or `/seo ...` prompts to the orchestrator or specialist skill.
2. Check `.seo-cache/` for reusable context.
3. Gather fresh evidence with scripts, Codex tools, or configured MCP/API integrations.
4. Write reports to `output/` and concise machine-readable summaries to `.seo-cache/`.
5. Return setup-required states when credentials or MCP servers are missing instead of fabricating data.

## Config And Cache

- New credentials: `~/.config/codex-seo/`
- New runtime caches: `~/.cache/codex-seo/`
- Legacy read fallback: `~/.config/claude-seo/` and `~/.cache/claude-seo/`
- Project cache: `.seo-cache/` in the active workspace, ignored by git

## Public Interfaces

- Skill discovery: `skills/*/SKILL.md`
- Agent discovery: `agents/*.toml`
- Plugin discovery: `.codex-plugin/plugin.json`
- Headless runner: `python scripts/run_skill_workflow.py --skill <skill> <url> --json`
- Smoke suite: `python scripts/run_api_smoke_suite.py <url> --json`

## Safety

All URL-aware scripts should use the shared public URL validation path or `google_auth.validate_url()`. Private, loopback, reserved, multicast, unspecified, and metadata hosts are blocked.
