"""Entry point for the frozen macOS app bundle.

PyInstaller needs a plain script to start from, and `persian_ebook.gui` uses
relative imports so it cannot be one. This is the whole reason the file exists.
"""

import multiprocessing
import sys


def main() -> int:
    # Without this a frozen app that ever touches multiprocessing re-launches
    # itself instead of forking.
    multiprocessing.freeze_support()
    from persian_ebook.gui import main as gui_main
    return gui_main()


if __name__ == "__main__":
    sys.exit(main())
