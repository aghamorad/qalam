#!/usr/bin/env python3
"""Character-level dump: codepoint plus x-origin, to diagnose ordering.

The lam-alef ligature is the case that matters. When a PDF shapes 'la' as a
ligature, extraction can emit the two base letters in visual order (alef, lam)
while genuine 'al' sequences in words like سال also read (alef, lam). The
codepoints are identical, so the only discriminator is geometry: in a flipped
ligature the alef sits to the left of the lam.

  python tools/probe_chars.py FILE.pdf --grep 1990 --page 0
"""
import argparse
import unicodedata
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pymupdf  # noqa: E402

pymupdf.TOOLS.mupdf_display_errors(False)
pymupdf.TOOLS.mupdf_display_warnings(False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--grep", default="")
    ap.add_argument("--page", type=int, default=0)
    ap.add_argument("--max-lines", type=int, default=3)
    a = ap.parse_args()

    doc = pymupdf.open(a.pdf)
    try:
        raw = doc[a.page].get_text("rawdict")
    finally:
        doc.close()

    shown = 0
    for block in raw.get("blocks", []):
        if block.get("type") != 0:
            continue
        for ln in block.get("lines", []):
            line_text = "".join(c["c"] for sp in ln.get("spans", [])
                                for c in sp.get("chars", []))
            if a.grep and a.grep not in line_text and a.grep not in line_text[::-1]:
                continue
            if shown >= a.max_lines:
                return
            shown += 1
            print(f"\nline [{a.page}]: {line_text}")
            for sp in ln.get("spans", []):
                print(f"  font={sp.get('font')} size={sp.get('size')}")
                for c in sp.get("chars", []):
                    ch = c["c"]
                    x = round(c["origin"][0], 1)
                    try:
                        nm = unicodedata.name(ch)
                    except ValueError:
                        nm = "?"
                    nm = nm.replace("ARABIC LETTER ", "").replace("FARSI ", "FA-")
                    print(f"    U+{ord(ch):04X} x={x:>7}  {ch}  {nm}")


if __name__ == "__main__":
    main()
