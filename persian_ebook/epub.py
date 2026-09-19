"""Package the rendered chapters into an EPUB 3.

Written against the zip format directly rather than through ebooklib, for one
reason: the RTL declaration that matters most lives in the OPF spine, and the
spine is exactly what a library's abstraction makes awkward to reach. Getting
`page-progression-direction="rtl"` onto the spine is what makes a reader open
the book on the right-hand page and turn leftward; without it the book reads
correctly but the pages turn the Western way, which is the single most common
failure of Persian EPUBs.

The archive layout is the one the spec prescribes:

    mimetype            first entry, stored uncompressed, no extra field
    META-INF/container.xml
    OEBPS/content.opf   manifest, spine (direction here), metadata
    OEBPS/nav.xhtml     EPUB 3 navigation
    OEBPS/toc.ncx       the EPUB 2 contents, kept for older Kindle converters
    OEBPS/style/book.css
    OEBPS/fonts/*       the embedded Persian face
    OEBPS/text/*.xhtml  one document per chapter
"""

import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from . import render
from .fonts import FontChoice
from .render import RenderOptions
from .structure import Structure

FONT_FACE_KEYS = ("regular", "bold", "italic", "bold_italic")

CONTAINER = """<?xml version="1.0" encoding="utf-8"?>
<container version="1.0"
           xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf"
              media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""


def _font_files(choice: FontChoice | None) -> dict:
    if choice is None:
        return {}
    out = {}
    for key in FONT_FACE_KEYS:
        p = getattr(choice, key, None)
        if p:
            out[key] = Path(p)
    return out


def _chapter_href(chapter_no: int, anchor: str) -> str:
    href = f"text/ch{chapter_no:03d}.xhtml"
    return f"{href}#{anchor}" if anchor else href


def _nav(chapters, outline, opts) -> str:
    toc = render.toc_html(render.outline_tree(outline), _chapter_href, indent=4)
    if not toc:
        items = "\n".join(
            f'      <li><a href="text/ch{i:03d}.xhtml">بخش {i}</a></li>'
            for i in range(1, len(chapters) + 1))
        toc = f"    <ol>\n{items}\n    </ol>"
    return f"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"
      xml:lang="{opts.language}" lang="{opts.language}" dir="rtl">
  <head>
    <meta charset="utf-8"/>
    <title>فهرست</title>
    <link rel="stylesheet" type="text/css" href="style/book.css"/>
  </head>
  <body dir="rtl">
    <nav epub:type="toc" id="toc">
      <h1>فهرست</h1>
{toc}
    </nav>
  </body>
</html>
"""


def _ncx(chapters, outline, opts, book_id: str) -> str:
    order = [0]

    def points(nodes, indent: str = "    ") -> str:
        out = []
        for (level, title, cno, anchor), children in nodes:
            order[0] += 1
            i = order[0]
            body = ""
            if children:
                body = "\n" + points(children, indent + "  ") + f"\n{indent}"
            out.append(
                f'{indent}<navPoint id="nav{i}" playOrder="{i}">\n'
                f"{indent}  <navLabel><text>{render.esc(title)}</text></navLabel>\n"
                f'{indent}  <content src="{_chapter_href(cno, anchor)}"/>{body}\n'
                f"{indent}</navPoint>")
        return "\n".join(out)

    tree = render.outline_tree(outline)
    body = points(tree) if tree else "\n".join(
        f'    <navPoint id="nav{i}" playOrder="{i}">\n'
        f"      <navLabel><text>بخش {i}</text></navLabel>\n"
        f'      <content src="text/ch{i:03d}.xhtml"/>\n'
        f"    </navPoint>" for i in range(1, len(chapters) + 1))
    depth = max((e[0] for e, _ in _flatten(tree)), default=1)
    return f"""<?xml version="1.0" encoding="utf-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1"
     xml:lang="{opts.language}">
  <head>
    <meta name="dtb:uid" content="{book_id}"/>
    <meta name="dtb:depth" content="{depth}"/>
  </head>
  <docTitle><text>{render.esc(opts.title or "کتاب")}</text></docTitle>
  <navMap>
{body}
  </navMap>
</ncx>
"""


def _flatten(nodes):
    for node in nodes:
        yield node
        yield from _flatten(node[1])


