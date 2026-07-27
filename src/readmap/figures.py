"""Figure and table extraction, delegated to figure-extractor.

Extraction is exhaustive: every exhibit the document labels is pulled out. Which
of them belong in a reading note is a separate question, decided while reading —
a figure the authors cite six times may still be decorative, and one cited once
may carry the whole claim. The tier recorded here is a triage signal for that
decision, never a substitute for it.

figure-extractor is an optional dependency. When it is absent the pipeline
continues and says so, following the degraded-mode contract the tool documents:
missing bitmaps are a stated gap, not a silent one.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from readmap.config import cfg


@dataclass
class FigureSet:
    """What extraction produced, and what it could not."""

    available: bool
    out_dir: Path | None
    items: list[dict]
    counts: dict
    note: str = ""

    @property
    def usable(self) -> list[dict]:
        """Items with a file on disk and a crop worth looking at."""
        return [
            i for i in self.items
            if i.get("output") and i.get("status") in {"ok", "suspect"}
        ]

    def by_tier(self, tier: str) -> list[dict]:
        return [i for i in self.usable if i.get("suggested_tier") == tier]

    @property
    def needs_review(self) -> list[dict]:
        return [i for i in self.items if i.get("status") in {"suspect", "failed"}]


def _find_cli() -> str | None:
    """Locate the figure-extractor CLI, preferring this interpreter's env."""
    candidate = Path(sys.executable).parent / "figure-extractor"
    if candidate.exists():
        return str(candidate)
    return shutil.which("figure-extractor")


def available() -> bool:
    return _find_cli() is not None


INSTALL_HINT = (
    "figure-extractor not installed — figures and tables were not extracted.\n"
    "  Install it with:  pip install git+https://github.com/Sunrich-HT/figure-extractor\n"
    "  Reading continues; cite figures by page number until it is available."
)


def extract(source: str, out_dir: Path, *, dpi: int | None = None,
            kinds: str | None = None, tiers: str | None = None,
            timeout: int = 900) -> FigureSet:
    """Extract every figure and table from ``source`` into ``out_dir``."""
    cli = _find_cli()
    if cli is None:
        return FigureSet(available=False, out_dir=None, items=[], counts={}, note=INSTALL_HINT)

    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        cli, "extract", source,
        "--out", str(out_dir),
        "--dpi", str(dpi or cfg.figures.dpi),
        "--kinds", kinds or cfg.figures.kinds,
        "--tiers", tiers or cfg.figures.tiers,
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return FigureSet(False, out_dir, [], {}, f"figure extraction timed out after {timeout}s")

    manifest_path = out_dir / "manifest.json"
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            return FigureSet(False, out_dir, [], {}, f"manifest unreadable: {exc}")
    elif proc.returncode != 0:
        # Surface the extractor's own diagnosis rather than a generic failure —
        # it distinguishes "the server refused us" from "no figures here".
        reason = (proc.stderr or proc.stdout or "").strip().splitlines()
        return FigureSet(False, out_dir, [], {}, reason[-1] if reason else "extraction failed")
    else:
        return FigureSet(False, out_dir, [], {}, "extractor produced no manifest")

    items = manifest.get("figures", [])
    counts = manifest.get("counts", {})
    note = ""
    dropped = manifest.get("dropped") or []
    if dropped:
        note = f"{len(dropped)} candidate(s) were not extracted; see manifest 'dropped' for reasons"
    return FigureSet(True, out_dir, items, counts, note)


def summarise(fs: FigureSet) -> str:
    """A short human-readable status line."""
    if not fs.available:
        return f"⚠ figures: {fs.note}"
    c = fs.counts
    parts = [f"{c.get('rendered', len(fs.usable))} extracted"]
    if c.get("figures") is not None:
        parts.append(f"{c['figures']} figures / {c.get('tables', 0)} tables")
    if c.get("suspect") or c.get("failed"):
        parts.append(f"⚠ {c.get('suspect', 0)} suspect, {c.get('failed', 0)} failed — check contact_sheet.jpg")
    return "figures: " + ", ".join(parts)


def catalogue_markdown(fs: FigureSet, note_dir: Path) -> str:
    """A reference table of every exhibit, for the reader to select from.

    Deliberately a catalogue, not an insertion: dropping every figure into the
    note is how a page ends up with ninety images and an argument that uses
    four. The reader moves the ones that carry the argument into the body.
    """
    if not fs.available:
        return f"> [!warning] 图表未提取\n> {fs.note}\n"
    if not fs.usable:
        return "> [!note] 本文未检出可提取的图表。\n"

    lines = [
        "> [!note] 图表目录（抠取穷尽，选用由你决定）",
        "> tier 只反映正文引用频次，不代表它是否承载论证。",
        "",
        "| 编号 | 页 | 引用次数 | tier | 状态 | 文件 | Caption |",
        "|---|---|---|---|---|---|---|",
    ]
    for item in sorted(fs.items, key=lambda i: (i.get("page", 0), str(i.get("label")))):
        out = item.get("output")
        rel = Path(out).relative_to(note_dir) if out and Path(out).is_relative_to(note_dir) else (Path(out).name if out else "—")
        caption = (item.get("caption") or "").replace("|", "\\|")[:80]
        lines.append(
            f"| {item.get('label', '?')} | {item.get('page', '—')} | "
            f"{item.get('referenced_in_body', '—')} | {item.get('suggested_tier', '—')} | "
            f"{item.get('status', '—')} | `{rel}` | {caption} |"
        )
    if fs.needs_review:
        lines += ["", f"> ⚠ {len(fs.needs_review)} 张裁剪存疑或失败，引用前请先核对 `contact_sheet.jpg`。"]
    return "\n".join(lines) + "\n"
