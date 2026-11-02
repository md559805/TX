from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest
from PIL import Image

from tx.core.engine import ExtractionService, file_kind, supported_extensions
from tx.core.models import CancelledError, ExtractionOptions
from tx.core.text import clean_text, count_words, has_useful_text, merge_native_and_ocr, normalize_persian_ocr
from tx.core.hocr import hocr_to_text
from conftest import requires_ocr, requires_rapid, FIXTURES


def test_clean_text_keeps_persian_half_space():
    raw = "سلام\u200cدنیا\r\nHello\x00 world\u00ad"
    assert clean_text(raw) == "سلام\u200cدنیا\nHello world"


def test_useful_text_ignores_page_numbers():
    assert not has_useful_text("12")
    assert has_useful_text("This is a real sentence.")


def test_merge_native_and_ocr_deduplicates():
    native = "Invoice 123\nTotal: 50"
    ocr = "Invoice 123\nTotal: 50\nExtra scanned note"
    merged = merge_native_and_ocr(native, ocr)
    assert merged.count("Invoice 123") == 1
    assert "Extra scanned note" in merged


def test_word_count_handles_persian():
    assert count_words("سلام دنیا hello world") == 4


def test_options_validate_languages():
    with pytest.raises(ValueError):
        ExtractionOptions(languages=("eng", "de"))
    assert ExtractionOptions(languages=("fas", "eng")).language_code == "fas+eng"


def test_supported_extensions_include_pdf_and_heic():
    extensions = supported_extensions()
    assert ".pdf" in extensions
    assert ".png" in extensions
    assert ".heic" in extensions


def test_unsupported_file_returns_error(tmp_path):
    path = tmp_path / "file.xyz"
    path.write_text("not an image")
    result = ExtractionService().extract(path)
    assert result.error
    assert not result.ok


def test_missing_tesseract_is_actionable():
    info = ExtractionService(ExtractionOptions(engine="tesseract", tesseract_path="/definitely/missing/tesseract")).diagnose()
    assert not info["available"]
    assert info["tesseract"] is False


def test_diagnose_separates_missing_rapid_models_from_missing_packages(monkeypatch):
    import sys

    import tx.core.rapid as rapid

    monkeypatch.setattr(rapid, "models_available", lambda: False)
    info = ExtractionService(ExtractionOptions(engine="rapid")).diagnose()
    assert info["rapid"]["models_present"] is False
    assert info["rapid"]["available"] is False
    assert "model files" in info["rapid"]["reason"]

    monkeypatch.setattr(rapid, "models_available", lambda: True)
    monkeypatch.setitem(sys.modules, "rapidocr", None)
    info = ExtractionService(ExtractionOptions(engine="rapid")).diagnose()
    assert info["rapid"]["models_present"] is True
    assert info["rapid"]["dependencies_present"] is False
    assert info["rapid"]["available"] is False
    assert "pip install -r requirements.txt" in info["rapid"]["reason"]


def test_cancel_before_start(bilingual_image):
    event = threading.Event()
    event.set()
    with pytest.raises(CancelledError):
        ExtractionService().extract(bilingual_image, cancel=event)


def test_native_pdf_does_not_require_tesseract(native_pdf):
    options = ExtractionOptions(tesseract_path="/definitely/missing/tesseract")
    result = ExtractionService(options).extract(native_pdf)
    assert result.ok
    assert "TX native PDF text layer" in result.text
    assert result.pages[0].method == "native"


@requires_ocr
def test_bilingual_image_ocr(bilingual_image):
    result = ExtractionService().extract(bilingual_image)
    assert result.ok
    assert "Hello from TX!" in result.text
    assert any("\u0600" <= c <= "\u06ff" for c in result.text)


@requires_ocr
def test_scanned_pdf_ocr(scanned_pdf):
    result = ExtractionService().extract(scanned_pdf)
    assert result.ok
    assert result.pages[0].method == "ocr"
    assert "Hello from TX!" in result.text
    assert "سلام دنیا! این یک آزمایش فارسی است." in result.text
    assert "فارسیاست" not in result.text


@requires_ocr
def test_mixed_pdf_merges_native_and_ocr(mixed_pdf):
    result = ExtractionService().extract(mixed_pdf)
    assert result.ok
    assert result.pages[0].method == "native+ocr"
    assert "Mixed page native heading" in result.text
    assert any("\u0600" <= c <= "\u06ff" for c in result.text)


@requires_ocr
def test_multiframe_tiff(tmp_path):
    paths = []
    for index, text in enumerate(("First frame text", "Second frame text")):
        image = Image.new("RGB", (900, 220), "white")
        from PIL import ImageDraw, ImageFont

        draw = ImageDraw.Draw(image)
        try:
            font = ImageFont.truetype("DejaVuSans.ttf", 48)
        except OSError:
            font = ImageFont.load_default()
        draw.text((40, 70), text, fill="black", font=font)
        paths.append(image)
    path = tmp_path / "multi.tiff"
    paths[0].save(path, save_all=True, append_images=paths[1:])
    result = ExtractionService().extract(path)
    assert result.ok
    assert len(result.pages) == 2
    assert "First frame" in result.pages[0].text
    assert "Second frame" in result.pages[1].text


