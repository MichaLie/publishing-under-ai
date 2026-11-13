#!/usr/bin/env python3
"""Render content/essay.md into docs/essay.html (clean light sans-serif essay) and docs/essay.md."""

from __future__ import annotations

import html
from pathlib import Path
import re
import yaml


def canonical_url(src: dict) -> str:
    if src.get("doi"):
        return f"https://doi.org/{src['doi']}"
    if src.get("arxiv_id"):
        return f"https://arxiv.org/abs/{src['arxiv_id']}"
    return str(src["url"])


def inline_md_to_html(text: str, src_by_id: dict[str, dict]) -> str:
    """Convert inline Markdown (**bold**, *italic*, `code`, [[id|label]], [label](url)) safely."""
    tokens: list[str] = []

    def stash(fragment: str) -> str:
        idx = len(tokens)
        tokens.append(fragment)
        return f"\x00TOK{idx}\x00"

    # 1. Inline code spans first
    def repl_code(m: re.Match) -> str:
        return stash(f"<code>{html.escape(m.group(1))}</code>")

    work = re.sub(r"`([^`]+)`", repl_code, text)

    # 2. Validated [[source-id|label]] citations
    def repl_cite(m: re.Match) -> str:
        cid, label_raw = m.group(1), m.group(2)
        src = src_by_id[cid]
        href = html.escape(canonical_url(src), quote=True)
        tip = html.escape(f"{src['authors']} ({src['year']}) — {src['venue']}", quote=True)
        label_html = format_emphasis(html.escape(label_raw))
        return stash(f'<a href="{href}" target="_blank" rel="noopener" title="{tip}">{label_html}</a>')

    work = re.sub(r"\[\[([a-z0-9-]+)\|([^\]]+)\]\]", repl_cite, work)

    # 3. Standard Markdown links [label](href)
    def repl_link(m: re.Match) -> str:
        label_raw, href_raw = m.group(1), m.group(2)
        href = html.escape(href_raw, quote=True)
        ext = ' target="_blank" rel="noopener"' if href_raw.startswith(("http://", "https://")) else ""
        label_html = format_emphasis(html.escape(label_raw))
        return stash(f'<a href="{href}"{ext}>{label_html}</a>')

    work = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", repl_link, work)

    # 4. Escape remaining plain text (except explicit inline <em>/<strong>/<a>/<code> inside colophon if any)
    work = html.escape(work)
    work = format_emphasis(work)

    # Restore stashed HTML fragments
    for idx, frag in enumerate(tokens):
        work = work.replace(f"\x00TOK{idx}\x00", frag)
    return work


def format_emphasis(escaped_txt: str) -> str:
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped_txt)
    s = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", s)
    return s


