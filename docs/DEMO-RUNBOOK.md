# Codex SEO Demo Runbook

Use this runbook for a live Codex SEO demo with DataForSEO and Gemini image tooling enabled.

## Pre-Demo Readiness

Run this from the repo root:

```bash
python scripts/demo_readiness.py --target https://example.com --live-apis --workflows --json
```

For one real, low-depth DataForSEO SERP proof, add:

```bash
python scripts/demo_readiness.py --target https://example.com --live-apis --live-serp --serp-keyword "seo tools" --json
```

`--live-serp` uses `serp_organic_live_advanced` with depth 10 and logs the actual cost through `scripts/dataforseo_costs.py`.

## Required Live Wiring

- Codex MCP settings: `~/.codex/settings.json`
- Required MCP servers: `dataforseo`, `nanobanana-mcp`
- Required local file: `~/.codex/skills/seo/dataforseo-field-config.json`
- Required npm packages: `dataforseo-mcp-server`, `@ycse/nanobanana-mcp@latest`
- Generated image output: `~/Documents/nanobanana_generated/`

Restart Codex after changing MCP settings so a demo session loads the configured servers.

## Demo Flow

1. Show the Codex-first plugin/skill surface:

   ```bash
   python scripts/demo_readiness.py --target https://example.com --json
   ```

2. Show deterministic workflow reliability:

   ```bash
   python scripts/run_api_smoke_suite.py https://example.com --json
   ```

3. Show a premium audit artifact:

   ```bash
   python scripts/run_skill_workflow.py --skill seo-audit https://example.com --json
   ```

4. Show provider-aware extension readiness:

   ```bash
   python scripts/run_skill_workflow.py --skill seo-dataforseo https://example.com --json
   python scripts/run_skill_workflow.py --skill seo-image-gen https://example.com --json
   python scripts/run_skill_workflow.py --skill seo-maps https://example.com --json
   ```

5. In a restarted Codex session, demonstrate natural-language routing:

   ```text
   Run a full SEO audit for https://example.com and generate the premium report.
   ```

   ```text
   Use DataForSEO to check the live Google SERP for "seo tools" in the US.
   ```

   ```text
   Generate an SEO image plan for an OG image for a Codex SEO launch page.
   ```

## Demo Safety

- Do not show raw `~/.codex/settings.json` on screen.
- Use `scripts/demo_readiness.py` for sanitized checks.
- Keep DataForSEO cost mode on `threshold` during demos.
- Use `python scripts/dataforseo_costs.py today` before and after live provider calls.
- Rotate temporary provider keys after the demo window.
