#!/usr/bin/env python3
"""Find Persian PDFs on disk and rank them by how much Arabic-script text they hold.

Also reports whether a text layer exists at all, which is the born-digital vs
scanned fork in the pipeline. Stops early once enough candidates are found, and
tolerates the malformed/encrypted PDFs that are common in a large corpus.
"""
import re
import sys
from pathlib import Path

import pymupdf

pymupdf.TOOLS.mupdf_display_errors(False)
pymupdf.TOOLS.mupdf_display_warnings(False)

ROOTS = [Path.home() / "Documents", Path.home() / "Desktop",
         Path.home() / "Downloads", Path.home() / "Claude"]
SKIP = {"node_modules", ".git", ".venv", "Library", ".Trash", "__pycache__"}
ARABIC = re.compile(r"[؀-ۿݐ-ݿﭐ-﷿ﹰ-﻿]")
PROBE_PAGES = 4
MAX_HITS = 30


def probe(path: Path) -> dict | None:
    try:
        doc = pymupdf.open(str(path))
    except Exception:
        return None
    try:
        if doc.needs_pass or doc.is_encrypted:
            return None
        n = len(doc)
        total = arabic = chars = 0
        sample = ""
        for i in range(min(PROBE_PAGES, n)):
            try:
                t = doc[i].get_text()
            except Exception:
                continue
            chars += len(t)
            hits = ARABIC.findall(t)
            arabic += len(hits)
            if not sample and len(hits) > 40:
                sample = " ".join(t.split())[:150]
        if not chars:
            return None
        return {"path": path, "pages": n, "chars": chars, "arabic": arabic,
                "ratio": arabic / chars, "sample": sample,
                "text_layer": chars > 200}
    except Exception:
        return None
    finally:
        try:
            doc.close()
        except Exception:
            pass


def main():
    candidates = []
    for root in ROOTS:
        if not root.is_dir():
            continue
        for p in root.rglob("*.pdf"):
            if any(part in SKIP for part in p.parts):
                continue
            try:
                if p.stat().st_size < 20_000:
                    continue
            except OSError:
                continue
            candidates.append(p)

    print(f"Found {len(candidates)} PDFs; probing until {MAX_HITS} Persian hits...",
          file=sys.stderr)

    rows = []
    for i, p in enumerate(candidates, 1):
        if i % 200 == 0:
            print(f"  ...{i}/{len(candidates)} probed, {len(rows)} hits",
                  file=sys.stderr)
        r = probe(p)
        if r and r["ratio"] > 0.25 and r["arabic"] > 400:
            rows.append(r)
            if len(rows) >= MAX_HITS:
                break

    rows.sort(key=lambda r: -r["ratio"])
    if not rows:
        print("No Persian-heavy PDFs found.")
        return
    print(f"{len(rows)} Persian PDFs by Arabic-script share:\n")
    for r in rows:
        rel = str(r["path"]).replace(str(Path.home()), "~")
        flag = "TEXT" if r["text_layer"] else "SCAN"
        print(f"[{flag}] ratio={r['ratio']:.2f} pages={r['pages']:<4} {rel}")


if __name__ == "__main__":
    main()
