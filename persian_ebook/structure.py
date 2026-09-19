"""Lines -> blocks: headings, paragraphs, poetry, footnotes.

This is where extraction stops reporting and starts interpreting. The signals
are deliberately few and boring, because every RTL PDF is laid out a little
differently and a clever rule that fires on one book will wreck another:

  size tiers    the load-bearing signal. A page's sizes cluster hard, and every
                cluster above the body size is a heading level. Weight is NOT
                reliable here - these legacy Persian fonts set the bold flag on
                ordinary body text (verified on the Mostazmi article, where the
                whole body carries it), so bold only breaks ties.
  centering     a heading is centered; a paragraph is not. Measured against the
                media box, with a loose tolerance because RTL justification is
                ragged on the right by design.
  geometry      vertical gaps and right-edge indentation separate paragraphs.
                In RTL the paragraph's start edge is its RIGHT edge.
  repetition    a line that recurs at the same height across many pages is a
                running head or a folio, and belongs in the bin, not the EPUB.

Nothing here reads the whole book at once, and the output is a block list that
render.py can walk without knowing anything about PDFs.
"""

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from .extract import Document, Line, Span

# A line is a heading candidate if it carries a size at least this much larger
# than the body text.
HEADING_RATIO = 1.12

# Centered lines up to this many characters can be headings even at body size.
CENTERED_HEADING_CHARS = 60

# A line this far below the body size, in the lower part of the page, is a note.
NOTE_SIZE_RATIO = 0.94
NOTE_Y_FRACTION = 0.55

# Repeated at this many pages, a line is a running head or a folio.
RUNNING_HEAD_MIN_PAGES = 3

# Explicit heading markers, for the many books whose headings are body-sized.
HEADING_PATTERNS = [
    re.compile(r"^(فصل|بخش|گفتار|دفتر|پیشگفتار|پیش‌گفتار|مقدمه|دیباچه|ضمیمه|"
               r"کتابنامه|منابع|نمایه|پیوست|نتیجه)\b"),
    re.compile(r"^[۰-۹0-9]+[.‌\-–]\s*[^۰-۹0-9]"),
    re.compile(r"^[۰-۹0-9]+(\.[۰-۹0-9]+)+\s"),
    re.compile(r"^[۰-۹0-9]+\)\s"),
    re.compile(r"^(?:[IVXLC]+)\.\s"),
]

# A line that is nothing but a folio.
FOLIO = re.compile(r"^[۰-۹0-9]{1,4}$")

# RTL sentences end with one of these, which is a soft paragraph break.
SENTENCE_END = ".:!?؟!…»"


@dataclass
class Block:
    kind: str                     # h1 h2 h3 p poem note caption rule
    spans: list[Span]
    page: int
    level: int = 0
    # Filled in by the renderer, which owns the ids the table of contents
    # points at; structure detection has no opinion about them.
    anchor: str = ""
    meta: dict = field(default_factory=dict)

    @property
    def text(self) -> str:
        return " ".join("".join(s.text for s in self.spans).split())

    @property
    def char_count(self) -> int:
        return sum(len(s.text) for s in self.spans)

    def runs(self) -> list[tuple[str, bool, bool, bool]]:
        """Adjacent spans collapsed into (text, bold, italic, superscript)."""
        out: list[list] = []
        for s in self.spans:
            key = (bool(s.bold), bool(s.italic), False)
            if out and out[-1][0] == key:
                out[-1][1] += s.text
            else:
                out.append([key, s.text])
        return [(t, k[0], k[1], k[2]) for k, t in out]


@dataclass
class Structure:
    blocks: list[Block]
    body_size: float
    stats: dict = field(default_factory=dict)

    def outline(self) -> list[tuple[int, str, str]]:
        """(level, kind, text) for every heading - the cheap way to eyeball a
        book's structure without reading it."""
        return [(b.level, b.kind, b.text) for b in self.blocks
                if b.kind.startswith("h") or b.kind == "caption"]

    def counts(self) -> Counter:
        return Counter(b.kind for b in self.blocks)


def _is_persian_digits(s: str) -> bool:
    return bool(s) and all("۰" <= c <= "۹" or "0" <= c <= "9" or c in ". "
                           for c in s)


def _heading_level(size: float, tiers: list[float]) -> int:
    """Map a size onto a heading level by rank among the heading tiers."""
    for i, t in enumerate(tiers):
        if abs(size - t) < 0.05:
            return min(i + 1, 3)
    return 3


def _size_tiers(doc: Document) -> list[float]:
    """Distinct sizes above the body size, largest first, capped at three."""
    body = doc.body_size()
    hist = doc.size_histogram()
    # Only sizes carrying real text count - a stray oversized glyph is not a tier.
    big = sorted((s for s, n in hist.items()
                  if s >= body * HEADING_RATIO and n >= 8), reverse=True)
    # Collapse near-identical sizes (45.0 and 45.2 are one tier).
    out: list[float] = []
    for s in big:
        if not out or abs(out[-1] - s) > 0.6:
            out.append(s)
    return out[:3]


