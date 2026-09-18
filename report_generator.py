"""
report_generator.py
--------------------
Turns a list of {facts, judgment} results into a Markdown report and an
HTML dashboard. Facts (script output) and judgment (LLM output) are always
shown in visually separate blocks so nobody confuses "detected" with "AI opinion".
"""
import html
from dataclasses import asdict
from datetime import datetime, timezone


def _fmt_bool(b):
    return "Yes" if b else "No"


def _facts_to_dict(facts):
    return asdict(facts) if not isinstance(facts, dict) else facts


def generate_markdown_report(results: list) -> str:
    """results: list of {"facts": SiteFacts|dict, "judgment": dict}"""
    lines = []
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines.append(f"# Immigration Consultancy Website Audit Report\n")
    lines.append(f"_Generated {ts}_\n")
    lines.append(
        "> **Note on this report:** Sections marked **Automatically Detected Facts** "
        "come directly from the scraping script with no interpretation. Sections marked "
        "**AI-Generated Judgment** are the LLM's opinion based on those facts and may be "
        "wrong or incomplete -- verify before acting on them.\n"
    )

    # Summary table
    lines.append("## Summary\n")
    lines.append("| Website | Score | # Problems | # Missing Features | Priority |")
    lines.append("|---|---|---|---|---|")
    for r in results:
        f = _facts_to_dict(r["facts"])
        j = r["judgment"]
        if not f.get("reachable"):
            lines.append(f"| {f['url']} | N/A | N/A | N/A | **UNREACHABLE** ({f.get('error')}) |")
            continue
        lines.append(
            f"| {f['url']} | {j.get('score', 'N/A')} | {len(j.get('problems', []))} "
            f"| {len(j.get('missing_features', []))} | {j.get('overall_priority', 'N/A')} |"
        )
    lines.append("")

    # Per-site detail
    for r in results:
        f = _facts_to_dict(r["facts"])
        j = r["judgment"]
        lines.append(f"---\n## {f['url']}\n")

        if not f.get("reachable"):
            lines.append(f"**Site could not be audited.** Error: `{f.get('error')}`\n")
            lines.append("_This is a graceful failure -- the script did not crash, it just recorded the error._\n")
            continue

        lines.append("### 🔍 Automatically Detected Facts (script output, no interpretation)\n")
        lines.append(f"- HTTP status: {f.get('http_status')} | HTTPS: {_fmt_bool(f.get('https'))} | Load time: {f.get('load_time_ms')} ms")
        lines.append(f"- Pages crawled: {f.get('pages_crawled')} | Internal links found: {f.get('internal_link_count')} | Nav links: {f.get('nav_link_count')}")
        lines.append(f"- Title: {f.get('title') or '_none found_'}")
        lines.append(f"- Meta description present: {_fmt_bool(f.get('has_meta_description'))}")
        lines.append(f"- Contact form present: {_fmt_bool(f.get('contact_form_present'))} (fields: {f.get('contact_form_fields') or 'n/a'})")
        lines.append(f"- Phone number visible: {_fmt_bool(f.get('phone_found'))} | Email visible: {_fmt_bool(f.get('email_found'))}")
        lines.append(f"- CTA buttons found ({f.get('cta_count')}): {', '.join(f.get('cta_buttons_found') or []) or 'none'}")
        lines.append(f"- Social links found: {', '.join(f.get('social_links', {}).keys()) or 'none'}")
        lines.append(f"- FAQ section present: {_fmt_bool(f.get('faq_present'))}")
        lines.append(f"- Images: {f.get('images_total')} total, {f.get('images_with_alt')} with alt text "
                      f"({f.get('alt_text_coverage_pct')}% coverage)")
        lines.append(f"- Mobile viewport meta tag present: {_fmt_bool(f.get('viewport_meta_present'))}")
        lines.append(f"- Approx. word count (crawled pages): {f.get('word_count')}")
        lines.append(f"- robots.txt status: {f.get('robots_txt_status')}\n")

        mock_tag = " ⚠️ _MOCK judgment (no LLM API key configured)_" if j.get("_mock") else ""
        lines.append(f"### 🤖 AI-Generated Judgment{mock_tag}\n")
        lines.append(f"**Score: {j.get('score')}/100** — {j.get('score_rationale')}\n")

        if j.get("problems"):
            lines.append("**Problems identified:**")
            for p in j["problems"]:
                lines.append(f"- {p}")
            lines.append("")

        if j.get("missing_features"):
            lines.append("**Missing features:**")
            for m in j["missing_features"]:
                lines.append(f"- {m}")
            lines.append("")

        if j.get("recommendations"):
            lines.append("**Recommendations:**")
            for rec in j["recommendations"]:
                lines.append(f"- **[{rec.get('priority','?').upper()}]** {rec.get('action')} — _{rec.get('why','')}_")
            lines.append("")

        lines.append(f"**Overall priority: {j.get('overall_priority', 'N/A').upper()}**\n")

    return "\n".join(lines)


