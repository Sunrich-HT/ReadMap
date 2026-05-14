#!/usr/bin/env python3
"""
MinerU pipeline 输出后处理
针对已知问题做修复：
1. LaTeX 清理：去掉 \begin{array} { r } 中多余的空格和 { } 包裹
2. Table 3 修复：用清晰截图替代错乱的 HTML
3. 删除冗余图片：清理 images/ 中未被引用的图片
4. 输出 paper_clean.md
"""

import argparse
import re
import shutil
from pathlib import Path


def clean_latex(content: str) -> str:
    """
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

    # 规则 5: 清理普通下标中的空格：h \ : = \ : 8 → h := 8
    content = re.sub(r'\$\s*h\s*\\\s*:\s*=\s*\\\s*:\s*8\s*\$', r'$h := 8$', content)

    # 规则 6: 清理下标中的空格：W _ { 1 } → W_1，b _ { 1 } → b_1
    content = re.sub(r'([a-zA-Z])\s*_\s*\{\s*(\d+)\s*\}', r'\1_{\2}', content)
    # 清理下标变量：d _ { \mathrm { model } } → d_{\mathrm{model}}
    content = re.sub(r'([a-zA-Z])\s*_\s*\{\s*\\mathrm\{([^}]+)\}\s*\}', r'\1_{\\mathrm{\2}}', content)

    # 规则 7: 清理括号周围的空格：( 0 , x → (0, x
    content = re.sub(r'\(\s+', '(', content)
    content = re.sub(r'\s+\)', ')', content)
    # 清理逗号周围的空格：, xW → , xW（保留一个空格在逗号后）
    content = re.sub(r',\s+', ', ', content)
    # 清理多余空格：两个空格变一个
    content = re.sub(r'  +', ' ', content)

    # 规则 8: 清理 \mathrm{head}_{\mathrm{h} } → \mathrm{head}_{\mathrm{h}}
    content = re.sub(r'\\mathrm\{([^}]+)\}_\{\\mathrm\{([^}]+)\}\s*\}', r'\\mathrm{\1}_{\\mathrm{\2}}', content)

    return content


def fix_table3(content: str) -> str:
    """
    修复 Table 3：MinerU 的 HTML 结构错乱，用清晰截图替代。
    Table 3 截图: da52b01f55903301b9bf6335519ab22f1dec04faea092f8e6892cfbd4c9a6aae.jpg
    """
    # 找到 Table 3 的 caption 和紧跟的 <table>...<table>
    pattern = r'(Table 3: Variations on the Transformer architecture\.[^\n]*)\n*<table>.*?</table>'

    def replacer(match):
        caption = match.group(1)
        return (
            f'{caption}\n\n'
            f'> [!note] 表格解析说明\n'
            f'> 以下为 PDF 原文截图，MinerU 自动解析的 HTML 表格结构存在错乱，故使用原图替代。\n\n'
            f'![](images/da52b01f55903301b9bf6335519ab22f1dec04faea092f8e6892cfbd4c9a6aae.jpg)\n'
        )

    content, n = re.subn(pattern, replacer, content, flags=re.DOTALL)
    if n > 0:
        print(f"  [FIXED] Table 3 replaced with screenshot (n={n})")
    return content


def remove_unreferenced_images(content: str, images_dir: Path) -> int:
    """
    删除 images/ 中未被 markdown content 引用的图片
    """
    removed = 0
    for img_path in list(images_dir.glob("*.jpg")):
        if img_path.name not in content:
            img_path.unlink()
            removed += 1
            print(f"  [REMOVED] {img_path.name} (unreferenced)")
    return removed


def postprocess(mineru_md_path: Path, images_dir: Path, output_path: Path | None = None) -> Path:
    """主入口"""
    if output_path is None:
        output_path = mineru_md_path.with_name("paper_clean.md")

    print(f"[PostProcess] Input: {mineru_md_path}")
    content = mineru_md_path.read_text(encoding="utf-8")
    original = content

    # 1. 清理 LaTeX
    print("\n[1/3] Cleaning LaTeX formatting...")
    content = clean_latex(content)

    # 2. 修复 Table 3
    print("\n[2/3] Fixing Table 3...")
    content = fix_table3(content)

    # 3. 删除冗余图片（基于最终 content，避免误删修复后新增引用的图片）
    print("\n[3/3] Removing unreferenced images...")
    removed = remove_unreferenced_images(content, images_dir)

    # 4. 清理多余空行
    content = re.sub(r'\n{3,}', '\n\n', content)

    output_path.write_text(content, encoding="utf-8")

    print(f"\n{'='*50}")
    print(f"Done: {output_path}")
    print(f"  Size: {len(original)} → {len(content)} chars")
    print(f"  Images removed: {removed}")
    print(f"{'='*50}")
    return output_path


def main():
    parser = argparse.ArgumentParser(description="Post-process MinerU pipeline output")
    parser.add_argument("md_file", help="Path to MinerU generated markdown")
    parser.add_argument("--images-dir", "-i", help="Path to images directory")
    parser.add_argument("--output", "-o", help="Output path")
    args = parser.parse_args()

    md_path = Path(args.md_file)
    images_dir = Path(args.images_dir) if args.images_dir else md_path.parent / "images"
    output_path = Path(args.output) if args.output else None
    postprocess(md_path, images_dir, output_path)


if __name__ == "__main__":
    main()
