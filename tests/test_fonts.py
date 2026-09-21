#!/usr/bin/env python3
"""Regression checks for font-license classification."""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from persian_ebook.fonts import BUNDLED_DIR, _license_allows_redistribution

bundled = sorted(BUNDLED_DIR.glob("*.ttf")) + sorted(BUNDLED_DIR.glob("*.otf"))
assert bundled, "no bundled fonts found"
for path in bundled:
    assert _license_allows_redistribution(path), path
print(f"  pass  {len(bundled)} bundled font files are recognized as redistributable")

unknown = Path(tempfile.mkdtemp()) / "not-a-font.ttf"
unknown.write_bytes(b"not a font")
assert not _license_allows_redistribution(unknown)
print("  pass  unknown/malformed font is not guessed redistributable")

print()
print("all passed")
