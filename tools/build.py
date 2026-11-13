"""Static builder for 'Publishing Under AI (2025–2026): A Fault-Line Observatory'.

Validates YAML records via tools/validate.py, computes all counts and 5-bin fault-line
distributions dynamically, and writes:
  - docs/index.html  (Editorial Observatory v3 — offline-ready, zero external CDNs)
  - docs/essay.html  (Companion essay HTML via tools/render_essay.py)
  - docs/essay.md    (Portable Markdown export of the companion essay)
  - docs/data.json   (machine-readable dataset; records CC0, quoted excerpts remain their authors')
"""

from __future__ import annotations

from datetime import datetime, timezone
import html
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import render_essay  # noqa: E402
import validate  # noqa: E402

DATA = ROOT / "data"
DOCS = ROOT / "docs"

STAGE_META = [
    {
        "id": "writing",
        "num": "01",
        "label": "Drafting & Framing",
        "short": "Drafting",
        "hook": "Fluency stops signaling effort; prose-thinking meets executable workflows.",
    },
    {
        "id": "citations",
        "num": "02",
        "label": "Citations & Synthesis",
        "short": "Citations",
        "hook": "Phantom DOIs and shallow secondary loops enter submitted bibliographies.",
    },
    {
        "id": "submission_triage",
        "num": "03",
        "label": "Submission & Triage",
        "short": "Desk Triage",
        "hook": "Zero-cost submissions strain editors; disclosure mandates decouple from practice.",
    },
    {
        "id": "peer_review",
        "num": "04",
        "label": "Peer Review",
        "short": "Peer Review",
        "hook": "Shadow AI reviewing, hidden prompt injection, and bounded 'Reviewer 4' proposals.",
    },
    {
        "id": "post_pub_audit",
        "num": "05",
        "label": "Post-Pub Audit",
        "short": "Post-Pub Audit",
        "hook": "Archive-scale error screeners collide with false-positive due process.",
    },
    {
        "id": "publishing_model",
        "num": "06",
        "label": "Venue Architecture",
        "short": "Venues",
        "hook": "Hard submission caps vs. preprints, runnable MCP papers, and journal exits.",
    },
]

# Crisp lead figures taken from the shockwave studies for visual scan speed
SHOCK_FIGURES = {
    "SW1": ("≥13.5% · 89%", "2024 abstracts vs. Dec 2025 PMC"),
    "SW2": ("2.1M papers", "Signal inversion & style compression"),
    "SW3": ("6.3 → 23.0", "Papers with a flagged ref, per 10,000"),
    "SW4": ("0.1% public", "76 / 75,172 full texts + hard caps"),
    "SW5": ("50.5% accuracy", "Readers: authentic vs. AI-manipulated"),
    "SW6": ("12% – 21%", "Classifier-flagged reviews, three corpora"),
    "SW7": ("53–96% · 26/30", "Bounded RCT & editor-pair tests"),
    "SW8": ("53.7% → 81.5%", "LLM auditor with logs + code added"),
}

GENRE_GROUPS = {
    "empirical_study": ("empirical", "Empirical study"),
    "preprint": ("empirical", "Preprint"),
    "editorial_comment": ("editorial", "Editorial / Comment"),
    "journal_news_feature": ("editorial", "Journal news"),
    "perspective_essay": ("editorial", "Perspective"),
    "blog_essay": ("discourse", "Essay / Blog"),
    "community_thread_writeup": ("discourse", "Community pulse"),
    "social_post": ("social", "X / LinkedIn"),
    "watchdog_investigation": ("sleuth", "Forensic / Sleuth"),
    "live_experiment": ("experiment", "Live pilot"),
    "institutional_experiment": ("experiment", "Institutional policy"),
}

DISCIPLINE_LABELS = {
    "biomed_lifesci": "Biomed & Life Sci",
    "cs_ml": "CS & ML",
    "cross_disciplinary": "Cross-disciplinary",
}

MATURITY_LABELS = {
    "piloted_at_scale": "Piloted at scale",
    "one_large_trial_plus_proposals": "One large trial; pilots & proposals",
    "research_prototypes": "Prototypes & early tools",
    "deployed_commercial_and_academic": "Deployed in screening",
    "proposed_and_selectively_piloted": "Selectively piloted",
    "early_pilots_and_proposals": "Early pilots & proposals",
    "growing_niche_adoption": "Growing niche adoption",
    "live_ecosystem": "Live ecosystem",
    "live_experiment_2025_2026": "Live 2025–2026 experiment",
    "bold_institutional_experiments": "Institutional experiment",
}

PROVENANCE_LABELS = {
    "arxiv_api": "arXiv abstract",
    "europepmc_api": "Europe PMC",
    "europepmc_fulltext": "Europe PMC full text",
    "europepmc_abstract": "Europe PMC abstract",
    "crossref_abstract": "Crossref abstract",
    "crossref_plus_open_page": "Publisher page",
    "live_html": "Live HTML",
    "publisher_html": "Official policy HTML",
    "fulltext_pdf": "Full text",
    "rss_feed": "Publisher feed",
    "browser_dom": "Primary post",
    "publisher_preview_paragraph": "Publisher preview (full text behind subscription)",
    "crossref_metadata_only": "Metadata",
    "crossref_api": "Crossref metadata",
}

BIN_HEADERS = [
    (-2, "Argues ◀", "−2"),
    (-1, "Leans ◀", "−1"),
    (0, "No side", "0"),
    (1, "Leans ▶", "+1"),
    (2, "Argues ▶", "+2"),
]


def wrap_quote(text: str) -> str:
    """Wrap an excerpt in quotation marks unless it already opens with one."""
    t = str(text or "")
    return t if t[:1] in "“\"‘" else f"“{t}”"


def esc(val: object) -> str:
    return html.escape(str(val or ""), quote=True)


COMPOUND_SURNAMES = ("La Rosa", "Di Carlo", "El Khoury", "Van de Rijt")
DEGREES = {"MD", "PhD", "MSc", "MPH", "SM", "Jr", "Jr.", "III"}


def _surname_of(person: str) -> str:
    p = person.strip()
    for cs in COMPOUND_SURNAMES:
        if p.endswith(cs):
            return cs
    words = [w.rstrip(",") for w in p.split() if w.rstrip(",") not in DEGREES]
    return words[-1] if len(words) >= 2 else (words[0] if words else p)


def short_cite(src: dict, compact_year: bool = False) -> str:
    authors = str(src.get("authors", "")).strip()
    yr = str(src.get("year", ""))
    yr_fmt = f"’{yr[-2:]}" if (compact_year and len(yr) == 4) else f"({yr})"
    if authors.startswith("American Journal of Political Science"):
        return f"AJPS Editors {yr_fmt}"
    if authors.lower() == "editorial":
        v = str(src.get("venue", "Editorial")).replace("Nature Nanotechnology", "Nat. Nanotech.")
        return f"{v} {yr_fmt}"
    if authors.startswith("ICLR 2026"):
        return f"ICLR Chairs {yr_fmt}"

    no_parens = re.sub(r"\s*\([^)]*\)", "", authors).strip()
    no_parens = re.sub(r"\s+via\s+.*$", "", no_parens, flags=re.I).strip()
    parts = [
        p.strip()
        for p in re.split(r",|\band\b|&", no_parens)
        if p.strip() and "et al" not in p.lower() and p.strip() not in DEGREES
    ]
    has_etal = "et al" in authors.lower()
    if not parts:
        first_tok = authors.split("(")[0].strip()[:18]
        return f"{first_tok} {yr_fmt}"

    p0 = parts[0]
    org_prefixes = (
        "nature", "elife", "arxiv", "gptzero", "pangram", "stanford",
        "ai research", "análise", "asimov", "anthropic", "news from",
    )
    if p0.lower().startswith(org_prefixes) or "@" in p0:
        lbl = p0[:20].rstrip()
    else:
        lbl = _surname_of(p0)
        if not has_etal and len(parts) == 2:
            s2 = _surname_of(parts[1]).replace("Program Chairs", "Chairs")
            if len(lbl) + len(s2) <= 19:
                return f"{lbl} & {s2} {yr_fmt}"
        if has_etal or len(parts) >= 2:
            return f"{lbl} et al. {yr_fmt}"

    dt = str(src.get("date") or "")
    if lbl in ("Thorp", "Gibney", "Naddaf") and len(dt) >= 7:
        months = {
            "01": "Jan", "02": "Feb", "03": "Mar", "04": "Apr", "05": "May", "06": "Jun",
            "07": "Jul", "08": "Aug", "09": "Sep", "10": "Oct", "11": "Nov", "12": "Dec",
        }
        mo = months.get(dt[5:7], "")
        if mo:
            return f"{lbl} ({mo} ’{yr[-2:]})" if compact_year else f"{lbl} ({mo} {yr})"
    return f"{lbl} {yr_fmt}"


