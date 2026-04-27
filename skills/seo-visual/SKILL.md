---
name: seo-visual
description: Visual specialist for full audits. Captures screenshots, evaluates above-the-fold signals, and checks mobile rendering basics.
---

# Visual Specialist

Use this for the visual sub-track in full audits.

## Shared Data Cache

**Step 0 -- Check shared data cache:**

Before gathering, check `.seo-cache/` for cached data from other skills.
Reference: `../seo/references/shared-data-cache.md` for schemas and dependency map.

This specialist does not require upstream cache inputs before running fresh visual checks.

- If found: no prerequisite cache is needed; continue with current visual capture workflow
- If missing: proceed normally and gather fresh visual data
- If JSON is corrupt or unreadable: treat it as missing and continue normally
- If the user says "refresh" or "re-run": ignore cache entirely

## Inputs
- URL
- Timeout
- Visual mode (`on|off|auto`)

## Outputs
- `VISUAL-AUDIT-REPORT.md`
- `SUMMARY.json`
- `screenshots/` (if Playwright available)

## Checks
- H1 and CTA visibility above the fold
- Mobile viewport + horizontal scroll
- Touch target sizing and minimum font size
- Multi-viewport screenshots

## Write to shared data cache

After completing all work, write results to `.seo-cache/`.

```bash
mkdir -p .seo-cache/pages/{url-slug}
```

Write `.seo-cache/pages/{url-slug}/visual.json` using the schema in `../seo/references/shared-data-cache.md`.
Preserve the documented top-level keys: `cache_type`, `analyzed_at`, `url`, `url_slug`, `score`, `layout_summary`, and `issues`.
Add extra visual detail only as supplemental fields, such as `above_fold`, `mobile`, `screenshots`, or `notes`.

Add `.seo-cache/` to `.gitignore` if not already present:
```bash
grep -qxF '.seo-cache/' .gitignore 2>/dev/null || echo '.seo-cache/' >> .gitignore
```

### Premium Deliverable
If the user requests a 'client report' or 'premium deliverable', automatically read `../seo-audit/assets/report-template.html` and `../seo/references/premium-report-standard.md`. Use that report standard as the default brief. Generate the HTML as an internal intermediate artifact, then produce the PDF as the public deliverable. Mention only the PDF in your final response unless the user explicitly asks for the HTML file.