def generate_html_report(results: list) -> str:
    """Simple, dependency-free HTML dashboard version of the same report."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    def esc(s):
        return html.escape(str(s)) if s is not None else ""

    rows = []
    for r in results:
        f = _facts_to_dict(r["facts"])
        j = r["judgment"]
        if not f.get("reachable"):
            rows.append(f"<tr class='unreachable'><td>{esc(f['url'])}</td><td colspan='4'>UNREACHABLE — {esc(f.get('error'))}</td></tr>")
            continue
        score = j.get("score", "N/A")
        score_class = "low" if isinstance(score, int) and score < 50 else "mid" if isinstance(score, int) and score < 75 else "high"
        rows.append(
            f"<tr><td><a href='{esc(f['url'])}' target='_blank'>{esc(f['url'])}</a></td>"
            f"<td class='score {score_class}'>{esc(score)}</td>"
            f"<td>{len(j.get('problems', []))}</td>"
            f"<td>{len(j.get('missing_features', []))}</td>"
            f"<td class='priority-{esc(j.get('overall_priority','na'))}'>{esc(j.get('overall_priority','N/A')).upper()}</td></tr>"
        )

    detail_sections = []
    for r in results:
        f = _facts_to_dict(r["facts"])
        j = r["judgment"]
        if not f.get("reachable"):
            detail_sections.append(f"""
            <section class="site-detail unreachable">
              <h2>{esc(f['url'])}</h2>
              <p><strong>Could not be audited.</strong> Error: <code>{esc(f.get('error'))}</code></p>
            </section>""")
            continue

        problems_html = "".join(f"<li>{esc(p)}</li>" for p in j.get("problems", [])) or "<li>None noted</li>"
        missing_html = "".join(f"<li>{esc(m)}</li>" for m in j.get("missing_features", [])) or "<li>None noted</li>"
        recs_html = "".join(
            f"<li><span class='badge {esc(rec.get('priority'))}'>{esc(rec.get('priority','?')).upper()}</span> "
            f"{esc(rec.get('action'))} <em>— {esc(rec.get('why',''))}</em></li>"
            for rec in j.get("recommendations", [])
        ) or "<li>None</li>"
        mock_note = "<p class='mock-note'>⚠️ MOCK judgment — no LLM API key configured for this run.</p>" if j.get("_mock") else ""

        detail_sections.append(f"""
        <section class="site-detail">
          <h2>{esc(f['url'])}</h2>
          <div class="facts-block">
            <h3>🔍 Automatically Detected Facts</h3>
            <ul class="facts-grid">
              <li>HTTP status: {esc(f.get('http_status'))} | HTTPS: {_fmt_bool(f.get('https'))} | Load time: {esc(f.get('load_time_ms'))} ms</li>
              <li>Pages crawled: {esc(f.get('pages_crawled'))} | Internal links: {esc(f.get('internal_link_count'))}</li>
              <li>Title: {esc(f.get('title') or 'none found')}</li>
              <li>Meta description present: {_fmt_bool(f.get('has_meta_description'))}</li>
              <li>Contact form present: {_fmt_bool(f.get('contact_form_present'))}</li>
              <li>Phone visible: {_fmt_bool(f.get('phone_found'))} | Email visible: {_fmt_bool(f.get('email_found'))}</li>
              <li>CTA buttons ({esc(f.get('cta_count'))}): {esc(', '.join(f.get('cta_buttons_found') or []) or 'none')}</li>
              <li>Social links: {esc(', '.join(f.get('social_links', {}).keys()) or 'none')}</li>
              <li>FAQ present: {_fmt_bool(f.get('faq_present'))}</li>
              <li>Alt text coverage: {esc(f.get('alt_text_coverage_pct'))}% ({esc(f.get('images_with_alt'))}/{esc(f.get('images_total'))} images)</li>
              <li>Mobile viewport meta present: {_fmt_bool(f.get('viewport_meta_present'))}</li>
              <li>robots.txt status: {esc(f.get('robots_txt_status'))}</li>
            </ul>
          </div>
          <div class="judgment-block">
            <h3>🤖 AI-Generated Judgment</h3>
            {mock_note}
            <p class="score-line">Score: <strong>{esc(j.get('score'))}/100</strong> — {esc(j.get('score_rationale'))}</p>
            <h4>Problems</h4><ul>{problems_html}</ul>
            <h4>Missing Features</h4><ul>{missing_html}</ul>
            <h4>Recommendations</h4><ul class="recs">{recs_html}</ul>
            <p class="overall-priority">Overall priority: <strong>{esc(j.get('overall_priority','N/A')).upper()}</strong></p>
          </div>
        </section>""")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Immigration Consultancy Website Audit</title>
<style>
  :root {{
    --bg: #f7f7f5; --card: #ffffff; --ink: #1f2421; --muted: #6b7280;
    --line: #e5e7eb; --accent: #2f6f4f; --high: #b91c1c; --mid: #b45309; --low: #15803d;
  }}
  body {{ font-family: -apple-system, Segoe UI, Roboto, sans-serif; background: var(--bg); color: var(--ink); margin: 0; padding: 2rem; }}
  h1 {{ margin-bottom: 0.2rem; }}
  .timestamp {{ color: var(--muted); font-size: 0.9rem; margin-bottom: 1.5rem; }}
  .disclaimer {{ background: #fff8e6; border: 1px solid #f0d98c; padding: 0.9rem 1.1rem; border-radius: 8px; margin-bottom: 1.5rem; font-size: 0.92rem; }}
  table {{ width: 100%; border-collapse: collapse; background: var(--card); border-radius: 8px; overflow: hidden; margin-bottom: 2rem; }}
  th, td {{ text-align: left; padding: 0.6rem 0.9rem; border-bottom: 1px solid var(--line); }}
  th {{ background: #eef2ee; }}
  tr.unreachable td {{ color: var(--muted); font-style: italic; }}
  .score.high {{ color: var(--low); font-weight: 700; }}
  .score.mid {{ color: var(--mid); font-weight: 700; }}
  .score.low {{ color: var(--high); font-weight: 700; }}
  .priority-high {{ color: var(--high); font-weight: 700; }}
  .priority-medium {{ color: var(--mid); font-weight: 700; }}
  .priority-low {{ color: var(--low); font-weight: 700; }}
  section.site-detail {{ background: var(--card); border: 1px solid var(--line); border-radius: 10px; padding: 1.2rem 1.5rem; margin-bottom: 1.5rem; }}
  .facts-block {{ background: #f4f8f5; border-radius: 8px; padding: 0.9rem 1.1rem; margin-bottom: 1rem; }}
  .judgment-block {{ background: #f4f6fb; border-radius: 8px; padding: 0.9rem 1.1rem; }}
  .facts-grid {{ columns: 2; column-gap: 2rem; font-size: 0.92rem; }}
  .mock-note {{ color: #92400e; font-size: 0.85rem; }}
  .badge {{ display: inline-block; font-size: 0.7rem; font-weight: 700; padding: 0.1rem 0.4rem; border-radius: 4px; margin-right: 0.3rem; }}
  .badge.high {{ background: #fee2e2; color: var(--high); }}
  .badge.medium {{ background: #fef3c7; color: var(--mid); }}
  .badge.low {{ background: #dcfce7; color: var(--low); }}
</style>
</head>
<body>
  <h1>Immigration Consultancy Website Audit</h1>
  <div class="timestamp">Generated {esc(ts)}</div>
  <div class="disclaimer">
    <strong>How to read this report:</strong> "🔍 Automatically Detected Facts" come straight from the
    scraping script — deterministic, no interpretation. "🤖 AI-Generated Judgment" is the LLM's opinion
    based on those facts and can be wrong or incomplete. Treat scores and recommendations as a
    starting point for human review, not a final verdict.
  </div>
  <table>
    <thead><tr><th>Website</th><th>Score</th><th># Problems</th><th># Missing</th><th>Priority</th></tr></thead>
    <tbody>{''.join(rows)}</tbody>
  </table>
  {''.join(detail_sections)}
</body>
</html>"""