def build() -> int:
    rc = validate.main()
    if rc != 0:
        return rc

    fault_lines = validate.load_yaml(DATA / "fault_lines.yml")
    models = validate.load_yaml(DATA / "models.yml")
    sources = validate.load_yaml(DATA / "sources.yml")
    shockwaves = validate.load_yaml(DATA / "shockwaves.yml") if (DATA / "shockwaves.yml").exists() else []

    sources = sorted(
        sources,
        key=lambda s: (str(s.get("date") or s.get("year") or ""), s.get("id", "")),
        reverse=True,
    )
    src_by_id = {s["id"]: s for s in sources}

    total_sources = len(sources)
    genre_counts = {"empirical": 0, "editorial": 0, "discourse": 0, "sleuth": 0, "experiment": 0, "social": 0}
    for s in sources:
        genre_counts[GENRE_GROUPS[s["source_type"]][0]] += 1

    n_empirical = genre_counts["empirical"]
    n_editorial = genre_counts["editorial"]
    n_discourse_all = genre_counts["discourse"] + genre_counts["sleuth"] + genre_counts["experiment"]
    n_social = genre_counts["social"]
    n_verbatim = sum(1 for s in sources if s.get("verbatim_excerpt"))

    stage_counts = {st["id"]: 0 for st in STAGE_META}
    for s in sources:
        for st in s.get("pipeline_stages", []):
            if st in stage_counts:
                stage_counts[st] += 1

    built_human = datetime.now().strftime("%d %b %Y")
    latest_src = max(str(s.get("date") or s.get("year") or "") for s in sources)
    try:
        _d = datetime.strptime(latest_src[:10], "%Y-%m-%d")
        latest_human = f"{_d.day} {_d:%b %Y}"
    except ValueError:
        latest_human = latest_src

    # Stacked genre composition bar for Hero card 1
    genre_bar_segs = []
    for gk, glbl in [
        ("empirical", "Empirical & preprints"),
        ("editorial", "Editorials & comments"),
        ("discourse", "Essays & blogs"),
        ("sleuth", "Forensic & sleuths"),
        ("experiment", "Live pilots & policies"),
        ("social", "X & LinkedIn"),
    ]:
        pct = genre_counts[gk] / total_sources * 100.0
        genre_bar_segs.append(
            f'<span class="gbar-seg dot-{gk}" style="width:{pct:.1f}%" title="{glbl}: {genre_counts[gk]}"></span>'
        )

    # 1. Pipeline Stage Cards
    stage_cards_html = []
    for st in STAGE_META:
        sid = st["id"]
        stage_cards_html.append(
            f"""<button type="button" class="stage-tile" data-stage-jump="{esc(sid)}" aria-label="Filter ledger by {esc(st['label'])}">
              <div class="st-top">
                <span class="st-num">{esc(st['num'])}</span>
                <span class="st-cnt">{stage_counts[sid]} sources</span>
              </div>
              <div class="st-title">{esc(st['label'])}</div>
              <p class="st-hook">{esc(st['hook'])}</p>
            </button>"""
        )

    # 2. Shockwave Data Cards (2-col elevated cards with bold callout metrics)
    shock_cards_html = []
    for sw in shockwaves:
        swid = sw["id"]
        fig_big, fig_sub = SHOCK_FIGURES.get(swid, (swid, sw.get("signal_type", "")))
        stage_label = next((x["short"] for x in STAGE_META if x["id"] == sw.get("stage")), sw.get("stage", ""))
        pills = []
        for ref_id in sw.get("evidence_ids", []):
            if ref_id in src_by_id:
                sref = src_by_id[ref_id]
                gclass, _ = GENRE_GROUPS[sref["source_type"]]
                pills.append(
                    f'<button type="button" class="cite-chip" data-open-src="{esc(ref_id)}">'
                    f'<span class="gdot dot-{esc(gclass)}"></span>{esc(short_cite(sref))}</button>'
                )
        shock_cards_html.append(
            f"""<article class="sw-card" id="{esc(swid)}">
              <div class="sw-top">
                <div class="sw-stat">
                  <span class="sw-big">{esc(fig_big)}</span>
                  <span class="sw-sub">{esc(fig_sub)}</span>
                </div>
                <span class="stage-tag">{esc(swid)} · {esc(stage_label)}</span>
              </div>
              <h3>{esc(sw.get('headline'))}</h3>
              <p>{esc(sw.get('detail'))}</p>
              <div class="chip-row">{''.join(pills)}</div>
            </article>"""
        )

    # 3. Seven Fault Lines: Diverging Tug-of-War Summary + Full Cards (capped columns with '+N more')
    tug_rows_html = []
    fl_cards_html = []
    VISIBLE_CAP = 6

    for fl in fault_lines:
        fid = fl["id"]
        bins: dict[int, list[dict]] = {-2: [], -1: [], 0: [], 1: [], 2: []}
        for s in sources:
            pos = (s.get("positions") or {}).get(fid)
            if pos in bins:
                bins[pos].append(s)
        total_on_axis = sum(len(v) for v in bins.values())
        stage_label = next((x["short"] for x in STAGE_META if x["id"] == fl["stage"]), fl["stage"])

        segs = []
        for sc, btitle, _ in BIN_HEADERS:
            cnt = len(bins[sc])
            pct = (cnt / total_on_axis * 100.0) if total_on_axis else 20.0
            cls = {-2: "tug-a2", -1: "tug-a1", 0: "tug-0", 1: "tug-b1", 2: "tug-b2"}[sc]
            segs.append(f'<span class="tug-seg {cls}" style="width:{pct:.1f}%" title="{esc(btitle)}: {cnt}"></span>')

        cnt_a = len(bins[-2]) + len(bins[-1])
        cnt_0 = len(bins[0])
        cnt_b = len(bins[1]) + len(bins[2])

        tug_rows_html.append(
            f"""<a href="#{esc(fid)}" class="tug-row">
              <span class="tug-id">{esc(fid)}</span>
              <span class="tug-title">{esc(fl['short'])}</span>
              <span class="tug-pa">{esc(fl['pole_a']['label'])} <em>({cnt_a})</em></span>
              <span class="tug-bar" aria-hidden="true">{''.join(segs)}</span>
              <span class="tug-pb"><em>({cnt_b})</em> {esc(fl['pole_b']['label'])}</span>
              <span class="tug-tot">{total_on_axis}</span>
            </a>"""
        )

        thin_sides = []
        if not bins[-2]:
            thin_sides.append(f"◀ “{fl['pole_a']['label']}”")
        if not bins[2]:
            thin_sides.append(f"“{fl['pole_b']['label']}” ▶")
        if len(thin_sides) == 2:
            thin_note = '<p class="thin-note">No source in this set argues for either side outright (score ±2); support for both sides here is indirect.</p>'
        elif thin_sides:
            thin_note = (
                '<p class="thin-note">No source in this set argues for '
                + esc(thin_sides[0])
                + " outright (score ±2); support for that side here is indirect.</p>"
            )
        else:
            thin_note = ""

        bin_cols_html = []
        for score, btitle, sc_str in BIN_HEADERS:
            items = bins[score]
            vis_items = items[:VISIBLE_CAP]
            extra_items = items[VISIBLE_CAP:]

            def make_pill(s: dict) -> str:
                gclass, glabel = GENRE_GROUPS[s["source_type"]]
                return (
                    f'<button type="button" class="voice-pill" data-open-src="{esc(s["id"])}" '
                    f'title="{esc(s["title"])} — {esc(glabel)}">'
                    f'<span class="gdot dot-{esc(gclass)}" aria-hidden="true"></span>'
                    f'<span>{esc(short_cite(s, compact_year=True))}</span>'
                    f'</button>'
                )

            vis_html = "".join(make_pill(s) for s in vis_items)
            extra_html = ""
            if extra_items:
                extra_pills = "".join(make_pill(s) for s in extra_items)
                extra_html = (
                    f'<div class="extra-pills" hidden>{extra_pills}</div>'
                    f'<button type="button" class="more-pills-btn" data-more-cnt="{len(extra_items)}">'
                    f'+{len(extra_items)} more</button>'
                )
            empty_html = '<span class="bin-empty">—</span>' if not items else ""
            tone_cls = "col-a" if score < 0 else ("col-b" if score > 0 else "col-0")

            bin_cols_html.append(
                f"""<div class="spec-bin {tone_cls}">
                  <div class="spec-hd">
                    <span class="spec-sc">{esc(sc_str)}</span>
                    <span class="spec-name">{esc(btitle)}</span>
                    <span class="spec-n">{len(items)}</span>
                  </div>
                  <div class="spec-body">{vis_html}{extra_html}{empty_html}</div>
                </div>"""
            )

        fl_cards_html.append(
            f"""<article class="fl-card" id="{esc(fid)}">
              <div class="fl-top">
                <div>
                  <div class="fl-meta">
                    <span class="id-badge">{esc(fid)}</span>
                    <span class="stage-tag">{esc(stage_label)}</span>
                    <span class="fl-tally">{cnt_a} ◀ · {cnt_0} no side · {cnt_b} ▶</span>
                  </div>
                  <h3>{esc(fl['short'])}</h3>
                </div>
                <button type="button" class="btn-outline" data-fl-jump="{esc(fid)}">Filter ledger →</button>
              </div>
              <p class="fl-question">{esc(fl['question'])}</p>
              <div class="poles-pair">
                <div class="pole-box pole-a">
                  <div class="pole-head">◀ {esc(fl['pole_a']['label'])}</div>
                  <p>{esc(fl['pole_a']['summary'])}</p>
                </div>
                <div class="pole-box pole-b">
                  <div class="pole-head">{esc(fl['pole_b']['label'])} ▶</div>
                  <p>{esc(fl['pole_b']['summary'])}</p>
                </div>
              </div>
              {thin_note}
              <div class="spec-grid" role="group" aria-label="Mapped positions on {esc(fl['short'])}">
                {''.join(bin_cols_html)}
              </div>
              <div class="fl-hinge"><strong>Load-bearing assumption:</strong> {esc(fl['hinge'])}</div>
            </article>"""
        )

    # 4. Eight Proposed Models (Architectural Blueprint Cards)
    model_cards_html = []
    for m in models:
        mid = m["id"]
        mat_label = MATURITY_LABELS.get(m.get("maturity", ""), m.get("maturity", ""))
        linked_sources = [s for s in sources if mid in (s.get("related_models") or [])]
        src_chips = []
        for s in linked_sources[:8]:
            gclass, _ = GENRE_GROUPS[s["source_type"]]
            src_chips.append(
                f'<button type="button" class="cite-chip" data-open-src="{esc(s["id"])}">'
                f'<span class="gdot dot-{esc(gclass)}"></span>{esc(short_cite(s, compact_year=True))}</button>'
            )
        more_src_note = (
            f'<span class="more-inline">+{len(linked_sources) - 8} in ledger</span>'
            if len(linked_sources) > 8
            else ""
        )
        fl_links = [f'<a href="#{esc(fid)}" class="axis-pill">{esc(fid)}</a>' for fid in m.get("fault_lines", [])]
        ex_items = "".join(f"<li>{esc(x)}</li>" for x in m.get("examples", []))

        model_cards_html.append(
            f"""<article class="model-card" id="{esc(mid)}">
              <div class="model-top">
                <span class="id-badge">{esc(mid)}</span>
                <span class="mat-pill">{esc(mat_label)}</span>
                <div class="model-axes">{''.join(fl_links)}</div>
              </div>
              <h3>{esc(m['name'])}</h3>
              <p class="model-tagline">{esc(m['tagline'])}</p>
              <p class="model-mech"><strong>Mechanism:</strong> {esc(m['mechanism'])}</p>
              <div class="callout-pair">
                <div class="m-box m-payoff">
                  <span class="m-lbl">Target payoff</span>
                  <p>{esc(m['solves'])}</p>
                </div>
                <div class="m-box m-risk">
                  <span class="m-lbl">Where it breaks / gets gamed</span>
                  <p>{esc(m['breaks_when'])}</p>
                </div>
              </div>
              <details class="model-drawer">
                <summary>Concrete 2025–2026 pilots ({len(m.get('examples', []))}) &amp; mapped sources ({len(linked_sources)})</summary>
                <ul>{ex_items}</ul>
                {f'<div class="chip-row" style="margin-top:10px">{"".join(src_chips)}{more_src_note}</div>' if src_chips else ''}
              </details>
            </article>"""
        )

    # 5. Evidence Ledger Cards (clean 2-column grid / 1-column compact toggle)
    corpus_cards_html = []
    for s in sources:
        sid = s["id"]
        gclass, glabel = GENRE_GROUPS[s["source_type"]]
        dlabel = DISCIPLINE_LABELS[s["discipline_scope"]]
        plabel = PROVENANCE_LABELS.get(s["provenance"], s["provenance"])
        if s["provenance"] == "browser_dom" and s["source_type"] != "social_post":
            plabel = "Publisher page"
        pos_map = s.get("positions") or {}
        fl_keys = " ".join(pos_map.keys())
        stages_str = " ".join(s.get("pipeline_stages") or [])
        tags_str = " ".join(s.get("stance_tags") or [])

        pos_chips = [
            f'<a href="#{esc(fid)}" class="axis-pill" title="Position {sc:+d} on {esc(fid)}">{esc(fid)} {sc:+d}</a>'
            for fid, sc in pos_map.items()
        ]
        id_links = []
        if s.get("doi"):
            id_links.append(f'<a href="https://doi.org/{esc(s["doi"])}" target="_blank" rel="noopener">DOI ↗</a>')
        if s.get("arxiv_id"):
            id_links.append(f'<a href="https://arxiv.org/abs/{esc(s["arxiv_id"])}" target="_blank" rel="noopener">arXiv ↗</a>')
        id_links.append(f'<a href="{esc(s["url"])}" target="_blank" rel="noopener">Source ↗</a>')

        quote_html = ""
        if s.get("verbatim_excerpt"):
            quote_html = (
                f'<blockquote class="src-quote" title="Click to expand/collapse full excerpt">'
                f'<span class="quote-txt">{esc(wrap_quote(s["verbatim_excerpt"]))}</span>'
                f'<span class="quote-prov">{esc(plabel)}</span>'
                f'</blockquote>'
            )

        searchable = " ".join(
            [
                s.get("title", ""),
                s.get("authors", ""),
                s.get("venue", ""),
                s.get("summary", ""),
                s.get("verbatim_excerpt") or "",
                tags_str,
            ]
        ).lower()

        corpus_cards_html.append(
            f"""<article class="src-card" id="src-{esc(sid)}"
                data-src-id="{esc(sid)}"
                data-genre="{esc(gclass)}"
                data-disc="{esc(s['discipline_scope'])}"
                data-stages="{esc(stages_str)}"
                data-fls="{esc(fl_keys)}"
                data-tags="{esc(tags_str)}"
                data-search="{esc(searchable)}">
              <div class="src-head">
                <span class="genre-tag"><span class="gdot dot-{esc(gclass)}"></span>{esc(glabel)}</span>
                <span class="src-meta-txt">{esc(dlabel)} · {esc(s['venue'])} · {esc(s.get('date') or s['year'])}</span>
              </div>
              <h3 class="src-title"><a href="#src-{esc(sid)}" class="card-anchor">#</a>{esc(s['title'])}</h3>
              <div class="src-authors">{esc(s['authors'])}</div>
              <p class="src-sum">{esc(s['summary'])}</p>
              {quote_html}
              <div class="src-foot">
                <div class="src-axes">{''.join(pos_chips)}</div>
                <div class="src-links">{' · '.join(id_links)}</div>
              </div>
            </article>"""
        )

    fl_filter_options = "".join(
        f'<option value="{esc(fl["id"])}">{esc(fl["id"])} · {esc(fl["short"])}</option>' for fl in fault_lines
    )
    stage_filter_options = "".join(
        f'<option value="{esc(st["id"])}">{esc(st["num"])} · {esc(st["label"])}</option>' for st in STAGE_META
    )

    sources_json_inline = json.dumps(src_by_id, ensure_ascii=False).replace("</", "<\\/")

    page_html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Publishing Under AI (2025–2026)</title>
