"""Persian text normalization.

PDF extraction produces text that is nominally Persian but wrong in specific,
recurring ways. This module fixes them in a fixed order, because the order matters:
presentation forms must be decomposed before codepoint mapping, and bidi controls
must be gone before anything tries to reason about word boundaries.

Every rule is in one of three tiers:
  always   - cannot make good text worse (decomposition, bidi strip, whitespace)
  default  - high confidence, tiny exception list (mi/nemi prefix ZWNJ)
  opt-in   - can be wrong on edge cases, belongs behind a review step (typography,
             aggressive ZWNJ insertion)
"""

import re
import unicodedata
from dataclasses import dataclass, field

# --- Character sets -------------------------------------------------------

PRESENTATION_FORM_RANGES = ((0xFB50, 0xFDFF), (0xFE70, 0xFEFF))

# Bidi/joiner controls that leak out of PDF text layers and wreck EPUB rendering.
# ZWNJ (U+200C) is deliberately NOT here - it is load-bearing Persian.
BIDI_CONTROLS = {
    0x200E, 0x200F,             # LRM, RLM
    0x202A, 0x202B, 0x202C,     # LRE, RLE, PDF
    0x202D, 0x202E,             # LRO, RLO
    0x2066, 0x2067, 0x2068, 0x2069,  # LRI, RLI, FSI, PDI
    0xFEFF,                     # BOM
}

ZWNJ = "‌"
ZWJ = "‍"
TATWEEL = "ـ"

# Arabic codepoints that Persian writes differently. PDFs of Persian text are
# frequently typed with Arabic keyboard layouts, so these arrive constantly.
ARABIC_TO_PERSIAN = {
    0x064A: 0x06CC,  # ARABIC YEH        -> FARSI YEH
    0x0649: 0x06CC,  # ALEF MAKSURA      -> FARSI YEH
    0x0643: 0x06A9,  # ARABIC KAF        -> KEHEH
    0x0629: 0x0647,  # TEH MARBUTA       -> HEH
    0x06C0: 0x0647,  # HEH WITH YEH ABOVE-> HEH
    0x06D2: 0x06CC,  # YEH BARREE        -> FARSI YEH
}

ARABIC_INDIC_DIGITS = {0x0660 + i: 0x06F0 + i for i in range(10)}
ASCII_DIGITS = {0x30 + i: 0x06F0 + i for i in range(10)}

# ASCII punctuation -> Persian typography. Only safe on Persian-dominant text.
TYPOGRAPHY = {
    0x2C: 0x060C,   # , -> ،
    0x3B: 0x061B,   # ; -> ؛
    0x3F: 0x061F,   # ? -> ؟
}

# Words that merely *look* like they take a mi/nemi prefix. Without this list the
# rule turns میان into می‌ان and میز into می‌ز.
MI_EXCEPTIONS = {
    "میان", "میز", "میزان", "میلی", "میلیون", "میلیارد", "مینا", "میرا", "میراث",
    "میوه", "میکا", "میکرب", "میکروسکوپ", "میگو", "میدان", "میل", "میله", "میم",
    "مینی", "میهن", "میخ", "میر", "میزبان", "میکرو", "میانگین", "میانسال",
    "نمیان", "میزنم",
}

# Suffixes where an inserted ZWNJ is usually right but occasionally splits a stem.
PLURAL_SUFFIXES = ("ها", "های", "هایی", "هایم", "هایت", "هایش", "هات")

# A bracket token that opens with a closing bracket and ends with its matching
# opening one. PDFKit hands these back for bracketed numbers inside RTL text when
# the run uses a Latin font: the PDF stores display-mirrored paren codepoints and
# the extractor passes them through. ')1882(' is malformed in every language, so
# repairing it needs no RTL guard - verified across the corpus for false hits.
CLOSE_TO_OPEN = {")": "(", "]": "[", "}": "{"}
OPEN_TO_CLOSE = {v: k for k, v in CLOSE_TO_OPEN.items()}
_TOKEN = re.compile(r"\S+")

