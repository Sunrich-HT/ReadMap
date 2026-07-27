"""Markdown → Notion block conversion.

This module was published without its imports or its helper functions, so
``markdown_to_notion_blocks`` raised ``NameError: name 're' is not defined`` on
the first line that used a regex. Everything below the converter is the missing
half, restored.

Beyond restoring it, the inline parser now recognises **evidence tags** —
``[Paper/Table 2]``, ``[Recomputed]``, ``[My inference]`` — and renders them as
coloured code spans, so a claim's provenance is visible at a glance instead of
having to be reconstructed from prose.
"""

from __future__ import annotations

import base64
import hashlib
import mimetypes
import os
import re
from pathlib import Path

import requests

from readmap.config import cfg

# ---------------------------------------------------------------------------
# Evidence tags
# ---------------------------------------------------------------------------
#
# The distinction a reading note has to preserve is not "what does the paper
# say" but "how do I know this". A number quoted from a table, a number the
# reader recomputed, and a number the reader inferred all look identical once
# they are prose. These tags keep them apart, and the colour makes the weakest
# ones impossible to skim past.

EVIDENCE_COLOURS = {
    "paper": "blue",
    "appendix": "blue",
    "code": "green",
    "recomputed": "purple",
    "inference": "orange",
    "unverified": "red",
}

EVIDENCE_PATTERNS = [
    (re.compile(r"^Paper\b", re.I), "paper"),
    (re.compile(r"^Appendix\b", re.I), "appendix"),
    (re.compile(r"^Code\b", re.I), "code"),
    (re.compile(r"^Recomputed\b", re.I), "recomputed"),
    (re.compile(r"^(?:My inference|Inference|Inferred)\b", re.I), "inference"),
    (re.compile(r"^Unverified\b", re.I), "unverified"),
]

# `[Paper/Table 2]` but not `[text](url)` — a markdown link is not a tag.
EVIDENCE_TAG_RE = re.compile(r"\[((?:Paper|Appendix|Code|Recomputed|My inference|Inference|Inferred|Unverified)[^\]\[]*)\](?!\()", re.I)


def evidence_kind(tag_text: str) -> str | None:
    for pattern, kind in EVIDENCE_PATTERNS:
        if pattern.match(tag_text.strip()):
            return kind
    return None


# ---------------------------------------------------------------------------
# Inline formatting
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(
    r"(?P<evidence>\[(?:Paper|Appendix|Code|Recomputed|My inference|Inference|Inferred|Unverified)[^\]\[]*\](?!\())"
    r"|(?P<link>\[[^\]]+\]\([^)]+\))"
    r"|(?P<code>`[^`]+`)"
    r"|(?P<bold>\*\*[^*]+\*\*)"
    r"|(?P<italic>(?<!\*)\*(?!\*)[^*]+\*(?!\*))"
    r"|(?P<math>\$[^$\n]+\$)",
)

NOTION_TEXT_LIMIT = 1900


def _text_item(content: str, *, bold=False, italic=False, code=False,
               colour: str | None = None, link: str | None = None) -> dict:
    annotations: dict = {}
    if bold:
        annotations["bold"] = True
    if italic:
        annotations["italic"] = True
    if code:
        annotations["code"] = True
    if colour:
        annotations["color"] = colour
    item: dict = {"type": "text", "text": {"content": content[:NOTION_TEXT_LIMIT]}}
    if link:
        item["text"]["link"] = {"url": link}
    if annotations:
        item["annotations"] = annotations
    return item


