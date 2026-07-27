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
    PROP_VENUE,
    PROP_YEAR,
)
from readmap.notion_client import (
    PROP_CLOSURE,
    PROP_DOC_TYPE,
    PROP_EVIDENCE_LEVEL,
    PROP_PROJECT_RELATION,
    PROP_RELATION_REASON,
    PROP_SCORE_NORM,
    PROP_SCORE_SCALE,
    PROP_VERDICT,
)
from readmap.schema import (
    CLOSURE_BY_KEY,
    DOC_TYPES,
    EVIDENCE_LEVELS,
    PROJECT_RELATIONS,
    VERDICTS,
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
    """Parse a local Markdown reading note.

    Delegates front-matter parsing to :mod:`readmap.notes` so the gate, the
    composer and this sync all read a note the same way.
    """
    from readmap.notes import one_line_summary, parse_note

    meta, body = parse_note(md_path)
    result = {
        "title": meta.title,
        "authors": meta.authors,
        "year": meta.year,
        "venue": meta.venue,
        "url": meta.url,
        "mode": _mode_from(meta),
        "tags": ", ".join(meta.tags),
        "reviewer_score": meta.score,
        "score_scale": meta.score_scale,
        "score_normalised": meta.score_normalised,
        "doc_type": meta.doc_type,
        "evidence_level": meta.evidence_level,
        "project_relation": meta.project_relation,
        "relation_reason": meta.relation_reason,
        "closure": meta.closure,
        "verdict": meta.verdict,
        "relevance": "",
        "quick_ref": "",
        "content": body,
        "one_line_summary": one_line_summary(body),
    }
    summary_match = re.search(r"> \[!summary\].*?(?=\n## |\n---|\Z)", body, re.DOTALL)
    if summary_match:
        result["quick_ref"] = (
            summary_match.group(0).replace("> ", "").replace("[!summary]", "").strip()
        )
    return result


def _mode_from(meta) -> str:
    """Map evidence level onto the legacy reading-mode column."""
    return {"L1": "quick-scan", "L2": "standard"}.get(meta.evidence_level, "deep-dive")


def _legacy_parse_markdown_note(md_path: Path) -> dict:
    """The previous hand-rolled front-matter reader, kept for reference."""
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


# Venue is a curated select. arXiv primary categories ("cs.CL", "stat.ML") are
# not venues, and writing them straight through adds a new option per category —
# the same mechanism that filled the topic property with bracket fragments.
_ARXIV_CATEGORY = re.compile(r"^(?:cs|stat|math|physics|q-bio|q-fin|eess|econ)\.[A-Za-z-]+$")
_KNOWN_VENUES = {
    "neurips": "NeurIPS", "icml": "ICML", "iclr": "ICLR", "acl": "ACL",
    "emnlp": "EMNLP", "aaai": "AAAI", "jcim": "JCIM", "nature": "Nature",
    "science": "Science", "anthropic": "Anthropic", "openai": "OpenAI",
    "arxiv": "arXiv",
}


def _normalise_venue(raw: str) -> str:
    raw = (raw or "").strip()
    if not raw:
        return ""
    if _ARXIV_CATEGORY.match(raw):
        return "arXiv"
    return _KNOWN_VENUES.get(raw.lower(), raw)


def build_paper_properties(info: dict) -> dict:
    """Build Notion database properties from parsed note metadata."""
    props = {}

    if info.get("title"):
        props[PROP_TITLE] = {"title": [{"text": {"content": info["title"]}}]}
    if info.get("authors"):
        props[PROP_AUTHORS] = {"rich_text": [{"text": {"content": info["authors"]}}]}
    if info.get("year"):
        props[PROP_YEAR] = {"number": info["year"]}
    venue = _normalise_venue(info.get("venue", ""))
    if venue:
        props[PROP_VENUE] = {"select": {"name": venue}}
    if info.get("url"):
        props[PROP_URL] = {"url": info["url"]}
    if info.get("one_line_summary"):
        props[PROP_KEY_TAKEAWAY] = {
            "rich_text": [{"text": {"content": info["one_line_summary"]}}]
        }

    props[PROP_READ_DATE] = {"date": {"start": datetime.now().strftime("%Y-%m-%d")}}
    # Reading status must follow the mode. Writing "精读完成" for every sync
    # marked five-minute scans as completed deep reads.
    # These names must exist as options on the Notion status property, which
    # offers 待读 / 在读 / 深度精读中 / 已读 / 精读完成. Writing a name that is not
    # in the list does not fail loudly — it quietly adds another option, which
    # is how a vocabulary drifts out of control.
    status_by_mode = {
        "quick-scan": "已读",
        "standard": "精读完成",
        "deep-dive": "精读完成",
    }
    props[PROP_READ_STATUS] = {
        "status": {"name": status_by_mode.get(info.get("mode", ""), "精读完成")}
    }

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
        # Strip bracket and quote residue: topic columns had picked up `[paper`
        # and `debate]` from lists that were stringified rather than serialised.
        raw = info["tags"].strip().strip("[]")
        tags = [t.strip().strip("\"'[]") for t in raw.replace("，", ",").split(",")]
        tags = [t for t in tags if t]
        if tags:
            props[PROP_TOPICS] = {"multi_select": [{"name": t} for t in tags]}

    _add_schema_properties(props, info)
    return props


def _add_schema_properties(props: dict, info: dict) -> None:
    """Write the fields that separate length from evidence.

    Each is a select with a fixed vocabulary, so the database can be sorted and
    filtered on them instead of on how long the page is.
    """
    doc_type = info.get("doc_type")
    if doc_type in DOC_TYPES:
        props[PROP_DOC_TYPE] = {"select": {"name": DOC_TYPES[doc_type]}}

    level = (info.get("evidence_level") or "").upper()
    if level in EVIDENCE_LEVELS:
        props[PROP_EVIDENCE_LEVEL] = {"select": {"name": level}}

    relation = info.get("project_relation")
    if relation in PROJECT_RELATIONS:
        props[PROP_PROJECT_RELATION] = {"select": {"name": relation}}
    if info.get("relation_reason"):
        props[PROP_RELATION_REASON] = {
            "rich_text": [{"text": {"content": info["relation_reason"][:1900]}}]
        }

    closure = info.get("closure")
    if closure in CLOSURE_BY_KEY:
        props[PROP_CLOSURE] = {"select": {"name": CLOSURE_BY_KEY[closure]}}

    verdict = info.get("verdict")
    if verdict in VERDICTS:
        props[PROP_VERDICT] = {"select": {"name": VERDICTS[verdict]}}

    # A bare reviewer number is meaningless across notes that mix 5- and
    # 10-point scales, so store the scale and a normalised value alongside it.
    scale = info.get("score_scale")
    if scale in (5, 10):
        props[PROP_SCORE_SCALE] = {"select": {"name": f"{scale} 分制"}}
    if info.get("score_normalised") is not None:
        props[PROP_SCORE_NORM] = {"number": info["score_normalised"]}


def sync_paper_to_notion(md_path: Path, clear_existing: bool = False) -> str:
    """Sync a single paper note to the Notion literature database.

    ``clear_existing`` defaults to False. It deletes every block on the page
    before uploading, so any annotation or comment added inside Notion is lost —
    that is a reasonable thing to ask for, and an unreasonable thing to do by
    default.
    """
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
    parser.add_argument("--no-clear", action="store_true",
                        help="Deprecated: keeping existing blocks is now the default")
    parser.add_argument("--replace", action="store_true",
                        help="Delete existing page blocks before uploading (destroys manual edits)")
    parser.add_argument("--batch", action="store_true", help="Batch sync directory")
    args = parser.parse_args()

    if args.batch:
        md_files = list(Path(args.md_file).rglob("*.md"))
        print(f"Found {len(md_files)} files")
        for f in md_files:
            if f.name.startswith("_"):
                continue
            try:
                sync_paper_to_notion(f, args.replace)
            except Exception as e:
                print(f"  ❌ {e}")
    else:
        sync_paper_to_notion(Path(args.md_file), args.replace)

    print("\n🎉 Done!")


if __name__ == "__main__":
    main()
