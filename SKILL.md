---
name: readmap
description: >-
  Deep-read an academic paper into a decision, not a report. Use whenever the
  user asks to 精读 / deep-read / properly read a paper, wants a structured
  reading note, asks "这篇论文值不值得信", wants figures and tables pulled out of
  a paper for reading, or wants a reading note filed to Notion. Reconstructs why
  the problem exists before describing the solution, isolates the smallest thing
  the authors actually added, separates what the experiments proved from what
  merely accompanied them, and ends in one decision. Keywords: 精读, deep dive,
  paper reading, reading note, literature note, 论文精读, arxiv 精读, ReadMap.
---

# ReadMap — 论文精读

> 精读不是把论文翻译成更专业的中文，而是把它拆到最基本的问题，看清它究竟解决了什么、
> 为什么有效、证据够不够，以及有没有用复杂包装掩盖一个普通技巧。

**唯一判断标准**：遮住标题、作者、会议和所有新术语后，仅凭问题、机制和证据，
还能不能判断这个工作值不值得相信？若只剩「用了一个复杂框架，在很多数据集上涨了」，
说明还没看穿。

## Step 0 — 环境检查

```bash
readmap --help          # 装了就走完整流程
```

- **可用** → 走下面的完整流程。
- **不可用**（没有 shell、没装）→ 直接按「正文八问」和「三条硬规则」精读，
  图表按降级模式处理。这**不算失败**，但必须说明缺口，不要假装跑过工具。

## 完整流程

```bash
readmap read <arXiv/OpenReview/ACL/PDF/文章 URL>   # 取源 → 解析 → 抠全部图表 → 生成骨架
# 读论文，填 papers/<id>/reading.md
readmap gate papers/<id>/reading.md                # 同步前的质量门
readmap sync papers/<id>/reading.md                # → Notion
```

`read` / `gate` / `figures` 不需要 Notion 凭据。

## 正文八问

完整版见 [`prompts/reading.md`](prompts/reading.md)。

1. **三十秒讲清楚** —— 解决什么？关键办法？最终判断？外加三条关键数字
2. **第一性原理** —— 不用论文任何术语：世界里原本有什么矛盾？哪两件事不可兼得？
3. **一个能在脑中运行的例子** —— 拆掉术语 → 最小玩具世界 → 回到严格表达。
   每个比喻必须补三句：对应什么数学对象、在哪里成立、在哪里会误导
4. **作者真正新增了什么** —— 最小创新单元；新增了哪个自由度，又带来什么新风险
5. **为什么理论上应该有效** —— 机制解释，不能只说结果涨了
6. **证明了什么、没证明什么** —— 直接证据 / 间接证据 / 作者推断 / 我的推断 /
   尚未验证，五类分开列
7. **承重审计** —— 作者真正想卖什么？为证明它搭了多少外围系统？去掉核心创新
   其他不变会掉多少？有没有更便宜的替代？增益是否只来自参数量或数据量？
   叙事是否超过证据？
   然后**收口到三问**（不要罗列通用局限）：只能推翻一个假设该推翻哪个？
   哪个结果消失论文就坍塌？最小判决实验是什么？
8. **最终判决** —— 择一：真突破 / 扎实增量 / 工程整合 / 评测贡献 /
   有趣但证据不足 / 包装大于贡献 / 当前无法判断。并写**主张降级**：
   作者说 X，证据只支持到 Y。

## 三条硬规则

**一 · 每个关键数字都带证据标签。** 说明"我是怎么知道的"：

`[Paper/Fig N]` `[Paper/Table N]` `[Appendix X.Y]` `[Code inspected]`
`[Recomputed]` `[My inference]` `[Unverified]`

无标签的数字一律按 `[Unverified]` 计。**"读过完整 PDF 所以置信度高"不等于
"关键数字已被独立核验"。**

**二 · 与我研究的关系默认 none。** 先回答"完全不考虑当前项目，这篇论文的独立
价值是什么"，再判断关系。只有满足下列之一才能改：

| 取值 | 门槛 |
|---|---|
| `cite` | 能指出进入正文哪一节 |
| `design` | 能说出增加哪个对照、改哪个指标、删哪个实验、加哪个压力测试 |
| `warning` | 能指出我的哪个测量、假设或结论可能失效 |
| `analogy` | 承认仅为思考素材，不进入当前项目 |

认真读完后判断"不相关"不是失败，说明没有被当前项目绑架。

**三 · 结论只写一处。** 开头一句话判决、中间证据链、结尾一个决策。
速查卡交给数据库字段承担，正文不要再重复一套。

## 必填元数据

| 字段 | 取值 |
|---|---|
| `doc_type` | 单篇精读 / Radar 综述 / 自主教程 / 复现报告 |
| `evidence_level` | L1 摘要 / L2 原文 / L3 图表附录 / L4 代码数据 / L5 局部复现 |
| `project_relation` | **none**（默认）/ cite / design / warning / analogy |
| `relation_reason` | 关系不为 none 时必填 |
| `closure` | 阅读完成 / 证据核验完成 / 复现完成 / 迁移实验完成 / 已进入论文 |
| `verdict` | 上面七选一 |
| `score` + `score_scale` | 必须同时给，4/5 与 4/10 不是一回事 |

**证据等级与篇幅无关**：L1 可以很长，L4 可以很短。不确定就填低不填高。

**下一步只能勾一项**：引用 / 改 claim / 改实验 / 登记不行动 / 最小验证实验。
一项都没产生时，`closure` 只能是「阅读完成」。

## 图表

`readmap read` 会调用
[figure-extractor](https://github.com/Sunrich-HT/figure-extractor)
抠出**全部** Figure / Table / Scheme / Algorithm（含 `Extended Data Fig.`、
`Supplementary Table`、章节式 `Figure 2.1`、附录 `Figure B.1`），连同 300 dpi
裁剪、caption、页码、正文引用次数和裁剪质量评分写进 manifest。

**抠取是穷尽的，选择不是。** 哪几张承载论证取决于论文自身的论证结构，计数器
看不见。骨架里给的是一份目录，不是一堆插图：进正文的通常只有支撑核心结论的
2–4 张，其余留在目录里待引。manifest 里的 tier 只反映引用频次，是分诊起点，
不是判决。标为 `suspect` / `failed` 的裁剪引用前先核对 `contact_sheet.jpg`。

### 降级模式（拿不到位图时）

无法运行抠图工具、图片 404、需要登录——这些情况**允许**，但必须：

1. 给出原文页码和图号
2. 基于 caption 与上下文如实描述，**绝不凭空描述没看见的图**
3. 明确写出缺口原因，例如「位图未获取 —— 原因：当前环境无 shell」

## 质量门

`readmap gate` 在同步前拦截：生成残留的孤立词、Markdown 转义残留、
标签里的括号引号碎片、超出制式的评分、自动综述冒充代码核验等级、
标了闭环却没有任何决策、以及同一结论在三处重复。