def parse_inline(text: str) -> list[dict]:
    """Convert inline Markdown into Notion rich-text items.

    Notion rejects a rich_text array longer than 100 items and any single item
    longer than 2000 characters, so both limits are enforced here rather than
    discovered as a 400 halfway through an upload.
    """
    if not text:
        return [_text_item("")]

    items: list[dict] = []
    cursor = 0
    for match in _TOKEN_RE.finditer(text):
        if match.start() > cursor:
            items.append(_text_item(text[cursor:match.start()]))
        kind = match.lastgroup
        raw = match.group()

        if kind == "evidence":
            inner = raw[1:-1]
            colour = EVIDENCE_COLOURS.get(evidence_kind(inner) or "", "gray")
            items.append(_text_item(inner, code=True, colour=f"{colour}_background"))
        elif kind == "link":
            label, url = re.match(r"\[([^\]]+)\]\(([^)]+)\)", raw).groups()
            # Notion rejects a link without a scheme with an unhelpful 400.
            items.append(_text_item(label, link=url) if "://" in url else _text_item(f"{label} ({url})"))
        elif kind == "code":
            items.append(_text_item(raw[1:-1], code=True))
        elif kind == "bold":
            items.append(_text_item(raw[2:-2], bold=True))
        elif kind == "italic":
            items.append(_text_item(raw[1:-1], italic=True))
        elif kind == "math":
            items.append({"type": "equation", "equation": {"expression": raw[1:-1]}})
        cursor = match.end()

    if cursor < len(text):
        items.append(_text_item(text[cursor:]))

    items = [i for i in items if i.get("type") == "equation" or i["text"]["content"]]
    if not items:
        return [_text_item("")]
    if len(items) > 100:
        # Collapse the tail rather than losing it to Notion's array limit.
        head, tail = items[:99], items[99:]
        tail_text = "".join(t.get("text", {}).get("content", "") for t in tail)
        head.append(_text_item(tail_text))
        items = head
    return items


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------

def _split_row(line: str) -> list[str]:
    cells = line.strip().strip("|").split("|")
    return [c.strip() for c in cells]


def _is_separator(line: str) -> bool:
    return bool(re.fullmatch(r"\|?[\s:\-|]+\|?", line.strip())) and "-" in line


def make_table_rows(table_lines: list[str]) -> list[dict]:
    """Build Notion ``table_row`` children from Markdown table lines."""
    rows = [ln for ln in table_lines if not _is_separator(ln)]
    if not rows:
        return []
    width = max(len(_split_row(ln)) for ln in rows)
    children = []
    for line in rows:
        cells = _split_row(line)
        cells += [""] * (width - len(cells))
        children.append({
            "object": "block",
            "type": "table_row",
            "table_row": {"cells": [parse_inline(c) for c in cells[:width]]},
        })
    return children


# ---------------------------------------------------------------------------
# Images
# ---------------------------------------------------------------------------

_IMGUR_UPLOAD = "https://api.imgur.com/3/image"


def make_image_block(alt_text: str, url: str) -> dict:
    """An image block, or a caption-bearing paragraph when the URL is unusable.

    Notion only accepts externally reachable http(s) URLs. A local path silently
    becomes a broken block, so an unresolvable image is turned into visible text
    naming the file instead of a blank space in the page.
    """
    if url.startswith(("http://", "https://")):
        block = {
            "object": "block",
            "type": "image",
            "image": {"type": "external", "external": {"url": url}},
        }
        if alt_text:
            block["image"]["caption"] = parse_inline(alt_text)
        return block
    label = alt_text or Path(url).name
    return {
        "object": "block",
        "type": "callout",
        "callout": {
            "rich_text": parse_inline(f"🖼 Local image not uploaded: `{url}` — {label}"),
            "icon": {"type": "emoji", "emoji": "🖼"},
        },
    }


