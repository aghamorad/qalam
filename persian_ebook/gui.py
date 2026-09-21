"""PySide6 front end: drop PDFs in, get EPUBs out.

    python -m persian_ebook.gui

Two languages, both first class. The interface ships Persian and English and
switches between them live, flipping the whole window's layout direction with
it - a Persian interface that runs left-to-right, or an English one running
right-to-left, is worse than either language on its own.

The window owns no conversion logic. Everything lives in convert.convert, which
this file calls on a worker thread - the same call the CLI makes - so the two
front ends cannot drift apart.
"""

import subprocess
import sys
import time
import traceback
from pathlib import Path

from PySide6.QtCore import QRectF, QSettings, Qt, QThread, QTimer, Signal
from PySide6.QtGui import (QColor, QFont, QFontDatabase, QIcon, QPainter,
                           QPalette, QPen, QPixmap)
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QComboBox, QFileDialog,
    QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget, QMainWindow,
    QMessageBox, QProgressBar, QPushButton, QRadioButton, QSizePolicy,
    QSplashScreen, QSpinBox, QVBoxLayout, QWidget,
)

from . import __version__

APP_NAME = "Qalam"
APP_REPO = "https://github.com/aghamorad/qalam"
DATA_DIR = Path(__file__).resolve().parent / "data"
ICON_PNG = DATA_DIR / "icon-1024.png"

# A splash that blinks past is worse than none; one that outstays its welcome is
# worse still. This is the floor, not the duration - font discovery across a
# few hundred families usually takes longer, and the splash is there so that
# wait has something on screen.
SPLASH_MIN = 1.6

from .convert import convert
from .fonts import BUNDLED_DIR, PERSIAN_PROBE, FontChoice, discover

PDF_FILTER_KEY = "PDF (*.pdf)"


