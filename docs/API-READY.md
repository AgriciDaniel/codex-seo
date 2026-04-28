# API Readiness

Codex SEO now includes a deterministic headless execution path so API agents do not need to infer intermediate orchestration steps from `SKILL.md`.

## Headless Entry Points

### 1. Environment Verification

```bash
python scripts/verify_environment.py --target https://www.python.org --json
```

What it verifies:
- Python version
- Required core imports from `requirements-core.txt`
- Optional visual, report, Google API, and OCR imports
- Playwright Chromium availability
- Writable `.seo-cache/` and `output/` directories
- Optional target connectivity

`verify_environment.py` is safe to run before dependencies are installed. In a cold runtime it reports missing packages instead of crashing on import.

Readiness fields:
- `ready`: core API/CLI readiness for non-visual workflows
- `capabilities.core_ready`: enough for non-visual API execution
- `capabilities.visual_ready`: screenshots and visual workflows are ready
- `capabilities.premium_report_ready`: HTML/PDF premium deliverables are ready
- `capabilities.full_ready`: full suite readiness, including Playwright-backed features

### 0. Runtime Bootstrap

```bash
python scripts/bootstrap_environment.py --target https://www.python.org --json
```

Use this first in fresh API runtimes such as Paperclip. It creates or updates a virtualenv, installs `requirements-core.txt`, then installs optional visual, report, Google API, and OCR requirement groups best-effort. It attempts `playwright install chromium` when the Playwright package is available, then runs `verify_environment.py` inside that venv so the bootstrap result reflects actual runtime readiness. `ok: true` means the core non-visual workflows are runnable. Use `full_ready` when you specifically need screenshots or premium PDF deliverables.

### 2. Full Audit Pipeline

```bash
python scripts/run_headless_audit.py https://www.python.org --premium-report auto --json
python scripts/run_headless_audit.py https://www.python.org --output-root output/custom-audits --json
```

What it does:
1. Verifies the environment
2. Fetches the homepage
3. Detects business type and writes `.seo-cache/site-meta.json`
4. Runs deterministic specialist analyzers:
   - `scripts/analyze_technical.py`
   - `scripts/analyze_content.py`
   - `scripts/analyze_schema.py`
   - `scripts/analyze_images.py`
   - `scripts/analyze_performance.py`
   - `scripts/analyze_geo.py`
   - `scripts/analyze_sitemap.py`
   - `scripts/analyze_visual.py` when Playwright is available
5. Writes cache outputs and report artifacts
6. Generates premium HTML/PDF deliverables when Playwright is available and `--premium-report` permits it

### 3. Standard Skill Wrapper

```bash
python scripts/run_skill_workflow.py --skill seo-page https://www.python.org --json
python scripts/run_skill_workflow.py --skill seo-hreflang https://www.python.org --json
python scripts/run_skill_workflow.py --skill seo-audit https://www.python.org --output-root output/custom-audits --json
```

This wrapper gives API agents a single deterministic command shape across the skill suite and handles:
- environment verification artifact creation
- standard report file generation
- cache writes aligned to `.seo-cache/`
- stable output directories under `output/`
- optional `--output-root` overrides with consistent absolute artifact paths

### 4. Full API Smoke Suite

```bash
python scripts/run_api_smoke_suite.py https://www.python.org --json
```

This simulates API usage by invoking each skill non-interactively through the wrapper and collecting pass/fail plus artifact data.

### 5. Provider Probe

```bash
python scripts/test_openai_responses_provider.py \
  --base-url https://api.example.com/v1/responses \
  --api-key-env OPENAI_API_KEY \
  --model gpt-5.1-codex \
  --json
```

Use this for live OpenAI-compatible provider testing. It checks:
- plain text response completion
- function-call emission for the standard wrapper command shape
- end-to-end tool-loop continuation with a local shell execution result

## Output Contract

The headless runner writes an audit directory under `output/`:

```text
output/<domain-slug>-audit-<timestamp>/
  ACTION-PLAN.md
  FULL-AUDIT-REPORT.md
  SUMMARY.json
  environment-verification.json
  homepage-parse.json
  crawl-all.json
  lighthouse.json
  visual-analysis.json
  screenshot-results.json
  screenshots/                    # When Playwright is available
  _internal/<pdf-base>.html       # When premium report generation succeeds
  <pdf-base>.pdf                  # When premium report generation succeeds
```

Related cache outputs:

```text
.seo-cache/
  site-meta.json
  audit-scores.json
  pages/homepage/
    technical.json
    content.json
    schema.json
    images.json
    performance.json
    geo.json
    visual.json
    page-analysis.json
```

## Failure Modes

- If Playwright or Chromium is unavailable, `ready` can still be true for core API workflows, but `capabilities.full_ready` stays false and visual analysis / PDF generation are reported as limited.
- If PageSpeed API data is unavailable, performance falls back to deterministic heuristics and labels that data source explicitly.
- If a cache file is missing or corrupt, the runner gathers fresh data instead of failing.
- If a provider probe passes text completion and function-call emission but fails the tool-loop continuation, treat that as a provider compatibility issue. In that case, drive Codex SEO through deterministic wrapper commands such as `scripts/run_skill_workflow.py` and `scripts/run_headless_audit.py` instead of relying on native provider function-calling until the provider is fixed.
