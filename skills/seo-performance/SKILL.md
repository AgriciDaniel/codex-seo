---
name: seo-performance
description: Performance specialist for full audits. Measures CWV (LCP/INP/CLS), Lighthouse score signals, and emits deterministic report artifacts.
---

# Performance Specialist

Use this for the performance sub-track in full audits.

## Shared Data Cache

**Step 0 -- Check shared data cache:**

Before gathering, check `.seo-cache/` for cached data from other skills.
Reference: `../seo/references/shared-data-cache.md` for schemas and dependency map.

This specialist does not require upstream cache inputs before running fresh performance checks.

- If found: no prerequisite cache is needed; continue with current measurements
- If missing: proceed normally and gather fresh performance data
- If the user says "refresh" or "re-run": ignore cache entirely

## Inputs
- URL
- Timeout
- Optional PageSpeed API key (`PAGESPEED_API_KEY`)

## Execution Path

Prefer running `scripts/analyze_performance.py` for deterministic performance analysis in API/headless environments. The script uses PageSpeed data when available and otherwise falls back to labeled heuristics so the pipeline still completes without a human in the loop.

## Outputs
- `PERFORMANCE-AUDIT-REPORT.md`
- `SUMMARY.json`

## Core checks
- Prefer real-user CWV data from PageSpeed Insights / CrUX when available
- If real-user data is unavailable, fall back to Lighthouse lab data and label it clearly as lab data
- Lighthouse performance score (mobile + desktop if available)
- LCP and CLS measurements
- INP only when the data source actually provides it; do not fabricate or infer INP from TBT
- TBT may be reported as a lab proxy when INP is unavailable
- Fallback guidance when API data is unavailable, quota-blocked, or unauthenticated

## Priority Rules
- **High**: Performance score < 70 or LCP > 2500ms or INP > 200ms or CLS > 0.1
- **Medium**: Performance score 70-79
- **Low**: Data-source limitations

## Write to shared data cache

After completing all work, write results to `.seo-cache/`.

```bash
mkdir -p .seo-cache/pages/{url-slug}
```

Write `.seo-cache/pages/{url-slug}/performance.json` using the schema in `../seo/references/shared-data-cache.md`.
At minimum, match the documented cache keys: `core_web_vitals` and `issues`. Add extra helpful fields only if they do not replace or rename the documented keys.

Add `.seo-cache/` to `.gitignore` if not already present:
```bash
grep -qxF '.seo-cache/' .gitignore 2>/dev/null || echo '.seo-cache/' >> .gitignore
```

### Premium Deliverable
If the user requests a 'client report' or 'premium deliverable', automatically read `../seo-audit/assets/report-template.html` and `../seo/references/premium-report-standard.md`. Use that report standard as the default brief. Generate the HTML as an internal intermediate artifact, then produce the PDF as the public deliverable. Mention only the PDF in your final response unless the user explicitly asks for the HTML file.
