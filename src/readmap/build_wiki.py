#!/usr/bin/env python3
"""
Generate Wiki knowledge maps from Notion literature database.
Produces Quartz-compatible Markdown files.
"""

import argparse
import re
from datetime import datetime
from pathlib import Path

from readmap.config import cfg
from readmap.notion_client import (
    api_post,
    get_all_concepts,
    get_all_papers,
    get_all_projects,
)


def extract_property(page: dict, prop_name: str, prop_type: str) -> str | list | None:
    """Safely extract a property value from a Notion page."""
    prop = page.get("properties", {}).get(prop_name, {})
    if prop_type == "title":
        return prop.get("title", [{}])[0].get("plain_text", "") if prop.get("title") else ""
    elif prop_type == "rich_text":
        return prop.get("rich_text", [{}])[0].get("plain_text", "") if prop.get("rich_text") else ""
    elif prop_type == "select":
        return prop.get("select", {}).get("name", "") if prop.get("select") else ""
    elif prop_type == "multi_select":
        return [o["name"] for o in prop.get("multi_select", [])]
    elif prop_type == "number":
        return prop.get("number")
    elif prop_type == "url":
        return prop.get("url", "")
    elif prop_type == "relation":
        return [r["id"] for r in prop.get("relation", [])]
    return None


def slugify(text: str) -> str:
    """Generate a URL-friendly slug."""
    return re.sub(r"[^\w\s-]", "", text).strip().replace(" ", "-").lower()[:50]


def build_map_page(wiki_dir: Path, research_line: str, papers: list[dict]):
    """Generate a knowledge map page for each research line."""
    maps_dir = wiki_dir / "content" / "maps"
    maps_dir.mkdir(parents=True, exist_ok=True)

    slug = slugify(research_line)
    map_path = maps_dir / f"{slug}.md"

    line_papers = []
    for p in papers:
        topics = extract_property(p, "主题", "multi_select") or []
        if any(research_line.lower() in t.lower() for t in topics):
            line_papers.append(p)

    content = f"""---
title: "🗺️ {research_line}"
---

# 🗺️ 认知地图：{research_line}

> 本文件由 `build_wiki.py` 自动维护。
> 最后更新：{datetime.now().strftime("%Y-%m-%d %H:%M")}

---

## 核心问题

（请在此手动补充该研究线的核心科学/工程问题）

---

## 方法谱系

```mermaid
mindmap
  root(({research_line}))
    早期方法
      待填充
    主流方法
      待填充
    前沿方法
      待填充
    你的贡献
      ★ 你的工作
```

---

## 论文节点

> 点击论文标题跳转到 Notion 完整精读页面。

"""

    for p in line_papers:
        title = extract_property(p, "论文标题", "title") or "Untitled"
        authors = extract_property(p, "作者", "rich_text") or ""
        year = extract_property(p, "年份", "number") or ""
        venue = extract_property(p, "会议期刊", "select") or ""
        mode = extract_property(p, "精读模式", "select") or ""
        score = extract_property(p, "Reviewer评分", "number")
        relevance = extract_property(p, "与我研究的关系", "select") or ""
        quick_ref = extract_property(p, "速查卡", "rich_text") or ""
        notion_url = p.get("url", "")

        mode_emoji = {"⚡ 速扫": "⚡", "📖 Standard": "📖", "🔬 Deep Dive": "🔬"}.get(mode, "📄")
        score_str = f"| Score: {score}/5" if score else ""

        content += f"""### [{title}]({notion_url}) 🔗

- **作者：** {authors}
- **年份：** {year} | **来源：** {venue}
- **精读模式：** {mode_emoji} {mode} {score_str}
- **与我关系：** {relevance}
- **速查：** {quick_ref[:200]}{"..." if len(quick_ref) > 200 else ""}

---

"""

    content += """## 开放问题

- [ ] 待填充

---

## 概念网络

（从概念卡片库自动提取相关概念）

---

## 与我工作的关系

- **当前活跃项目：** （手动补充）
- **下一步计划：** （手动补充）
"""

    map_path.write_text(content, encoding="utf-8")
    print(f"Generated map: {map_path}")
    return map_path


