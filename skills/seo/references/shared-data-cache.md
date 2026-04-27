# Shared Data Cache Reference

This reference defines the shared `.seo-cache/` system used across codex-seo skills.
All cache files are optional performance optimizations. If a cache is missing,
stale, corrupt, or unreadable, the skill proceeds with normal gathering.

## Core Rules

- Cache location: `.seo-cache/`
- Reference this file from each skill Step 0 block
- No cache file is required for a skill to run
- Corrupt JSON should be treated as missing cache
- Permission errors should be skipped silently
- Users can force fresh gathering by saying `refresh` or `re-run`
- Cache freshness does not auto-expire; each file should include an analysis timestamp
- Never commit `.seo-cache/` contents

## Directory Layout

```text
.seo-cache/
  site-meta.json
  plan.json
  audit-scores.json
  sitemap.json
  hreflang.json
  programmatic.json
  competitors.json
  backlinks.json
  google.json
  local.json
  maps.json
  cluster.json
  sxo.json
  drift.json
  ecommerce.json
  flow.json
  dataforseo.json
  firecrawl.json
  pages/
    {url-slug}/
      technical.json
      content.json
      schema.json
      geo.json
      performance.json
      visual.json
      images.json
      page-analysis.json
```

## URL Slug Resolution Algorithm

Use this algorithm for all page-level cache paths:

1. Parse the URL and extract the path component
2. Strip protocol, domain, query string, fragment, and trailing slash
3. If the path is empty or `/`, use `homepage`
4. Replace `/` with `--`
5. Strip leading and trailing hyphens
6. Lowercase the result
7. Truncate to 80 characters; if possible, break at the last `--` before the limit

Examples:

- `https://example.com` → `homepage`
- `https://example.com/blog/seo-guide` → `blog--seo-guide`
- `https://example.com/about/team` → `about--team`

## Freshness Rules

- No automatic expiry window
- Cache represents the state at analysis time
- Each cache file should include `analyzed_at`
- If the user asks to refresh or re-run, ignore cache reads and overwrite on write
- If downstream cache context conflicts with live findings, prefer fresh evidence and note the mismatch

## Step 0 Template

Use this at the beginning of each skill process or gather section:

```md
**Step 0 — Check shared data cache:**

Before gathering, check `.seo-cache/` for cached data from other skills.
Reference: `seo/references/shared-data-cache.md` for schemas and dependency map.

[List specific cache files this skill checks]

- If found: parse and use the data (note "Using cached [X] from [date]")
- If missing: proceed without it (note "No cached [X] found, gathering fresh")
- If the user says "refresh" or "re-run": ignore cache entirely
```

## Cache Write Template

Use this at the end of each skill delivery section:

```md
**Write to shared data cache:**

After completing all work, write results to `.seo-cache/`.

```bash
mkdir -p .seo-cache/pages/{url-slug}
mkdir -p .seo-cache
```

Write the JSON file per the schema in `seo/references/shared-data-cache.md`.
Add `.seo-cache/` to `.gitignore` if not already present:

```bash
grep -qxF '.seo-cache/' .gitignore 2>/dev/null || echo '.seo-cache/' >> .gitignore
```
```

## Error Handling Rules

- Missing cache file: continue normally
- Invalid JSON: treat as missing cache
- Permission denied: skip cache silently
- Partial cache payloads: use only clearly valid fields
- Unknown fields: ignore unless the active skill explicitly needs them

## Dependency Map

