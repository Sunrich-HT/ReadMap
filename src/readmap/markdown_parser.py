

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

        td = re.match(r"^- \[(.)\]\s+(.*)", line)
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
