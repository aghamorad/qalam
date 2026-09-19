#!/usr/bin/env python3
"""Turn the icon artwork into a macOS .icns.

    .venv/bin/python tools/make_icon.py                 # use data/icon-source.png
    .venv/bin/python tools/make_icon.py --draw          # draw a fallback instead
    .venv/bin/python tools/make_icon.py --from art.png

The artwork arrives as a flat image on a black background, so two things have to
happen before macOS will accept it: the black has to become real transparency,
and the tile has to be refitted to Apple's icon grid. Apple masks app icons and
spots a tile that sits proud or shy of the grid immediately, so the artwork is
cropped to the tile it actually contains and re-placed at 824 of 1024 points
rather than trusted to have been drawn at that size.

`--draw` paints a plain geometric variant with Qt for when no artwork is
available - offline, or the generator is rate limited. It is deliberately
text-free: an isolated Persian letter at icon size reads to a Latin eye as a
Latin letter, which is a mistake worth not shipping.
"""
import argparse
import math
import subprocess
import sys
from collections import deque
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QPointF, QRectF, Qt                  # noqa: E402
from PySide6.QtGui import (QColor, QFont, QFontDatabase, QGuiApplication,
                           QImage, QLinearGradient, QPainter, QPainterPath,
                           QRadialGradient)                     # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
BUNDLED = ROOT / "persian_ebook" / "data" / "fonts"
OUT = ROOT / "persian_ebook" / "data"
SOURCE = OUT / "icon-source.png"

CANVAS = 1024
INSET = 100.0                    # Apple's grid: the tile is 824 of 1024
SPAN = CANVAS - 2 * int(INSET)   # 824
MASK_WORK = 512                  # resolution the cut-out is solved at
BG_LEVEL = 14                    # at or below this luminance counts as backdrop
EDGE = 8                         # alpha above this counts as part of the tile


def _luma(rgb: int) -> int:
    return (299 * ((rgb >> 16) & 255) + 587 * ((rgb >> 8) & 255)
            + 114 * (rgb & 255)) // 1000


def _components(keep: bytearray, w: int, h: int) -> list[list[int]]:
    """Connected components of `keep`, 4-connected, largest first."""
    seen = bytearray(w * h)
    out: list[list[int]] = []
    for start in range(w * h):
        if not keep[start] or seen[start]:
            continue
        blob: list[int] = []
        queue = deque([start])
        seen[start] = 1
        while queue:
            i = queue.popleft()
            blob.append(i)
            x, y = i % w, i // w
            if x and keep[i - 1] and not seen[i - 1]:
                seen[i - 1] = 1
                queue.append(i - 1)
            if x + 1 < w and keep[i + 1] and not seen[i + 1]:
                seen[i + 1] = 1
                queue.append(i + 1)
            if y and keep[i - w] and not seen[i - w]:
                seen[i - w] = 1
                queue.append(i - w)
            if y + 1 < h and keep[i + w] and not seen[i + w]:
                seen[i + w] = 1
                queue.append(i + w)
        out.append(blob)
    out.sort(key=len, reverse=True)
    return out


