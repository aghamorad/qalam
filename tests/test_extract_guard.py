#!/usr/bin/env python3
"""Regression checks for unsafe private-use glyphs in extracted PDF text."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from persian_ebook.extract import Line, Span, _private_use_codepoints


def make_line(text: str) -> Line:
    box = (0.0, 0.0, 100.0, 20.0)
    return Line(
        spans=[Span(text=text, size=12.0, font="Vazirmatn", flags=0, bbox=box)],
        page=0,
        block=0,
        bbox=box,
        page_width=595.0,
        page_height=842.0,
    )


assert _private_use_codepoints([make_line("متن فارسی")]) == []
print("  pass  normal Persian text is not flagged")

bad = _private_use_codepoints([make_line("متن " + chr(0x10FC00))])
assert bad == [0x10FC00], bad
print("  pass  supplementary private-use glyph is detected")

print()
print("all passed")
