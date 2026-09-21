<p align="center">
  <img src="docs/splash.png" width="420" alt="Qalam">
</p>

# Qalam — قلم

A Persian PDF to EPUB/MOBI converter. Drop in a text-based PDF and get a
right-to-left EPUB, a KF8-based MOBI, or both. EPUB remains the recommended
format for Send to Kindle; MOBI output is for direct sideloading and is produced
locally through calibre.

![The Qalam window](docs/screenshot.png)

## EPUB and MOBI

Qalam's native output is EPUB 3. iPad and Kobo can open it directly, and
Amazon's Send to Kindle service accepts EPUB and converts it server-side.

Optional MOBI output is generated from Qalam's EPUB with calibre's
`ebook-convert`. Qalam requests KF8-only MOBI rather than old MOBI 6 because
KF8 has the CSS/layout features Persian RTL books need. Amazon no longer accepts
MOBI for KDP or Send to Kindle, so use this option for direct sideloading to a
compatible Kindle or another reader, not for Amazon cloud delivery.

## Requirements

**macOS.** This is not a packaging accident. Text extraction runs on Apple's
PDFKit, and that choice is load-bearing (see below). There is no Linux or
Windows build and no plan for one.

- macOS 12 or later
- Python 3.11 or later
- calibre (optional; required only for MOBI output)

## Install

```bash
git clone https://github.com/aghamorad/qalam.git
cd qalam
python3 -m venv .venv
.venv/bin/pip install -e .
```

Run the app:

```bash
.venv/bin/qalam-gui
```

Or from the command line:

```bash
.venv/bin/qalam book.pdf -o book.epub
.venv/bin/qalam book.pdf --format mobi -o book.mobi
.venv/bin/qalam book.pdf --format both
```

## Using it

The window has one job. Add PDFs, set a title and author if the file doesn't
carry them, choose a body font (or leave it on Automatic), and press Convert.
The interface switches between English and Persian with the radio buttons in the
header and remembers which one you picked.

Everyday options:

| | |
|---|---|
| **Output format** | EPUB, MOBI (KF8), or both. MOBI requires calibre. |
| **Pages** | Convert the whole book, or the first N pages while you check the settings. |
| **Body font** | Any Persian family installed on this machine, plus the bundled Vazirmatn. |
| **Keep footnotes** | Preserve detected bottom-of-page notes as note blocks; turn this off to remove them. |
| **Paragraph spacing** | Preserve obvious paragraph gaps and RTL first-line indentation from the source PDF instead of flattening every paragraph to one generic rhythm. |
| **Also write an HTML preview** | A single file you can open in a browser and read before committing to the EPUB. |

The command line takes the same options:

```bash
.venv/bin/qalam --help
.venv/bin/qalam --list-fonts          # every Persian family found, ranked
.venv/bin/qalam book.pdf --pages 20 --preview
```

## How it works

The native PDF-to-EPUB conversion is four steps, and each one exists because of
a specific thing that goes wrong otherwise. If MOBI is requested, a fifth
post-processing step asks calibre to convert the finished EPUB to KF8-based
MOBI.

**1. Extract.** PDFKit reads the page and reports what is actually printed:
each span of text with its font size, family, style flags, and bounding box.
This is the step that makes the app macOS-only. PyMuPDF and poppler both
re-order Arabic-script text on their own and get it wrong: a lam-alef ligature
comes back transposed, so `تلاش` arrives as `تالش`; digit runs inside a
right-to-left line come out in visual order; parentheses end up mis-paired. The
PDF is fine (its `ToUnicode` map has the ligature down correctly), so there is
nothing to repair in the file, only a broken extractor to route around. PDFKit
returns logical order, correct digits, and correct parentheses on the same page.