def _find_running_lines(doc: Document) -> set[tuple[int, str]]:
    """(page, text) pairs for lines that recur like a header or folio."""
    seen: dict[str, set[int]] = defaultdict(set)
    for line in doc.lines:
        t = line.text.strip()
        # Keep the key short: running heads are titles, not sentences.
        if 0 < len(t) <= 60:
            seen[t].add(line.page)
    drop = set()
    pages = max(1, len(doc.pages))
    threshold = max(2, min(RUNNING_HEAD_MIN_PAGES, pages // 3))
    for line in doc.lines:
        t = line.text.strip()
        if len(seen[t]) >= threshold and len(t) <= 60:
            # A folio repeats by being a number; a running head by being words.
            if FOLIO.match(t) or len(t) > 3:
                drop.add((line.page, t))
    return drop


def _page_note_region(page) -> float:
    """y below which a small-font line is a footnote rather than body text."""
    return page.height * NOTE_Y_FRACTION if page.height else 0.0


def _looks_like_heading(line: Line, body: float, tiers: list[float]) -> bool:
    if line.char_count > 200:
        return False
    if line.size >= body * HEADING_RATIO:
        return True
    t = line.text.strip()
    if not _is_persian_digits(t):
        return any(p.match(t) for p in HEADING_PATTERNS)
    return False


def _media_gap(a: Line, b: Line) -> float:
    """Vertical whitespace between two consecutive lines."""
    return max(0.0, b.bbox[1] - a.bbox[3])


def _median_gap(lines: list[Line]) -> float:
    gaps = [_media_gap(a, b) for a, b in zip(lines, lines[1:])
            if a.block == b.block]
    gaps = [g for g in gaps if g >= 0]
    if not gaps:
        return 0.0
    gaps.sort()
    return gaps[len(gaps) // 2]


def _merge_spans(left: list[Span], right: list[Span]) -> list[Span]:
    """Join two span lists with a space, keeping style boundaries."""
    if not left:
        return list(right)
    if not right:
        return list(left)
    sep = Span(text=" ", size=left[-1].size, font="", flags=0, bbox=left[-1].bbox)
    return left + [sep] + right


def build(doc: Document, keep_notes: bool = True) -> Structure:
    body = doc.body_size()
    tiers = _size_tiers(doc)
    running = _find_running_lines(doc)

    blocks: list[Block] = []
    stats = Counter()
    # Lines accumulate here and the block is built once, in flush(). Adding the
    # first line at open time and then merging it again built every block's
    # opening line twice.
    pending: list[Line] = []
    pending_kind: str | None = None
    pending_page = 0
    pending_level = 0
    pending_meta: dict = {}

    def flush():
        nonlocal pending, pending_kind
        if pending_kind is not None and pending:
            spans: list[Span] = []
            for ln in pending:
                # Keep whitespace-only spans: on a page whose words are placed
                # individually they carry the word separators, and dropping them
                # glues the line into one long word.
                spans = _merge_spans(spans, [s for s in ln.spans if s.text])
            blocks.append(Block(kind=pending_kind, spans=spans,
                                page=pending_page, level=pending_level,
                                meta=dict(pending_meta)))
            stats[pending_kind] += 1
        pending = []
        pending_kind = None

    def open_block(kind: str, line: Line, level: int = 0,
                   meta: dict | None = None):
        nonlocal pending_kind, pending_page, pending_level, pending_meta
        flush()
        pending_kind = kind
        pending_page = line.page
        pending_level = level
        pending_meta = dict(meta or {})

    for page in doc.pages:
        if not page.lines:
            continue
        note_y = _page_note_region(page)
        page_lines = [l for l in page.lines]
        med_gap = _median_gap(page_lines)

        for line in page_lines:
            text = line.text.strip()
            if not text:
                continue
            if (line.page, text) in running:
                stats["dropped_running"] += 1
                continue
            if FOLIO.match(text) and line.bbox[1] > page.height * 0.85:
                stats["dropped_folio"] += 1
                continue

            is_note = (keep_notes and line.size <= body * NOTE_SIZE_RATIO
                       and line.bbox[1] >= note_y)
            if is_note:
                if pending_kind != "note" or pending_meta.get("page") != line.page:
                    open_block("note", line, meta={"page": line.page})
                pending.append(line)
                continue

            if _looks_like_heading(line, body, tiers):
                if line.size >= body * HEADING_RATIO:
                    level = _heading_level(line.size, tiers)
                else:
                    level = 3
                open_block(f"h{level}", line, level=level)
                pending.append(line)
                flush()
                continue

            # Body text: start a paragraph, or continue the open one.
            new_para = False
            if pending_kind != "p":
                new_para = True
            elif pending and _media_gap(pending[-1], line) > max(2.0, med_gap * 1.6):
                new_para = True
            elif pending and pending[-1].text.strip().endswith(SENTENCE_END) \
                    and line.size != pending[-1].size:
                new_para = True

            if new_para:
                open_block("p", line)
            pending.append(line)

    flush()
    return Structure(blocks=blocks, body_size=body,
                     stats={"tiers": tiers,
                            "blocks": len(blocks),
                            **{k: v for k, v in stats.items()}})
