#!/usr/bin/env python3
"""Offscreen multi-file preview smoke test. Saves docs/preview-multi-file.png."""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication

from tx.gui.main_window import MainWindow


def main() -> int:
    app = QApplication([])
    window = MainWindow()
    window.show()
    first = ROOT / "tests" / "fixtures" / "bilingual.png"
    second = ROOT / "tests" / "fixtures" / "persian-mixed.png"
    window.add_paths([first, second])
    window._switch_tab(True)
    app.processEvents()
    assert window.preview_file_combo.count() == 2
    assert window.preview_path == first.resolve()
    window.next_file.click()
    app.processEvents()
    assert window.preview_path == second.resolve()
    assert window.file_list.selected == second.resolve()
    window.preview_file_combo.setCurrentIndex(0)
    app.processEvents()
    assert window.preview_path == first.resolve()
    out = ROOT / "docs" / "preview-multi-file.png"
    window.grab().save(str(out))
    print(f"Multi-file preview smoke test passed. Screenshot: {out}")
    window.running = False
    window.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