| Skill | Reads | Writes |
|---|---|---|
| `seo-audit` | `site-meta.json`, `audit-scores.json`, page specialist caches during Phase 2 | `site-meta.json`, `audit-scores.json` |
| `seo-technical` | `site-meta.json` | `pages/{slug}/technical.json` |
| `seo-content` | `site-meta.json`, `pages/{slug}/geo.json` | `pages/{slug}/content.json` |
| `seo-schema` | `site-meta.json` | `pages/{slug}/schema.json` |
| `seo-geo` | `site-meta.json`, `pages/{slug}/technical.json` | `pages/{slug}/geo.json` |
| `seo-performance` | `site-meta.json` | `pages/{slug}/performance.json` |
| `seo-visual` | `site-meta.json` | `pages/{slug}/visual.json` |
| `seo-images` | `site-meta.json` | `pages/{slug}/images.json` |
| `seo-page` | `site-meta.json`, `pages/{slug}/schema.json`, `pages/{slug}/content.json` | `pages/{slug}/page-analysis.json` |
| `seo-plan` | `site-meta.json`, `audit-scores.json` | `plan.json` |
| `seo-sitemap` | `site-meta.json`, `plan.json` | `sitemap.json` |
| `seo-programmatic` | `site-meta.json`, `sitemap.json` | `programmatic.json` |
| `seo-competitor-pages` | `site-meta.json`, `plan.json` | `competitors.json` |
| `seo-hreflang` | `site-meta.json` | `hreflang.json` |
| `seo-backlinks` | `site-meta.json`, `competitors.json` | `backlinks.json` |
| `seo-google` | `site-meta.json`, `sitemap.json` | `google.json`, page performance/index data when URL-specific |
| `seo-local` | `site-meta.json`, `pages/{slug}/geo.json` | `local.json` |
| `seo-maps` | `site-meta.json`, `local.json` | `maps.json` |
| `seo-cluster` | `site-meta.json`, `plan.json`, `content.json` | `cluster.json` |
| `seo-sxo` | `site-meta.json`, `pages/{slug}/content.json` | `sxo.json` |
| `seo-drift` | `site-meta.json`, prior `drift.json` | `drift.json` |
| `seo-ecommerce` | `site-meta.json`, `schema.json`, `images.json` | `ecommerce.json` |
| `seo-flow` | `site-meta.json`, latest specialist caches | `flow.json` |
| `seo-dataforseo` | `site-meta.json`, active specialist cache | `dataforseo.json` |
| `seo-firecrawl` | `site-meta.json`, `sitemap.json` | `firecrawl.json` |
| `seo-image-gen` | `site-meta.json`, `images.json`, `content.json` | `image-gen.json` |
| `seo` | `site-meta.json`, `audit-scores.json` | none |

## JSON Schemas

Each schema below is intentionally lightweight and additive. Skills may include extra
fields when useful, but should preserve the documented top-level structure.

### 1. `site-meta.json`

```json
{
  "cache_type": "site-meta",
  "analyzed_at": "2026-01-15T12:34:56Z",
  "domain": "example.com",
  "homepage_url": "https://example.com/",
  "business_type": "local service business",
  "industry": "home services",
  "language": "en",
  "country": "US",
  "notes": []
}
```

### 2. `audit-scores.json`

```json
{
  "cache_type": "audit-scores",
  "analyzed_at": "2026-01-15T12:34:56Z",
  "domain": "example.com",
  "overall_score": 78,
  "category_scores": {
    "technical": 74,
    "content": 80,
    "schema": 71,
    "sitemap": 83,
    "geo": 79
  },
  "priority_issues": [
    {
      "severity": "high",
      "issue": "Missing Organization schema on homepage"
    }
  ]
}
```

### 3. `plan.json`

```json
{
  "cache_type": "plan",
  "analyzed_at": "2026-01-15T12:34:56Z",
  "domain": "example.com",
  "goals": ["Increase qualified organic traffic"],
  "priority_tracks": ["technical cleanup", "location pages"],
  "target_pages": ["/services/roof-repair"],
  "competitors": ["competitor-a.com", "competitor-b.com"]
}
```

### 4. `sitemap.json`

```json
{
  "cache_type": "sitemap",
  "analyzed_at": "2026-01-15T12:34:56Z",
  "domain": "example.com",
  "sitemap_urls": ["https://example.com/sitemap.xml"],
  "coverage_summary": {
    "indexed_candidates": 120,
    "missing_key_pages": 3
  },
  "recommendations": ["Add location pages to sitemap"]
}
```

### 5. `hreflang.json`

```json
{
  "cache_type": "hreflang",
  "analyzed_at": "2026-01-15T12:34:56Z",
  "domain": "example.com",
  "language_targets": ["en-us", "es-us"],
  "implementation_status": "missing",
  "issues": ["No hreflang annotations detected"]
}
```

### 6. `programmatic.json`

```json
{
  "cache_type": "programmatic",
  "analyzed_at": "2026-01-15T12:34:56Z",
  "domain": "example.com",
  "templates": ["city-service landing page"],
  "data_sources": ["internal inventory"],
  "risks": ["thin near-duplicate location pages"]
}
```

### 7. `competitors.json`

```json
{
  "cache_type": "competitors",
  "analyzed_at": "2026-01-15T12:34:56Z",
  "domain": "example.com",
  "competitors": [
    {
      "domain": "competitor-a.com",
      "reason": "Overlaps on core service terms"
    }
  ],
  "content_gaps": ["commercial intent comparison pages"]
}
```

### 8. `pages/{slug}/technical.json`