# Arabic combining marks. On decorated pages PDFKit emits them as standalone
# positioned glyphs, so they arrive doubled ('دشمن ِِ'), detached from their
# letter by a space, or trailing a Latin word. None of those shapes is
# well-formed in any language, so the repairs below cannot make good text worse.
HARAKAT = set("ًٌٍَُِّْٰٕٓٔ")

PERSIAN_LETTERS = set(
    "ابپتثجچحخدذرزژسشصضطظعغفقکگلمنوهیءآأإئؤة"
    "پچژکگی۰۱۲۳۴"
    "۵۶۷۸۹"
)

# Frequent Persian function words. Used to detect visually-ordered (mirrored)
# extraction: if the reversed spellings outscore the real ones, the text layer
# stored glyphs in visual order and every line needs flipping.
COMMON_WORDS = [
    "و", "در", "به", "از", "که", "این", "را", "با", "برای", "است", "یک", "آن",
    "تا", "هم", "بود", "شد", "بر", "خود", "او", "ما", "شما", "ولی", "اما",
    "یا", "اگر", "چون", "همه", "هر", "دو", "سه", "نیز", "بی", "چند", "روی",
]


@dataclass
class NormalizeOptions:
    """Tiered rules. Defaults are the safe set."""
    strip_bidi: bool = True              # always safe
    decompose_presentation_forms: bool = True
    fold_arabic_to_persian: bool = True
    persian_digits: bool = True          # Arabic-Indic -> Persian forms
    ascii_to_persian_digits: bool = False  # opt-in; wrong in mixed/Latin text
    drop_tatweel: bool = True
    drop_zwj: bool = True
    collapse_whitespace: bool = True
    # Set False when normalizing a fragment (one span, not one line): the span's
    # boundary spaces are what separate it from its neighbours.
    strip_whitespace: bool = True
    repair_zwnj: bool = True             # conservative only
    repair_brackets: bool = True         # always safe; malformed order only
    repair_harakat: bool = True          # always safe; malformed placement only
    zwnj_mi_prefix: bool = True          # default; exception-listed
    zwnj_plurals: bool = False           # opt-in; needs review
    typography: bool = False             # opt-in; needs Persian-dominant text

    reported: dict = field(default_factory=dict)


def decompose_presentation_forms(text: str) -> str:
    """NFKC-decompose only the Arabic presentation-form blocks, leaving the rest
    of the document untouched. Whole-string NFKC would also mangle superscript
    footnote markers and typographic ligatures we may want to keep."""
    out = []
    for ch in text:
        cp = ord(ch)
        if any(lo <= cp <= hi for lo, hi in PRESENTATION_FORM_RANGES):
            out.append(unicodedata.normalize("NFKC", ch))
        else:
            out.append(ch)
    return "".join(out)


def strip_bidi_controls(text: str, drop_zwj: bool = True) -> str:
    bad = set(BIDI_CONTROLS)
    if drop_zwj:
        bad.add(0x200D)
    return "".join(ch for ch in text if ord(ch) not in bad)


def fold_codepoints(text: str) -> str:
    out = []
    for ch in text:
        cp = ord(ch)
        if cp in ARABIC_TO_PERSIAN:
            out.append(chr(ARABIC_TO_PERSIAN[cp]))
        elif cp in ARABIC_INDIC_DIGITS:
            out.append(chr(ARABIC_INDIC_DIGITS[cp]))
        else:
            out.append(ch)
    return "".join(out)


def to_persian_digits(text: str) -> str:
    return "".join(chr(ASCII_DIGITS[ord(c)]) if ord(c) in ASCII_DIGITS else c
                   for c in text)


def repair_zwnj_conservative(text: str) -> str:
    """Only the repairs that cannot produce a wrong word."""
    text = text.replace(ZWNJ + ZWNJ, ZWNJ)
    text = text.replace(ZWJ, "")
    # ZWNJ touching whitespace or punctuation is always a typesetting fault.
    out = []
    n = len(text)
    for i, ch in enumerate(text):
        if ch == ZWNJ:
            prev = text[i - 1] if i else ""
            nxt = text[i + 1] if i + 1 < n else ""
            if prev.isspace() or nxt.isspace() or not prev or not nxt:
                continue
            if prev in "«»()[]{}،؛؟!.:" or nxt in "«»()[]{}،؛؟!.:":
                continue
        out.append(ch)
    text = "".join(out)
    # Do not leave a ZWNJ stranded at either end of a line.
    text = text.strip(ZWNJ)
    return text


