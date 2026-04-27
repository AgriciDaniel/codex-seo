# Troubleshooting

## Skill Not Loading

Verify the canonical skill exists:

```bash
ls ~/.codex/skills/seo/SKILL.md
ls ~/.codex/agents/seo-technical.toml
```

Restart Codex after reinstalling.

## Runtime Not Ready

```bash
~/.codex/skills/seo/.venv/bin/python ~/.codex/skills/seo/scripts/verify_environment.py
```

If Playwright Chromium fails, core workflows can still run. Visual and PDF workflows remain limited until browser installation succeeds.

## Credentials Missing

Use Codex paths for new setup:

- Google: `~/.config/codex-seo/google-api.json`
- Backlinks: `~/.config/codex-seo/backlinks-api.json`
- DataForSEO budgets: `~/.config/codex-seo/dataforseo-costs.json`

Legacy `~/.config/claude-seo/` files are read as fallback only.

## Headless Workflow Fails

Run a narrow workflow first:

```bash
python scripts/run_skill_workflow.py --skill seo-technical https://example.com --json
```

For optional MCP/API workflows, `setup_required` is a valid result when credentials or MCP servers are absent.

## Reinstall

```bash
CODEX_SEO_REPO=https://github.com/AgriciDaniel/codex-seo CODEX_SEO_REF=main bash install.sh
```
