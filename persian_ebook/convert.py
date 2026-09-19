"""The whole pipeline, in the one place both the CLI and the GUI call.

    PDF -> lines (extract) -> normalized text -> blocks (structure) -> EPUB

Keeping it here rather than in the GUI matters for more than tidiness: the
conversion is long enough that it has to run off the UI thread, and a function
with no widgets in it is a function that can be handed to a worker thread
without dragging the toolkit along.
"""

import re
import time
from dataclasses import dataclass, field, replace
from pathlib import Path

from . import epub, render
from .extract import Document, extract_pdf
from .fonts import FontChoice, pick
from .normalize import NormalizeOptions, normalize
from .render import RenderOptions
from .structure import Structure, build

# Persian text that a filename may carry, for guessing a title when the PDF has
# no metadata of its own.
_TRAILING_JUNK = re.compile(r"\s*[\(\[]?(?:نسخه|نسخهٔ|ویرایش|چاپ)[^\)\]]*[\)\]]?$")
_SEPARATOR = re.compile(r"\s*[،,]\s*")


@dataclass
class ConvertResult:
    source: Path
    epub_path: Path
    pages_read: int = 0
    pages_total: int = 0
    blocks: int = 0
    headings: int = 0
    scanned_pages: int = 0
    counts: dict = field(default_factory=dict)
    font: str = ""
    warnings: list[str] = field(default_factory=list)
    elapsed: float = 0.0
    preview_path: Path | None = None
    title: str = ""
    author: str = ""

    def report(self) -> str:
        lines = [
            f"{self.source.name} -> {self.epub_path.name}",
            f"  pages        {self.pages_read}/{self.pages_total}"
            + (f"  ({self.scanned_pages} with no text layer)"
               if self.scanned_pages else ""),
            f"  blocks       {self.blocks}  {self.counts}",
            f"  headings     {self.headings}",
            f"  font         {self.font or 'none embedded'}",
            f"  time         {self.elapsed:.1f}s",
        ]
        lines += [f"  warning      {w}" for w in self.warnings]
        return "\n".join(lines)


def guess_title_author(doc: Document) -> tuple[str, str]:
    """Title and author from PDF metadata, falling back to the filename.

    The filename fallback is not decoration: this corpus is scanned and re-typed
    books whose metadata is usually empty, and the convention here is
    'Author, Title.pdf' - so the split is on the Persian comma.
    """
    title = (doc.meta.get("title") or "").strip()
    author = (doc.meta.get("author") or "").strip()
    if title:
        return title, author

    stem = doc.path.stem
    stem = _TRAILING_JUNK.sub("", stem).strip()
    parts = [p.strip() for p in _SEPARATOR.split(stem) if p.strip()]
    if len(parts) >= 2 and not author:
        author, title = parts[0], "، ".join(parts[1:])
    else:
        title = stem
    return title, author


def normalize_document(doc: Document, opts: NormalizeOptions | None = None
                       ) -> dict:
    """Normalize every span in place. Returns the aggregated repair counts.

    Normalizing per span rather than per line is a deliberate trade: it keeps
    the bold and italic runs that structure detection worked out, at the cost of
    the odd typed token that straddles a font boundary. Every rule that matters
    here - folding, bidi stripping, detached harakat, bracket order - is a
    within-word or within-token repair and is unaffected by that boundary.
    """
    opts = opts or NormalizeOptions()
    # A span is a fragment, not a line: its leading and trailing spaces are the
    # gaps between it and the spans beside it, and normalization must not trim
    # them away or the words fuse. `reported` is shared with the caller's opts,
    # so the repair counts still aggregate into it.
    opts = replace(opts, strip_whitespace=False)
    for page in doc.pages:
        for line in page.lines:
            for span in line.spans:
                span.text = normalize(span.text, opts)
    return dict(opts.reported)


def build_structure(doc: Document, keep_notes: bool = True) -> Structure:
    return build(doc, keep_notes=keep_notes)


def render_options(doc: Document, title: str = "", author: str = "",
                   font: FontChoice | None = None,
                   **overrides) -> RenderOptions:
    opts = RenderOptions(
        title=title or "",
        author=author or "",
        font_family=font.family if font else "",
    )
    for k, v in overrides.items():
        if v is not None and hasattr(opts, k):
            setattr(opts, k, v)
    return opts


def convert(source: str | Path, out_path: str | Path | None = None,
            title: str = "", author: str = "", font_name: str = "",
            max_pages: int | None = None, keep_notes: bool = True,
            want_preview: bool = False, progress=None, **render_overrides
            ) -> ConvertResult:
    """Convert one PDF to an EPUB.

    `progress` is called with (fraction, message) if given, so a caller with a
    window can show something moving without this function knowing about it.
    """
    started = time.monotonic()
    source = Path(source)

    def step(frac, msg):
        if progress:
            progress(frac, msg)

    step(0.02, "خواندن پی‌دی‌اف…")
    doc = extract_pdf(source, max_pages=max_pages)
    if not doc.pages:
        raise ValueError(f"{source.name}: هیچ صفحه‌ای خوانده نشد")

    step(0.35, "نرمال‌سازی متن…")
    repairs = normalize_document(doc)

    step(0.55, "تشخیص ساختار…")
    structure = build_structure(doc, keep_notes=keep_notes)

    guess_t, guess_a = guess_title_author(doc)
    final_title = title.strip() or guess_t
    final_author = author.strip() or guess_a

    step(0.70, "جست‌وجوی قلم…")
    font = pick(font_name or None)

    # title and author are settled above; a caller that also passed them as
    # render overrides would otherwise collide on the keyword.
    overrides = {k: v for k, v in render_overrides.items()
                 if k not in ("title", "author")}
    opts = render_options(doc, title=final_title, author=final_author, font=font,
                          **overrides)

    warnings: list[str] = []
    if doc.scanned_pages:
        warnings.append(
            f"{doc.scanned_pages} صفحه متن لایه‌ای ندارد و در کتاب نیامده")
    if font is None:
        warnings.append("هیچ قلم فارسی روی این دستگاه پیدا نشد")
    elif not font.redistributable:
        warnings.append(f"قلم «{font.family}» اجازه بازتوزیع ندارد؛ "
                        f"برای انتشار عمومی از قلم آزاد استفاده کنید")
    if repairs.get("brackets_repaired"):
        warnings.append(f"{repairs['brackets_repaired']} مورد پرانتز اصلاح شد")

    if out_path is None:
        out_dir = source.parent / "converted"
        out_path = out_dir / (source.stem + ".epub")
    out_path = Path(out_path)

    step(0.82, "نوشتن ایپاب…")
    epub.build(structure, out_path, opts, font=font)

    result = ConvertResult(
        source=source,
        epub_path=out_path,
        pages_read=len(doc.pages),
        pages_total=doc.total_pages,
        blocks=len(structure.blocks),
        headings=len(structure.outline()),
        scanned_pages=doc.scanned_pages,
        counts=dict(structure.counts()),
        font=font.family if font else "",
        warnings=warnings,
        title=final_title,
        author=final_author,
    )

    if want_preview:
        step(0.94, "ساختن پیش‌نمایش…")
        preview = out_path.with_suffix(".preview.html")
        preview.write_text(
            render.preview_html(structure, opts, epub._font_files(font)),
            encoding="utf-8")
        result.preview_path = preview

    result.elapsed = time.monotonic() - started
    step(1.0, "انجام شد")
    return result
