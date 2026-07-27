#!/usr/bin/env python3
"""
Full reading pipeline orchestrator.
Download → determine reading mode → save → sync Notion → update Wiki.
"""

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from readmap.config import cfg
from readmap.notion_client import find_paper_by_title, get_page_url

PAPERS_DIR = cfg.papers_dir


def fetch_paper(url_or_id: str) -> dict:
    """Download paper and return metadata."""
    script_dir = Path(__file__).parent
    result = subprocess.run(
        [sys.executable, "-m", "readmap.fetch_paper", url_or_id, "--output", str(PAPERS_DIR)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"[ERROR] fetch_paper failed: {result.stderr}")
        return {}
    try:
        lines = [l for l in result.stdout.strip().split("\n") if l.strip()]
        for line in reversed(lines):
            try:
                return json.loads(line)
            except Exception:
                continue
    except Exception:
        pass
    return {}


def build_output_path(metadata: dict, mode: str) -> Path:
    """Build output directory. Prefer fetch_paper's existing directory."""
    if metadata.get("pdf_path"):
        return Path(metadata["pdf_path"]).parent
    now = datetime.now()
    short_title = re.sub(r"[^\w\s-]", "", metadata.get("title", "untitled"))[:30].strip().replace(" ", "-")
    paper_dir = PAPERS_DIR / f"{now.year}-{now.month:02d}" / short_title
    paper_dir.mkdir(parents=True, exist_ok=True)
    return paper_dir


def save_markdown(paper_dir: Path, content: str, mode: str) -> Path:
    """Save Markdown file."""
    filename = {"quick-scan": "quick-scan.md", "standard": "standard.md", "deep-dive": "deep-dive.md"}.get(mode, "note.md")
    md_path = paper_dir / filename
    md_path.write_text(content, encoding="utf-8")
    return md_path


def sync_to_notion(md_path: Path, create_detail: bool = True) -> dict:
    """Sync to Notion."""
    script_dir = Path(__file__).parent
    result = subprocess.run(
        [sys.executable, "-m", "readmap.sync_notion", str(md_path)]
        + (["--no-clear"] if not create_detail else []),
        capture_output=True, text=True,
    )
    print(result.stdout)
    if result.returncode != 0:
        print(f"[WARN] Notion sync issues: {result.stderr}")

    content = md_path.read_text()
    title_match = re.search(r'^title:\s*"?([^"\n]+)"?', content, re.MULTILINE)
    title = title_match.group(1) if title_match else md_path.stem

    page_id = find_paper_by_title(title)
    if page_id:
        return {"page_id": page_id, "url": get_page_url(page_id)}
    return {}


def update_wiki(paper_dir: Path):
    """Update Wiki knowledge map."""
    script_dir = Path(__file__).parent
    result = subprocess.run(
        [sys.executable, "-m", "readmap.build_wiki",
         "--papers-dir", str(PAPERS_DIR),
         "--wiki-dir", str(cfg.wiki_dir),
         "--research-lines", cfg.research_lines],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        print("[OK] Wiki updated")
    else:
        print(f"[WARN] Wiki update: {result.stderr}")


def run_full_pipeline(url_or_id: str, mode: str | None = None):
    """
    Full pipeline:
      1. Download paper
      2. Determine reading mode
      3. Execute reading (performed by user with prompts)
      4. Save Markdown
      5. Sync to Notion
      6. Update Wiki
      7. Return results
    """
    print(f"\n{'=' * 60}")
    print("ReadMap — Full Pipeline")
    print(f"{'=' * 60}")
    print(f"URL: {url_or_id}")

    # Step 1: Download
    print("\n[1/5] Downloading paper...")
    metadata = fetch_paper(url_or_id)
    if not metadata:
        print("[ERROR] Failed to download paper")
        return
    print(f"  Title: {metadata.get('title', 'N/A')}")

    # Step 2: Determine mode
    if not mode:
        print("\n[2/5] Reading mode: 📖 Standard (default)")
        print("      Use --mode deep-dive for full 12-section analysis")
        mode = "standard"
    else:
        print(f"\n[2/5] Reading mode: {mode}")

    # Step 3: Reading
    print(f"\n[3/5] Running {mode} reading...")
    print("      (Perform deep reading using the prompts in prompts/)")

    paper_dir = build_output_path(metadata, mode)

    clean_md_path = metadata.get("clean_markdown_path")
    raw_md_path = metadata.get("markdown_path")
    if clean_md_path and Path(clean_md_path).exists():
        print(f"  ✓ Clean Markdown: {clean_md_path}")
        print(f"  ✓ Images: {metadata.get('images_dir', 'N/A')}")
        print(f"  Tip: Use paper_clean.md as reading input for best figure/table/formula quality")
    elif raw_md_path and Path(raw_md_path).exists():
        print(f"  ✓ Raw Markdown: {raw_md_path}")
        print(f"  ✓ Images: {metadata.get('images_dir', 'N/A')}")
        print(f"  Tip: Post-process skipped or failed; using raw MinerU output")
    else:
        print(f"  ⚠ No structured Markdown available, using raw PDF text only")

    # Step 4: Save
    print(f"\n[4/5] Saving to {paper_dir}")
    frontmatter_path = paper_dir / "deep-dive.md"
    if frontmatter_path.exists():
        print(f"  ✓ Frontmatter template: {frontmatter_path}")
        print(f"    Tip: Use this template for reading to ensure correct Notion metadata")

    # Step 5: Sync Notion
    print("\n[5/5] Syncing to Notion...")
    print("  (Run with --md-file <path> to auto-sync after reading)")

    print(f"\n{'=' * 60}")
    print("Pipeline setup complete.")
    print(f"Output dir: {paper_dir}")
    if frontmatter_path.exists():
        print(f"Frontmatter:  {frontmatter_path}")
    print(f"{'=' * 60}")

    return paper_dir


def main():
    parser = argparse.ArgumentParser(description="ReadMap — Full Pipeline")
    parser.add_argument("url_or_id", help="Paper URL or arXiv ID")
    parser.add_argument("--mode", choices=["quick-scan", "standard", "deep-dive"], help="Reading mode")
    parser.add_argument("--md-file", help="Path to pre-generated markdown file")
    parser.add_argument("--no-notion", action="store_true", help="Skip Notion sync")
    parser.add_argument("--no-wiki", action="store_true", help="Skip Wiki update")
    args = parser.parse_args()

    paper_dir = run_full_pipeline(args.url_or_id, args.mode)

    if args.md_file:
        md_path = Path(args.md_file)
        if md_path.exists():
            if not args.no_notion:
                notion_info = sync_to_notion(md_path, create_detail=(args.mode == "deep-dive"))
                print(f"\n📎 Notion URL: {notion_info.get('url', 'N/A')}")
            if not args.no_wiki:
                update_wiki(paper_dir)


if __name__ == "__main__":
    main()
