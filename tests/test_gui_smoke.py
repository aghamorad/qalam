#!/usr/bin/env python3
"""Headless smoke test for the GUI's wiring.

Run: QT_QPA_PLATFORM=offscreen python tests/test_gui_smoke.py [sample.pdf]

Drives the real MainWindow through a real conversion on the offscreen platform,
so it catches the failures a pipeline test cannot see: a signal connected to the
wrong slot, a worker thread that never emits, progress that never advances.
Needs a sample PDF; without one it only checks that the window builds.
"""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QSettings, QTimer                   # noqa: E402
from PySide6.QtWidgets import QApplication                     # noqa: E402

from persian_ebook.gui import MainWindow                       # noqa: E402

# The window persists language and font through QSettings, and a test that
# toggles languages would otherwise overwrite the real user's preferences.
test_prefs = QSettings(
    str(Path(tempfile.mkdtemp(prefix="gui-smoke-")) / "prefs.ini"),
    QSettings.IniFormat)

sample = Path(sys.argv[1]) if len(sys.argv) > 1 else None
app = QApplication([])
win = MainWindow(settings=test_prefs)

assert win.font_combo.count() >= 1, "font combo did not populate"
print(f"  pass  fonts listed ({win.font_combo.count() - 1} families)")
assert not win.go.isEnabled(), "convert button enabled with an empty list"
print("  pass  convert disabled with nothing to do")

win.set_language("en")
assert win.go.text() == "Convert to EPUB", win.go.text()
assert win.lang_en.isChecked()
print("  pass  english interface")
win.set_language("fa")
assert win.lang_fa.isChecked()
print("  pass  persian interface")

if sample:
    assert sample.exists(), f"no such file: {sample}"
    win.pages.setValue(6)
    win.list.add_paths([sample])
    win._refresh()
    assert win.go.isEnabled(), "convert button stayed disabled after a drop"
    print("  pass  convert enabled once a file is listed")

    seen = {"progress": 0, "done": None, "failed": None}

    def watch_progress(frac, msg):
        seen["progress"] += 1

    win.start()
    win.thread.progress.connect(watch_progress)
    win.thread.item_done.connect(lambda r: seen.update(done=r))
    win.thread.item_failed.connect(lambda n, m: seen.update(failed=(n, m)))

    timed_out = QTimer()
    timed_out.setSingleShot(True)
    timed_out.timeout.connect(lambda: (seen.update(timed_out=True), app.quit()))
    timed_out.start(120_000)
    win.thread.finished.connect(app.quit)
    app.exec()
    assert not seen.get("timed_out"), "conversion never finished"

    assert seen["failed"] is None, f"conversion failed: {seen['failed']}"
    assert seen["done"] is not None, "no result was emitted"
    assert seen["progress"] > 3, f"progress fired only {seen['progress']} times"
    result = seen["done"]
    assert result.epub_path.exists(), "epub was not written"
    assert win.reveal_btn.isEnabled(), "reveal button not enabled after success"
    assert win.bar.value() == 1000, f"progress bar ended at {win.bar.value()}"
    print(f"  pass  converted {result.epub_path.name}: "
          f"{result.pages_read} pages, {result.blocks} blocks, "
          f"{result.headings} headings, font {result.font or 'default'}")
    print(f"  pass  progress fired {seen['progress']} times, bar reached 100%")
    print(f"  pass  status line: {win.status.text()[:90]}")

print()
print("all passed")
