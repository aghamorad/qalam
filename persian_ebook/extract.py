"""PDF -> structured lines, keeping the typography that structure detection needs.

Extraction is done by Apple's PDFKit, not PyMuPDF. This is not a preference.
PyMuPDF (and poppler) re-order Arabic-script content themselves and get it
wrong: a lam-alef ligature comes back transposed ('تلاش' -> 'تالش'), digit
runs inside an RTL line come out in visual order, and parentheses end up
mis-paired. The PDFs are fine - the glyphs' ToUnicode maps the ligature to
'لا' correctly - so there is nothing to repair in the file, only an extractor
to route around. PDFKit returns the logical order, correct digits, and correct
paren pairing on the same page.

This module still does NOT interpret. It reports what is on the page: per-span
font size, family, style flags, bounding box. Heading and footnote inference
happens in structure.py, working from this.
"""

import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from Foundation import NSRange, NSURL
from Quartz import PDFDocument

# PDFKit gives a font family plus a face name. The face is the honest signal:
# these legacy Persian fonts carry bogus OS/2 style bits (B Nazanin Bold
# advertises the italic trait), so traits cannot be trusted for weight.
BOLD_PAT = re.compile(r"(bold|black|heavy|semibold|demi)", re.I)
ITALIC_PAT = re.compile(r"(italic|oblique)", re.I)

# kPDFDisplayBoxMediaBox
MEDIA_BOX = 0

# Two line selections belong to the same visual line when their baselines sit
# within this many points of each other.
Y_TOLERANCE = 4.0

# PDFKit cuts a visual line into segments at font boundaries, which on these
# books happens *inside* words as often as between them, and the pieces of a word
# arrive with no separator at all - the word space survives only as a gap in the
# geometry. Measured on the Ibsen body text at size 12, the gap histogram over
# six pages has a clean valley at 1-2pt with 154 breaks at 0pt on the intra-word
# side and a cluster sitting on 3pt on the word-space side, so the threshold has
# to fall inside that valley rather than on top of the 3pt cluster.
SPACE_GAP_RATIO = 0.20
SPACE_GAP_FLOOR = 2.5

# A segment boundary next to one of these is a run split in the middle of a word
# or phrase, never a word gap: punctuation hugs what it follows in RTL just as it
# does in Latin, and a combining mark belongs to the letter before it.
TIGHT = set("«»()[]{}.,،؛؟!:;…") | set("ًٌٍَُِّْٰٕٓٔ")


@dataclass
class Span:
    text: str
    size: float
    font: str
    flags: int
    bbox: tuple[float, float, float, float]

    @property
    def bold(self) -> bool:
        return bool(BOLD_PAT.search(self.font))

    @property
    def italic(self) -> bool:
        return bool(ITALIC_PAT.search(self.font))


@dataclass
class Line:
    spans: list[Span]
    page: int
    block: int
    bbox: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
    page_width: float = 0.0
    page_height: float = 0.0

    @property
    def text(self) -> str:
        return "".join(s.text for s in self.spans)

    @property
    def stripped(self) -> str:
        return self.text.strip()

    @property
    def size(self) -> float:
        """Size of the bulk of the line, by character count - not the max, which
        a single superscript run would skew."""
        counts: Counter[float] = Counter()
        for s in self.spans:
            counts[round(s.size, 1)] += len(s.text)
        return counts.most_common(1)[0][0] if counts else 0.0

    @property
    def dominant(self) -> Span | None:
        return max(self.spans, key=lambda s: len(s.text), default=None)

    @property
    def bold(self) -> bool:
        s = self.dominant
        return bool(s and s.bold)

    @property
    def italic(self) -> bool:
        s = self.dominant
        return bool(s and s.italic)

    @property
    def char_count(self) -> int:
        return sum(len(s.text) for s in self.spans)

    @property
    def x_center(self) -> float:
        return (self.bbox[0] + self.bbox[2]) / 2.0

    @property
    def centered(self) -> bool:
        """Horizontal centering, used as a heading signal. Tolerance is loose
        because RTL justification is ragged on the right by design."""
        if not self.page_width or not self.bbox[2]:
            return False
        return abs(self.x_center - self.page_width / 2.0) < self.page_width * 0.06

    @property
    def font_names(self) -> set[str]:
        return {s.font for s in self.spans}


