#!/usr/bin/env python3
"""Rasterize the SVG app icon to PNG and Windows ICO."""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication


def main() -> int:
    app = QApplication([])
    assets = ROOT / "tx" / "assets"
    renderer = QSvgRenderer(str(assets / "icon.svg"))
    image = QImage(512, 512, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter)
    painter.end()
    image.save(str(assets / "icon.png"))
    with Image.open(assets / "icon.png") as pil:
        pil.save(assets / "icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("Wrote icon.png and icon.ico")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