def _opf(chapters, opts, book_id: str, modified: str, font_names: list[str],
         has_titlepage: bool) -> str:
    manifest = [
        '    <item id="nav" href="nav.xhtml" '
        'media-type="application/xhtml+xml" properties="nav"/>',
        '    <item id="ncx" href="toc.ncx" '
        'media-type="application/x-dtbncx+xml"/>',
        '    <item id="css" href="style/book.css" media-type="text/css"/>',
    ]
    spine = []
    if has_titlepage:
        manifest.append('    <item id="titlepage" href="text/titlepage.xhtml" '
                        'media-type="application/xhtml+xml"/>')
        spine.append('    <itemref idref="titlepage"/>')
    for i, ch in enumerate(chapters, start=1):
        manifest.append(f'    <item id="ch{i:03d}" href="text/ch{i:03d}.xhtml" '
                        f'media-type="application/xhtml+xml"/>')
        spine.append(f'    <itemref idref="ch{i:03d}"/>')
    for key, name in font_names:
        manifest.append(f'    <item id="font-{key}" href="fonts/{name}" '
                        f'media-type="font/{Path(name).suffix.lstrip(".").lower()}"/>')

    return f"""<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0"
         unique-identifier="bookid" xml:lang="{opts.language}"
         prefix="rendition: http://www.idpf.org/vocab/rendition/#">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="bookid">urn:uuid:{book_id}</dc:identifier>
    <dc:title>{render.esc(opts.title or "کتاب")}</dc:title>
    <dc:language>{opts.language}</dc:language>
    {f'<dc:creator>{render.esc(opts.author)}</dc:creator>' if opts.author else ''}
    <meta property="dcterms:modified">{modified}</meta>
    <meta name="cover" content="titlepage"/>
  </metadata>
  <manifest>
{chr(10).join(manifest)}
  </manifest>
  <spine toc="ncx" page-progression-direction="rtl">
{chr(10).join(spine)}
  </spine>
  <guide>
    <reference type="toc" title="فهرست" href="nav.xhtml"/>
  </guide>
</package>
"""


def build(structure: Structure, out_path: str | Path, opts: RenderOptions,
          font: FontChoice | None = None) -> Path:
    """Write the book. Returns the path written."""
    out_path = Path(out_path)
    face_files = _font_files(font)
    fonts = [(k, p.name) for k, p in face_files.items()]

    chapters = render.split_chapters(structure.blocks, opts.chapter_break_at)
    outline = render.assign_anchors(chapters)

    def epub_href(p: Path) -> str:
        return f"../fonts/{p.name}"

    faces_css = render.font_faces_css(face_files, opts.font_family, epub_href)
    style = render.css(opts, faces_css)

    book_id = str(uuid.uuid4())
    modified = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    has_titlepage = bool(opts.title or opts.author)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_path, "w") as z:
        # The spec requires the mimetype first and stored, so readers can sniff
        # the file type without inflating the archive.
        zi = zipfile.ZipInfo("mimetype", date_time=(1980, 1, 1, 0, 0, 0))
        zi.compress_type = zipfile.ZIP_STORED
        zi.external_attr = 0o644 << 16
        z.writestr(zi, "application/epub+zip")

        def add(name: str, data: str | bytes):
            zi = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = 0o644 << 16
            z.writestr(zi, data)

        add("META-INF/container.xml", CONTAINER)
        add("OEBPS/style/book.css", style)
        add("OEBPS/nav.xhtml", _nav(chapters, outline, opts))
        add("OEBPS/toc.ncx", _ncx(chapters, outline, opts, book_id))

        if has_titlepage:
            tp = f"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"
      xml:lang="{opts.language}" lang="{opts.language}" dir="rtl">
  <head>
    <meta charset="utf-8"/>
    <title>{render.esc(opts.title or "کتاب")}</title>
    <link rel="stylesheet" type="text/css" href="../style/book.css"/>
  </head>
  <body dir="rtl">
{render.titlepage_html(opts)}
  </body>
</html>
"""
            add("OEBPS/text/titlepage.xhtml", tp)

        for i, ch in enumerate(chapters, start=1):
            add(f"OEBPS/text/ch{i:03d}.xhtml",
                render.chapter_xhtml(ch, opts, standalone=True))

        for key, p in face_files.items():
            add(f"OEBPS/fonts/{p.name}", p.read_bytes())

        add("OEBPS/content.opf",
            _opf(chapters, opts, book_id, modified, fonts, has_titlepage))

    return out_path
