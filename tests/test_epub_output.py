#!/usr/bin/env python3
"""Check the EPUB archive produced by the generated CI fixture."""
import sys
import re
import zipfile
from xml.etree import ElementTree as ET
from pathlib import Path

if len(sys.argv) < 2:
    raise SystemExit("usage: test_epub_output.py book.epub [--no-notes]")

path = Path(sys.argv[1])
no_notes = "--no-notes" in sys.argv[2:]
assert path.exists(), path

with zipfile.ZipFile(path) as zf:
    infos = zf.infolist()
    assert infos, "empty EPUB"
    assert infos[0].filename == "mimetype", infos[0].filename
    assert infos[0].compress_type == zipfile.ZIP_STORED, "mimetype must be uncompressed"

    opf = zf.read("OEBPS/content.opf").decode("utf-8")
    ncx = zf.read("OEBPS/toc.ncx").decode("utf-8")
    css = zf.read("OEBPS/style/book.css").decode("utf-8")
    assert 'page-progression-direction="rtl"' in opf
    assert '<meta name="cover"' not in opf
    book_id = opf.split('<dc:identifier id="bookid">', 1)[1].split("</dc:identifier>", 1)[0]
    assert f'name="dtb:uid" content="{book_id}"' in ncx
    assert "direction:" not in css

    xhtml = "\n".join(
        zf.read(name).decode("utf-8")
        for name in zf.namelist()
        if name.endswith(".xhtml")
    )

    # Validate visible text while the archive is still open. Legitimate
    # paragraph or inline-element boundaries may occur between words.
    visible_parts = []
    for name in zf.namelist():
        if name.startswith("OEBPS/text/ch") and name.endswith(".xhtml"):
            root = ET.fromstring(zf.read(name))
            visible_parts.append(" ".join(root.itertext()))
    import unicodedata
    visible = unicodedata.normalize(
        "NFC", re.sub(r"\s+", " ", " ".join(visible_parts)).strip()
    )

assert "آزمون" in xhtml, "Persian fixture text did not survive conversion"

# Requiring \s+ between each token still catches glued Persian words while
# allowing legitimate XHTML element boundaries and line wrapping.
sentence = re.compile(
    r"یک\s+متن\s+فارسی\s+برای\s+آزمون\s+واقعی\s+است[.]"
)
assert sentence.search(visible), (
    "Persian word spacing/order from the PDF did not survive conversion: "
    + repr(visible[:500])
)
has_note = "پانوشت کوچک" in xhtml
if no_notes:
    assert not has_note, "footnote text survived --no-notes"
    print("  pass  --no-notes output contains no detected footnote text")
else:
    assert has_note, "kept footnote text is missing"
    print("  pass  kept footnote text is present")

print("  pass  EPUB mimetype ordering/compression is correct")
print("  pass  OPF declares RTL page progression")
print("  pass  invalid legacy cover metadata is absent")
print("  pass  NCX and OPF publication identifiers match")
print("  pass  RTL is expressed without forbidden CSS direction")
print("  pass  Persian text is present in XHTML")
print("  pass  Persian word spacing/order is preserved")
print()
print("all passed")
