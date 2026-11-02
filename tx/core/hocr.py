"""Reconstruct plain text from Tesseract hOCR without losing word boundaries.

Tesseract's plain-text writer can join adjacent RTL words even when its word
boxes are separate. hOCR keeps those words as separate elements, so we join
them with explicit spaces and use the paragraph/line structure for line breaks.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from .text import clean_text

_WORD_CLASSES = {"ocrx_word"}
_LINE_CLASSES = {"ocr_line"}
_PAR_CLASSES = {"ocr_par"}
_PUNCT_ATTACH_LEFT = ".,;:!?\u060c\u061b\u061f\u066b\u066c)]}\u00bb"
_PUNCT_ATTACH_RIGHT = "([{\u00ab"


def _classes(element: ET.Element) -> set[str]:
    return set((element.get("class") or "").split())


def _word_text(element: ET.Element) -> str:
    return "".join(element.itertext()).strip()


def _join_words(words: list[str]) -> str:
    if not words:
        return ""
    result = words[0]
    for word in words[1:]:
        if not word:
            continue
        # Keep punctuation attached when the OCR engine emits it as a token.
        if word[0] in _PUNCT_ATTACH_LEFT or (result and result[-1] in _PUNCT_ATTACH_RIGHT):
            result += word
        else:
            result += " " + word
    return result


def _line_text(line: ET.Element) -> str:
    words = [_word_text(w) for w in line.iter() if _classes(w) & _WORD_CLASSES]
    return _join_words([w for w in words if w])


def hocr_to_text(document: str) -> str:
    """Return cleaned text, preserving paragraph and line boundaries.

    The word order supplied by Tesseract is kept as-is. Sorting RTL words by
    their x coordinates would reverse Persian sentences, so we deliberately do
    not do that.
    """
    if not document.strip():
        return ""
    try:
        root = ET.fromstring(document)
    except ET.ParseError:
        # Some builds emit HTML entities or a truncated document. Fall back to
        # a conservative tag stripper rather than returning XML to the user.
        stripped = re.sub(r"<[^>]+>", " ", document)
        return clean_text(stripped)

    paragraphs = [e for e in root.iter() if _classes(e) & _PAR_CLASSES]
    chunks: list[str] = []
    if paragraphs:
        for paragraph in paragraphs:
            lines = [e for e in paragraph.iter() if _classes(e) & _LINE_CLASSES]
            if lines:
                chunks.append("\n".join(_line_text(line) for line in lines))
            else:
                chunks.append(_line_text(paragraph))
    else:
        lines = [e for e in root.iter() if _classes(e) & _LINE_CLASSES]
        chunks.append("\n".join(_line_text(line) for line in lines))
    return clean_text("\n\n".join(chunk for chunk in chunks if chunk.strip()))
