from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import Qt, QThread, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from .. import CREATED_BY, __version__
from ..core.engine import ExtractionService, managed_tessdata_dir
from ..core.models import ExtractionOptions
from .icons import app_icon, make_icon
from .theme import ASSETS
from .worker import LanguageSetupWorker


class _DialogTitleBar(QFrame):
    """Small draggable title bar for frameless, shadow-free dialogs."""

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            window = self.window().windowHandle()
            if window is not None:
                window.startSystemMove()
                event.accept()
                return
        super().mousePressEvent(event)


class FlatDialog(QDialog):
    """A dialog without the native Windows frame/DWM drop shadow.

    We intentionally do not use WA_TranslucentBackground: on some Windows/Qt
    backends it produces black corners or a black halo. The dialog is opaque,
    bordered, draggable, and keeps normal modal/keyboard behavior.
    """

    def __init__(self, title: str, colors: dict, parent=None, min_width: int = 500):
        super().__init__(parent)
        self.colors = colors
        self.setObjectName("FlatDialog")
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setWindowTitle(title)
        self.setMinimumWidth(min_width)
        self._geometry_ready = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(1, 1, 1, 1)
        outer.setSpacing(0)
        # Let the dialog's minimum size follow the real content size. On Windows
        # this avoids frameless-window setGeometry warnings when the default
        # QDialog height is smaller than the wrapped content's minimum height.
        outer.setSizeConstraint(QVBoxLayout.SizeConstraint.SetMinimumSize)
        surface = QFrame()
        surface.setObjectName("DialogSurface")
        outer.addWidget(surface)
        surface_layout = QVBoxLayout(surface)
        surface_layout.setContentsMargins(0, 0, 0, 0)
        surface_layout.setSpacing(0)

        bar = _DialogTitleBar()
        bar.setObjectName("DialogTitleBar")
        bar.setFixedHeight(40)
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(12, 0, 8, 0)
        bar_layout.setSpacing(8)
        icon = QLabel()
        icon.setPixmap(app_icon().pixmap(18, 18))
        icon.setFixedSize(20, 20)
        bar_layout.addWidget(icon)
        caption = QLabel(title)
        caption.setObjectName("DialogTitle")
        bar_layout.addWidget(caption, 1)
        close = QPushButton()
        close.setObjectName("IconOnly")
        close.setFixedSize(28, 28)
        close.setIcon(make_icon("close", colors["muted"], 14))
        close.setToolTip("Close")
        close.clicked.connect(self.close)
        bar_layout.addWidget(close)
        surface_layout.addWidget(bar)

        self.body = QWidget()
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(24, 20, 24, 20)
        self.body_layout.setSpacing(14)
        surface_layout.addWidget(self.body, 1)

    def showEvent(self, event) -> None:
        if not self._geometry_ready:
            self._geometry_ready = True
            self.layout().activate()
            # Size to the wrapped content before the native window is shown,
            # instead of asking Windows for a too-short default QDialog height.
            self.adjustSize()
        super().showEvent(event)


