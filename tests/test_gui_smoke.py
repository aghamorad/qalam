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

    state = {"timed_out": False}
    win.start()

    # Poll the window-owned thread instead of attaching test-only signals after
    # start(). A tiny fixture can finish before a late signal connection lands.
    poll = QTimer()
    poll.setInterval(25)
    poll.timeout.connect(lambda: app.quit() if win.thread is None else None)
    poll.start()

    timed_out = QTimer()
    timed_out.setSingleShot(True)
    timed_out.timeout.connect(
        lambda: (state.update(timed_out=True), app.quit()))
    timed_out.start(120_000)

    app.exec()
    assert not state["timed_out"], "conversion never finished"
    assert win.last_output is not None, f"conversion failed: {win.status.text()}"
    assert win.last_output.exists(), "epub was not written"
    assert win.reveal_btn.isEnabled(), "reveal button not enabled after success"
    assert win.bar.value() == 1000, f"progress bar ended at {win.bar.value()}"
    print(f"  pass  converted {win.last_output.name}")
    print("  pass  progress bar reached 100%")
    print(f"  pass  status line: {win.status.text()[:90]}")

print()
print("all passed")
