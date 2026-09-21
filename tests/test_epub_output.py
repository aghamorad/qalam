#!/usr/bin/env python3
"""Check the EPUB archive produced by the generated CI fixture."""
import sys
import zipfile
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
    assert 'page-progression-direction="rtl"' in opf
    assert '<meta name="cover"' not in opf

    xhtml = "\n".join(
        zf.read(name).decode("utf-8")
        for name in zf.namelist()
        if name.endswith(".xhtml")
    )

assert "آزمون" in xhtml, "Persian fixture text did not survive conversion"
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
print("  pass  Persian text is present in XHTML")
print()
print("all passed")