STRINGS = {
    "fa": {
        "window": "قلم — فارسی به ایپاب",
        "tagline": "پی‌دی‌اف فارسی را به ایپاب راست‌به‌چپ تبدیل کنید",
        "subtitle": "قلم ایپاب استاندارد می‌سازد؛ آی‌پد و کوبو مستقیم بازش می‌کنند و «ارسال به کیندل» آن را برای کیندل تبدیل می‌کند.",
        "drop": "فایل‌های پی‌دی‌اف را اینجا رها کنید",
        "drop_sub": "یا از دکمهٔ «افزودن» استفاده کنید",
        "add": "افزودن…",
        "remove": "برداشتن",
        "clear": "خالی کردن",
        "settings": "تنظیمات خروجی",
        "format_l": "قالب خروجی",
        "format_epub": "EPUB",
        "format_mobi": "MOBI (KF8)",
        "format_both": "EPUB + MOBI",
        "format_note": "خروجی MOBI به calibre نیاز دارد و برای ارسال به کیندل توصیه نمی‌شود؛ EPUB را به Send to Kindle بدهید.",
        "title_l": "عنوان",
        "title_ph": "خالی بگذارید تا از خود فایل خوانده شود",
        "author_l": "نویسنده",
        "author_ph": "خالی بگذارید تا از خود فایل خوانده شود",
        "pages_l": "تعداد صفحه",
        "pages_all": "کتاب کامل",
        "pages_other": "صفحه‌های اول",
        "notes": "پانوشت‌ها بمانند",
        "preview": "فایل پیش‌نمایش HTML هم بساز",
        "font_l": "قلم متن",
        "font_auto": "خودکار — بهترین قلم موجود",
        "font_count": "{n} قلم روی این دستگاه پیدا شد.",
        "font_none": "هیچ قلم فارسی پیدا نشد؛ خواننده از قلم خودش استفاده می‌کند.",
        "font_pick": "به‌طور خودکار «{name}» انتخاب می‌شود.",
        "font_selected": "«{name}» انتخاب شده است.",
        "font_support": "پشتیبانی از {ok} نویسه از {total} نویسهٔ ویژهٔ فارسی.",
        "font_free": "اجازهٔ بازتوزیع دارد.",
        "font_paid": "مجوز بازتوزیع این قلم تأیید نشده؛ پیش از انتشار عمومی بررسی کنید.",
        "convert": "تبدیل",
        "convert_n": "تبدیل {n} فایل",
        "reveal": "نمایش خروجی",
        "ready": "آماده",
        "working": "شروع {n} فایل…",
        "result": "{name} — {pages} صفحه، {blocks} بلوک، {heads} سربخش، قلم {font}",
        "failed_item": "{name} — {message}",
        "all_ok": "{n} فایل تبدیل شد",
        "all_part": "{ok} فایل تبدیل شد، {failed} ناموفق",
        "close_q": "تبدیل در جریان است",
        "close_body": "یک تبدیل در جریان است. پنجره بسته شود؟",
        "bad_file": "فایل پیدا نشد: {path}",
        "about": "درباره",
        "credit": "ساختهٔ مراد",
        "about_body": (
            "<b>قلم {v}</b><br>"
            "تبدیل‌کنندهٔ پی‌دی‌اف فارسی به ایپاب.<br><br>"
            "پی‌دی‌اف‌های فارسی معمولاً چپ‌به‌راست حروف‌چینی شده‌اند و با "
            "قلمی نوشته شده‌اند که هیچ کتاب‌خوانی ندارد. قلم آن‌ها را "
            "راست‌به‌چپ می‌خواند، سربخش‌ها و پانوشت‌ها را نگه می‌دارد، یک "
            "قلم فارسی را داخل خودِ فایل جای می‌دهد و ایپاب ۳ می‌سازد؛ "
            "آی‌پد و کوبو آن را مستقیم باز می‌کنند؛ سرویس «ارسال به کیندل» "
            "ایپاب را برای کیندل تبدیل می‌کند.<br><br>"
            "تنها قالب خروجی ایپاب است. سرویس «ارسال به کیندل» خودش ایپاب را "
            "روی سرور تبدیل می‌کند، و کیندل هم MOBI و KFX را نمی‌پذیرد مگر "
            "جیلبریک شده باشد؛ پس ساختن‌شان فقط یک مرحلهٔ اضافه است.<br><br>"
            "<b>ساختهٔ مراد.</b>"
        ),
    },
    "en": {
        "window": "Qalam — Persian to EPUB",
        "tagline": "Turn Persian PDFs into right-to-left EPUBs",
        "subtitle": "Qalam writes standard EPUB 3 files. iPad and Kobo open them "
                    "directly; Send to Kindle accepts EPUB and converts it for Kindle.",
        "drop": "Drop Persian PDFs here",
        "drop_sub": "or use the Add button",
        "add": "Add…",
        "remove": "Remove",
        "clear": "Clear",
        "settings": "Output settings",
        "format_l": "Output format",
        "format_epub": "EPUB",
        "format_mobi": "MOBI (KF8)",
        "format_both": "EPUB + MOBI",
        "format_note": "MOBI requires calibre. For Send to Kindle, use EPUB instead; Amazon no longer accepts MOBI there.",
        "title_l": "Title",
        "title_ph": "Leave empty to read it from the file",
        "author_l": "Author",
        "author_ph": "Leave empty to read it from the file",
        "pages_l": "Pages",
        "pages_all": "Whole book",
        "pages_other": "First pages",
        "notes": "Keep footnotes",
        "preview": "Also write an HTML preview file",
        "font_l": "Body font",
        "font_auto": "Automatic — best installed font",
        "font_count": "{n} font families found on this machine.",
        "font_none": "No Persian font found; the reader will use its own.",
        "font_pick": "Picking “{name}” automatically.",
        "font_selected": "“{name}” selected.",
        "font_support": "{ok} of {total} Persian-specific characters supported.",
        "font_free": "Free to redistribute.",
        "font_paid": "Redistribution license not verified — check the font license "
                     "before publishing.",
        "convert": "Convert",
        "convert_n": "Convert {n} files",
        "reveal": "Show output",
        "ready": "Ready",
        "working": "Starting {n} files…",
        "result": "{name} — {pages} pages, {blocks} blocks, {heads} headings, "
                  "font {font}",
        "failed_item": "{name} — {message}",
        "all_ok": "{n} converted",
        "all_part": "{ok} converted, {failed} failed",
        "close_q": "Conversion running",
        "close_body": "A conversion is still running. Close the window anyway?",
        "bad_file": "No such file: {path}",
        "about": "About",
        "credit": "Made by Morad",
        "about_body": (
            "<b>Qalam {v}</b><br>"
            "A Persian PDF → EPUB converter.<br><br>"
            "Persian PDFs are usually typeset left-to-right, in fonts no "
            "e-reader owns. Qalam reads them right-to-left, keeps the "
            "headings and footnotes, embeds a Persian font inside the file, "
            "and writes a standard EPUB 3. iPad and Kobo open it directly; "
            "Send to Kindle accepts EPUB and converts it for Kindle.<br><br>"
            "EPUB is the only output on purpose. Send to Kindle converts an "
            "EPUB server-side already, and a Kindle will not take MOBI or KFX "
            "unless it has been jailbroken — so writing them would only add a "
            "step.<br><br>"
            "<b>Made by Morad.</b>"
        ),
    },
}

