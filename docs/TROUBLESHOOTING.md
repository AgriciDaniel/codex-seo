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

On Python 3.14 macOS, some optional packages can lag wheel support. The installer should still complete when `requirements-core.txt` installs and `core_ready` is true; use the verifier notes to identify any optional visual, Google API, report, or OCR capability that needs a different Python/runtime.

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
CODEX_SEO_REPO=https://github.com/AgriciDaniel/codex-seo CODEX_SEO_REF=v1.9.6-codex.4 bash install.sh
```
