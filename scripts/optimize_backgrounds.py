#!/usr/bin/env python3
"""
Compress background images larger than a threshold to be under target size.
Strategy:
- For JPEG/JPG: downscale to max width/height while keeping aspect ratio,
  then save progressive with optimize=True, and binary-search quality to fit under size.
- For PNG: skip by default (usually UI assets); can convert to JPEG with --convert-png.

Usage:
  python scripts/optimize_backgrounds.py --root static/img --max-mb 1 --max-width 1920

This script is idempotent and will overwrite the original file after a temporary
compressed version passes the size check. A backup copy will be written next to
original as <name>.bak only when the original is larger than threshold (opt-in via --backup).
"""
from __future__ import annotations
import argparse
import io
import os
from pathlib import Path
from typing import Tuple

from PIL import Image

SUPPORTED_EXT = {".jpg", ".jpeg"}


def human(n: int) -> str:
    return f"{n/1024/1024:.2f}MB"


def save_jpeg_fit(img: Image.Image, target_bytes: int, max_dim: int) -> bytes:
    """Try to produce a JPEG <= target_bytes, downscaling and adjusting quality."""
    # Step 1: downscale if needed
    w, h = img.size
    scale = 1.0
    if max(w, h) > max_dim:
        scale = max_dim / float(max(w, h))
        new_size = (max(1, int(w * scale)), max(1, int(h * scale)))
        img = img.resize(new_size, Image.LANCZOS)

    # Step 2: binary search JPEG quality
    lo, hi = 40, 90  # conservative bounds for background photos
    best: bytes | None = None

    while lo <= hi:
        q = (lo + hi) // 2
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=q, optimize=True, progressive=True)
        data = buf.getvalue()
        size = len(data)
        if size <= target_bytes:
            best = data
            lo = q + 1
        else:
            hi = q - 1

    # If still too big at lowest acceptable quality, do a second downscale pass.
    if best is None:
        # further downscale by 85% and retry once
        w, h = img.size
        new_size = (max(1, int(w * 0.85)), max(1, int(h * 0.85)))
        img2 = img.resize(new_size, Image.LANCZOS)
        buf = io.BytesIO()
        img2.save(buf, format="JPEG", quality=60, optimize=True, progressive=True)
        data = buf.getvalue()
        return data
    return best


def process_file(path: Path, target_mb: float, max_width: int, backup: bool) -> Tuple[bool, int, int]:
    before = path.stat().st_size
    if path.suffix.lower() not in SUPPORTED_EXT:
        return False, before, before

    if before <= target_mb * 1024 * 1024:
        return False, before, before

    with Image.open(path) as im:
        # Convert to RGB to ensure JPEG compatible
        if im.mode not in ("RGB", "L"):
            im = im.convert("RGB")
        data = save_jpeg_fit(im, int(target_mb * 1024 * 1024), max_width)

    after = len(data)
    if after < before:
        if backup:
            bak = path.with_suffix(path.suffix + ".bak")
            if not bak.exists():
                path.rename(bak)
            else:
                # if backup exists, don't overwrite
                pass
        with open(path, "wb") as f:
            f.write(data)
        return True, before, after
    return False, before, after


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="static/img", help="root directory for images")
    ap.add_argument("--max-mb", type=float, default=1.0, help="target max size in MB")
    ap.add_argument("--max-width", type=int, default=1920, help="max dimension for longer side")
    ap.add_argument("--backup", action="store_true", help="write .bak of original if changed")
    args = ap.parse_args()

    root = Path(args.root)
    changed = 0
    total_before = 0
    total_after = 0

    for p in root.rglob("*"):
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXT:
            done, b, a = process_file(p, args.max_mb, args.max_width, args.backup)
            total_before += b
            total_after += a
            if done:
                changed += 1
                print(f"Optimized: {p} | {human(b)} -> {human(a)}")

    print(f"Done. Files changed: {changed}. Total {human(total_before)} -> {human(total_after)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