@dataclass
class Page:
    number: int
    width: float
    height: float
    lines: list[Line]

    @property
    def text_chars(self) -> int:
        return sum(l.char_count for l in self.lines)

    @property
    def looks_scanned(self) -> bool:
        """A page with no usable text layer. PDFKit does not surface images, so
        the text layer itself is the signal - which is the one that matters."""
        return self.text_chars < 40


@dataclass
class Document:
    path: Path
    pages: list[Page]
    total_pages: int
    meta: dict = field(default_factory=dict)

    @property
    def lines(self) -> list[Line]:
        return [l for p in self.pages for l in p.lines]

    @property
    def scanned_pages(self) -> int:
        return sum(1 for p in self.pages if p.looks_scanned)

    def size_histogram(self) -> Counter:
        h: Counter[float] = Counter()
        for l in self.lines:
            h[l.size] += l.char_count
        return h

    def body_size(self) -> float:
        """The size carrying the most characters - the running text."""
        h = self.size_histogram()
        return h.most_common(1)[0][0] if h else 0.0

    def is_born_digital(self) -> bool:
        if not self.pages:
            return False
        return self.scanned_pages / len(self.pages) < 0.5

    def summary(self) -> str:
        """Stats only. Never dumps book text, so it is safe to print anywhere."""
        if not self.pages:
            return f"{self.path.name}: no pages read"
        h = self.size_histogram()
        top = ", ".join(f"{s}->{n}" for s, n in h.most_common(5))
        return (
            f"{self.path.name}: {self.total_pages} pages "
            f"({len(self.pages)} read), "
            f"{'born-digital' if self.is_born_digital() else 'scanned'}, "
            f"body={self.body_size()}, "
            f"{len(self.lines)} lines, sizes[{top}]"
        )


def _page_meta(doc) -> dict:
    try:
        attrs = doc.documentAttributes() or {}
    except Exception:
        return {}
    out = {}
    for src, dst in (("Title", "title"), ("Author", "author"),
                     ("Subject", "subject")):
        v = attrs.get(src)
        if v:
            out[dst] = str(v)
    return out


def _line_bbox(page, loc: int, length: int, page_height: float):
    """Bounding box for a character range, converted to top-left origin so the
    geometry matches how a reader thinks about a page."""
    sel = page.selectionForRange_(NSRange(loc, length))
    if sel is None:
        return (0.0, 0.0, 0.0, 0.0)
    r = sel.boundsForPage_(page)
    if r is None or (r.size.width == 0 and r.size.height == 0):
        return (0.0, 0.0, 0.0, 0.0)
    top = page_height - (r.origin.y + r.size.height)
    bottom = page_height - r.origin.y
    return (float(r.origin.x), float(top),
            float(r.origin.x + r.size.width), float(bottom))


def _char_fonts(attr, n: int) -> list:
    """Per-character (size, face) from the run list. A run can span many lines,
    so the font has to be carried down to the character before lines are cut."""
    fonts: list = [None] * n

    def collect(attrs, r, _stop):
        f = attrs.get("NSFont")
        spec = (float(f.pointSize()) if f else 0.0,
                str(f.fontName()) if f else "")
        for i in range(max(0, int(r.location)),
                       min(int(r.location + r.length), n)):
            fonts[i] = spec

    attr.enumerateAttributesInRange_options_usingBlock_(NSRange(0, n), 0, collect)

    last = (0.0, "")
    for i in range(n):
        if fonts[i] is None:
            fonts[i] = last
        else:
            last = fonts[i]
    return fonts


