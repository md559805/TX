from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from threading import Event
from typing import Literal


class ExtractionError(Exception):
    """An actionable, user-facing processing error."""

    def __init__(self, message: str, code: str = "processing"):
        super().__init__(message)
        self.code = code


class CancelledError(ExtractionError):
    def __init__(self) -> None:
        super().__init__("Extraction was cancelled.", "cancelled")


@dataclass(frozen=True)
class ExtractionOptions:
    languages: tuple[str, ...] = ("eng", "fas")
    dpi: int = 300
    smart_pdf: bool = True
    enhance: bool = True
    detect_orientation: bool = True
    timeout: int = 300
    max_pixels: int = 20_000_000
    tesseract_path: str | None = None
    tessdata_dir: str | None = None
    engine: Literal["auto", "rapid", "tesseract"] = "auto"

    def __post_init__(self) -> None:
        if self.engine not in ("auto", "rapid", "tesseract"):
            raise ValueError("OCR engine must be auto, rapid, or tesseract.")
        if not self.languages or set(self.languages) - {"eng", "fas"}:
            raise ValueError("Choose English, Persian, or both.")
        if len(set(self.languages)) != len(self.languages):
            raise ValueError("Duplicate OCR languages are not allowed.")
        if not 72 <= self.dpi <= 600:
            raise ValueError("DPI must be between 72 and 600.")
        if not 10 <= self.timeout <= 1800:
            raise ValueError("The page timeout must be between 10 and 1800 seconds.")
        if not 1_000_000 <= self.max_pixels <= 40_000_000:
            raise ValueError("The image pixel limit is outside the supported range.")

    @property
    def language_code(self) -> str:
        return "+".join(self.languages)


@dataclass
class PageResult:
    number: int
    text: str = ""
    method: Literal["native", "ocr", "native+ocr", "empty", "error"] = "empty"
    error: str | None = None


@dataclass
class DocumentResult:
    path: Path
    pages: list[PageResult] = field(default_factory=list)
    error: str | None = None
    elapsed: float = 0.0

    @property
    def ok(self) -> bool:
        return self.error is None and not any(p.error for p in self.pages)

    @property
    def text(self) -> str:
        return "\n\n".join(p.text for p in self.pages if p.text).strip()

    @property
    def warnings(self) -> list[str]:
        values = [self.error] if self.error else []
        values.extend(f"Page {p.number}: {p.error}" for p in self.pages if p.error)
        return values


@dataclass
class Progress:
    file_index: int
    file_count: int
    page: int
    page_count: int
    fraction: float
    message: str


@dataclass
class PasswordRequest:
    """A thread-safe bridge between the OCR worker and a password dialog."""

    path: Path
    ready: Event = field(default_factory=Event)
    password: str | None = None


def results_to_text(results: list[DocumentResult], labels: bool = True) -> str:
    """UTF-8 text, with optional source/page labels; never includes error text."""
    chunks: list[str] = []
    multiple_files = len(results) > 1
    for result in results:
        for page in result.pages:
            if not page.text:
                continue
            if labels and (multiple_files or len(result.pages) > 1):
                title = result.path.name
                if len(result.pages) > 1:
                    title += f" — page {page.number}"
                chunks.append(f"── {title} ──\n{page.text}")
            else:
                chunks.append(page.text)
    return "\n\n".join(chunks).strip() + ("\n" if chunks else "")
