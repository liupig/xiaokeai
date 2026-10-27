#!/usr/bin/env python3
"""把 Seedream 原图收成透明底图标，并导出一张按界面尺寸排的验收图。"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

# Pillow 8 没有 Resampling / Transpose 枚举，常量和 9.1+ 的枚举值相同。
if not hasattr(Image, "Resampling"):
    class _Resampling:
        LANCZOS = Image.LANCZOS
    Image.Resampling = _Resampling  # type: ignore[attr-defined]
if not hasattr(Image, "Transpose"):
    class _Transpose:
        FLIP_TOP_BOTTOM = Image.FLIP_TOP_BOTTOM
    Image.Transpose = _Transpose  # type: ignore[attr-defined]

REPO = Path(__file__).resolve().parent.parent
RAW_DIR = REPO / "assets" / "ui-icons" / "raw"
OUT_DIR = REPO / "frontend" / "src" / "assets" / "icons"
PREVIEW = REPO / "assets" / "ui-icons" / "preview.png"

# 界面里大约 22px，文件用 96（约 4 倍）保住金线。
ICON_PX = 96


def key_and_clean(im: Image.Image) -> Image.Image:
    rgb = np.asarray(im.convert("RGB"))
    r = rgb[:, :, 0].astype(np.int16)
    g = rgb[:, :, 1].astype(np.int16)
    b = rgb[:, :, 2].astype(np.int16)
    lum = (r.astype(np.int32) + g + b) / 3
    # 夜色底：暗且偏蓝。木匣的深褐、朱红录制钮留下。
    navy = (lum < 52) & (b + 8 >= r) & (b + 4 >= g)
    alpha = np.where(navy, 0, 255).astype(np.uint8)
    rgba = np.dstack([rgb, alpha])
    out = Image.fromarray(rgba)
    return _drop_specks(out)


def _drop_specks(im: Image.Image) -> Image.Image:
    """只留主体，以及落在主体框里的零件（宝石、眼睛、窗里的线）。框外金粉丢掉。"""
    arr = np.asarray(im).copy()
    mask = arr[:, :, 3] > 40
    try:
        from scipy import ndimage
    except Exception:
        return im
    labeled, n = ndimage.label(mask)
    if n == 0:
        return im
    counts = np.bincount(labeled.ravel())
    largest = int(np.argmax(counts[1:]) + 1)
    slices = ndimage.find_objects(labeled)
    sl = slices[largest - 1]
    if sl is None:
        return im
    pad = int(max(arr.shape[0], arr.shape[1]) * 0.04)
    y0 = sl[0].start - pad
    y1 = sl[0].stop + pad
    x0 = sl[1].start - pad
    x1 = sl[1].stop + pad
    drop_ids: list[int] = []
    for i, slc in enumerate(slices, 1):
        if slc is None or i == largest:
            continue
        cy = (slc[0].start + slc[0].stop) / 2
        cx = (slc[1].start + slc[1].stop) / 2
        inside = x0 <= cx <= x1 and y0 <= cy <= y1
        if not inside or counts[i] < 200:
            drop_ids.append(i)
    if drop_ids:
        lut = np.zeros(n + 1, dtype=bool)
        lut[drop_ids] = True
        arr[lut[labeled], 3] = 0
    return Image.fromarray(arr)


def thicken(im: Image.Image, radius: int) -> Image.Image:
    if radius <= 0:
        return im
    arr = np.asarray(im).copy()
    alpha = Image.fromarray(arr[:, :, 3])
    grown = alpha.filter(ImageFilter.MaxFilter(radius * 2 + 1))
    grown_a = np.asarray(grown)
    new_px = (grown_a > 40) & (arr[:, :, 3] < 40)
    try:
        from scipy.ndimage import distance_transform_edt
        inv = arr[:, :, 3] < 40
        _, (iy, ix) = distance_transform_edt(inv, return_indices=True)
        arr[new_px, :3] = arr[iy[new_px], ix[new_px], :3]
    except Exception:
        src = arr[:, :, 3] > 80
        med = np.median(arr[src][:, :3], axis=0).astype(np.uint8) if src.any() else np.array([212, 175, 90])
        arr[new_px, 0] = med[0]
        arr[new_px, 1] = med[1]
        arr[new_px, 2] = med[2]
    arr[:, :, 3] = np.maximum(arr[:, :, 3], np.where(grown_a > 40, grown_a, 0).astype(np.uint8))
    return Image.fromarray(arr)


def fit_square(im: Image.Image, size: int, pad_ratio: float = 0.08) -> Image.Image:
    arr = np.asarray(im)
    ys, xs = np.where(arr[:, :, 3] > 24)
    if len(xs) == 0:
        return Image.new("RGBA", (size, size), (0, 0, 0, 0))
    x0, x1 = int(xs.min()), int(xs.max())
    y0, y1 = int(ys.min()), int(ys.max())
    crop = im.crop((x0, y0, x1 + 1, y1 + 1))
    side = max(crop.size)
    pad = int(side * pad_ratio)
    canvas = Image.new("RGBA", (side + pad * 2, side + pad * 2), (0, 0, 0, 0))
    ox = (canvas.size[0] - crop.size[0]) // 2
    oy = (canvas.size[1] - crop.size[1]) // 2
    canvas.paste(crop, (ox, oy), crop)
    return canvas.resize((size, size), Image.Resampling.LANCZOS)


def process_one(src: Path, radius: int) -> Image.Image:
    # 先收到 256 再加粗，加粗发生在图标尺度上，金线缩小后还在。
    im = key_and_clean(Image.open(src))
    im = fit_square(im, 256)
    im = thicken(im, radius)
    return im.resize((ICON_PX, ICON_PX), Image.Resampling.LANCZOS)


def contact(icons: list[tuple[str, Image.Image]]) -> Image.Image:
    """每个图标两档：顶栏 22px、再大一档 36px，铺在夜色按钮底上。"""
    cols = 5
    cell_w, cell_h = 160, 120
    rows = (len(icons) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cell_w, rows * cell_h), (14, 14, 26))
    draw = ImageDraw.Draw(sheet)
    for i, (name, icon) in enumerate(icons):
        c, r = i % cols, i // cols
        ox, oy = c * cell_w, r * cell_h
        for k, px in enumerate((22, 36)):
            small = icon.resize((px, px), Image.Resampling.LANCZOS)
            x = ox + 18 + k * 70
            y = oy + 28
            draw.rounded_rectangle(
                [x - 7, y - 7, x + px + 7, y + px + 7],
                radius=10,
                fill=(32, 32, 52),
            )
            sheet.paste(small, (x, y), small)
        draw.text((ox + 12, oy + cell_h - 22), name, fill=(220, 200, 150))
    return sheet


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    icons: list[tuple[str, Image.Image]] = []
    # 细线多扩，实心少扩。折角原图朝上，界面要朝下。
    # 半径是在 256px 稿上的像素。实心符号不加，细线加 2。
    radius_of = {
        "settings": 2, "review": 2, "code": 2, "chevron": 0, "film": 1,
        "tarot": 1, "log": 0, "assets": 1, "mic": 1, "cam": 1, "snap": 0,
        "quick": 0, "keepsake": 1, "rec": 0, "send": 0,
        "reload": 2, "pet": 1, "glance": 1,
    }
    for src in sorted(RAW_DIR.glob("*.png")):
        icon = process_one(src, radius_of.get(src.stem, 3))
        if src.stem == "chevron":
            icon = icon.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
        icon.save(OUT_DIR / f"{src.stem}.png")
        icons.append((src.stem, icon))
        print(f"fit {src.stem}", flush=True)
    if icons:
        contact(icons).save(PREVIEW)
        print(f"preview {PREVIEW}")


if __name__ == "__main__":
    main()
