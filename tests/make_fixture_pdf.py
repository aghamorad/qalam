#!/usr/bin/env python3
"""Generate a tiny text-based Persian PDF for CI smoke tests."""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QFont, QFontDatabase, QGuiApplication, QPageSize, QPainter, QPdfWriter

ROOT = Path(__file__).resolve().parents[1]
FONT = ROOT / "persian_ebook" / "data" / "fonts" / "Vazirmatn-Regular.ttf"
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "tests" / "qalam-smoke.pdf"
OUT.parent.mkdir(parents=True, exist_ok=True)

app = QGuiApplication.instance() or QGuiApplication([])
font_id = QFontDatabase.addApplicationFont(str(FONT))
families = QFontDatabase.applicationFontFamilies(font_id)
if font_id < 0 or not families:
    raise SystemExit(f"could not load bundled test font: {FONT}")
family = families[0]

writer = QPdfWriter(str(OUT))
writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
writer.setResolution(72)
writer.setTitle("آزمون قلم")
writer.setCreator("Qalam CI fixture")

painter = QPainter(writer)
if not painter.isActive():
    raise SystemExit("could not start PDF painter")

flags = int(Qt.AlignmentFlag.AlignRight | Qt.TextFlag.TextWordWrap)

def draw_page(page_no: int):
    title = QFont(family, 22)
    title.setBold(True)
    body = QFont(family, 13)
    note = QFont(family, 8)

    painter.setFont(title)
    painter.drawText(QRectF(55, 55, 485, 50), flags,
                     f"فصل {page_no}: آزمون قلم")

    painter.setFont(body)
    prose = (
        "یک متن فارسی برای آزمون واقعی است. "
        "قلم باید ترتیب واژه‌ها و اعداد ۱۲۳۴ را حفظ کند. "
        "متن فارسی و فاصله واژه‌ها برای آزمون درست است. "
    ) * 6
    painter.drawText(QRectF(55, 130, 485, 390), flags, prose)

    painter.setFont(note)
    painter.drawText(QRectF(55, 700, 485, 60), flags,
                     f"{page_no}. یک پانوشت کوچک برای آزمون است.")

draw_page(1)
writer.newPage()
draw_page(2)
painter.end()

if not OUT.exists() or OUT.stat().st_size < 1000:
    raise SystemExit("fixture PDF was not written correctly")
print(OUT)
