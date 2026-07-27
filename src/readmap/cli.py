#!/usr/bin/env python3
"""ReadMap command line.

``readmap read <url>`` runs the whole retrieval half in one command: fetch the
source, parse it, extract every figure and table, and lay down the eight-question
skeleton with the exhibit catalogue attached. Reading itself is yours. Then
``readmap gate`` and ``readmap sync`` close the loop.

Commands that never touch Notion run without credentials configured — the
previous entry point could not even print its own help on a fresh checkout.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from readmap import figures as figures_mod
from readmap.config import ConfigError, cfg


def _die(message: str) -> int:
    print(f"error: {message}", file=sys.stderr)
    return 2


def _slug(text: str, limit: int = 48) -> str:
    text = re.sub(r"[^\w\s一-鿿-]", "", text or "")
    return re.sub(r"[\s_]+", "-", text.strip())[:limit].strip("-") or "untitled"


# ---------------------------------------------------------------------------
# read: fetch → parse → figures → skeleton
# ---------------------------------------------------------------------------

def cmd_read(args) -> int:
    from readmap.compose import write_note
    from readmap.fetch_paper import extract_arxiv_id, fetch_arxiv, fetch_web_article
    from readmap.schema import DOC_TYPES, EVIDENCE_LEVELS, ReadingMeta

    if args.doc_type not in DOC_TYPES:
        return _die(f"unknown doc-type {args.doc_type!r} (choose from {', '.join(DOC_TYPES)})")
    if args.level not in EVIDENCE_LEVELS:
        return _die(f"unknown evidence level {args.level!r} (L1–L5)")

    papers_dir = Path(args.output or cfg.papers_dir)
    source = args.source

    print(f"[1/3] Fetching {source}")
    arxiv_id = extract_arxiv_id(source)
    try:
        if arxiv_id:
            meta_raw = fetch_arxiv(arxiv_id, papers_dir / arxiv_id, backend=args.backend)
            note_dir = papers_dir / arxiv_id
        else:
            meta_raw = fetch_web_article(source, papers_dir)
            note_dir = Path(meta_raw.get("output_dir") or papers_dir / _slug(source))
    except Exception as exc:
        return _die(f"could not fetch source: {exc}")

    meta = ReadingMeta(
        title=meta_raw.get("title", ""),
        authors=", ".join(meta_raw.get("authors", []) or []),
        year=int(meta_raw["published"][:4]) if meta_raw.get("published") else None,
        venue=meta_raw.get("primary_category", ""),
        url=meta_raw.get("abs_url") or meta_raw.get("url") or source,
        doc_type=args.doc_type,
        evidence_level=args.level,
        tags=[t for t in [meta_raw.get("primary_category", "")] if t],
    )
    print(f"      {meta.title or '(untitled)'}")

    print("[2/3] Extracting figures and tables")
    fs = None
    if args.figures and cfg.figures.enabled:
        fs = figures_mod.extract(
            str(meta_raw.get("pdf_path") or source),
            note_dir / "figures",
            dpi=args.dpi,
            kinds=args.kinds,
            tiers=args.tiers,
        )
        print(f"      {figures_mod.summarise(fs)}")
        if fs.note and fs.available:
            print(f"      note: {fs.note}")
    else:
        print("      skipped (--no-figures)")

    print("[3/3] Composing the reading skeleton")
    path = write_note(meta, fs, note_dir, filename=args.filename, overwrite=args.force)
    print(f"      {path}")

    print()
    print("Next:")
    print(f"  1. Read the paper and fill in {path.name} (八问结构，证据标签必填)")
    print(f"  2. readmap gate {path}")
    print(f"  3. readmap sync {path}")
    return 0


# ---------------------------------------------------------------------------
# gate
# ---------------------------------------------------------------------------

def cmd_gate(args) -> int:
    from readmap.gate import check
    from readmap.notes import parse_note

    targets = _collect(Path(args.path))
    if not targets:
        return _die(f"no markdown notes under {args.path}")

    failed = 0
    for path in targets:
        meta, body = parse_note(path)
        report = check(meta, body, strict=not args.lenient)
        print(report.render(path))
        if not report.passed:
            failed += 1
    print()
    print(f"{len(targets) - failed}/{len(targets)} passed")
    return 1 if failed else 0


def _collect(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    return sorted(p for p in path.rglob("*.md") if not p.name.startswith("_"))


# ---------------------------------------------------------------------------
# figures (standalone)
# ---------------------------------------------------------------------------

def cmd_figures(args) -> int:
    fs = figures_mod.extract(
        args.source, Path(args.out), dpi=args.dpi, kinds=args.kinds, tiers=args.tiers
    )
    print(figures_mod.summarise(fs))
    if args.json:
        print(json.dumps({"counts": fs.counts, "items": fs.items}, indent=2, ensure_ascii=False))
    return 0 if fs.available else 1


# ---------------------------------------------------------------------------
# sync / wiki
# ---------------------------------------------------------------------------

def cmd_sync(args) -> int:
    from readmap.gate import check
    from readmap.notes import parse_note
    from readmap.sync_notion import sync_paper_to_notion

    if not cfg.notion.configured:
        return _die("Notion is not configured; copy .env.example to .env and fill it in")

    targets = _collect(Path(args.path))
    for path in targets:
        if not args.skip_gate:
            meta, body = parse_note(path)
            report = check(meta, body, strict=False)
            if not report.passed:
                print(report.render(path))
                print("  → 未同步。修复后重试，或加 --skip-gate 强制同步。")
                continue
        try:
            sync_paper_to_notion(path, clear_existing=args.replace)
        except ConfigError as exc:
            return _die(str(exc))
    return 0


def cmd_wiki(args) -> int:
    from readmap.build_wiki import main as wiki_main

    if not cfg.notion.configured:
        return _die("Notion is not configured; the wiki is generated from the Notion database")
    sys.argv = ["build_wiki", "--wiki-dir", args.wiki_dir or str(cfg.wiki_dir),
                "--research-lines", args.research_lines or cfg.research_lines]
    wiki_main()
    return 0


# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="readmap", description="ReadMap — paper reading pipeline")
    sub = p.add_subparsers(dest="command", required=True)

    r = sub.add_parser("read", help="Fetch, extract figures, and lay down the reading skeleton")
    r.add_argument("source", help="arXiv URL/ID, OpenReview/ACL link, PDF URL, or article URL")
    r.add_argument("--level", default="L1", help="Starting evidence level (L1–L5, default L1)")
    r.add_argument("--doc-type", dest="doc_type", default="paper-reading",
                   help="paper-reading / radar / tutorial / replication")
    r.add_argument("--kinds", default=None, help="Exhibit kinds to extract (default: all)")
    r.add_argument("--tiers", default=None, help="Triage tiers to render (default: all)")
    r.add_argument("--dpi", type=int, default=None)
    r.add_argument("--no-figures", dest="figures", action="store_false",
                   help="Skip figure and table extraction")
    r.add_argument("--backend", default="pipeline", help="MinerU backend")
    r.add_argument("--output", "-o", default=None, help="Papers directory")
    r.add_argument("--filename", default="reading.md")
    r.add_argument("--force", action="store_true", help="Overwrite an existing skeleton")
    r.set_defaults(func=cmd_read)

    g = sub.add_parser("gate", help="Check a note before filing it")
    g.add_argument("path", help="Markdown file or directory")
    g.add_argument("--lenient", action="store_true", help="Allow unfilled placeholders")
    g.set_defaults(func=cmd_gate)

    f = sub.add_parser("figures", help="Extract figures and tables only")
    f.add_argument("source")
    f.add_argument("--out", default="./figures")
    f.add_argument("--dpi", type=int, default=None)
    f.add_argument("--kinds", default=None)
    f.add_argument("--tiers", default=None)
    f.add_argument("--json", action="store_true")
    f.set_defaults(func=cmd_figures)

    s = sub.add_parser("sync", help="Sync a note to Notion (runs the gate first)")
    s.add_argument("path")
    s.add_argument("--replace", action="store_true",
                   help="Delete existing page blocks before uploading (destroys manual edits)")
    s.add_argument("--skip-gate", action="store_true")
    s.set_defaults(func=cmd_sync)

    w = sub.add_parser("wiki", help="Rebuild the wiki knowledge map from Notion")
    w.add_argument("--wiki-dir", default=None)
    w.add_argument("--research-lines", default=None)
    w.set_defaults(func=cmd_wiki)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args) or 0
    except ConfigError as exc:
        return _die(str(exc))
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
