#!/usr/bin/env python3
"""Create small sample files for trying the app."""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas


def main() -> int:
    examples = ROOT / "examples"
    examples.mkdir(exist_ok=True)
    image = ROOT / "tests" / "fixtures" / "bilingual.png"
    shutil.copyfile(image, examples / "sample-bilingual.png")
    pdf = examples / "sample.pdf"
    c = canvas.Canvas(str(pdf), pagesize=(720, 520))
    c.setFont("Helvetica-Bold", 18)
    c.drawString(48, 460, "TX sample")
    c.setFont("Helvetica", 13)
    c.drawString(48, 430, "Page 1 has a real PDF text layer, so smart mode can read it without OCR.")
    c.drawString(48, 405, "Page 2 is a scanned bilingual image, so it needs OCR.")
    c.showPage()
    c.drawImage(ImageReader(str(image)), 36, 80, width=648, height=281)
    c.showPage()
    c.save()
    (examples / "README.txt").write_text(
        "فایل‌های نمونه برای امتحان برنامه\n\n"
        "sample-bilingual.png: تصویر دو زبانه برای OCR.\n"
        "sample.pdf: صفحهٔ اول متن اصلی PDF دارد، صفحهٔ دوم تصویر اسکن‌شده است.\n",
        encoding="utf-8",
    )
    print(f"Wrote {examples}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