def _upload_to_imgur(path: Path) -> str | None:
    if not cfg.imgur.enabled:
        return None
    try:
        payload = base64.b64encode(path.read_bytes())
        resp = requests.post(
            _IMGUR_UPLOAD,
            headers={"Authorization": f"Client-ID {cfg.imgur.client_id}"},
            data={"image": payload, "type": "base64"},
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()["data"]["link"]
    except Exception as exc:  # network, quota, malformed response
        print(f"  [WARN] Imgur upload failed for {path.name}: {exc}")
        return None


def resolve_image_url(url: str, base_dir: Path, cache: dict[str, str]) -> str:
    """Turn a local image reference into something Notion can display.

    Uploads via Imgur when configured, caching by content hash so the same
    figure referenced from several sections is uploaded once. Without an Imgur
    client id the original path is returned unchanged and
    :func:`make_image_block` renders it as a visible note.
    """
    if url.startswith(("http://", "https://", "data:")):
        return url

    candidate = (base_dir / url).resolve() if not os.path.isabs(url) else Path(url)
    if not candidate.exists():
        return url

    digest = hashlib.sha256(candidate.read_bytes()).hexdigest()
    if digest in cache:
        return cache[digest]

    mime, _ = mimetypes.guess_type(candidate.name)
    if mime and not mime.startswith("image/"):
        return url

    uploaded = _upload_to_imgur(candidate)
    if uploaded:
        cache[digest] = uploaded
        return uploaded
    return url


# ---------------------------------------------------------------------------
# Main converter
# ---------------------------------------------------------------------------

def markdown_to_notion_blocks(content: str, base_dir: Path | None = None) -> list[dict]:
    """Convert Markdown content to Notion block objects.

    Args:
        content: Markdown text.
        base_dir: Directory of the Markdown file, used to resolve local image paths.
    """
    blocks = []
    code_lines = []
    code_lang = ""
    table_lines = []
    in_code_block = False
    _imgur_cache: dict[str, str] = {}

    # Strip YAML frontmatter
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            content = parts[2].strip()

    lines = content.split("\n")
    i = 0

    def flush_code():
        nonlocal code_lines, code_lang
        if not code_lines:
            code_lines = []
            code_lang = ""
            return
        if "latex" in code_lang.lower():
            for cline in code_lines:
                cline = cline.strip()
                if not cline:
                    continue
                if cline.startswith("%"):
                    text = cline[1:].strip()
                    if text:
                        blocks.append({
                            "object": "block",
                            "type": "paragraph",
                            "paragraph": {"rich_text": parse_inline(text)},
                        })
                else:
                    blocks.append({
                        "object": "block",
                        "type": "equation",
                        "equation": {"expression": cline},
                    })
        else:
            code_text = "\n".join(code_lines)
            if len(code_text) > 1900:
                code_text = code_text[:1900] + "\n... [truncated]"
            blocks.append({
                "object": "block",
                "type": "code",
                "code": {
                    "rich_text": [{"type": "text", "text": {"content": code_text}}],
                    "language": "mermaid" if "mermaid" in code_lang.lower() else "plain text",
                },
            })
        code_lines = []
        code_lang = ""

    def flush_table():
        nonlocal table_lines
        if len(table_lines) >= 2:
            header = [c.strip() for c in table_lines[0].split("|")[1:-1]]
            table_width = len(header)
            if table_width > 0:
                blocks.append({
                    "object": "block",
                    "type": "table",
                    "table": {
                        "table_width": table_width,
                        "has_column_header": True,
                        "has_row_header": False,
                        "children": make_table_rows(table_lines),
                    },
                })
        table_lines = []

    def flush_quote(quote_lines: list[str]) -> dict | None:
        if not quote_lines:
            return None
        while quote_lines and not quote_lines[-1]:
            quote_lines.pop()
        if not quote_lines:
            return None
        quote_text = "\n".join(quote_lines)
        if len(quote_text) > 1900:
            quote_text = quote_text[:1900] + "..."
        return {
            "object": "block",
            "type": "quote",
            "quote": {"rich_text": parse_inline(quote_text)},
        }

    while i < len(lines):
        line = lines[i]

        img_match = re.match(r"^!\[(.*?)\]\((.*?)\)$", line.strip())
        if img_match:
            flush_table()
            alt_text = img_match.group(1)
            img_url = img_match.group(2)
            if base_dir:
                img_url = resolve_image_url(img_url, base_dir, _imgur_cache)
            blocks.append(make_image_block(alt_text, img_url))
            i += 1
            continue

        if line.strip().startswith("```"):
            if in_code_block:
                flush_code()
                in_code_block = False
            else:
                flush_table()
                in_code_block = True
                code_lang = line.strip()[3:]
            i += 1
            continue

        if in_code_block:
            code_lines.append(line)
            i += 1
            continue

        if line.strip().startswith("|") and "|" in line.strip()[1:]:
            table_lines.append(line.strip())
            i += 1
            continue
        elif table_lines:
            flush_table()

        if not line.strip():
            i += 1
            continue

        heading_match = re.match(r"^(#{1,4})\s+(.*)$", line)
        if heading_match:
            level = len(heading_match.group(1))
            text = heading_match.group(2).strip()
            block_type = f"heading_{min(level, 3)}"
            blocks.append({
                "object": "block",
                "type": block_type,
                block_type: {"rich_text": parse_inline(text)},
            })
            i += 1
            continue

        callout_match = re.match(r"> \[!(\w+)\]\s*(.*)", line)
        if callout_match:
            icon_type = callout_match.group(1).lower()
            text = callout_match.group(2)
            j = i + 1
            while j < len(lines) and lines[j].lstrip().startswith(">"):
                raw = lines[j].lstrip()
                content_q = raw[1:].lstrip()
                if re.match(r"^!\[(.*?)\]\((.*?)\)$", content_q):
                    break
                text += "\n" + content_q
                j += 1
            icon_map = {
                "note": "💡", "tip": "💡", "info": "ℹ️", "warning": "⚠️",
                "caution": "⚠️", "summary": "📋", "important": "⭐",
                "verdict": "⚖️", "evidence": "🔍",
            }
            blocks.append({
                "object": "block", "type": "callout",
                "callout": {
                    "rich_text": parse_inline(text),
                    "icon": {"type": "emoji", "emoji": icon_map.get(icon_type, "💬")},
                },
            })
            i = j
            continue

        raw_lstrip = line.lstrip()
        if raw_lstrip.startswith(">"):
            quote_lines = []
            while i < len(lines):
                raw = lines[i].lstrip()
                if not raw.startswith(">"):
                    break
                content_q = raw[1:].lstrip()
                img_in_quote = re.match(r"^!\[(.*?)\]\((.*?)\)$", content_q)
                if img_in_quote:
                    q = flush_quote(quote_lines)
                    if q:
                        blocks.append(q)
                    quote_lines = []
                    blocks.append(make_image_block(img_in_quote.group(1), img_in_quote.group(2)))
                else:
                    if content_q or quote_lines:
                        quote_lines.append(content_q)
                i += 1
            q = flush_quote(quote_lines)
            if q:
                blocks.append(q)
            continue

        # Checklists must be tested before plain bullets: "- [x] done" also
        # matches the bullet pattern, and whichever runs first wins.
        td = re.match(r"^\s*[-*]\s+\[(.)\]\s+(.*)", line)
        if td:
            blocks.append({
                "object": "block",
                "type": "to_do",
                "to_do": {
                    "rich_text": parse_inline(td.group(2)),
                    "checked": td.group(1).lower() == "x",
                },
            })
            i += 1
            continue

        if line.strip().startswith("- ") or line.strip().startswith("* "):
            item_text = line.strip()[2:]
            blocks.append({
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {"rich_text": parse_inline(item_text)},
            })
            i += 1
            continue

        m = re.match(r"^(\d+)\.\s+(.+)$", line.strip())
        if m:
            item_text = m.group(2)
            blocks.append({
                "object": "block",
                "type": "numbered_list_item",
                "numbered_list_item": {"rich_text": parse_inline(item_text)},
            })
            i += 1
            continue

        if line.strip() == "---":
            blocks.append({"object": "block", "type": "divider", "divider": {}})
            i += 1
            continue

        para_lines = [line]
        i += 1
        while i < len(lines) and lines[i].strip():
            stripped = lines[i].strip()
            if (re.match(r"^(#{1,4})\s", stripped) or
                stripped.startswith(("- ", "* ")) or
                lines[i].lstrip().startswith(">") or
                stripped.startswith(("|", "```", "---", "![")) or
                re.match(r"^\d+\.", stripped)):
                break
            para_lines.append(lines[i])
            i += 1

        para_text = " ".join(para_lines)
        if len(para_text) > 1900:
            para_text = para_text[:1900] + "..."
        blocks.append({
            "object": "block",
            "type": "paragraph",
            "paragraph": {"rich_text": parse_inline(para_text)},
        })

    flush_table()
    flush_code()
    return blocks