def _segments(page, n: int) -> list[dict]:
    """One entry per line selection, with ranges contained in a wider selection
    already dropped.

    `selectionsByLine()` is the right line API - `string()`'s newlines separate
    runs, not visual lines. But it reports a decorated line several times over,
    a wide selection plus degenerate sub-ranges of it, so the contained ones are
    discarded here.
    """
    sel = page.selectionForRange_(NSRange(0, n))
    getter = getattr(sel, "selectionsByLine", None) if sel is not None else None
    if getter is None:
        return []

    by_line = getter()
    raw: list[dict] = []
    for i in range(by_line.count()):
        ln = by_line.objectAtIndex_(i)
        text = str(ln.string() or "")
        if not text.strip():
            continue
        r = ln.rangeAtIndex_onPage_(0, page)
        loc, length = int(r.location), int(r.length)
        if loc < 0 or loc >= n or length <= 0:
            continue
        b = ln.boundsForPage_(page)
        if b is None:
            continue
        raw.append({
            "loc": loc,
            "len": min(length, n - loc),
            "text": text,
            "x0": float(b.origin.x),
            "x1": float(b.origin.x + b.size.width),
            "y0": float(b.origin.y),
            "y1": float(b.origin.y + b.size.height),
        })

    keep = []
    for i, x in enumerate(raw):
        contained = any(
            j != i
            and o["loc"] <= x["loc"]
            and x["loc"] + x["len"] <= o["loc"] + o["len"]
            and (o["len"] > x["len"] or j < i)
            for j, o in enumerate(raw)
        )
        if not contained:
            keep.append(x)
    return keep


def _bands(segments: list[dict]) -> list[list[dict]]:
    """Group segments that share a baseline, then restore logical order.

    PDFKit hands the selections back in logical reading order, which grouping by
    baseline destroys - so each band is put back in ascending character order.
    Bands themselves run from the top of the page down.
    """
    ordered = sorted(segments, key=lambda s: -s["y1"])
    bands: list[list[dict]] = []
    cur: list[dict] = []
    for s in ordered:
        if cur and cur[0]["y1"] - s["y1"] > Y_TOLERANCE:
            bands.append(cur)
            cur = []
        cur.append(s)
    if cur:
        bands.append(cur)
    for band in bands:
        band.sort(key=lambda s: s["loc"])
    return bands


def _band_bbox(band: list[dict], page_height: float):
    x0 = min(s["x0"] for s in band)
    x1 = max(s["x1"] for s in band)
    y0 = min(s["y0"] for s in band)
    y1 = max(s["y1"] for s in band)
    return (x0, page_height - y1, x1, page_height - y0)


def _interval_gap(a, b) -> float:
    """Horizontal whitespace between two boxes; zero when they overlap."""
    return max(0.0, max(a[0], b[0]) - min(a[1], b[1]))


def _band_spans(band: list[dict], fonts: list, n: int, bbox) -> list[Span]:
    """Concatenate a band's segments into styled spans.

    PDFKit separates words within a selection with the same "\\n" it uses for
    run boundaries, so a dropped newline between two non-space characters has to
    come back as a space - otherwise 'نمایشنامه ای در پنج پرده' extracts as
    'نمایشنامهایدرپنجپرده'.
    """
    spans: list[Span] = []
    prev_box = None
    for seg in band:
        text = seg["text"]
        pairs: list[tuple[str, object]] = []
        for k, ch in enumerate(text):
            i = seg["loc"] + k
            spec = fonts[i] if 0 <= i < n else None
            if ch == "\n":
                prev = text[k - 1] if k else ""
                nxt = text[k + 1] if k + 1 < len(text) else ""
                if prev and nxt and not prev.isspace() and not nxt.isspace():
                    pairs.append((" ", pairs[-1][1] if pairs else spec))
                continue
            pairs.append((ch, spec))
        if not pairs:
            continue
        prev = spans[-1] if spans else None
        box = (seg["x0"], seg["x1"])
        if (prev is not None and prev_box is not None
                and not prev.text[-1].isspace() and not pairs[0][0].isspace()
                and prev.text[-1] not in TIGHT and pairs[0][0] not in TIGHT
                and _interval_gap(prev_box, box)
                > max(SPACE_GAP_FLOOR, prev.size * SPACE_GAP_RATIO)):
            spans.append(Span(text=" ", size=prev.size, font="", flags=0,
                              bbox=bbox))
        prev_box = box
        i = 0
        while i < len(pairs):
            spec = pairs[i][1] or (0.0, "")
            j = i + 1
            while j < len(pairs) and (pairs[j][1] or (0.0, "")) == spec:
                j += 1
            spans.append(Span(text="".join(c for c, _ in pairs[i:j]),
                              size=spec[0], font=spec[1], flags=0, bbox=bbox))
            i = j
    return spans


