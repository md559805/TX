from __future__ import annotations

from pathlib import Path
from string import Template

from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette
from PySide6.QtWidgets import QApplication, QWidget

ASSETS = Path(__file__).resolve().parents[1] / "assets"

LIGHT = {
    "bg": "#F3F5F7", "surface": "#FFFFFF", "surface2": "#F7F9FB",
    "border": "#E3E8EE", "text": "#17212B", "muted": "#68788A",
    "accent": "#0E7C66", "accent_hover": "#0A6957", "accent_text": "#FFFFFF",
    "soft": "#E7F4F0", "soft_border": "#BFE2D7", "danger": "#B42318",
    "warning": "#B54708", "shadow": "#1014202C",
}
DARK = {
    "bg": "#0F1419", "surface": "#171E25", "surface2": "#1D262F",
    "border": "#2A3540", "text": "#E8EEF4", "muted": "#94A4B4",
    "accent": "#31BE9F", "accent_hover": "#45D0B2", "accent_text": "#06231D",
    "soft": "#12352E", "soft_border": "#1F5A4C", "danger": "#F97066",
    "warning": "#FDB022", "shadow": "#3C000000",
}

_QSS = Template("""
* { font-family: "Vazirmatn", "Segoe UI", "DejaVu Sans", sans-serif; }
QMainWindow, QDialog { background: $bg; }
QWidget { color: $text; font-size: 13px; }
QWidget#AppRoot, QWidget#LeftPanel, QWidget#ScrollBody { background: $bg; }
QScrollArea#LeftScroll { background: $bg; }
QScrollArea#FileListScroll, QWidget#FileListContainer { background: $surface; }
QScrollArea#PreviewScroll, QWidget#PreviewPage { background: $surface; }
QDialog#FlatDialog { background: $bg; }
QFrame#DialogSurface { background: $bg; border: 1px solid $border; }
QFrame#DialogTitleBar { background: $surface2; border-bottom: 1px solid $border; }
QLabel#DialogTitle { font-weight: 600; }
QLabel { background: transparent; }
QLabel#H1 { font-size: 23px; font-weight: 700; letter-spacing: -0.5px; }
QLabel#H2 { font-size: 15px; font-weight: 600; }
QLabel#Muted { color: $muted; font-size: 12px; }
QLabel#Tiny { color: $muted; font-size: 11px; }
QLabel#Badge { background: $soft; color: $accent; border-radius: 10px; padding: 3px 9px; font-size: 11px; font-weight: 600; }
QLabel#Warning { color: $warning; font-size: 12px; }
QFrame#Card { background: $surface; border: 1px solid $border; border-radius: 16px; }
QFrame#InnerCard { background: $surface2; border: 1px solid $border; border-radius: 12px; }
QLabel#InnerCard { background: $surface2; border: 1px solid $border; border-radius: 12px; padding: 12px 14px; }
QFrame#DropZone { background: $surface2; border: 1.5px dashed $border; border-radius: 14px; }
QFrame#DropZone[active="true"] { background: $soft; border-color: $accent; }
QFrame#FileRow { background: transparent; border: 1px solid transparent; border-radius: 12px; }
QFrame#FileRow:hover { background: $surface2; }
QFrame#FileRow[selected="true"] { background: $soft; border-color: $soft_border; }
QFrame#Divider { background: $border; max-height: 1px; border: none; }
QPushButton {
    background: $surface; color: $text; border: 1px solid $border;
    border-radius: 9px; padding: 7px 14px; font-weight: 500; min-height: 20px;
}
QPushButton:hover { background: $surface2; border-color: $muted; }
QPushButton:pressed { background: $border; }
QPushButton:disabled { color: $muted; background: $surface2; border-color: $border; }
QPushButton#Primary { background: $accent; color: $accent_text; border: none; font-weight: 600; font-size: 14px; min-height: 30px; }
QPushButton#Primary:hover { background: $accent_hover; }
QPushButton#Primary:disabled { background: $border; color: $muted; }
QPushButton#Ghost { background: transparent; border: none; color: $muted; padding: 6px 9px; }
QPushButton#Ghost:hover { background: $surface2; color: $text; }
QPushButton#Danger { color: $danger; }
QPushButton#Tab { background: transparent; border: none; border-radius: 8px; color: $muted; padding: 7px 16px; font-weight: 600; }
QPushButton#Tab:hover { color: $text; background: $surface2; }
QPushButton#Tab:checked { background: $soft; color: $accent; }
QPushButton#IconOnly { background: transparent; border: none; border-radius: 8px; padding: 6px; }
QPushButton#IconOnly:hover { background: $surface2; }
QLineEdit, QComboBox, QSpinBox {
    background: $surface2; border: 1px solid $border; border-radius: 8px;
    padding: 6px 10px; min-height: 22px; selection-background-color: $soft;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus { border-color: $accent; background: $surface; }
QComboBox::drop-down { border: none; width: 24px; }
QComboBox QAbstractItemView { background: $surface; border: 1px solid $border; border-radius: 8px; selection-background-color: $soft; selection-color: $text; outline: none; }
QCheckBox { spacing: 8px; color: $text; }
QCheckBox::indicator { width: 17px; height: 17px; border-radius: 5px; border: 1.5px solid $border; background: $surface2; }
QCheckBox::indicator:hover { border-color: $accent; }
QCheckBox::indicator:checked { background: $accent; border-color: $accent; image: url($check_icon); }
QTextEdit, QTextBrowser { background: $surface; border: none; selection-background-color: $soft; selection-color: $text; font-size: 14px; }
QScrollArea { background: transparent; border: none; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: $border; border-radius: 4px; min-height: 28px; }
QScrollBar::handle:vertical:hover { background: $muted; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 2px; }
QScrollBar::handle:horizontal { background: $border; border-radius: 4px; min-width: 28px; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
QProgressBar { background: $surface2; border: none; border-radius: 4px; max-height: 7px; min-height: 7px; }
QProgressBar::chunk { background: $accent; border-radius: 4px; }
QSplitter::handle { background: transparent; width: 10px; }
QStatusBar { background: $surface; border-top: 1px solid $border; color: $muted; font-size: 12px; }
QStatusBar::item { border: none; }
QToolTip { background: $text; color: $bg; border: none; padding: 6px 9px; border-radius: 6px; font-size: 12px; }
QMenu { background: $surface; border: 1px solid $border; border-radius: 10px; padding: 6px; }
QMenu::item { padding: 7px 18px; border-radius: 6px; }
QMenu::item:selected { background: $soft; color: $accent; }
QMessageBox { background: $surface; }
""")