def slugify(heading: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", heading.lower()).strip("-")
    return s or "section"


def build_markdown_export(fm: dict, body: str, src_by_id: dict[str, dict]) -> str:
    """Produce clean, portable Markdown (docs/essay.md) with all [[id|label]] resolved to URLs."""
    def repl_cite_md(m: re.Match) -> str:
        cid, label = m.group(1), m.group(2)
        return f"[{label}]({canonical_url(src_by_id[cid])})"

    out = re.sub(r"\[\[([a-z0-9-]+)\|([^\]]+)\]\]", repl_cite_md, body)
    # Strip layout wrapper divs cleanly for portable Substack/GitHub Markdown
    out = re.sub(r"</?div[^>]*>\n?", "", out)
    out = out.replace("<strong>", "**").replace("</strong>", "**")
    out = out.replace("<em>", "*").replace("</em>", "*")
    out = re.sub(r'<a href="([^"]+)"><code>([^<]+)</code></a>', r"[`\2`](\1)", out)
    out = re.sub(r"<code>([^<]+)</code>", r"`\1`", out)

    header = (
        f"# {fm['title']}\n\n"
        f"*{fm['subtitle']}*\n\n"
        f"**{fm['authors']}** · {fm['byline_note']}\n\n---\n\n"
    )
    return header + out.strip() + "\n"


def render_essay(essay_path: Path, docs_dir: Path, src_by_id: dict[str, dict], total_sources: int) -> None:
    raw = essay_path.read_text(encoding="utf-8")
    _, fm_raw, body = raw.split("---\n", 2)
    fm = yaml.safe_load(fm_raw)

    # 1. Write portable Markdown export
    md_export = build_markdown_export(fm, body, src_by_id)
    (docs_dir / "essay.md").write_text(md_export, encoding="utf-8")

    # 2. Parse blocks into clean semantic HTML
    lines = body.strip().splitlines()
    html_blocks: list[str] = []
    para_buf: list[str] = []
    ul_buf: list[str] = []
    ol_buf: list[str] = []
    in_colophon = False
    colophon_buf: list[str] = []

    def flush_para() -> None:
        if not para_buf:
            return
        joined = " ".join(x.strip() for x in para_buf).strip()
        para_buf.clear()
        if joined.startswith("*Explore ") and joined.endswith("*"):
            inner = inline_md_to_html(joined[1:-1], src_by_id)
            html_blocks.append(f'<p class="obs-jump">{inner}</p>')
        else:
            html_blocks.append(f"<p>{inline_md_to_html(joined, src_by_id)}</p>")

    def flush_lists() -> None:
        if ul_buf:
            items = "".join(f"<li>{inline_md_to_html(it, src_by_id)}</li>" for it in ul_buf)
            html_blocks.append(f"<ul>{items}</ul>")
            ul_buf.clear()
        if ol_buf:
            items = "".join(f"<li>{inline_md_to_html(it, src_by_id)}</li>" for it in ol_buf)
            html_blocks.append(f"<ol>{items}</ol>")
            ol_buf.clear()

    for line in lines:
        stripped = line.strip()

        if stripped == '<div class="colophon">':
            flush_para()
            flush_lists()
            in_colophon = True
            continue
        if in_colophon:
            if stripped == "</div>":
                in_colophon = False
                col_txt = " ".join(colophon_buf)
                # Resolve [[id|label]] inside colophon HTML while keeping clean tags
                def repl_col_cite(m: re.Match) -> str:
                    cid, lbl = m.group(1), m.group(2)
                    s = src_by_id[cid]
                    return f'<a href="{html.escape(canonical_url(s), quote=True)}" target="_blank" rel="noopener">{lbl}</a>'

                col_txt = re.sub(r"\[\[([a-z0-9-]+)\|([^\]]+)\]\]", repl_col_cite, col_txt)
                html_blocks.append(f'<aside class="colophon" aria-label="Authorship colophon">{col_txt}</aside>')
                colophon_buf.clear()
            else:
                colophon_buf.append(stripped)
            continue

        if stripped in ('<div class="compass-grid">', '<div class="compass-col">', "</div>"):
            flush_para()
            flush_lists()
            html_blocks.append(stripped)
            continue

        if not stripped:
            flush_para()
            flush_lists()
            continue

        if stripped == "---":
            flush_para()
            flush_lists()
            html_blocks.append("<hr>")
            continue

        if stripped.startswith("## "):
            flush_para()
            flush_lists()
            h_txt = stripped[3:].strip()
            html_blocks.append(f'<h2 id="{slugify(h_txt)}">{inline_md_to_html(h_txt, src_by_id)}</h2>')
            continue

        if stripped.startswith("### "):
            flush_para()
            flush_lists()
            h_txt = stripped[4:].strip()
            html_blocks.append(f'<h3 id="{slugify(h_txt)}">{inline_md_to_html(h_txt, src_by_id)}</h3>')
            continue

        if stripped.startswith("* "):
            flush_para()
            if ol_buf:
                flush_lists()
            ul_buf.append(stripped[2:].strip())
            continue

        m_ol = re.match(r"^\d+\.\s+(.*)$", stripped)
        if m_ol:
            flush_para()
            if ul_buf:
                flush_lists()
            ol_buf.append(m_ol.group(1).strip())
            continue

        flush_lists()
        para_buf.append(stripped)

    flush_para()
    flush_lists()

    body_html = "\n".join(html_blocks)
    title_esc = html.escape(fm["title"])
    sub_esc = html.escape(fm["subtitle"])
    authors_esc = html.escape(fm["authors"])
    note_esc = html.escape(fm["byline_note"])

    page = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title_esc}</title>
