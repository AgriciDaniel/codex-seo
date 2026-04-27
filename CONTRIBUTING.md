# Contributing to Codex SEO

Thanks for contributing.

## Ground Rules

- Keep changes focused and minimal.
- Preserve project lineage and attribution to the upstream project.
- Do not remove legal/disclosure language without maintainer approval.
- Use clear commit messages.

## Local Setup

```bash
git clone https://github.com/AgriciDaniel/codex-seo.git
cd codex-seo
pip install -r requirements.txt
```

## Validation Before PR

Run the same baseline checks used by CI:

```bash
bash -n install.sh
bash -n uninstall.sh
bash -n hooks/pre-commit-seo-check.sh
python -m pytest tests/
```

## Pull Request Checklist

- Explain the problem and the fix.
- Note any behavior changes.
- Update docs when commands or workflows change.
- Avoid unrelated refactors.

## Code Style

- Python: follow PEP 8 conventions. If you have [Ruff](https://docs.astral.sh/ruff/) installed, run `ruff check .` before submitting.
- Shell scripts: use `shellcheck` where possible.
- Keep formatting consistent with surrounding code.

## Security Fixes

For vulnerabilities, follow `SECURITY.md` instead of opening a detailed public issue.
