#!/usr/bin/env python3
"""Offscreen responsive-layout regression. Saves screenshots at several sizes."""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from tx.gui.main_window import MainWindow

SIZES = [(720, 520), (900, 640), (1180, 780), (1440, 900)]


def visible_in_window(window, widget) -> bool:
    if not widget.isVisible():
        return False
    top = widget.mapTo(window, widget.rect().topLeft())
    bottom = widget.mapTo(window, widget.rect().bottomRight())
    return 0 <= top.x() and 0 <= top.y() and bottom.x() <= window.width() and bottom.y() <= window.height()


def main() -> int:
    app = QApplication([])
    window = MainWindow()
    window.show()
    window.add_paths([ROOT / "tests" / "fixtures" / "bilingual.png"])
    out = ROOT / "docs" / "responsive"
    out.mkdir(parents=True, exist_ok=True)
    ok = True
    for width, height in SIZES:
        window.resize(width, height)
        app.processEvents()
        window._apply_responsive_layout()
        app.processEvents()
        checks = {
            "start": visible_in_window(window, window.start_button),
            "add": visible_in_window(window, window.add_button),
            "copy": visible_in_window(window, window.copy_button),
            "setup": visible_in_window(window, window.setup_button),
            "no-hscroll": window.left_scroll.horizontalScrollBar().isVisible() is False,
        }
        expected_vertical = width < 980
        checks["orientation"] = (window.splitter.orientation() == Qt.Orientation.Vertical) == expected_vertical
        passed = all(checks.values())
        ok = ok and passed
        path = out / f"tx-{width}x{height}.png"
        window.grab().save(str(path))
        print(f"{width}x{height}: {'PASS' if passed else 'FAIL'} {checks} -> {path}")
    window.running = False
    window.close()
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