<meta name="description" content="Prose is cheap now. Check what’s behind it. {total_sources} checked sources on how AI is changing scientific writing and peer review: what has been measured, where researchers and editors disagree, and what fixes are being proposed or tried.">
<link rel="canonical" href="https://michalie.github.io/publishing-under-ai/">
<meta property="og:type" content="website">
<meta property="og:title" content="Publishing Under AI (2025–2026)">
<meta property="og:description" content="Prose is cheap now. Check what’s behind it. {total_sources} checked sources on AI in scientific writing and peer review: what has been measured, where researchers disagree, what fixes are proposed or tried.">
<meta property="og:url" content="https://michalie.github.io/publishing-under-ai/">
<meta property="og:image" content="https://michalie.github.io/publishing-under-ai/social-card.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
<style>
/* ── Editorial Observatory v3 ──────────────────────────────────────────────
   Warm architectural gallery ground + crisp white cards, editorial serif
   display headings + modern sans body, terracotta vs. petrol polarity, and
   clean jewel-tone genre dots instead of rainbow badge clutter. */
:root {{
  --ground: #F6F6F2;
  --surface: #FFFFFF;
  --surface-2: #EFEFE9;
  --ink: #161817;
  --body: #2D3330;
  --muted: #5F6964;
  --subtle: #8C9690;
  --rule: #DCDFD9;
  --rule-soft: #E8EAE5;
  --accent: #1E40AF;
  --accent-soft: #EEF2FF;

  /* Cautious side (warm terracotta) vs. opening side (deep petrol teal) */
  --pole-a: #9A3412;
  --pole-a-mid: #EA580C;
  --pole-a-bg: #FDF5F0;
  --pole-a-bdr: #F3D4C3;

  --pole-b: #115E59;
  --pole-b-mid: #0D9488;
  --pole-b-bg: #F0F9F8;
  --pole-b-bdr: #BFE3DF;

  --diag: #94A3B8;

  /* Payoff / Break subtle tints */
  --payoff-fg: #166534;
  --payoff-bg: #F2F9F4;
  --risk-fg: #9A3412;
  --risk-bg: #FDF6F2;

  /* Jewel-tone genre signal dots */
  --dot-emp: #0D9488;
  --dot-ed: #4338CA;
  --dot-disc: #B45309;
  --dot-sleuth: #DC2626;
  --dot-exp: #16A34A;
  --dot-soc: #9333EA;

  --shadow-sm: 0 1px 2px rgba(22, 24, 23, 0.04);
  --shadow-md: 0 6px 18px rgba(22, 24, 23, 0.06);

  --f-serif: "Iowan Old Style", "Newsreader", "Palatino Linotype", Palatino, Georgia, serif;
  --f-sans: -apple-system, BlinkMacSystemFont, "Inter", "IBM Plex Sans", "Segoe UI", Roboto, sans-serif;
  --f-mono: ui-monospace, SFMono-Regular, "IBM Plex Mono", Menlo, Consolas, monospace;
  color-scheme: light;
}}

:root[data-theme="dark"] {{
  --ground: #111413;
  --surface: #191E1C;
  --surface-2: #222926;
  --ink: #F1F4F2;
  --body: #CFD6D2;
  --muted: #94A09A;
  --subtle: #68756F;
  --rule: #2E3733;
  --rule-soft: #252D29;
  --accent: #93C5FD;
  --accent-soft: #1E293B;

  --pole-a: #FDBA74;
  --pole-a-mid: #FB923C;
  --pole-a-bg: #2B1A14;
  --pole-a-bdr: #4A2A1E;

  --pole-b: #5EEAD4;
  --pole-b-mid: #2DD4BF;
  --pole-b-bg: #122827;
  --pole-b-bdr: #1E4442;

  --diag: #64748B;

  --payoff-fg: #86EFAC;
  --payoff-bg: #13261A;
  --risk-fg: #FDBA74;
  --risk-bg: #291B14;

  --dot-emp: #2DD4BF;
  --dot-ed: #818CF8;
  --dot-disc: #FBBF24;
  --dot-sleuth: #F87171;
  --dot-exp: #4ADE80;
  --dot-soc: #C084FC;

  --shadow-sm: none;
  --shadow-md: none;
  color-scheme: dark;
}}