def cut_out(src: QImage) -> QImage:
    """Replace the flat backdrop with real alpha.

    A luminance threshold alone is not enough: the artwork carries a few bright
    specks floating in the black, which would survive as opaque confetti. So the
    backdrop is found by flooding inward from the border, only the largest
    remaining island is kept, and any pocket fully enclosed by the tile is
    sealed back in - those are the dark crevices inside the book, not holes.
    """
    work = src.scaled(MASK_WORK, MASK_WORK, Qt.IgnoreAspectRatio,
                      Qt.SmoothTransformation)

    lit = bytearray(MASK_WORK * MASK_WORK)
    for y in range(MASK_WORK):
        for x in range(MASK_WORK):
            if _luma(work.pixel(x, y)) > BG_LEVEL:
                lit[y * MASK_WORK + x] = 1

    outside = bytearray(MASK_WORK * MASK_WORK)
    queue = deque()
    for i in range(MASK_WORK * MASK_WORK):
        x, y = i % MASK_WORK, i // MASK_WORK
        if lit[i] or not (x in (0, MASK_WORK - 1) or y in (0, MASK_WORK - 1)):
            continue
        outside[i] = 1
        queue.append(i)
    while queue:
        i = queue.popleft()
        x, y = i % MASK_WORK, i // MASK_WORK
        for j in ((i - 1 if x else -1), (i + 1 if x + 1 < MASK_WORK else -1),
                  (i - MASK_WORK if y else -1),
                  (i + MASK_WORK if y + 1 < MASK_WORK else -1)):
            if j >= 0 and not lit[j] and not outside[j]:
                outside[j] = 1
                queue.append(j)

    islands = _components(bytearray(1 - outside[i]
                                    for i in range(MASK_WORK * MASK_WORK)),
                          MASK_WORK, MASK_WORK)
    keep = bytearray(MASK_WORK * MASK_WORK)
    if islands:
        for i in islands[0]:
            keep[i] = 1

    # Everything the flood could not reach from the border is inside the tile.
    sealed = bytearray(1 - keep[i] for i in range(MASK_WORK * MASK_WORK))
    queue = deque()
    for i in range(MASK_WORK * MASK_WORK):
        x, y = i % MASK_WORK, i // MASK_WORK
        if sealed[i] and (x in (0, MASK_WORK - 1) or y in (0, MASK_WORK - 1)):
            sealed[i] = 0
            queue.append(i)
    while queue:
        i = queue.popleft()
        x, y = i % MASK_WORK, i // MASK_WORK
        for j in ((i - 1 if x else -1), (i + 1 if x + 1 < MASK_WORK else -1),
                  (i - MASK_WORK if y else -1),
                  (i + MASK_WORK if y + 1 < MASK_WORK else -1)):
            if j >= 0 and sealed[j]:
                sealed[j] = 0
                queue.append(j)

    filled = bytearray(1 if (keep[i] or not sealed[i]) else 0
                       for i in range(MASK_WORK * MASK_WORK))

    # Erode by one work pixel before the mask is scaled up. The smooth upscale
    # feathers the edge over a few pixels, and at the outer border those pixels
    # are a blend of tile and black - which reads as a dark rim on a light
    # background. Pulling the edge in by a pixel moves the feather onto the
    # tile's own bright edge instead, where it is invisible.
    small_mask = QImage(MASK_WORK, MASK_WORK, QImage.Format_ARGB32)
    small_mask.fill(Qt.transparent)
    for i in range(MASK_WORK * MASK_WORK):
        if not filled[i]:
            continue
        x, y = i % MASK_WORK, i // MASK_WORK
        if (x and filled[i - 1] and x + 1 < MASK_WORK and filled[i + 1]
                and y and filled[i - MASK_WORK]
                and y + 1 < MASK_WORK and filled[i + MASK_WORK]):
            small_mask.setPixel(x, y, QColor(0, 0, 0, 255).rgba())

    mask = small_mask.scaled(src.width(), src.height(), Qt.IgnoreAspectRatio,
                             Qt.SmoothTransformation)

    out = QImage(src.size(), QImage.Format_ARGB32_Premultiplied)
    out.fill(Qt.transparent)
    p = QPainter(out)
    p.drawImage(0, 0, src)
    p.setCompositionMode(QPainter.CompositionMode_DestinationIn)
    p.drawImage(0, 0, mask)
    p.end()
    return out


def refit(tile: QImage) -> QImage:
    """Centre the tile on the canvas and scale it onto Apple's 824 grid.

    The artwork is not cropped to its bounding box first - its framing is
    deliberate and it already sits close to the grid, so the whole frame is
    carried over and only scaled and centred. Measuring the box on a small copy
    keeps this off a megapixel of per-pixel calls; a few pixels of slack in the
    box costs nothing when the target is a soft-edged glass tile.
    """
    probe = MASK_WORK
    small = tile.scaled(probe, probe, Qt.IgnoreAspectRatio,
                        Qt.SmoothTransformation)
    x0, y0, x1, y1 = probe, probe, -1, -1
    for y in range(probe):
        for x in range(probe):
            if ((small.pixel(x, y) >> 24) & 255) > EDGE:
                x0, y0 = min(x0, x), min(y0, y)
                x1, y1 = max(x1, x), max(y1, y)
    if x1 < x0:
        return tile

    back = tile.width() / probe
    box_w, box_h = (x1 - x0 + 1) * back, (y1 - y0 + 1) * back
    cx, cy = (x0 + x1 + 1) / 2 * back, (y0 + y1 + 1) / 2 * back
    scale = SPAN / max(box_w, box_h)

    canvas = QImage(CANVAS, CANVAS, QImage.Format_ARGB32_Premultiplied)
    canvas.fill(Qt.transparent)
    p = QPainter(canvas)
    p.setRenderHint(QPainter.SmoothPixmapTransform, True)
    p.translate(CANVAS / 2, CANVAS / 2)
    p.scale(scale, scale)
    p.translate(-cx, -cy)
    p.drawImage(0, 0, tile)
    p.end()
    return canvas


def squircle(rect: QRectF, n: float = 5.0) -> QPainterPath:
    """Superellipse |x|^n + |y|^n = 1, for the continuous macOS corner."""
    cx, cy = rect.center().x(), rect.center().y()
    a, b = rect.width() / 2, rect.height() / 2
    path = QPainterPath()
    for i in range(721):
        t = 2 * math.pi * i / 720
        ct, st = math.cos(t), math.sin(t)
        x = cx + a * math.copysign(abs(ct) ** (2 / n), ct)
        y = cy + b * math.copysign(abs(st) ** (2 / n), st)
        path.moveTo(x, y) if i == 0 else path.lineTo(x, y)
    path.closeSubpath()
    return path


