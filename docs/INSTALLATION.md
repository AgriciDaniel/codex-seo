# Installation

## Unix

```bash
curl -fsSL https://raw.githubusercontent.com/AgriciDaniel/codex-seo/main/install.sh | bash
```

## Windows

```powershell
irm https://raw.githubusercontent.com/AgriciDaniel/codex-seo/main/install.ps1 | iex
```

## What Gets Installed

- `~/.codex/skills/seo`
- `~/.codex/skills/seo-*`
- `~/.codex/agents/seo-*.toml`
- Python runtime at `~/.codex/skills/seo/.venv`

## Overrides

- `CODEX_HOME`: alternate Codex home
- `CODEX_SEO_REPO`: fork or local Git path
- `CODEX_SEO_REF`: branch, tag, or commit; defaults to `v1.9.6-codex.1`
- `CODEX_SEO_SKIP_PLAYWRIGHT_BROWSER=1`: skip Chromium install
- `CODEX_SEO_PLAYWRIGHT_WITH_DEPS=1`: install Playwright system deps where supported

## Verify

```bash
~/.codex/skills/seo/.venv/bin/python ~/.codex/skills/seo/scripts/verify_environment.py
```

Windows:

```powershell
& "$HOME\.codex\skills\seo\.venv\Scripts\python.exe" "$HOME\.codex\skills\seo\scripts\verify_environment.py"
```

## Uninstall

```bash
bash uninstall.sh
```

Windows:

```powershell
powershell -ExecutionPolicy Bypass -File .\uninstall.ps1
```