def _lines_by_newline(text: str, fonts: list, n: int, page, index: int,
                      width: float, height: float, block_ids: dict) -> list[Line]:
    """Fallback for pages where line selections are unavailable: cut on the
    newlines PDFKit emits between runs. Worse, but better than nothing."""
    lines: list[Line] = []
    offset = 0
    for raw in text.split("\n"):
        start, end = offset, offset + len(raw)
        offset = end + 1
        if not raw.strip():
            continue

        spans: list[Span] = []
        i = start
        while i < end:
            spec = fonts[i] if i < n else (0.0, "")
            j = i + 1
            while j < end and (fonts[j] if j < n else (0.0, "")) == spec:
                j += 1
            spans.append(Span(text=text[i:j], size=spec[0], font=spec[1],
                              flags=0, bbox=(0.0, 0.0, 0.0, 0.0)))
            i = j

        bbox = _line_bbox(page, start, end - start, height)
        for s in spans:
            s.bbox = bbox

        bkey = block_ids.setdefault((index, round(bbox[1], 1)), len(block_ids))
        lines.append(Line(spans=spans, page=index, block=bkey, bbox=bbox,
                          page_width=width, page_height=height))
    return lines


def _extract_page(page, index: int, block_ids: dict) -> Page:
    media = page.boundsForBox_(MEDIA_BOX)
    width = float(media.size.width) if media else 0.0
    height = float(media.size.height) if media else 0.0

    attr = page.attributedString()
    if attr is None:
        return Page(number=index, width=width, height=height, lines=[])
    n = attr.length()
    if n == 0:
        return Page(number=index, width=width, height=height, lines=[])

    fonts = _char_fonts(attr, n)

    lines: list[Line] = []
    for band in _bands(_segments(page, n)):
        bbox = _band_bbox(band, height)
        spans = _band_spans(band, fonts, n, bbox)
        if not "".join(s.text for s in spans).strip():
            continue
        bkey = block_ids.setdefault((index, round(bbox[1], 1)), len(block_ids))
        lines.append(Line(spans=spans, page=index, block=bkey, bbox=bbox,
                          page_width=width, page_height=height))

    if not lines:
        lines = _lines_by_newline(str(attr.string()), fonts, n, page, index,
                                  width, height, block_ids)

    return Page(number=index, width=width, height=height, lines=lines)


def extract_pdf(path: str | Path, max_pages: int | None = None,
                sort: bool = False) -> Document:
    """Read a PDF into positioned lines.

    max_pages bounds the work - useful for probing a large book without paying
    to process all of it. `sort` is accepted for call compatibility; PDFKit
    already returns reading order, so it is ignored.
    """
    del sort
    path = Path(path)
    doc = PDFDocument.alloc().initWithURL_(NSURL.fileURLWithPath_(str(path)))
    if doc is None:
        raise ValueError(f"{path.name}: could not be opened")
    if doc.isLocked():
        raise ValueError(f"{path.name} is password protected")

    total = int(doc.pageCount())
    limit = total if max_pages is None else min(max_pages, total)
    block_ids: dict = {}
    pages: list[Page] = []

    for i in range(limit):
        page = doc.pageAtIndex_(i)
        if page is None:
            continue
        try:
            pages.append(_extract_page(page, i, block_ids))
        except Exception:
            continue

    return Document(path=path, pages=pages, total_pages=total,
                    meta=_page_meta(doc))
