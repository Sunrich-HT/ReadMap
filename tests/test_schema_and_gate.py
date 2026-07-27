"""Tests for the distinctions the schema is supposed to enforce.

Each case below reproduces something that reached a real reading note and had to
be found by hand.
"""

from pathlib import Path

import pytest

from readmap.gate import check
from readmap.notes import _as_tags, one_line_summary, parse_note, split_frontmatter
from readmap.schema import ReadingMeta


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

def test_relevance_must_be_argued_for():
    """Relation defaults to none; anything stronger needs a stated reason."""
    assert ReadingMeta(title="T").project_relation == "none"
    assert ReadingMeta(title="T").problems() == []

    claimed = ReadingMeta(title="T", project_relation="cite")
    assert any("relation_reason" in p for p in claimed.problems())

    justified = ReadingMeta(title="T", project_relation="cite",
                            relation_reason="进入 Related Work 第 2 段")
    assert justified.problems() == []


def test_score_scales_are_not_interchangeable():
    """A 4/5 and a 4/10 were stored in one numeric column and sorted together."""
    five = ReadingMeta(title="T", score=4, score_scale=5)
    ten = ReadingMeta(title="T", score=4, score_scale=10)
    assert five.score_normalised == 0.8
    assert ten.score_normalised == 0.4
    assert five.score_normalised != ten.score_normalised


def test_score_outside_its_scale_is_rejected():
    assert any("超出" in p for p in ReadingMeta(title="T", score=8, score_scale=5).problems())


def test_deep_verification_must_match_the_closure_state():
    """Claiming code-level verification while still merely 'read' is incoherent."""
    meta = ReadingMeta(title="T", evidence_level="L4", closure="reading-done")
    assert any("不一致" in p for p in meta.problems())


def test_tag_residue_is_reported():
    assert any("残留符号" in p for p in ReadingMeta(title="T", tags=["[paper", "debate]"]).problems())


# ---------------------------------------------------------------------------
# Front matter
# ---------------------------------------------------------------------------

def test_comments_in_front_matter_are_not_fields():
    fm, body = split_frontmatter('---\n# 证据等级 L1-L5\ntitle: "T"\n---\nbody\n')
    assert fm == {"title": "T"}
    assert body.strip() == "body"


def test_stringified_tag_lists_are_cleaned():
    """Topic columns had picked up `[paper` and `debate]` fragments."""
    assert _as_tags('[paper, debate]') == ["paper", "debate"]
    assert _as_tags('"rlhf", "safety"') == ["rlhf", "safety"]
    assert _as_tags("机制可解释性，安全") == ["机制可解释性", "安全"]


def test_placeholder_summary_is_not_a_summary():
    assert one_line_summary("> [!summary] 一句话判决\n> （待填写）\n") == ""
    assert one_line_summary("> [!summary] 一句话判决\n> 扎实增量。\n") == "扎实增量。"


# ---------------------------------------------------------------------------
# Gate
# ---------------------------------------------------------------------------

def _note(tmp_path: Path, front: str, body: str) -> tuple:
    path = tmp_path / "n.md"
    path.write_text(f"---\n{front}\n---\n{body}", encoding="utf-8")
    return parse_note(path)


def test_gate_catches_generation_residue(tmp_path):
    meta, body = _note(tmp_path, 'title: "T"', "> [!summary] x\n> ok\n\nzaza\n")
    report = check(meta, body, strict=False)
    assert any("zaza" in f.message for f in report.blocking)


def test_gate_catches_escape_residue_and_internal_links(tmp_path):
    meta, body = _note(tmp_path, 'title: "T"', "见 \\> 引用与 \\^ 上标\n\n[s](.claude/skills/SKILL.md)\n")
    messages = " ".join(f.message for f in check(meta, body, strict=False).findings)
    assert "转义残留" in messages
    assert "内部文件" in messages


def test_gate_flags_untagged_claim_numbers(tmp_path):
    meta, body = _note(tmp_path, 'title: "T"', "准确率 93.68%，基线 76.4%。\n")
    assert any("证据标签" in f.message for f in check(meta, body, strict=False).findings)


def test_section_numbers_are_not_claim_numbers(tmp_path):
    """`3.1` is a heading, not a result."""
    meta, body = _note(tmp_path, 'title: "T"', "**3.1 拆掉术语**\n\n**3.2 玩具世界**\n")
    assert not any("证据标签" in f.message for f in check(meta, body, strict=False).findings)


def test_gate_blocks_a_survey_claiming_verified_evidence(tmp_path):
    meta, body = _note(tmp_path, 'title: "T"\ndoc_type: radar\nevidence_level: L4', "x\n")
    assert any("radar" in f.message for f in check(meta, body, strict=False).blocking)


def test_gate_blocks_closure_without_a_decision(tmp_path):
    """Writing the report is not closing the question."""
    meta, body = _note(tmp_path, 'title: "T"\nclosure: evidence-checked', "没有勾选任何决策项。\n")
    assert any("闭环" in f.message for f in check(meta, body, strict=False).blocking)


def test_gate_flags_more_than_one_next_step(tmp_path):
    meta, body = _note(tmp_path, 'title: "T"', "- [x] 引用\n- [x] 改实验\n")
    assert any("只应有一项" in f.message for f in check(meta, body, strict=False).warnings)


def test_gate_flags_a_conclusion_restated_in_three_places(tmp_path):
    conclusion = (
        "这项工作是扎实增量。奖励模型只观察文本表面，与正确性在训练数据中相关，"
        "优化器寻找的是提高分数的方向，因此持续优化会把代理偏差放大成 Goodhart 失效。"
    )
    body = f"## 开头\n\n{conclusion}\n\n## 正文结论\n\n{conclusion}\n\n## 速查卡\n\n{conclusion}\n"
    meta, parsed = _note(tmp_path, 'title: "T"', body)
    assert any("重复" in f.message for f in check(meta, parsed, strict=False).warnings)


def test_unfilled_skeleton_does_not_pass_strict_gate(tmp_path):
    from readmap.compose import build_note

    path = tmp_path / "reading.md"
    path.write_text(build_note(ReadingMeta(title="T"), None, tmp_path), encoding="utf-8")
    meta, body = parse_note(path)
    assert not check(meta, body, strict=True).passed


@pytest.mark.parametrize("level,ok", [("L1", True), ("L5", True), ("L9", False)])
def test_evidence_level_vocabulary(level, ok):
    # L4/L5 additionally require a closure state consistent with having
    # verified something, so pair them with one.
    closure = "replicated" if level in ("L4", "L5") else "reading-done"
    problems = ReadingMeta(title="T", evidence_level=level, closure=closure).problems()
    assert (problems == []) is ok
