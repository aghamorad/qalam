#!/usr/bin/env python3
"""Semantic EPUB regression test: RTL, formatting, headings, and TOC."""
import sys
import tempfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from persian_ebook.epub import build as build_epub
from persian_ebook.extract import Document, Line, Page, Span
from persian_ebook.render import RenderOptions
from persian_ebook.structure import build as build_structure


def span(text: str, size: float, font: str, y: float) -> Span:
    return Span(
        text=text,
        size=size,
        font=font,
        flags=0,
        bbox=(70.0, y, 525.0, y + size + 3),
    )


def line(spans: list[Span], y: float, block: int) -> Line:
    box = (70.0, y, 525.0, y + max(s.size for s in spans) + 3)
    return Line(
        spans=spans,
        page=0,
        block=block,
        bbox=box,
        page_width=595.0,
        page_height=842.0,
    )


# Body text deliberately dominates the size histogram so heading levels are
# inferred from the larger size tiers rather than from the test construction.
lines = [
    line([span("فصل اول: آغاز", 22.0, "Vazirmatn-Bold", 80)], 80, 1),
    line([
        span("این متن ", 12.0, "Vazirmatn-Regular", 140),
        span("پررنگ", 12.0, "Vazirmatn-Bold", 140),
        span(" و ", 12.0, "Vazirmatn-Regular", 140),
        span("ایتالیک", 12.0, "Vazirmatn-Italic", 140),
        span(" باید با قالب‌بندی خود باقی بماند. " * 5, 12.0, "Vazirmatn-Regular", 140),
    ], 140, 2),
    line([span("بخش نخست", 17.0, "Vazirmatn-Bold", 230)], 230, 3),
    line([
        span("این پاراگراف دوم است و برای تثبیت اندازهٔ متن بدنه به اندازهٔ کافی طولانی است. " * 5,
             12.0, "Vazirmatn-Regular", 285)
    ], 285, 4),
]

page = Page(number=0, width=595.0, height=842.0, lines=lines)
doc = Document(path=Path("semantic-fixture.pdf"), pages=[page], total_pages=1)
structure = build_structure(doc)

headings = [b for b in structure.blocks if b.kind.startswith("h")]
assert [b.kind for b in headings] == ["h1", "h2"], [b.kind for b in headings]
assert headings[0].bold and headings[1].bold
print("  pass  heading hierarchy detected as h1 -> h2")

out = Path(tempfile.mkdtemp(prefix="qalam-semantics-")) / "semantic.epub"
opts = RenderOptions(language="fa")
build_epub(structure, out, opts)

with zipfile.ZipFile(out) as zf:
    opf = zf.read("OEBPS/content.opf").decode("utf-8")
    nav = zf.read("OEBPS/nav.xhtml").decode("utf-8")
    chapters = "\n".join(
        zf.read(name).decode("utf-8")
        for name in zf.namelist()
        if name.startswith("OEBPS/text/ch") and name.endswith(".xhtml")
    )

assert 'page-progression-direction="rtl"' in opf
assert 'dir="rtl"' in chapters
assert "<h1" in chapters and "فصل اول: آغاز" in chapters
assert "<h2" in chapters and "بخش نخست" in chapters
assert "<strong>پررنگ</strong>" in chapters
assert "<em>ایتالیک</em>" in chapters
print("  pass  XHTML is RTL and preserves h1/h2 + strong/em formatting")

# Parse the EPUB 3 navigation document and verify both semantic headings are
# present as linked TOC entries, with h2 nested beneath h1.
ns = {
    "x": "http://www.w3.org/1999/xhtml",
    "epub": "http://www.idpf.org/2007/ops",
}
root = ET.fromstring(nav)
nav_node = next(
    n for n in root.findall(".//x:nav", ns)
    if n.attrib.get("{http://www.idpf.org/2007/ops}type") == "toc"
)
links = nav_node.findall(".//x:a", ns)
labels = ["".join(a.itertext()).strip() for a in links]
hrefs = [a.attrib.get("href", "") for a in links]
assert labels[:2] == ["فصل اول: آغاز", "بخش نخست"], labels
assert all("#h" in href for href in hrefs[:2]), hrefs
top_li = nav_node.find("./x:ol/x:li", ns)
assert top_li is not None
nested = top_li.find("./x:ol/x:li/x:a", ns)
assert nested is not None and "".join(nested.itertext()).strip() == "بخش نخست"
print("  pass  EPUB navigation TOC contains linked, nested h1/h2 entries")

print()
print("all passed")
