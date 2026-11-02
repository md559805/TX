from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from tx.gui.main_window import MainWindow

FIXTURES = Path(__file__).parent / "fixtures"


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_preview_can_switch_between_multiple_uploaded_files():
    app = _app()
    window = MainWindow()
    try:
        first = FIXTURES / "bilingual.png"
        second = FIXTURES / "persian-mixed.png"
        window.add_paths([first, second])
        window._switch_tab(True)
        app.processEvents()

        assert window.preview_file_combo.count() == 2
        assert window.preview_path == first.resolve()
        assert window.file_position.text() == "1 / 2"
        assert not window.prev_file.isEnabled()
        assert window.next_file.isEnabled()

        window.next_file.click()
        app.processEvents()
        assert window.preview_path == second.resolve()
        assert window.preview_file_combo.currentIndex() == 1
        assert window.file_list.selected == second.resolve()
        assert window.file_position.text() == "2 / 2"
        assert window.prev_file.isEnabled()
        assert not window.next_file.isEnabled()

        window.prev_file.click()
        app.processEvents()
        assert window.preview_path == first.resolve()
        assert window.preview_file_combo.currentIndex() == 0

        window.preview_file_combo.setCurrentIndex(1)
        app.processEvents()
        assert window.preview_path == second.resolve()
        assert window.file_list.selected == second.resolve()

        row = window.file_list.rows[first.resolve()]
        assert row.name_label.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        assert row.meta_label.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        assert not row.remove_button.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        window.file_list.remove(second.resolve())
        app.processEvents()
        assert window.preview_file_combo.count() == 1
        assert window.preview_path == first.resolve()
        assert not window.next_file.isEnabled()

        window.clear_files()
        app.processEvents()
        assert window.preview_file_combo.count() == 1
        assert window.preview_file_combo.itemData(0) is None
        assert not window.preview_file_combo.isEnabled()
        assert window.preview_path is None
    finally:
        window.running = False
        window.close()


def test_preview_page_controls_are_per_file_and_reset_on_file_change(tmp_path):
    app = _app()
    pdf = tmp_path / "two-pages.pdf"
    with Image.open(FIXTURES / "bilingual.png") as one, Image.open(FIXTURES / "persian-mixed.png") as two:
        one.convert("RGB").save(pdf, "PDF", resolution=100.0, save_all=True, append_images=[two.convert("RGB")])
    image = FIXTURES / "bilingual.png"

    window = MainWindow()
    try:
        window.add_paths([pdf, image])
        window._switch_tab(True)
        app.processEvents()

        assert window.preview_path == pdf.resolve()
        assert window.preview_total == 2
        assert window.page_spin.isEnabled()
        assert window.next_page.isEnabled()
        assert not window.prev_page.isEnabled()

        window.next_page.click()
        app.processEvents()
        assert window.preview_page == 2
        assert window.prev_page.isEnabled()
        assert not window.next_page.isEnabled()

        window.next_file.click()
        app.processEvents()
        assert window.preview_path == image.resolve()
        assert window.preview_page == 1
        assert window.preview_total == 1
        assert not window.page_spin.isEnabled()
        assert not window.prev_page.isEnabled()
        assert not window.next_page.isEnabled()
    finally:
        window.running = False
        window.close()
