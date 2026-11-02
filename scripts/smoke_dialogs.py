#!/usr/bin/env python3
"""Offscreen dialog smoke test: frameless dialogs, readable status, themed surfaces."""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication

from tx.core.models import ExtractionOptions
from tx.gui.dialogs import HelpDialog, SetupDialog
from tx.gui.theme import apply_theme


def check_dialog(dialog, name: str) -> None:
    assert dialog.windowFlags() & Qt.WindowType.FramelessWindowHint, name
    assert not dialog.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground), name
    assert dialog.graphicsEffect() is None, name


def main() -> int:
    app = QApplication([])
    colors = apply_theme(app, False)
    setup = SetupDialog(ExtractionOptions(), colors)
    setup.refresh_status()
    setup.show()
    app.processEvents()
    check_dialog(setup, "setup")
    assert setup.status.height() >= setup.status.sizeHint().height() - 2, "setup status is clipped"
    assert "RapidOCR" in setup.status.text()
    out = ROOT / "docs" / "setup-dialog.png"
    setup.grab().save(str(out))
    setup.close()

    about = HelpDialog(colors)
    about.show()
    app.processEvents()
    check_dialog(about, "about")
    about.grab().save(str(ROOT / "docs" / "about-dialog.png"))
    about.close()

    dark = apply_theme(app, True)
    setup_dark = SetupDialog(ExtractionOptions(), dark)
    setup_dark.show()
    app.processEvents()
    assert setup_dark.palette().color(QPalette.ColorRole.Window).name().lower() == dark["bg"].lower()
    setup_dark.close()
    print(f"Dialog smoke test passed. Screenshot: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
