#!/usr/bin/env python3
"""Audit installed fonts for real Persian (Arabic-script) support.

Distinguishes fonts that will shape correctly in Kindle/Apple Books from the
legacy Iranian fonts that only carry Arabic presentation forms or a non-Unicode
encoding. Those render as disconnected letters and are useless for EPUB embedding.
"""
import sys
from pathlib import Path

from fontTools.ttLib import TTFont, TTCollection
from fontTools.ttLib.tables._c_m_a_p import CmapSubtable

# Base Arabic letters Persian actually needs, plus the Persian-only four.
CORE = {
    0x0627: "alef", 0x0628: "beh", 0x062A: "teh", 0x0646: "noon", 0x0645: "meem",
}
PERSIAN_ONLY = {
    0x067E: "peh", 0x0686: "cheh", 0x0698: "jeh", 0x06A9: "kaf-fa", 0x06AF: "gaf",
    0x06CC: "yeh-fa", 0x06F0: "digit-0-fa",
}
SHAPING_FEATURES = {"init", "medi", "fina", "isol", "rlig", "rclt", "calt", "liga", "mark", "mkmk"}
PRESFORM_RANGES = ((0xFB50, 0xFDFF), (0xFE70, 0xFEFF))


def coverage(cmap: dict) -> dict:
    keys = set(cmap)
    return {
        "core": [n for c, n in CORE.items() if c in keys],
        "persian_only": [n for c, n in PERSIAN_ONLY.items() if c in keys],
        "zwnj": 0x200C in keys,
        "presforms": sum(1 for k in keys if any(a <= k <= b for a, b in PRESFORM_RANGES)),
        "arabic_yeh_kaf": (0x064A in keys, 0x0643 in keys),
    }


def shape_features(font: TTFont) -> set:
    if "GSUB" not in font:
        return set()
    try:
        recs = font["GSUB"].table.FeatureList.FeatureRecord
    except Exception:
        return set()
    return {r.FeatureTag for r in recs} & SHAPING_FEATURES


def audit(path: Path) -> list[dict]:
    out = []
    try:
        if path.suffix.lower() == ".ttc":
            fonts = [TTCollection(str(path), lazy=True).fonts[i]
                     for i in range(len(TTCollection(str(path), lazy=True).fonts))]
        else:
            fonts = [TTFont(str(path), lazy=True, fontNumber=0)]
    except Exception as e:
        return [{"path": path, "error": str(e)}]

    for f in fonts:
        try:
            best = f.getBestCmap() or {}
            if not best:
                continue
            cov = coverage(best)
            # Skip fonts with no Arabic at all.
            if not cov["core"] and not cov["persian_only"]:
                continue
            feats = shape_features(f)
            name = "?"
            for rec in f["name"].names:
                if rec.nameID == 1:
                    try:
                        name = rec.toUnicode()
                        break
                    except Exception:
                        pass
            out.append({
                "path": path, "family": name, "cov": cov, "features": feats,
                "upem": f["head"].unitsPerEm,
                "size_kb": path.stat().st_size // 1024,
            })
        except Exception as e:
            out.append({"path": path, "error": str(e)})
    return out


def verdict(r: dict) -> tuple[str, str]:
    cov, feats = r["cov"], r["features"]
    shaped = bool(feats & {"init", "medi", "fina"})
    persian = len(cov["persian_only"]) >= 5
    legacy = cov["presforms"] > 40 and not shaped
    if legacy:
        return "LEGACY", "presentation-form only, no shaping - will break"
    if shaped and persian and cov["zwnj"]:
        return "GOOD", "proper Unicode + Arabic shaping"
    if shaped and persian:
        return "GOOD*", "shapes, no ZWNJ glyph (falls back, usually fine)"
    if shaped and not persian:
        return "ARABIC", "shapes, but missing some Persian-specific letters"
    if not shaped:
        return "BROKEN", "no init/medi/fina - letters will not join"
    return "?", ""


def main():
    roots = [Path.home() / "Library/Fonts", Path("/Library/Fonts"),
             Path("/System/Library/Fonts/Supplemental"), Path("/System/Library/Fonts")]
    seen = set()
    rows = []
    for root in roots:
        if not root.is_dir():
            continue
        for p in sorted(root.iterdir()):
            if p.suffix.lower() not in (".ttf", ".otf", ".ttc", ".otc"):
                continue
            for r in audit(p):
                if "error" in r:
                    print(f"  ! {r['path'].name}: {r['error']}", file=sys.stderr)
                    continue
                key = (r["family"], str(r["path"]))
                if key in seen:
                    continue
                seen.add(key)
                rows.append(r)

    buckets = {}
    for r in rows:
        v, why = verdict(r)
        buckets.setdefault(v, []).append((r, why))

    order = ["GOOD", "GOOD*", "ARABIC", "LEGACY", "BROKEN", "?"]
    print(f"Scanned {len(rows)} Arabic-script font faces across {len(roots)} roots.\n")
    for v in order:
        if v not in buckets:
            continue
        items = buckets[v]
        print(f"=== {v} ({len(items)}) ===")
        for r, why in sorted(items, key=lambda x: x[0]["family"].lower()):
            fam = r["family"]
            n = len(r["cov"]["persian_only"])
            print(f"  {fam:<34} persian={n}/7 upem={r['upem']:<5} {r['size_kb']:>5}KB  {why}")
        print()

    good = [r["family"] for r, _ in buckets.get("GOOD", [])]
    if good:
        print("EMBEDDABLE:", ", ".join(sorted(set(good), key=str.lower)))


if __name__ == "__main__":
    main()