def test_encrypted_pdf_password_provider(tmp_path):
    pytest.importorskip("reportlab")
    from reportlab.lib.pdfencrypt import StandardEncryption
    from reportlab.pdfgen import canvas

    path = tmp_path / "encrypted.pdf"
    encryption = StandardEncryption(userPassword="secret", ownerPassword="owner", canPrint=1)
    c = canvas.Canvas(str(path), encrypt=encryption)
    c.setFont("Helvetica", 16)
    c.drawString(72, 720, "Protected but readable text")
    c.showPage()
    c.save()

    def provider(request):
        request.password = "secret"
        request.ready.set()

    result = ExtractionService(ExtractionOptions(tesseract_path="/definitely/missing/tesseract")).extract(
        path, password_provider=provider
    )
    assert result.ok
    assert "Protected but readable text" in result.text


@requires_ocr
def test_persian_words_are_not_glued_together(bilingual_image):
    result = ExtractionService().extract(bilingual_image)
    assert result.ok
    assert "فارسی است." in result.text
    assert "فارسیاست" not in result.text
    assert "سلام دنیا! این یک آزمایش فارسی است." in result.text


@requires_ocr
def test_persian_paragraph_preserves_lines_and_zwnj():
    result = ExtractionService().extract(FIXTURES / "persian-paragraph.png")
    assert result.ok
    assert "سلام دنیا! این یک آزمایش فارسی است." in result.text
    assert "ما هر روز صبح به مدرسه می\u200cرویم." in result.text
    assert "کتاب\u200cهای فارسی را با دقت می\u200cخوانیم." in result.text
    assert "\u200c" in result.text


@requires_ocr
def test_persian_mixed_line_keeps_english_and_spacing():
    result = ExtractionService().extract(FIXTURES / "persian-mixed.png")
    assert result.ok
    assert "این برنامه متن\u200cهای فارسی و English را با دقت بیشتری می\u200cخواند." in result.text


def test_hocr_reconstruction_inserts_rtl_word_spaces():
    hocr = """<?xml version='1.0' encoding='UTF-8'?>
    <html xmlns='http://www.w3.org/1999/xhtml'><body>
    <div class='ocr_page'><p class='ocr_par' dir='rtl'>
    <span class='ocr_line'><span class='ocrx_word'>فارسی</span><span class='ocrx_word'>است.</span></span>
    </p></div></body></html>"""
    assert hocr_to_text(hocr) == "فارسی است."


def test_persian_ocr_normalizes_arabic_yeh_and_kaf():
    assert normalize_persian_ocr("اين كتاب") == "این کتاب"
    assert normalize_persian_ocr("می\u200cرویم") == "می\u200cرویم"


@requires_rapid
def test_rapid_models_are_bundled_and_local():
    from tx.core.rapid import models_available

    assert models_available()


@requires_rapid
def test_persian_line_normalization_repairs_common_ocr_glue():
    from tx.core.rapid import normalize_persian_line

    assert normalize_persian_line("می روم") == "می‌روم"
    assert normalize_persian_line("کتاب ها") == "کتاب‌ها"
    assert normalize_persian_line("وشایسته") == "و شایسته"
    assert normalize_persian_line("١٢٣") == "۱۲۳"


@requires_rapid
@requires_ocr
def test_advertisement_layout_fixture_keeps_persian_english_and_numbers():
    result = ExtractionService().extract(FIXTURES / "persian-poster.png")
    assert result.ok
    text = result.text
    assert "COMFORT YOU FEEL, STYLE YOU LOVE" in text
    assert "شلوار زنانه لاکچری" in text
    assert "تا در تمام لحظات روز همراهی مطمئن و شایسته باشد." in text
    assert "بهترین جنس، نرم، لطیف و ضدحساسیت" in text
    assert "سایزبندی کامل، ۳۸ تا ۵۴" in text
    assert "همین حالا سفارش دهید!" in text
    assert "ارسال سریع به سراسر کشور" in text
    assert "Gly" not in text and "wlio" not in text


def test_language_manifest_is_pinned():
    manifest = json.loads((Path(__file__).resolve().parents[1] / "tx" / "core" / "language_packs.json").read_text())
    assert set(manifest) == {"eng", "fas", "osd"}
    for item in manifest.values():
        assert len(item["sha256"]) == 64
        assert item["bytes"] > 0
        assert item["url"].startswith("https://raw.githubusercontent.com/tesseract-ocr/")