* {{ box-sizing: border-box; }}
html {{ scroll-behavior: smooth; }}
body {{
  margin: 0;
  background: var(--ground);
  color: var(--body);
  font: 15.5px/1.6 var(--f-sans);
  -webkit-font-smoothing: antialiased;
}}
button, select, input {{ font: inherit; color: inherit; }}
a {{ color: var(--accent); text-decoration-thickness: 1px; text-underline-offset: 2.5px; }}
:focus-visible {{ outline: 2px solid var(--accent); outline-offset: 2px; border-radius: 5px; }}

/* Genre signal dots */
.gdot {{
  width: 7px;
  height: 7px;
  border-radius: 50%;
  display: inline-block;
  flex: none;
}}
.dot-empirical  {{ background: var(--dot-emp); }}
.dot-editorial  {{ background: var(--dot-ed); }}
.dot-discourse  {{ background: var(--dot-disc); }}
.dot-sleuth     {{ background: var(--dot-sleuth); }}
.dot-experiment {{ background: var(--dot-exp); }}
.dot-social     {{ background: var(--dot-soc); }}

/* Sticky Navigation Bar */
nav.topnav {{
  position: sticky;
  top: 0;
  z-index: 40;
  background: color-mix(in srgb, var(--ground) 90%, transparent);
  backdrop-filter: blur(10px);
  border-bottom: 1px solid var(--rule);
}}
.topnav-inner {{
  max-width: 1180px;
  margin: 0 auto;
  padding: 11px 24px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 14px;
  flex-wrap: wrap;
}}
.brand-mark {{
  font: 700 0.96rem/1 var(--f-serif);
  color: var(--ink);
  text-decoration: none;
  letter-spacing: -0.01em;
}}
.nav-items {{
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}}
.nav-items a.nav-link {{
  text-decoration: none;
  color: var(--muted);
  font: 500 0.82rem/1 var(--f-sans);
  padding: 6px 10px;
  border-radius: 6px;
}}
.nav-items a.nav-link:hover {{
  color: var(--ink);
  background: var(--surface);
}}
.btn-essay {{
  text-decoration: none;
  background: var(--ink);
  color: var(--surface);
  font: 600 0.8rem/1 var(--f-sans);
  padding: 7px 13px;
  border-radius: 999px;
  margin-left: 4px;
}}
.btn-essay:hover {{ opacity: 0.9; }}
.btn-outline {{
  background: var(--surface);
  border: 1px solid var(--rule);
  border-radius: 7px;
  padding: 6px 11px;
  font: 500 0.8rem/1 var(--f-sans);
  color: var(--body);
  cursor: pointer;
  box-shadow: var(--shadow-sm);
}}
.btn-outline:hover {{ border-color: var(--muted); }}

.wrap {{
  max-width: 1180px;
  margin: 0 auto;
  padding: 38px 24px 92px;
}}

/* Hero Masthead */
header.hero {{
  margin-bottom: 48px;
}}
.hero-kicker {{
  font: 600 0.74rem/1 var(--f-mono);
  text-transform: uppercase;
  letter-spacing: 0.09em;
  color: var(--pole-b);
  margin-bottom: 12px;
}}
h1 {{
  font: 700 clamp(2.1rem, 3.8vw, 2.85rem)/1.12 var(--f-serif);
  color: var(--ink);
  letter-spacing: -0.018em;
  margin: 0 0 14px;
  max-width: 860px;
}}
.hero-lead {{
  font-size: 1.08rem;
  line-height: 1.6;
  color: var(--body);
  max-width: 820px;
  margin: 0 0 12px;
}}
.hero-sub {{
  font-size: 0.88rem;
  color: var(--muted);
  margin: 0 0 26px;
}}

/* 4 Architectural Summary Cards + Genre Key */
.hero-cards {{
  display: grid;
  grid-template-columns: 1.45fr repeat(3, 1fr);
  gap: 14px;
}}
.h-card {{
  background: var(--surface);
  border: 1px solid var(--rule);
  border-radius: 11px;
  padding: 16px 18px;
  box-shadow: var(--shadow-sm);
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  gap: 8px;
}}
.h-num {{
  font: 700 1.75rem/1.05 var(--f-serif);
  color: var(--ink);
}}
.h-lbl {{
  font: 600 0.74rem/1.2 var(--f-mono);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--muted);
}}
.h-note {{
  font-size: 0.82rem;
  color: var(--muted);
  line-height: 1.38;
}}
.gbar {{
  height: 7px;
  border-radius: 999px;
  overflow: hidden;
  display: flex;
  gap: 1.5px;
  margin-top: 2px;
}}
.gbar-seg {{ display: block; height: 100%; }}

.legend-strip {{
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 18px;
  margin-top: 14px;
  padding: 10px 14px;
  background: var(--surface);
  border: 1px solid var(--rule-soft);
  border-radius: 9px;
  font-size: 0.8rem;
  color: var(--muted);
}}
.legend-lbl {{
  font: 600 0.72rem/1 var(--f-mono);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--ink);
}}
.leg-item {{
  display: inline-flex;
  align-items: center;
  gap: 6px;
}}

/* Section Headers */
section.block {{
  margin-bottom: 64px;
  scroll-margin-top: 68px;
}}
.sec-head {{
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  gap: 16px;
  flex-wrap: wrap;
  margin-bottom: 20px;
  padding-bottom: 12px;
  border-bottom: 1.5px solid var(--ink);
}}
.sec-eyebrow {{
  font: 600 0.73rem/1 var(--f-mono);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--pole-b);
  margin-bottom: 5px;
}}
.sec-head h2 {{
  font: 700 1.65rem/1.18 var(--f-serif);
  color: var(--ink);
  margin: 0;
  letter-spacing: -0.01em;
}}
.sec-sub {{
  margin: 5px 0 0;
  font-size: 0.93rem;
  color: var(--muted);
  max-width: 740px;
}}

/* 01 · Pipeline Tiles + Data-Forward Shockwaves */
.stage-ribbon {{
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 20px;
}}
.stage-tile {{
  text-align: left;
  background: var(--surface);
  border: 1px solid var(--rule);
  border-top: 3px solid var(--pole-b-mid);
  border-radius: 9px;
  padding: 12px 13px;
  cursor: pointer;
  box-shadow: var(--shadow-sm);
  transition: transform 0.14s, box-shadow 0.14s, border-color 0.14s;
}}
.stage-tile:hover {{
  transform: translateY(-2px);
  box-shadow: var(--shadow-md);
  border-color: var(--pole-b);
}}
.st-top {{
  display: flex;
  justify-content: space-between;
  font: 600 0.72rem/1 var(--f-mono);
  color: var(--muted);
  margin-bottom: 6px;
}}
.st-num {{ color: var(--pole-b); }}
.st-title {{
  font: 700 0.95rem/1.25 var(--f-serif);
  color: var(--ink);
  margin-bottom: 4px;
}}
.st-hook {{
  margin: 0;
  font-size: 0.79rem;
  line-height: 1.4;
  color: var(--muted);
}}

.sw-grid {{
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}}
.sw-card {{
  background: var(--surface);
  border: 1px solid var(--rule);
  border-radius: 11px;
  padding: 18px 20px;
  box-shadow: var(--shadow-sm);
  display: flex;
  flex-direction: column;
  gap: 9px;
}}
.sw-top {{
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 10px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--rule-soft);
}}
.sw-big {{
  display: block;
  font: 700 1.38rem/1.1 var(--f-serif);
  color: var(--pole-b);
  letter-spacing: -0.015em;
}}
.sw-sub {{
  display: block;
  font: 500 0.74rem/1.3 var(--f-mono);
  color: var(--muted);
  margin-top: 2px;
}}
.stage-tag {{
  font: 600 0.71rem/1 var(--f-mono);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  background: var(--surface-2);
  color: var(--muted);
  padding: 4px 8px;
  border-radius: 5px;
  white-space: nowrap;
}}
.sw-card h3 {{
  font: 700 1.06rem/1.32 var(--f-serif);
  color: var(--ink);
  margin: 0;
}}
.sw-card p {{
  margin: 0;
  font-size: 0.9rem;
  color: var(--body);
  line-height: 1.54;
}}
.chip-row {{
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: auto;
  padding-top: 4px;
}}
.cite-chip {{
  display: inline-flex;
  align-items: center;
  gap: 5px;
  background: var(--ground);
  border: 1px solid var(--rule);
  border-radius: 6px;
  padding: 3px 8px;
  font: 500 0.75rem/1.2 var(--f-sans);
  color: var(--ink);
  cursor: pointer;
}}
.cite-chip:hover {{
  border-color: var(--accent);
  color: var(--accent);
}}

/* 02 · Diverging Tug-of-War Summary + Fault-Line Cards */
.tug-box {{
  background: var(--surface);
  border: 1px solid var(--rule);
  border-radius: 11px;
  padding: 14px 18px;
  margin-bottom: 22px;
  box-shadow: var(--shadow-sm);
}}
.tug-caption {{
  display: flex;
  justify-content: space-between;
  align-items: center;
  font: 600 0.72rem/1 var(--f-mono);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--muted);
  padding-bottom: 10px;
  border-bottom: 1px solid var(--rule-soft);
  margin-bottom: 6px;
}}
.tug-row {{
  display: grid;
  grid-template-columns: 36px 1.2fr 1fr 180px 1fr 34px;
  gap: 12px;
  align-items: center;
  padding: 8px 6px;
  border-bottom: 1px dashed var(--rule-soft);
  text-decoration: none;
  border-radius: 6px;
}}
.tug-row:last-child {{ border-bottom: 0; }}
.tug-row:hover {{ background: var(--ground); }}
.tug-id {{
  font: 700 0.76rem/1 var(--f-mono);
  color: var(--ink);
}}
.tug-title {{
  font: 600 0.9rem/1.25 var(--f-sans);
  color: var(--ink);
}}
.tug-pa, .tug-pb {{
  font-size: 0.78rem;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}}
