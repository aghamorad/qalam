"""Command line entry point.

    python -m persian_ebook.cli book.pdf [-o out.epub] [--pages 20] ...

Kept deliberately thin: everything it does is a call into convert.convert, so
the GUI and the CLI cannot drift apart in behaviour.
"""

import argparse
import sys
from pathlib import Path

from .convert import convert
from .fonts import discover


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="qalam",
        description="تبدیل پی‌دی‌اف فارسی به ایپاب (کیندل و آی‌پد)")
    p.add_argument("source", type=Path, nargs="?", help="PDF ورودی")
    p.add_argument("-o", "--out", type=Path, default=None,
                   help="مسیر ایپاب خروجی")
    p.add_argument("--title", default="", help="عنوان کتاب")
    p.add_argument("--author", default="", help="نام نویسنده")
    p.add_argument("--font", default="", help="نام خانوادگی قلم (مثلاً Vazirmatn)")
    p.add_argument("--pages", type=int, default=None,
                   help="فقط این تعداد صفحه اول را بخوان")
    p.add_argument("--no-notes", action="store_true",
                   help="پانوشت‌ها را نادیده بگیر")
    p.add_argument("--preview", action="store_true",
                   help="یک فایل HTML برای دیدن در مرورگر هم بساز")
    p.add_argument("--list-fonts", action="store_true",
                   help="قلم‌های فارسی این دستگاه را نشان بده و بیرون بیا")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)

    if args.list_fonts:
        choices = discover()
        if not choices:
            print("هیچ قلم فارسی پیدا نشد.")
            return 1
        for i, c in enumerate(choices[:40]):
            faces = sum(1 for k in ("regular", "bold", "italic", "bold_italic")
                        if getattr(c, k, None))
            print(f"{i:3d}  {c.label:<44} {faces} وزن   "
                  f"پوشش عربی {c.arabic_coverage}")
        return 0

    if args.source is None:
        build_parser().print_help()
        return 2

    if not args.source.exists():
        print(f"فایل پیدا نشد: {args.source}", file=sys.stderr)
        return 2

    def progress(frac, msg):
        bar = "#" * int(frac * 24)
        print(f"\r  [{bar:<24}] {frac * 100:3.0f}%  {msg}",
              end="", file=sys.stderr, flush=True)

    try:
        result = convert(
            args.source,
            out_path=args.out,
            title=args.title,
            author=args.author,
            font_name=args.font,
            max_pages=args.pages,
            keep_notes=not args.no_notes,
            want_preview=args.preview,
            progress=progress,
        )
    except Exception as exc:                      # noqa: BLE001
        print(f"\nخطا: {exc}", file=sys.stderr)
        return 1

    print("\r" + " " * 60 + "\r", end="", file=sys.stderr)
    print(result.report())
    if result.preview_path:
        print(f"  preview      {result.preview_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