```json
{
  "cache_type": "technical",
  "analyzed_at": "2026-01-15T12:34:56Z",
  "url": "https://example.com/services/roof-repair",
  "url_slug": "services--roof-repair",
  "score": 76,
  "findings": {
    "indexability": "indexable",
    "canonicals": "self-referential",
    "mobile": "pass",
    "cwv": "needs improvement"
  },
  "issues": ["Render-blocking CSS on mobile"]
}
```

### 9. `pages/{slug}/content.json`

```json
{
  "cache_type": "content",
  "analyzed_at": "2026-01-15T12:34:56Z",
  "url": "https://example.com/services/roof-repair",
  "url_slug": "services--roof-repair",
  "score": 81,
  "eeat_summary": "Strong expertise signals, limited first-hand proof",
  "ai_citation_readiness": "moderate",
  "issues": ["Missing author or reviewer attribution"]
}
```

### 10. `pages/{slug}/schema.json`

```json
{
  "cache_type": "schema",
  "analyzed_at": "2026-01-15T12:34:56Z",
  "url": "https://example.com/services/roof-repair",
  "url_slug": "services--roof-repair",
  "score": 70,
  "detected_types": ["Service", "FAQPage"],
  "validation": "warnings",
  "issues": ["Missing provider details on Service schema"]
}
```

### 11. `pages/{slug}/geo.json`

```json
{
  "cache_type": "geo",
  "analyzed_at": "2026-01-15T12:34:56Z",
  "url": "https://example.com/services/roof-repair",
  "url_slug": "services--roof-repair",
  "score": 73,
  "ai_crawler_access": "allowed",
  "local_signals": ["city mentioned in title tag"],
  "issues": ["No llms.txt detected"]
}
```

### 12. `pages/{slug}/performance.json`

```json
{
  "cache_type": "performance",
  "analyzed_at": "2026-01-15T12:34:56Z",
  "url": "https://example.com/services/roof-repair",
  "url_slug": "services--roof-repair",
  "score": 68,
  "core_web_vitals": {
    "lcp": "3.1s",
    "inp": "240ms",
    "cls": "0.08"
  },
  "issues": ["Large hero image delays LCP"]
}
```

### 13. `pages/{slug}/visual.json`

```json
{
  "cache_type": "visual",
  "analyzed_at": "2026-01-15T12:34:56Z",
  "url": "https://example.com/services/roof-repair",
  "url_slug": "services--roof-repair",
  "score": 75,
  "layout_summary": "Clear hierarchy with weak CTA contrast",
  "issues": ["Primary CTA blends into hero background"]
}
```

### 14. `pages/{slug}/images.json`

```json
{
  "cache_type": "images",
  "analyzed_at": "2026-01-15T12:34:56Z",
  "url": "https://example.com/services/roof-repair",
  "url_slug": "services--roof-repair",
  "score": 72,
  "image_summary": {
    "missing_alt": 4,
    "oversized_images": 2
  },
  "issues": ["Four decorative images missing explicit empty alt text"]
}
```

### 15. `pages/{slug}/page-analysis.json`

```json
{
  "cache_type": "page-analysis",
  "analyzed_at": "2026-01-15T12:34:56Z",
  "url": "https://example.com/services/roof-repair",
  "url_slug": "services--roof-repair",
  "summary_score": 79,
  "inputs_used": ["schema", "content"],
  "top_actions": ["Add reviewer credentials", "Expand FAQ coverage"]
}
```

### 16. Root-level specialist summaries

Use this shared shape for `backlinks.json`, `google.json`, `local.json`,
`maps.json`, `cluster.json`, `sxo.json`, `drift.json`, `ecommerce.json`,
`flow.json`, `dataforseo.json`, `firecrawl.json`, and `image-gen.json`:

```json
{
  "cache_type": "backlinks",
  "analyzed_at": "2026-01-15T12:34:56Z",
  "domain": "example.com",
  "url": "https://example.com/",
  "score": 72,
  "data_sources": ["Common Crawl"],
  "findings": {
    "summary": "Domain-level backlink data available; API credentials missing."
  },
  "issues": ["No Moz or Bing credentials configured"],
  "recommendations": ["Configure backlink API credentials for higher confidence"],
  "limitations": ["Free-tier data is directional, not exhaustive"]
}
```

Set `cache_type` to the skill family (`google`, `local`, `maps`, `cluster`,
`sxo`, `drift`, `ecommerce`, `flow`, `dataforseo`, `firecrawl`, or `image-gen`).
If a workflow is unavailable because an MCP server or credential is missing, still
write a summary when useful with `status: "setup_required"` and clear limitations.
