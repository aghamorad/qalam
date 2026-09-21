#!/usr/bin/env python3
"""Regression test for RTL paragraph spacing and first-line indentation."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from persian_ebook.extract import Document, Line, Page, Span
from persian_ebook.render import RenderOptions, block_xhtml
from persian_ebook.structure import build


BODY = 12.0


def make_line(text: str, y: float, right: float, block: int) -> Line:
    box = (70.0, y, right, y + 15.0)
    return Line(
        spans=[Span(text=text, size=BODY, font="Vazirmatn-Regular",
                    flags=0, bbox=box)],
        page=0,
        block=block,
        bbox=box,
        page_width=595.0,
        page_height=842.0,
    )


# Normal body right edge is 530. Paragraph starts are visibly shifted left to
# 500, i.e. a 30pt / 2.5em RTL first-line indent. Ordinary leading is 3pt;
# between paragraphs there is a 12pt gap.
lines = [
    make_line("این آغاز پاراگراف نخست است و از سمت راست تورفتگی دارد", 100, 500, 1),
    make_line("این خط ادامهٔ همان پاراگراف است و تا حاشیهٔ راست می‌رود", 118, 530, 2),
    make_line("این آغاز پاراگراف دوم است و فاصلهٔ بیشتری پیش از خود دارد", 145, 500, 3),
    make_line("این نیز ادامهٔ پاراگراف دوم است", 163, 530, 4),
]

page = Page(number=0, width=595.0, height=842.0, lines=lines)
doc = Document(path=Path("spacing.pdf"), pages=[page], total_pages=1)
structure = build(doc)

paras = [b for b in structure.blocks if b.kind == "p"]
assert len(paras) == 2, [(b.kind, b.text, b.meta) for b in structure.blocks]

first, second = paras
assert first.meta["first_line_indent_em"] == 2.5, first.meta
assert first.meta["space_before_em"] == 0.0, first.meta
assert second.meta["first_line_indent_em"] == 2.5, second.meta
assert 0.7 <= second.meta["space_before_em"] <= 0.8, second.meta
print("  pass  RTL first-line indents become paragraph boundaries")
print("  pass  larger PDF paragraph gap is preserved separately from normal leading")

opts = RenderOptions(language="fa")
first_html = block_xhtml(first, opts)
second_html = block_xhtml(second, opts)
assert 'text-indent: 2.50em' in first_html, first_html
assert 'margin-top: 0.00em' in first_html, first_html
assert 'text-indent: 2.50em' in second_html, second_html
assert 'margin-top: 0.75em' in second_html, second_html
print("  pass  detected indentation and spacing are emitted into XHTML")

print()
print("all passed")
