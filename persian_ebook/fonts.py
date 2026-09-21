"""Find a Persian font on this machine, and say which ones are safe to ship.

An EPUB has to carry its own font. A Kindle or an iPad has no Persian face worth
relying on, and the fonts these PDFs were set in are commercial Iranian designs
that the reader certainly does not have. So one family is chosen here and
embedded in the archive.

Two things matter when choosing: does the font actually cover Persian, and is it
licensed to travel inside the file. Coverage comes from the font's own cmap.
Redistribution status comes only from the bundled font we ship under OFL or from
license text embedded in the actual font file; family names alone are not enough
evidence to make a licensing claim.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

# Codepoint blocks that mean "this font can set Persian".
ARABIC_RANGES = (
    (0x0600, 0x06FF),   # Arabic
    (0x0750, 0x077F),   # Arabic Supplement
    (0xFB50, 0xFDFF),   # Arabic Presentation Forms-A
    (0xFE70, 0xFEFF),   # Arabic Presentation Forms-B
)

# A font is only useful here if it has the letters, not just a stray ornament.
MIN_ARABIC_COVERAGE = 40

FONT_DIRS = (
    Path.home() / "Library/Fonts",
    Path("/Library/Fonts"),
    Path("/System/Library/Fonts"),
    Path("/System/Library/Fonts/Supplemental"),
)

BUNDLED_DIR = Path(__file__).resolve().parent / "data" / "fonts"

# Letters that separate a font designed for Persian from one that merely has
# some Arabic in it. The coverage count cannot do this on its own: Arial and
# Tahoma carry the presentation-form blocks too and would outrank a real
# Persian design on sheer breadth. These are the letters Persian adds.
PERSIAN_PROBE = "پچژگکیۃ۰۱۲۳۴۵۶۷۸۹"

# Designs that actually look right for a Persian book, best first. Ranking by
# name is crude, but the alternative - guessing quality from the font tables -
# is worse, and the user can always override the choice in the GUI.
PREFERRED_FAMILIES = (
    "vazirmatn", "vazir", "iransans", "iranyekan", "yekan bakh", "sahel",
    "shabnam", "samim", "tanha", "gandom", "parastoo", "estedad", "dana",
    "peyda", "morabba", "mikhak", "shahab", "bnazanin", "inazanin", "nazanin",
    "bmitra", "imitra", "mitra", "btitr", "titr", "amiri", "noto naskh arabic",
    "noto sans arabic", "scheherazade", "markazi text", "kalameh", "dubai",
)

OPEN_LICENSE_MARKERS = (
    "sil open font license",
    "open font license",
    "scripts.sil.org/ofl",
    "openfontlicense",
    "apache license, version 2.0",
    "apache.org/licenses/license-2.0",
)

# Filename fragments that mark a face as bold or italic when the family's faces
# ship as separate files. 'bd' is here for the Borna designs, which label the
# bold weight 'BNazaninBd' rather than 'BNazanin-Bold'.
BOLD_FILE = re.compile(r"(^|[^a-z])(bd|bold|black|heavy|semibold|demibold)([^a-z]|$)",
                       re.I)
ITALIC_FILE = re.compile(r"(italic|oblique|it\b)", re.I)

# Weights that are neither regular nor bold, so they must not be mistaken for
# the regular face when a family ships an UltraLight and a Medium as well.
NOT_REGULAR = re.compile(r"(light|thin|ultra|black|medium|heavy|semi|demi|bd|bold)",
                         re.I)


@dataclass
class FontChoice:
    family: str
    regular: Path
    bold: Path | None = None
    italic: Path | None = None
    bold_italic: Path | None = None
    redistributable: bool = False
    arabic_coverage: int = 0
    persian_probe: int = 0
    sources: list[Path] = field(default_factory=list)

    @property
    def label(self) -> str:
        mark = "" if self.redistributable else "  [license unknown]"
        return f"{self.family}{mark}"


def _sfnt_paths() -> list[Path]:
    out: list[Path] = []
    for d in FONT_DIRS:
        if not d.is_dir():
            continue
        for p in d.iterdir():
            if p.suffix.lower() in (".ttf", ".otf", ".ttc") and not p.name.startswith("."):
                out.append(p)
    if BUNDLED_DIR.is_dir():
        out.extend(sorted(p for p in BUNDLED_DIR.iterdir()
                          if p.suffix.lower() in (".ttf", ".otf")
                          and not p.name.startswith(".")))
    return sorted(out)


def _cmap_stats(path: Path) -> tuple[int, int]:
    """(Arabic codepoints covered, Persian-specific letters covered).

    fontTools is chatty about malformed 'post' tables in these old font files;
    the warnings are noise here, since a broken post table does not affect the
    cmap being read.
    """
    try:
        import logging
        from fontTools.ttLib import TTCollection, TTFont
        logging.getLogger("fontTools").setLevel(logging.ERROR)
    except ImportError:
        return 0, 0
    try:
        if path.suffix.lower() == ".ttc":
            fonts = list(TTCollection(str(path), lazy=True).fonts)
        else:
            fonts = [TTFont(str(path), lazy=True, fontNumber=0)]
    except Exception:
        return 0, 0
    best = (0, 0)
    for f in fonts:
        try:
            cmap = set()
            for t in f["cmap"].tables:
                cmap |= set(t.cmap.keys())
        except Exception:
            continue
        n = sum(1 for lo, hi in ARABIC_RANGES for cp in range(lo, hi + 1)
                if cp in cmap)
        probe = sum(1 for ch in PERSIAN_PROBE if ord(ch) in cmap)
        if (probe, n) > best:
            best = (probe, n)
    return best[1], best[0]


def arabic_coverage(path: Path) -> int:
    """How many Persian letter codepoints the font's cmap can actually set."""
    return _cmap_stats(path)[0]


