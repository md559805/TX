from __future__ import annotations

import re
import unicodedata
from collections import Counter

# Keep Persian half-spaces (ZWNJ). Do not reverse RTL text or transliterate it.
_UNWANTED = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\u00ad\u200b\u200e\u200f\ufeff\u202a-\u202e\u2066-\u2069]")


def clean_text(value: str) -> str:
    value = unicodedata.normalize("NFC", value.replace("\r\n", "\n").replace("\r", "\n"))
    value = _UNWANTED.sub("", value).replace("\u00a0", " ").expandtabs(4)
    lines = [line.rstrip() for line in value.split("\n")]
    return re.sub(r"\n{4,}", "\n\n\n", "\n".join(lines)).strip()


def has_useful_text(value: str) -> bool:
    """A page number or a handful of punctuation marks is not a useful text layer."""
    compact = re.sub(r"\s+", "", value)
    return len(compact) >= 12 and sum(c.isalnum() for c in compact) >= 8


def _comparison_key(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold()
    return re.sub(r"[\s\u200c]+", "", value)


def merge_native_and_ocr(native: str, ocr: str) -> str:
    """Add OCR-only lines to a mixed PDF page, accounting for repeated lines.

    This deliberately avoids rearranging paragraphs. Identical lines already
    present in the PDF text layer are not copied a second time.
    """
    if not has_useful_text(native):
        return clean_text(ocr)
    if not ocr.strip():
        return clean_text(native)
    available = Counter(_comparison_key(line) for line in native.splitlines() if line.strip())
    additions: list[str] = []
    for line in ocr.splitlines():
        key = _comparison_key(line)
        if not key:
            if additions and additions[-1]:
                additions.append("")
            continue
        if available[key] > 0:
            available[key] -= 1
        else:
            additions.append(line)
    extra = clean_text("\n".join(additions))
    return clean_text(native + ("\n\n" + extra if extra else ""))


def count_words(value: str) -> int:
    return len(re.findall(r"[^\W_]+(?:[\u200c'’\-][^\W_]+)*", value, re.UNICODE))


# Tesseract's Persian model sometimes emits the Arabic forms of yeh/kaf.
# Normalize those to the Persian letters when Persian OCR is enabled. This is
# intentionally narrow: it does not transliterate, reverse, or remove ZWNJ.
_PERSIAN_OCR_MAP = str.maketrans({"\u064a": "\u06cc", "\u0643": "\u06a9", "\u0649": "\u06cc"})


def normalize_persian_ocr(value: str) -> str:
    return value.translate(_PERSIAN_OCR_MAP)
