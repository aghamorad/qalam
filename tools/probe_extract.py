#!/usr/bin/env python3
"""Inspect extraction quality on a page range without dumping the book.

Prints typography stats and a handful of truncated lines - enough to judge
whether RTL ordering is right, whether headings are separable by size, and
whether anything needs the PDFKit escape hatch.

  python tools/probe_extract.py FILE.pdf [--pages N] [--lines K] [--raw]
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from persian_ebook.extract import extract_pdf  # noqa: E402
from persian_ebook.normalize import looks_mirrored, normalize  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--pages", type=int, default=3)
    ap.add_argument("--lines", type=int, default=12)
    ap.add_argument("--show", type=int, default=58, help="chars shown per line")
    ap.add_argument("--raw", action="store_true", help="skip normalization")
    ap.add_argument("--sort", action="store_true", help="PyMuPDF bbox sort")
    ap.add_argument("--grep", help="only lines containing this substring")
    ap.add_argument("--codepoints", action="store_true",
                    help="dump hex codepoints under each line")
    a = ap.parse_args()

    doc = extract_pdf(a.pdf, max_pages=a.pages, sort=a.sort)
    print(doc.summary())
    if doc.meta.get("title"):
        print(f"  PDF title: {doc.meta['title'][:70]}")

    lines = doc.lines
    if not lines:
        print("  no text lines extracted")
        return

    joined = "\n".join(l.stripped for l in lines)
    print(f"  mirror-detected (visual order): {looks_mirrored(joined)}")

    body = doc.body_size()
    print(f"  body size = {body}; distinct sizes = "
          f"{len(doc.size_histogram())}")
    print()
    print(f"  {'pg':>3} {'size':>6} {'b':<1} {'ch':>4}  text")
    print("  " + "-" * 72)

    shown = 0
    for l in lines:
        if a.grep and a.grep not in l.text:
            continue
        if shown >= a.lines:
            break
        shown += 1
        t = l.text if a.raw else normalize(l.text)
        flat = " ".join(t.split())
        print(f"  {l.page:>3} {l.size:>6} {'B' if l.bold else ' ':<1} "
              f"{l.char_count:>4}  {flat[:a.show]}")
        if a.codepoints:
            for word in flat.split()[:8]:
                cps = " ".join(f"{ord(c):04X}" for c in word)
                print(f"          {word}  ->  {cps}")


if __name__ == "__main__":
    main()