def insert_mi_prefix_zwnj(text: str) -> str:
    """Split the verbal prefixes می and نمی when they are glued to a stem.

    Exception-listed because میان (among), میز (table) and friends are nouns
    that must not be split.
    """
    out = []
    for token in text.split(" "):
        out.append(_split_token(token))
    return " ".join(out)


def _split_token(token: str) -> str:
    # Strip punctuation for inspection, reattach after.
    lead = ""
    trail = ""
    while token and token[0] in "«»()[]{}،؛؟!.:،":
        lead += token[0]
        token = token[1:]
    while token and token[-1] in "«»()[]{}،؛؟!.:،":
        trail = token[-1] + trail
        token = token[:-1]
    if not token or ZWNJ in token:
        return lead + token + trail

    for prefix in ("نمی", "می"):
        if token.startswith(prefix) and len(token) > len(prefix) + 1:
            rest = token[len(prefix):]
            if rest[0] in PERSIAN_LETTERS and token not in MI_EXCEPTIONS:
                return lead + prefix + ZWNJ + rest + trail
    return lead + token + trail


def repair_mirrored_brackets(text: str) -> tuple[str, int]:
    """Swap the outer brackets of tokens that arrive closed-before-open.

    Returns the repaired text and how many tokens were changed, so the caller can
    surface it: a non-zero count is worth a glance, since it means an extractor
    mirrored punctuation on that page.
    """
    fixed = 0

    def _fix(m: re.Match) -> str:
        nonlocal fixed
        token = m.group(0)
        if (len(token) >= 3 and token[0] in CLOSE_TO_OPEN
                and CLOSE_TO_OPEN[token[0]] == token[-1]):
            fixed += 1
            return CLOSE_TO_OPEN[token[0]] + token[1:-1] + OPEN_TO_CLOSE[token[-1]]
        return token

    return _TOKEN.sub(_fix, text), fixed


def repair_detached_harakat(text: str) -> tuple[str, int]:
    """Drop combining marks that arrived detached, doubled, or on Latin text.

    Returns the repaired text and the count removed, so a caller can surface it:
    a page that reports many is a decorated page whose diacritics were drawn as
    free-standing glyphs rather than composed with their letters.
    """
    out: list[str] = []
    removed = 0
    for ch in text:
        if ch in HARAKAT:
            # A mark cannot follow whitespace, so the space in front of it is not
            # where the space belongs - but it is usually still a real word gap.
            # PDFKit draws these marks as positioned glyphs and lists them in
            # stream order, which puts the gap of 'بیلِ کش' before the mark
            # instead of after it. Deleting the space there fuses two words, so
            # it is held back and re-emitted behind the mark; a gap that turns
            # out to be spurious collapses later with the rest of the whitespace.
            gap = False
            prev = out[-1] if out else ""
            if prev == " ":
                out.pop()
                gap = True
                prev = out[-1] if out else ""
            if prev == ch or (prev.isascii() and prev.isalpha()):
                # The mark itself is the artifact: a duplicate of the one before
                # it, or a stray on Latin text.
                removed += 1
            elif prev and prev not in HARAKAT and not prev.isspace():
                # A real mark, detached from the letter it belongs to.
                out.append(ch)
            else:
                # Nothing left to attach it to.
                removed += 1
            if gap:
                out.append(" ")
            continue
        out.append(ch)
    return "".join(out), removed