def build_entity_page(wiki_dir: Path, concept: dict):
    """Generate an entity page for each concept."""
    entities_dir = wiki_dir / "content" / "entities"
    entities_dir.mkdir(parents=True, exist_ok=True)

    name = extract_property(concept, "概念名", "title") or "Untitled"
    definition = extract_property(concept, "一句话定义", "rich_text") or ""
    maturity = extract_property(concept, "成熟度", "select") or ""
    domain = extract_property(concept, "领域", "multi_select") or []
    ctype = extract_property(concept, "类型", "select") or ""
    first_seen = extract_property(concept, "首次见于", "rich_text") or ""
    notion_url = concept.get("url", "")

    slug = slugify(name)
    entity_path = entities_dir / f"{slug}.md"

    content = f"""---
title: "🧠 {name}"
---

# 🧠 {name}

> {maturity} | {ctype} | {', '.join(domain)}
> 概念卡片库链接：[{name}]({notion_url}) 🔗

---

## 一句话定义

> {definition}

---

## 我的理解

（请在此补充个人理解）

---

## 已知性质

- 待补充

## 典型实例

- 待补充

---

## 相关论文

（自动从概念卡片库关联）

---

## 相关概念

（通过双向链接建立）

---

## 成熟度演进

- {'[x]' if '🌱' in maturity else '[ ]'} 🌱 种子
- {'[x]' if '🌿' in maturity else '[ ]'} 🌿 在长
- {'[x]' if '🌳' in maturity else '[ ]'} 🌳 成熟
- {'[x]' if '💎' in maturity else '[ ]'} 💎 结晶
"""

    entity_path.write_text(content, encoding="utf-8")
    print(f"Generated entity: {entity_path}")
    return entity_path


def build_index_page(wiki_dir: Path, research_lines: list[str]):
    """Generate the wiki homepage."""
    index_path = wiki_dir / "content" / "index.md"

    maps_links = "\n".join(f'- [[maps/{slugify(rl)}|🗺️ {rl}]]' for rl in research_lines if rl.strip())

    content = f"""---
title: "🏠 Research Knowledge Map"
---

# 🏠 Research Knowledge Map

> 这里是我（{{{{USER_NAME}}}}）的学术研究认知地图。
> 文章精读全文存放在 Notion，这里只挂结构化地图和知识网络。

---

## 🗺️ 认知地图

{maps_links if maps_links else '- （暂无研究线，请在 .env 中配置 RESEARCH_LINES）'}

---

## 🧠 概念实体

- [[entities/index|浏览全部概念 →]]

---

## 📐 方法论

- [[methodology/reading-sop|12节精读 SOP]]
- [[methodology/reviewer-simulation|Reviewer Simulation 指南]]
- [[methodology/critical-lens|Critical Lens 检查清单]]

---

## 📚 最新动态

（自动从 Notion 文献库同步）

---

```mermaid
mindmap
  root((Research))
    认知地图
      按研究线组织
    概念实体
      按领域聚合
    方法论
      精读 SOP
      Reviewer 模拟
    论文节点
      链接到 Notion
```
"""

    index_path.write_text(content, encoding="utf-8")
    print(f"Generated index: {index_path}")


def main():
    parser = argparse.ArgumentParser(description="Generate Wiki knowledge maps from Notion")
    parser.add_argument("--wiki-dir", default="./wiki", help="Wiki output directory")
    parser.add_argument("--research-lines", default="", help="Comma-separated research lines")
    args = parser.parse_args()

    wiki_dir = Path(args.wiki_dir)
    wiki_dir.mkdir(parents=True, exist_ok=True)

    research_lines = [rl.strip() for rl in (args.research_lines or cfg.research_lines).split(",") if rl.strip()]

    print("Fetching papers from Notion...")
    papers = get_all_papers()
    print(f"  Found {len(papers)} papers")

    print("Fetching concepts from Notion...")
    concepts = get_all_concepts()
    print(f"  Found {len(concepts)} concepts")

    print("\nBuilding map pages...")
    for rl in research_lines:
        build_map_page(wiki_dir, rl, papers)

    print("\nBuilding entity pages...")
    for c in concepts:
        build_entity_page(wiki_dir, c)

    print("\nBuilding index page...")
    build_index_page(wiki_dir, research_lines)

    print("\n🎉 Wiki build complete!")


if __name__ == "__main__":
    main()
