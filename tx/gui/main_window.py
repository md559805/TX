from __future__ import annotations

import html
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QSettings, QThread, Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QKeySequence, QPixmap, QShortcut, QTextCursor, QTextDocument
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from PIL.ImageQt import ImageQt

from .. import APP_NAME, CREATED_BY, __version__
from ..core.engine import ExtractionService, file_kind, preview_document, supported_extensions
from ..core.models import DocumentResult, PageResult, PasswordRequest, results_to_text
from ..core.text import count_words
from .dialogs import HelpDialog, SetupDialog
from .icons import app_icon, make_icon
from .theme import ASSETS, add_card_shadow, apply_theme, set_surface
from .widgets import DropZone, EmptyState, FileList
from .worker import ExtractionWorker
from .flow import FlowLayout

COMMON_IMAGES = "*.png *.jpg *.jpeg *.tif *.tiff *.bmp *.webp *.gif *.heic *.heif *.avif *.jp2 *.ico *.psd *.tga *.pcx *.ppm *.pgm *.pnm *.qoi"


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = QSettings("TX", "TX")
        self.dark = self.settings.value("dark", False, type=bool)
        self.colors = apply_theme(QApplication.instance(), self.dark)
        self.options = self._load_options()
        self.results_by_path: dict[Path, DocumentResult] = {}
        self.run_paths: list[Path] = []
        self.session_passwords: dict[Path, str] = {}
        self.thread: QThread | None = None
        self.worker: ExtractionWorker | None = None
        self.running = False
        self.preview_path: Path | None = None
        self.preview_page = 1
        self.preview_total = 1
        self.preview_pixmap: QPixmap | None = None
        self.setWindowTitle(f"{APP_NAME} — Image & PDF to Text")
        self.setWindowIcon(app_icon())
        self.resize(1180, 780)
        self.setMinimumSize(720, 520)
        self.setAcceptDrops(True)
        self._build_ui()
        self._connect_shortcuts()
        self._restore_geometry()
        self._update_buttons()
        QTimer.singleShot(250, self._update_ocr_badge)

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        central = QWidget()
        central.setObjectName("AppRoot")
        self.setCentralWidget(central)
        self.root_layout = QVBoxLayout(central)
        self.root_layout.setContentsMargins(24, 20, 24, 12)
        self.root_layout.setSpacing(18)
        self.root_layout.addWidget(self._build_header())

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setHandleWidth(14)
        self.splitter.addWidget(self._build_left_panel())
        self.splitter.addWidget(self._build_right_panel())
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([360, 820])
        self.root_layout.addWidget(self.splitter, 1)

        self.status_label = QLabel("Ready. Add an image or a PDF to begin.")
        self.status_label.setObjectName("Muted")
        self.statusBar().addWidget(self.status_label, 1)
        privacy = QLabel("Local processing · No uploads")
        privacy.setObjectName("Tiny")
        self.statusBar().addPermanentWidget(privacy)
        self.statusBar().setSizeGripEnabled(True)
        self._apply_surface_colors()

    def _apply_surface_colors(self) -> None:
        """Keep every plain container/viewport on the active theme background.

        This is deliberately explicit: on Windows dark mode an unstyled Qt
        viewport can otherwise paint black behind the cards even when the QSS
        looks correct on Linux/macOS.
        """
        bg = self.colors["bg"]
        surface = self.colors["surface"]
        central = self.centralWidget()
        if central is not None:
            set_surface(central, bg)
        for name in ("left_panel", "scroll_body"):
            widget = getattr(self, name, None)
            if widget is not None:
                set_surface(widget, bg)
        if hasattr(self, "left_scroll"):
            set_surface(self.left_scroll.viewport(), bg)
        if hasattr(self, "file_list"):
            set_surface(self.file_list.container, surface)
            set_surface(self.file_list.scroll.viewport(), surface)
        # ``preview_page`` is the current page *number*; the preview container
        # widget must use a different attribute name.
        preview_widget = getattr(self, "preview_page_widget", None)
        if isinstance(preview_widget, QWidget):
            set_surface(preview_widget, surface)
        if hasattr(self, "preview_scroll"):
            set_surface(self.preview_scroll.viewport(), surface)

    def _build_header(self) -> QWidget:
        header = QWidget()
        self.header_layout = QHBoxLayout(header)
        self.header_layout.setContentsMargins(0, 0, 0, 0)
        self.header_layout.setSpacing(12)
        logo = QLabel()
        logo.setPixmap(app_icon().pixmap(42, 42))
        title_box = QVBoxLayout()
        title_box.setSpacing(0)
        title = QLabel("TX")
        title.setObjectName("H1")
        self.header_subtitle = QLabel("IMAGE & PDF → TEXT")
        self.header_subtitle.setObjectName("Tiny")
        created_by = QLabel(CREATED_BY)
        created_by.setObjectName("Tiny")
        title_box.addWidget(title)
        title_box.addWidget(self.header_subtitle)
        title_box.addWidget(created_by)
        self.header_layout.addWidget(logo)
        self.header_layout.addLayout(title_box)
        self.header_layout.addStretch(1)
        actions = QWidget()
        self.header_actions = FlowLayout(actions, margin=0, spacing=8)
        self.ocr_badge = QLabel("Checking OCR…")
        self.ocr_badge.setObjectName("Badge")
        self.header_actions.addWidget(self.ocr_badge)
        self.setup_button = QPushButton("OCR setup")
        self.setup_button.setIcon(make_icon("settings", self.colors["muted"], 17))
        self.setup_button.clicked.connect(self.open_setup)
        self.header_actions.addWidget(self.setup_button)
        self.theme_button = QPushButton()
        self.theme_button.setObjectName("IconOnly")
        self.theme_button.setFixedSize(36, 36)
        self.theme_button.setToolTip("Toggle light / dark theme")
        self.theme_button.clicked.connect(self.toggle_theme)
        self.header_actions.addWidget(self.theme_button)
        help_button = QPushButton()
        help_button.setObjectName("IconOnly")
        help_button.setFixedSize(36, 36)
        help_button.setIcon(make_icon("help", self.colors["muted"], 19))
        help_button.setToolTip("Help & about")
        help_button.clicked.connect(lambda: HelpDialog(self.colors, self).exec())
        self.header_actions.addWidget(help_button)
        self.header_layout.addWidget(actions)
        self._refresh_theme_icon()
        return header

    def _build_left_panel(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("LeftPanel")
        self.left_panel = panel
        panel.setMinimumWidth(0)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        self.left_scroll = QScrollArea()
        self.left_scroll.setObjectName("LeftScroll")
        self.left_scroll.setWidgetResizable(True)
        self.left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.left_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_body = QWidget()
        self.scroll_body.setObjectName("ScrollBody")
        scroll_layout = QVBoxLayout(self.scroll_body)
        scroll_layout.setContentsMargins(0, 0, 6, 0)
        scroll_layout.setSpacing(14)
        self.left_scroll.setWidget(self.scroll_body)
        layout.addWidget(self.left_scroll, 1)

        files_card = QFrame()
        files_card.setObjectName("Card")
        add_card_shadow(files_card, self.colors)
        card = QVBoxLayout(files_card)
        card.setContentsMargins(18, 18, 18, 18)
        card.setSpacing(12)
        heading = QHBoxLayout()
        label = QLabel("Source files")
        label.setObjectName("H2")
        self.count_badge = QLabel("0")
        self.count_badge.setObjectName("Badge")
        heading.addWidget(label)
        heading.addStretch(1)
        heading.addWidget(self.count_badge)
        card.addLayout(heading)
        self.drop_zone = DropZone(self.colors)
        self.drop_zone.clicked.connect(self.add_files)
        self.drop_zone.files_dropped.connect(self.add_paths)
        card.addWidget(self.drop_zone)
        buttons = QHBoxLayout()
        self.add_button = QPushButton("Add files")
        self.add_button.setIcon(make_icon("folder", self.colors["text"], 17))
        self.add_button.clicked.connect(self.add_files)
        self.clear_button = QPushButton("Clear")
        self.clear_button.setObjectName("Ghost")
        self.clear_button.clicked.connect(self.clear_files)
        buttons.addWidget(self.add_button, 1)
        buttons.addWidget(self.clear_button)
        card.addLayout(buttons)
        self.file_list = FileList(self.colors)
        self.file_list.files_changed.connect(self._on_files_changed)
        self.file_list.selection_changed.connect(self._on_selection_changed)
        card.addWidget(self.file_list, 1)
        scroll_layout.addWidget(files_card)

        settings_card = QFrame()
        settings_card.setObjectName("Card")
        add_card_shadow(settings_card, self.colors)
        settings_layout = QVBoxLayout(settings_card)
        settings_layout.setContentsMargins(18, 16, 18, 16)
        settings_layout.setSpacing(10)
        settings_title = QLabel("Extraction settings")
        settings_title.setObjectName("H2")
        settings_layout.addWidget(settings_title)
        engine_row = QHBoxLayout()
        engine_label = QLabel("Engine")
        engine_label.setObjectName("Muted")
        self.engine_combo = QComboBox()
        self.engine_combo.addItem("Auto · layout-aware", "auto")
        self.engine_combo.addItem("RapidOCR · posters & mixed", "rapid")
        self.engine_combo.addItem("Tesseract · clean scans", "tesseract")
        self.engine_combo.setCurrentIndex(max(0, self.engine_combo.findData(self.options.engine)))
        self.engine_combo.setToolTip("Auto uses the bundled RapidOCR models for complex designs and Tesseract for clean scans when available.")
        engine_row.addWidget(engine_label)
        engine_row.addWidget(self.engine_combo, 1)
        settings_layout.addLayout(engine_row)
        lang_row = QHBoxLayout()
        lang_label = QLabel("Language")
        lang_label.setObjectName("Muted")
        self.language_combo = QComboBox()
        self.language_combo.addItem("English + فارسی", ("eng", "fas"))
        self.language_combo.addItem("English only", ("eng",))
        self.language_combo.addItem("فارسی only", ("fas",))
        index = self.language_combo.findData(self.options.languages)
        self.language_combo.setCurrentIndex(max(0, index))
        lang_row.addWidget(lang_label)
        lang_row.addWidget(self.language_combo, 1)
        settings_layout.addLayout(lang_row)
        quality_row = QHBoxLayout()
        quality_label = QLabel("Quality")
        quality_label.setObjectName("Muted")
        self.quality_combo = QComboBox()
        self.quality_combo.addItem("Fast · 200 DPI", 200)
        self.quality_combo.addItem("Balanced · 300 DPI", 300)
        self.quality_combo.addItem("Fine · 400 DPI", 400)
        self.quality_combo.setCurrentIndex(max(0, self.quality_combo.findData(self.options.dpi)))
        quality_row.addWidget(quality_label)
        quality_row.addWidget(self.quality_combo, 1)
        settings_layout.addLayout(quality_row)
        self.smart_check = QCheckBox("Smart PDF text · use existing text first")
        self.smart_check.setChecked(self.options.smart_pdf)
        self.enhance_check = QCheckBox("Persian spacing-aware enhancement")
        self.enhance_check.setToolTip("Improves thin Persian strokes without closing word gaps, and rebuilds text from word boxes.")
        self.enhance_check.setChecked(self.options.enhance)
        self.orientation_check = QCheckBox("Detect page rotation")
        self.orientation_check.setChecked(self.options.detect_orientation)
        for widget in (self.smart_check, self.enhance_check, self.orientation_check):
            widget.setToolTip(widget.text())
            settings_layout.addWidget(widget)
        scroll_layout.addWidget(settings_card)
        scroll_layout.addStretch(1)

        self.start_button = QPushButton("Extract text")
        self.start_button.setObjectName("Primary")
        self.start_button.setMinimumHeight(48)
        self.start_button.setIcon(make_icon("play", self.colors["accent_text"], 18))
        self.start_button.clicked.connect(self.start_extraction)
        layout.addWidget(self.start_button)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setObjectName("Danger")
        self.cancel_button.setIcon(make_icon("stop", self.colors["danger"], 16))
        self.cancel_button.clicked.connect(self.cancel_extraction)
        self.cancel_button.hide()
        layout.addWidget(self.cancel_button)
        self.progress = _ProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setValue(0)
        self.progress.hide()
        layout.addWidget(self.progress)
        return panel

    def _build_right_panel(self) -> QWidget:
        card = QFrame()
        card.setObjectName("Card")
        add_card_shadow(card, self.colors)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)
        header = QHBoxLayout()
        tabs = QHBoxLayout()
        tabs.setSpacing(4)
        self.text_tab = QPushButton("Text")
        self.text_tab.setObjectName("Tab")
        self.text_tab.setCheckable(True)
        self.text_tab.setChecked(True)
        self.text_tab.setIcon(make_icon("text", self.colors["accent"], 16))
        self.preview_tab = QPushButton("Preview")
        self.preview_tab.setObjectName("Tab")
        self.preview_tab.setCheckable(True)
        self.preview_tab.setIcon(make_icon("eye", self.colors["muted"], 16))
        self.tab_group = QButtonGroup(self)
        self.tab_group.setExclusive(True)
        self.tab_group.addButton(self.text_tab)
        self.tab_group.addButton(self.preview_tab)
        self.text_tab.clicked.connect(lambda: self._switch_tab(False))
        self.preview_tab.clicked.connect(lambda: self._switch_tab(True))
        tabs.addWidget(self.text_tab)
        tabs.addWidget(self.preview_tab)
        header.addLayout(tabs)
        header.addStretch(1)
        self.stats_label = QLabel("No text yet")
        self.stats_label.setObjectName("Muted")
        header.addWidget(self.stats_label)
        layout.addLayout(header)

        toolbar_widget = QWidget()
        toolbar = FlowLayout(toolbar_widget, margin=0, spacing=8)
        self.copy_button = QPushButton("Copy text")
        self.copy_button.setIcon(make_icon("copy", self.colors["text"], 16))
        self.copy_button.clicked.connect(self.copy_text)
        self.save_button = QPushButton("Save .txt")
        self.save_button.setIcon(make_icon("save", self.colors["text"], 16))
        self.save_button.clicked.connect(self.save_text)
        self.find_button = QPushButton("Find")
        self.find_button.setIcon(make_icon("search", self.colors["text"], 16))
        self.find_button.clicked.connect(self.toggle_find)
        self.issues_button = QPushButton("View issues")
        self.issues_button.setObjectName("Ghost")
        self.issues_button.setIcon(make_icon("warning", self.colors["warning"], 16))
        self.issues_button.clicked.connect(self.show_issues)
        self.issues_button.hide()
        toolbar.addWidget(self.copy_button)
        toolbar.addWidget(self.save_button)
        toolbar.addWidget(self.find_button)
        toolbar.addWidget(self.issues_button)
        layout.addWidget(toolbar_widget)

        self.find_row = QWidget()
        find_layout = QHBoxLayout(self.find_row)
        find_layout.setContentsMargins(0, 0, 0, 0)
        self.find_edit = QLineEdit()
        self.find_edit.setPlaceholderText("Find in extracted text…")
        self.find_edit.returnPressed.connect(lambda: self.find_next(True))
        prev = QPushButton()
        prev.setObjectName("IconOnly")
        prev.setIcon(make_icon("left", self.colors["muted"], 16))
        prev.clicked.connect(lambda: self.find_next(False))
        nxt = QPushButton()
        nxt.setObjectName("IconOnly")
        nxt.setIcon(make_icon("right", self.colors["muted"], 16))
        nxt.clicked.connect(lambda: self.find_next(True))
        close = QPushButton()
        close.setObjectName("IconOnly")
        close.setIcon(make_icon("close", self.colors["muted"], 16))
        close.clicked.connect(self.toggle_find)
        find_layout.addWidget(self.find_edit, 1)
        find_layout.addWidget(prev)
        find_layout.addWidget(nxt)
        find_layout.addWidget(close)
        self.find_row.hide()
        layout.addWidget(self.find_row)

        self.stack = QStackedWidget()
        self.empty_state = EmptyState(self.colors)
        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setPlaceholderText("Extracted text will appear here.")
        self.text_edit.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.stack.addWidget(self.empty_state)
        self.stack.addWidget(self.text_edit)
        self.stack.addWidget(self._build_preview())
        layout.addWidget(self.stack, 1)
        self._switch_tab(False)
        return card

    def _build_preview(self) -> QWidget:
        page = QWidget()
        page.setObjectName("PreviewPage")
        # Do not name this ``preview_page``: that attribute stores the current
        # preview page number and is replaced by an int during navigation.
        self.preview_page_widget = page
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        self.preview_scroll = QScrollArea()
        self.preview_scroll.setObjectName("PreviewScroll")
        self.preview_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.preview_scroll.setWidgetResizable(True)
        self.preview_scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label = QLabel("Select a file to preview it")
        self.preview_label.setObjectName("Muted")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.preview_scroll.setWidget(self.preview_label)

        # File-level navigation: with several uploaded files, the preview must
        # be switchable without relying only on the left-hand file list.
        file_bar = QHBoxLayout()
        file_bar.setSpacing(6)
        self.prev_file = QPushButton()
        self.prev_file.setObjectName("IconOnly")
        self.prev_file.setFixedSize(32, 32)
        self.prev_file.setIcon(make_icon("left", self.colors["muted"], 17))
        self.prev_file.setToolTip("Previous file")
        self.prev_file.clicked.connect(lambda: self._change_preview_file(-1))
        self.preview_file_combo = QComboBox()
        self.preview_file_combo.setMinimumWidth(80)
        self.preview_file_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.preview_file_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.preview_file_combo.setMinimumContentsLength(8)
        self.preview_file_combo.setToolTip("Choose a file to preview")
        self.preview_file_combo.currentIndexChanged.connect(self._on_preview_file_combo)
        self.next_file = QPushButton()
        self.next_file.setObjectName("IconOnly")
        self.next_file.setFixedSize(32, 32)
        self.next_file.setIcon(make_icon("right", self.colors["muted"], 17))
        self.next_file.setToolTip("Next file")
        self.next_file.clicked.connect(lambda: self._change_preview_file(1))
        self.file_position = QLabel("0 / 0")
        self.file_position.setObjectName("Muted")
        file_bar.addWidget(self.prev_file)
        file_bar.addWidget(self.preview_file_combo, 1)
        file_bar.addWidget(self.next_file)
        file_bar.addWidget(self.file_position)
        layout.addLayout(file_bar)

        layout.addWidget(self.preview_scroll, 1)
        controls = QHBoxLayout()
        controls.addStretch(1)
        self.prev_page = QPushButton()
        self.prev_page.setObjectName("IconOnly")
        self.prev_page.setIcon(make_icon("left", self.colors["muted"], 17))
        self.prev_page.clicked.connect(lambda: self._change_preview_page(-1))
        self.page_spin = QSpinBox()
        self.page_spin.setMinimum(1)
        self.page_spin.setMaximum(1)
        self.page_spin.setFixedWidth(72)
        self.page_spin.setEnabled(False)
        self.page_spin.valueChanged.connect(self._on_page_spin)
        self.page_total = QLabel("/ 1")
        self.page_total.setObjectName("Muted")
        self.next_page = QPushButton()
        self.next_page.setObjectName("IconOnly")
        self.next_page.setIcon(make_icon("right", self.colors["muted"], 17))
        self.next_page.clicked.connect(lambda: self._change_preview_page(1))
        self.prev_page.setEnabled(False)
        self.next_page.setEnabled(False)
        controls.addWidget(self.prev_page)
        controls.addWidget(self.page_spin)
        controls.addWidget(self.page_total)
        controls.addWidget(self.next_page)
        controls.addStretch(1)
        layout.addLayout(controls)
        return page

    def _connect_shortcuts(self) -> None:
        QShortcut(QKeySequence("Ctrl+O"), self, activated=self.add_files)
        QShortcut(QKeySequence("Ctrl+Return"), self, activated=self.start_extraction)
        QShortcut(QKeySequence("Ctrl+Enter"), self, activated=self.start_extraction)
        QShortcut(QKeySequence("Ctrl+F"), self, activated=self.toggle_find)
        QShortcut(QKeySequence("Ctrl+Shift+C"), self, activated=self.copy_text)
        QShortcut(QKeySequence("Ctrl+S"), self, activated=self.save_text)

    # ------------------------------------------------------------- settings
    def _load_options(self):
        from ..core.models import ExtractionOptions

        languages = self.settings.value("languages", "eng+fas")
        if isinstance(languages, str):
            languages = tuple(x for x in languages.split("+") if x in ("eng", "fas"))
        return ExtractionOptions(
            languages=tuple(languages) or ("eng", "fas"),
            dpi=self.settings.value("dpi", 300, type=int),
            smart_pdf=self.settings.value("smart_pdf", True, type=bool),
            enhance=self.settings.value("enhance", True, type=bool),
            detect_orientation=self.settings.value("detect_orientation", True, type=bool),
            tesseract_path=self.settings.value("tesseract_path", "", type=str) or None,
            tessdata_dir=self.settings.value("tessdata_dir", "", type=str) or None,
            engine=self.settings.value("engine", "auto", type=str),
        )

    def _collect_options(self):
        return replace(
            self.options,
            languages=self.language_combo.currentData(),
            dpi=self.quality_combo.currentData(),
            smart_pdf=self.smart_check.isChecked(),
            enhance=self.enhance_check.isChecked(),
            detect_orientation=self.orientation_check.isChecked(),
            engine=self.engine_combo.currentData(),
        )

    def _save_settings(self) -> None:
        self.settings.setValue("dark", self.dark)
        self.settings.setValue("languages", "+".join(self.options.languages))
        self.settings.setValue("dpi", self.options.dpi)
        self.settings.setValue("smart_pdf", self.options.smart_pdf)
        self.settings.setValue("enhance", self.options.enhance)
        self.settings.setValue("detect_orientation", self.options.detect_orientation)
        self.settings.setValue("tesseract_path", self.options.tesseract_path or "")
        self.settings.setValue("tessdata_dir", self.options.tessdata_dir or "")
        self.settings.setValue("engine", self.options.engine)

    def _restore_geometry(self) -> None:
        geometry = self.settings.value("geometry")
        if geometry:
            self.restoreGeometry(geometry)
        state = self.settings.value("windowState")
        if state:
            self.restoreState(state)

    def toggle_theme(self) -> None:
        self.dark = not self.dark
        self.colors = apply_theme(QApplication.instance(), self.dark)
        self._apply_surface_colors()
        self._refresh_theme_icon()
        self.setup_button.setIcon(make_icon("settings", self.colors["muted"], 17))
        self._save_settings()

    def _refresh_theme_icon(self) -> None:
        self.theme_button.setIcon(make_icon("sun" if self.dark else "moon", self.colors["muted"], 19))

    def _update_ocr_badge(self) -> None:
        info = ExtractionService(self.options).diagnose()
        if info.get("available") and not info.get("missing"):
            self.ocr_badge.setText("OCR ready")
            self.ocr_badge.setToolTip(info.get("version", "Tesseract is ready"))
        else:
            self.ocr_badge.setText("OCR setup")
            self.ocr_badge.setToolTip(info.get("reason") or "Language packs are missing. Open OCR setup.")

    def open_setup(self) -> None:
        dialog = SetupDialog(self.options, self.colors, self)
        dialog.options_changed.connect(self._on_setup_changed)
        dialog.exec()
        self._update_ocr_badge()

    def _on_setup_changed(self, options) -> None:
        self.options = options
        self._save_settings()
        self._update_ocr_badge()

    # ---------------------------------------------------------------- files
    def add_files(self) -> None:
        supported = " ".join(f"*{ext}" for ext in sorted(supported_extensions()))
        selected, _ = QFileDialog.getOpenFileNames(
            self,
            "Add images or PDFs",
            "",
            f"All supported ({supported});;PDF documents (*.pdf);;Images ({COMMON_IMAGES});;All files (*)",
        )
        if selected:
            self.add_paths([Path(p) for p in selected])

    def add_paths(self, paths: list[Path]) -> None:
        valid: list[Path] = []
        skipped = 0
        for path in paths:
            try:
                if path.is_dir():
                    skipped += 1
                    continue
                file_kind(path)
                valid.append(path)
            except Exception:
                skipped += 1
        added = self.file_list.add_paths(valid)
        if skipped:
            self.status_label.setText(f"Added {added} file(s). Skipped {skipped} unsupported item(s) or folder(s).")
        elif added:
            self.status_label.setText(f"Added {added} file(s). Ready to extract.")
        self._update_buttons()

    def clear_files(self) -> None:
        if self.running:
            return
        self.file_list.clear()
        self.results_by_path.clear()
        self.preview_path = None
        self.preview_pixmap = None
        self.preview_label.setText("Select a file to preview it")
        self._refresh_results()
        self._update_buttons()
        self.status_label.setText("Cleared. Add an image or a PDF to begin.")

    def _on_files_changed(self) -> None:
        current = set(self.file_list.paths())
        for path in list(self.results_by_path):
            if path not in current:
                self.results_by_path.pop(path, None)
        self.count_badge.setText(str(len(current)))
        self._refresh_preview_file_list()
        self._update_buttons()
        self._refresh_results()

    def _on_selection_changed(self, path: Path | None) -> None:
        self.preview_path = path
        self.preview_page = 1
        self._refresh_preview_file_list()
        if path is None:
            self.preview_pixmap = None
            self.preview_label.setText("Select a file to preview it")
            self.page_spin.setMaximum(1)
            self.page_spin.setEnabled(False)
            self.page_total.setText("/ 1")
            self.prev_page.setEnabled(False)
            self.next_page.setEnabled(False)
            return
        self._load_preview()

    def _update_buttons(self) -> None:
        has_files = bool(self.file_list.paths())
        has_text = bool(self._ordered_results() and any(r.text for r in self._ordered_results()))
        self.start_button.setEnabled(has_files and not self.running)
        self.add_button.setEnabled(not self.running)
        self.clear_button.setEnabled(has_files and not self.running)
        self.drop_zone.setEnabled(not self.running)
        for widget in (self.engine_combo, self.language_combo, self.quality_combo, self.smart_check, self.enhance_check, self.orientation_check):
            widget.setEnabled(not self.running)
        self.copy_button.setEnabled(has_text and not self.running)
        self.save_button.setEnabled(has_text and not self.running)
        self.find_button.setEnabled(has_text)
        self.preview_tab.setEnabled(not self.running)
        self._refresh_preview_file_list()
        self.cancel_button.setVisible(self.running)
        self.progress.setVisible(self.running)
        self.start_button.setText("Working…" if self.running else "Extract text")

    # ----------------------------------------------------------- extraction
    def start_extraction(self) -> None:
        if self.running or not self.file_list.paths():
            return
        self.options = self._collect_options()
        self._save_settings()
        paths = self.file_list.paths()
        needs_ocr = any(file_kind(p) == "image" for p in paths) or not self.options.smart_pdf
        if needs_ocr:
            info = ExtractionService(self.options).diagnose()
            if not info.get("available") or info.get("missing"):
                QMessageBox.information(self, "OCR setup needed", "No OCR engine is ready. Reinstall TX to restore the bundled RapidOCR models, or install Tesseract and the selected language packs.")
                self.open_setup()
                return
        self.run_paths = paths
        for path in paths:
            self.results_by_path.pop(path, None)
            self.file_list.set_status(path, "queued")
        self.running = True
        self.progress.setValue(0)
        self._update_buttons()
        self._refresh_results()
        self.status_label.setText("Starting…")
        self.thread = QThread(self)
        self.worker = ExtractionWorker(paths, self.options)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.file_started.connect(self._on_file_started)
        self.worker.page_finished.connect(self._on_page_finished)
        self.worker.file_finished.connect(self._on_file_finished)
        self.worker.progress.connect(self._on_progress)
        self.worker.password_requested.connect(self._on_password_requested)
        self.worker.finished.connect(self._on_finished)
        self.worker.failed.connect(self._on_failed)
        self.worker.finished.connect(self.thread.quit)
        self.thread.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.finished.connect(self._on_thread_finished)
        self.thread.start()

    def cancel_extraction(self) -> None:
        if self.worker:
            self.worker.cancel()
            self.cancel_button.setEnabled(False)
            self.cancel_button.setText("Stopping…")
            self.status_label.setText("Cancelling after the current step…")

    def _on_file_started(self, index: int, path: str) -> None:
        self.file_list.set_status(Path(path), "reading", "Reading…")

    def _on_page_finished(self, index: int, page: PageResult) -> None:
        if index >= len(self.run_paths):
            return
        path = self.run_paths[index]
        result = self.results_by_path.setdefault(path, DocumentResult(path=path))
        result.pages = [p for p in result.pages if p.number != page.number] + [page]
        result.pages.sort(key=lambda p: p.number)
        self._refresh_results()

    def _on_file_finished(self, index: int, result: DocumentResult) -> None:
        self.results_by_path[result.path] = result
        if result.error:
            self.file_list.set_status(result.path, "error", "Could not read file")
        elif result.warnings:
            self.file_list.set_status(result.path, "warning", f"{len(result.pages)} page(s) · check issues")
        else:
            empty = sum(not p.text for p in result.pages)
            detail = f"{len(result.pages)} page(s)" + (f" · {empty} empty" if empty else "")
            self.file_list.set_status(result.path, "done", detail)
        self._refresh_results()

    def _on_progress(self, fraction: float, message: str) -> None:
        self.progress.setValue(round(max(0, min(1, fraction)) * 1000))
        self.status_label.setText(message)

    def _on_password_requested(self, request: PasswordRequest) -> None:
        password, ok = QInputDialog.getText(
            self,
            "PDF password",
            f"Enter the password for:\n{request.path.name}",
            QLineEdit.EchoMode.Password,
        )
        if ok:
            self.session_passwords[request.path] = password
            request.password = password
        else:
            request.password = None
        request.ready.set()
        if self.preview_path == request.path and ok:
            self._load_preview()

    def _on_finished(self, results: list, cancelled: bool) -> None:
        self.running = False
        self.cancel_button.setEnabled(True)
        self.cancel_button.setText("Cancel")
        self._update_buttons()
        self._refresh_results()
        ordered = self._ordered_results()
        if cancelled:
            self.status_label.setText("Cancelled. Completed files are kept.")
        else:
            warnings = sum(len(r.warnings) for r in ordered)
            pages = sum(len(r.pages) for r in ordered)
            self.status_label.setText(f"Done · {len(ordered)} file(s), {pages} page(s)" + (f" · {warnings} issue(s)" if warnings else ""))
        if not self.text_tab.isChecked() and ordered:
            pass
        self._update_ocr_badge()

    def _on_failed(self, message: str) -> None:
        self.running = False
        self._update_buttons()
        QMessageBox.critical(self, "Extraction failed", message)
        self.status_label.setText("Extraction failed.")

    def _on_thread_finished(self) -> None:
        self.thread = None
        self.worker = None

    # -------------------------------------------------------------- results
    def _ordered_results(self) -> list[DocumentResult]:
        return [self.results_by_path[p] for p in self.file_list.paths() if p in self.results_by_path]

    def _refresh_results(self) -> None:
        results = self._ordered_results()
        text = results_to_text(results, labels=False)
        pages = sum(len(r.pages) for r in results)
        words = count_words(text)
        if text:
            self.stats_label.setText(f"{len(results)} file(s) · {pages} page(s) · {words:,} words · {len(text):,} characters")
            self.text_edit.setHtml(self._results_html(results))
        else:
            self.stats_label.setText("No text yet")
            self.text_edit.clear()
            if self.file_list.paths():
                self.empty_state.set_message("Ready when you are.", "Press Extract text to read your files.\nYou can follow the progress on the left.")
            else:
                self.empty_state.set_message("Drop a file. Keep the words.", "Images and PDFs · English + فارسی\nProcessed on your device, not in the cloud.")
        warnings = [w for r in results for w in r.warnings]
        self.issues_button.setVisible(bool(warnings))
        self.issues_button.setText(f"View issues · {len(warnings)}")
        self._update_buttons()
        self._switch_tab(self.preview_tab.isChecked())

    def _results_html(self, results: list[DocumentResult]) -> str:
        multiple = len(results) > 1
        parts = [
            "<style>",
            "body { font-family:'Vazirmatn'; font-size:14px; }",
            f".meta {{ color:{self.colors['muted']}; font-size:11px; margin:14px 0 6px 0; }}",
            "p { margin:0 0 9px 0; }",
            "</style>",
        ]
        method_names = {"native": "PDF text", "ocr": "OCR", "native+ocr": "PDF text + OCR", "empty": "No text found"}
        for result in results:
            for page in result.pages:
                if not page.text:
                    continue
                if multiple or len(result.pages) > 1:
                    title = html.escape(result.path.name)
                    if len(result.pages) > 1:
                        title += f" · page {page.number}"
                    title += f" · {method_names.get(page.method, page.method)}"
                    parts.append(f'<div class="meta">{title}</div>')
                for paragraph in page.text.split("\n\n"):
                    escaped = html.escape(paragraph).replace("\n", "<br>")
                    parts.append(f'<p dir="auto">{escaped}</p>')
        return "".join(parts)

    def copy_text(self) -> None:
        text = results_to_text(self._ordered_results(), labels=False)
        if not text:
            return
        QApplication.clipboard().setText(text)
        self.status_label.setText("Copied to clipboard.")

    def save_text(self) -> None:
        results = self._ordered_results()
        text = results_to_text(results, labels=True)
        if not text:
            return
        default = (results[0].path.stem + "-text.txt") if len(results) == 1 else "tx-extracted-text.txt"
        path, _ = QFileDialog.getSaveFileName(self, "Save extracted text", default, "Text files (*.txt)")
        if not path:
            return
        try:
            Path(path).write_text(text, encoding="utf-8")
            self.status_label.setText(f"Saved {Path(path).name}")
        except OSError as exc:
            QMessageBox.critical(self, "Save failed", str(exc))

    def show_issues(self) -> None:
        messages = []
        for result in self._ordered_results():
            for warning in result.warnings:
                messages.append(f"{result.path.name}\n{warning}")
        if messages:
            QMessageBox.warning(self, "Extraction issues", "\n\n".join(messages))

    def toggle_find(self) -> None:
        visible = not self.find_row.isVisible()
        self.find_row.setVisible(visible)
        if visible:
            self.find_edit.setFocus()
            self.find_edit.selectAll()
        else:
            cursor = self.text_edit.textCursor()
            cursor.clearSelection()
            self.text_edit.setTextCursor(cursor)

    def find_next(self, forward: bool = True) -> None:
        query = self.find_edit.text()
        if not query:
            return
        flags = QTextDocument.FindFlag(0) if forward else QTextDocument.FindFlag.FindBackward
        if not self.text_edit.find(query, flags):
            cursor = self.text_edit.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End if forward else QTextCursor.MoveOperation.Start)
            self.text_edit.setTextCursor(cursor)
            if not self.text_edit.find(query, flags):
                self.status_label.setText(f"No matches for “{query}”.")

    # -------------------------------------------------------------- preview
    def _refresh_preview_file_list(self) -> None:
        """Keep the preview file chooser in sync with the uploaded file list."""
        if not hasattr(self, "preview_file_combo"):
            return
        paths = self.file_list.paths()
        combo = self.preview_file_combo
        combo.blockSignals(True)
        combo.clear()
        for path in paths:
            combo.addItem(path.name, path)
        if paths:
            current = self.preview_path if self.preview_path in paths else self.file_list.selected
            if current not in paths:
                current = paths[0]
            combo.setCurrentIndex(paths.index(current))
            combo.setEnabled(not self.running)
            index = combo.currentIndex()
            self.file_position.setText(f"{index + 1} / {len(paths)}")
            self.prev_file.setEnabled(not self.running and index > 0)
            self.next_file.setEnabled(not self.running and index < len(paths) - 1)
        else:
            combo.addItem("No files", None)
            combo.setCurrentIndex(0)
            combo.setEnabled(False)
            self.file_position.setText("0 / 0")
            self.prev_file.setEnabled(False)
            self.next_file.setEnabled(False)
        combo.blockSignals(False)

    def _on_preview_file_combo(self, index: int) -> None:
        if index < 0:
            return
        path = self.preview_file_combo.itemData(index)
        if isinstance(path, Path) and path in self.file_list.rows:
            # Selecting from the preview chooser also highlights the file on the
            # left and loads its first page through the normal selection path.
            self.file_list.select(path)

    def _change_preview_file(self, delta: int) -> None:
        paths = self.file_list.paths()
        if not paths:
            return
        current = self.preview_path if self.preview_path in paths else self.file_list.selected
        index = paths.index(current) if current in paths else 0
        new_index = index + delta
        if 0 <= new_index < len(paths):
            self.file_list.select(paths[new_index])

    def _switch_tab(self, preview: bool) -> None:
        self.preview_tab.setChecked(preview)
        self.text_tab.setChecked(not preview)
        if preview:
            self.stack.setCurrentIndex(2)
            self._refresh_preview_file_list()
            if self.preview_path:
                self._load_preview()
            else:
                self.preview_label.setText("Select a file to preview it")
        else:
            has_text = any(r.text for r in self._ordered_results())
            self.stack.setCurrentIndex(1 if has_text else 0)
        QTimer.singleShot(0, self._scale_preview)

    def _load_preview(self) -> None:
        if not self.preview_path:
            return
        if self.running:
            self.preview_pixmap = None
            self.preview_label.setText("Preview pauses while extraction is running.")
            self.page_spin.setEnabled(False)
            self.prev_page.setEnabled(False)
            self.next_page.setEnabled(False)
            return
        try:
            image, total = preview_document(self.preview_path, self.preview_page, self.session_passwords.get(self.preview_path))
            self.preview_total = total
            self.preview_pixmap = QPixmap.fromImage(ImageQt(image))
            self.page_spin.blockSignals(True)
            self.page_spin.setMaximum(max(1, total))
            self.page_spin.setValue(self.preview_page)
            self.page_spin.blockSignals(False)
            self.page_spin.setEnabled(total > 1)
            self.page_total.setText(f"/ {total}")
            self.prev_page.setEnabled(self.preview_page > 1)
            self.next_page.setEnabled(self.preview_page < total)
            self._scale_preview()
        except Exception as exc:
            self.preview_pixmap = None
            message = str(exc)
            if "password" in message.lower():
                message = "Password-protected PDF.\nStart extraction to enter the password, then preview it here."
            self.preview_label.setText(f"Preview unavailable\n{message}")
            self.page_spin.setMaximum(1)
            self.page_spin.setEnabled(False)
            self.page_total.setText("/ 1")
            self.prev_page.setEnabled(False)
            self.next_page.setEnabled(False)

    def _scale_preview(self) -> None:
        if self.preview_pixmap is None:
            return
        viewport = self.preview_scroll.viewport().size()
        scaled = self.preview_pixmap.scaled(
            max(100, viewport.width() - 24), max(100, viewport.height() - 24),
            Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation,
        )
        self.preview_label.setPixmap(scaled)

    def _change_preview_page(self, delta: int) -> None:
        new = self.preview_page + delta
        if 1 <= new <= self.preview_total:
            self.preview_page = new
            self._load_preview()

    def _on_page_spin(self, value: int) -> None:
        if value != self.preview_page:
            self.preview_page = value
            self._load_preview()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._apply_responsive_layout()
        QTimer.singleShot(0, self._scale_preview)

    def _apply_responsive_layout(self) -> None:
        width = self.width()
        narrow = width < 980
        compact = width < 760
        margins = (12, 12, 12, 8) if compact else ((16, 16, 16, 10) if narrow else (24, 20, 24, 12))
        self.root_layout.setContentsMargins(*margins)
        self.root_layout.setSpacing(10 if narrow else 18)
        self.header_subtitle.setVisible(not compact)
        self.setup_button.setText("Setup" if compact else "OCR setup")
        actions = self.header_actions.parentWidget()
        self.header_layout.setDirection(QHBoxLayout.Direction.LeftToRight)
        actions.setMinimumWidth(300 if compact else (250 if narrow else 320))
        actions.setMaximumWidth(420)
        if narrow:
            if self.splitter.orientation() != Qt.Orientation.Vertical:
                self.splitter.setOrientation(Qt.Orientation.Vertical)
            self.splitter.setSizes([max(220, int(self.height() * 0.48)), max(180, int(self.height() * 0.52))])
            self.left_scroll.setMinimumHeight(200)
            self.left_scroll.setMaximumHeight(420)
            self.splitter.widget(0).setMaximumWidth(16777215)
            self.splitter.widget(0).setMinimumWidth(0)
            self.splitter.widget(1).setMinimumHeight(160)
        else:
            if self.splitter.orientation() != Qt.Orientation.Horizontal:
                self.splitter.setOrientation(Qt.Orientation.Horizontal)
                self.splitter.setSizes([360, max(420, width - 420)])
            self.left_scroll.setMinimumHeight(0)
            self.left_scroll.setMaximumHeight(16777215)
            self.splitter.widget(0).setMinimumWidth(300)
            self.splitter.widget(0).setMaximumWidth(460)
            self.splitter.widget(1).setMinimumHeight(0)

    # --------------------------------------------------------------- events
    def dragEnterEvent(self, event) -> None:
        if not self.running and event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        if self.running:
            return
        paths = [Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()]
        if paths:
            self.add_paths(paths)
            event.acceptProposedAction()

    def closeEvent(self, event) -> None:
        if self.running:
            answer = QMessageBox.question(self, "Stop and exit?", "Extraction is still running. Stop it and exit?")
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            if self.worker:
                self.worker.cancel()
            if self.thread:
                self.thread.quit()
                self.thread.wait(5000)
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("windowState", self.saveState())
        self._save_settings()
        event.accept()


class _ProgressBar(QFrame):
    """Thin indeterminate-looking progress bar backed by QProgressBar semantics."""

    def __init__(self, parent=None):
        super().__init__(parent)
        from PySide6.QtWidgets import QProgressBar

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        layout.addWidget(self.bar)

    def setRange(self, minimum: int, maximum: int) -> None:
        self.bar.setRange(minimum, maximum)

    def setValue(self, value: int) -> None:
        self.bar.setValue(value)