.tug-pa {{ text-align: right; color: var(--pole-a); }}
.tug-pb {{ text-align: left; color: var(--pole-b); }}
.tug-pa em, .tug-pb em {{ font-style: normal; opacity: 0.75; font-family: var(--f-mono); font-size: 0.73rem; }}
.tug-bar {{
  height: 9px;
  border-radius: 999px;
  overflow: hidden;
  display: flex;
  gap: 1.5px;
  background: var(--surface-2);
}}
.tug-seg {{ display: block; height: 100%; }}
.tug-a2 {{ background: var(--pole-a); }}
.tug-a1 {{ background: var(--pole-a-mid); opacity: 0.75; }}
.tug-0  {{ background: var(--diag); opacity: 0.55; }}
.tug-b1 {{ background: var(--pole-b-mid); opacity: 0.75; }}
.tug-b2 {{ background: var(--pole-b); }}
.tug-tot {{
  font: 600 0.75rem/1 var(--f-mono);
  color: var(--muted);
  text-align: right;
}}

.fl-stack {{
  display: grid;
  gap: 20px;
}}
.fl-card {{
  background: var(--surface);
  border: 1px solid var(--rule);
  border-radius: 12px;
  padding: 22px 24px;
  box-shadow: var(--shadow-sm);
  scroll-margin-top: 74px;
}}
.fl-top {{
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 6px;
}}
.fl-meta {{
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 6px;
}}
.id-badge {{
  font: 700 0.76rem/1 var(--f-mono);
  background: var(--ink);
  color: var(--surface);
  padding: 4px 8px;
  border-radius: 5px;
}}
.fl-tally {{
  font: 500 0.75rem/1 var(--f-mono);
  color: var(--muted);
}}
.fl-card h3 {{
  font: 700 1.36rem/1.2 var(--f-serif);
  color: var(--ink);
  margin: 0;
}}
.fl-question {{
  font-size: 0.98rem;
  color: var(--body);
  margin: 6px 0 14px;
  max-width: 880px;
}}
.poles-pair {{
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
  margin-bottom: 14px;
}}
.pole-box {{
  border-radius: 9px;
  padding: 13px 15px;
}}
.pole-a {{
  background: var(--pole-a-bg);
  border: 1px solid var(--pole-a-bdr);
}}
.pole-b {{
  background: var(--pole-b-bg);
  border: 1px solid var(--pole-b-bdr);
}}
.pole-head {{
  font: 700 0.75rem/1.2 var(--f-mono);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  margin-bottom: 5px;
}}
.pole-a .pole-head {{ color: var(--pole-a); }}
.pole-b .pole-head {{ color: var(--pole-b); }}
.pole-box p {{
  margin: 0;
  font-size: 0.89rem;
  line-height: 1.5;
  color: var(--body);
}}

.spec-grid {{
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 9px;
  margin-bottom: 12px;
}}
.spec-bin {{
  background: var(--ground);
  border: 1px solid var(--rule-soft);
  border-radius: 8px;
  padding: 9px;
  display: flex;
  flex-direction: column;
  gap: 7px;
}}
.spec-bin.col-a {{ border-top: 2.5px solid var(--pole-a); }}
.spec-bin.col-0 {{ border-top: 2.5px solid var(--diag); }}
.spec-bin.col-b {{ border-top: 2.5px solid var(--pole-b); }}
.spec-hd {{
  display: flex;
  align-items: baseline;
  gap: 5px;
  padding-bottom: 5px;
  border-bottom: 1px solid var(--rule-soft);
}}
.spec-sc {{
  font: 700 0.73rem/1 var(--f-mono);
  color: var(--ink);
}}
.spec-name {{
  font-size: 0.72rem;
  color: var(--muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}}
.spec-n {{
  margin-left: auto;
  font: 600 0.72rem/1 var(--f-mono);
  color: var(--muted);
}}
.spec-body, .extra-pills {{
  display: flex;
  flex-direction: column;
  gap: 4px;
}}
.extra-pills[hidden] {{ display: none; }}
.voice-pill {{
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  text-align: left;
  background: var(--surface);
  border: 1px solid var(--rule);
  border-radius: 6px;
  padding: 4px 7px;
  font: 500 0.76rem/1.25 var(--f-sans);
  color: var(--ink);
  cursor: pointer;
}}
.voice-pill:hover {{
  border-color: var(--accent);
  color: var(--accent);
}}
.more-pills-btn {{
  background: transparent;
  border: 1px dashed var(--rule);
  border-radius: 5px;
  padding: 3px 7px;
  font: 600 0.72rem/1.2 var(--f-mono);
  color: var(--muted);
  cursor: pointer;
  text-align: center;
  margin-top: 2px;
}}
.more-pills-btn:hover {{ color: var(--ink); border-color: var(--muted); }}
.bin-empty {{ color: var(--subtle); font-size: 0.8rem; }}
.fl-hinge {{
  font-size: 0.86rem;
  color: var(--muted);
  padding-top: 10px;
  border-top: 1px solid var(--rule-soft);
}}
.fl-hinge strong {{ color: var(--ink); }}

/* 03 · Eight Institutional Models */
.models-grid {{
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}}
.model-card {{
  background: var(--surface);
  border: 1px solid var(--rule);
  border-radius: 11px;
  padding: 20px 22px;
  box-shadow: var(--shadow-sm);
  display: flex;
  flex-direction: column;
  gap: 10px;
  scroll-margin-top: 74px;
}}
.model-top {{
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}}
.mat-pill {{
  font: 600 0.72rem/1 var(--f-mono);
  background: var(--accent-soft);
  color: var(--accent);
  padding: 4px 8px;
  border-radius: 5px;
}}
.model-axes {{
  margin-left: auto;
  display: flex;
  gap: 5px;
}}
.axis-pill {{
  font: 600 0.72rem/1 var(--f-mono);
  background: var(--surface-2);
  color: var(--ink);
  border: 1px solid var(--rule);
  padding: 3px 6px;
  border-radius: 4px;
  text-decoration: none;
}}
.axis-pill:hover {{ border-color: var(--accent); color: var(--accent); }}
.model-card h3 {{
  font: 700 1.18rem/1.25 var(--f-serif);
  color: var(--ink);
  margin: 0;
}}
.model-tagline {{
  margin: 0;
  font-size: 0.88rem;
  color: var(--pole-b);
  font-weight: 500;
}}
.model-mech {{
  margin: 0;
  font-size: 0.89rem;
  color: var(--body);
}}
.callout-pair {{
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}}
.m-box {{
  border-radius: 8px;
  padding: 10px 12px;
}}
.m-payoff {{ background: var(--payoff-bg); }}
.m-risk   {{ background: var(--risk-bg); }}
.m-lbl {{
  display: block;
  font: 700 0.7rem/1.2 var(--f-mono);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  margin-bottom: 4px;
}}
.m-payoff .m-lbl {{ color: var(--payoff-fg); }}
.m-risk .m-lbl   {{ color: var(--risk-fg); }}
.m-box p {{
  margin: 0;
  font-size: 0.84rem;
  line-height: 1.45;
  color: var(--body);
}}
.model-drawer {{
  margin-top: auto;
  padding-top: 8px;
  border-top: 1px solid var(--rule-soft);
  font-size: 0.84rem;
}}
.model-drawer summary {{
  cursor: pointer;
  font: 600 0.78rem var(--f-mono);
  color: var(--muted);
}}
.model-drawer ul {{
  margin: 8px 0 0;
  padding-left: 18px;
  display: grid;
  gap: 4px;
}}
.more-inline {{
  font: 500 0.74rem var(--f-mono);
  color: var(--muted);
  align-self: center;
}}

/* 04 · Evidence Ledger (2-col Card Grid + Compact List Switcher) */
.filter-panel {{
  background: var(--surface);
  border: 1px solid var(--rule);
  border-radius: 11px;
  padding: 14px 16px;
  margin-bottom: 12px;
  box-shadow: var(--shadow-sm);
}}
.filter-grid {{
  display: grid;
  grid-template-columns: 1.5fr repeat(4, minmax(120px, 1fr)) auto;
  gap: 8px;
  align-items: center;
}}
.filter-grid input, .filter-grid select {{
  background: var(--ground);
  border: 1px solid var(--rule);
  border-radius: 7px;
  padding: 7px 10px;
  font-size: 0.86rem;
  width: 100%;
}}
.status-bar {{
  display: flex;
  justify-content: space-between;
  align-items: center;
  font: 500 0.78rem var(--f-mono);
  color: var(--muted);
  margin-bottom: 12px;
}}

.corpus-grid {{
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}}
.corpus-grid.list-mode {{
  grid-template-columns: 1fr;
  gap: 10px;
}}
.src-card {{
  background: var(--surface);
  border: 1px solid var(--rule);
  border-radius: 10px;
  padding: 16px 18px;
  box-shadow: var(--shadow-sm);
  display: flex;
  flex-direction: column;
  gap: 6px;
  scroll-margin-top: 76px;
}}
.src-card.highlight {{
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-soft);
}}
.src-head {{
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}}
.genre-tag {{
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font: 600 0.74rem/1 var(--f-sans);
  color: var(--ink);
}}
.src-meta-txt {{
  font: 500 0.73rem/1.2 var(--f-mono);
  color: var(--muted);
}}
.src-title {{
  font: 700 1.04rem/1.3 var(--f-serif);
  color: var(--ink);
  margin: 2px 0 0;
}}
.card-anchor {{
  color: var(--subtle);
  text-decoration: none;
  font-family: var(--f-mono);
  font-weight: 400;
  margin-right: 5px;
}}
.src-authors {{
  font-size: 0.82rem;
  color: var(--muted);
}}
.src-sum {{
  margin: 2px 0 4px;
  font-size: 0.88rem;
  line-height: 1.52;
  color: var(--body);
}}
.src-quote {{
  margin: 2px 0 4px;
  padding: 9px 12px;
  background: var(--ground);
  border-left: 2.5px solid var(--pole-b-mid);
  border-radius: 0 6px 6px 0;
  cursor: pointer;
}}
.quote-txt {{
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
  font-style: italic;
  font-size: 0.84rem;
  line-height: 1.48;
  color: var(--ink);
}}
.src-quote.is-open .quote-txt {{
  display: block;
}}
.quote-prov {{
  display: block;
  font: 500 0.7rem/1.3 var(--f-mono);
  font-style: normal;
  color: var(--muted);
  margin-top: 5px;
}}
.src-foot {{
  margin-top: auto;
  padding-top: 8px;
  border-top: 1px dashed var(--rule-soft);
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}}
.src-axes {{ display: flex; gap: 4px; flex-wrap: wrap; }}
.src-links {{ font: 600 0.75rem var(--f-mono); }}

