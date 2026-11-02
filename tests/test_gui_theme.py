from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QFrame, QWidget

from tx.gui.theme import DARK, LIGHT, add_card_shadow, apply_theme, set_surface, theme_palette


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_card_shadow_does_not_use_opaque_graphics_effect():
    app = _app()
    for colors in (LIGHT, DARK):
        widget = QFrame()
        add_card_shadow(widget, colors)
        assert widget.graphicsEffect() is None
        color = QColor(colors["shadow"])
        assert color.isValid()
        assert color.alpha() < 255


def test_theme_sets_explicit_light_and_dark_palette():
    app = _app()
    for dark, colors in ((False, LIGHT), (True, DARK)):
        apply_theme(app, dark)
        palette = app.palette()
        assert palette.color(QPalette.ColorRole.Window).name().lower() == colors["bg"].lower()
        assert palette.color(QPalette.ColorRole.Base).name().lower() == colors["surface"].lower()
        assert palette.color(QPalette.ColorRole.Text).name().lower() == colors["text"].lower()
    apply_theme(app, False)


def test_set_surface_forces_opaque_background():
    app = _app()
    widget = QFrame()
    set_surface(widget, LIGHT["bg"])
    assert widget.autoFillBackground()
    assert widget.palette().color(QPalette.ColorRole.Window).name().lower() == LIGHT["bg"].lower()
    assert widget.palette().color(QPalette.ColorRole.Base).name().lower() == LIGHT["bg"].lower()


def test_main_window_cards_and_scroll_surfaces_are_explicit():
    app = _app()
    from tx.gui.main_window import MainWindow

    window = MainWindow()
    try:
        cards = window.findChildren(QFrame, "Card")
        assert cards
        assert all(card.graphicsEffect() is None for card in cards)
        bg = window.colors["bg"].lower()
        surface = window.colors["surface"].lower()
        assert window.left_scroll.viewport().autoFillBackground()
        assert window.left_scroll.viewport().palette().color(QPalette.ColorRole.Window).name().lower() == bg
        assert window.scroll_body.palette().color(QPalette.ColorRole.Window).name().lower() == bg
        assert window.file_list.container.palette().color(QPalette.ColorRole.Window).name().lower() == surface
        assert window.file_list.scroll.viewport().palette().color(QPalette.ColorRole.Window).name().lower() == surface
        assert window.preview_scroll.viewport().palette().color(QPalette.ColorRole.Window).name().lower() == surface
    finally:
        window.running = False
        window.close()


def test_theme_toggle_survives_preview_page_number_attribute():
    app = _app()
    from tx.gui.main_window import MainWindow

    window = MainWindow()
    try:
        # Regression: ``preview_page`` is a page number, not the preview widget.
        # Theme switching must not try to call QWidget methods on an int.
        window.preview_page = 3
        window._on_selection_changed(None)
        assert isinstance(window.preview_page, int)
        window.toggle_theme()
        window.toggle_theme()
        assert isinstance(window.preview_page, int)
        assert isinstance(window.preview_page_widget, QWidget)
        assert window.preview_page_widget.objectName() == "PreviewPage"
    finally:
        window.running = False
        window.close()


def test_dialogs_are_frameless_without_translucent_black_halo():
    app = _app()
    from tx.core.models import ExtractionOptions
    from tx.gui.dialogs import HelpDialog, SetupDialog

    colors = apply_theme(app, False)
    setup = SetupDialog(ExtractionOptions(), colors)
    about = HelpDialog(colors)
    try:
        for dialog in (setup, about):
            assert dialog.windowFlags() & Qt.WindowType.FramelessWindowHint
            assert not dialog.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            assert dialog.graphicsEffect() is None
        assert setup.status.objectName() == "InnerCard"
        margins = setup.status.contentsMargins()
        assert margins.left() == margins.top() == margins.right() == margins.bottom() == 0
        setup.status.setText("RapidOCR (bundled): ready\nTesseract: ready\nLanguages: eng, fas")
        setup.status.adjustSize()
        assert setup.status.sizeHint().height() >= setup.status.fontMetrics().lineSpacing() * 3 + 20
    finally:
        setup.close()
        about.close()
