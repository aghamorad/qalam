#!/usr/bin/env python3
"""Regression tests for block detection and note dropping."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from persian_ebook.extract import Document, Line, Page, Span
from persian_ebook.structure import build


def line(text: str, size: float, y: float, page: int = 0) -> Line:
    box = (60.0, y, 530.0, y + size + 3)
    return Line(
        spans=[Span(text=text, size=size, font="Vazirmatn", flags=0, bbox=box)],
        page=page,
        block=int(y),
        bbox=box,
        page_width=595.0,
        page_height=842.0,
    )


body = line(
    "این متن بدنه است و عمداً طولانی است تا اندازهٔ دوازده اندازهٔ غالب سند باشد. " * 3,
    12.0,
    120.0,
)
note = line("۱. این پانوشت باید قابل حذف باشد.", 8.0, 700.0)
page = Page(number=0, width=595.0, height=842.0, lines=[body, note])
doc = Document(path=Path("fixture.pdf"), pages=[page], total_pages=1)

kept = build(doc, keep_notes=True)
assert any(b.kind == "note" and "پانوشت" in b.text for b in kept.blocks), kept.blocks
print("  pass  detected footnote is preserved when requested")

dropped = build(doc, keep_notes=False)
assert all("پانوشت" not in b.text for b in dropped.blocks), dropped.blocks
assert dropped.stats.get("dropped_notes") == 1, dropped.stats
print("  pass  disabling footnotes removes them instead of reclassifying them")

print()
print("all passed")