def _collapse_keep_ends(text: str) -> str:
    """Collapse whitespace runs but keep at most one space at either end.

    Normalizing a fragment rather than a whole line: a span's own boundary
    whitespace *is* the word gap between it and the span beside it, and the
    separators extraction inserts between segments are nothing but a space.
    Trimming here fuses words that were never adjacent, which is how
    'هنریک ایبسن' came out as 'هنریکایبسن'.
    """
    out = []
    for line in text.split("\n"):
        core = " ".join(line.split())
        if not core:
            out.append("" if not line else " ")
            continue
        out.append((" " if line[0].isspace() else "") + core
                   + (" " if line[-1].isspace() else ""))
    return "\n".join(out)


def collapse_whitespace(text: str, strip: bool = True) -> str:
    if not strip:
        return _collapse_keep_ends(text)
    text = text.replace(" ", " ")
    text = text.replace("​", "")
    text = "\n".join(" ".join(line.split()) for line in text.split("\n"))
    while "\n\n\n" in text:
        text = text.replace("\n\n\n", "\n\n")
    return text


def apply_typography(text: str) -> str:
    return "".join(chr(TYPOGRAPHY[ord(c)]) if ord(c) in TYPOGRAPHY else c
                   for c in text)


# --- Reversal detection ---------------------------------------------------

def _score_words(tokens) -> int:
    return sum(1 for t in tokens if t in COMMON_WORDS)


def looks_mirrored(text: str, threshold: float = 1.6) -> bool:
    """True when the text layer stored glyphs in visual order.

    Extraction in visual order leaves every word letter-reversed while the word
    sequence stays intact, so reversing each word and scoring against a list of
    frequent function words separates the two cases cleanly.
    """
    tokens = [t for t in text.split() if t.isalpha()]
    if len(tokens) < 30:
        return False
    forward = _score_words(tokens)
    backward = _score_words([t[::-1] for t in tokens])
    if backward == 0:
        return False
    return forward < backward * threshold


def unmirror_line(line: str) -> str:
    """Reverse a visually-ordered line back to logical order, then un-reverse the
    embedded Latin/digit runs that were already left-to-right."""
    rev = line[::-1]
    # Latin words and digit groups read left-to-right in both orders.
    out, buf = [], []
    for ch in rev:
        if ch.isascii() and (ch.isalnum() or ch in "._-@:/"):
            buf.append(ch)
        else:
            if buf:
                out.append("".join(reversed(buf)))
                buf = []
            out.append(ch)
    if buf:
        out.append("".join(reversed(buf)))
    return "".join(out)


# --- Entry point ----------------------------------------------------------

def normalize(text: str, opts: NormalizeOptions | None = None) -> str:
    opts = opts or NormalizeOptions()
    stats = opts.reported

    if opts.strip_bidi:
        text = strip_bidi_controls(text, drop_zwj=opts.drop_zwj)
    if opts.decompose_presentation_forms:
        text = decompose_presentation_forms(text)
    if opts.fold_arabic_to_persian or opts.persian_digits:
        text = fold_codepoints(text)
    if opts.ascii_to_persian_digits:
        text = to_persian_digits(text)
    if opts.drop_tatweel:
        text = text.replace(TATWEEL, "")

    mirror = looks_mirrored(text)
    stats["mirrored"] = mirror
    if mirror:
        text = "\n".join(unmirror_line(l) for l in text.split("\n"))

    if opts.repair_brackets:
        text, fixed = repair_mirrored_brackets(text)
        stats["brackets_repaired"] = fixed

    if opts.repair_harakat:
        text, dropped = repair_detached_harakat(text)
        stats["harakat_removed"] = dropped

    if opts.repair_zwnj:
        before = text.count(ZWNJ)
        text = repair_zwnj_conservative(text)
        stats["zwnj_removed"] = before - text.count(ZWNJ)
    if opts.zwnj_mi_prefix:
        before = text.count(ZWNJ)
        text = insert_mi_prefix_zwnj(text)
        stats["zwnj_added"] = text.count(ZWNJ) - before
    if opts.collapse_whitespace:
        text = collapse_whitespace(text, strip=opts.strip_whitespace)
    if opts.typography:
        text = apply_typography(text)
    return text


def has_persian(text: str) -> bool:
    return any("؀" <= ch <= "ۿ" for ch in text)
