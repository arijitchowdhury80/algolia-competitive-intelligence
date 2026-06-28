"""Export dashboard-ready static assets from CI runtime artifacts."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


DATE_RE = re.compile(r"^(?P<date>\d{4}-\d{2}-\d{2})(?P<weekly>-weekly)?\.md$")
LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


@dataclass(frozen=True)
class ReportFile:
    date: str
    cadence: str
    path: Path
    text: str


def strip_markdown(text: str) -> str:
    text = LINK_RE.sub(r"\1", text or "")
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"^\s*[-*]\s+", "", text, flags=re.MULTILINE)
    text = humanize_copy(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def humanize_copy(text: str) -> str:
    text = (text or "").replace("_", " ")
    replacements = {
        "changed case study": "customer proof changed",
        "changed blog": "blog changed",
        "changed press": "press page changed",
        "case study source": "customer proof source",
        "case study": "customer proof",
    }
    for before, after in replacements.items():
        text = re.sub(before, after, text, flags=re.IGNORECASE)
    return text


def markdown_inline_to_html(text: str) -> str:
    text = humanize_copy(text)
    safe = escape(text or "")

    def repl(match: re.Match[str]) -> str:
        label = escape(match.group(1))
        url = escape(match.group(2), quote=True)
        return '<a href="{url}">{label}</a>'.format(url=url, label=label)

    safe = LINK_RE.sub(repl, safe)
    safe = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", safe)
    return safe


def primary_title(daily: Optional[ReportFile], fallback_text: str) -> str:
    if daily:
        links = evidence_links(daily.text, limit=1)
        if links:
            label = strip_markdown(links[0][0])
            return "%s needs validation." % label
    title = strip_markdown(fallback_text).rstrip(".") + "."
    if len(title) > 110:
        title = title[:107].rstrip() + "..."
    return title


def parse_section(markdown: str, heading: str) -> str:
    wanted = heading.strip().lower()
    lines = markdown.splitlines()
    start: Optional[int] = None
    for i, line in enumerate(lines):
        label = line.strip().strip("*").strip().lower()
        if label == wanted:
            start = i + 1
            break
    if start is None:
        return ""
    collected: List[str] = []
    for line in lines[start:]:
        label = line.strip()
        if label.startswith("**") and label.endswith("**") and collected:
            break
        collected.append(line)
    return "\n".join(collected).strip()


def first_paragraph(section: str) -> str:
    blocks = [part.strip() for part in re.split(r"\n\s*\n", section or "") if part.strip()]
    return blocks[0] if blocks else ""


def bullet_lines(section: str, limit: int = 6) -> List[str]:
    lines = []
    for line in (section or "").splitlines():
        stripped = line.strip()
        if stripped.startswith("- "):
            lines.append(stripped[2:].strip())
    return lines[:limit]


def report_files(output_root: Path) -> List[ReportFile]:
    briefs_dir = output_root / "briefs"
    reports: List[ReportFile] = []
    if not briefs_dir.exists():
        return reports
    for path in sorted(briefs_dir.glob("*.md")):
        match = DATE_RE.match(path.name)
        if not match:
            continue
        reports.append(
            ReportFile(
                date=match.group("date"),
                cadence="weekly" if match.group("weekly") else "daily",
                path=path,
                text=path.read_text(),
            )
        )
    return reports


def latest_report(reports: Sequence[ReportFile], cadence: str) -> Optional[ReportFile]:
    matches = [report for report in reports if report.cadence == cadence]
    return max(matches, key=lambda report: report.date) if matches else None


def copy_archive(reports: Sequence[ReportFile], public_dir: Path) -> None:
    archive_dir = public_dir / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    for report in reports:
        shutil.copy2(report.path, archive_dir / report.path.name)


def copy_latest(report: Optional[ReportFile], public_dir: Path, name: str) -> None:
    target = public_dir / name
    if report:
        target.write_text(report.text)
    elif target.exists():
        target.unlink()


def covered_range(reports: Sequence[ReportFile]) -> str:
    if not reports:
        return "No archived reports"
    dates = sorted({report.date for report in reports})
    if len(dates) == 1:
        return dates[0]
    return "%s to %s" % (dates[0], dates[-1])


def day_span(reports: Sequence[ReportFile]) -> str:
    if not reports:
        return "0d"
    dates = sorted({datetime.strptime(report.date, "%Y-%m-%d") for report in reports})
    return "%dd" % max(1, (dates[-1] - dates[0]).days + 1)


def evidence_links(markdown: str, limit: int = 4) -> List[Tuple[str, str]]:
    seen = set()
    links: List[Tuple[str, str]] = []
    for label, url in LINK_RE.findall(markdown or ""):
        key = (label, url)
        if key in seen:
            continue
        seen.add(key)
        links.append((label, url))
        if len(links) >= limit:
            break
    return links


def render_evidence(links: Sequence[Tuple[str, str]], fallback_href: str) -> str:
    items = ['<a href="{href}">Open latest daily brief</a>'.format(href=escape(fallback_href, quote=True))]
    for label, url in links:
        items.append(
            '<a href="{url}">{label}</a>'.format(
                url=escape(url, quote=True),
                label=escape(strip_markdown(label)),
            )
        )
    return " · ".join(items)


def render_finding_cards(weekly: Optional[ReportFile], daily: Optional[ReportFile]) -> str:
    cards: List[str] = []
    if weekly:
        actions = bullet_lines(parse_section(weekly.text, "Recommended actions by owner"), limit=4)
        for action in actions:
            owner = "Review"
            title = strip_markdown(action)
            if ":" in title:
                owner, title = title.split(":", 1)
                owner = owner.strip()
                title = title.strip()
            cards.append(
                """
            <article class="finding">
              <div class="rank">
                <strong>{owner}</strong>
                <span>Found: {date} weekly</span>
                <span>Source: Weekly synthesis</span>
              </div>
              <div>
                <h3>{title}</h3>
                <p><strong>What happened:</strong> {what}</p>
                <p><strong>Why it matters:</strong> {why}</p>
                <div class="recommendation">Recommended response: {title}</div>
                <div class="tags">
                  <span class="pill blue">Owner specific</span>
                  <span class="pill amber">Validate before action</span>
                </div>
                <details>
                  <summary>Show evidence</summary>
                  <div class="proof-grid">
                    <div class="proof"><span>Archived weekly</span><a href="archive/{weekly_name}">Open weekly synthesis</a></div>
                    {daily_proof}
                  </div>
                </details>
              </div>
            </article>
                """.format(
                    owner=escape(owner),
                    date=escape(weekly.date),
                    title=escape(title),
                    what=escape(strip_markdown(first_paragraph(parse_section(weekly.text, "What changed")))),
                    why=escape(strip_markdown(first_paragraph(parse_section(weekly.text, "Strategic pattern")))),
                    weekly_name=escape(weekly.path.name, quote=True),
                    daily_proof=(
                        '<div class="proof"><span>Archived daily</span><a href="archive/{name}">Open daily brief</a></div>'.format(
                            name=escape(daily.path.name, quote=True)
                        )
                        if daily
                        else ""
                    ),
                )
            )
    if not cards:
        cards.append(
            """
            <article class="finding">
              <div class="rank"><strong>Review</strong><span>No weekly action available</span></div>
              <div>
                <h3>No owner-specific action is available yet.</h3>
                <p><strong>What happened:</strong> The dashboard found no weekly recommendations in the archived briefs.</p>
                <p><strong>Why it matters:</strong> A quiet or incomplete archive should not create fake actions.</p>
                <div class="recommendation">Recommended response: wait for the next complete CI run.</div>
              </div>
            </article>
            """
        )
    return "\n".join(cards)


def render_report_history(reports: Sequence[ReportFile]) -> str:
    rows = []
    for report in sorted(reports, key=lambda item: (item.date, item.cadence), reverse=True)[:10]:
        section_name = "What changed" if report.cadence == "weekly" else "Bottom line"
        summary = strip_markdown(first_paragraph(parse_section(report.text, section_name))) or "Archived CI report."
        label = "%s %s" % (report.date, report.cadence)
        rows.append(
            """
            <div class="report-row">
              <time>{date}</time>
              <div><b>{label}</b><span>{summary}</span></div>
              <a href="archive/{name}">Open</a>
            </div>
            """.format(
                date=escape(report.date),
                label=escape(label),
                summary=escape(summary[:180]),
                name=escape(report.path.name, quote=True),
            )
        )
    return "\n".join(rows) or '<div class="empty">No archived reports yet.</div>'


def render_dashboard_html(
    reports: Sequence[ReportFile],
    daily: Optional[ReportFile],
    weekly: Optional[ReportFile],
    generated_at: str,
) -> str:
    what = first_paragraph(parse_section(daily.text, "Bottom line")) if daily else "No daily competitive pulse has been archived yet."
    response = first_paragraph(parse_section(daily.text, "Recommended action")) if daily else "Wait for the next daily CI run before taking action."
    why = (
        first_paragraph(parse_section(weekly.text, "Strategic pattern"))
        if weekly
        else "There is not enough weekly context yet to separate a real pattern from a single-day signal."
    )
    evidence = evidence_links(daily.text if daily else "", limit=4)
    daily_href = "archive/%s" % daily.path.name if daily else "latest-daily.md"
    headline = primary_title(daily, what)
    weekly_actions = bullet_lines(parse_section(weekly.text, "Recommended actions by owner") if weekly else "")
    battlecard_updates = bullet_lines(parse_section(weekly.text, "Battlecard updates") if weekly else "")
    daily_count = len([report for report in reports if report.cadence == "daily"])
    weekly_count = len([report for report in reports if report.cadence == "weekly"])
    finding_count = max(1 if daily else 0, len(weekly_actions))

    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <base target="_blank">
  <title>Algolia Competitive Intelligence</title>
  <style>
    :root {{
      --blue: #003dff;
      --ink: #06133f;
      --body: #2f374e;
      --muted: #68748c;
      --line: #d9e1ef;
      --canvas: #f6f8fc;
      --paper: #ffffff;
      --soft: #fbfcff;
      --blue-soft: #eef3ff;
      --green: #087f5b;
      --green-soft: #e9fbf3;
      --amber: #9a6700;
      --amber-soft: #fff5d6;
      --red: #b42318;
      --red-soft: #fff1f0;
      --violet: #5b35d5;
      --violet-soft: #f0edff;
      --shadow: 0 12px 30px rgba(6, 19, 63, .08);
      --radius: 8px;
      color-scheme: light;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    * {{ box-sizing: border-box; }}
    html, body {{ max-width: 100%; overflow-x: hidden; }}
    body {{ margin: 0; background: var(--canvas); color: var(--body); }}
    a {{ color: var(--blue); font-weight: 760; text-decoration: none; overflow-wrap: anywhere; }}
    a:hover {{ text-decoration: underline; }}
    h1, h2, h3, p {{ margin-top: 0; }}
    h1 {{ margin-bottom: 8px; color: var(--ink); font-size: clamp(34px, 5vw, 66px); line-height: .98; letter-spacing: 0; }}
    h2 {{ margin-bottom: 14px; color: var(--ink); font-size: 22px; line-height: 1.18; letter-spacing: 0; }}
    h3 {{ margin-bottom: 8px; color: var(--ink); font-size: 18px; line-height: 1.25; letter-spacing: 0; }}
    p {{ margin-bottom: 12px; line-height: 1.5; }}
    .shell {{ width: min(1280px, 100%); margin: 0 auto; padding: 28px; }}
    .topbar {{ display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 20px; align-items: end; margin-bottom: 22px; padding-bottom: 18px; border-bottom: 1px solid var(--line); }}
    .eyebrow {{ color: var(--blue); font-size: 12px; font-weight: 900; letter-spacing: .09em; text-transform: uppercase; }}
    .meta {{ color: var(--muted); font-size: 13px; line-height: 1.5; text-align: right; }}
    .layout {{ display: grid; grid-template-columns: minmax(0, 1fr) 330px; gap: 18px; align-items: start; }}
    .main {{ display: grid; gap: 18px; min-width: 0; }}
    .side {{ position: sticky; top: 18px; display: grid; gap: 14px; min-width: 0; }}
    .hero, .panel, .side-panel, .finding, .report-row {{ border: 1px solid var(--line); border-radius: var(--radius); background: var(--paper); box-shadow: var(--shadow); }}
    .hero {{ padding: 24px; border-top: 5px solid var(--blue); }}
    .hero-grid {{ display: grid; grid-template-columns: minmax(0, 1fr); gap: 18px; align-items: start; }}
    .answer {{ margin-bottom: 14px; color: var(--ink); font-size: clamp(25px, 3.2vw, 42px); line-height: 1.06; font-weight: 900; letter-spacing: 0; overflow-wrap: anywhere; }}
    .finding-blocks {{ display: grid; gap: 14px; margin-top: 18px; }}
    .finding-block {{ border: 1px solid var(--line); border-radius: var(--radius); background: var(--soft); padding: 14px; }}
    .finding-block h3 {{ margin-bottom: 6px; font-size: 15px; }}
    .finding-block p {{ margin-bottom: 0; }}
    .panel, .side-panel {{ padding: 20px; }}
    .section-head {{ display: flex; justify-content: space-between; gap: 12px; align-items: flex-start; margin-bottom: 14px; }}
    .finding-list {{ display: grid; gap: 12px; }}
    .finding {{ display: grid; grid-template-columns: 120px minmax(0, 1fr); gap: 16px; padding: 16px; box-shadow: none; }}
    .rank {{ display: grid; align-content: start; gap: 8px; }}
    .rank strong {{ width: fit-content; border-radius: var(--radius); background: var(--ink); color: #fff; padding: 8px 10px; font-size: 12px; line-height: 1; }}
    .rank span {{ color: var(--muted); font-size: 12px; line-height: 1.35; }}
    .recommendation {{ border-left: 4px solid var(--blue); border-radius: 0 var(--radius) var(--radius) 0; background: var(--blue-soft); padding: 10px 12px; color: var(--ink); font-weight: 760; }}
    .tags {{ display: flex; flex-wrap: wrap; gap: 6px; margin: 10px 0 0; }}
    .pill {{ min-height: 26px; display: inline-flex; align-items: center; border-radius: 999px; padding: 0 9px; font-size: 12px; font-weight: 850; white-space: nowrap; }}
    .pill.green {{ background: var(--green-soft); color: var(--green); }}
    .pill.amber {{ background: var(--amber-soft); color: var(--amber); }}
    .pill.red {{ background: var(--red-soft); color: var(--red); }}
    .pill.blue {{ background: var(--blue-soft); color: var(--blue); }}
    .pill.violet {{ background: var(--violet-soft); color: var(--violet); }}
    .pill.neutral {{ background: #eef2f8; color: #475467; }}
    details {{ margin-top: 12px; border-top: 1px solid var(--line); padding-top: 10px; }}
    summary {{ width: fit-content; color: var(--blue); cursor: pointer; font-weight: 850; }}
    summary:focus-visible, a:focus-visible {{ outline: 3px solid rgba(0, 61, 255, .24); outline-offset: 3px; }}
    .proof-grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; margin-top: 10px; }}
    .proof {{ border: 1px solid var(--line); border-radius: var(--radius); background: var(--soft); padding: 10px; font-size: 13px; line-height: 1.4; }}
    .proof span {{ display: block; margin-bottom: 4px; color: var(--muted); font-size: 11px; font-weight: 900; letter-spacing: .06em; text-transform: uppercase; }}
    .quality-list, .report-list {{ display: grid; gap: 9px; }}
    .limit-stats {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; margin-bottom: 12px; }}
    .limit-stat {{ border: 1px solid var(--line); border-radius: var(--radius); background: var(--soft); padding: 10px; }}
    .limit-stat strong {{ display: block; color: var(--ink); font-size: 22px; line-height: 1; }}
    .limit-stat span {{ display: block; margin-top: 5px; color: var(--muted); font-size: 12px; line-height: 1.35; }}
    .quality-row {{ display: grid; grid-template-columns: 28px minmax(0, 1fr); gap: 10px; border: 1px solid var(--line); border-radius: var(--radius); background: var(--soft); padding: 10px; }}
    .mark {{ width: 28px; height: 28px; display: grid; place-items: center; border-radius: 50%; background: var(--green-soft); color: var(--green); font-weight: 900; }}
    .mark.warn {{ background: var(--amber-soft); color: var(--amber); }}
    .quality-row strong {{ display: block; color: var(--ink); font-size: 14px; }}
    .quality-row span {{ display: block; margin-top: 3px; color: var(--muted); font-size: 12px; line-height: 1.35; }}
    .report-row {{ display: grid; grid-template-columns: 92px minmax(0, 1fr) auto; gap: 12px; align-items: start; padding: 12px; box-shadow: none; }}
    .report-row time {{ color: var(--muted); font-size: 12px; font-weight: 850; }}
    .report-row b {{ display: block; color: var(--ink); margin-bottom: 3px; }}
    .report-row span {{ display: block; color: var(--muted); font-size: 12px; line-height: 1.35; }}
    .note {{ margin: 12px 0 0; color: var(--muted); font-size: 12px; line-height: 1.45; }}
    @media (max-width: 980px) {{
      .layout, .hero-grid {{ grid-template-columns: 1fr; }}
      .side {{ position: static; }}
    }}
    @media (max-width: 680px) {{
      .shell {{ width: 100%; max-width: 100%; padding: 16px; }}
      .topbar, .finding, .report-row {{ grid-template-columns: 1fr; }}
      .meta {{ text-align: left; }}
      .hero, .panel, .side-panel, .finding {{ width: 100%; max-width: 100%; overflow: hidden; }}
      .proof-grid {{ grid-template-columns: 1fr; }}
      h1 {{ font-size: 34px; }}
      .answer {{ font-size: 23px; line-height: 1.12; }}
      h3 {{ font-size: 16px; }}
    }}
  </style>
</head>
<body>
  <main class="shell">
    <header class="topbar">
      <div>
        <div class="eyebrow">Algolia competitive intelligence</div>
        <h1>Competitive Brief</h1>
      </div>
      <div class="meta">
        <div>Actual archive: {covered_range}</div>
        <div>Daily reports: {daily_count} | Weekly reports: {weekly_count}</div>
        <div>Generated from archived CI briefs, not mock data</div>
      </div>
    </header>
    <div class="layout">
      <div class="main">
        <section class="hero" aria-labelledby="answer">
          <div class="hero-grid">
            <div>
              <div class="eyebrow">Primary finding</div>
              <h2 class="answer" id="answer">{primary_title}</h2>
              <div class="finding-blocks">
                <section class="finding-block"><h3>What happened</h3><p>{what}</p></section>
                <section class="finding-block"><h3>Why it matters</h3><p>{why}</p></section>
                <section class="finding-block"><h3>Recommended response</h3><p>{response}</p></section>
                <section class="finding-block"><h3>Evidence</h3><p>{evidence}</p></section>
              </div>
            </div>
          </div>
        </section>
        <section class="panel" aria-labelledby="findings-title">
          <div class="section-head">
            <div><div class="eyebrow">Intel queue</div><h2 id="findings-title">Other findings</h2></div>
            <span class="pill blue">Actual archive</span>
          </div>
          <div class="finding-list">{finding_cards}</div>
        </section>
        <section class="panel" aria-labelledby="history-title">
          <div class="section-head">
            <div><div class="eyebrow">Where this came from</div><h2 id="history-title">Report history</h2></div>
            <span class="pill neutral">Automated archive</span>
          </div>
          <div class="report-list">{report_history}</div>
        </section>
      </div>
      <aside class="side" aria-label="Data reliability">
        <section class="side-panel">
          <div class="eyebrow">Can I trust this?</div>
          <h2>Data limits</h2>
          <div class="limit-stats" aria-label="Archive coverage">
            <div class="limit-stat"><strong>{report_count}</strong><span>Archived CI briefs used</span></div>
            <div class="limit-stat"><strong>{finding_count}</strong><span>Findings surfaced</span></div>
            <div class="limit-stat"><strong>{battlecard_count}</strong><span>Battlecard updates listed</span></div>
            <div class="limit-stat"><strong>{day_span}</strong><span>Covered date range</span></div>
          </div>
          <div class="quality-list">
            <div class="quality-row"><div class="mark">✓</div><div><strong>Uses real archived briefs</strong><span>No mock findings or fake action buttons are used on this page.</span></div></div>
            <div class="quality-row"><div class="mark warn">!</div><div><strong>Public-source only</strong><span>No Gong, Salesforce, Slack, G2 paid exports, Semrush API, or internal win/loss data.</span></div></div>
            <div class="quality-row"><div class="mark warn">!</div><div><strong>Generated by Chowmes</strong><span>Last generated at {generated_at} after CI runtime artifacts were exported.</span></div></div>
          </div>
          <details>
            <summary>Show collection details</summary>
            <p class="note">Collection context is captured in the CI ledger and source health events. This public dashboard shows the executive brief first and keeps collection mechanics secondary.</p>
          </details>
        </section>
      </aside>
    </div>
  </main>
  <script>
    document.querySelectorAll("a[href]").forEach((link) => {{
      link.target = "_blank";
      link.rel = "noopener noreferrer";
    }});
  </script>
</body>
</html>
""".format(
        covered_range=escape(covered_range(reports)),
        daily_count=daily_count,
        weekly_count=weekly_count,
        primary_title=escape(headline),
        what=markdown_inline_to_html(what),
        why=markdown_inline_to_html(why),
        response=markdown_inline_to_html(response),
        evidence=render_evidence(evidence, daily_href),
        finding_cards=render_finding_cards(weekly, daily),
        report_history=render_report_history(reports),
        report_count=len(reports),
        finding_count=finding_count,
        battlecard_count=len(battlecard_updates),
        day_span=escape(day_span(reports)),
        generated_at=escape(generated_at),
    )


