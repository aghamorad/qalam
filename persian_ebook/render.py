"""Blocks -> XHTML and CSS for a right-to-left book.

Nothing here knows what a PDF is. It takes the block list structure.py built and
writes the markup an EPUB reader will open, which keeps the two halves of the
problem separable: structure decides *what* a paragraph is, this decides how it
looks.

The RTL requirements are not cosmetic and are easy to get subtly wrong:

  * the reading direction has to be declared on the document AND in the OPF
    spine - the spine is what makes a reader lay pages out right-to-left and
    turn to the next page on a leftward swipe;
  * `dir="rtl"` on the body is what makes the bidi algorithm put a trailing
    full stop on the left, where a Persian reader expects it;
  * text-align: justify is safe in Persian but `text-align: start` is what
    keeps the last line flush right, so the two are used together.

The markup is written as XML, not as loose HTML: XHTML in an EPUB is parsed by
a real XML parser, and an unclosed tag or a bare `&` fails the whole book.
"""

import html
import re
from dataclasses import dataclass, field

from .structure import Block, Structure

LANG_TAG = "fa-IR"


@dataclass
class RenderOptions:
    title: str = ""
    author: str = ""
    language: str = LANG_TAG
    font_family: str = ""          # CSS family name; empty = leave it to the reader
    base_size: float = 1.0         # em
    line_height: float = 1.85
    justify: bool = True
    indent_paragraphs: bool = True
    keep_notes: bool = True
    chapter_break_at: int = 1      # heading level that starts a new file


@dataclass
class Chapter:
    title: str
    blocks: list[Block]
    level: int = 1
    meta: dict = field(default_factory=dict)


def esc(text: str) -> str:
    """XML-escape, keeping the characters that carry meaning in Persian text."""
    return html.escape(text, quote=False)


def runs_html(block: Block) -> str:
    """The block's spans as inline markup, preserving emphasis.

    Bold and italic come from the span's font name, never from the font's own
    style bits - the legacy Persian faces set those wrongly (B Nazanin Bold
    advertises the italic trait), so the name is the only honest signal.
    """
    out = []
    for text, bold, italic, sup in block.runs():
        if not text:
            continue
        piece = esc(text)
        if bold:
            piece = f"<strong>{piece}</strong>"
        if italic:
            piece = f"<em>{piece}</em>"
        if sup:
            piece = f"<sup>{piece}</sup>"
        out.append(piece)
    return "".join(out)


def _clean(text: str) -> str:
    return re.sub(r"[ \t]+", " ", text).strip()


def block_xhtml(block: Block, opts: RenderOptions) -> str:
    inner = runs_html(block)
    kind = block.kind

    if kind == "rule":
        return "      <hr/>"
    if not _clean(block.text):
        return ""

    if kind.startswith("h"):
        level = max(1, min(6, block.level or int(kind[1:] or 3)))
        aid = f' id="{block.anchor}"' if block.anchor else ""
        return f"      <h{level}{aid}>{inner}</h{level}>"
    if kind == "note":
        return f'      <aside class="note">{inner}</aside>'
    if kind == "poem":
        lines = [_clean(s) for s in "".join(s.text for s in block.spans).split("\n")]
        body = "".join(f"\n        <span class=\"verse\">{esc(l)}</span><br/>"
                       for l in lines if l)
        return f'      <div class="poem">{body}\n      </div>'
    if kind == "caption":
        return f'      <p class="caption">{inner}</p>'
    return f"      <p>{inner}</p>"


def split_chapters(blocks: list[Block], level: int = 1) -> list[Chapter]:
    """Cut the block list into chapters at headings of the given level.

    A book whose top level cuts only once - a play whose h1 is the title and
    whose acts are h2 - would otherwise become one enormous file with a
    one-entry table of contents, so the cut descends a level at a time until it
    actually divides the text. A book with no headings at all stays in one piece:
    that still reads, it just costs the reader the contents list.
    """
    levels = sorted({int(b.kind[1]) for b in blocks
                     if b.kind.startswith("h") and b.kind[1:].isdigit()})
    if not levels:
        return [Chapter(title="", blocks=list(blocks), level=0)]

    candidates = [l for l in levels if l >= level] or [levels[-1]]
    chapters = _cut(blocks, candidates[0])
    for cut in candidates[1:]:
        if len(chapters) >= 2:
            break
        chapters = _cut(blocks, cut)
    return chapters


