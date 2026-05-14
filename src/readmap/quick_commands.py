#!/usr/bin/env python3
"""
Lightweight command entry points for single-function triggers.
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

from readmap.config import cfg

SCRIPT_DIR = Path(__file__).parent


def run_quick_scan(url_or_id: str):
    """5-minute quick scan."""
    print(f"\n⚡ Quick Scan: {url_or_id}")
    print("Run the quick-scan prompt (prompts/quick-scan.md) with your LLM.")
    print("\n[Next] Save result to ./papers/.../quick-scan.md")
    print("[Next] Run: python -m readmap.sync_notion ./papers/.../quick-scan.md")


def run_standard(url_or_id: str):
    """30-45 min Standard reading."""
    print(f"\n📖 Standard Reading: {url_or_id}")
    print("Run the standard prompt (prompts/standard.md) with your LLM.")
    print("\n[Next] Save result to ./papers/.../standard.md")
    print("[Next] Run: python -m readmap.sync_notion ./papers/.../standard.md")


def run_deep_dive(url_or_id: str):
    """Full Deep Dive reading."""
    print(f"\n🔬 Deep Dive: {url_or_id}")
    print("Run the deep-dive prompt (prompts/deep-dive.md) with your LLM.")
    print("\n[Next] Save result to ./papers/.../deep-dive.md")
    print("[Next] Run: python -m readmap.sync_notion ./papers/.../deep-dive.md --batch")


def run_sync(md_file: str, add_queue: bool = False):
    """Sync local Markdown to Notion."""
    result = subprocess.run(
        [sys.executable, "-m", "readmap.sync_notion", md_file],
        capture_output=True, text=True,
    )
    print(result.stdout)
    if result.stderr:
        print(result.stderr)


def run_reviewer_sim(url_or_id: str):
    """Standalone Reviewer Simulation."""
    print(f"\n👁️ Reviewer Simulation: {url_or_id}")
    print("Run the reviewer-simulation prompt (prompts/reviewer-simulation.md) with your LLM.")
    print("\nOutput format: Score table + 3 Weaknesses + Rebuttal strategy + Lessons")


def run_extract_concepts(md_file: str):
    """Extract new concepts from a reading note."""
    print(f"\n🧠 Extracting concepts from: {md_file}")
    content = Path(md_file).read_text()
    tags_match = re.search(r"^tags:\s*(.+)$", content, re.MULTILINE)
    if tags_match:
        tags = [t.strip() for t in tags_match.group(1).replace("，", ",").split(",")]
        print(f"Candidate concepts: {tags}")
        print("\n[Tip] Check your Notion concept card database for existing entries.")


def run_update_wiki():
    """Update Wiki knowledge map."""
    result = subprocess.run(
        [sys.executable, "-m", "readmap.build_wiki",
         "--papers-dir", str(cfg.papers_dir),
         "--wiki-dir", str(cfg.wiki_dir),
         "--research-lines", cfg.research_lines],
        capture_output=True, text=True,
    )
    print(result.stdout)


def main():
    parser = argparse.ArgumentParser(description="Paper Nexus — Quick Commands")
    sub = parser.add_subparsers(dest="command", help="Available commands")

    sub.add_parser("quick-scan", aliases=["scan"]).add_argument("url_or_id", help="Paper URL or arXiv ID")
    sub.add_parser("standard", aliases=["std"]).add_argument("url_or_id", help="Paper URL or arXiv ID")
    sub.add_parser("deep-dive", aliases=["dd"]).add_argument("url_or_id", help="Paper URL or arXiv ID")

    p_sync = sub.add_parser("sync")
    p_sync.add_argument("md_file", help="Path to markdown file")

    sub.add_parser("reviewer", aliases=["rev"]).add_argument("url_or_id", help="Paper URL or arXiv ID")
    sub.add_parser("extract-concepts", aliases=["concepts"]).add_argument("md_file", help="Path to markdown file")
    sub.add_parser("update-wiki", aliases=["wiki"])

    args = parser.parse_args()

    if args.command in ("quick-scan", "scan"):
        run_quick_scan(args.url_or_id)
    elif args.command in ("standard", "std"):
        run_standard(args.url_or_id)
    elif args.command in ("deep-dive", "dd"):
        run_deep_dive(args.url_or_id)
    elif args.command == "sync":
        run_sync(args.md_file)
    elif args.command in ("reviewer", "rev"):
        run_reviewer_sim(args.url_or_id)
    elif args.command in ("extract-concepts", "concepts"):
        run_extract_concepts(args.md_file)
    elif args.command in ("update-wiki", "wiki"):
        run_update_wiki()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
