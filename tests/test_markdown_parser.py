"""Tests for the Markdown → Notion converter.

This module shipped without its imports or half its functions, so the first
regex it reached raised ``NameError``. These tests would have caught that on
import, and they pin the behaviours that were wrong once it ran.
"""

from pathlib import Path

from readmap.markdown_parser import (
    make_image_block,
    make_table_rows,
    markdown_to_notion_blocks,
    parse_inline,
)


def _types(blocks):
    return [b["type"] for b in blocks]


def test_module_is_importable_and_callable():
    """The published version raised NameError on its first regex."""
    assert markdown_to_notion_blocks("# Hi\n\nbody")[0]["type"] == "heading_1"


def test_checkboxes_are_to_do_blocks_not_bullets():
    """`- [x]` also matches the bullet pattern; ordering decided the outcome.

    The bullet branch ran first, so every checklist in every note — including
    the project roadmap — synced to Notion as plain bullets.
    """
    blocks = markdown_to_notion_blocks("- [x] done\n- [ ] pending\n- plain bullet\n")
    assert _types(blocks) == ["to_do", "to_do", "bulleted_list_item"]
    assert blocks[0]["to_do"]["checked"] is True
    assert blocks[1]["to_do"]["checked"] is False


def test_tables_round_trip_with_a_separator_row():
    rows = make_table_rows(["| a | b |", "|---|---|", "| 1 | 2 |"])
    assert len(rows) == 2  # the separator is not a row
    assert rows[0]["table_row"]["cells"][0][0]["text"]["content"] == "a"


def test_ragged_table_rows_are_padded():
    rows = make_table_rows(["| a | b | c |", "|---|---|---|", "| 1 |"])
    assert all(len(r["table_row"]["cells"]) == 3 for r in rows)


def test_evidence_tags_are_colour_coded():
    """Provenance has to be visible without reading the sentence around it."""
    colours = {}
    for item in parse_inline("值 [Paper/Table 2]，我推的 [My inference]，没核 [Unverified]"):
        if item.get("annotations", {}).get("code"):
            colours[item["text"]["content"]] = item["annotations"]["color"]
    assert colours["Paper/Table 2"] == "blue_background"
    assert colours["My inference"] == "orange_background"
    assert colours["Unverified"] == "red_background"


def test_markdown_links_are_not_mistaken_for_evidence_tags():
    items = parse_inline("see [Paper](https://example.com/x)")
    linked = [i for i in items if i.get("text", {}).get("link")]
    assert linked and linked[0]["text"]["link"]["url"] == "https://example.com/x"


def test_schemeless_links_do_not_become_invalid_notion_payloads():
    """Notion rejects a link without a scheme with an unhelpful 400."""
    items = parse_inline("see [x](papers/local.md)")
    assert all("link" not in i.get("text", {}) for i in items)


def test_local_images_become_visible_notes_not_blank_blocks():
    block = make_image_block("Figure 1", "figures/fig1.png")
    assert block["type"] == "callout"
    rendered = "".join(i.get("text", {}).get("content", "") for i in block["callout"]["rich_text"])
    assert "fig1.png" in rendered


def test_external_images_become_image_blocks():
    block = make_image_block("Figure 1", "https://example.com/f.png")
    assert block["type"] == "image"
    assert block["image"]["external"]["url"] == "https://example.com/f.png"


def test_rich_text_arrays_stay_within_notion_limits():
    long_text = " ".join(f"**b{i}**" for i in range(200))
    assert len(parse_inline(long_text)) <= 100


def test_frontmatter_is_stripped_from_the_body():
    blocks = markdown_to_notion_blocks('---\ntitle: "T"\n---\n\n# Heading\n')
    assert _types(blocks) == ["heading_1"]


def test_mermaid_blocks_keep_their_language():
    blocks = markdown_to_notion_blocks("```mermaid\ngraph TD\n  A --> B\n```\n")
    assert blocks[0]["code"]["language"] == "mermaid"
