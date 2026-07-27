"""The reading schema: the distinctions a note must make explicit.

A twelve-section document and a two-paragraph summary look equally authoritative
once both are filed under "Deep Dive". Length is not evidence strength, a
reminder is not a citation, and a written report is not a closed question — but
none of those distinctions survive unless the schema forces them.

Each field here exists to stop a specific confusion:

``doc_type``          a multi-source radar sweep is not a paper reading
``evidence_level``    how far verification actually went, independent of length
``project_relation``  defaults to *none*, so relevance must be argued for
``closure``           report written vs. question closed
``verdict``           what the work is, chosen from a closed list
``score`` + ``scale`` a 4/5 and a 4/10 are not the same number
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Document type
# ---------------------------------------------------------------------------
# A radar sweep, a tutorial and a single-paper reading have different evidential
# standing. Filing them under one label makes an automated survey look like a
# verified reading of a specific paper.

DOC_TYPES = {
    "paper-reading": "单篇精读",
    "radar": "Radar 综述",
    "tutorial": "自主教程",
    "replication": "复现报告",
}

# ---------------------------------------------------------------------------
# Evidence level
# ---------------------------------------------------------------------------
# The point of the ladder is that it is orthogonal to how much was written. L1
# can be three pages; L4 can be three paragraphs.

EVIDENCE_LEVELS = {
    "L1": "L1 摘要整理 — 基于摘要/二手描述",
    "L2": "L2 原文核验 — 读过正文，关键论断已回原文定位",
    "L3": "L3 图表核验 — 关键数字已对照图表/附录核对",
    "L4": "L4 代码数据核验 — 已检查代码或数据，确认与论文描述一致",
    "L5": "L5 局部复现 — 已自行跑通关键实验的一部分",
}

# ---------------------------------------------------------------------------
# Relation to the reader's own work
# ---------------------------------------------------------------------------
# The default is *none*. A paper has to earn its way into a project: being
# thought-provoking is not the same as changing a claim, an experiment, or a
# citation list. Defaulting to "relevant" is how every paper ends up mapped onto
# whatever project is currently open.

PROJECT_RELATIONS = {
    "none": "none — 当前无直接关系",
    "cite": "Cite — 可进入正文 / Related Work / Limitation",
    "design": "Design — 改变实验设计（增对照 / 改指标 / 加压力测试）",
    "warning": "Warning — 暴露了本方案的具体失效模式",
    "analogy": "Analogy — 仅跨领域类比，不进入当前项目",
}

RELATION_REQUIREMENTS = {
    "cite": "必须能指出进入哪一节（Related Work / Method / Experiment / Limitation）",
    "design": "必须能说出增加哪个对照、改哪个指标、删哪个实验或加哪个压力测试",
    "warning": "必须指出我们的哪个测量、假设或结论可能失效",
    "analogy": "承认仅为思考素材，不进入当前项目",
    "none": "无需理由",
}

# ---------------------------------------------------------------------------
# Decision closure
# ---------------------------------------------------------------------------
# "精读完成" used to mean "the document is written". These states separate
# writing from closing, so a high-value open question cannot hide inside a
# finished-looking page.

CLOSURE_STATES = [
    ("reading-done", "阅读完成"),
    ("evidence-checked", "证据核验完成"),
    ("replicated", "复现完成"),
    ("transferred", "迁移实验完成"),
    ("in-paper", "已进入论文"),
]
CLOSURE_BY_KEY = dict(CLOSURE_STATES)

# ---------------------------------------------------------------------------
# Verdict
# ---------------------------------------------------------------------------
# A closed list, so the judgement cannot dissolve into hedging prose.

VERDICTS = {
    "breakthrough": "真突破",
    "solid-increment": "扎实增量",
    "engineering": "工程整合",
    "benchmark": "评测贡献",
    "interesting-unproven": "有趣但证据不足",
    "overpackaged": "包装大于贡献",
    "undecidable": "当前无法判断",
}

# ---------------------------------------------------------------------------
# Evidence tags used inline in the body
# ---------------------------------------------------------------------------

EVIDENCE_TAGS = [
    "[Paper/Fig N]", "[Paper/Table N]", "[Paper/§N]",
    "[Appendix X.Y]", "[Code inspected]", "[Recomputed]",
    "[My inference]", "[Unverified]",
]


@dataclass
class ReadingMeta:
    """Validated front-matter for one reading note."""

    title: str = ""
    authors: str = ""
    year: int | None = None
    venue: str = ""
    url: str = ""
    doc_type: str = "paper-reading"
    evidence_level: str = "L1"
    project_relation: str = "none"
    relation_reason: str = ""
    closure: str = "reading-done"
    verdict: str = ""
    score: float | None = None
    score_scale: int = 5
    tags: list[str] = field(default_factory=list)
    figures_used: list[str] = field(default_factory=list)

    @property
    def score_normalised(self) -> float | None:
        """Score on a 0-1 scale.

        Reviewer scores were stored as a bare number while notes mixed 5-point
        and 10-point conventions, so sorting the database compared 4/5 against
        4/10 as if they were the same.
        """
        if self.score is None or not self.score_scale:
            return None
        return round(self.score / self.score_scale, 3)

    def problems(self) -> list[str]:
        """Everything wrong with this metadata, in plain language."""
        issues: list[str] = []
        if not self.title.strip():
            issues.append("缺少 title")
        if self.doc_type not in DOC_TYPES:
            issues.append(f"doc_type 非法: {self.doc_type!r}（可选 {', '.join(DOC_TYPES)}）")
        if self.evidence_level not in EVIDENCE_LEVELS:
            issues.append(f"evidence_level 非法: {self.evidence_level!r}（L1–L5）")
        if self.project_relation not in PROJECT_RELATIONS:
            issues.append(f"project_relation 非法: {self.project_relation!r}")
        elif self.project_relation != "none" and not self.relation_reason.strip():
            issues.append(
                f"project_relation={self.project_relation} 需要 relation_reason —— "
                f"{RELATION_REQUIREMENTS[self.project_relation]}"
            )
        if self.closure not in CLOSURE_BY_KEY:
            issues.append(f"closure 非法: {self.closure!r}")
        if self.verdict and self.verdict not in VERDICTS:
            issues.append(f"verdict 非法: {self.verdict!r}（可选 {', '.join(VERDICTS)}）")
        if self.score is not None:
            if self.score_scale not in (5, 10):
                issues.append(f"score_scale 只能是 5 或 10，收到 {self.score_scale}")
            elif not 0 <= self.score <= self.score_scale:
                issues.append(f"score={self.score} 超出 0–{self.score_scale}")

        # A claim of deep verification that the closure state contradicts.
        rank = {k: i for i, (k, _) in enumerate(CLOSURE_STATES)}
        if self.evidence_level in ("L4", "L5") and rank.get(self.closure, 0) < 1:
            issues.append(
                f"evidence_level={self.evidence_level} 声称已做代码/复现核验，"
                f"但 closure 仍是「{CLOSURE_BY_KEY.get(self.closure, self.closure)}」——两者不一致"
            )
        for tag in self.tags:
            if re.search(r"[\[\]\"']", tag):
                issues.append(f"主题标签含残留符号: {tag!r}")
        return issues


def normalise_relation(value: str) -> str:
    v = (value or "").strip().lower()
    aliases = {
        "": "none", "无": "none", "无关": "none", "无直接关系": "none",
        "可借鉴": "design", "借鉴": "design",
        "引用": "cite", "直接竞争": "cite",
        "警示": "warning", "类比": "analogy",
    }
    return aliases.get(v, v if v in PROJECT_RELATIONS else "none")