def draw_fallback(out_path: Path) -> None:
    img = QImage(CANVAS, CANVAS, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setRenderHint(QPainter.TextAntialiasing, True)

    body = QRectF(INSET, INSET, CANVAS - 2 * INSET, CANVAS - 2 * INSET)
    shape = squircle(body)
    p.save()
    p.setClipPath(shape)
    wash = QLinearGradient(body.topLeft(), body.bottomRight())
    wash.setColorAt(0.0, QColor("#232a72"))
    wash.setColorAt(0.52, QColor("#4b3bb4"))
    wash.setColorAt(1.0, QColor("#7c4de0"))
    p.fillPath(shape, wash)
    glow = QRadialGradient(QPointF(body.center().x() - 40, body.top() + 40),
                           body.width() * 0.95)
    glow.setColorAt(0.0, QColor(255, 255, 255, 130))
    glow.setColorAt(1.0, QColor(255, 255, 255, 0))
    p.fillPath(shape, glow)
    pool = QRadialGradient(QPointF(body.right() - 120, body.bottom() - 70),
                           body.width() * 0.75)
    pool.setColorAt(0.0, QColor(233, 181, 60, 80))
    pool.setColorAt(1.0, QColor(233, 181, 60, 0))
    p.fillPath(shape, pool)
    p.restore()

    page = QRectF(0, 0, 452, 566)
    page.moveCenter(QPointF(body.center().x(), body.center().y() + 18))
    page_path = QPainterPath()
    page_path.addRoundedRect(page, 40, 40)
    p.fillPath(page_path, QColor(255, 255, 255, 236))

    left, right = page.left() + 56, page.right() - 56
    inner = right - left
    p.setFont(QFont("Vazirmatn", 74, QFont.Bold))
    p.setPen(QColor("#2b2f7d"))
    p.drawText(QRectF(left, page.top() + 62, inner, 96),
               int(Qt.AlignRight | Qt.AlignVCenter), "کتاب")
    p.fillRect(QRectF(right - 168, page.top() + 178, 168, 9),
               QColor("#e9b53c"))

    y = page.top() + 228
    for width in (0.97, 0.80, 0.90, 0.68, 0.86, 0.52):
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(43, 47, 125, 132))
        p.drawRoundedRect(QRectF(right - inner * width, y, inner * width, 20),
                          10, 10)
        y += 48

    p.save()
    p.setClipPath(shape)
    rim = QLinearGradient(body.topLeft(), body.bottomLeft())
    rim.setColorAt(0.0, QColor(255, 255, 255, 215))
    rim.setColorAt(0.34, QColor(255, 255, 255, 70))
    rim.setColorAt(1.0, QColor(0, 0, 0, 80))
    pen = p.pen()
    pen.setWidthF(7.0)
    pen.setBrush(rim)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    p.drawPath(shape)
    p.restore()
    p.end()
    img.save(str(out_path), "PNG")


def build_icns(master: QImage, iconset: Path) -> None:
    master_path = OUT / "icon-1024.png"
    master.save(str(master_path), "PNG")
    iconset.mkdir(exist_ok=True)
    for size in (16, 32, 128, 256, 512):
        for scale in (1, 2):
            px = size * scale
            name = f"icon_{size}x{size}{'@2x' if scale == 2 else ''}.png"
            subprocess.run(["sips", "-z", str(px), str(px), str(master_path),
                            "--out", str(iconset / name)],
                           check=True, capture_output=True)
    subprocess.run(["iconutil", "-c", "icns", str(iconset),
                    "-o", str(OUT / "icon.icns")], check=True)
    print(f"wrote {master_path} and {OUT / 'icon.icns'}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="src", type=Path, default=SOURCE)
    ap.add_argument("--draw", action="store_true")
    ap.add_argument("--render-only", action="store_true",
                    help="write the 1024 master without building the .icns")
    args = ap.parse_args()

    app = QGuiApplication([])                                    # noqa: F841
    for face in sorted(BUNDLED.glob("*.ttf")):
        QFontDatabase.addApplicationFont(str(face))

    master_path = OUT / "icon-1024.png"
    iconset = OUT / "icon.iconset"

    if args.draw or not args.src.exists():
        if not args.draw:
            print(f"no artwork at {args.src}; drawing a fallback")
        draw_fallback(master_path)
        master = QImage(str(master_path))
    else:
        master = refit(cut_out(QImage(str(args.src))
                               .convertToFormat(QImage.Format_ARGB32)))

    if args.render_only:
        master.save(str(master_path), "PNG")
        print(f"wrote {master_path}")
        return 0

    build_icns(master, iconset)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
