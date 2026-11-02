"""Local RapidOCR (ONNX Runtime) engine with bundled Arabic-script PP-OCRv5 models.

The Arabic-script recognizer covers Persian and English. Models are shipped in
``tx/assets/models`` and loaded from explicit paths so RapidOCR never downloads
anything implicitly. Tesseract remains available as a second opinion for clean
scans where its Persian orthography (ZWNJ, punctuation) is stronger.
"""
from __future__ import annotations

import re
import threading
from pathlib import Path

from PIL import Image, ImageOps

from .models import CancelledError, ExtractionError

_MODEL_DIR = Path(__file__).resolve().parents[1] / "assets" / "models"
_DET = "ch_PP-OCRv5_det_mobile.onnx"
_REC = "arabic_PP-OCRv5_rec_mobile.onnx"
_CLS = "ch_PP-LCNet_x0_25_textline_ori_cls_mobile.onnx"

_PERSIAN_MAP = str.maketrans({
    "\u064a": "\u06cc", "\u0643": "\u06a9", "\u0649": "\u06cc",
    "\u0660": "\u06f0", "\u0661": "\u06f1", "\u0662": "\u06f2", "\u0663": "\u06f3",
    "\u0664": "\u06f4", "\u0665": "\u06f5", "\u0666": "\u06f6", "\u0667": "\u06f7",
    "\u0668": "\u06f8", "\u0669": "\u06f9",
})
_ZWNJ = "\u200c"


def models_available() -> bool:
    # The orientation classifier is optional; the detector + recognizer are enough.
    return all((_MODEL_DIR / name).is_file() for name in (_DET, _REC))


def normalize_persian_line(value: str) -> str:
    """Conservative Persian orthography repair for Arabic-script OCR output."""
    value = value.translate(_PERSIAN_MAP)
    # Verbal prefixes: می رود / نمی دانم -> می‌رود / نمی‌دانم
    value = re.sub(r"(?<![\w\u200c])(می|نمی) +(?=[^\s])", r"\1" + _ZWNJ, value)
    # Common suffixes: کتاب ها / بزرگ تر -> کتاب‌ها / بزرگ‌تر
    value = re.sub(r"(?<=[^\s\u200c]) +(ها|های|هایی|تر|ترین)(?=[\s،.!?؛:]|$)", r"" + _ZWNJ + r"\1", value)
    # Plural/comparative suffixes that the recognizer glues to the stem.
    value = re.sub(r"(?<=[^\s\u200c]{3})(ها|های|هایی)(?=[\s،.!?؛:]|$)", _ZWNJ + r"\1", value)
    # Well-known compounds that the recognizer tends to split or glue.
    value = value.replace("فوق العاده", "فوق\u200cالعاده")
    value = value.replace("بی نظیر", "بی\u200cنظیر")
    value = value.replace("دهیدا", "دهید!")
    # The conjunction و is frequently glued to the following word by OCR.
    # Split only when the remainder is not a common و-initial lexical word.
    _VAV_WORDS = {"ولی", "وقتی", "وجود", "ورزش", "وقت", "وحی", "وطن", "وضع", "وعده", "وفات", "وفادار", "وهن", "وهم", "ویران", "ویروس", "ویژه", "والدین", "وارد", "واقعی", "والا", "واکسن", "وب", "وتر", "وحدت", "وحشت", "وداع", "ورد", "روش", "روشن", "روز", "روزمره", "رود", "روح", "روان", "روبرو", "رویداد", "رهایی", "رفتار", "رقابت", "رنگ", "رنج", "رمز", "رشد", "رسانه", "رسمی", "رسید", "رئیس", "ذره", "ذوق", "ذکاوت"}
    def _split_vav(match):
        token = match.group(0)
        return token if token in _VAV_WORDS else "و " + match.group(1)
    value = re.sub(r"(?<![\w\u200c])و([^\s\u200c،.!?؛:]{3,})", _split_vav, value)
    # Keep a visual boundary between numerals and adjacent Persian words.
    value = re.sub(r"(?<=[0-9۰-۹٠-٩])(?=[^\s0-9۰-۹٠-٩،.٫٬%/:\-])", " ", value)
    value = re.sub(r"(?<=[^\s0-9۰-۹٠-٩،.٫٬%/:\-])(?=[0-9۰-۹٠-٩])", " ", value)
    value = re.sub(r"[ \t]{2,}", " ", value).strip()
    return value