# Colour tokens, light and dark. One stylesheet is built from whichever the
# system is using; a single hard-coded palette looks broken in half the cases.
THEMES = {
    "light": {
        "bg": "#f4f5f7", "card": "#ffffff", "border": "#e2e5ea",
        "text": "#1b1e23", "muted": "#6b7280", "field": "#ffffff",
        "hover": "#eef1f5", "accent": "#2f6feb", "accent_hover": "#2459c4",
        "accent_text": "#ffffff", "ok": "#1a7f4b", "bad": "#c0392b",
        "chunk": "#2f6feb", "track": "#e6e9ee",
    },
    "dark": {
        "bg": "#16181c", "card": "#22252a", "border": "#343840",
        "text": "#e9ebee", "muted": "#969ba5", "field": "#1b1e22",
        "hover": "#2b2f35", "accent": "#5b8def", "accent_hover": "#729df3",
        "accent_text": "#0f1114", "ok": "#4fbf8b", "bad": "#e5736a",
        "chunk": "#5b8def", "track": "#2c3037",
    },
}

QSS = """
QWidget {{ color: {text}; }}
QMainWindow, #root {{ background: {bg}; }}
QLabel#tagline {{ font-size: 19px; font-weight: 600; }}
QLabel#subtitle, QLabel#muted, QLabel#hint {{ color: {muted}; }}
QLabel#hint {{ font-size: 13px; }}
QLabel#status {{ color: {muted}; }}
QFrame#card {{
    background: {card}; border: 1px solid {border}; border-radius: 12px;
}}
QFrame#dropzone {{
    background: {card}; border: 1px dashed {border}; border-radius: 12px;
}}
QListWidget {{
    background: transparent; border: none; outline: none;
    padding: 2px; font-size: 14px;
}}
QListWidget::item {{ padding: 7px 9px; border-radius: 7px; }}
QListWidget::item:hover {{ background: {hover}; }}
QListWidget::item:selected {{ background: {accent}; color: {accent_text}; }}
QLineEdit, QSpinBox, QComboBox {{
    background: {field}; border: 1px solid {border}; border-radius: 8px;
    padding: 7px 10px; min-height: 20px; font-size: 14px;
}}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{ border-color: {accent}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{
    background: {card}; border: 1px solid {border};
    selection-background-color: {accent}; selection-color: {accent_text};
}}
QPushButton {{
    background: {card}; border: 1px solid {border}; border-radius: 8px;
    padding: 8px 16px; font-size: 14px; min-height: 20px;
}}
QPushButton:hover {{ background: {hover}; }}
QPushButton:disabled {{ color: {muted}; border-color: {border}; }}
QPushButton#primary {{
    background: {accent}; border-color: {accent}; color: {accent_text};
    font-weight: 600; padding: 10px 26px;
}}
QPushButton#primary:hover {{ background: {accent_hover}; }}
QPushButton#primary:disabled {{
    background: {track}; border-color: {track}; color: {muted};
}}
QRadioButton, QCheckBox {{ font-size: 14px; padding: 2px 0; }}
QProgressBar {{
    background: {track}; border: none; border-radius: 3px;
    height: 6px; text-align: center;
}}
QProgressBar::chunk {{ background: {chunk}; border-radius: 3px; }}
"""


class DropList(QListWidget):
    """A file list you can drop PDFs onto."""

    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setFrameShape(QFrame.NoFrame)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        added = self.add_paths(
            Path(u.toLocalFile()) for u in event.mimeData().urls()
            if u.isLocalFile())
        event.acceptProposedAction()
        if added:
            self.changed.emit()

    def add_paths(self, paths) -> int:
        have = {self.item(i).text() for i in range(self.count())}
        added = 0
        for p in paths:
            if p.suffix.lower() != ".pdf" or str(p) in have:
                continue
            self.addItem(str(p))
            added += 1
        return added

    def paths(self) -> list[Path]:
        return [Path(self.item(i).text()) for i in range(self.count())]


