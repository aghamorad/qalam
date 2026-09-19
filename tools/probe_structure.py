#!/usr/bin/env python3
"""Show the inferred block structure for a page range.

Prints kinds, heading levels, and short text excerpts - enough to judge whether
headings were found and paragraphs merged sanely, without pulling the book in.

  python tools/probe_structure.py FILE.pdf --pages 12 --blocks 24
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from persian_ebook.extract import extract_pdf          # noqa: E402
from persian_ebook.normalize import normalize          # noqa: E402
from persian_ebook.structure import build              # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--pages", type=int, default=10)
    ap.add_argument("--blocks", type=int, default=24)
    ap.add_argument("--show", type=int, default=64)
    a = ap.parse_args()

    doc = extract_pdf(a.pdf, max_pages=a.pages)
    st = build(doc)
    print(f"{doc.path.name}")
    print(f"  pages read   {len(doc.pages)}/{doc.total_pages}")
    print(f"  body size    {st.body_size}")
    print(f"  heading tiers {st.stats.get('tiers')}")
    print(f"  blocks       {st.counts().most_common()}")
    print()
    for b in st.blocks[:a.blocks]:
        t = " ".join(normalize(b.text).split())
        print(f"  [{b.kind:<6}] p{b.page:<3} {t[:a.show]}")
    print()
    print("  heading outline:")
    for level, kind, text in st.outline()[:14]:
        print(f"    {'  ' * (level - 1)}{kind} {text[:60]}")


if __name__ == "__main__":
    main()