class RapidRunner:
    """Thin, lazy wrapper around RapidOCR. One instance per worker thread."""

    def __init__(self) -> None:
        self._engine = None

    def _load(self):
        if self._engine is not None:
            return self._engine
        if not models_available():
            raise ExtractionError(
                "The bundled Persian/English OCR models are missing. Reinstall TX or restore tx/assets/models.",
                "models",
            )
        try:
            from rapidocr import EngineType, LangRec, ModelType, OCRVersion, RapidOCR
        except ImportError as exc:
            raise ExtractionError(
                "RapidOCR is not installed. Run: python -m pip install 'rapidocr[rtl]==3.10.0' onnxruntime",
                "dependency",
            ) from exc
        params = {
            "Det.engine_type": EngineType.ONNXRUNTIME,
            "Det.ocr_version": OCRVersion.PPOCRV5,
            "Det.model_type": ModelType.MOBILE,
            "Det.model_path": str(_MODEL_DIR / _DET),
            "Det.limit_side_len": 1600,
            "Det.limit_type": "max",
            "Rec.engine_type": EngineType.ONNXRUNTIME,
            "Rec.lang_type": LangRec.ARABIC,
            "Rec.ocr_version": OCRVersion.PPOCRV5,
            "Rec.model_type": ModelType.MOBILE,
            "Rec.model_path": str(_MODEL_DIR / _REC),
            "Cls.engine_type": EngineType.ONNXRUNTIME,
            "Cls.ocr_version": OCRVersion.PPOCRV5,
            "Cls.model_type": ModelType.MOBILE,
            "Cls.model_path": str(_MODEL_DIR / _CLS),
            "Global.log_level": "error",
            "Global.model_root_dir": str(_MODEL_DIR),
            "EngineConfig.onnxruntime.intra_op_num_threads": 2,
            "EngineConfig.onnxruntime.inter_op_num_threads": 1,
        }
        try:
            self._engine = RapidOCR(params=params)
        except Exception as exc:
            raise ExtractionError(f"Could not initialize the local OCR engine: {exc}", "engine") from exc
        return self._engine

    def recognize_detailed(self, image: Image.Image, cancel: threading.Event | None = None):
        """Return (lines, boxes, scores). Lines are Persian-normalized strings."""
        if cancel is not None and cancel.is_set():
            raise CancelledError()
        engine = self._load()
        work = image.convert("RGB")
        scale = 1.0
        if max(work.size) > 2000:
            scale = 2000 / max(work.size)
            work.thumbnail((2000, 2000), Image.Resampling.LANCZOS)
        try:
            import numpy as np

            # The text-line orientation classifier is deliberately disabled:
            # on Persian/English artwork it can rotate correct lines and erase
            # them. Page-level rotation is handled by Tesseract OSD when present.
            result = engine(np.asarray(work), use_det=True, use_cls=False, text_score=0.3)
        except Exception as exc:
            work.close()
            raise ExtractionError(f"The local OCR engine could not read this page: {exc}", "engine") from exc
        if cancel is not None and cancel.is_set():
            work.close()
            raise CancelledError()
        lines: list[str] = []
        boxes = []
        scores: list[float] = []
        raw_boxes = getattr(result, "boxes", None)
        raw_texts = list(result.txts or ())
        raw_scores = list(result.scores or ())
        for index, (text, score) in enumerate(zip(raw_texts, raw_scores)):
            if score < 0.3:
                continue
            box = None
            if raw_boxes is not None and index < len(raw_boxes):
                box = raw_boxes[index]
            # Low-confidence detections are often small or low-contrast lines.
            # Re-recognize an upscaled crop without re-detecting; this recovers
            # lines the full-page pass reduced to a few stray letters.
            if box is not None and score < 0.78:
                try:
                    import numpy as np

                    pts = np.asarray(box)
                    x0, y0 = pts.min(axis=0).astype(int)
                    x1, y1 = pts.max(axis=0).astype(int)
                    pad = 10
                    crop = work.crop((max(0, x0 - pad), max(0, y0 - pad), min(work.width, x1 + pad), min(work.height, y1 + pad)))
                    crop = ImageOps.expand(crop, border=16, fill="white")
                    factor = max(1.0, 96 / max(1, crop.height))
                    if factor > 1.01:
                        crop = crop.resize((max(1, int(crop.width * factor)), max(1, int(crop.height * factor))), Image.Resampling.LANCZOS)
                    retry = engine(np.asarray(crop), use_det=False, use_cls=False)
                    if retry.txts and retry.scores and retry.scores[0] > score + 0.05:
                        candidate = str(retry.txts[0])
                        if sum(c.isalpha() for c in candidate) >= max(2, sum(c.isalpha() for c in text) * 0.8):
                            text, score = candidate, float(retry.scores[0])
                    crop.close()
                except Exception:
                    pass
            text = normalize_persian_line(str(text))
            if not text or re.fullmatch(r"[\s•·.\-–—_=+*/\\|()\[\]{}]+", text):
                continue
            # Drop recognizer noise: several isolated letters with low confidence.
            tokens = text.split()
            if score < 0.6 and len(tokens) >= 3 and sum(len(t) == 1 for t in tokens) / len(tokens) > 0.5:
                continue
            lines.append(text)
            scores.append(float(score))
            boxes.append((box / scale).tolist() if box is not None and scale != 1.0 else (box.tolist() if box is not None else None))
        work.close()
        return lines, boxes, scores

    def recognize(self, image: Image.Image, cancel: threading.Event | None = None) -> str:
        lines, _, _ = self.recognize_detailed(image, cancel)
        return "\n".join(lines)
