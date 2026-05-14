#!/usr/bin/env python3
"""
网页文章图片提取器
支持：
  - base64 内联图片（如 transformer-circuits.pub）
  - HTTP(S) 外链图片
  - 生成 markdown 引用索引

用法：
  python extract_web_images.py <url> --output-dir ./papers/2024-05/xxx/figures
"""

import argparse
import base64
import re
import urllib.request
from pathlib import Path
from urllib.parse import urljoin, urlparse


USER_AGENT = "Mozilla/5.0 (compatible; PaperBot/1.0)"


def fetch_html(url: str) -> str:
    """下载网页 HTML"""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        charset = resp.headers.get_content_charset() or "utf-8"
        return resp.read().decode(charset, errors="replace")


def clean_base64(b64data: str) -> str:
    """清理 base64 字符串中的换行和空格"""
    return b64data.replace("\n", "").replace(" ", "").replace("\r", "")


def ext_from_mime(mime: str) -> str:
    """从 MIME type 推断文件扩展名"""
    mime = mime.lower().strip()
    if "png" in mime:
        return "png"
    if "jpg" in mime or "jpeg" in mime:
        return "jpg"
    if "webp" in mime:
        return "webp"
    if "gif" in mime:
        return "gif"
    return "png"


def download_image(url: str, output_path: Path) -> bool:
    """下载外链图片"""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
            if len(data) < 100:
                return False
            output_path.write_bytes(data)
            return True
    except Exception as e:
        print(f"  [WARN] 下载失败 {url}: {e}")
        return False


def extract_images(url: str, output_dir: Path, min_size: int = 5000) -> list[Path]:
    """
    提取网页中的所有图片

    Args:
        url: 网页 URL
        output_dir: 输出目录
        min_size: 最小文件大小（字节），过滤掉小图标

    Returns:
        保存成功的图片路径列表
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    html = fetch_html(url)
    base_url = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
    saved: list[Path] = []
    seen_hashes: set[str] = set()  # 去重

    # ============================================================
    # 1. 提取 base64 内联图片
    # ============================================================
    base64_pattern = re.compile(
        r"<img[^>]*src=[\"'](data:image/([^;]+);base64,([^\"']+))[\"']",
        re.IGNORECASE,
    )
    base64_matches = base64_pattern.findall(html)
    print(f"[WebImg] 发现 {len(base64_matches)} 个 base64 内联图片")

    for i, (full, mime_type, b64data) in enumerate(base64_matches):
        ext = ext_from_mime(mime_type)
        fname = output_dir / f"figure_{len(saved)+1:02d}.{ext}"
        try:
            data = base64.b64decode(clean_base64(b64data))
            if len(data) < min_size:
                continue
            h = hash(data)
            if h in seen_hashes:
                print(f"  [SKIP] {fname.name} (重复)")
                continue
            seen_hashes.add(h)
            fname.write_bytes(data)
            saved.append(fname)
            print(f"  [OK] base64 → {fname.name} ({len(data)} bytes)")
        except Exception as e:
            print(f"  [ERR] base64 figure_{i+1}: {e}")

    # ============================================================
    # 2. 提取 HTTP(S) 外链图片
    # ============================================================
    url_pattern = re.compile(
        r'<img[^>]*src=["\'](https?://[^"\'<>\s]+)["\']',
        re.IGNORECASE,
    )
    url_matches = url_pattern.findall(html)
    # 去重 URL
    unique_urls = []
    seen_urls: set[str] = set()
    for u in url_matches:
        if u not in seen_urls:
            seen_urls.add(u)
            unique_urls.append(u)

    print(f"[WebImg] 发现 {len(unique_urls)} 个外链图片")

    for img_url in unique_urls:
        # 跳过已知的小图标/追踪像素
        if any(k in img_url.lower() for k in ["pixel", "tracking", "beacon", "1x1", "spacer"]):
            continue
        # 推断扩展名
        parsed = urlparse(img_url)
        path = parsed.path.lower()
        if path.endswith(".png"):
            ext = "png"
        elif path.endswith(".jpg") or path.endswith(".jpeg"):
            ext = "jpg"
        elif path.endswith(".webp"):
            ext = "webp"
        elif path.endswith(".gif"):
            ext = "gif"
        else:
            ext = "png"

        fname = output_dir / f"figure_{len(saved)+1:02d}.{ext}"
        if download_image(img_url, fname):
            h = hash(fname.read_bytes())
            if h in seen_hashes:
                print(f"  [SKIP] {fname.name} (重复)")
                fname.unlink()
                continue
            seen_hashes.add(h)
            saved.append(fname)
            print(f"  [OK] url → {fname.name}")

    # ============================================================
    # 3. 尝试提取 <figure> 内的 <img>（某些网站用 picture/source）
    # ============================================================
    # 匹配 <source srcset="..."> 中的第一个 URL
    source_pattern = re.compile(
        r'<source[^>]*srcset=["\']([^"\'<>]+)["\']',
        re.IGNORECASE,
    )
    source_matches = source_pattern.findall(html)
    print(f"[WebImg] 发现 {len(source_matches)} 个 <source> 图片")

    for srcset in source_matches:
        # srcset 格式: "url 1x, url 2x" 或 "url"
        first_url = srcset.split(",")[0].strip().split(" ")[0]
        if not first_url.startswith("http"):
            first_url = urljoin(base_url, first_url)

        if first_url in seen_urls:
            continue
        seen_urls.add(first_url)

        fname = output_dir / f"figure_{len(saved)+1:02d}.png"
        if download_image(first_url, fname):
            h = hash(fname.read_bytes())
            if h in seen_hashes:
                print(f"  [SKIP] {fname.name} (重复)")
                fname.unlink()
                continue
            seen_hashes.add(h)
            saved.append(fname)
            print(f"  [OK] source → {fname.name}")

    print(f"\n[WebImg] 总计保存: {len(saved)} 张图片 → {output_dir}")
    return saved


def generate_markdown_index(saved_images: list[Path], title: str = "论文原图") -> str:
    """生成 markdown 图片引用索引"""
    lines = [f"\n## {title}\n"]
    for i, img_path in enumerate(saved_images, 1):
        rel = f"./{img_path.parent.name}/{img_path.name}"
        lines.append(f"![Figure {i}]({rel})")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Extract images from web articles")
    parser.add_argument("url", help="Article URL")
    parser.add_argument("--output-dir", "-o", required=True, help="Output directory for images")
    parser.add_argument("--min-size", type=int, default=5000, help="Minimum image size in bytes (default: 5000)")
    parser.add_argument("--print-index", action="store_true", help="Print markdown image index to stdout")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    saved = extract_images(args.url, output_dir, min_size=args.min_size)

    if args.print_index:
        print(generate_markdown_index(saved))

    return 0 if saved else 1


if __name__ == "__main__":
    raise SystemExit(main())