/* 05 · Provenance Cards */
.prov-pair {{
  display: grid;
  grid-template-columns: 1.2fr 0.8fr;
  gap: 16px;
}}
.prov-card {{
  background: var(--surface);
  border: 1px solid var(--rule);
  border-radius: 10px;
  padding: 18px 20px;
  box-shadow: var(--shadow-sm);
}}
.prov-card h3 {{
  font: 700 1.04rem var(--f-serif);
  color: var(--ink);
  margin: 0 0 10px;
}}
.prov-card ul {{
  margin: 0;
  padding-left: 18px;
  display: grid;
  gap: 9px;
  font-size: 0.86rem;
}}
.prov-sub {{
  display: block;
  color: var(--muted);
  font-size: 0.81rem;
  margin-top: 2px;
}}
code {{
  font-family: var(--f-mono);
  font-size: 0.84em;
  background: var(--ground);
  padding: 1px 5px;
  border-radius: 4px;
}}

/* Spotlight Modal */
dialog#spotlight {{
  max-width: 650px;
  width: calc(100% - 28px);
  border: 1px solid var(--rule);
  border-radius: 12px;
  background: var(--surface);
  color: var(--body);
  padding: 22px 24px;
  box-shadow: 0 24px 56px rgba(0, 0, 0, 0.24);
}}
dialog#spotlight::backdrop {{ background: rgba(16, 20, 18, 0.48); }}
.sp-top {{
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
}}
dialog#spotlight h3 {{
  font: 700 1.18rem/1.3 var(--f-serif);
  color: var(--ink);
  margin: 0 0 4px;
}}
.sp-quote-box {{
  margin: 12px 0;
  padding: 10px 14px;
  background: var(--ground);
  border-left: 3px solid var(--pole-b-mid);
  border-radius: 0 7px 7px 0;
  font-style: italic;
  font-size: 0.9rem;
  color: var(--ink);
}}

footer.foot {{
  margin-top: 64px;
  padding-top: 18px;
  border-top: 1px solid var(--rule);
  display: flex;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 10px;
  font-size: 0.84rem;
  color: var(--muted);
}}

.takeaway {{
  margin: 6px 0 18px;
  padding: 18px 22px;
  background: var(--surface);
  border: 1px solid var(--rule);
  border-left: 5px solid var(--pole-b-mid);
  border-radius: 10px;
  max-width: 860px;
  box-shadow: var(--shadow-sm);
}}
.takeaway .tk-line {{
  font: 700 clamp(1.35rem, 3.2vw, 1.9rem)/1.2 var(--f-serif);
  color: var(--ink);
  margin: 0 0 8px;
}}
.takeaway p {{ margin: 0; font-size: 1.02rem; line-height: 1.55; color: var(--body); }}
.start-here {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 10px;
  margin: 4px 0 16px;
  max-width: 1000px;
}}
.start-here a {{
  display: block;
  padding: 12px 14px;
  background: var(--surface);
  border: 1px solid var(--rule);
  border-radius: 9px;
  text-decoration: none;
  color: var(--ink);
  font-size: 0.9rem;
  line-height: 1.4;
}}
.start-here a:hover {{ border-color: var(--pole-b); }}
.start-here a b {{ display: block; font: 700 0.7rem/1.3 var(--f-mono); letter-spacing: 0.06em; text-transform: uppercase; color: var(--pole-b); margin-bottom: 4px; }}
.hero-scope {{ font-size: 0.86rem; color: var(--muted); max-width: 860px; margin: 0 0 16px; line-height: 1.55; }}
.thin-note {{ font-size: 0.82rem; color: var(--muted); font-style: italic; margin: 10px 0 0; }}
.about-grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }}
.about-grid .prov-card p {{ margin: 0 0 8px; font-size: 0.9rem; line-height: 1.55; }}

@media (max-width: 960px) {{
  .about-grid {{ grid-template-columns: 1fr; }}
  .hero-cards {{ grid-template-columns: 1fr 1fr; }}
  .stage-ribbon {{ grid-template-columns: repeat(2, 1fr); }}
  .sw-grid, .models-grid, .corpus-grid, .poles-pair, .callout-pair, .prov-pair {{ grid-template-columns: 1fr; }}
  .tug-row {{
    grid-template-columns: 32px 1fr 1fr 28px;
    grid-template-areas: "id title title tot" ". bar bar ." ". pa pb .";
    row-gap: 6px;
  }}
  .tug-id {{ grid-area: id; }}
  .tug-title {{ grid-area: title; }}
  .tug-tot {{ grid-area: tot; }}
  .tug-bar {{ grid-area: bar; }}
  .tug-pa {{ grid-area: pa; text-align: left; white-space: normal; }}
  .tug-pb {{ grid-area: pb; text-align: right; white-space: normal; }}
  .spec-grid {{ grid-template-columns: 1fr; }}
  .filter-grid {{ grid-template-columns: 1fr 1fr; }}
}}
</style>
</head>
<body>

<nav class="topnav" aria-label="Observatory navigation">
  <div class="topnav-inner">
    <a href="#" class="brand-mark">Publishing Under AI · 2025–2026</a>
    <div class="nav-items">
      <a href="#shockwaves" class="nav-link">01 What changed</a>
      <a href="#fault-lines" class="nav-link">02 Where people disagree</a>
      <a href="#models" class="nav-link">03 Proposed fixes</a>
      <a href="#corpus" class="nav-link">04 All sources ({total_sources})</a>
      <a href="#about" class="nav-link">About</a>
      <a href="https://github.com/MichaLie/publishing-under-ai" class="nav-link" target="_blank" rel="noopener">GitHub ↗</a>
      <button type="button" class="btn-outline" id="theme-toggle" aria-label="Switch color theme">Dark</button>
      <a href="essay.html" class="btn-essay">Read the essay →</a>
    </div>
  </div>
</nav>

