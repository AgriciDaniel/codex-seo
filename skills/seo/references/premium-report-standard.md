# Premium Report Standard

Use this as the default brief whenever generating a premium report.
Apply it across audit, page, schema, GEO, performance, visual, planning, programmatic,
competitor, hreflang, and image deliverables unless the user gives stronger instructions.

## Deliverable Policy

- Generate HTML as an internal intermediate artifact when it helps produce the final PDF.
- Treat the PDF as the primary user-facing deliverable by default.
- Do not present, recommend, or link the HTML artifact unless the user explicitly asks for it.
- If HTML is generated, save it to an internal path rather than the main deliverable surface when possible.

## Core Requirements

- Include all relevant findings, data points, supporting evidence, and recommendations.
- Embed relevant screenshots inline near the sections they support.
- Add charts or graphs where comparisons clarify the findings.
- Preserve proper chart aspect ratios; never squish or stretch charts.
- Add captions and labels for every screenshot, chart, or visual element.

## Layout and Formatting

- Use a clean, professional layout with a title page, table of contents, and clear section headers.
- Use consistent fonts, colors, spacing, and styling throughout.
- Add section dividers and page numbers in the print/PDF output.
- Ensure all text, images, tables, and charts fit within page boundaries.
- Review the final HTML and PDF for clipping, overflow, overlap, or broken pagination before delivery.

## Visual Rules

- Use bar, pie, or line charts where metric comparisons or score breakdowns are relevant.
- Size screenshots and visuals to fit within page boundaries with clear margins.
- Keep screenshots readable and proportional.
- Prefer one strong visual per section over cluttered multi-visual layouts.

## Content Structure

1. Title page
2. Table of contents
3. Executive summary
4. Findings by section
5. Recommendations / action plan
6. Supporting visuals, charts, and evidence

## Adaptation Rules

- Adapt the exact section naming to the report type.
- For HTML and PDF, the content should be the same deliverable in two formats, but the PDF is the default shareable output.
- If some requested visual or chart would be misleading due to weak data, omit it and say why.
- When screenshots are available, use them rather than describing visual issues abstractly.
- When quantitative metrics exist, prefer charts over dense prose lists.

## Final Response Rule

- In your final response, reference the PDF deliverable with its absolute filesystem path so it is clickable in Codex CLI.
- Reference the internal HTML artifact only if the user explicitly asks for the HTML file.