def _cut(blocks: list[Block], cut: int) -> list[Chapter]:
    chapters: list[Chapter] = []
    current = Chapter(title="", blocks=[], level=cut)
    for b in blocks:
        if b.kind == f"h{cut}":
            if current.blocks or current.title:
                chapters.append(current)
            current = Chapter(title=_clean(b.text), blocks=[b], level=cut)
        else:
            current.blocks.append(b)
    if current.blocks or current.title:
        chapters.append(current)
    # Discard the front-matter chapter if it holds nothing but a running head.
    if chapters and not chapters[0].title and len(chapters[0].blocks) <= 1:
        chapters.pop(0)
    return chapters


def assign_anchors(chapters: list[Chapter]) -> list[tuple[int, str, int, str]]:
    """Id every heading and return the book's outline.

    Each entry is (level, title, chapter number from 1, anchor), in reading
    order. The anchors have to be handed out here rather than inside
    block_xhtml because the table of contents is written before any chapter
    document is, and it needs to know where each heading will land.
    """
    outline: list[tuple[int, str, int, str]] = []
    for cno, chapter in enumerate(chapters, start=1):
        for b in chapter.blocks:
            if not (b.kind.startswith("h") and b.kind[1:].isdigit()):
                continue
            title = _clean(b.text)
            if not title:
                b.anchor = ""
                continue
            b.anchor = f"h{len(outline) + 1}"
            outline.append((int(b.kind[1]), title, cno, b.anchor))
    return outline


def outline_tree(entries: list[tuple[int, str, int, str]]):
    """Nest a flat outline by heading level.

    Returns a list of ((level, title, cno, anchor), children) pairs. A heading
    deeper than its predecessor becomes its child; a heading at the same depth
    or shallower closes back up.
    """
    root: list = []
    stack: list = []
    for entry in entries:
        node = (entry, [])
        while stack and stack[-1][0][0] >= entry[0]:
            stack.pop()
        (stack[-1][1] if stack else root).append(node)
        stack.append(node)
    return root


def toc_html(nodes, href_for, indent: int = 0) -> str:
    pad = "  " * indent
    if not nodes:
        return ""
    out = [f"{pad}<ol>"]
    for (level, title, cno, anchor), children in nodes:
        out.append(f'{pad}  <li><a href="{esc(href_for(cno, anchor))}">'
                   f"{esc(title)}</a>")
        if children:
            out.append(toc_html(children, href_for, indent + 2))
        out.append(f"{pad}  </li>")
    out.append(f"{pad}</ol>")
    return "\n".join(out)


def css(opts: RenderOptions, embed_faces: str = "") -> str:
    family = f'"{opts.font_family}", ' if opts.font_family else ""
    align = "justify" if opts.justify else "start"
    indent = ("    text-indent: 1.6em;\n" if opts.indent_paragraphs else "")
    first = ("    text-indent: 0;\n" if opts.indent_paragraphs else "")
    return f"""@charset "utf-8";

{embed_faces}html, body {{
  writing-mode: horizontal-tb;
}}

body {{
  font-family: {family}serif;
  font-size: {opts.base_size:.2f}em;
  line-height: {opts.line_height};
  text-align: {align};
  margin: 0 5%;
  -webkit-hyphens: none;
  hyphens: none;
}}

p {{
  margin: 0;
{indent}    text-align: {align};
}}

p + p, aside + p, div + p {{
  margin-top: 0.35em;
}}

p:first-of-type, h1 + p, h2 + p, h3 + p {{
{first}}}

h1, h2, h3, h4, h5, h6 {{
  text-align: center;
  line-height: 1.5;
  margin: 1.6em 0 0.9em;
  page-break-after: avoid;
  break-after: avoid;
}}

h1 {{ font-size: 1.7em; margin-top: 1.2em; }}
h2 {{ font-size: 1.4em; }}
h3 {{ font-size: 1.18em; }}
h4 {{ font-size: 1.06em; }}

.note {{
  font-size: 0.88em;
  line-height: 1.6;
  margin: 0.9em 1.4em 0.9em 0;
  padding-inline-start: 0.7em;
  border-inline-start: 0.15em solid currentColor;
  opacity: 0.85;
}}

.poem {{
  text-align: center;
  margin: 1.1em 0;
  line-height: 2.05;
}}

.poem .verse {{ display: inline-block; }}

.caption {{
  font-size: 0.9em;
  text-align: center;
  margin: 0.6em 0 1em;
  opacity: 0.8;
}}

hr {{
  border: 0;
  border-top: 0.08em solid currentColor;
  width: 30%;
  margin: 1.6em auto;
  opacity: 0.4;
}}

strong {{ font-weight: bold; }}
em {{ font-style: italic; }}

.titlepage {{
  text-align: center;
  margin-top: 18%;
  page-break-after: always;
}}

.titlepage .book-title {{ font-size: 2em; line-height: 1.5; }}
.titlepage .book-author {{ font-size: 1.15em; margin-top: 2.2em; opacity: 0.85; }}
"""


