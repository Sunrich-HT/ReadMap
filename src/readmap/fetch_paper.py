#!/usr/bin/env python3
"""
Paper download & structured parsing.
Supports: arXiv / OpenReview / DOI (via Semantic Scholar / Unpaywall)

Integrated with MinerU: PDF → structured Markdown + precise image extraction + structured JSON.
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

import requests

from readmap.config import cfg
from readmap.parse_with_mineru import parse_paper
from readmap.extract_web_images import extract_images, generate_markdown_index


def extract_arxiv_id(url_or_id: str) -> str | None:
    """Extract arXiv ID from various URL formats."""
    patterns = [
        r"arxiv\.org/abs/(\d+\.\d+)",
        r"arxiv\.org/pdf/(\d+\.\d+)",
        r"^(\d+\.\d+)$",
    ]
    for pat in patterns:
        m = re.search(pat, url_or_id)
        if m:
            return m.group(1)
    return None


def fetch_arxiv(arxiv_id: str, output_dir: Path, backend: str = "pipeline") -> dict:
    """Download arXiv paper, metadata, and parse with MinerU."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. Fetch metadata
    api_url = f"https://export.arxiv.org/api/query?id_list={arxiv_id}"
    resp = requests.get(api_url, timeout=30)
    resp.raise_for_status()

    import xml.etree.ElementTree as ET

    root = ET.fromstring(resp.content)
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    entry = root.find("atom:entry", ns)

    metadata = {
        "arxiv_id": arxiv_id,
        "title": entry.findtext("atom:title", "", ns).replace("\n", " ").strip(),
        "authors": [a.findtext("atom:name", "", ns) for a in entry.findall("atom:author", ns)],
        "summary": entry.findtext("atom:summary", "", ns).replace("\n", " ").strip(),
        "published": entry.findtext("atom:published", "", ns),
        "primary_category": entry.find("atom:category", ns).get("term", "") if entry.find("atom:category", ns) else "",
        "pdf_url": f"https://arxiv.org/pdf/{arxiv_id}.pdf",
        "abs_url": f"https://arxiv.org/abs/{arxiv_id}",
    }

    # 2. Download PDF
    pdf_path = output_dir / f"{arxiv_id}.pdf"
    if not pdf_path.exists():
        print(f"Downloading PDF to {pdf_path} ...")
        r = requests.get(metadata["pdf_url"], timeout=60)
        r.raise_for_status()
        pdf_path.write_bytes(r.content)
    metadata["pdf_path"] = str(pdf_path)

    # 3. Parse with MinerU
    print(f"\n[MinerU] Parsing PDF into structured Markdown (backend={backend})...")
    parse_result = parse_paper(pdf_path, output_dir, backend=backend)

    if parse_result.get("success"):
        md_path = parse_result["md_path"]
        images_dir = parse_result["images_dir"]
        metadata["markdown_path"] = str(md_path) if md_path else None
        metadata["images_dir"] = str(images_dir) if images_dir else None
        metadata["content_list_path"] = str(parse_result["content_list_path"]) if parse_result.get("content_list_path") else None
        print(f"  ✓ Markdown: {metadata['markdown_path']}")
        print(f"  ✓ Images: {metadata['images_dir']}")

        # 4. Post-process
        print(f"\n[PostProcess] Optimizing output...")
        from readmap.postprocess_mineru import postprocess

        clean_md = postprocess(md_path, images_dir)
        metadata["clean_markdown_path"] = str(clean_md)
        print(f"  ✓ Clean Markdown: {metadata['clean_markdown_path']}")
    else:
        print(f"  ⚠ MinerU parsing failed, falling back to raw PDF only")
        metadata["mineru_error"] = parse_result.get("error", "unknown")

    # 5. Save metadata
    meta_path = output_dir / "metadata.json"
    meta_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False))
    print(f"Metadata saved to {meta_path}")

    # 6. Generate frontmatter template
    year = metadata.get("published", "")[:4] if metadata.get("published") else ""
    frontmatter_md = output_dir / "deep-dive.md"
    frontmatter_content = f"""---
title: "{metadata.get('title', '')}"
authors: "{', '.join(metadata.get('authors', []))}"
year: {year}
venue: "{metadata.get('primary_category', '')}"
url: "{metadata.get('abs_url', '')}"
mode: deep-dive
tags: "{metadata.get('primary_category', '')}"
---

# 🔬 Deep Dive: {metadata.get('title', '')}

> **作者：** {', '.join(metadata.get('authors', []))}
> **年份：** {year}
> **来源：** {metadata.get('primary_category', '')}
> **arXiv：** [{metadata.get('arxiv_id', '')}]({metadata.get('abs_url', '')})

---

## Section 1: 论文基本信息 & TL;DR

| 字段 | 内容 |
|------|------|
| **标题** | {metadata.get('title', '')} |
| **作者** | {', '.join(metadata.get('authors', []))} |
| **年份** | {year} |
| **arXiv** | [{metadata.get('arxiv_id', '')}]({metadata.get('abs_url', '')}) |

> [!summary] 速查卡
> **问题：**
> **方法：**
> **关键结果：**

---

## 精读正文

（请基于 paper_clean.md 进行逐节精读，覆盖 12 节结构）
"""
    frontmatter_md.write_text(frontmatter_content, encoding="utf-8")
    print(f"  ✓ Frontmatter template: {frontmatter_md}")

    return metadata