def load_app_font() -> str:
    font_file = ASSETS / "fonts" / "Vazirmatn[wght].ttf"
    if font_file.exists():
        font_id = QFontDatabase.addApplicationFont(str(font_file))
        families = QFontDatabase.applicationFontFamilies(font_id)
        if families:
            return families[0]
    return "Segoe UI" if QApplication.instance() and QApplication.instance().platformName() == "windows" else "DejaVu Sans"


def theme_palette(colors: dict) -> QPalette:
    """A complete light/dark palette.

    Windows dark mode can otherwise give plain Qt containers and scroll-area
    viewports a near-black default palette. The stylesheet alone does not cover
    every native/unstyled surface, so we set the application palette explicitly.
    """
    palette = QPalette()
    bg = QColor(colors["bg"])
    surface = QColor(colors["surface"])
    surface2 = QColor(colors["surface2"])
    text = QColor(colors["text"])
    muted = QColor(colors["muted"])
    accent = QColor(colors["accent"])
    border = QColor(colors["border"])
    role = QPalette.ColorRole
    palette.setColor(role.Window, bg)
    palette.setColor(role.WindowText, text)
    palette.setColor(role.Base, surface)
    palette.setColor(role.AlternateBase, surface2)
    palette.setColor(role.Text, text)
    palette.setColor(role.Button, surface)
    palette.setColor(role.ButtonText, text)
    palette.setColor(role.Highlight, accent)
    palette.setColor(role.HighlightedText, QColor(colors["accent_text"]))
    palette.setColor(role.ToolTipBase, surface)
    palette.setColor(role.ToolTipText, text)
    palette.setColor(role.PlaceholderText, muted)
    palette.setColor(role.Link, accent)
    palette.setColor(role.Light, surface)
    palette.setColor(role.Midlight, surface2)
    palette.setColor(role.Mid, border)
    palette.setColor(role.Dark, border)
    palette.setColor(role.Shadow, QColor(0, 0, 0, 0))
    for group in (QPalette.ColorGroup.Disabled, QPalette.ColorGroup.Inactive):
        palette.setColor(group, role.WindowText, muted)
        palette.setColor(group, role.Text, muted)
        palette.setColor(group, role.ButtonText, muted)
    return palette


def apply_theme(app: QApplication, dark: bool = False) -> dict:
    colors = dict(DARK if dark else LIGHT)
    check_name = "check-dark.svg" if dark else "check-white.svg"
    colors["check_icon"] = (ASSETS / "icons" / check_name).as_posix()
    app.setStyle("Fusion")
    app.setPalette(theme_palette(colors))
    family = load_app_font()
    font = QFont(family, 10)
    font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    app.setFont(font)
    app.setStyleSheet(_QSS.substitute(colors))
    return colors


def set_surface(widget: QWidget, color: str) -> None:
    """Force an opaque theme background on plain containers/viewports.

    Some Windows/Qt combinations ignore stylesheet backgrounds on scroll-area
    viewports and fall back to the native (often dark) palette. An explicit
    auto-filled palette makes the surface deterministic in light and dark mode.
    """
    widget.setAutoFillBackground(True)
    palette = widget.palette()
    palette.setColor(QPalette.ColorRole.Window, QColor(color))
    palette.setColor(QPalette.ColorRole.Base, QColor(color))
    widget.setPalette(palette)
    widget.update()


def add_card_shadow(widget: QWidget, colors: dict) -> None:
    """Keep cards flat/bordered instead of using QGraphicsDropShadowEffect.

    Qt graphics effects can render as opaque black rectangles around rounded
    cards on some Windows/Qt backends, especially inside scroll areas. The QSS
    border already provides the card edge, so we intentionally avoid the effect.
    """
    widget.setGraphicsEffect(None)


def repolish(widget: QWidget) -> None:
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()
