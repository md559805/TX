from __future__ import annotations

import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent / "fixtures"


def tesseract_available() -> bool:
    return shutil.which("tesseract") is not None


requires_ocr = pytest.mark.skipif(not tesseract_available(), reason="Tesseract is not installed")


def rapid_available() -> bool:
    try:
        from tx.core.rapid import models_available
        import rapidocr  # noqa: F401
        import onnxruntime  # noqa: F401

        return models_available()
    except Exception:
        return False


requires_rapid = pytest.mark.skipif(not rapid_available(), reason="RapidOCR models/dependencies are not installed")


@pytest.fixture(scope="session")
def bilingual_image() -> Path:
    return FIXTURES / "bilingual.png"


@pytest.fixture(scope="session")
def native_pdf(tmp_path_factory) -> Path:
    reportlab = pytest.importorskip("reportlab")
    from reportlab.pdfgen import canvas

    path = tmp_path_factory.mktemp("pdf") / "native.pdf"
    c = canvas.Canvas(str(path))
    c.setFont("Helvetica", 16)
    c.drawString(72, 720, "TX native PDF text layer")
    c.drawString(72, 690, "This page should not need OCR.")
    c.showPage()
    c.save()
    return path


@pytest.fixture(scope="session")
def scanned_pdf(bilingual_image, tmp_path_factory) -> Path:
    from PIL import Image

    path = tmp_path_factory.mktemp("pdf") / "scanned.pdf"
    with Image.open(bilingual_image) as image:
        image.convert("RGB").save(path, "PDF", resolution=150.0)
    return path


@pytest.fixture(scope="session")
def mixed_pdf(bilingual_image, tmp_path_factory) -> Path:
    pytest.importorskip("reportlab")
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    path = tmp_path_factory.mktemp("pdf") / "mixed.pdf"
    c = canvas.Canvas(str(path), pagesize=(720, 520))
    c.setFont("Helvetica-Bold", 16)
    c.drawString(48, 480, "Mixed page native heading")
    c.drawImage(ImageReader(str(bilingual_image)), 36, 60, width=648, height=281)
    c.showPage()
    c.save()
    return path