class SetupDialog(FlatDialog):
    options_changed = Signal(object)

    def __init__(self, options: ExtractionOptions, colors: dict, parent=None):
        super().__init__("OCR setup", colors, parent, min_width=520)
        self.options = options
        self.thread: QThread | None = None
        self.worker: LanguageSetupWorker | None = None
        self._close_when_done = False
        layout = self.body_layout
        intro = QLabel("TX ships with local RapidOCR models for Persian/English artwork and complex layouts. Tesseract is optional and can improve clean scans; install it once, then add the English and Persian language packs.")
        intro.setObjectName("Muted")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self.status = QLabel("Checking your installation…")
        self.status.setWordWrap(True)
        self.status.setObjectName("InnerCard")
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.status)

        path_label = QLabel("Tesseract executable (leave empty for automatic detection)")
        path_label.setObjectName("Muted")
        row = QHBoxLayout()
        self.path_edit = QLineEdit(options.tesseract_path or "")
        self.path_edit.setPlaceholderText("Automatic")
        browse = QPushButton("Browse…")
        browse.clicked.connect(self.browse)
        row.addWidget(self.path_edit, 1)
        row.addWidget(browse)
        layout.addWidget(path_label)
        layout.addLayout(row)

        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.progress.hide()
        self.download_message = QLabel("")
        self.download_message.setObjectName("Muted")
        self.download_message.setWordWrap(True)
        self.download_message.hide()
        layout.addWidget(self.progress)
        layout.addWidget(self.download_message)

        buttons = QHBoxLayout()
        self.download_button = QPushButton("Download language packs · ~15 MB")
        self.download_button.setObjectName("Primary")
        self.download_button.setIcon(make_icon("save", colors["accent_text"], 18))
        self.download_button.clicked.connect(self.download)
        auto = QPushButton("Use automatic detection")
        auto.clicked.connect(self.use_auto)
        buttons.addWidget(self.download_button, 1)
        buttons.addWidget(auto)
        layout.addLayout(buttons)

        note = QLabel("Language packs are downloaded from the official tesseract-ocr/tessdata_fast repository and verified with SHA-256. Your documents are never uploaded.")
        note.setObjectName("Tiny")
        note.setWordWrap(True)
        layout.addWidget(note)

        bottom = QHBoxLayout()
        docs = QPushButton("Open Persian guide")
        docs.setObjectName("Ghost")
        docs.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(ASSETS.parent / "docs" / "راهنمای-فارسی.html"))))
        done = QPushButton("Done")
        done.clicked.connect(self.finish)
        bottom.addWidget(docs)
        bottom.addStretch(1)
        bottom.addWidget(done)
        layout.addLayout(bottom)
        QTimer.singleShot(50, self.refresh_status)

    def current_options(self) -> ExtractionOptions:
        path = self.path_edit.text().strip() or None
        return replace(self.options, tesseract_path=path)

    def refresh_status(self) -> None:
        try:
            info = ExtractionService(self.current_options()).diagnose()
            rapid = info.get("rapid", {})
            if rapid.get("available"):
                rapid_state = "ready"
            elif not rapid.get("models_present", True):
                rapid_state = "missing model files"
            elif not rapid.get("dependencies_present", True):
                rapid_state = "missing Python packages · pip install -r requirements.txt"
            elif info.get("engine") == "tesseract":
                rapid_state = "installed · Tesseract is the selected engine"
            else:
                rapid_state = "not ready"
            lines = [f"RapidOCR (bundled): {rapid_state}"]
            if info.get("tesseract"):
                langs = ", ".join(info.get("languages", [])) or "none"
                missing = info.get("missing", [])
                state = "ready" if not missing else f"missing: {', '.join(missing)}"
                lines.append(f"Tesseract: {state} · {info.get('version', '')}")
                lines.append(f"Languages: {langs}")
            else:
                lines.append("Tesseract: not found (optional)")
            if not info.get("available"):
                lines.append(info.get("reason") or "No OCR engine is ready.")
            self.status.setText("\n".join(lines))
        except Exception as exc:
            self.status.setText(f"Could not check OCR engines: {exc}")

    def browse(self) -> None:
        pattern = "Tesseract (tesseract.exe tesseract);;All files (*)"
        path, _ = QFileDialog.getOpenFileName(self, "Locate Tesseract", "", pattern)
        if path:
            self.path_edit.setText(path)
            self.refresh_status()

    def use_auto(self) -> None:
        self.path_edit.clear()
        self.options = replace(self.options, tesseract_path=None, tessdata_dir=None)
        self.refresh_status()

    def download(self) -> None:
        if self.thread is not None:
            return
        self.download_button.setEnabled(False)
        self.progress.show()
        self.download_message.show()
        self.progress.setValue(0)
        self.thread = QThread(self)
        self.worker = LanguageSetupWorker(managed_tessdata_dir())
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(self.on_download_progress)
        self.worker.finished.connect(self.on_download_finished)
        self.worker.failed.connect(self.on_download_failed)
        self.worker.finished.connect(self.thread.quit)
        self.worker.failed.connect(self.thread.quit)
        self.thread.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.finished.connect(self.on_thread_finished)
        self.thread.start()

    def on_download_progress(self, message: str, fraction: float) -> None:
        self.download_message.setText(message)
        self.progress.setValue(round(fraction * 1000))

    def on_download_finished(self, path: str) -> None:
        self.options = replace(self.current_options(), tessdata_dir=path)
        self.download_message.setText("Language packs installed. You're ready to extract text.")
        self.progress.setValue(1000)
        self.refresh_status()

    def on_download_failed(self, message: str) -> None:
        self.download_message.setText(message)
        self.progress.hide()

    def on_thread_finished(self) -> None:
        self.thread = None
        self.worker = None
        self.download_button.setEnabled(True)
        if self._close_when_done:
            self.accept()

    def finish(self) -> None:
        self.options_changed.emit(self.current_options())
        self.accept()

    def closeEvent(self, event) -> None:
        if self.thread is not None and self.worker is not None:
            self._close_when_done = True
            self.worker.cancel()
            self.download_message.setText("Cancelling the download before closing…")
            event.ignore()
            return
        super().closeEvent(event)


