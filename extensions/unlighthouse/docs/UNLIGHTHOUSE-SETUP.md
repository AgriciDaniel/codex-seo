# Unlighthouse extension setup

[Unlighthouse](https://unlighthouse.dev) is an MIT-licensed multi-page
Lighthouse runner that produces a single aggregate report. No API
quota, no credentials, no network egress beyond crawling the target.

## Install

```bash
./extensions/unlighthouse/install.sh
.\extensions\unlighthouse\install.ps1
```

The installer:

1. Verifies Python 3 + Node 18+.
2. Pre-warms `unlighthouse@0.13.5` via `npx --yes`.
3. Copies the `seo-unlighthouse` skill into `~/.claude/skills/`.

No API keys, no settings.json mutation.

## Verify

```
/seo unlighthouse https://example.com --max-routes 5
```

## When to use Unlighthouse vs. PageSpeed Insights

| Use Unlighthouse | Use PSI |
|---|---|
| Site has 100s of pages and you want every one audited | Single-URL focused audit |
| Offline / restricted environment | Field data from real Chrome users (CrUX) |
| CI-driven regression check post-deploy | Quick CLI/web-form check |
| Free / no quota concern | PSI quota OK for small sites |

PSI uses CrUX field data when available (real users); Unlighthouse
runs Lighthouse lab tests locally. For trustworthy CWV measurement
on production traffic, prefer PSI / CrUX.

## Uninstall

```bash
./extensions/unlighthouse/uninstall.sh
```
