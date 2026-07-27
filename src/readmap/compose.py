"""Build the reading skeleton.

The old skeleton had twelve sections and rewarded filling them. Twelve filled
sections read as twelve verified findings, so a well-written summary of an
abstract became indistinguishable from a paper whose numbers had been checked
against the appendix.

The eight questions below are not a shorter checklist. They change what the
document is *for*: reconstructing why the problem exists before describing the
solution, isolating the smallest thing the authors actually added, separating
what the experiments proved from what they merely accompanied, and ending in a
decision rather than a list of ideas.

Two habits are folded in rather than given sections of their own:

*Reconstruct the problem* — what tension exists in the world, which two things
cannot both be had, what new degree of freedom the authors introduced, and what
new risk that freedom creates. This is question 2 and question 4.

*Test what carries the weight* — whether the advertised contribution is what
produces the gain, whether a cheaper substitute would do, whether the gain is
really extra parameters or data, and what remains once the terminology is
stripped. This is question 7. Both are the same first-principles move applied
first to the problem and then to the claim.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from readmap.config import cfg
from readmap.figures import FigureSet, catalogue_markdown
from readmap.schema import EVIDENCE_TAGS, ReadingMeta

TEMPLATE_MARKER = "（待填写）"


def render_template_vars(text: str) -> str:
    """Substitute ``{{USER_NAME}}``-style placeholders.

    The prompts have always carried these placeholders and nothing ever replaced
    them, so every user edited the prompt files by hand or read instructions
    addressed to ``{{USER_NAME}}``.
    """
    for key, value in cfg.template_vars().items():
        text = text.replace("{{" + key + "}}", value or f"<{key} 未配置>")
    return text


def frontmatter(meta: ReadingMeta) -> str:
    tags = ", ".join(meta.tags)
    return f"""---
title: "{meta.title}"
authors: "{meta.authors}"
year: {meta.year or ""}
venue: "{meta.venue}"
url: "{meta.url}"

# 文档类型：单篇精读 / radar / tutorial / replication
doc_type: {meta.doc_type}

# 证据等级 L1–L5。与篇幅无关：L1 可以很长，L4 可以很短。
#   L1 摘要整理  L2 原文核验  L3 图表核验  L4 代码数据核验  L5 局部复现
evidence_level: {meta.evidence_level}

# 与当前研究的关系。默认 none —— 相关性需要被论证，而不是被假定。
#   none / cite / design / warning / analogy
project_relation: {meta.project_relation}
relation_reason: "{meta.relation_reason}"

# 决策闭环：写完报告 ≠ 问题闭环
#   reading-done / evidence-checked / replicated / transferred / in-paper
closure: {meta.closure}

# 最终判决（择一）：breakthrough / solid-increment / engineering /
#   benchmark / interesting-unproven / overpackaged / undecidable
verdict: {meta.verdict}

# Reviewer 评分必须带制式，否则 4/5 与 4/10 在数据库里无法区分
score:
score_scale: {meta.score_scale}

tags: "{tags}"
read_date: {date.today().isoformat()}
---
"""


def _body(meta: ReadingMeta, figures_block: str) -> str:
    tag_list = "  ".join(f"`{t}`" for t in EVIDENCE_TAGS)
    return f"""
# {meta.title or TEMPLATE_MARKER}

> [!evidence] 证据标签
> 正文中每一个关键数字或论断都要带标签，说明**我是怎么知道的**：
> {tag_list}
> 无标签的数字默认视为 `[Unverified]`。

---

## 1 · 三十秒讲清楚

> [!summary] 一句话判决
> {TEMPLATE_MARKER}

- **解决什么问题：** {TEMPLATE_MARKER}
- **关键办法：** {TEMPLATE_MARKER}
- **三条关键数字：** {TEMPLATE_MARKER} `[Paper/Table N]`

---

## 2 · 第一性原理：这个问题为什么存在

不使用论文的任何术语作答。

- **世界里原本有什么矛盾？** {TEMPLATE_MARKER}
- **哪两件事物理上不可兼得？**（稀疏性 vs 重构 / 安全性 vs 覆盖率 / 解释性 vs 保真 / 尾部覆盖 vs 无偏 / 信息量 vs 噪声 / 灵活性 vs 可审计性）
  {TEMPLATE_MARKER}
- **不先说清这个矛盾，就说不出这篇论文为什么需要存在。**

---

## 3 · 一个能在脑中运行的例子

先拆掉论文语言，再回到技术表达。比喻负责建立直觉，公式负责划清边界。

**3.1 拆掉术语后，这件事在干什么**
{TEMPLATE_MARKER}

**3.2 最小玩具世界**（一个小到能在脑子里跑的例子）
{TEMPLATE_MARKER}

**3.3 比喻的边界**（每个比喻必须补这三句，否则会制造错误直觉）
- 这个比喻对应什么数学对象：{TEMPLATE_MARKER}
- 它在哪些地方成立：{TEMPLATE_MARKER}
- 它在哪些地方会误导：{TEMPLATE_MARKER}

---

## 4 · 作者真正新增了什么

去掉系统包装，只保留最小创新单元。

