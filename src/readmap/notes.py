"""Reading and writing note files: front matter in, :class:`ReadingMeta` out.

Front matter used to be parsed inline in the sync step with a hand-rolled
``line.split(":", 1)``, which meant every consumer re-implemented it slightly
differently and none of them knew about the schema fields. Parsing lives here so
the gate, the sync and the composer all agree on what a note says.
"""

from __future__ import annotations

import re
from pathlib import Path

from readmap.schema import ReadingMeta, normalise_relation

_FM_LINE = re.compile(r"^(?P<key>[A-Za-z_][\w-]*)\s*:\s*(?P<value>.*)$")


def split_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Return (front matter mapping, body).

    Comment lines are skipped: the generated skeleton documents each field
    inline with ``#`` comments, and treating those as data produced keys like
    ``# 证据等级 L1–L5``.
    """
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    raw = text[3:end]
    body = text[end + 4:].lstrip("\n")

    data: dict[str, str] = {}
    for line in raw.split("\n"):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        m = _FM_LINE.match(stripped)
        if not m:
            continue
        value = m.group("value").strip()
        if "#" in value and not value.startswith(("\"", "'")):
            value = value.split("#", 1)[0].strip()
        data[m.group("key")] = value.strip().strip('"').strip("'")
    return data, body


def _as_int(value: str) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _as_float(value: str) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_tags(value: str) -> list[str]:
    """Split a tag field, tolerating the shapes that reach real notes.

    Topic columns had picked up ``[paper`` and ``debate]`` fragments from lists
    that were stringified rather than serialised, so bracket and quote residue
    is stripped rather than carried into the database.
    """
    if not value:
        return []
    cleaned = value.strip().strip("[]")
    parts = re.split(r"[,，]", cleaned.replace("，", ","))
    out = []
    for part in parts:
        tag = part.strip().strip("\"'[]").strip()
        if tag:
            out.append(tag)
    return out


def parse_note(path: Path) -> tuple[ReadingMeta, str]:
    text = path.read_text(encoding="utf-8")
    fm, body = split_frontmatter(text)

    meta = ReadingMeta(
        title=fm.get("title", "") or path.stem,
        authors=fm.get("authors", ""),
        year=_as_int(fm.get("year", "")),
        venue=fm.get("venue", ""),
        url=fm.get("url", "") or fm.get("arxiv_url", ""),
        doc_type=fm.get("doc_type", "paper-reading") or "paper-reading",
        evidence_level=(fm.get("evidence_level", "L1") or "L1").upper(),
        project_relation=normalise_relation(fm.get("project_relation", "")),
        relation_reason=fm.get("relation_reason", ""),
        closure=fm.get("closure", "reading-done") or "reading-done",
        verdict=fm.get("verdict", ""),
        score=_as_float(fm.get("score", "") or fm.get("reviewer_score", "")),
        score_scale=_as_int(fm.get("score_scale", "5")) or 5,
        tags=_as_tags(fm.get("tags", "")),
    )
    return meta, body


def one_line_summary(body: str) -> str:
    """The verdict line, for the database's Key Takeaway column."""
    for pattern in (
        r"> \[!summary\][^\n]*\n>\s*(.+)",
        r"> \[!verdict\][^\n]*\n>\s*(.+)",
        r"\*\*一句话 ?TL;DR：?\*\*\s*(.+)",
        r"一句话总结[:：]\s*(.+)",
    ):
        m = re.search(pattern, body)
        if m:
            text = m.group(1).strip().lstrip("> ").strip()
            if text and "（待填写）" not in text:
                return text
    return ""
