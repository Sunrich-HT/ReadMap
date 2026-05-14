#!/usr/bin/env python3
"""
Notion sync — upload Markdown paper notes to your Notion literature database.

Uses native requests to call the Notion REST API.
"""

import argparse
import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from readmap.config import cfg
from readmap.markdown_parser import markdown_to_notion_blocks
from readmap.notion_client import (
    api_delete,
    api_get,
    api_patch,
    api_post,
    find_paper_by_title,
    get_page_url,
)
from readmap.notion_client import (
    PROP_AUTHORS,
    PROP_KEY_TAKEAWAY,
    PROP_QUICK_REF,
    PROP_READ_DATE,
    PROP_READ_STATUS,
    PROP_READING_MODE,
    PROP_RELEVANCE,
    PROP_REVIEWER_SCORE,
    PROP_TITLE,
    PROP_TOPICS,
    PROP_URL,
    PROP_YEAR,
)


def delete_all_blocks(page_id: str, max_workers: int = 4) -> int:
    """Delete all blocks under a page concurrently."""
    all_ids = []
    cursor = None
    while True:
        url = f"blocks/{page_id}/children?page_size=100"
        if cursor:
            url += f"&start_cursor={cursor}"
        r = api_get(url)
        for b in r.get("results", []):
            all_ids.append(b["id"])
        if not r.get("has_more"):
            break
        cursor = r.get("next_cursor")

    if not all_ids:
        return 0

    def del_one(bid: str):
        try:
            api_delete(f"blocks/{bid}")
        except Exception:
            pass

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        ex.map(del_one, all_ids)

    return len(all_ids)


def upload_blocks_to_notion(page_id: str, blocks: list[dict]) -> tuple[int, int]:
    """Upload blocks in batches (max 100). If a batch fails, retry one-by-one."""
    total = len(blocks)
    success = 0
    fail = 0
    for batch_idx in range(0, total, 100):
        batch = blocks[batch_idx : batch_idx + 100]
        try:
            result = api_patch(f"blocks/{page_id}/children", {"children": batch})
            if "results" in result:
                success += len(batch)
            else:
                fail += len(batch)
        except Exception as e:
            print(f"  Batch {batch_idx}-{batch_idx + len(batch)} failed: {e}")
            for idx, block in enumerate(batch):
                try:
                    result = api_patch(f"blocks/{page_id}/children", {"children": [block]})
                    if "results" in result:
                        success += 1
                    else:
                        fail += 1
                        print(f"    Block {batch_idx + idx} ({block.get('type')}) failed: no results")
                except Exception as e2:
                    fail += 1
                    block_json = json.dumps(block, ensure_ascii=False)[:300]
                    print(f"    Block {batch_idx + idx} ({block.get('type')}) failed: {e2}")
                    print(f"      Content: {block_json}")
    return success, fail


def parse_markdown_note(md_path: Path) -> dict:
    """Parse a local Markdown reading note."""
    content = md_path.read_text(encoding="utf-8")

    result = {
        "title": md_path.stem,
        "authors": "",
        "year": None,
        "venue": "",
        "url": "",
        "code_url": "",
        "mode": "standard",
        "tags": "",
        "reviewer_score": None,
        "relevance": "",
        "quick_ref": "",
        "content": content,
        "one_line_summary": "",
    }

    if content.startswith("---"):
        end = content.find("---", 3)
        if end != -1:
            fm_text = content[3:end].strip()
            result["content"] = content[end + 3 :].strip()
            for line in fm_text.split("\n"):
                if ":" in line:
                    key, val = line.split(":", 1)
                    key = key.strip()
                    val = val.strip().strip('"').strip("'")
                    if key == "title":
                        result["title"] = val
                    elif key == "authors":
                        result["authors"] = val
                    elif key == "year":
                        try:
                            result["year"] = int(val)
                        except Exception:
                            pass
                    elif key == "venue":
                        result["venue"] = val
                    elif key in ("url", "arxiv_url"):
                        result["url"] = val
                    elif key == "code_url":
                        result["code_url"] = val
                    elif key == "mode":
                        result["mode"] = val
                    elif key == "tags":
                        result["tags"] = val
                    elif key == "reviewer_score":
                        try:
                            result["reviewer_score"] = float(val)
                        except Exception:
                            pass
                    elif key == "relevance":
                        result["relevance"] = val

    summary_match = re.search(
        r"> \[!summary\].*?(?=\n## |\n---|\Z)", result["content"], re.DOTALL
    )
    if summary_match:
        result["quick_ref"] = (
            summary_match.group(0).replace("> ", "").replace("[!summary]", "").strip()
        )

    tldr = re.search(r"> \*\*一句话 TL;DR：\*\*(.*?)(?=\n|$)", result["content"])
    if tldr:
        result["one_line_summary"] = tldr.group(1).strip()
    else:
        tldr2 = re.search(r"一句话总结[:：](.*?)(?=\n|$)", result["content"])
        if tldr2:
            result["one_line_summary"] = tldr2.group(1).strip()

    return result