<main class="wrap">

  <header class="hero">
    <div class="hero-kicker">Evidence map · sources up to {esc(latest_human)} · page built {esc(built_human)}</div>
    <h1>Publishing Under AI (2025–2026)</h1>
    <div class="takeaway">
      <p class="tk-line">Prose is cheap now. Check what’s behind it.</p>
      <p>Now that fluent prose costs almost nothing, a well-written paper no longer shows that the work behind it was done well. Trust has to come from what can be checked: data, code, references that resolve, and a named person who answers for each claim.</p>
    </div>
    <p class="hero-lead">
      This page puts {total_sources} studies, editorials, policies and public posts side by side: <strong>what has measurably changed</strong> in scientific writing and peer review, <strong>seven questions where researchers and editors disagree</strong>, and <strong>eight fixes</strong> proposed or tried by journals, conferences, preprint servers and funders, with how each can fail.
    </p>
    <nav class="start-here" aria-label="Where to start">
      <a href="essay.html"><b>New to the debate?</b>Read the 15-minute essay, <em>When Fluency Costs Nothing</em> →</a>
      <a href="essay.html#5-a-monday-morning-compass"><b>Writing or supervising a thesis?</b>Practical habits for PhD students, PIs and reviewers →</a>
      <a href="#F2"><b>Editor or reviewer?</b>AI inside peer review (F2) and what disclosure rules achieve (F3) →</a>
      <a href="#SW3"><b>Research integrity?</b>Fabricated references (SW3) and automated error-checking (F6) →</a>
    </nav>
    <p class="hero-scope">
      A curated collection, not a systematic review: {total_sources} sources, almost all from 2025 and 2026, each linked and quoted. Many of the large public experiments ran at computer-science conferences; use the discipline filter in the source list to see biomedical sources only. Positions on the seven questions are my reading; if you disagree or know a study I missed, <a href="https://github.com/MichaLie/publishing-under-ai/issues" target="_blank" rel="noopener">open an issue</a>.
      Related: <a href="https://michalie.github.io/journal-ai-policies/" target="_blank" rel="noopener">What journals actually require</a> · <a href="https://michalie.github.io/agent-risk-atlas/" target="_blank" rel="noopener">Agent Risk Atlas</a>.
    </p>

    <div class="hero-cards" aria-label="Corpus overview">
      <div class="h-card">
        <div>
          <span class="h-lbl">Sources</span>
          <div class="h-num">{total_sources} sources</div>
        </div>
        <div class="gbar" aria-hidden="true">{''.join(genre_bar_segs)}</div>
        <div class="h-note">{n_empirical} empirical · {n_editorial} editorials · {n_discourse_all} essays, sleuths &amp; pilots · {n_social} social</div>
      </div>
      <div class="h-card">
        <div>
          <span class="h-lbl">Quoted</span>
          <div class="h-num">{n_verbatim}/{total_sources}</div>
        </div>
        <div class="h-note">every record carries a short verbatim quote and a link to its source</div>
      </div>
      <div class="h-card">
        <div>
          <span class="h-lbl">Where people disagree</span>
          <div class="h-num">{len(fault_lines)} fault lines</div>
        </div>
        <div class="h-note">each from the cautious side ◀ (−2) to the side that lets AI in ▶ (+2)</div>
      </div>
      <div class="h-card">
        <div>
          <span class="h-lbl">Proposed fixes</span>
          <div class="h-num">{len(models)} proposed models</div>
        </div>
        <div class="h-note">Conference, journal, funder, and executable-paper interventions, proposed or piloted</div>
      </div>
    </div>

    <div class="legend-strip" aria-label="Source genre color key">
      <span class="legend-lbl">Genre key:</span>
      <span class="leg-item"><span class="gdot dot-empirical"></span>Empirical / Preprint ({n_empirical})</span>
      <span class="leg-item"><span class="gdot dot-editorial"></span>Editorial / Comment ({n_editorial})</span>
      <span class="leg-item"><span class="gdot dot-discourse"></span>Essay / Blog ({genre_counts['discourse']})</span>
      <span class="leg-item"><span class="gdot dot-sleuth"></span>Forensic / Sleuth ({genre_counts['sleuth']})</span>
      <span class="leg-item"><span class="gdot dot-experiment"></span>Live Pilot / Policy ({genre_counts['experiment']})</span>
      <span class="leg-item"><span class="gdot dot-social"></span>X &amp; LinkedIn ({n_social})</span>
    </div>
  </header>

  <section class="block" id="shockwaves">
    <div class="sec-head">
      <div>
        <div class="sec-eyebrow">01 · Measured shifts</div>
        <h2>What has measurably changed</h2>
        <p class="sec-sub">Click any pipeline stage tile to filter the ledger below, or click any citation chip to inspect its verbatim excerpt.</p>
      </div>
    </div>

    <div class="stage-ribbon" role="group" aria-label="Six publishing pipeline stages">
      {''.join(stage_cards_html)}
    </div>

    <div class="sw-grid">
      {''.join(shock_cards_html)}
    </div>
  </section>

  <section class="block" id="fault-lines">
    <div class="sec-head">
      <div>
        <div class="sec-eyebrow">02 · Fault lines</div>
        <h2>Seven questions where researchers and editors disagree</h2>
        <p class="sec-sub">Every question has a more cautious side on the left (◀, keep or tighten human control) and a side that lets AI in or opens up the system on the right (▶). Click a row to jump to that question, or a name to read the source’s claim and quote. Positions are my reading: ±2 means the source argues for that side, ±1 that it leans that way or mainly supplies evidence for it, 0 that it addresses the question without taking a side. Each underlying claim is placed once: news reports and posts that echo an already-placed study, sources that do not address a question, pseudonymous accounts and casual posts by private individuals are listed without a position.</p>
      </div>
    </div>

    <div class="tug-box" aria-label="Overview of all seven fault lines">
      <div class="tug-caption">
        <span>How the placed sources split (click a row to jump)</span>
        <span><span style="color:var(--pole-a)">■ ◀ cautious side</span> · <span style="color:var(--muted)">■ no side</span> · <span style="color:var(--pole-b)">■ lets AI in / opens up ▶</span></span>
      </div>
      {''.join(tug_rows_html)}
    </div>

    <div class="fl-stack">
      {''.join(fl_cards_html)}
    </div>
  </section>

  <section class="block" id="models">
    <div class="sec-head">
      <div>
        <div class="sec-eyebrow">03 · Proposed models</div>
        <h2>Eight proposed fixes, and how each can fail</h2>
        <p class="sec-sub">Ideas piloted or debated by journals, conferences, preprint servers and funders in 2025–2026.</p>
      </div>
    </div>

    <div class="models-grid">
      {''.join(model_cards_html)}
    </div>
  </section>

  <section class="block" id="corpus">
    <div class="sec-head">
      <div>
        <div class="sec-eyebrow">04 · Source ledger</div>
        <h2>All {total_sources} sources</h2>
        <p class="sec-sub">Click any truncated quote block to expand the full excerpt, or switch between 2-column cards and compact 1-column rows.</p>
      </div>
      <div style="display:flex;gap:8px;flex-wrap:wrap">
        <button type="button" class="btn-outline" id="toggle-quotes">Expand all quotes</button>
        <button type="button" class="btn-outline" id="toggle-layout">View: 2-column cards</button>
      </div>
    </div>

    <div class="filter-panel" role="search" aria-label="Filter source corpus">
      <div class="filter-grid">
        <input type="search" id="f-q" placeholder="Search titles, authors, venues, quotes (e.g. 'ICLR', 'JACC', 'AJPS')…">
        <select id="f-genre" aria-label="Filter by genre">
          <option value="">All genres</option>
          <option value="empirical">Empirical &amp; Preprints</option>
          <option value="editorial">Editorials &amp; Comments</option>
          <option value="discourse">Essays &amp; Blogs</option>
          <option value="sleuth">Forensic &amp; Sleuths</option>
          <option value="experiment">Live Pilots &amp; Policies</option>
          <option value="social">X &amp; LinkedIn</option>
        </select>
        <select id="f-disc" aria-label="Filter by discipline">
          <option value="">All disciplines</option>
          <option value="biomed_lifesci">Biomed &amp; Life Sci</option>
          <option value="cs_ml">CS &amp; ML</option>
          <option value="cross_disciplinary">Cross-disciplinary</option>
        </select>
        <select id="f-stage" aria-label="Filter by pipeline stage">
          <option value="">All stages</option>
          {stage_filter_options}
        </select>
        <select id="f-fl" aria-label="Filter by fault line">
          <option value="">All fault lines</option>
          {fl_filter_options}
        </select>
        <button type="button" class="btn-outline" id="f-reset">Reset</button>
      </div>
    </div>

    <div class="status-bar">
      <span id="f-count">Showing all {total_sources} sources</span>
      <span>Press <code>Esc</code> to clear spotlight or active highlight</span>
    </div>

    <div class="corpus-grid" id="corpus-list">
      {''.join(corpus_cards_html)}
    </div>
  </section>

  <section class="block" id="about">
    <div class="sec-head">
      <div>
        <div class="sec-eyebrow">05 · About</div>
        <h2>About this collection</h2>
      </div>
    </div>
    <div class="about-grid">
      <div class="prov-card">
        <h3>What it is, and what it is not</h3>
        <p>A curated map of {total_sources} sources on generative AI in scientific writing, peer review and research integrity, almost all from 2025 and 2026: empirical studies and preprints, journal editorials, integrity investigations, policy announcements, and public posts by researchers and editors. Every record links to its source and quotes it briefly.</p>
        <p>It is not a systematic review and does not replicate any study. Positions on the seven questions are one reader’s interpretation, shown so you can check them against the quoted text.</p>
      </div>
      <div class="prov-card">
        <h3>Corrections and suggestions</h3>
        <p>Think a summary or a position misreads your work? Know a study, pilot or policy that is missing? <a href="https://github.com/MichaLie/publishing-under-ai/issues" target="_blank" rel="noopener">Open an issue on GitHub</a>.</p>
        <p>Source code and data: <a href="https://github.com/MichaLie/publishing-under-ai" target="_blank" rel="noopener">github.com/MichaLie/publishing-under-ai</a> · <a href="data.json">data.json</a> (records CC0; quoted excerpts remain their authors’ and publishers’).</p>
      </div>
      <div class="prov-card">
        <h3>How this was made</h3>
        <p>Created by Michaela Liegertová (Jan Evangelista Purkyně University in Ústí nad Labem; Institute of Molecular Genetics of the Czech Academy of Sciences) in collaboration with AI agents running Gemini Carbon, Claude Opus 5.5 and Fable 5.2.</p>
      </div>
      <div class="prov-card">
        <h3>How to cite</h3>
        <p>Liegertová M. <em>Publishing Under AI (2025–2026)</em>. Version 1.1, 2026. https://michalie.github.io/publishing-under-ai/</p>
      </div>
    </div>
  </section>

  <footer class="foot">
    <div>Michaela Liegertová, in collaboration with AI agents running Gemini Carbon, Claude Opus 5.5 and Fable 5.2 · <a href="essay.html">Essay</a> · <a href="data.json">data.json</a> (records CC0; quoted excerpts remain their authors’)</div>
    <div><a href="https://github.com/MichaLie/publishing-under-ai" target="_blank" rel="noopener">GitHub</a> · <a href="https://github.com/MichaLie/publishing-under-ai/issues" target="_blank" rel="noopener">Suggest a source or a correction</a></div>
  </footer>

</main>