**2. Normalize.** Extraction produces text that is nominally Persian and wrong
in specific, recurring ways: Arabic presentation forms instead of base letters,
Arabic yeh and kaf where Persian wants U+06CC and U+06A9, stray bidi control
characters, non-breaking spaces wedged into the middle of words. These are fixed
in a fixed order, because the order matters. Presentation forms have to be
decomposed before codepoints are mapped, and bidi controls have to be gone
before anything reasons about where a word ends.

**3. Structure.** Lines become blocks: headings, paragraphs, poetry, footnotes.
For body text, Qalam also uses page geometry to distinguish ordinary line leading
from a real paragraph gap and to detect RTL first-line indentation from the
right edge of the text column. Those cues are carried into the reflowable ebook.
The signals are deliberately few, because every Persian PDF is laid out a little
differently and a clever rule that reads one book correctly will wreck another.
Font size is the load-bearing signal: a page's sizes cluster hard, and each
cluster above body size is a heading level. Weight is not reliable (some legacy
Persian fonts set the bold flag on ordinary body text). Conventional section
labels and numbering catch some body-sized headings; vertical gaps separate
paragraphs. Qalam deliberately avoids claiming structure from geometry it cannot
infer consistently.

**4. Render and package.** Blocks become XHTML and CSS, and the result is zipped
into an EPUB 3 by hand rather than through a library. That is deliberate:
`page-progression-direction="rtl"` has to land on the OPF spine, because the
spine is what makes a reader open the book on the right-hand page and turn
leftward. Without it the book still reads correctly and still turns pages the
Western way, which is the most common failure in Persian EPUBs and is invisible
until someone tries to read one. The archive is written to spec: `mimetype`
first, stored uncompressed, no extra field.

A Persian font is embedded in the file. E-readers do not ship a Persian face
worth relying on, and the fonts these PDFs were typeset in are commercial
Iranian designs that your reader certainly does not have.

## Fonts and licensing

Qalam bundles **Vazirmatn** by Saber Rastikerdar, under the SIL Open Font
License 1.1, so that a converted book carries a Persian face even on a machine
with none installed.

It also finds every Persian-capable family already on your Mac (measured from
each font's own character map, not a hardcoded list) and offers them in the font
menu. Qalam only marks a font as redistributable when the actual font file
contains recognized open-license metadata, or when it is the bundled Vazirmatn.
Anything else is labelled `[license unknown]`; check that font's license before
sharing an EPUB or MOBI that embeds it.

## Development

```bash
.venv/bin/python tests/test_normalize.py
QT_QPA_PLATFORM=offscreen .venv/bin/python tests/test_gui_smoke.py sample.pdf
.venv/bin/python tests/test_structure.py
.venv/bin/python tests/test_fonts.py
```

Both are plain scripts that print a line per check and exit non-zero on failure;
neither needs a test runner.

`test_gui_smoke.py` drives the real window through a real conversion on the
offscreen Qt platform, which catches the failures a pipeline test cannot see: a
signal wired to the wrong slot, a worker thread that never reports progress. It
caps itself at six pages. CI generates a small Persian PDF fixture and runs that
conversion automatically; for local testing you can also point it at a real
book.

The icon is generated, not drawn by hand:

```bash
.venv/bin/python tools/make_icon.py            # from data/icon-source.png
.venv/bin/python tools/make_icon.py --draw     # a geometric fallback, no artwork needed
```

It converts the artwork's flat backdrop to real transparency with a border flood
fill, keeps only the largest connected component so floating specks disappear,
seals pockets enclosed by the tile so the dark crevices inside the book stay
opaque, erodes the mask by one pixel to stop a dark rim appearing on a light
background, and refits the tile to Apple's 824-of-1024 icon grid. Then `sips`
and `iconutil` build the `.icns`.

`tools/` also holds the probe scripts used to work out the extraction and
structuring behaviour against real books. They are kept because they document
what was measured, not because they are part of the app.

## Credits

Written by **Morad**.

## License

MIT, for the code. Vazirmatn is under the SIL Open Font License 1.1 and that
license governs `persian_ebook/data/fonts/`. See [LICENSE](LICENSE).
