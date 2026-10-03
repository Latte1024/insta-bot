#!/usr/bin/env python3
"""写真を images/ に追加: EXIF回転反映 → 4:5〜1.91:1 の外なら中央切り抜き → JPEG保存 → commit & push。

usage: python add.py 写真またはフォルダ [...]   (要 Pillow: pip install pillow / 手元専用)
       python add.py --selftest
"""
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageOps

IMAGES = Path(__file__).parent / "images"
EXT = {".jpg", ".jpeg", ".png", ".webp"}


def fit(im):
    im = ImageOps.exif_transpose(im).convert("RGB")
    w, h = im.size
    if w / h < 0.8:  # 縦長すぎ: 上下を切る
        nh = round(w / 0.8); t = (h - nh) // 2
        return im.crop((0, t, w, t + nh))
    if w / h > 1.91:  # 横長すぎ: 左右を切る
        nw = round(h * 1.91); l = (w - nw) // 2
        return im.crop((l, 0, l + nw, h))
    return im


def selftest():
    for size in [(1000, 3000), (3000, 1000), (1000, 1000), (1844, 4096)]:
        w, h = fit(Image.new("RGB", size)).size
        assert 0.8 - 1e-3 <= w / h <= 1.91, (size, w, h)
    print("selftest OK")


def main(args):
    files = [f for a in args for p in [Path(a)]
             for f in (sorted(p.iterdir()) if p.is_dir() else [p]) if f.suffix.lower() in EXT]
    if not files:
        sys.exit("no images found")
    IMAGES.mkdir(exist_ok=True)
    for f in files:
        out = IMAGES / (f.stem + ".jpg")
        fit(Image.open(f)).save(out, "JPEG", quality=92)
        print("added", out.name)
    git = lambda *a: subprocess.run(["git", "-C", str(IMAGES.parent), *a], check=True)
    git("add", "images")
    if subprocess.run(["git", "-C", str(IMAGES.parent), "diff", "--cached", "--quiet"]).returncode:
        git("commit", "-m", f"add {len(files)} image(s)")
        git("push")


if __name__ == "__main__":
    selftest() if sys.argv[1:] == ["--selftest"] else main(sys.argv[1:])
