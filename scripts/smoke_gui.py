#!/usr/bin/env python3
"""Offscreen GUI smoke test. Saves docs/gui-screenshot.png on success."""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from tx.gui.main_window import MainWindow


def main() -> int:
    app = QApplication([])
    window = MainWindow()
    window.show()
    window.add_paths([ROOT / "tests" / "fixtures" / "bilingual.png"])
    QTimer.singleShot(100, window.start_extraction)
    deadline = QTimer()
    deadline.setSingleShot(True)
    deadline.timeout.connect(app.quit)
    deadline.start(30000)

    def poll() -> None:
        if not window.running:
            app.quit()
        else:
            QTimer.singleShot(100, poll)

    QTimer.singleShot(300, poll)
    app.exec()
    text = window.text_edit.toPlainText()
    ok = (
        not window.running
        and "Hello from TX!" in text
        and "فارسی است." in text
        and "فارسیاست" not in text
    )
    if ok:
        output = ROOT / "docs" / "gui-screenshot.png"
        output.parent.mkdir(parents=True, exist_ok=True)
        window.grab().save(str(output))
        print(f"GUI smoke test passed. Screenshot: {output}")
    else:
        print("GUI smoke test failed.", file=sys.stderr)
    # Avoid modal close prompts if something went wrong.
    window.running = False
    window.close()
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
