#!/usr/bin/env python3
"""Self-checking tests for the normalizer. Run: python tests/test_normalize.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from persian_ebook.normalize import (  # noqa: E402
    NormalizeOptions, looks_mirrored, normalize, unmirror_line,
)

ZWNJ = "‌"
FAILED = []


def check(name, got, want):
    if got == want:
        print(f"  pass  {name}")
    else:
        FAILED.append(name)
        print(f"  FAIL  {name}")
        print(f"        got  {got!r}")
        print(f"        want {want!r}")


def check_true(name, cond):
    check(name, bool(cond), True)


print("codepoint folding")
check("arabic yeh/kaf -> persian", normalize("يك"), "یک")
check("teh marbuta -> heh", normalize("مدينه"), "مدینه")
check("arabic-indic digits -> persian", normalize("١٢٣٤"), "۱۲۳۴")

print("\npresentation forms (NFKC on Arabic blocks only)")
check("lam-alef ligature splits", normalize("ﻻ"), "لا")
check("final yeh form -> farsi yeh", normalize("ﻲ"), "ی")
check("latin ligature untouched", normalize("ﬁ"), "ﬁ")

print("\nbidi controls")
check("RLM stripped", normalize("abc‏def"), "abcdef")
check("RLE/PDF stripped", normalize("a‪b‬"), "ab")
check("ZWNJ survives bidi strip", normalize("می" + ZWNJ + "رود"),
      "می" + ZWNJ + "رود")

print("\ntatweel + whitespace")
check("tatweel removed", normalize("ســـلام"), "سلام")
check("nbsp -> space", normalize("a b"), "a b")
check("runs collapsed", normalize("a   b\n\n\n\nc"), "a b\n\nc")

print("\nZWNJ repair")
check("doubled ZWNJ collapsed", normalize("می" + ZWNJ + ZWNJ + "رود"),
      "می" + ZWNJ + "رود")
check("ZWNJ beside space dropped", normalize("می " + ZWNJ + "رود"), "می رود")
check("ZWNJ before punctuation dropped", normalize("کتاب" + ZWNJ + "،"), "کتاب،")

print("\nmi/nemi prefix")
check("miravam split", normalize("میروم"), "می" + ZWNJ + "روم")
check("nemikhanam split", normalize("نمیخواهم"), "نمی" + ZWNJ + "خواهم")
check("miyan NOT split", normalize("میان"), "میان")
check("miz NOT split", normalize("میز"), "میز")
check("existing ZWNJ left alone", normalize("می" + ZWNJ + "رود"),
      "می" + ZWNJ + "رود")

print("\nmirror detection (visual-order text layers)")
PROSE = ("در این کتاب نویسنده می‌کوشد نشان دهد که فرهنگ عامه چگونه شکل می‌گیرد "
         "و چه رابطه‌ای با قدرت دارد . این پرسش که ما چگونه به این وضع رسیدیم "
         "پرسشی است که هر خواننده می‌تواند از خود بپرسد و پاسخ آن را در فصل "
         "های بعدی جستجو کند . ")
text = PROSE * 4
# Visual-order extraction mirrors each line wholesale: the whole glyph run is
# stored left-to-right, so word order comes out reversed AND each word reversed.
mirrored = "\n".join(l[::-1] for l in text.split("\n"))
check_true("real text not flagged", not looks_mirrored(text))
check_true("mirrored text flagged", looks_mirrored(mirrored))
restored = "\n".join(unmirror_line(l) for l in mirrored.split("\n"))
check_true("line restored whole by unmirror", restored == text)

print("\nmirrored brackets (PDFKit artifact on bracketed numbers in RTL)")
check("closed-before-open paren swapped", normalize(")1882("), "(1882)")
check("normal paren pair untouched", normalize("(1882)"), "(1882)")
check("reversed square pair swapped", normalize("]12["), "[12]")
check("lone closing bracket untouched", normalize(")"), ")")
check("parens in place untouched", normalize("گفت (به نظر من) خوب"),
      "گفت (به نظر من) خوب")
o = NormalizeOptions()
normalize("می‌گفت )1369(", o)
check_true("repair counted for reporting", o.reported["brackets_repaired"] == 1)

print("\ndetached harakat (PDFKit artifact on decorated pages)")
# The space in front of a detached mark is not around the wrong way - it is the
# word gap of 'دشمنِ مردم', listed before the mark because the mark is drawn as a
# positioned glyph. It has to survive the absorption.
check("space before kasra absorbed", normalize("دشمن ِمردم"), "دشمنِ مردم")
check("doubled kasra collapsed", normalize("دشمن ِِ مردم"), "دشمنِ مردم")
# The title of the Ibsen book arrives as 'دشمن ِ ِمردم ِ': PDFKit emitted the
# word gap and the duplicated ezafe mark in the other order, and dropping the
# duplicate must not take the word gap with it.
check("space restored when a duplicate mark ate it",
      normalize("دشمن ِ ِمردم ِ"), "دشمنِ مردمِ")
check("kasra on latin word dropped", normalize("Madjid Omraniِِِ"),
      "Madjid Omrani")
check("composed kasra untouched", normalize("میرومِ"), "می‌رومِ")
check("shadda kept", normalize("مدّرس"), "مدّرس")
o = NormalizeOptions()
normalize("Omraniِِ", o)
check_true("removal counted for reporting", o.reported["harakat_removed"] == 2)

print("\nfragment mode (one span, not one line)")
# convert.normalize_document normalizes each span on its own. A span's boundary
# space is the gap between it and the span beside it, and the separators
# extraction inserts between segments are nothing but a space - trimming either
# fuses 'هنریک ایبسن' into 'هنریکایبسن'.
FRAG = NormalizeOptions(strip_whitespace=False)
check("trailing space on a span kept", normalize("هنریک ", FRAG), "هنریک ")
check("leading space on a span kept", normalize(" ایبسن", FRAG), " ایبسن")
check("bare separator span survives", normalize(" ", FRAG), " ")
check("interior runs still collapse", normalize("a   b", FRAG), "a b")
check("both ends kept at once", normalize(" a  b ", FRAG), " a b ")
check_true("default still trims", normalize(" a ") == "a")

print("\nopt-in rules")
check("typography off by default", normalize("a, b?"), "a, b?")
check("typography on request",
      normalize("a, b?", NormalizeOptions(typography=True)), "a، b؟")
check("ascii digits untouched by default", normalize("1400"), "1400")
check("ascii digits on request",
      normalize("1400", NormalizeOptions(ascii_to_persian_digits=True)), "۱۴۰۰")

print("\nstats surface what happened")
o = NormalizeOptions()
normalize("میروم", o)
check_true("zwnj_added reported", o.reported.get("zwnj_added") == 1)

print()
if FAILED:
    print(f"{len(FAILED)} FAILED: {', '.join(FAILED)}")
    sys.exit(1)
print("all passed")
