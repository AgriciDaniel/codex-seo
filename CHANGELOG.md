# Changelog

## [1.9.6+codex.5] - 2026-04-28

### Fixed

- Hardened installer bootstrap JSON transport on macOS, Linux, and PowerShell by writing the bootstrap payload to a dedicated JSON file instead of scraping mixed stdout/stderr.
- Added structured JSON error output when bootstrap fails before environment verification, so platform failures produce actionable diagnostics instead of raw tracebacks.
- Added PowerShell fallback parsing through Python for large or deeply nested bootstrap payloads.
- Truncated captured subprocess logs inside bootstrap JSON to keep installer parsing stable.
- Updated public install refs to `v1.9.6-codex.5` so users receive the macOS Python 3.14 bootstrap fix from `main`.

## [1.9.6+codex.1] - 2026-04-27

### Added

- Synced Codex SEO to `AgriciDaniel/claude-seo` `main` at `a9cf338`.
- Added Codex plugin manifest at `.codex-plugin/plugin.json`.
- Expanded to 26 specialist workflows and 24 Codex TOML agent profiles.
- Added upstream backlink, cluster, local, maps, Google APIs, SXO, drift, ecommerce, FLOW, DataForSEO, image-gen, and Firecrawl workflows.
- Added upstream API/helper scripts for Google, backlinks, drift, DataForSEO, FLOW sync, reports, and verification.
- Added contract tests for plugin metadata, skill cache guidance, installer coverage, TOML agents, and FLOW sync safety.

### Changed

- Canonical skill tree is now `skills/`; `skills/seo/SKILL.md` is the main orchestrator.
- Installers default to `https://github.com/AgriciDaniel/codex-seo`.
- New credentials and runtime caches use `~/.config/codex-seo/` and `~/.cache/codex-seo/`.
- Legacy `~/.config/claude-seo/` and `~/.cache/claude-seo/` files are read only as migration fallback.
- Community footer is config-gated and disabled by default for Codex/API/client deliverables.

### Fixed

- Fixed cross-platform virtualenv Python resolution in `bootstrap_environment.py`.
- Fixed `run_headless_audit.py` `data_only` scoping for wrapper-driven audits.
- Hardened URL validation for private, loopback, reserved, multicast, unspecified, and metadata hosts.

### Verified

- `python -m pytest tests/`
- script compile/help checks for all Python scripts
- `bash -n install.sh uninstall.sh`
- PowerShell parse check for `install.ps1` and `uninstall.ps1`
- deterministic smoke runs for core, audit/page, and setup-required workflows