def export_dashboard_assets(output_root: Path, repo_root: Path, generated_at: Optional[str] = None) -> Dict[str, object]:
    output_root = Path(output_root)
    repo_root = Path(repo_root)
    public_dir = repo_root / "apps" / "dashboard" / "public"
    data_dir = public_dir / "data"
    public_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)

    reports = report_files(output_root)
    daily = latest_report(reports, "daily")
    weekly = latest_report(reports, "weekly")
    generated = generated_at or datetime.now().replace(microsecond=0).isoformat()

    copy_archive(reports, public_dir)
    copy_latest(daily, public_dir, "latest-daily.md")
    copy_latest(weekly, public_dir, "latest-weekly.md")
    html_text = render_dashboard_html(reports, daily, weekly, generated)
    (public_dir / "index.html").write_text(html_text)

    payload: Dict[str, object] = {
        "generated_at": generated,
        "archive_range": covered_range(reports),
        "report_count": len(reports),
        "latest_daily": {"date": daily.date, "path": "latest-daily.md"} if daily else None,
        "latest_weekly": {"date": weekly.date, "path": "latest-weekly.md"} if weekly else None,
        "reports": [
            {"date": report.date, "cadence": report.cadence, "path": "archive/%s" % report.path.name}
            for report in sorted(reports, key=lambda item: (item.date, item.cadence), reverse=True)
        ],
    }
    (data_dir / "latest.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return payload


def run_git(repo_root: Path, args: Sequence[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=str(repo_root),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=check,
    )


def git_has_dashboard_changes(repo_root: Path) -> bool:
    result = run_git(repo_root, ["status", "--porcelain", "--", "apps/dashboard/public"], check=True)
    return bool(result.stdout.strip())


def publish_git(repo_root: Path, message: str) -> bool:
    if not git_has_dashboard_changes(repo_root):
        print("Dashboard publish: no Git changes.")
        return False
    run_git(repo_root, ["add", "apps/dashboard/public"], check=True)
    env = os.environ.copy()
    env.setdefault("GIT_AUTHOR_NAME", "Chowmes CI")
    env.setdefault("GIT_AUTHOR_EMAIL", "chowmes-ci@users.noreply.github.com")
    env.setdefault("GIT_COMMITTER_NAME", env["GIT_AUTHOR_NAME"])
    env.setdefault("GIT_COMMITTER_EMAIL", env["GIT_AUTHOR_EMAIL"])
    subprocess.run(
        ["git", "commit", "-m", message],
        cwd=str(repo_root),
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=True,
    )
    run_git(repo_root, ["push", "origin", "main"], check=True)
    print("Dashboard publish: committed and pushed.")
    return True


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export and optionally publish dashboard assets")
    parser.add_argument("--output-root", default=os.environ.get("COMPETITIVE_RESEARCH_OUTPUT_ROOT"))
    parser.add_argument("--repo-root", default=os.environ.get("ALGOLIA_CI_REPO_ROOT"))
    parser.add_argument("--generated-at")
    parser.add_argument("--commit-message", default="Update CI dashboard from Chowmes run")
    parser.add_argument("--no-git", action="store_true", help="Only export files; do not commit or push")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    if not args.output_root:
        print("COMPETITIVE_RESEARCH_OUTPUT_ROOT or --output-root is required", file=sys.stderr)
        return 2
    if not args.repo_root:
        print("ALGOLIA_CI_REPO_ROOT or --repo-root is required", file=sys.stderr)
        return 2
    payload = export_dashboard_assets(
        output_root=Path(args.output_root),
        repo_root=Path(args.repo_root),
        generated_at=args.generated_at,
    )
    print("Dashboard assets exported: %s reports" % payload["report_count"])
    if not args.no_git:
        publish_git(Path(args.repo_root), args.commit_message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