def fetch_semantic_scholar(title: str, api_key: str | None = None) -> dict:
    """Fetch citation data via Semantic Scholar."""
    url = "https://api.semanticscholar.org/graph/v1/paper/search"
    headers = {}
    if api_key:
        headers["x-api-key"] = api_key
    params = {
        "query": title,
        "fields": "title,authors,year,citationCount,referenceCount,influentialCitationCount,openAccessPdf",
        "limit": 1,
    }
    resp = requests.get(url, headers=headers, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if data.get("data"):
        return data["data"][0]
    return {}


def fetch_web_article(url: str, output_dir: Path) -> dict:
    """
    Process web articles (non-PDF).
    1. Extract article text (jina.ai/readability)
    2. Extract images
    3. Generate frontmatter template
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    parsed = urlparse(url)
    path_parts = [p for p in parsed.path.split("/") if p]
    short_name = path_parts[-1] if path_parts else "web-article"
    short_name = re.sub(r"[^a-zA-Z0-9_-]", "-", short_name).strip("-")

    paper_dir = output_dir / short_name
    paper_dir.mkdir(parents=True, exist_ok=True)
    figures_dir = paper_dir / "figures"

    print(f"[Web] Processing web article: {url}")
    print(f"[Web] Output dir: {paper_dir}")

    # 1. Extract article text
    try:
        jina_url = f"https://r.jina.ai/http://{url}"
        resp = requests.get(jina_url, timeout=60, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        article_text = resp.text

        lines = article_text.split("\n")
        title = lines[0].strip("# ").strip() if lines else short_name
        title = re.sub(r"^Title:\s*", "", title, flags=re.IGNORECASE)

        (paper_dir / "article_raw.md").write_text(article_text, encoding="utf-8")
        print(f"[Web] Article text saved ({len(article_text)} chars)")
    except Exception as e:
        print(f"[Web] Failed to fetch article text: {e}")
        article_text = ""
        title = short_name

    # 2. Extract images
    try:
        saved_images = extract_images(url, figures_dir)
    except Exception as e:
        print(f"[Web] Image extraction failed: {e}")
        saved_images = []

    # 3. Generate frontmatter template
    img_index = generate_markdown_index(saved_images) if saved_images else ""

    frontmatter = f"""---
title: "{title}"
url: "{url}"
mode: deep-dive
tags: [paper, deep-dive]
status: to-read
---

# {title}

> Source: {url}

## 论文基本信息 & TL;DR

| 字段 | 内容 |
|------|------|
| **标题** | {title} |
| **来源** | {url} |
| **类型** | 网页文章 |

## TL;DR

（待补充）

---

## 沿论文脉络的逐节解读

（请基于 article_raw.md 进行精读）

{img_index}

---

> [!note] 精读提示
> 网页文章的原始文本已保存到 `article_raw.md`。
> 请在此基础上继续完成 Deep Dive 的其余 11 个 Section。
"""

    md_path = paper_dir / "deep-dive.md"
    md_path.write_text(frontmatter, encoding="utf-8")
    print(f"[Web] Template saved: {md_path}")

    metadata = {
        "title": title,
        "url": url,
        "type": "web-article",
        "output_dir": str(paper_dir),
        "figures_count": len(saved_images),
        "figures_dir": str(figures_dir),
    }

    meta_path = paper_dir / "metadata.json"
    meta_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")

    return metadata


def main():
    parser = argparse.ArgumentParser(description="Fetch paper metadata, PDF, and structured Markdown")
    parser.add_argument("url_or_id", help="arXiv URL/ID, or other paper URL")
    parser.add_argument("--output", "-o", default="./papers", help="Output directory")
    parser.add_argument("--ss-key", help="Semantic Scholar API key")
    parser.add_argument("--no-mineru", action="store_true", help="Skip MinerU parsing (PDF only)")
    parser.add_argument(
        "--backend", "-b", default="pipeline",
        choices=["pipeline", "hybrid-auto-engine", "vlm-auto-engine", "hybrid-http-client", "vlm-http-client"],
        help="MinerU parsing backend (default: pipeline)",
    )
    args = parser.parse_args()

    output_dir = Path(args.output)
    arxiv_id = extract_arxiv_id(args.url_or_id)

    if arxiv_id:
        print(f"Detected arXiv ID: {arxiv_id}")
        meta = fetch_arxiv(arxiv_id, output_dir / arxiv_id, backend=args.backend)

        try:
            ss_data = fetch_semantic_scholar(meta["title"], args.ss_key)
            if ss_data:
                meta["semantic_scholar"] = ss_data
                meta_path = output_dir / arxiv_id / "metadata.json"
                meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False))
                print(f"Citation count: {ss_data.get('citationCount', 'N/A')}")
        except Exception as e:
            print(f"Semantic Scholar fetch failed: {e}")

        print(json.dumps(meta, indent=2, ensure_ascii=False))
    else:
        print(f"Non-arXiv URL detected: {args.url_or_id}")
        meta = fetch_web_article(args.url_or_id, output_dir)
        print(json.dumps(meta, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
