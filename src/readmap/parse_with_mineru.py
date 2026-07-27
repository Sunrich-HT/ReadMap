#!/usr/bin/env python3
"""
MinerU PDF 解析封装
将 PDF 解析为结构化 Markdown + 精确提取图片 + 结构化 JSON
替代原有的 extract_figures.py，同时提供比纯文本更好的精读输入
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


def run_mineru(pdf_path: Path, output_dir: Path, backend: str = "pipeline") -> dict:
    """
    调用 MinerU 解析 PDF
    
    Args:
        pdf_path: PDF 文件路径
        output_dir: MinerU 原始输出目录
        backend: 解析后端 (pipeline/vlm/hybrid)，默认 pipeline 纯 CPU
    
    Returns:
        {"md_path": Path, "images_dir": Path, "content_list_path": Path, "success": bool}
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # MinerU pulls in a heavy, conflicting dependency set, so the README asks
    # for it in a separate .venv-mineru. The code looked only for .venv, i.e.
    # the one environment guaranteed *not* to have MinerU installed.
    script_dir = Path(__file__).resolve().parent
    python_exec = None
    env_override = os.environ.get("MINERU_PYTHON", "").strip()
    if env_override and Path(env_override).exists():
        python_exec = Path(env_override)
    else:
        for level in range(5):
            for venv_name in (".venv-mineru", ".venv"):
                candidate = script_dir.parents[level] / venv_name / "bin" / "python"
                if candidate.exists():
                    python_exec = candidate
                    break
            if python_exec:
                break
    if not python_exec:
        python_exec = Path(sys.executable)
    
    env = os.environ.copy()
    env["CUDA_VISIBLE_DEVICES"] = ""  # 强制纯 CPU，避免 OOM
    
    cmd = [
        str(python_exec), "-m", "mineru.cli.client",
        "-p", str(pdf_path),
        "-o", str(output_dir),
        "-b", backend,
    ]
    
    print(f"[MinerU] Parsing {pdf_path.name} with backend={backend} ...")
    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    
    if result.returncode != 0:
        print(f"[MinerU ERROR] {result.stderr}")
        return {"success": False, "error": result.stderr}
    
    # MinerU 输出结构: output_dir/{stem}/auto/{stem}.md
    stem = pdf_path.stem
    auto_dir = output_dir / stem / "auto"
    
    md_path = auto_dir / f"{stem}.md"
    images_dir = auto_dir / "images"
    content_list_path = auto_dir / f"{stem}_content_list.json"
    
    return {
        "success": md_path.exists(),
        "md_path": md_path,
        "images_dir": images_dir if images_dir.exists() else None,
        "content_list_path": content_list_path if content_list_path.exists() else None,
        "raw_output_dir": auto_dir,
    }


def organize_output(mineru_result: dict, paper_dir: Path) -> dict:
    """
    整理 MinerU 输出到标准目录结构
    
    输出:
        paper_dir/
            paper.md              # 结构化 Markdown
            paper.json            # 结构化 content_list
            images/               # 提取的图片
            ...
    """
    if not mineru_result["success"]:
        return mineru_result
    
    paper_dir.mkdir(parents=True, exist_ok=True)
    
    # 复制 Markdown
    md_src = mineru_result["md_path"]
    md_dst = paper_dir / "paper.md"
    shutil.copy2(md_src, md_dst)
    
    # 复制 JSON
    if mineru_result.get("content_list_path"):
        shutil.copy2(mineru_result["content_list_path"], paper_dir / "paper.json")
    
    # 复制图片
    images_dst = paper_dir / "images"
    if mineru_result.get("images_dir") and mineru_result["images_dir"].exists():
        if images_dst.exists():
            shutil.rmtree(images_dst)
        shutil.copytree(mineru_result["images_dir"], images_dst)
        # 统计图片
        image_files = list(images_dst.glob("*"))
        print(f"[MinerU] Extracted {len(image_files)} images -> {images_dst}")
    
    # 更新 Markdown 中的图片路径为相对路径
    content = md_dst.read_text(encoding="utf-8")
    # MinerU 默认输出 ![](images/xxx.jpg)，已经相对 auto_dir
    # 我们复制到 paper_dir/images/，路径保持不变
    
    return {
        "success": True,
        "md_path": md_dst,
        "images_dir": images_dst if images_dst.exists() else None,
        "content_list_path": paper_dir / "paper.json" if (paper_dir / "paper.json").exists() else None,
    }


def parse_paper(pdf_path: Path, paper_dir: Path, backend: str = "pipeline") -> dict:
    """
    主入口：解析 PDF 并整理输出
    """
    # 使用临时目录作为 MinerU 原始输出
    tmp_output = paper_dir / ".mineru_raw"
    
    try:
        result = run_mineru(pdf_path, tmp_output, backend)
        if result["success"]:
            organized = organize_output(result, paper_dir)
            return organized
        return result
    finally:
        # 清理临时目录（可选，保留用于调试）
        # shutil.rmtree(tmp_output, ignore_errors=True)
        pass


def main():
    parser = argparse.ArgumentParser(description="Parse PDF with MinerU")
    parser.add_argument("pdf", help="Path to PDF file")
    parser.add_argument("--output-dir", "-o", required=True, help="Output directory")
    parser.add_argument("--backend", "-b", default="pipeline",
                        choices=["pipeline", "hybrid-auto-engine", "vlm-auto-engine", "hybrid-http-client", "vlm-http-client"])
    args = parser.parse_args()
    
    result = parse_paper(Path(args.pdf), Path(args.output_dir), args.backend)
    print(json.dumps({k: str(v) if isinstance(v, Path) else v for k, v in result.items()}, indent=2))
    
    sys.exit(0 if result.get("success") else 1)


if __name__ == "__main__":
    main()