class DropZone(QFrame):
    """The card around the file list, so a drop lands anywhere inside it.

    The list is hidden while it is empty - which is exactly when a drop is most
    likely - so the card has to be the target, not the list.
    """

    def __init__(self, list_widget: DropList, parent=None):
        super().__init__(parent)
        self.setObjectName("dropzone")
        self.list = list_widget
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        self.list.dragEnterEvent(event)

    def dragMoveEvent(self, event):
        self.list.dragMoveEvent(event)

    def dropEvent(self, event):
        self.list.dropEvent(event)


class Converter(QThread):
    """Runs the pipeline off the UI thread, one file at a time, in order."""

    progress = Signal(float, str)
    item_done = Signal(object)       # ConvertResult
    item_failed = Signal(str, str)   # filename, message
    all_done = Signal(int, int)      # ok, failed

    def __init__(self, jobs, settings, parent=None):
        super().__init__(parent)
        self.jobs = jobs
        self.settings = settings

    def run(self):
        ok = failed = 0
        for path in self.jobs:
            try:
                result = convert(
                    path,
                    title=self.settings["title"],
                    author=self.settings["author"],
                    font_name=self.settings["font"],
                    max_pages=self.settings["max_pages"],
                    keep_notes=self.settings["keep_notes"],
                    want_preview=self.settings["preview"],
                    output_format=self.settings["output_format"],
                    progress=lambda f, m, p=path:
                        self.progress.emit(f, f"{p.name} — {m}"),
                )
            except Exception as exc:                       # noqa: BLE001
                failed += 1
                self.item_failed.emit(path.name, str(exc))
                traceback.print_exc()
                continue
            ok += 1
            self.item_done.emit(result)
        self.all_done.emit(ok, failed)