def build_paper_properties(info: dict) -> dict:
    """Build Notion database properties from parsed note metadata."""
    props = {}

    if info.get("title"):
        props[PROP_TITLE] = {"title": [{"text": {"content": info["title"]}}]}
    if info.get("authors"):
        props[PROP_AUTHORS] = {"rich_text": [{"text": {"content": info["authors"]}}]}
    if info.get("year"):
        props[PROP_YEAR] = {"number": info["year"]}
    if info.get("venue"):
        props[PROP_VENUE] = {"select": {"name": info["venue"]}}
    if info.get("url"):
        props[PROP_URL] = {"url": info["url"]}
    if info.get("one_line_summary"):
        props[PROP_KEY_TAKEAWAY] = {
            "rich_text": [{"text": {"content": info["one_line_summary"]}}]
        }

    props[PROP_READ_DATE] = {"date": {"start": datetime.now().strftime("%Y-%m-%d")}}
    props[PROP_READ_STATUS] = {"status": {"name": "精读完成"}}

    if info.get("mode"):
        mode_map = {
            "quick-scan": "⚡ 速扫",
            "standard": "📖 Standard",
            "deep-dive": "🔬 Deep Dive",
            "⚡ 速扫": "⚡ 速扫",
            "📖 Standard": "📖 Standard",
            "🔬 Deep Dive": "🔬 Deep Dive",
        }
        mapped = mode_map.get(info["mode"], info["mode"])
        props[PROP_READING_MODE] = {"select": {"name": mapped}}

    if info.get("reviewer_score") is not None:
        props[PROP_REVIEWER_SCORE] = {"number": info["reviewer_score"]}

    if info.get("relevance"):
        props[PROP_RELEVANCE] = {"select": {"name": info["relevance"]}}

    if info.get("quick_ref"):
        props[PROP_QUICK_REF] = {"rich_text": [{"text": {"content": info["quick_ref"]}}]}

    if info.get("tags"):
        tags = [t.strip() for t in info["tags"].replace("，", ",").split(",") if t.strip()]
        if tags:
            props[PROP_TOPICS] = {"multi_select": [{"name": t} for t in tags]}

    return props


def sync_paper_to_notion(md_path: Path, clear_existing: bool = True) -> str:
    """Sync a single paper note to the Notion literature database."""
    print(f"\n📄 Syncing: {md_path.name}")
    info = parse_markdown_note(md_path)
    print(f"  Title: {info['title']}")
    print(f"  Mode: {info['mode']}")
    print(f"  Reviewer Score: {info.get('reviewer_score', 'N/A')}")

    existing_id = find_paper_by_title(info["title"])
    properties = build_paper_properties(info)

    if existing_id:
        api_patch(f"pages/{existing_id}", {"properties": properties})
        page_id = existing_id
        print(f"  ✅ Updated DB entry: {page_id}")
    else:
        result = api_post(
            "pages",
            {"parent": {"database_id": cfg.notion.paper_db_id}, "properties": properties},
        )
        page_id = result["id"]
        print(f"  ✅ Created DB entry: {page_id}")

    blocks = markdown_to_notion_blocks(info["content"], md_path.parent)
    print(f"  Generated {len(blocks)} blocks")

    if clear_existing:
        deleted = delete_all_blocks(page_id)
        print(f"  Deleted {deleted} existing blocks")

    success, fail = upload_blocks_to_notion(page_id, blocks)
    print(f"  ✅ Uploaded: {success} OK, {fail} failed")

    return page_id


def main():
    parser = argparse.ArgumentParser(description="Sync paper notes to Notion")
    parser.add_argument("md_file", help="Path to markdown file or directory")
    parser.add_argument("--no-clear", action="store_true", help="Keep existing blocks")
    parser.add_argument("--batch", action="store_true", help="Batch sync directory")
    args = parser.parse_args()

    if args.batch:
        md_files = list(Path(args.md_file).rglob("*.md"))
        print(f"Found {len(md_files)} files")
        for f in md_files:
            if f.name.startswith("_"):
                continue
            try:
                sync_paper_to_notion(f, not args.no_clear)
            except Exception as e:
                print(f"  ❌ {e}")
    else:
        sync_paper_to_notion(Path(args.md_file), not args.no_clear)

    print("\n🎉 Done!")


if __name__ == "__main__":
    main()