<meta name="description" content="{sub_esc}">
<link rel="canonical" href="https://michalie.github.io/publishing-under-ai/essay.html">
<meta property="og:type" content="article">
<meta property="og:title" content="{title_esc}">
<meta property="og:description" content="{sub_esc}">
<meta property="og:url" content="https://michalie.github.io/publishing-under-ai/essay.html">
<meta property="og:image" content="https://michalie.github.io/publishing-under-ai/social-card.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
<style>
/* Minimalist light sans-serif academic essay layout (zero external CDNs, no visual clutter) */
:root {{
  --bg: #FFFFFF;
  --surface: #F8FAFC;
  --ink: #18181B;
  --body: #27272A;
  --muted: #64748B;
  --rule: #E4E4E7;
  --link-line: #94A3B8;
  --link-hover: #1D4ED8;
  --f-sans: -apple-system, BlinkMacSystemFont, "Inter", "Segoe UI", "IBM Plex Sans", Roboto, Helvetica, Arial, sans-serif;
  --f-mono: ui-monospace, SFMono-Regular, "IBM Plex Mono", Menlo, Consolas, monospace;
}}
* {{ box-sizing: border-box; }}
html {{ scroll-behavior: smooth; }}
body {{
  margin: 0;
  background: var(--bg);
  color: var(--body);
  font: 17.5px/1.72 var(--f-sans);
  -webkit-font-smoothing: antialiased;
}}
.topbar {{
  max-width: 740px;
  margin: 0 auto;
  padding: 20px 24px 14px;
  border-bottom: 1px solid var(--rule);
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  font-size: 0.86rem;
  color: var(--muted);
}}
.topbar a {{
  color: var(--ink);
  text-decoration: none;
  font-weight: 500;
}}
.topbar a:hover {{
  color: var(--link-hover);
  text-decoration: underline;
}}
.topbar .right-links {{
  display: flex;
  gap: 16px;
  align-items: center;
}}
main.article {{
  max-width: 680px;
  margin: 0 auto;
  padding: 44px 24px 88px;
}}
header.post-head {{
  margin-bottom: 34px;
}}
h1 {{
  color: var(--ink);
  font-size: clamp(1.85rem, 3.6vw, 2.38rem);
  font-weight: 700;
  line-height: 1.18;
  letter-spacing: -0.024em;
  margin: 0 0 14px;
}}
.subtitle {{
  font-size: 1.15rem;
  line-height: 1.52;
  color: var(--muted);
  font-weight: 400;
  margin: 0 0 22px;
}}
.byline {{
  padding-top: 16px;
  border-top: 1px solid var(--rule);
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 4px 16px;
  font-size: 0.9rem;
}}
.byline strong {{
  color: var(--ink);
  font-weight: 600;
}}
.byline span {{
  color: var(--muted);
}}
h2 {{
  color: var(--ink);
  font-size: 1.42rem;
  font-weight: 650;
  line-height: 1.28;
  letter-spacing: -0.015em;
  margin: 42px 0 14px;
}}
h3 {{
  color: var(--ink);
  font-size: 1.06rem;
  font-weight: 650;
  line-height: 1.35;
  margin: 0 0 12px;
}}
p {{
  margin: 0 0 1.22em;
}}
ul, ol {{
  margin: 0 0 1.35em;
  padding-left: 1.35em;
}}
li {{
  margin-bottom: 0.65em;
}}
li strong, p strong {{
  color: var(--ink);
  font-weight: 600;
}}
a {{
  color: var(--ink);
  text-decoration: underline;
  text-decoration-color: var(--link-line);
  text-decoration-thickness: 1px;
  text-underline-offset: 3px;
  transition: color 0.12s, text-decoration-color 0.12s;
}}
a:hover {{
  color: var(--link-hover);
  text-decoration-color: var(--link-hover);
}}
code {{
  font-family: var(--f-mono);
  font-size: 0.86em;
  background: var(--surface);
  padding: 2px 5px;
  border-radius: 4px;
}}
hr {{
  border: 0;
  border-top: 1px solid var(--rule);
  margin: 38px 0;
}}
p.obs-jump {{
  font-size: 0.92rem;
  color: var(--muted);
  background: var(--surface);
  border-left: 2px solid #CBD5E1;
  padding: 10px 14px;
  border-radius: 0 6px 6px 0;
  margin-top: 18px;
}}
.compass-grid {{
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 18px;
  margin: 24px -36px 28px;
}}
.compass-col {{
  background: var(--surface);
  border: 1px solid var(--rule);
  border-radius: 8px;
  padding: 20px 20px 12px;
  font-size: 0.94rem;
  line-height: 1.6;
}}
.compass-col ol {{
  padding-left: 1.2em;
  margin-bottom: 0.4em;
}}
.compass-col li {{
  margin-bottom: 0.75em;
}}
aside.colophon {{
  margin-top: 36px;
  padding: 18px 20px;
  background: var(--surface);
  border: 1px solid var(--rule);
  border-radius: 8px;
  font-size: 0.88rem;
  line-height: 1.62;
  color: var(--muted);
}}
aside.colophon strong {{
  color: var(--ink);
}}
footer.foot {{
  margin-top: 48px;
  padding-top: 18px;
  border-top: 1px solid var(--rule);
  display: flex;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 10px;
  font-size: 0.84rem;
  color: var(--muted);
}}
@media (max-width: 780px) {{
  body {{ font-size: 16.5px; }}
  .compass-grid {{
    grid-template-columns: 1fr;
    margin-inline: 0;
  }}
}}
</style>
</head>
<body>

<nav class="topbar" aria-label="Site navigation">
  <a href="index.html">← Interactive Observatory ({total_sources} source records)</a>
  <div class="right-links">
    <a href="index.html#fault-lines">7 Fault Lines</a>
    <a href="index.html#models">8 Models</a>
    <a href="essay.md">Markdown (.md)</a>
  </div>
</nav>

<main class="article">
  <header class="post-head">
    <h1>{title_esc}</h1>
    <p class="subtitle">{sub_esc}</p>
    <div class="byline">
      <strong>{authors_esc}</strong>
      <span>{note_esc}</span>
    </div>
  </header>

  {body_html}

  <footer class="foot">
    <div>Part of <a href="index.html">Publishing Under AI (2025–2026)</a> · <a href="https://github.com/MichaLie/publishing-under-ai" target="_blank" rel="noopener">GitHub</a> · <a href="https://github.com/MichaLie/publishing-under-ai/issues" target="_blank" rel="noopener">Suggest a source or a correction</a></div>
    <div>Siblings: <a href="https://michalie.github.io/journal-ai-policies/" target="_blank" rel="noopener">Journal AI Policies</a> · <a href="https://michalie.github.io/agent-risk-atlas/" target="_blank" rel="noopener">Agent Risk Atlas</a></div>
  </footer>
</main>

</body>
</html>
"""
    (docs_dir / "essay.html").write_text(page, encoding="utf-8")
