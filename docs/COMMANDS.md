# Command Reference

Codex SEO works best from natural-language prompts, but command-style prompts are supported.

## Common Workflows

| Prompt | Purpose |
|---|---|
| `/seo audit <url>` | Full SEO audit with specialist routing |
| `/seo page <url>` | Deep single-page analysis |
| `/seo technical <url>` | Crawlability, indexability, CWV, JavaScript, security |
| `/seo content <url>` | E-E-A-T, helpfulness, readability, AI citation readiness |
| `/seo schema <url>` | Structured data detection, validation, generation |
| `/seo images <url>` | Alt text, image weight, metadata, SERP image opportunities |
| `/seo sitemap <url>` | XML sitemap discovery, coverage, generation guidance |
| `/seo geo <url>` | AI search/GEO readiness, crawler access, citability |
| `/seo performance <url>` | Core Web Vitals and Lighthouse-oriented performance |
| `/seo visual <url>` | Screenshot, mobile, above-the-fold, CTA visibility |
| `/seo plan <business-type>` | Strategic SEO roadmap |
| `/seo programmatic <url>` | Programmatic SEO risk and scale planning |
| `/seo competitor-pages <url>` | Comparison/alternative page opportunities |
| `/seo hreflang <url>` | International SEO and content parity |
| `/seo local <url>` | Local SEO, NAP, GBP signals, citations, reviews |
| `/seo maps <command>` | Maps/geo-grid intelligence when integrations exist |
| `/seo google setup` | Google API credential setup guidance |
| `/seo backlinks <url>` | Backlink profile summary and data-source detection |
| `/seo cluster <keyword>` | SERP-based topic clustering |
| `/seo sxo <url>` | Search Experience Optimization |
| `/seo drift baseline <url>` | Capture SEO baseline |
| `/seo drift compare <url>` | Compare against baseline |
| `/seo ecommerce <url>` | Product/e-commerce SEO |
| `/seo flow <stage>` | FLOW framework prompt workflow |
| `/seo dataforseo <command>` | Live DataForSEO data when MCP is configured |
| `/seo firecrawl <command>` | Site crawling when Firecrawl MCP is configured |
| `/seo image-gen <use-case>` | SEO image asset generation when MCP is configured |

## Headless Examples

```bash
python scripts/run_skill_workflow.py --skill seo-technical https://example.com --json
python scripts/run_skill_workflow.py --skill seo-google https://example.com --json
python scripts/run_api_smoke_suite.py https://example.com --skill seo-drift --json
```

Wrappers write artifacts to `output/` and cache summaries to `.seo-cache/`.