class HelpDialog(FlatDialog):
    def __init__(self, colors: dict, parent=None):
        super().__init__("About TX", colors, parent, min_width=520)
        self.setMinimumHeight(460)
        layout = self.body_layout
        title = QLabel("TX")
        title.setObjectName("H1")
        version = QLabel(f"Version {__version__} · Local image & PDF text extraction")
        version.setObjectName("Muted")
        created_by = QLabel(CREATED_BY)
        created_by.setObjectName("Badge")
        layout.addWidget(title)
        layout.addWidget(version)
        layout.addWidget(created_by)
        browser = QTextBrowser()
        browser.setOpenExternalLinks(True)
        browser.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        browser.setHtml(PERSIAN_HELP)
        layout.addWidget(browser, 1)
        row = QHBoxLayout()
        guide = QPushButton("Open the full Persian guide")
        guide.setObjectName("Primary")
        guide.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(ASSETS.parent / "docs" / "راهنمای-فارسی.html"))))
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        row.addWidget(guide)
        row.addStretch(1)
        row.addWidget(close)
        layout.addLayout(row)


PERSIAN_HELP = """
<div dir="rtl" style="font-family:'Vazirmatn'; font-size:14px; line-height:1.9;">
<h2>TX، بدون تایپ دوباره</h2>
<p>TX فایل تصویری یا PDF را می‌گیرد و نوشته‌های انگلیسی و فارسی آن را به متن قابل کپی تبدیل می‌کند. همهٔ پردازش‌ها روی همین کامپیوتر انجام می‌شود؛ فایل‌ها به جایی فرستاده نمی‌شوند.</p>
<p style="color:#68788A;">ساخته‌شده توسط Matt.</p>
<h3>شروع سریع</h3>
<ol>
<li>از بخش OCR setup، موتور Tesseract و بسته‌های زبانی را آماده کنید.</li>
<li>فایل‌ها را بکشید و رها کنید یا دکمهٔ Add files را بزنید.</li>
<li>زبان و کیفیت را انتخاب کنید و Extract text را بزنید.</li>
<li>متن را کپی کنید یا با پسوند .txt و رمزگذاری UTF-8 ذخیره کنید.</li>
</ol>
<h3>چند نکتهٔ صادقانه</h3>
<p>اگر PDF از قبل لایهٔ متن داشته باشد، همان متن خوانده می‌شود و نیازی به OCR نیست. صفحه‌های اسکن‌شده با OCR خوانده می‌شوند. برای صفحه‌های ترکیبی، متن اصلی و نتیجهٔ OCR با هم ادغام می‌شوند.</p>
<p>OCR صددرصد دقیق نیست. عکس تار، دست‌خط، جدول‌های پیچیده و فونت‌های خیلی ریز ممکن است خطا داشته باشند. نسخهٔ ۱٫۲ برای پوسترها و طرح‌های شلوغ از مدل‌های همراه RapidOCR استفاده می‌کند و برای اسکن‌های تمیز، در صورت نصب بودن، از Tesseract کمک می‌گیرد. گزینهٔ Persian spacing-aware enhancement فاصلهٔ واژه‌ها و نصف‌فاصله را حفظ می‌کند.</p>
<p>پنجره حالا واکنش‌گراست: در عرض کم، پنل‌ها زیر هم می‌آیند و تنظیمات اسکرول می‌شوند؛ دکمه‌ها هم می‌شکنند تا از کادر بیرون نزنند.</p>
<h3>میان‌برها</h3>
<p>Ctrl+O افزودن فایل · Ctrl+Enter شروع · Ctrl+F جست‌وجو · Ctrl+Shift+C کپیٔ متن · Ctrl+S ذخیره</p>
<p style="color:#68788A;">راهنمای کامل فارسی، راهنمای نصب ویندوز/مک/لینوکس و توضیح معماری برنامه در پوشهٔ docs همراه برنامه قرار دارد.</p>
</div>
"""
