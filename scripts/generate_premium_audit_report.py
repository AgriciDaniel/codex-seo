#!/usr/bin/env python3
"""
Generate a premium SEO audit report from an audit output directory.

Usage:
    python scripts/generate_premium_audit_report.py output/example-com-audit-20260321-112541

This script creates a consistent premium deliverable with:
- title page
- table of contents
- inline charts
- inline screenshots
- print-safe HTML
- PDF with page numbers
"""

from __future__ import annotations

import argparse
import base64
from html import escape
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

try:
    from markdown import markdown
except ImportError as exc:
    markdown = None
    MARKDOWN_IMPORT_ERROR = exc
else:
    MARKDOWN_IMPORT_ERROR = None

try:
    from playwright.sync_api import sync_playwright
except ImportError as exc:
    sync_playwright = None
    PLAYWRIGHT_IMPORT_ERROR = exc
else:
    PLAYWRIGHT_IMPORT_ERROR = None


REPO_ROOT = Path(__file__).resolve().parent.parent
PREMIUM_STANDARD = REPO_ROOT / "seo" / "references" / "premium-report-standard.md"


@dataclass
class Section:
    title: str
    anchor: str
    markdown_body: str


def slugify(value: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return value or "section"


def load_json_if_present(path: Path) -> dict | None:
    """Load JSON when present and valid."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def title_case_label(value: str | None, fallback: str) -> str:
    """Render a short human-facing label."""
    if not value:
        return fallback
    return value.replace("_", " ").replace("-", " ").strip().title() or fallback


def extract_audit_date_slug(audit_dir: Path, report_md: str) -> str:
    dir_match = re.search(r"-(\d{8})-\d{6}$", audit_dir.name)
    if dir_match:
        raw = dir_match.group(1)
        return f"{raw[0:4]}-{raw[4:6]}-{raw[6:8]}"

    report_match = re.search(r"Audit date:\*\*\s*([A-Za-z]+\s+\d{1,2},\s+\d{4})", report_md)
    if report_match:
        try:
            parsed = datetime.strptime(report_match.group(1), "%B %d, %Y")
            return parsed.strftime("%Y-%m-%d")
        except ValueError:
            pass

    return datetime.utcnow().strftime("%Y-%m-%d")


def derive_report_filenames(audit_dir: Path, canonical_url: str, report_md: str) -> tuple[str, str]:
    domain = re.sub(r"^https?://", "", canonical_url).rstrip("/")
    domain_slug = slugify(domain.replace(".", " "))
    date_slug = extract_audit_date_slug(audit_dir, report_md)
    base_name = f"codex-seo-audit-{domain_slug}-{date_slug}"
    return f"_internal/{base_name}.html", f"{base_name}.pdf"


def parse_report_sections(report_md: str) -> tuple[str, list[Section]]:
    lines = report_md.splitlines()
    intro_lines: list[str] = []
    sections: list[Section] = []
    current_title: str | None = None
    current_lines: list[str] = []

    for line in lines:
        if line.startswith("## "):
            if current_title is None:
                intro_lines = current_lines[:]
            else:
                sections.append(
                    Section(
                        title=current_title,
                        anchor=slugify(current_title),
                        markdown_body="\n".join(current_lines).strip(),
                    )
                )
            current_title = line[3:].strip()
            current_lines = []
        elif line.startswith("# ") and current_title is None and not intro_lines:
            continue
        else:
            current_lines.append(line)

    if current_title is not None:
        sections.append(
            Section(
                title=current_title,
                anchor=slugify(current_title),
                markdown_body="\n".join(current_lines).strip(),
            )
        )
    else:
        intro_lines = current_lines

    return "\n".join(intro_lines).strip(), sections


def svg_bar_chart(title: str, items: list[tuple[str, float]], max_value: float, color: str) -> str:
    width = 960
    height = 520
    margin_left = 180
    margin_right = 60
    margin_top = 70
    margin_bottom = 70
    plot_width = width - margin_left - margin_right
    plot_height = height - margin_top - margin_bottom
    row_height = plot_height / max(len(items), 1)
    bar_height = row_height * 0.55

    guides = []
    for i in range(0, int(max_value) + 1, 20 if max_value >= 100 else max(1, int(max_value / 5) or 1)):
        x = margin_left + (i / max_value * plot_width if max_value else 0)
        guides.append(
            f"<line x1='{x:.2f}' y1='{margin_top}' x2='{x:.2f}' y2='{height-margin_bottom}' "
            "stroke='rgba(148,163,184,0.18)' stroke-width='1' />"
            f"<text x='{x:.2f}' y='{height-36}' text-anchor='middle' fill='#94a3b8' font-size='12'>{i}</text>"
        )

    bars = []
    for idx, (label, value) in enumerate(items):
        y = margin_top + idx * row_height + (row_height - bar_height) / 2
        bar_width = (value / max_value * plot_width) if max_value else 0
        bars.append(
            f"<text x='{margin_left-16}' y='{y + bar_height/2 + 5:.2f}' text-anchor='end' fill='#e2e8f0' font-size='15'>{label}</text>"
            f"<rect x='{margin_left}' y='{y:.2f}' width='{bar_width:.2f}' height='{bar_height:.2f}' rx='10' fill='{color}' />"
            f"<text x='{margin_left + bar_width + 10:.2f}' y='{y + bar_height/2 + 5:.2f}' fill='#cbd5e1' font-size='14'>{value:g}</text>"
        )

    return f"""
<figure class="chart-figure">
  <figcaption>{title}</figcaption>
  <svg class="chart chart-bar" viewBox="0 0 {width} {height}" preserveAspectRatio="xMidYMid meet" role="img" aria-label="{title}">
    <rect x="0" y="0" width="{width}" height="{height}" fill="#08101d"></rect>
    <text x="{width/2}" y="36" text-anchor="middle" fill="#f8fafc" font-size="24" font-weight="700">{title}</text>
    {''.join(guides)}
    {''.join(bars)}
  </svg>
</figure>
"""


def score_ring(score: int) -> str:
    return f"""
<div class="score-ring" style="background: conic-gradient(var(--accent) {score}%, rgba(15, 23, 42, 0.14) 0);">
  <div class="score-ring-inner">
    <span class="score-number">{score}</span>
    <span class="score-label">SEO Health</span>
  </div>
</div>
"""


def image_data_uri(image_path: Path) -> str:
    suffix = image_path.suffix.lower()
    mime_type = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".svg": "image/svg+xml",
    }.get(suffix, "application/octet-stream")
    encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def screenshot_figure(image_path: Path, caption: str) -> str:
    image_src = image_data_uri(image_path)
    return f"""
<figure class="screenshot-card">
  <img src="{image_src}" alt="{caption}">
  <figcaption>{caption}</figcaption>
</figure>
"""


def render_metric_cards(metrics: list[tuple[str, str]]) -> str:
    cards = []
    for label, value in metrics:
        cards.append(
            f"<div class='metric-card'><span class='metric-value'>{value}</span><span class='metric-label'>{label}</span></div>"
        )
    return "<div class='metric-grid'>" + "".join(cards) + "</div>"


def extract_overall_score(report_md: str) -> int:
    match = re.search(r"Overall SEO Health Score:\*\*?\s*\**(\d{1,3})/100", report_md)
    if match:
        return int(match.group(1))
    match = re.search(r"\*\*Overall\*\*\s*\|\s*\*\*(\d{1,3})\*\*", report_md)
    if match:
        return int(match.group(1))
    return 0


def strip_leading_h1(markdown_text: str) -> str:
    lines = markdown_text.splitlines()
    while lines and not lines[0].strip():
        lines.pop(0)
    if lines and lines[0].startswith("# "):
        lines.pop(0)
        while lines and not lines[0].strip():
            lines.pop(0)
    return "\n".join(lines)


def normalize_crawl_rows(payload: object) -> list[dict]:
    """Normalize crawl-all payloads across list and dict formats."""
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict) and isinstance(payload.get("pages"), list):
        return [item for item in payload["pages"] if isinstance(item, dict)]
    return []


def safe_category_score(lighthouse: dict, key: str, fallback: int = 0) -> int:
    """Return a Lighthouse category score on a 0-100 scale."""
    category = (lighthouse.get("categories", {}) or {}).get(key, {}) or {}
    raw = category.get("score")
    if isinstance(raw, (int, float)):
        return round(raw * 100) if raw <= 1 else round(raw)
    return fallback


def build_category_score_items(audit_summary: dict | None, lighthouse: dict) -> list[tuple[str, int]]:
    """Return category chart values from the audit summary when available."""
    scores = ((audit_summary or {}).get("category_scores", {}) or {})
    return [
        ("Technical", int(scores.get("technical", 0) or 0)),
        ("Content", int(scores.get("content", 0) or 0)),
        ("On-Page", int(scores.get("on_page", 0) or 0)),
        ("Schema", int(scores.get("schema", 0) or 0)),
        ("Performance", int(scores.get("performance", safe_category_score(lighthouse, "performance", 0)) or 0)),
        ("AI Readiness", int(scores.get("geo", 0) or 0)),
        ("Images", int(scores.get("images", 0) or 0)),
    ]


def build_cover_highlights(audit_summary: dict | None, lcp_seconds: float, non_200: int, visual: dict) -> list[str]:
    """Build data-driven cover highlights for the premium report."""
    highlights = [
        item.get("issue", "")
        for item in ((audit_summary or {}).get("priority_issues", []) or [])
        if item.get("issue")
    ][:3]
    if highlights:
        return highlights

    fallback = []
    if non_200:
        fallback.append(f"Crawl sample includes {non_200} non-200 URL(s) that should be reviewed.")
    if lcp_seconds:
        fallback.append(f"Homepage LCP snapshot is {lcp_seconds:.2f}s.")
    if visual.get("issues"):
        fallback.append(visual["issues"][0])
    if not fallback:
        fallback.append("Audit artifacts were generated successfully and are ready for review.")
    return fallback[:3]


def discover_screenshots(audit_dir: Path) -> list[tuple[Path, str]]:
    """Discover screenshots dynamically instead of relying on hard-coded names."""
    screenshots_dir = audit_dir / "screenshots"
    if not screenshots_dir.is_dir():
        return []

    files = sorted(
        path for path in screenshots_dir.iterdir()
        if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
    )
    if not files:
        return []

    prioritized = []
    for needle, caption in [
        ("desktop", "Desktop homepage render"),
        ("laptop", "Laptop homepage render"),
        ("tablet", "Tablet homepage render"),
        ("mobile", "Mobile homepage render"),
    ]:
        for path in files:
            if needle in path.stem.lower():
                prioritized.append((path, caption))
                break

    if prioritized:
        return prioritized
    return [(files[0], "Rendered page screenshot")]


def build_html(audit_dir: Path) -> tuple[str, int, str, str]:
    if markdown is None:
        raise RuntimeError(f"Markdown dependency unavailable: {MARKDOWN_IMPORT_ERROR}")

    report_path = audit_dir / "FULL-AUDIT-REPORT.md"
    action_path = audit_dir / "ACTION-PLAN.md"
    audit_summary = load_json_if_present(audit_dir / "SUMMARY.json") or {}
    summary_path = audit_dir / "strategy-pack" / "SUMMARY.json"
    summary: dict | None = None

    if summary_path.exists():
        summary = json.loads(summary_path.read_text(encoding="utf-8"))

    if report_path.exists():
        report_md = report_path.read_text(encoding="utf-8")
    elif summary is not None:
        analyzed_at = summary.get("analyzed_at", "")
        try:
            audit_date = datetime.fromisoformat(analyzed_at.replace("Z", "+00:00")).strftime("%B %d, %Y") if analyzed_at else datetime.utcnow().strftime("%B %d, %Y")
        except ValueError:
            audit_date = datetime.utcnow().strftime("%B %d, %Y")
        domain_value = summary.get("domain", audit_dir.name)
        target_pages = summary.get("target_pages", [])
        priority_tracks = summary.get("priority_tracks", [])
        competitors = summary.get("competitors", [])
        discovered_paths = summary.get("discovered_paths", [])
        content_calendar = summary.get("content_calendar", [])
        report_md = "\n".join(
            [
                f"# SEO Audit Report for {domain_value}",
                "",
                f"**Audit date:** {audit_date}",
                "",
                "## Executive Summary",
                f"This premium report was generated from the available audit artifacts for **{domain_value}**. The upstream pipeline did not provide `FULL-AUDIT-REPORT.md`, so this section was assembled from `strategy-pack/SUMMARY.json` and the machine-generated audit outputs.",
                "",
                "## Strategic Priorities",
                *(f"- {track}" for track in priority_tracks),
                "",
                "## Target Pages",
                *(f"- `{page}`" for page in target_pages),
                "",
                "## Competitive Landscape",
                *(f"- {competitor}" for competitor in competitors),
                "",
                "## Content Opportunities",
                *(f"- {entry.get('month', 'Upcoming')}: {entry.get('focus', 'Focus TBD')} - {entry.get('topics', 'Topics TBD')}" for entry in content_calendar),
                "",
                "## Site Inventory Snapshot",
                f"- Discovered paths: {len(discovered_paths)}",
                *(f"- `{path}`" for path in discovered_paths[:10]),
            ]
        ).strip()
    else:
        raise FileNotFoundError(f"Missing required report source: {report_path} or {summary_path}")

    if action_path.exists():
        action_md = strip_leading_h1(action_path.read_text(encoding="utf-8"))
    elif summary is not None:
        priority_tracks = summary.get("priority_tracks", [])
        goals = summary.get("goals", [])
        target_pages = summary.get("target_pages", [])
        action_md = "\n".join(
            [
                "## 30-60-90 Day Action Plan",
                "",
                "### Next 30 Days",
                *(f"- Align execution around: {goal}" for goal in goals),
                *(f"- Prioritize workstream: {track}" for track in priority_tracks),
                "",
                "### Days 31-60",
                *(f"- Expand or improve page: `{page}`" for page in target_pages[:5]),
                "",
                "### Days 61-90",
                "- Review impact, refresh underperforming pages, and extend winning content patterns.",
                "- Re-run the audit after implementation to validate score and performance improvements.",
            ]
        ).strip()
    else:
        raise FileNotFoundError(f"Missing required action plan source: {action_path} or {summary_path}")

    crawl_path = audit_dir / "crawl-all.json"
    if crawl_path.exists():
        crawl_all = json.loads(crawl_path.read_text(encoding="utf-8"))
    elif summary is not None:
        crawl_all = [{"url": page} for page in summary.get("target_pages", [])]
    else:
        raise FileNotFoundError(f"Missing crawl source: {crawl_path}")

    crawl_all = normalize_crawl_rows(crawl_all)
    parse_data = json.loads((audit_dir / "homepage-parse.json").read_text(encoding="utf-8"))

    lighthouse_path = audit_dir / "lighthouse.json"
    if lighthouse_path.exists():
        lighthouse = json.loads(lighthouse_path.read_text(encoding="utf-8"))
    else:
        lighthouse = {
            "categories": {
                "performance": {"score": 0},
                "accessibility": {"score": 0},
                "best-practices": {"score": 0},
                "seo": {"score": 0},
            },
            "audits": {
                "largest-contentful-paint": {"numericValue": 0},
                "cumulative-layout-shift": {"numericValue": 0},
            },
        }

    visual = json.loads((audit_dir / "visual-analysis.json").read_text(encoding="utf-8"))

    intro_md, sections = parse_report_sections(report_md)
    overall_score = extract_overall_score(report_md)
    if not overall_score:
        overall_score = int(audit_summary.get("overall_score", 0) or 0)
    audit_date_match = re.search(r"Audit date:\*\*\s*([A-Za-z]+\s+\d{1,2},\s+\d{4})", report_md)
    audit_date = audit_date_match.group(1) if audit_date_match else datetime.utcnow().strftime("%B %d, %Y")

    canonical_url = parse_data.get("canonical") or parse_data.get("open_graph", {}).get("og:url") or audit_dir.name
    domain = re.sub(r"^https?://", "", canonical_url).rstrip("/")
    long_titles = sum(1 for row in crawl_all if row.get("title_length", 0) > 60)
    long_meta = sum(1 for row in crawl_all if row.get("meta_description_length", 0) > 160)
    non_200 = sum(1 for row in crawl_all if row.get("status") != 200)

    category_scores = build_category_score_items(audit_summary, lighthouse)
    score_chart = svg_bar_chart("Category Score Breakdown", category_scores, 100, "#22d3ee")
    issue_chart = svg_bar_chart(
        "Issue Counts",
        [("404 URLs in sitemap", non_200), ("Long title tags", long_titles), ("Long meta descriptions", long_meta)],
        max(max(non_200, long_titles, long_meta), 10),
        "#f59e0b",
    )
    lighthouse_chart = svg_bar_chart(
        "Lighthouse Snapshot",
        [
            ("Performance", safe_category_score(lighthouse, "performance", 0)),
            ("Accessibility", safe_category_score(lighthouse, "accessibility", 0)),
            ("Best Practices", safe_category_score(lighthouse, "best-practices", 0)),
            ("SEO", safe_category_score(lighthouse, "seo", 0)),
        ],
        100,
        "#34d399",
    )

    screenshots = discover_screenshots(audit_dir)
    screenshot_markup = ""
    if screenshots:
        screenshot_markup = (
            "<div class='screenshot-grid'>"
            + "".join(screenshot_figure(path, caption) for path, caption in screenshots)
            + "</div>"
        )

    toc_items = []
    for section in sections:
        toc_items.append(f"<li><a href='#{section.anchor}'>{section.title}</a></li>")
    toc_items.append("<li><a href='#action-plan'>Action Plan</a></li>")
    toc_items.append("<li><a href='#visual-analysis-snapshot'>Visual Analysis Snapshot</a></li>")

    lcp_value = (((lighthouse.get("audits", {}) or {}).get("largest-contentful-paint", {}) or {}).get("numericValue", 0) or 0) / 1000
    cls_value = (((lighthouse.get("audits", {}) or {}).get("cumulative-layout-shift", {}) or {}).get("numericValue", 0) or 0)
    business_type_value = (
        ((summary or {}).get("site_meta", {}) or {}).get("business_type")
        or audit_summary.get("business_type")
    )
    industry_value = (
        ((summary or {}).get("site_meta", {}) or {}).get("industry")
        or audit_summary.get("industry")
    )
    if business_type_value and industry_value and industry_value.lower() not in business_type_value.lower():
        business_type_label = f"{title_case_label(business_type_value, 'Website')} / {title_case_label(industry_value, 'General Business')}"
    elif business_type_value or industry_value:
        business_type_label = title_case_label(business_type_value or industry_value, "Website")
    else:
        business_type_label = "Website"
    cover_highlights = build_cover_highlights(audit_summary, lcp_value, non_200, visual)
    executive_cards = render_metric_cards(
        [
            ("Pages reviewed", str(len(crawl_all))),
            ("Homepage word count", str(parse_data["word_count"])),
            ("LCP", f"{lcp_value:.2f}s"),
            ("CLS", f"{cls_value:.3f}"),
            ("Title issues", str(long_titles)),
            ("Meta issues", str(long_meta)),
        ]
    )

    section_html = []
    for section in sections:
        body_html = markdown(section.markdown_body, extensions=["tables", "fenced_code", "sane_lists"])
        extras = []
        if section.title == "Executive Summary":
            extras.append(executive_cards)
            extras.append(score_chart)
        elif section.title == "On-Page SEO":
            extras.append(issue_chart)
        elif section.title == "Performance":
            extras.append(lighthouse_chart)
        elif section.title == "Visual and UX Signals":
            extras.append(screenshot_markup)
        section_html.append(
            f"<section class='report-section' id='{section.anchor}'><h2>{section.title}</h2>{''.join(extras)}{body_html}</section>"
        )

    action_plan_html = markdown(action_md, extensions=["tables", "fenced_code", "sane_lists"])
    intro_html = markdown(intro_md, extensions=["tables", "fenced_code", "sane_lists"]) if intro_md else ""

    html_doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{domain} | Premium SEO Audit</title>
  <style>
    :root {{
      --ink: #081120;
      --surface: #f8fafc;
      --panel: #ffffff;
      --panel-alt: #eff6ff;
      --text: #0f172a;
      --muted: #475569;
      --line: #dbe4f0;
      --accent: #0ea5e9;
      --accent-2: #10b981;
      --warning: #f59e0b;
      --danger: #ef4444;
      --shadow: 0 16px 40px rgba(15, 23, 42, 0.08);
    }}
    * {{ box-sizing: border-box; }}
    html {{ scroll-behavior: smooth; }}
    body {{
      margin: 0;
      font-family: "Segoe UI", Inter, Arial, sans-serif;
      color: var(--text);
      background:
        radial-gradient(circle at top left, rgba(14, 165, 233, 0.10), transparent 24%),
        radial-gradient(circle at top right, rgba(16, 185, 129, 0.08), transparent 20%),
        var(--surface);
      line-height: 1.65;
    }}
    .page {{
      width: min(1120px, calc(100% - 48px));
      margin: 0 auto;
      padding: 32px 0 64px;
    }}
    .cover {{
      min-height: 92vh;
      display: grid;
      grid-template-columns: 1.2fr 0.8fr;
      gap: 32px;
      align-items: stretch;
      padding: 28px 0 40px;
    }}
    .cover-card, .cover-side, .toc, .report-section, .appendix {{
      background: rgba(255,255,255,0.92);
      border: 1px solid var(--line);
      border-radius: 24px;
      box-shadow: var(--shadow);
      overflow: hidden;
    }}
    .cover-card {{
      padding: 48px;
      background:
        linear-gradient(140deg, rgba(14,165,233,0.12), rgba(16,185,129,0.06)),
        rgba(255,255,255,0.94);
    }}
    .eyebrow {{
      display: inline-flex;
      gap: 8px;
      align-items: center;
      padding: 8px 14px;
      border-radius: 999px;
      background: rgba(14,165,233,0.10);
      color: #0369a1;
      font-size: 13px;
      font-weight: 700;
      letter-spacing: 0.06em;
      text-transform: uppercase;
    }}
    .cover h1 {{
      margin: 22px 0 14px;
      font-size: 48px;
      line-height: 1.05;
      letter-spacing: -0.04em;
    }}
    .subhead {{
      margin: 0;
      font-size: 19px;
      color: var(--muted);
      max-width: 55ch;
    }}
    .cover-meta {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 18px;
      margin-top: 28px;
    }}
    .cover-meta div {{
      padding: 16px 18px;
      border-radius: 16px;
      background: rgba(255,255,255,0.72);
      border: 1px solid rgba(148,163,184,0.24);
    }}
    .cover-meta span {{
      display: block;
      font-size: 12px;
      font-weight: 700;
      color: #64748b;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      margin-bottom: 6px;
    }}
    .cover-side {{
      padding: 32px 26px;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      background: linear-gradient(180deg, #081120, #0f172a);
      color: #e2e8f0;
    }}
    .score-ring {{
      width: 220px;
      height: 220px;
      margin: 0 auto 24px;
      border-radius: 50%;
      display: grid;
      place-items: center;
      padding: 14px;
    }}
    .score-ring-inner {{
      width: 100%;
      height: 100%;
      border-radius: 50%;
      background: #06101d;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      border: 1px solid rgba(255,255,255,0.08);
    }}
    .score-number {{ font-size: 64px; font-weight: 800; line-height: 1; }}
    .score-label {{ margin-top: 8px; font-size: 13px; text-transform: uppercase; letter-spacing: 0.12em; color: #7dd3fc; }}
    .highlight-list {{ margin: 0; padding-left: 20px; }}
    .highlight-list li {{ margin-bottom: 10px; color: #cbd5e1; }}
    .divider {{
      height: 1px;
      background: linear-gradient(90deg, transparent, rgba(148,163,184,0.3), transparent);
      margin: 22px 0;
    }}
    .toc {{
      padding: 28px 32px;
      margin-bottom: 28px;
    }}
    .toc h2, .report-section h2, .appendix h2 {{
      margin: 0 0 16px;
      font-size: 28px;
      letter-spacing: -0.03em;
    }}
    .toc ol {{
      margin: 0;
      padding-left: 22px;
      columns: 2;
      column-gap: 40px;
    }}
    .toc li {{ margin-bottom: 10px; break-inside: avoid; }}
    .toc a {{ color: #0f172a; text-decoration: none; }}
    .toc a:hover {{ color: var(--accent); }}
    .report-section, .appendix {{
      padding: 28px 32px;
      margin-bottom: 26px;
      page-break-inside: avoid;
    }}
    .report-section h3 {{ margin-top: 24px; }}
    .report-section p, .report-section li, .appendix p, .appendix li {{
      color: var(--muted);
    }}
    .report-section table {{
      width: 100%;
      border-collapse: collapse;
      margin: 22px 0;
      overflow: hidden;
      border-radius: 16px;
    }}
    .report-section th, .report-section td {{
      border: 1px solid var(--line);
      padding: 12px 14px;
      text-align: left;
      vertical-align: top;
    }}
    .report-section th {{
      background: #eff6ff;
      font-size: 13px;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: #0f172a;
    }}
    .metric-grid {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 16px;
      margin: 18px 0 28px;
    }}
    .metric-card {{
      background: linear-gradient(180deg, #f8fbff, #eef6ff);
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 18px;
      min-height: 112px;
      display: flex;
      flex-direction: column;
      justify-content: center;
    }}
    .metric-value {{
      font-size: 34px;
      font-weight: 800;
      line-height: 1.1;
      color: #0f172a;
    }}
    .metric-label {{
      margin-top: 8px;
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: #64748b;
    }}
    .chart-figure {{
      margin: 24px 0 26px;
      padding: 18px;
      background: #0b1423;
      border-radius: 20px;
      overflow: hidden;
      box-shadow: inset 0 0 0 1px rgba(148,163,184,0.12);
    }}
    .chart-figure figcaption {{
      margin-bottom: 10px;
      color: #cbd5e1;
      font-size: 13px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }}
    .chart {{
      width: 100%;
      height: auto;
      aspect-ratio: 16 / 9;
      display: block;
    }}
    .screenshot-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 18px;
      margin: 22px 0 28px;
    }}
    .screenshot-card {{
      margin: 0;
      border: 1px solid var(--line);
      border-radius: 18px;
      overflow: hidden;
      background: #fff;
      box-shadow: var(--shadow);
    }}
    .screenshot-card img {{
      width: 100%;
      height: auto;
      display: block;
      object-fit: contain;
      background: #f8fafc;
    }}
    .screenshot-card figcaption {{
      padding: 12px 14px;
      font-size: 14px;
      color: var(--muted);
      background: #fff;
    }}
    .appendix details {{
      border: 1px solid var(--line);
      border-radius: 16px;
      padding: 14px 16px;
      margin-bottom: 14px;
      background: #fff;
    }}
    .appendix summary {{
      cursor: pointer;
      font-weight: 700;
      color: #0f172a;
    }}
    .appendix .prose {{
      margin-top: 12px;
    }}
    code {{
      background: #eaf2ff;
      color: #0f172a;
      padding: 2px 6px;
      border-radius: 6px;
    }}
    @media print {{
      @page {{
        margin: 18mm 14mm 22mm 14mm;
      }}
      body {{ background: #fff; }}
      .page {{ width: 100%; padding: 0; }}
      .cover {{
        grid-template-columns: 1fr 0.9fr;
        min-height: auto;
        padding: 0;
        page-break-after: always;
      }}
      .cover-card, .cover-side, .toc, .report-section, .appendix {{
        box-shadow: none;
        break-inside: avoid;
      }}
      .toc {{ page-break-after: always; }}
      .report-section {{ margin-bottom: 14px; }}
    }}
    @media (max-width: 900px) {{
      .cover {{ grid-template-columns: 1fr; }}
      .metric-grid, .screenshot-grid {{ grid-template-columns: 1fr; }}
      .toc ol {{ columns: 1; }}
    }}
  </style>
</head>
<body>
  <div class="page">
    <section class="cover">
      <div class="cover-card">
        <div class="eyebrow">Premium SEO Deliverable</div>
        <h1>SEO Audit & Strategy Report</h1>
        <p class="subhead">A professional HTML and PDF report for {domain}, built from the completed Codex SEO audit with inline evidence, charts, screenshots, and a print-safe structure.</p>
        <div class="cover-meta">
          <div><span>Website</span>{domain}</div>
          <div><span>Audit Date</span>{audit_date}</div>
          <div><span>Business Type</span>{business_type_label}</div>
          <div><span>Pages Reviewed</span>{len(crawl_all)} URLs reviewed</div>
        </div>
      </div>
      <aside class="cover-side">
        <div>
          {score_ring(overall_score)}
          <ul class="highlight-list">
            {''.join(f"<li>{escape(item)}</li>" for item in cover_highlights)}
          </ul>
        </div>
        <div>
          <div class="divider"></div>
          <p style="margin:0;color:#94a3b8;font-size:13px;">Generated from the shared premium report standard in <code>{PREMIUM_STANDARD.relative_to(REPO_ROOT)}</code>.</p>
        </div>
      </aside>
    </section>

    <nav class="toc" id="table-of-contents">
      <h2>Table of Contents</h2>
      {intro_html}
      <ol>{''.join(toc_items)}</ol>
    </nav>

    {''.join(section_html)}

    <section class="report-section" id="action-plan">
      <h2>Action Plan</h2>
      {action_plan_html}
    </section>

    <section class="appendix" id="visual-analysis-snapshot">
      <h2>Visual Analysis Snapshot</h2>
      <div class="prose">
        <p><strong>H1 visible above the fold:</strong> {"Yes" if visual['above_fold']['h1_visible'] else "No"}</p>
        <p><strong>CTA visible above the fold:</strong> {"Yes" if visual['above_fold']['cta_visible'] else "No"}</p>
        <p><strong>Mobile viewport meta present:</strong> {"Yes" if visual['mobile']['viewport_meta'] else "No"}</p>
        <p><strong>Horizontal scroll detected:</strong> {"Yes" if visual['mobile']['horizontal_scroll'] else "No"}</p>
      </div>
    </section>
  </div>
</body>
</html>"""
    default_html_name, default_pdf_name = derive_report_filenames(audit_dir, canonical_url, report_md)
    return html_doc, overall_score, default_html_name, default_pdf_name


def generate_report(audit_dir: Path, html_name: str | None = None, pdf_name: str | None = None) -> dict[str, object]:
    """Generate internal HTML plus PDF for an audit directory."""
    if sync_playwright is None:
        raise RuntimeError(f"Playwright dependency unavailable: {PLAYWRIGHT_IMPORT_ERROR}")

    audit_dir = audit_dir.resolve()
    if not audit_dir.is_dir():
        raise RuntimeError(f"Audit directory not found: {audit_dir}")

    html_doc, overall_score, default_html_name, default_pdf_name = build_html(audit_dir)
    html_path = audit_dir / (html_name or default_html_name)
    pdf_path = audit_dir / (pdf_name or default_pdf_name)
    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(html_doc, encoding="utf-8")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(html_path.as_uri(), wait_until="networkidle")

        page.evaluate(
            """
            () => {
              document.querySelectorAll('details').forEach((el) => { el.open = true; });
            }
            """
        )
        page.emulate_media(media="print")

        content_metrics = page.evaluate(
            """
            () => {
              const doc = document.documentElement;
              const body = document.body;
              const width = Math.max(doc.scrollWidth, body.scrollWidth, doc.offsetWidth, body.offsetWidth);
              const height = Math.max(doc.scrollHeight, body.scrollHeight, doc.offsetHeight, body.offsetHeight);
              return { width, height };
            }
            """
        )
        pdf_gutter_px = 32
        content_width_px = max(int(content_metrics["width"]), 1100)
        content_height_px = int(content_metrics["height"])
        pdf_width_px = content_width_px + (pdf_gutter_px * 2)
        pdf_height_px = content_height_px + (pdf_gutter_px * 2)

        page.add_style_tag(
            content=f"""
            @page {{
              size: {pdf_width_px}px {pdf_height_px}px;
              margin: 0;
            }}
            html, body {{
              margin: 0 !important;
              padding: 0 !important;
              background: #ffffff !important;
            }}
            .page {{
              width: {content_width_px}px !important;
              max-width: none !important;
              padding: 0 !important;
              margin: {pdf_gutter_px}px auto !important;
            }}
            .cover, .toc, .report-section, .appendix {{
              break-inside: avoid !important;
              page-break-inside: avoid !important;
              page-break-after: auto !important;
            }}
            details {{
              display: block !important;
            }}
            details > *:not(summary) {{
              display: block !important;
            }}
            summary {{
              list-style: none !important;
            }}
            summary::-webkit-details-marker {{
              display: none !important;
            }}
            """
        )
        page.wait_for_timeout(250)
        page.pdf(
            path=str(pdf_path),
            width=f"{pdf_width_px}px",
            height=f"{pdf_height_px}px",
            print_background=True,
            display_header_footer=False,
            prefer_css_page_size=True,
            margin={"top": "0", "right": "0", "bottom": "0", "left": "0"},
        )
        browser.close()

    return {
        "audit_dir": str(audit_dir),
        "html_internal": str(html_path),
        "pdf": str(pdf_path),
        "overall_score": overall_score,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a premium SEO audit report.")
    parser.add_argument("audit_dir", help="Path to the audit output directory")
    parser.add_argument("--html", help="Internal HTML filename")
    parser.add_argument("--pdf", help="Output PDF filename")
    args = parser.parse_args()

    audit_dir = Path(args.audit_dir).resolve()
    if not audit_dir.is_dir():
        raise SystemExit(f"Audit directory not found: {audit_dir}")

    print(json.dumps(generate_report(audit_dir, html_name=args.html, pdf_name=args.pdf), indent=2))


if __name__ == "__main__":
    main()
