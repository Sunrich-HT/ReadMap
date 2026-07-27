#!/usr/bin/env python3
r"""
MinerU pipeline 输出后处理
针对已知问题做修复：
1. LaTeX 清理：去掉 \begin{array} { r } 中多余的空格和 { } 包裹
2. 报告 images/ 中未被引用的图片（删除需显式开启）
3. 输出 paper_clean.md
"""

import argparse
import re
import shutil
from pathlib import Path


def clean_latex(content: str) -> str:
    r"""
    清理 MinerU 生成的混乱 LaTeX 格式。
    主要问题：\begin{array} { r } { ... } \end{array} 中多余空格和 { } 包裹
    """
    # 规则 1: 去掉 array 环境外围的 { } 包裹
    # $$ \begin{array} { r } { \begin{array} { r l } & { ... } \end{array} } \end{array} $$
    # → $$ \begin{array}{rl} ... \end{array} $$
    def fix_array_env(match):
        inner = match.group(1)
        # 去掉最外层的 { }
        inner = inner.strip()
        if inner.startswith('{') and inner.endswith('}'):
            inner = inner[1:-1].strip()
        # 简化 \begin{array} { r } → \begin{array}{r}
        inner = re.sub(r'\\begin\{array\}\s*\{\s*r\s*\}', r'\\begin{array}{r}', inner)
        inner = re.sub(r'\\begin\{array\}\s*\{\s*rl\s*\}', r'\\begin{array}{rl}', inner)
        inner = re.sub(r'\\end\{array\}', r'\\end{array}', inner)
        # 去掉 & { ... } 中的多余 { }
        inner = re.sub(r'&\s*\{\s*', '& ', inner)
        inner = re.sub(r'\s*\}\s*\\\\', r' \\', inner)
        inner = re.sub(r'\s*\}\s*\\end', r' \\end', inner)
        # 去掉 \qquad \mathrm { w h e r e ~ h e a d } 中的字母间空格
        inner = re.sub(r'\\mathrm\s*\{\s*', r'\\mathrm{', inner)
        inner = re.sub(r'\\text\s*\{\s*', r'\\text{', inner)
        inner = re.sub(r'\\operatorname\*\s*\{\s*', r'\\operatorname*{', inner)
        inner = re.sub(r'\\mathrm\{([^}]+)\}', lambda m: '\\mathrm{' + re.sub(r'\s+', '', m.group(1)) + '}', inner)
        # 清理 \mathbb { R } → \mathbb{R}
        inner = re.sub(r'\\mathbb\s*\{\s*([^}]+)\s*\}', r'\\mathbb{\1}', inner)
        # 清理下标中的多余空格：d _ { \mathrm { m o d e l } } → d_{\mathrm{model}}
        inner = re.sub(r'_\s*\{\s*', '_{', inner)
        inner = re.sub(r'\^\s*\{\s*', '^{', inner)
        inner = re.sub(r'\}\s*\^\s*\{', '}^{', inner)
        inner = re.sub(r'\}\s*_\s*\{', '}_{', inner)
        # 清理变量名中的空格：M u l t i H e a d → MultiHead
        inner = re.sub(r'\\mathrm\{([^}]+)\}', lambda m: '\\mathrm{' + re.sub(r'(?<!\\)\s+', '', m.group(1)) + '}', inner)
        return f'$$\n{inner}\n$$'

    # 匹配被 $$...$$ 包裹的 array 环境
    content = re.sub(
        r'\$\$\s*\\begin\{array\}\s*\{\s*r\s*\}\s*\{\s*(.*?)\s*\}\s*\\end\{array\}\s*\$\$',
        fix_array_env,
        content,
        flags=re.DOTALL
    )

    # 规则 2: 清理行内公式中的 \begin{array} { r } { ... } \end{array}
    def fix_inline_array(match):
        inner = match.group(1)
        # 简化
        inner = re.sub(r'\\begin\{array\}\s*\{\s*r\s*\}\s*\{\s*', '', inner)
        inner = re.sub(r'\s*\}\s*\\end\{array\}', '', inner)
        # 清理 \mathbb { R } → \mathbb{R}
        inner = re.sub(r'\\mathbb\s*\{\s*([^}]+)\s*\}', r'\\mathbb{\1}', inner)
        # 清理下标
        inner = re.sub(r'_\s*\{\s*', '_{', inner)
        inner = re.sub(r'\^\s*\{\s*', '^{', inner)
        # 清理 \mathrm { ... }
        inner = re.sub(r'\\mathrm\s*\{\s*', r'\\mathrm{', inner)
        inner = re.sub(r'\\mathrm\{([^}]+)\}', lambda m: '\\mathrm{' + re.sub(r'(?<!\\)\s+', '', m.group(1)) + '}', inner)
        return f'${inner}$'

    content = re.sub(
        r'\$\s*\\begin\{array\}\s*\{\s*r\s*\}\s*\{\s*(.*?)\s*\}\s*\\end\{array\}\s*\$',
        fix_inline_array,
        content,
        flags=re.DOTALL
    )

    # 规则 3: 清理独立的 \mathrm { M u l t i H e a d } → \mathrm{MultiHead}
    content = re.sub(
        r'\\mathrm\s*\{\s*([^}]+)\s*\}',
        lambda m: '\\mathrm{' + re.sub(r'(?<!\\)\s+', '', m.group(1)) + '}',
        content
    )

    # 规则 4: 清理 \operatorname* { m a x } → \operatorname*{max}
    content = re.sub(
        r'\\operatorname\*\s*\{\s*([^}]+)\s*\}',
        lambda m: '\\operatorname*{' + re.sub(r'(?<!\\)\s+', '', m.group(1)) + '}',
        content
    )

    # 规则 5: 清理 "a \ : = \ : b" 这类被拆开的赋值符号
    content = re.sub(r'\$\s*([A-Za-z])\s*\\\s*:\s*=\s*\\\s*:\s*(\d+)\s*\$', r'$\1 := \2$', content)

    # 规则 6: 清理下标中的空格：W _ { 1 } → W_1，b _ { 1 } → b_1
    content = re.sub(r'([a-zA-Z])\s*_\s*\{\s*(\d+)\s*\}', r'\1_{\2}', content)
    # 清理下标变量：d _ { \mathrm { model } } → d_{\mathrm{model}}
    content = re.sub(r'([a-zA-Z])\s*_\s*\{\s*\\mathrm\{([^}]+)\}\s*\}', r'\1_{\\mathrm{\2}}', content)

    # 规则 7: 括号与逗号周围的空格 —— 只在数学环境内做。
    # 这些替换原本作用于整篇文档，会压掉 Markdown 表格的对齐空格和代码块缩进，
    # 为了修公式而破坏正文是不划算的交换。
    def _tidy_math(match):
        inner = match.group(0)
        inner = re.sub(r'\(\s+', '(', inner)
        inner = re.sub(r'\s+\)', ')', inner)
        inner = re.sub(r'\s*,\s*', ', ', inner)
        return re.sub(r'  +', ' ', inner)

    content = re.sub(r'\$\$.*?\$\$', _tidy_math, content, flags=re.DOTALL)
    content = re.sub(r'(?<!\$)\$[^$\n]+\$(?!\$)', _tidy_math, content)

    # 规则 8: 清理 \mathrm{head}_{\mathrm{h} } → \mathrm{head}_{\mathrm{h}}
    content = re.sub(r'\\mathrm\{([^}]+)\}_\{\\mathrm\{([^}]+)\}\s*\}', r'\\mathrm{\1}_{\\mathrm{\2}}', content)

    return content


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


