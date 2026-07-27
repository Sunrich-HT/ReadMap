"""Quality gate: refuse to file a note that misreports itself.

Every check here corresponds to something that reached a real page and then had
to be found by hand: a stray ``zaza`` after a TL;DR, escape residue from an
automated writer, topic tags carrying ``[paper`` and ``debate]`` fragments from
a stringified list, reviewer scores mixing 5-point and 10-point conventions in
one numeric column, and the same conclusion restated in the opening callout, the
body and the quick-reference card — three places to update and three places to
drift apart.

The gate blocks on things that would corrupt the database or misstate evidence,
and warns about things that only cost effort.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path

from readmap.schema import CLOSURE_BY_KEY, ReadingMeta, normalise_relation

BLOCK = "block"
WARN = "warn"


@dataclass
class Finding:
    level: str
    message: str
    line: int | None = None

    def render(self) -> str:
        where = f" (line {self.line})" if self.line else ""
        mark = "✗" if self.level == BLOCK else "!"
        return f"  {mark} {self.message}{where}"


@dataclass
class GateReport:
    findings: list[Finding] = field(default_factory=list)

    @property
    def blocking(self) -> list[Finding]:
        return [f for f in self.findings if f.level == BLOCK]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if f.level == WARN]

    @property
    def passed(self) -> bool:
        return not self.blocking

    def render(self, path: Path) -> str:
        if not self.findings:
            return f"✓ {path.name}: 通过"
        lines = [f"{'✓' if self.passed else '✗'} {path.name}: "
                 f"{len(self.blocking)} 阻断 / {len(self.warnings)} 提醒"]
        lines += [f.render() for f in self.findings]
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Text hygiene
# ---------------------------------------------------------------------------

# Short alphabetic runs sitting alone on a line, adjacent to no punctuation.
# Automated writers leave these behind; a human sentence almost never is one.
_ORPHAN_RE = re.compile(r"^\s*([a-z]{3,10})\s*$")
_ORPHAN_ALLOW = {"todo", "tbd", "n/a", "na", "etc", "ibid"}

# Include `<`: real notes carry both `\>` and `\<` from automated writers,
# and a character class that covers only one direction misses half of them.
_ESCAPE_RESIDUE_RE = re.compile(r"\\[<>^~#*_`|\[\]]")
_INTERNAL_LINK_RE = re.compile(r"\]\(([^)]*\b(?:SKILL\.md|CLAUDE\.md|\.claude/)[^)]*)\)")
_BROKEN_NOTION_URL_RE = re.compile(r"https://[^\s)]*notion[^\s)]*[?&]pvs=\d+[^\s)]*\)")


def _check_text_hygiene(body: str) -> list[Finding]:
    out: list[Finding] = []
    for n, line in enumerate(body.split("\n"), 1):
        m = _ORPHAN_RE.match(line)
        if m and m.group(1).lower() not in _ORPHAN_ALLOW:
            out.append(Finding(BLOCK, f"疑似生成残留的孤立词: {m.group(1)!r}", n))
        if _ESCAPE_RESIDUE_RE.search(line):
            found = set(_ESCAPE_RESIDUE_RE.findall(line))
            out.append(Finding(WARN, f"Markdown 转义残留: {' '.join(sorted(found))}", n))
        if _INTERNAL_LINK_RE.search(line):
            out.append(Finding(WARN, "正文链接指向内部文件（SKILL.md / .claude/），对外不可解析", n))
    return out


# ---------------------------------------------------------------------------
# Duplication
# ---------------------------------------------------------------------------

def _sections(body: str) -> dict[str, str]:
    out: dict[str, str] = {}
    current = "_preamble"
    buf: list[str] = []
    for line in body.split("\n"):
        if line.startswith("#"):
            out[current] = "\n".join(buf)
            current = line.strip("# ").strip()
            buf = []
        else:
            buf.append(line)
    out[current] = "\n".join(buf)
    return out


def _normalise(text: str) -> str:
    text = re.sub(r"[`*_>|#\-\[\]()]", " ", text)
    return " ".join(text.split()).lower()


def _check_duplication(body: str) -> list[Finding]:
    """Flag conclusions restated verbatim in several places.

    Restating the verdict in the opening callout, the body and a quick-reference
    card inflates the page without adding information, and guarantees the three
    copies disagree after the first revision.
    """
    # 60 characters, not 120: Chinese prose carries far more meaning per
    # character, and three verbatim copies of a conclusion came to 78.
    sections = {k: _normalise(v) for k, v in _sections(body).items() if len(_normalise(v)) > 60}
    names = list(sections)
    out: list[Finding] = []
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            ratio = SequenceMatcher(None, sections[a][:1200], sections[b][:1200]).ratio()
            if ratio > 0.72:
                out.append(Finding(
                    WARN,
                    f"「{a}」与「{b}」内容重复约 {ratio:.0%} —— "
                    f"结论只保留一处，速查卡交给数据库字段承担",
                ))
    return out


# ---------------------------------------------------------------------------
# Evidence discipline
# ---------------------------------------------------------------------------

_TAGGED_RE = re.compile(r"\[(?:Paper|Appendix|Code|Recomputed|My inference|Inference|Inferred|Unverified)[^\]]*\]", re.I)
# A number carrying a unit or decimal — the kind a claim rests on.
_CLAIM_NUMBER_RE = re.compile(r"(?<![\w.])\d+\.\d+\s*%?|(?<![\w.])\d{2,}\s*%")


# Section numbering ("3.1", "**4.2**", "1.") is not a claim about the world.
_SECTION_NUMBER_RE = re.compile(r"^[\s>*_#\-]*\d+(?:\.\d+)*[\s.、·:：)]")


def _check_evidence_tags(body: str) -> list[Finding]:
    out: list[Finding] = []
    untagged = 0
    for n, line in enumerate(body.split("\n"), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith(("|---", "#", "```")):
            continue
        scannable = _SECTION_NUMBER_RE.sub("", stripped, count=1)
        if _CLAIM_NUMBER_RE.search(scannable) and not _TAGGED_RE.search(stripped):
            untagged += 1
            if untagged <= 3:
                out.append(Finding(WARN, f"含具体数字但无证据标签，将按 [Unverified] 计: {stripped[:56]!r}", n))
    if untagged > 3:
        out.append(Finding(WARN, f"另有 {untagged - 3} 处数字缺少证据标签"))
    return out


# ---------------------------------------------------------------------------
# Decision closure
# ---------------------------------------------------------------------------

_DECISION_RE = re.compile(r"^\s*-\s*\[[xX]\]\s*(引用|改 ?claim|改实验|登记不行动|最小验证实验)")


def _check_closure(body: str, meta: ReadingMeta) -> list[Finding]:
    decided = [m.group(1) for m in (_DECISION_RE.match(ln) for ln in body.split("\n")) if m]
    out: list[Finding] = []
    if len(decided) > 1:
        out.append(Finding(WARN, f"下一步勾选了 {len(decided)} 项（{', '.join(decided)}）—— 只应有一项"))
    if not decided and meta.closure != "reading-done":
        out.append(Finding(
            BLOCK,
            f"closure 标为「{CLOSURE_BY_KEY.get(meta.closure, meta.closure)}」，"
            f"但正文没有勾选任何决策项 —— 写完报告不等于问题闭环",
        ))
    if not meta.verdict:
        out.append(Finding(WARN, "verdict 为空 —— 最终判决必须落到那七个选项之一"))
    return out


def _check_placeholders(body: str) -> list[Finding]:
    remaining = body.count("（待填写）")
    if remaining:
        return [Finding(BLOCK, f"仍有 {remaining} 处「（待填写）」未完成")]
    return []


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def check(meta: ReadingMeta, body: str, *, strict: bool = True) -> GateReport:
    """Run every gate over one note."""
    report = GateReport()
    report.findings += [Finding(BLOCK, m) for m in meta.problems()]
    report.findings += _check_text_hygiene(body)
    report.findings += _check_evidence_tags(body)
    report.findings += _check_closure(body, meta)
    report.findings += _check_duplication(body)
    if strict:
        report.findings += _check_placeholders(body)

    # A radar sweep is not a paper reading; letting it claim verified evidence
    # is exactly how an automated survey ends up looking as trustworthy as a
    # paper whose code was inspected.
    if meta.doc_type == "radar" and meta.evidence_level not in ("L1", "L2"):
        report.findings.append(Finding(
            BLOCK,
            f"doc_type=radar 但 evidence_level={meta.evidence_level} —— "
            f"多源综述无法达到图表/代码核验等级",
        ))
    if meta.project_relation != normalise_relation(meta.project_relation):
        report.findings.append(Finding(
            WARN,
            f"project_relation={meta.project_relation!r} 已归一为 "
            f"{normalise_relation(meta.project_relation)!r}",
        ))
    return report