def titlepage_html(opts: RenderOptions) -> str:
    if not (opts.title or opts.author):
        return ""
    parts = ['    <section class="titlepage" epub:type="titlepage">']
    if opts.title:
        parts.append(f'      <p class="book-title">{esc(opts.title)}</p>')
    if opts.author:
        parts.append(f'      <p class="book-author">{esc(opts.author)}</p>')
    parts.append("    </section>")
    return "\n".join(parts)


def chapter_xhtml(chapter: Chapter, opts: RenderOptions, embed_faces: str = "",
                  standalone: bool = True) -> str:
    """One EPUB content document. `standalone=False` returns the fragment, for
    the browser preview where everything shares one stylesheet."""
    body = "\n".join(x for x in (block_xhtml(b, opts) for b in chapter.blocks) if x)
    head = ""
    if standalone:
        head = f"""  <head>
    <meta charset="utf-8"/>
    <title>{esc(chapter.title or opts.title or "—")}</title>
    <link rel="stylesheet" type="text/css" href="../style/book.css"/>
  </head>
"""
    return f"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"
      xml:lang="{opts.language}" lang="{opts.language}" dir="rtl">
{head}  <body dir="rtl">
    <section epub:type="chapter">
{body}
    </section>
  </body>
</html>
"""


def preview_html(structure: Structure, opts: RenderOptions,
                 font_files: dict | None = None) -> str:
    """A single self-contained HTML file of the whole book, for looking at in a
    browser. This is the only way to see whether the typography is right before
    it is sealed inside an EPUB, so it gets the same CSS the EPUB gets - and the
    font has to be inlined, since a preview has no font directory to point at.
    """
    import base64

    def inline(path):
        mime = {"otf": "font/otf", "ttc": "font/collection"}.get(
            path.suffix.lstrip(".").lower(), "font/ttf")
        data = base64.b64encode(path.read_bytes()).decode("ascii")
        return f"data:{mime};base64,{data}"

    faces = font_faces_css(font_files or {}, opts.font_family or "Persian Book",
                           inline)
    assign_anchors(split_chapters(structure.blocks, opts.chapter_break_at))
    body = [block_xhtml(b, opts) for b in structure.blocks]
    parts = "\n".join(x for x in body if x)
    title_page = titlepage_html(opts)
    if title_page:
        parts = title_page + "\n" + parts
    return f"""<!DOCTYPE html>
<html lang="{opts.language}" dir="rtl">
<head>
<meta charset="utf-8"/>
<title>{esc(opts.title or "preview")}</title>
<style>
{css(opts, faces)}
body {{ max-width: 34em; margin: 0 auto; padding: 2.5em 1em 6em; }}
</style>
</head>
<body dir="rtl">
{parts}
</body>
</html>
"""


def font_faces_css(font_files: dict, family: str, href_for) -> str:
    """@font-face rules for the faces that were found.

    The URL is supplied by the caller because the same CSS has to work in two
    places with different layouts: inside the EPUB, where the fonts sit in a
    sibling directory, and in the browser preview, where they have to be inlined
    as data URIs to be readable at all.
    """
    style_of = {"regular": "normal", "bold": "normal",
                "italic": "italic", "bold_italic": "italic"}
    blocks = []
    for key, path in font_files.items():
        if not path:
            continue
        weight = "bold" if "bold" in key else "normal"
        fmt = {"ttf": "truetype", "otf": "opentype", "ttc": "collection"}.get(
            path.suffix.lstrip(".").lower(), "truetype")
        blocks.append(
            f"@font-face {{\n"
            f"  font-family: \"{family}\";\n"
            f"  font-style: {style_of.get(key, 'normal')};\n"
            f"  font-weight: {weight};\n"
            f"  src: url(\"{href_for(path)}\") format(\"{fmt}\");\n"
            f"}}")
    return "\n".join(blocks) + ("\n\n" if blocks else "")