def find_unreferenced_images(content: str, images_dir: Path) -> list[Path]:
    """Images on disk that the Markdown never references.

    Matching is by filename appearing anywhere in the text, which is a weak
    test — hence reporting rather than deleting by default.
    """
    if not images_dir or not images_dir.exists():
        return []
    return [
        p for p in sorted(images_dir.iterdir())
        if p.suffix.lower() in IMAGE_SUFFIXES and p.name not in content
    ]


def remove_unreferenced_images(content: str, images_dir: Path, *, delete: bool = False) -> int:
    """Report — and only on request, delete — unreferenced images.

    This used to unlink files unconditionally, and only ``.jpg`` ones, on every
    fetch. Deleting a user's extracted figures because a filename did not appear
    in a text file is not a cleanup step worth taking without being asked.
    """
    orphans = find_unreferenced_images(content, images_dir)
    for path in orphans:
        if delete:
            path.unlink()
            print(f"  [REMOVED] {path.name} (unreferenced)")
        else:
            print(f"  [ORPHAN] {path.name} (unreferenced; pass --delete-orphans to remove)")
    return len(orphans)


def postprocess(mineru_md_path: Path, images_dir: Path, output_path: Path | None = None,
                *, delete_orphans: bool = False) -> Path:
    """主入口"""
    if output_path is None:
        output_path = mineru_md_path.with_name("paper_clean.md")

    print(f"[PostProcess] Input: {mineru_md_path}")
    content = mineru_md_path.read_text(encoding="utf-8")
    original = content

    # 1. 清理 LaTeX
    print("\n[1/2] Cleaning LaTeX formatting...")
    content = clean_latex(content)

    # 2. 未被引用的图片：默认只报告
    print("\n[2/2] Checking for unreferenced images...")
    removed = remove_unreferenced_images(content, images_dir, delete=delete_orphans)

    # 4. 清理多余空行
    content = re.sub(r'\n{3,}', '\n\n', content)

    output_path.write_text(content, encoding="utf-8")

    print(f"\n{'='*50}")
    print(f"Done: {output_path}")
    print(f"  Size: {len(original)} → {len(content)} chars")
    print(f"  Unreferenced images: {removed}{' (deleted)' if delete_orphans else ' (kept)'}")
    print(f"{'='*50}")
    return output_path


def main():
    parser = argparse.ArgumentParser(description="Post-process MinerU pipeline output")
    parser.add_argument("md_file", help="Path to MinerU generated markdown")
    parser.add_argument("--images-dir", "-i", help="Path to images directory")
    parser.add_argument("--output", "-o", help="Output path")
    parser.add_argument("--delete-orphans", action="store_true",
                        help="Actually delete unreferenced images (default: report only)")
    args = parser.parse_args()

    md_path = Path(args.md_file)
    images_dir = Path(args.images_dir) if args.images_dir else md_path.parent / "images"
    output_path = Path(args.output) if args.output else None
    postprocess(md_path, images_dir, output_path, delete_orphans=args.delete_orphans)


if __name__ == "__main__":
    main()