- **新增的自由度是什么：** {TEMPLATE_MARKER}
- **拿掉华丽术语后的一句话描述：** {TEMPLATE_MARKER}
- **这个自由度带来了什么新风险**（新的不可识别性 / 偏差 / 攻击面）：{TEMPLATE_MARKER}

---

## 5 · 为什么它理论上应该有效

把直觉、公式、假设三者对应起来。只说"结果涨了"不算回答。

- **机制解释：** {TEMPLATE_MARKER}
- **关键公式与符号含义：** {TEMPLATE_MARKER}
- **成立所依赖的假设：** {TEMPLATE_MARKER}

---

## 6 · 实验证明了什么，没证明什么

必须分开列，不能混写。

| 类别 | 内容 | 证据标签 |
|---|---|---|
| 直接证据 | {TEMPLATE_MARKER} | `[Paper/Table N]` |
| 间接证据 | {TEMPLATE_MARKER} | `[Paper/Fig N]` |
| 作者的推断 | {TEMPLATE_MARKER} | `[Paper/§N]` |
| 我的推断 | {TEMPLATE_MARKER} | `[My inference]` |
| 尚未验证 | {TEMPLATE_MARKER} | `[Unverified]` |

---

## 7 · 承重审计：哪根梁真正承重

不列举七八条通用局限。只回答"这篇论文的创新是否真的承重"。

1. **作者真正想卖的是什么？**（新模块 / 新损失 / 新路由 / 新 benchmark / 一个响亮的理论概念）
   {TEMPLATE_MARKER}
2. **为证明它，搭了多少外围系统？**（更大 backbone / 更多数据 / 更长上下文 / 更多 agent / 更贵检索 / 对自己有利的指标）
   {TEMPLATE_MARKER}
3. **有没有针对性消融？** 去掉核心创新、其他不变，性能掉多少？
   {TEMPLATE_MARKER} `[Paper/Table N]`
4. **有没有更便宜的替代？** 线性模型 / 简单检索 / 朴素基线 / 更干净的数据能否拿到同样收益？
   {TEMPLATE_MARKER}
5. **增益是否只来自参数量、计算量或信息量的增加？**
   {TEMPLATE_MARKER}
6. **叙事是否超过了证据？**
   {TEMPLATE_MARKER}

### 单一判决问题

不要罗列通用 reviewer checklist。只答这三问：

- **如果只能推翻一个假设，应该推翻哪一个？** {TEMPLATE_MARKER}
- **哪个实验结果一旦消失，整篇论文的主张就坍塌？** {TEMPLATE_MARKER}
- **最小判决实验是什么？** {TEMPLATE_MARKER}

---

## 8 · 最终判决

> [!verdict] 判决
> **这是什么工作：** {TEMPLATE_MARKER}
> （真突破 / 扎实增量 / 工程整合 / 评测贡献 / 有趣但证据不足 / 包装大于贡献 / 当前无法判断）
>
> **主张降级：** 作者说 {TEMPLATE_MARKER}，证据只支持到 {TEMPLATE_MARKER}。

**对当前研究：** `none`（默认）

> 只有满足下列之一才能改：
> - `cite` — 能指出进入正文哪一节
> - `design` — 能说出增加哪个对照 / 改哪个指标 / 删哪个实验 / 加哪个压力测试
> - `warning` — 能指出我们的哪个测量、假设或结论可能失效
> - `analogy` — 承认仅为思考素材，不进入当前项目
>
> 认真读完后判断"不相关"不是失败，而是没有被当前项目绑架。

**下一步（择一，且只能一项）：** {TEMPLATE_MARKER}
- [ ] 引用
- [ ] 改 claim
- [ ] 改实验
- [ ] 登记不行动
- [ ] 最小验证实验：{TEMPLATE_MARKER}

> 若以上一项都没产生，本文只能记为「阅读整理完成」，不能记为研究闭环。

---

## 图表

{figures_block}

---

## 遮蔽测试

> 遮住标题、作者、会议和所有新术语后，仅凭问题、机制和证据，还能不能判断这个工作值不值得相信？
>
> **答：** {TEMPLATE_MARKER}
>
> 若只剩「用了一个复杂框架，在很多数据集上涨了」，说明还没看穿。

---

## 延伸阅读

每条必须附可点击链接（arXiv 优先，其次 DOI）。

- [{TEMPLATE_MARKER}]({TEMPLATE_MARKER}) — 推荐理由：{TEMPLATE_MARKER}
"""


def build_note(meta: ReadingMeta, figures: FigureSet | None, note_dir: Path) -> str:
    """Assemble the full skeleton for one reading."""
    figures_block = (
        catalogue_markdown(figures, note_dir)
        if figures is not None
        else "> [!note] 未运行图表提取。\n"
    )
    return render_template_vars(frontmatter(meta) + _body(meta, figures_block))


def write_note(meta: ReadingMeta, figures: FigureSet | None, note_dir: Path,
               filename: str = "reading.md", overwrite: bool = False) -> Path:
    note_dir.mkdir(parents=True, exist_ok=True)
    path = note_dir / filename
    if path.exists() and not overwrite:
        # Never clobber work in progress; the skeleton is cheap to regenerate
        # under another name, a half-written reading is not.
        path = note_dir / f"{Path(filename).stem}.new{Path(filename).suffix}"
    path.write_text(build_note(meta, figures, note_dir), encoding="utf-8")
    return path
