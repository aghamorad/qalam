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

from persian_ebook import __version__                           # noqa: E402
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
assert win.go.text() == "Convert", win.go.text()
assert win.lang_en.isChecked()
assert [win.format_combo.itemData(i) for i in range(win.format_combo.count())] == [
    "epub", "mobi", "both"
]
print("  pass  english interface and output format choices")
win.set_language("fa")
assert win.lang_fa.isChecked()
print("  pass  persian interface")

# The version stamp, in both of its states. The window never asks GitHub in a
# test - that only happens from main() - so the answer is fed in directly.
assert win.version.text() == f"v{__version__}", win.version.text()
assert win.version.property("out") == "false"
assert win.checked is False, "window claimed to have checked without asking"
assert win.check is None, "a window built in a test started a network check"
print(f"  pass  version stamp reads {win.version.text()}")

win.outdated = "9.9.9"
win._paint_version()
assert win.version.property("out") == "true", "stamp did not turn"
assert "9.9.9" in win.version.text(), win.version.text()
win.set_language("en")
assert win.version.text() == "v9.9.9 IS OUT", win.version.text()
print(f"  pass  stale stamp reads {win.version.text()}")
win.outdated = ""
win._paint_version()
assert win.version.property("out") == "false"
win.set_language("fa")
print("  pass  stamp returns to plain")

# "no answer" and "you are current" are different answers, and only the second
# may claim to be the latest release.
win.set_language("en")
win.outdated, win.checked = "", False
assert "not been checked" in win._version_note(), win._version_note()
win.checked = True
assert "the latest release" in win._version_note(), win._version_note()
win.outdated = "9.9.9"
assert "A newer Qalam is out" in win._version_note(), win._version_note()
win.outdated, win.checked = "", False
win.set_language("fa")
print("  pass  about dialog tells the three version states apart")

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
    assert win.last_output.exists(), "output file was not written"
    assert win.reveal_btn.isEnabled(), "reveal button not enabled after success"
    assert win.bar.value() == 1000, f"progress bar ended at {win.bar.value()}"
    print(f"  pass  converted {win.last_output.name}")
    print("  pass  progress bar reached 100%")
    print(f"  pass  status line: {win.status.text()[:90]}")

print()
print("all passed")