class MainWindow(QMainWindow):
    def __init__(self, settings=None):
        super().__init__()
        # Injectable so a test can hand in a throwaway store instead of
        # overwriting the real preferences with its own language toggling.
        self.settings = settings or QSettings("persian-ebook", "persian-ebook")
        # English is the default because that is the language the app is
        # actually navigated in; Persian is one click away in the header.
        self.lang = self.settings.value("language", "en")
        if self.lang not in STRINGS:
            self.lang = "en"
        self.thread: Converter | None = None
        self.choices: list[FontChoice] = []
        self.last_output: Path | None = None
        self._done_count = 0
        self.total = 0
        self._build()
        self.apply_theme()
        self.retranslate()
        self.load_fonts()
        self.resize(760, 700)
        self.setMinimumWidth(600)

    def t(self, key, **kw) -> str:
        text = STRINGS[self.lang][key]
        return text.format(**kw) if kw else text

    # --- construction ----------------------------------------------------

    def _build(self):
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(24, 22, 24, 22)
        outer.setSpacing(14)

        outer.addLayout(self._header())
        outer.addWidget(self._drop_card(), 1)
        outer.addWidget(self._settings_card())
        outer.addWidget(self._footer())

    def _header(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(12)

        col = QVBoxLayout()
        col.setSpacing(3)
        self.tagline = QLabel()
        self.tagline.setObjectName("tagline")
        self.subtitle = QLabel()
        self.subtitle.setObjectName("subtitle")
        col.addWidget(self.tagline)
        col.addWidget(self.subtitle)
        row.addLayout(col)
        row.addStretch(1)

        self.lang_fa = QRadioButton("فارسی")
        self.lang_en = QRadioButton("English")
        (self.lang_fa if self.lang == "fa" else self.lang_en).setChecked(True)
        self.lang_fa.toggled.connect(lambda on: on and self.set_language("fa"))
        self.lang_en.toggled.connect(lambda on: on and self.set_language("en"))
        row.addWidget(self.lang_fa)
        row.addWidget(self.lang_en)
        return row

    def _drop_card(self) -> QFrame:
        self.list = DropList()
        self.list.changed.connect(self._refresh)
        card = DropZone(self.list)
        col = QVBoxLayout(card)
        col.setContentsMargins(14, 14, 14, 14)
        col.setSpacing(8)

        # Both occupy the same slot: only ever one of them is visible, and the
        # visible one gets the whole card, so the empty-state hint is centred
        # rather than pinned to the top of an otherwise blank box.
        self.drop_hint = QLabel()
        self.drop_hint.setObjectName("hint")
        self.drop_hint.setAlignment(Qt.AlignCenter)
        col.addWidget(self.drop_hint, 1)
        col.addWidget(self.list, 1)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        self.add_btn = QPushButton()
        self.add_btn.clicked.connect(self.browse)
        self.remove_btn = QPushButton()
        self.remove_btn.clicked.connect(self.remove_selected)
        self.clear_btn = QPushButton()
        self.clear_btn.clicked.connect(self.clear_list)
        for b in (self.add_btn, self.remove_btn, self.clear_btn):
            buttons.addWidget(b)
        buttons.addStretch(1)
        col.addLayout(buttons)
        return card

    def _settings_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        col = QVBoxLayout(card)
        col.setContentsMargins(16, 14, 16, 16)
        col.setSpacing(10)

        self.settings_title = QLabel()
        self.settings_title.setObjectName("muted")
        f = self.settings_title.font()
        f.setBold(True)
        self.settings_title.setFont(f)
        col.addWidget(self.settings_title)

        self.title_edit = QLineEdit()
        self.title_lbl = QLabel()
        col.addLayout(self._field(self.title_lbl, self.title_edit))

        self.author_edit = QLineEdit()
        self.author_lbl = QLabel()
        col.addLayout(self._field(self.author_lbl, self.author_edit))

        self.format_combo = QComboBox()
        self.format_combo.addItem("EPUB", "epub")
        self.format_combo.addItem("MOBI (KF8)", "mobi")
        self.format_combo.addItem("EPUB + MOBI", "both")
        saved_format = self.settings.value("output_format", "epub")
        fmt_index = self.format_combo.findData(saved_format)
        self.format_combo.setCurrentIndex(max(0, fmt_index))
        self.format_combo.currentIndexChanged.connect(
            lambda: self.settings.setValue(
                "output_format", self.format_combo.currentData()))
        self.format_lbl = QLabel()
        col.addLayout(self._field(self.format_lbl, self.format_combo))

        self.format_note = QLabel()
        self.format_note.setObjectName("hint")
        self.format_note.setWordWrap(True)
        col.addWidget(self.format_note)

        self.pages = QSpinBox()
        self.pages.setRange(0, 5000)
        self.pages.setValue(0)
        self.pages.setMinimumWidth(150)
        # The step buttons render as a stray empty box next to the "whole book"
        # text; the number is typed, not clicked.
        self.pages.setButtonSymbols(QSpinBox.NoButtons)
        self.pages_lbl = QLabel()
        row = QHBoxLayout()
        row.addWidget(self.pages_lbl)
        row.addWidget(self.pages)
        row.addStretch(1)
        col.addLayout(row)

        self.font_combo = QComboBox()
        self.font_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.font_combo.setMinimumWidth(280)
        self.font_combo.currentIndexChanged.connect(self._font_changed)
        self.font_lbl = QLabel()
        col.addLayout(self._field(self.font_lbl, self.font_combo))

        self.font_note = QLabel()
        self.font_note.setObjectName("hint")
        self.font_note.setWordWrap(True)
        col.addWidget(self.font_note)

        checks = QHBoxLayout()
        checks.setSpacing(18)
        self.notes = QCheckBox()
        self.notes.setChecked(True)
        self.preview = QCheckBox()
        self.preview.setChecked(True)
        checks.addWidget(self.notes)
        checks.addWidget(self.preview)
        checks.addStretch(1)
        col.addLayout(checks)
        return card

    @staticmethod
    def _field(label: QLabel, widget: QWidget) -> QHBoxLayout:
        label.setMinimumWidth(96)
        label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        row = QHBoxLayout()
        row.setSpacing(10)
        row.addWidget(label)
        row.addWidget(widget, 1)
        return row

    def _footer(self) -> QWidget:
        box = QWidget()
        col = QVBoxLayout(box)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(10)

        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        self.bar.setTextVisible(False)
        self.bar.setValue(0)
        self.bar.setVisible(False)
        col.addWidget(self.bar)

        row = QHBoxLayout()
        row.setSpacing(10)
        self.go = QPushButton()
        self.go.setObjectName("primary")
        self.go.setDefault(True)
        self.go.clicked.connect(self.start)
        self.reveal_btn = QPushButton()
        self.reveal_btn.setEnabled(False)
        self.reveal_btn.clicked.connect(self.reveal_output)
        self.about_btn = QPushButton()
        self.about_btn.setObjectName("ghost")
        self.about_btn.clicked.connect(self.show_about)
        row.addWidget(self.go)
        row.addWidget(self.reveal_btn)
        row.addStretch(1)
        row.addWidget(self.about_btn)
        col.addLayout(row)

        self.status = QLabel()
        self.status.setObjectName("status")
        self.status.setWordWrap(True)
        col.addWidget(self.status)
        return box

    # --- language and theme ----------------------------------------------

    def set_language(self, lang: str):
        if lang == self.lang or lang not in STRINGS:
            return
        self.lang = lang
        self.settings.setValue("language", lang)
        self.retranslate()

    def retranslate(self):
        rtl = self.lang == "fa"
        QApplication.instance().setLayoutDirection(
            Qt.RightToLeft if rtl else Qt.LeftToRight)

        (self.lang_fa if rtl else self.lang_en).setChecked(True)
        self.setWindowTitle(self.t("window"))
        self.tagline.setText(self.t("tagline"))
        self.subtitle.setText(self.t("subtitle"))
        self.add_btn.setText(self.t("add"))
        self.remove_btn.setText(self.t("remove"))
        self.clear_btn.setText(self.t("clear"))
        self.settings_title.setText(self.t("settings"))
        self.title_lbl.setText(self.t("title_l"))
        self.title_edit.setPlaceholderText(self.t("title_ph"))
        self.author_lbl.setText(self.t("author_l"))
        self.author_edit.setPlaceholderText(self.t("author_ph"))
        self.format_lbl.setText(self.t("format_l"))
        self.format_combo.setItemText(0, self.t("format_epub"))
        self.format_combo.setItemText(1, self.t("format_mobi"))
        self.format_combo.setItemText(2, self.t("format_both"))
        self.format_note.setText(self.t("format_note"))
        self.pages_lbl.setText(self.t("pages_l"))
        self.pages.setSpecialValueText(self.t("pages_all"))
        self.pages.setToolTip(self.t("pages_all"))
        self.notes.setText(self.t("notes"))
        self.preview.setText(self.t("preview"))
        self.font_lbl.setText(self.t("font_l"))
        self.font_combo.setItemText(0, self.t("font_auto"))
        self.go.setText(self.t("convert"))
        self.reveal_btn.setText(self.t("reveal"))
        self.about_btn.setText(self.t("about"))
        if not self.status.text() or self._is_default_status():
            self.status.setText(self.t("ready"))
        self._font_changed()
        self._refresh()

    def _is_default_status(self) -> bool:
        return any(self.status.text() == STRINGS[l]["ready"] for l in STRINGS)

    def apply_theme(self):
        dark = self.palette().color(QPalette.Window).lightness() < 128
        self.setStyleSheet(QSS.format(**THEMES["dark" if dark else "light"]))

    # --- fonts -----------------------------------------------------------

    def load_fonts(self):
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self.choices = discover()
        except Exception:                                  # noqa: BLE001
            self.choices = []
        finally:
            QApplication.restoreOverrideCursor()

        previous = self.settings.value("font", "")
        self.font_combo.blockSignals(True)
        self.font_combo.clear()
        self.font_combo.addItem(self.t("font_auto"), "")
        for c in self.choices:
            self.font_combo.addItem(c.label, c.family)
        index = self.font_combo.findData(previous)
        self.font_combo.setCurrentIndex(max(0, index))
        self.font_combo.blockSignals(False)
        self._font_changed()

    def _font_changed(self):
        name = self.font_combo.currentData()
        self.settings.setValue("font", name or "")
        if not self.choices:
            self.font_note.setText(self.t("font_none"))
            return
        choice = next((c for c in self.choices if c.family == name), None)
        if choice is None:
            choice = self.choices[0]
            head = self.t("font_pick", name=choice.family)
        else:
            head = self.t("font_selected", name=choice.family)
        share = self.t("font_free" if choice.redistributable else "font_paid")
        # One sentence per line: run together they read as a single wall of
        # qualifiers, which is how this note started out.
        self.font_note.setText("\n".join([
            head,
            self.t("font_count", n=len(self.choices)),
            self.t("font_support", ok=choice.persian_probe,
                   total=len(PERSIAN_PROBE)),
            share,
        ]))

    # --- list ------------------------------------------------------------

    def browse(self):
        start = self.settings.value("last_dir", str(Path.home()))
        names, _ = QFileDialog.getOpenFileNames(
            self, self.t("add"), start, PDF_FILTER_KEY)
        if names:
            self.settings.setValue("last_dir", str(Path(names[0]).parent))
            if self.list.add_paths(Path(n) for n in names):
                self._refresh()

    def remove_selected(self):
        for item in self.list.selectedItems():
            self.list.takeItem(self.list.row(item))
        self._refresh()

    def clear_list(self):
        self.list.clear()
        self._refresh()

    def _refresh(self):
        busy = self.thread is not None
        count = self.list.count()
        self.drop_hint.setText(f"{self.t('drop')}\n{self.t('drop_sub')}")
        self.drop_hint.setVisible(count == 0)
        self.list.setVisible(count > 0)
        self.go.setEnabled(not busy and count > 0)
        self.go.setText(self.t("convert") if count < 2
                        else self.t("convert_n", n=count))
        self.add_btn.setEnabled(not busy)
        self.remove_btn.setEnabled(not busy and count > 0)
        self.clear_btn.setEnabled(not busy and count > 0)

    # --- conversion ------------------------------------------------------

    def start(self):
        jobs = self.list.paths()
        if not jobs:
            return
        # A title and author describe one book. Applying them to a batch would
        # mislabel every file but the first, so they are only passed through
        # when there is exactly one.
        single = len(jobs) == 1
        settings = {
            "title": self.title_edit.text().strip() if single else "",
            "author": self.author_edit.text().strip() if single else "",
            "font": self.font_combo.currentData() or "",
            "max_pages": self.pages.value() or None,
            "keep_notes": self.notes.isChecked(),
            "preview": self.preview.isChecked(),
            "output_format": self.format_combo.currentData() or "epub",
        }
        self.last_output = None
        self._done_count = 0
        self.total = len(jobs)
        self.thread = Converter(jobs, settings)
        self.thread.progress.connect(self._on_progress)
        self.thread.item_done.connect(self._on_item)
        self.thread.item_failed.connect(self._on_fail)
        self.thread.all_done.connect(self._on_all_done)
        self.thread.finished.connect(self._on_thread_finished)
        self.bar.setValue(0)
        self.bar.setVisible(True)
        self.status.setStyleSheet("")
        self.status.setText(self.t("working", n=self.total))
        self._refresh()
        self.thread.start()

    def _on_progress(self, frac, msg):
        overall = (self._done_count + frac) / max(1, self.total)
        self.bar.setValue(int(overall * 1000))
        self.status.setText(msg)

    def _on_item(self, result):
        self._done_count += 1
        self.last_output = result.primary_path
        self.reveal_btn.setEnabled(self.last_output is not None)
        output_name = self.last_output.name if self.last_output else result.source.name
        line = self.t("result", name=output_name,
                      pages=result.pages_read, blocks=result.blocks,
                      heads=result.headings, font=result.font or "—")
        self.status.setText(line + ("" if not result.warnings
                                    else "  ·  " + "; ".join(result.warnings)))

    def show_about(self):
        box = QMessageBox(self)
        box.setWindowTitle(self.t("about"))
        box.setTextFormat(Qt.RichText)
        box.setText(self.t("about_body", v=__version__))
        box.setIconPixmap(icon_pixmap(96))
        box.setStandardButtons(QMessageBox.Close)
        box.exec()

    def _on_fail(self, name, message):
        self._done_count += 1
        self.status.setText(self.t("failed_item", name=name, message=message))

    def _on_all_done(self, ok, failed):
        self._done_count = 0
        self.bar.setValue(1000)
        self.status.setText(self.t("all_ok", n=ok) if not failed
                            else self.t("all_part", ok=ok, failed=failed))
        if failed:
            self.status.setStyleSheet(
                f"color: {THEMES['dark' if self._dark() else 'light']['bad']};")

    def _on_thread_finished(self):
        # Releasing the QThread here would delete it while it is still emitting
        # `finished`, which silently drops every later slot on that signal -
        # including any quit() a caller hooked up. Hand the release to the next
        # event-loop turn, once the emission is over.
        QTimer.singleShot(0, self._release_thread)

    def _release_thread(self):
        self.thread = None
        self._refresh()

    def _dark(self) -> bool:
        return self.palette().color(QPalette.Window).lightness() < 128

    # --- output ----------------------------------------------------------

    def reveal_output(self):
        if self.last_output:
            subprocess.run(["open", "-R", str(self.last_output)], check=False)

    def closeEvent(self, event):
        if self.thread is not None and self.thread.isRunning():
            answer = QMessageBox.question(
                self, self.t("close_q"), self.t("close_body"))
            if answer != QMessageBox.Yes:
                event.ignore()
                return
            self.thread.wait(2000)
        event.accept()


def register_bundled_fonts() -> list[str]:
    """Expose the shipped faces to Qt. Returns the family names it added.

    The font in `data/fonts` is what makes the window legible on a machine that
    has no Persian font installed at all - which is the machine this app is
    meant to be downloaded onto. Qt only sees a font file once it is added to
    its database, so the EPUB embedding and the UI need separate registration
    even though they read the same directory.
    """
    added: list[str] = []
    if not BUNDLED_DIR.is_dir():
        return added
    for path in sorted(BUNDLED_DIR.iterdir()):
        if path.suffix.lower() not in (".ttf", ".otf"):
            continue
        font_id = QFontDatabase.addApplicationFont(str(path))
        if font_id >= 0:
            added += QFontDatabase.applicationFontFamilies(font_id)
    return added


def icon_pixmap(size: int) -> QPixmap:
    if ICON_PNG.exists():
        pm = QPixmap(str(ICON_PNG))
        if not pm.isNull():
            return pm.scaled(size, size, Qt.KeepAspectRatio,
                             Qt.SmoothTransformation)
    return QPixmap()


def splash_pixmap(theme: str) -> QPixmap:
    """The launch card: name, what it does, and whose work it is.

    Both scripts are on it at once rather than following the saved language.
    The splash is painted before the window exists, so it has no way to know
    which language was chosen, and showing one of them at random would be
    wrong half the time.
    """
    tok = THEMES[theme]
    w, h = 560, 340
    pm = QPixmap(w, h)
    pm.fill(Qt.transparent)

    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setRenderHint(QPainter.SmoothPixmapTransform, True)
    p.setRenderHint(QPainter.TextAntialiasing, True)

    card = QRectF(6, 6, w - 12, h - 12)
    p.setPen(QPen(QColor(tok["border"]), 1.0))
    p.setBrush(QColor(tok["card"]))
    p.drawRoundedRect(card, 22, 22)

    art = icon_pixmap(150)
    if not art.isNull():
        p.drawPixmap(int((w - art.width()) / 2), 34, art)

    family = QApplication.instance().font().family()
    p.setPen(QColor(tok["text"]))
    p.setFont(QFont(family, 30, QFont.DemiBold))
    p.drawText(QRectF(0, 196, w, 44), int(Qt.AlignCenter), APP_NAME)
    p.setFont(QFont(family, 17))
    p.drawText(QRectF(0, 240, w, 28), int(Qt.AlignCenter), "قلم")

    p.setPen(QColor(tok["muted"]))
    p.setFont(QFont(family, 13))
    p.drawText(QRectF(0, 274, w, 22), int(Qt.AlignCenter),
               "Persian PDF → EPUB")
    p.setFont(QFont(family, 12))
    p.drawText(QRectF(0, 298, w, 20), int(Qt.AlignCenter),
               STRINGS["en"]["credit"] + "  ·  " + STRINGS["fa"]["credit"])
    p.end()
    return pm


class Splash(QSplashScreen):
    """A splash you can get rid of by clicking it."""

    def mousePressEvent(self, event):
        self.hide()
        event.accept()


def main(argv=None) -> int:
    app = QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName("qalam")
    app.setApplicationDisplayName(APP_NAME)
    app.setApplicationVersion(__version__)
    if ICON_PNG.exists():
        app.setWindowIcon(QIcon(str(ICON_PNG)))

    bundled = register_bundled_fonts()

    # Without a face that carries the Persian glyphs the window renders whole
    # rows of tofu, so this is a correctness step, not a cosmetic one. IRANSans
    # leads because his machine has it, but the bundled family is now
    # guaranteed present, so the list no longer ends in tofu on a clean install.
    for family in ("IRANSans", *bundled, "Vazirmatn", "Sahel", "Shabnam",
                   "Tahoma"):
        f = QFont(family, 13)
        if f.exactMatch() or family == "Tahoma":
            app.setFont(f)
            break

    # The window is not cheap to build - it walks the font book to find every
    # family that can set Persian - so the splash goes up first and stays for
    # at least SPLASH_MIN, whichever is longer.
    theme = "dark" if app.palette().color(QPalette.Window).lightness() < 128 \
        else "light"
    splash = Splash(splash_pixmap(theme))
    splash.show()
    app.processEvents()

    started = time.monotonic()
    win = MainWindow()
    win.show()
    win.raise_()
    win.activateWindow()

    dwell = max(0, int((SPLASH_MIN - (time.monotonic() - started)) * 1000))
    QTimer.singleShot(dwell, lambda: splash.finish(win))
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