<dialog id="spotlight" aria-labelledby="sp-title">
  <div class="sp-top">
    <span id="sp-badges" class="genre-tag"></span>
    <button type="button" class="btn-outline" id="sp-close">Close (Esc)</button>
  </div>
  <h3 id="sp-title"></h3>
  <div id="sp-authors" class="src-authors"></div>
  <p id="sp-summary" class="src-sum" style="margin-top:8px"></p>
  <blockquote id="sp-quote" class="sp-quote-box" hidden></blockquote>
  <div class="src-foot">
    <div id="sp-links" class="src-links"></div>
    <a id="sp-jump" href="#corpus" class="btn-outline" style="text-decoration:none">Jump to ledger card ↓</a>
  </div>
</dialog>

<script>
const SOURCES = {sources_json_inline};
const GENRE_META = {{
  empirical_study: ["empirical", "Empirical study"],
  preprint: ["empirical", "Preprint"],
  editorial_comment: ["editorial", "Editorial / Comment"],
  journal_news_feature: ["editorial", "Journal news"],
  perspective_essay: ["editorial", "Perspective"],
  blog_essay: ["discourse", "Essay / Blog"],
  community_thread_writeup: ["discourse", "Community pulse"],
  social_post: ["social", "X / LinkedIn"],
  watchdog_investigation: ["sleuth", "Forensic / Sleuth"],
  live_experiment: ["experiment", "Live pilot"],
  institutional_experiment: ["experiment", "Institutional policy"]
}};

// Theme toggle
const themeBtn = document.getElementById('theme-toggle');
themeBtn.addEventListener('click', () => {{
  const root = document.documentElement;
  const dark = root.getAttribute('data-theme') !== 'dark';
  if (dark) root.setAttribute('data-theme', 'dark');
  else root.removeAttribute('data-theme');
  themeBtn.textContent = dark ? 'Light' : 'Dark';
}});

// '+N more' expanders inside spectrum columns
document.querySelectorAll('.more-pills-btn').forEach(btn => {{
  btn.addEventListener('click', () => {{
    const extra = btn.previousElementSibling;
    const opening = extra.hidden;
    extra.hidden = !opening;
    btn.textContent = opening ? 'Show fewer' : `+${{btn.dataset.moreCnt}} more`;
  }});
}});

// Click individual quote block to expand/collapse, plus global toggle
let allQuotesOpen = false;
const quotesBtn = document.getElementById('toggle-quotes');
document.querySelectorAll('.src-quote').forEach(q => {{
  q.addEventListener('click', () => q.classList.toggle('is-open'));
}});
quotesBtn.addEventListener('click', () => {{
  allQuotesOpen = !allQuotesOpen;
  document.querySelectorAll('.src-quote').forEach(q => q.classList.toggle('is-open', allQuotesOpen));
  quotesBtn.textContent = allQuotesOpen ? 'Collapse quotes' : 'Expand all quotes';
}});

// 2-column vs 1-column layout toggle
const corpusList = document.getElementById('corpus-list');
const layoutBtn = document.getElementById('toggle-layout');
layoutBtn.addEventListener('click', () => {{
  const listMode = corpusList.classList.toggle('list-mode');
  layoutBtn.textContent = listMode ? 'View: 1-column list' : 'View: 2-column cards';
}});

// Filtering
const qEl = document.getElementById('f-q');
const genreEl = document.getElementById('f-genre');
const discEl = document.getElementById('f-disc');
const stageEl = document.getElementById('f-stage');
const flEl = document.getElementById('f-fl');
const resetBtn = document.getElementById('f-reset');
const countEl = document.getElementById('f-count');
const cards = Array.from(document.querySelectorAll('.src-card'));

function applyFilters() {{
  const q = qEl.value.trim().toLowerCase();
  const g = genreEl.value;
  const d = discEl.value;
  const st = stageEl.value;
  const fl = flEl.value;
  let shown = 0;
  for (const c of cards) {{
    const ok =
      (!q || c.dataset.search.includes(q)) &&
      (!g || c.dataset.genre === g) &&
      (!d || c.dataset.disc === d) &&
      (!st || c.dataset.stages.split(' ').includes(st)) &&
      (!fl || c.dataset.fls.split(' ').includes(fl));
    c.hidden = !ok;
    if (ok) shown++;
  }}
  countEl.textContent = shown === cards.length
    ? `Showing all ${{cards.length}} sources`
    : `Showing ${{shown}} of ${{cards.length}} sources`;
}}


[qEl, genreEl, discEl, stageEl, flEl].forEach(el => el.addEventListener('input', applyFilters));
resetBtn.addEventListener('click', () => {{
  qEl.value = ''; genreEl.value = ''; discEl.value = ''; stageEl.value = ''; flEl.value = '';
  applyFilters();
}});

document.querySelectorAll('[data-stage-jump]').forEach(btn => {{
  btn.addEventListener('click', () => {{
    stageEl.value = btn.dataset.stageJump;
    applyFilters();
    document.getElementById('corpus').scrollIntoView({{ behavior: 'smooth' }});
  }});
}});

document.querySelectorAll('[data-fl-jump]').forEach(btn => {{
  btn.addEventListener('click', () => {{
    flEl.value = btn.dataset.flJump;
    applyFilters();
    document.getElementById('corpus').scrollIntoView({{ behavior: 'smooth' }});
  }});
}});

// Spotlight modal
const dlg = document.getElementById('spotlight');
const spBadges = document.getElementById('sp-badges');
const spTitle = document.getElementById('sp-title');
const spAuthors = document.getElementById('sp-authors');
const spSummary = document.getElementById('sp-summary');
const spQuote = document.getElementById('sp-quote');
const spLinks = document.getElementById('sp-links');
const spJump = document.getElementById('sp-jump');

function openSpotlight(id) {{
  const s = SOURCES[id];
  if (!s) return;
  const [gclass, glabel] = GENRE_META[s.source_type] || ['discourse', s.source_type];
  spBadges.innerHTML = `<span class="gdot dot-${{gclass}}"></span><span>${{glabel}} · ${{s.venue}} · ${{s.date || s.year}}</span>`;
  spTitle.textContent = s.title;
  spAuthors.textContent = s.authors;
  spSummary.textContent = s.summary;
  if (s.verbatim_excerpt) {{
    spQuote.hidden = false;
    const ve = s.verbatim_excerpt;
    spQuote.textContent = /^[“"‘]/.test(ve) ? ve : `“${{ve}}”`;
  }} else {{
    spQuote.hidden = true;
    spQuote.textContent = '';
  }}
  const links = [];
  if (s.doi) links.push(`<a href="https://doi.org/${{encodeURI(s.doi)}}" target="_blank" rel="noopener">DOI:${{s.doi}}</a>`);
  if (s.arxiv_id) links.push(`<a href="https://arxiv.org/abs/${{encodeURI(s.arxiv_id)}}" target="_blank" rel="noopener">arXiv:${{s.arxiv_id}}</a>`);
  links.push(`<a href="${{s.url}}" target="_blank" rel="noopener">Open primary source ↗</a>`);
  spLinks.innerHTML = links.join(' · ');

  spJump.href = `#src-${{id}}`;
  spJump.onclick = () => {{
    dlg.close();
    resetBtn.click();
    const target = document.getElementById(`src-${{id}}`);
    cards.forEach(c => c.classList.remove('highlight'));
    if (target) {{
      target.classList.add('highlight');
      const qt = target.querySelector('.src-quote');
      if (qt) qt.classList.add('is-open');
      setTimeout(() => target.scrollIntoView({{ behavior: 'smooth', block: 'center' }}), 50);
    }}
  }};
  dlg.showModal();
}}

document.querySelectorAll('[data-open-src]').forEach(btn => {{
  btn.addEventListener('click', () => openSpotlight(btn.dataset.openSrc));
}});
document.getElementById('sp-close').addEventListener('click', () => dlg.close());
dlg.addEventListener('click', (e) => {{ if (e.target === dlg) dlg.close(); }});
document.addEventListener('keydown', (e) => {{
  if (e.key === 'Escape') cards.forEach(c => c.classList.remove('highlight'));
}});
</script>
</body>
</html>
"""

    DOCS.mkdir(parents=True, exist_ok=True)
    n_2025_2026 = sum(1 for s in sources if int(s.get("year", 0)) >= 2025)
    export_payload = {
        "title": "Publishing Under AI (2025–2026)",
        "version": "1.1",
        "position_scale": "-2 argues for pole_a (the more cautious side: keep or tighten human control); +2 argues for pole_b (lets AI in or opens up the system); ±1 leans that way or mainly supplies evidence for it; 0 addresses the question without taking a side.",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "counts": {
            "sources": total_sources,
            "empirical_and_preprints": n_empirical,
            "editorials_and_comments": n_editorial,
            "blogs_sleuths_experiments": n_discourse_all,
            "social_posts": n_social,
            "sources_2025_2026": n_2025_2026,
            "with_verbatim_excerpt": n_verbatim,
            "fault_lines": len(fault_lines),
            "models": len(models),
        },
        "stages": STAGE_META,
        "shockwaves": shockwaves,
        "fault_lines": fault_lines,
        "models": models,
        "sources": sources,
        "licence": "Records (summaries, positions, card text): CC0 1.0. Verbatim excerpts belong to their authors and publishers and are quoted for comparison and criticism.",
    }
    (DOCS / "data.json").write_text(json.dumps(export_payload, indent=2, ensure_ascii=False), encoding="utf-8")
    (DOCS / "index.html").write_text(page_html, encoding="utf-8")

    essay_src = ROOT / "content" / "essay.md"
    if essay_src.exists():
        render_essay.render_essay(essay_src, DOCS, src_by_id, total_sources)
        print(
            f"Built {DOCS / 'index.html'}, {DOCS / 'essay.html'}, {DOCS / 'essay.md'}, and {DOCS / 'data.json'} successfully."
        )
    else:
        print(f"Built {DOCS / 'index.html'} and {DOCS / 'data.json'} successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(build())
