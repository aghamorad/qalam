"""Optional EPUB -> MOBI conversion through calibre.

Qalam owns the PDF -> structured EPUB pipeline. MOBI is produced only as a
post-processing step from that EPUB using calibre's maintained `ebook-convert`
tool. This keeps the MOBI writer out of Qalam while still allowing a one-click
workflow when calibre is installed.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


def find_ebook_convert() -> Path | None:
    """Return calibre's ebook-convert executable when it is available."""
    explicit = os.environ.get("QALAM_EBOOK_CONVERT", "").strip()
    if explicit:
        path = Path(explicit).expanduser()
        if path.is_file() and os.access(path, os.X_OK):
            return path

    on_path = shutil.which("ebook-convert")
    if on_path:
        return Path(on_path)

    candidates = (
        Path("/Applications/calibre.app/Contents/MacOS/ebook-convert"),
        Path.home() / "Applications/calibre.app/Contents/MacOS/ebook-convert",
    )
    for path in candidates:
        if path.is_file() and os.access(path, os.X_OK):
            return path
    return None


def calibre_available() -> bool:
    return find_ebook_convert() is not None


def build_mobi(epub_path: str | Path, mobi_path: str | Path,
               *, timeout: int = 180) -> Path:
    """Convert a Qalam EPUB into a KF8-only MOBI file with calibre.

    KF8 is selected intentionally: old MOBI 6 has much weaker CSS/RTL support.
    The resulting file still carries a .mobi extension, but its content is the
    newer Kindle format that can preserve the EPUB's modern layout features.
    """
    epub_path = Path(epub_path)
    mobi_path = Path(mobi_path)
    tool = find_ebook_convert()
    if tool is None:
        raise RuntimeError(
            "MOBI output requires calibre. Install calibre, then try again. "
            "Qalam looks for ebook-convert on PATH and inside /Applications/calibre.app."
        )

    mobi_path.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [
            str(tool),
            str(epub_path),
            str(mobi_path),
            "--output-profile", "kindle",
            "--mobi-file-type", "new",
        ],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if proc.returncode != 0 or not mobi_path.exists() or mobi_path.stat().st_size < 512:
        detail = (proc.stderr or proc.stdout or "").strip()
        if len(detail) > 1200:
            detail = detail[-1200:]
        raise RuntimeError(
            "calibre could not create the MOBI file"
            + (f": {detail}" if detail else "")
        )
    return mobi_path
