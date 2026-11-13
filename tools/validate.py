#!/usr/bin/env python3
"""Schema, cross-reference, and provenance validator for the Publishing Under AI observatory.

Inspired by MichaLie/journal-ai-policies and MichaLie/agent-risk-atlas:
- Every record must carry a verified identifier/URL (never constructed by pattern).
- Verbatim excerpts cannot claim metadata-only provenance.
- Fault-line coordinates and model links must resolve cleanly.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

VALID_STAGES = {
    "writing",
    "citations",
    "submission_triage",
    "peer_review",
    "post_pub_audit",
    "publishing_model",
}

VALID_SOURCE_TYPES = {
    "empirical_study",
    "preprint",
    "editorial_comment",
    "journal_news_feature",
    "perspective_essay",
    "blog_essay",
    "watchdog_investigation",
    "live_experiment",
    "institutional_experiment",
    "community_thread_writeup",
    "social_post",
}

VALID_DISCIPLINES = {
    "biomed_lifesci",
    "cs_ml",
    "cross_disciplinary",
}

TEXT_PROVENANCES = {
    "arxiv_api",
    "europepmc_api",
    "europepmc_fulltext",
    "europepmc_abstract",
    "crossref_abstract",
    "crossref_plus_open_page",
    "fulltext_pdf",
    "publisher_html",
    "publisher_preview_paragraph",
    "live_html",
    "rss_feed",
    "browser_dom",
}

METADATA_ONLY_PROVENANCES = {
    "crossref_metadata_only",
    "crossref_api",
}

VALID_PROVENANCES = TEXT_PROVENANCES | METADATA_ONLY_PROVENANCES

SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$")


def load_yaml(path: Path):
    if not path.exists():
        raise FileNotFoundError(f"Missing required data file: {path}")
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def main() -> int:
    errors: list[str] = []

    fault_lines = load_yaml(DATA / "fault_lines.yml") or []
    models = load_yaml(DATA / "models.yml") or []
    sources = load_yaml(DATA / "sources.yml") or []
    shockwaves = load_yaml(DATA / "shockwaves.yml") if (DATA / "shockwaves.yml").exists() else []

    fl_ids: set[str] = set()
    for fl in fault_lines:
        fid = fl.get("id", "")
        if not fid or fid in fl_ids:
            errors.append(f"fault_lines.yml: duplicate or empty id '{fid}'")
        fl_ids.add(fid)
        if fl.get("stage") not in VALID_STAGES:
            errors.append(f"fault_lines.yml [{fid}]: invalid stage '{fl.get('stage')}'")
        for pole in ("pole_a", "pole_b"):
            p = fl.get(pole) or {}
            if not p.get("label") or not p.get("summary"):
                errors.append(f"fault_lines.yml [{fid}]: {pole} missing label or summary")

    model_ids: set[str] = set()
    for m in models:
        mid = m.get("id", "")
        if not mid or mid in model_ids:
            errors.append(f"models.yml: duplicate or empty id '{mid}'")
        model_ids.add(mid)
        if m.get("stage") not in VALID_STAGES:
            errors.append(f"models.yml [{mid}]: invalid stage '{m.get('stage')}'")
        for fid in m.get("fault_lines", []):
            if fid not in fl_ids:
                errors.append(f"models.yml [{mid}]: unknown fault line '{fid}'")

    if not sources:
        errors.append("sources.yml: corpus is empty")

    src_ids: set[str] = set()
    for idx, s in enumerate(sources, start=1):
        sid = s.get("id", "")
        label = sid or f"row#{idx}"
        if not sid or not SLUG_RE.match(sid):
            errors.append(f"sources.yml [{label}]: id must be kebab-case")
        if sid in src_ids:
            errors.append(f"sources.yml [{label}]: duplicate id '{sid}'")
        src_ids.add(sid)

        for req in ("title", "authors", "venue", "summary"):
            if not str(s.get(req, "")).strip():
                errors.append(f"sources.yml [{label}]: missing '{req}'")

        year = s.get("year")
        if not isinstance(year, int) or year < 2023 or year > 2027:
            errors.append(f"sources.yml [{label}]: invalid year '{year}'")

        stype = s.get("source_type")
        if stype not in VALID_SOURCE_TYPES:
            errors.append(f"sources.yml [{label}]: invalid source_type '{stype}'")

        disc = s.get("discipline_scope")
        if disc not in VALID_DISCIPLINES:
            errors.append(f"sources.yml [{label}]: invalid discipline_scope '{disc}'")

        stages = s.get("pipeline_stages") or []
        if not stages:
            errors.append(f"sources.yml [{label}]: pipeline_stages must be non-empty")
        for st in stages:
            if st not in VALID_STAGES:
                errors.append(f"sources.yml [{label}]: invalid stage '{st}'")

        url = s.get("url")
        doi = s.get("doi")
        arxiv_id = s.get("arxiv_id")
        if not url or not str(url).startswith(("http://", "https://")):
            errors.append(f"sources.yml [{label}]: missing or invalid http(s) url")
        elif "/search/" in str(url) or "?keywords=" in str(url):
            errors.append(f"sources.yml [{label}]: search-query URL not allowed as citation permalink '{url}'")
        if doi is not None and not DOI_RE.match(str(doi)):
            errors.append(f"sources.yml [{label}]: malformed DOI '{doi}'")
        if arxiv_id is not None and not str(arxiv_id).strip():
            errors.append(f"sources.yml [{label}]: empty arxiv_id string (use null)")

        prov = s.get("provenance")
        if prov not in VALID_PROVENANCES:
            errors.append(f"sources.yml [{label}]: invalid provenance '{prov}'")

        excerpt = s.get("verbatim_excerpt")
        if excerpt:
            if prov in METADATA_ONLY_PROVENANCES:
                errors.append(
                    f"sources.yml [{label}]: verbatim_excerpt present under metadata-only provenance '{prov}'"
                )
            if len(str(excerpt).strip()) < 20:
                errors.append(f"sources.yml [{label}]: verbatim_excerpt suspiciously short")

        positions = s.get("positions") or {}
        if not isinstance(positions, dict):
            errors.append(f"sources.yml [{label}]: 'positions' must be a mapping (it may be empty)")
        else:
            for fid, score in positions.items():
                if fid not in fl_ids:
                    errors.append(f"sources.yml [{label}]: unknown fault line '{fid}' in positions")
                if score not in (-2, -1, 0, 1, 2):
                    errors.append(
                        f"sources.yml [{label}]: position score '{score}' for {fid} must be in -2..+2"
                    )

        for mid in s.get("related_models") or []:
            if mid not in model_ids:
                errors.append(f"sources.yml [{label}]: unknown model '{mid}' in related_models")

    for sw in shockwaves:
        swid = sw.get("id", "")
        if sw.get("stage") not in VALID_STAGES:
            errors.append(f"shockwaves.yml [{swid}]: invalid stage '{sw.get('stage')}'")
        for evid in sw.get("evidence_ids") or []:
            if evid not in src_ids:
                errors.append(f"shockwaves.yml [{swid}]: unknown evidence_id '{evid}'")

    essay_path = ROOT / "content" / "essay.md"
    essay_cites = 0
    if essay_path.exists():
        raw_essay = essay_path.read_text(encoding="utf-8")
        if not raw_essay.startswith("---\n"):
            errors.append("content/essay.md: missing YAML frontmatter block")
        else:
            parts = raw_essay.split("---\n", 2)
            if len(parts) < 3:
                errors.append("content/essay.md: malformed YAML frontmatter block")
            else:
                fm = yaml.safe_load(parts[1]) or {}
                for k in ("title", "subtitle", "authors", "byline_note"):
                    if not str(fm.get(k, "")).strip():
                        errors.append(f"content/essay.md: frontmatter missing '{k}'")
                body = parts[2]
                for m in re.finditer(r"\[\[([a-z0-9-]+)\|([^\]]+)\]\]", body):
                    cid, clabel = m.group(1), m.group(2).strip()
                    essay_cites += 1
                    if cid not in src_ids:
                        errors.append(f"content/essay.md: cited source '{cid}' not found in sources.yml")
                    if not clabel:
                        errors.append(f"content/essay.md: empty anchor text for '{cid}'")
                for m in re.finditer(r"index\.html#(F\d+)", body):
                    if m.group(1) not in fl_ids:
                        errors.append(f"content/essay.md: unknown fault line anchor '#{m.group(1)}'")

    if errors:
        print(f"VALIDATION FAILED ({len(errors)} issue(s)):", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    with_quotes = sum(1 for s in sources if s.get("verbatim_excerpt"))
    essay_msg = f", essay citation keys resolved ({essay_cites} inline citations)" if essay_path.exists() else ""
    print(
        f"OK · {len(sources)} structurally valid source records ({with_quotes} with verbatim excerpts), "
        f"{len(fault_lines)} fault lines, {len(models)} proposed models{essay_msg}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