def family_name(path: Path) -> str:
    """The family as the font itself names it, not as the file is called -
    files in a font book are frequently renamed and the CSS name has to match
    what is inside the file for a reader to pick it up."""
    try:
        from fontTools.ttLib import TTFont, TTCollection
    except ImportError:
        return path.stem
    try:
        f = (list(TTCollection(str(path), lazy=True).fonts)[0]
             if path.suffix.lower() == ".ttc"
             else TTFont(str(path), lazy=True, fontNumber=0))
        for rec in f["name"].names:
            if rec.nameID in (16, 1):
                try:
                    v = rec.toUnicode().strip()
                except Exception:
                    continue
                if v:
                    return v
    except Exception:
        pass
    return path.stem



def _license_allows_redistribution(path: Path) -> bool:
    """Return True only when the actual font file provides positive evidence.

    Bundled Vazirmatn is covered by the OFL file shipped with Qalam. For fonts
    installed elsewhere, inspect the SFNT name table's license description/URL.
    Unknown or missing metadata is deliberately treated as unknown, not as a
    guess based on the family name.
    """
    try:
        if path.resolve().is_relative_to(BUNDLED_DIR.resolve()):
            return True
    except Exception:
        pass

    try:
        from fontTools.ttLib import TTCollection, TTFont
        if path.suffix.lower() == ".ttc":
            fonts = list(TTCollection(str(path), lazy=True).fonts)
        else:
            fonts = [TTFont(str(path), lazy=True, fontNumber=0)]
    except Exception:
        return False

    if not fonts:
        return False

    for font in fonts:
        try:
            records = []
            for rec in font["name"].names:
                if rec.nameID not in (13, 14):
                    continue
                try:
                    records.append(rec.toUnicode().strip().lower())
                except Exception:
                    continue
            evidence = " ".join(records)
        except Exception:
            return False
        if not evidence or not any(marker in evidence for marker in OPEN_LICENSE_MARKERS):
            return False
    return True


def _stats(path: Path, cache: dict) -> tuple[int, int]:
    key = str(path)
    if key not in cache:
        cache[key] = _cmap_stats(path)
    return cache[key]


def _rank(family: str) -> int:
    low = family.strip().lower()
    for i, name in enumerate(PREFERRED_FAMILIES):
        if name in low:
            return i
    return len(PREFERRED_FAMILIES)


def discover() -> list[FontChoice]:
    """Every Persian-capable family installed here, best candidates first.

    Ranking prefers a design actually made for Persian, then explicit evidence
    that its license allows redistribution, then how completely the face covers
    the language.
    """
    cache: dict = {}
    by_family: dict[str, list[Path]] = {}
    for p in _sfnt_paths():
        if _stats(p, cache)[0] < MIN_ARABIC_COVERAGE:
            continue
        fam = family_name(p)
        # Dot-prefixed families are macOS internals (.LastResort, .SF Arabic);
        # .LastResort in particular covers every block and would rank first.
        if not fam or fam.startswith("."):
            continue
        by_family.setdefault(fam, []).append(p)

    choices: list[FontChoice] = []
    for fam, paths in by_family.items():
        regular = bold = italic = bold_italic = None
        for p in sorted(paths, key=lambda q: (len(q.name), q.name)):
            is_b = bool(BOLD_FILE.search(p.stem))
            is_i = bool(ITALIC_FILE.search(p.stem))
            if is_b and is_i and bold_italic is None:
                bold_italic = p
            elif is_b and bold is None:
                bold = p
            elif is_i and italic is None:
                italic = p
            elif regular is None and not NOT_REGULAR.search(p.stem):
                regular = p
        if regular is None:
            # Every face is a non-regular weight; take the plainest one anyway.
            regular = sorted(paths, key=lambda q: len(q.name))[0]
        cov, probe = max((_stats(p, cache) for p in paths), key=lambda t: t[0])
        choices.append(FontChoice(
            family=fam,
            regular=regular,
            bold=bold,
            italic=italic,
            bold_italic=bold_italic,
            redistributable=all(_license_allows_redistribution(p) for p in paths),
            arabic_coverage=cov,
            persian_probe=probe,
            sources=sorted(paths),
        ))

    choices.sort(key=lambda c: (_rank(c.family), -c.persian_probe,
                                not c.redistributable, -c.arabic_coverage,
                                c.family.lower()))
    return choices


def pick(preferred: str | None = None, choices=None) -> FontChoice | None:
    """Resolve a family name to a choice, falling back to the best available."""
    choices = choices if choices is not None else discover()
    if not choices:
        return None
    if preferred:
        want = preferred.strip().lower()
        for c in choices:
            if c.family.strip().lower() == want:
                return c
        for c in choices:
            if want in c.family.strip().lower():
                return c
    return choices[0]
