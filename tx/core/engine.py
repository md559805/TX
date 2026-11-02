from __future__ import annotations

import math
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Callable, Iterator

from PIL import Image, ImageChops, ImageOps, ImageSequence

from .hocr import hocr_to_text
from .models import (
    CancelledError,
    DocumentResult,
    ExtractionError,
    ExtractionOptions,
    PageResult,
    PasswordRequest,
    Progress,
)
from .text import clean_text, has_useful_text, merge_native_and_ocr, normalize_persian_ocr

try:
    from pillow_heif import register_heif_opener

    register_heif_opener()
    HEIF_AVAILABLE = True
except ImportError:  # The rest of the application still works without HEIC.
    HEIF_AVAILABLE = False

MAX_FRAMES = 500
ProgressCallback = Callable[[Progress], None]
PasswordProvider = Callable[[PasswordRequest], None]


def managed_tessdata_dir() -> Path:
    """Language packs installed by TX; never mixed implicitly with system packs."""
    return Path.home() / ".tx-ocr" / "tessdata"


def legacy_tessdata_dir() -> Path:
    """Reuse packs downloaded by the pre-rename app, if present."""
    return Path.home() / ".matn-ocr" / "tessdata"


def find_tesseract(explicit: str | None = None) -> str | None:
    if explicit:
        candidate = Path(explicit).expanduser()
        if candidate.is_file():
            return str(candidate.resolve())
        raise ExtractionError(
            "The saved Tesseract path no longer exists. Choose tesseract.exe again in OCR setup.",
            "executable",
        )
    env_path = os.environ.get("TESSERACT_CMD")
    if env_path and Path(env_path).is_file():
        return str(Path(env_path).resolve())
    found = shutil.which("tesseract")
    if found:
        return found
    candidates: list[Path] = []
    if os.name == "nt":
        for variable in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
            root = os.environ.get(variable)
            if root:
                base = Path(root)
                if variable == "LOCALAPPDATA":
                    base /= "Programs"
                candidates.append(base / "Tesseract-OCR" / "tesseract.exe")
    else:
        candidates.extend(
            Path(p)
            for p in ("/opt/homebrew/bin/tesseract", "/usr/local/bin/tesseract", "/usr/bin/tesseract")
        )
    return next((str(p) for p in candidates if p.is_file()), None)


def _creation_flags() -> int:
    return subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


def _check_cancel(cancel: threading.Event | None) -> None:
    if cancel is not None and cancel.is_set():
        raise CancelledError()


class TesseractRunner:
    """Small, cancellable subprocess wrapper. No shell and no cloud requests."""

    def __init__(self, options: ExtractionOptions):
        self.options = options
        self.executable = find_tesseract(options.tesseract_path)
        self.tessdata = options.tessdata_dir
        if not self.tessdata:
            for candidate_dir in (managed_tessdata_dir(), legacy_tessdata_dir()):
                if all((candidate_dir / f"{lang}.traineddata").is_file() for lang in options.languages):
                    self.tessdata = str(candidate_dir)
                    break
        if self.tessdata and not Path(self.tessdata).expanduser().is_dir():
            raise ExtractionError("The tessdata folder does not exist. Check OCR setup.", "languages")
        self._languages: tuple[str, ...] | None = None

    def _base(self) -> list[str]:
        if not self.executable:
            raise ExtractionError(
                "Tesseract is not installed or could not be found. Open OCR setup to install it "
                "or locate tesseract.exe. Existing PDF text can still be extracted without it.",
                "executable",
            )
        command = [self.executable]
        if self.tessdata:
            command += ["--tessdata-dir", str(Path(self.tessdata).expanduser())]
        return command

    def _run(
        self, arguments: list[str], cancel: threading.Event | None = None, timeout: int | None = None
    ) -> str:
        timeout = timeout or self.options.timeout
        environment = os.environ.copy()
        environment["OMP_THREAD_LIMIT"] = "1"
        command = self._base() + arguments
        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=environment,
                creationflags=_creation_flags(),
            )
        except OSError as exc:
            raise ExtractionError(f"Could not start Tesseract: {exc}", "executable") from exc
        started = time.monotonic()
        while True:
            if cancel is not None and cancel.is_set():
                self._kill(process)
                raise CancelledError()
            try:
                stdout, stderr = process.communicate(timeout=0.12)
                break
            except subprocess.TimeoutExpired:
                if time.monotonic() - started > timeout:
                    self._kill(process)
                    raise ExtractionError(
                        f"OCR exceeded the {timeout}-second page limit. Try a lower quality setting "
                        "or a smaller crop.",
                        "timeout",
                    )
        errors = stderr.decode("utf-8", errors="replace").strip()
        if process.returncode != 0:
            if "Error opening data file" in errors or "Failed loading language" in errors:
                raise ExtractionError(
                    "A required language pack is missing. Open OCR setup and download English "
                    "+ Persian, or install tesseract-ocr-eng and tesseract-ocr-fas.",
                    "languages",
                )
            detail = errors[-700:] if errors else f"exit code {process.returncode}"
            raise ExtractionError(f"Tesseract could not read this page: {detail}")
        return stdout.decode("utf-8", errors="replace")

    @staticmethod
    def _kill(process: subprocess.Popen) -> None:
        process.kill()
        try:
            process.communicate(timeout=3)
        except subprocess.TimeoutExpired:
            pass

    def languages(self) -> tuple[str, ...]:
        if self._languages is None:
            output = self._run(["--list-langs"], timeout=15)
            self._languages = tuple(
                line.strip() for line in output.splitlines()[1:] if re.fullmatch(r"[A-Za-z_]+", line.strip())
            )
        return self._languages

    def ensure_languages(self) -> None:
        installed = self.languages()
        missing = [lang for lang in self.options.languages if lang not in installed]
        if missing:
            names = ", ".join("Persian (fas)" if x == "fas" else "English (eng)" for x in missing)
            raise ExtractionError(
                f"Missing language pack: {names}. Open OCR setup to download the language files.",
                "languages",
            )

    def version(self) -> str:
        return self._run(["--version"], timeout=15).splitlines()[0]

    def orientation(self, image: Image.Image, cancel: threading.Event | None) -> int:
        if "osd" not in self.languages():
            return 0
        preview = image.copy()
        preview.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
        with tempfile.TemporaryDirectory(prefix="tx-osd-") as directory:
            path = Path(directory) / "page.png"
            preview.save(path, format="PNG", compress_level=1)
            try:
                output = self._run(
                    [str(path), "stdout", "-l", "osd", "--psm", "0"], cancel, timeout=30
                )
            except ExtractionError:
                # OSD often fails on short receipts or sparse text. This is not an OCR failure.
                return 0
        rotate = re.search(r"Rotate:\s*(\d+)", output)
        confidence = re.search(r"Orientation confidence:\s*([\d.]+)", output)
        if rotate and confidence and float(confidence.group(1)) >= 2.0:
            angle = int(rotate.group(1))
            if angle in (0, 90, 180, 270):
                return angle
        return 0

    def _ocr_image(self, image: Image.Image, cancel: threading.Event | None, psm: int = 3) -> str:
        with tempfile.TemporaryDirectory(prefix="tx-") as directory:
            path = Path(directory) / "page.png"
            image.save(path, format="PNG", compress_level=1)
            _check_cancel(cancel)
            output = self._run(
                [
                    str(path), "stdout",
                    "-l", self.options.language_code,
                    "--psm", str(psm),
                    "--dpi", str(self.options.dpi),
                    "-c", "preserve_interword_spaces=1",
                    "hocr",
                ],
                cancel,
            )
        # hOCR keeps RTL words as separate boxes. Rebuilding from those boxes
        # avoids Tesseract's plain-text writer gluing Persian words together.
        text = hocr_to_text(output)
        if "fas" in self.options.languages:
            text = normalize_persian_ocr(text)
        return text

    def recognize(self, image: Image.Image, cancel: threading.Event | None) -> str:
        self.ensure_languages()
        _check_cancel(cancel)
        if self.options.detect_orientation and min(image.size) > 80:
            angle = self.orientation(image, cancel)
            if angle:
                transpose = {
                    90: Image.Transpose.ROTATE_270,
                    180: Image.Transpose.ROTATE_180,
                    270: Image.Transpose.ROTATE_90,
                }[angle]
                image = image.transpose(transpose)
        _check_cancel(cancel)
        text = self._ocr_image(image, cancel, psm=3)

        # Persian-aware recovery. Do not thicken strokes in all directions:
        # that can erase the horizontal gaps between words. hOCR word boxes
        # restore spaces; a vertical-only boost helps thin strokes/dots.
        if self.options.enhance and "fas" in self.options.languages:
            small = None
            try:
                # Rendered PDF pages can be much larger than Tesseract's
                # Persian model likes. Try a bounded downscale early.
                if max(image.size) > 1800:
                    _check_cancel(cancel)
                    small = image.copy()
                    small.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
                    candidate = self._ocr_image(small, cancel, psm=6)
                    if _prefer_persian_candidate(text, candidate):
                        text = candidate
                _check_cancel(cancel)
                boosted = _vertical_stroke_boost(image)
                try:
                    candidate = self._ocr_image(boosted, cancel, psm=6)
                finally:
                    boosted.close()
                if _prefer_persian_candidate(text, candidate):
                    text = candidate
                if _needs_persian_retry(text):
                    _check_cancel(cancel)
                    candidate = self._ocr_image(image, cancel, psm=6)
                    if _prefer_persian_candidate(text, candidate):
                        text = candidate
                if small is not None and _needs_persian_retry(text):
                    _check_cancel(cancel)
                    boosted_small = _vertical_stroke_boost(small)
                    try:
                        candidate = self._ocr_image(boosted_small, cancel, psm=6)
                    finally:
                        boosted_small.close()
                    if _prefer_persian_candidate(text, candidate):
                        text = candidate
            finally:
                if small is not None:
                    small.close()
        return text


def _persian_letters(value: str) -> int:
    return sum(1 for c in value if "\u0600" <= c <= "\u06ff" and c.isalpha())


def _alpha_count(value: str) -> int:
    return sum(c.isalpha() for c in value)


def _needs_persian_retry(value: str) -> bool:
    persian = _persian_letters(value)
    if persian < max(8, _alpha_count(value) * 0.05):
        return True
    # A very long unbroken Persian token is a common sign of glued words.
    return any(len(token.replace("\u200c", "")) >= 20 for token in re.findall(r"[\u0600-\u06ff\u200c]+", value))


def _prefer_persian_candidate(current: str, candidate: str) -> bool:
    if not candidate:
        return False
    if not current:
        return True
    current_fa, candidate_fa = _persian_letters(current), _persian_letters(candidate)
    current_alpha, candidate_alpha = _alpha_count(current), _alpha_count(candidate)
    if candidate_fa > current_fa and candidate_alpha >= max(1, current_alpha * 0.6):
        return True
    if candidate_fa == current_fa and candidate_fa > 0 and candidate_alpha >= current_alpha * 0.9:
        current_words = len(re.findall(r"[\u0600-\u06ff\u200c]+", current))
        candidate_words = len(re.findall(r"[\u0600-\u06ff\u200c]+", candidate))
        return candidate_words > current_words
    return False


def _vertical_stroke_boost(image: Image.Image) -> Image.Image:
    """Thicken strokes vertically by one pixel without closing word gaps.

    A square MinFilter thickens horizontally too, which can merge Persian
    words. Offsetting only up/down preserves the horizontal whitespace that
    separates words while making thin horizontal strokes/dots easier to read.
    """
    fill = (255, 255, 255) if image.mode == "RGB" else 255
    padded = ImageOps.expand(image, border=2, fill=fill)
    up = ImageChops.offset(padded, 0, 1)
    down = ImageChops.offset(padded, 0, -1)
    dark = ImageChops.darker(ImageChops.darker(padded, up), down)
    result = dark.crop((2, 2, image.width + 2, image.height + 2))
    for temporary in (padded, up, down, dark):
        temporary.close()
    return result


def _layout_is_complex(boxes, size) -> bool:
    """Heuristic: many distinct left edges / short lines => poster or columns."""
    if not boxes or len(boxes) < 4:
        return False
    try:
        import statistics

        lefts = [min(p[0] for p in box) for box in boxes if box]
        widths = [max(p[0] for p in box) - min(p[0] for p in box) for box in boxes if box]
        if len(lefts) < 4:
            return False
        spread = statistics.pstdev(lefts)
        median_width = statistics.median(widths)
        return spread > 0.12 * size[0] or median_width < 0.55 * size[0]
    except Exception:
        return False


def _candidate_score(value: str) -> float:
    """Conservative quality score used only to choose between two OCR engines."""
    if not value:
        return -1.0
    fa = sum(1 for c in value if "\u0600" <= c <= "\u06ff" and c.isalpha())
    alpha = sum(c.isalpha() for c in value)
    zwnj = value.count("\u200c")
    words = len(re.findall(r"[\w\u200c]+", value))
    garbage = len(re.findall(r"\b[A-Za-z]{1,3}\b", value))
    glued = sum(1 for t in re.findall(r"[\u0600-\u06ff\u200c]+", value) if len(t.replace("\u200c", "")) >= 18)
    return fa + 0.5 * (alpha - fa) + 2.0 * zwnj + 0.2 * words - 1.5 * garbage - 3.0 * glued


def supported_extensions() -> set[str]:
    extensions = set(Image.registered_extensions())
    # Pillow's PDF/EPS/PS plugins need external Ghostscript and are not image inputs here.
    extensions -= {".pdf", ".eps", ".ps"}
    extensions.add(".pdf")
    return extensions


def file_kind(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        return "pdf"
    if path.suffix.lower() in supported_extensions():
        return "image"
    raise ExtractionError(
        f"Unsupported file type: {path.suffix or '(no extension)'}. "
        "Use PDF or an image format supported by Pillow (PNG, JPEG, TIFF, WebP, HEIC, and more).",
        "format",
    )


def _flatten(image: Image.Image) -> Image.Image:
    image = ImageOps.exif_transpose(image)
    if image.mode in ("RGBA", "LA") or "transparency" in image.info:
        rgba = image.convert("RGBA")
        background = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        flattened = Image.alpha_composite(background, rgba).convert("RGB")
        rgba.close()
        background.close()
        return flattened
    return image.convert("RGB")


def prepare_image(image: Image.Image, options: ExtractionOptions) -> Image.Image:
    """Conservative cleanup: no thresholding, which can erase Persian dots."""
    result = _flatten(image)
    if options.enhance:
        gray = ImageOps.grayscale(result)
        result.close()
        result = ImageOps.autocontrast(gray, cutoff=1)
        gray.close()
    longest = max(result.size)
    scale = 1.0
    if longest < 1200:
        scale = min(2.0, 2400 / longest)
    scale = min(scale, math.sqrt(options.max_pixels / (result.width * result.height)))
    if abs(scale - 1.0) > 0.01:
        size = (max(1, round(result.width * scale)), max(1, round(result.height * scale)))
        resized = result.resize(size, Image.Resampling.LANCZOS)
        result.close()
        result = resized
    return result


def iter_image_frames(path: Path) -> Iterator[tuple[int, int, Image.Image]]:
    try:
        with Image.open(path) as source:
            total = getattr(source, "n_frames", 1)
            if total > MAX_FRAMES:
                raise ExtractionError(
                    f"This image has {total} frames. The safety limit is {MAX_FRAMES}; split it first.",
                    "format",
                )
            for index, frame in enumerate(ImageSequence.Iterator(source), start=1):
                yield index, total, frame.copy()
    except ExtractionError:
        raise
    except Image.DecompressionBombError as exc:
        raise ExtractionError("This image is too large to decode safely. Resize or crop it first.", "size") from exc
    except Exception as exc:
        raise ExtractionError(
            f"Could not open the image: {exc}. If this is a camera raw file, export it as JPEG or TIFF first.",
            "format",
        ) from exc


def open_pdf(
    path: Path,
    password: str | None = None,
    provider: PasswordProvider | None = None,
    cancel: threading.Event | None = None,
):
    import pypdfium2 as pdfium

    try:
        document = pdfium.PdfDocument(str(path), password=password)
        document.init_forms()
        return document
    except pdfium.PdfiumError as exc:
        _check_cancel(cancel)
        if provider is None:
            raise ExtractionError(
                "This PDF cannot be opened. It may need a password, or it may be damaged.", "password"
            ) from exc
    last_error: Exception | None = None
    for _ in range(3):
        request = PasswordRequest(path)
        provider(request)
        while not request.ready.wait(0.1):
            _check_cancel(cancel)
        _check_cancel(cancel)
        if request.password is None:
            raise ExtractionError("A password is required to open this PDF.", "password")
        try:
            document = pdfium.PdfDocument(str(path), password=request.password)
            document.init_forms()
            return document
        except pdfium.PdfiumError as exc:
            last_error = exc
    raise ExtractionError("The PDF password was not accepted after three attempts.", "password") from last_error


def render_pdf_page(page, dpi: int, max_pixels: int) -> Image.Image:
    import pypdfium2 as pdfium

    width, height = page.get_size()
    if width <= 0 or height <= 0:
        raise ExtractionError("The PDF page has invalid dimensions.")
    scale = min(dpi / 72.0, math.sqrt(max_pixels / (width * height)), 12000 / max(width, height))
    bitmap = page.render(
        scale=scale,
        fill_color=(255, 255, 255, 255),
        draw_annots=True,
        may_draw_forms=True,
        rev_byteorder=True,
    )
    try:
        return bitmap.to_pil().convert("RGB")
    finally:
        bitmap.close()


def _large_image_coverage(page) -> float:
    """Detect scans or mixed pages with a large raster image, without decoding it."""
    import pypdfium2.raw as raw

    width, height = page.get_size()
    page_area = max(1.0, width * height)
    coverage = 0.0
    try:
        for obj in page.get_objects(filter=(raw.FPDF_PAGEOBJ_IMAGE,)):
            left, bottom, right, top = obj.get_bounds()
            clipped_w = max(0.0, min(right, width) - max(left, 0.0))
            clipped_h = max(0.0, min(top, height) - max(bottom, 0.0))
            area = clipped_w * clipped_h / page_area
            if area > 0.02:
                coverage += area
    except Exception:
        return 0.0
    return min(1.0, coverage)


def preview_document(path: Path, page_number: int = 1, password: str | None = None) -> tuple[Image.Image, int]:
    """Return a bounded preview and the total page/frame count."""
    path = Path(path)
    if file_kind(path) == "image":
        with Image.open(path) as source:
            total = getattr(source, "n_frames", 1)
            source.seek(min(max(0, page_number - 1), total - 1))
            result = _flatten(source)
    else:
        document = open_pdf(path, password=password)
        page = None
        try:
            total = len(document)
            if not 1 <= page_number <= total:
                raise ExtractionError("That PDF page does not exist.")
            page = document[page_number - 1]
            result = render_pdf_page(page, 110, 2_000_000)
        finally:
            if page is not None:
                page.close()
            document.close()
    result.thumbnail((1100, 1400), Image.Resampling.LANCZOS)
    return result, total


def preview_image(path: Path, page_number: int = 1, password: str | None = None) -> Image.Image:
    return preview_document(path, page_number, password)[0]


class ExtractionService:
    def __init__(self, options: ExtractionOptions | None = None):
        self.options = options or ExtractionOptions()
        self._runner: TesseractRunner | None = None
        self._rapid = None

    def runner(self) -> TesseractRunner:
        if self._runner is None:
            self._runner = TesseractRunner(self.options)
        return self._runner

    def rapid_runner(self):
        if self._rapid is None:
            from .rapid import RapidRunner

            self._rapid = RapidRunner()
        return self._rapid

    def diagnose(self) -> dict:
        from .rapid import models_available

        models_present = models_available()
        dependencies_present = True
        try:
            import rapidocr  # noqa: F401
            import onnxruntime  # noqa: F401
        except ImportError:
            dependencies_present = False
        rapid_ready = models_present and dependencies_present and self.options.engine != "tesseract"
        if not models_present:
            rapid_reason = "Bundled RapidOCR model files are missing."
        elif not dependencies_present:
            rapid_reason = "RapidOCR Python packages are missing. Run: python -m pip install -r requirements.txt"
        elif self.options.engine == "tesseract":
            rapid_reason = "RapidOCR is installed but the selected engine is Tesseract."
        else:
            rapid_reason = None
        info: dict = {
            "engine": self.options.engine,
            "rapid": {
                "available": rapid_ready,
                "models": str(Path(__file__).resolve().parents[1] / "assets" / "models"),
                "models_present": models_present,
                "dependencies_present": dependencies_present,
                "reason": rapid_reason,
            },
        }
        try:
            runner = self.runner()
            if not runner.executable:
                info.update(available=rapid_ready, reason=None if rapid_ready else "Tesseract was not found.", languages=[], tesseract=False)
                return info
            languages = runner.languages()
            missing = [x for x in self.options.languages if x not in languages]
            info.update(
                available=rapid_ready or not missing,
                path=runner.executable,
                version=runner.version(),
                languages=list(languages),
                tessdata=runner.tessdata,
                missing=missing if not rapid_ready else [],
                tesseract=True,
                reason=None if (rapid_ready or not missing) else "Language packs are missing.",
            )
            return info
        except ExtractionError as exc:
            info.update(available=rapid_ready, reason=None if rapid_ready else str(exc), languages=[], tesseract=False)
            return info

    def _recognize(self, image: Image.Image, cancel: threading.Event | None) -> str:
        """Route to the selected engine. Auto prefers the bundled layout-aware
        RapidOCR models for complex pages and Tesseract for clean scans."""
        from .rapid import models_available

        engine = self.options.engine
        if engine == "tesseract":
            prepared = prepare_image(image, self.options)
            try:
                return self.runner().recognize(prepared, cancel)
            finally:
                prepared.close()
        if engine == "rapid":
            return self.rapid_runner().recognize(image, cancel)
        # auto
        rapid_ok = models_available()
        if rapid_ok:
            try:
                import rapidocr  # noqa: F401
                import onnxruntime  # noqa: F401
            except ImportError:
                rapid_ok = False
        tess_ok = False
        try:
            tess_ok = bool(self.runner().executable)
            if tess_ok:
                self.runner().ensure_languages()
        except ExtractionError:
            tess_ok = False
        if not rapid_ok and not tess_ok:
            raise ExtractionError(
                "No OCR engine is ready. Reinstall TX to restore the bundled models, or install Tesseract "
                "and the English/Persian language packs via OCR setup.",
                "engine",
            )
        if rapid_ok and not tess_ok:
            return self.rapid_runner().recognize(image, cancel)
        if tess_ok and not rapid_ok:
            prepared = prepare_image(image, self.options)
            try:
                return self.runner().recognize(prepared, cancel)
            finally:
                prepared.close()
        # Both available: RapidOCR handles posters/multi-column designs much
        # better; Tesseract is still stronger on clean, single-column scans.
        lines, boxes, scores = self.rapid_runner().recognize_detailed(image, cancel)
        complex_layout = len(lines) >= 8 or _layout_is_complex(boxes, image.size)
        if complex_layout:
            lines = self._refine_numeric_lines(image, lines, boxes, cancel)
            return "\n".join(lines)
        rapid_text = "\n".join(lines)
        prepared = prepare_image(image, self.options)
        try:
            tess_text = self.runner().recognize(prepared, cancel)
        finally:
            prepared.close()
        if _candidate_score(tess_text) >= _candidate_score(rapid_text):
            return tess_text
        return rapid_text

    def extract(
        self,
        path: str | Path,
        cancel: threading.Event | None = None,
        progress: ProgressCallback | None = None,
        password_provider: PasswordProvider | None = None,
        file_index: int = 0,
        file_count: int = 1,
        page_callback: Callable[[PageResult], None] | None = None,
    ) -> DocumentResult:
        path = Path(path).expanduser().resolve()
        started = time.monotonic()
        result = DocumentResult(path=path)
        if not path.is_file():
            result.error = "The file no longer exists or is not a regular file."
            return result

        def report(page: int, total: int, done: bool, message: str) -> None:
            if done and page_callback and result.pages:
                page_callback(result.pages[-1])
            if progress:
                fraction = (page - (0 if done else 0.5)) / max(1, total)
                progress(Progress(file_index, file_count, page, total, fraction, message))

        try:
            _check_cancel(cancel)
            kind = file_kind(path)
            if kind == "image":
                self._extract_images(path, result, cancel, report)
            else:
                self._extract_pdf(path, result, cancel, report, password_provider)
        except CancelledError:
            raise
        except ExtractionError as exc:
            result.error = str(exc)
        except Exception as exc:
            result.error = f"Could not process this file: {exc}"
        result.elapsed = time.monotonic() - started
        return result

    def _refine_numeric_lines(self, image, lines, boxes, cancel):
        """Use Tesseract on numeric crop lines when it recovers more digits.

        RapidOCR's Arabic-script recognizer sometimes drops a digit in prices or
        size ranges. Tesseract is conservative here: we only replace a line when
        the crop yields strictly more digits and the surrounding letters agree.
        """
        try:
            runner = self.runner()
            if not runner.executable:
                return lines
            runner.ensure_languages()
        except ExtractionError:
            return lines
        digit_re = re.compile(r"[0-9۰-۹٠-٩]")
        out = list(lines)
        for index, (line, box) in enumerate(zip(lines, boxes)):
            _check_cancel(cancel)
            if not box or not digit_re.search(line):
                continue
            try:
                import numpy as np

                pts = np.asarray(box)
                x0, y0 = pts.min(axis=0).astype(int)
                x1, y1 = pts.max(axis=0).astype(int)
                crop = image.crop((max(0, x0 - 10), max(0, y0 - 10), min(image.width, x1 + 10), min(image.height, y1 + 10)))
                crop = ImageOps.expand(crop, border=16, fill="white")
                factor = max(1.0, 96 / max(1, crop.height))
                if factor > 1.01:
                    crop = crop.resize((int(crop.width * factor), int(crop.height * factor)), Image.Resampling.LANCZOS)
                with tempfile.TemporaryDirectory(prefix="tx-num-") as directory:
                    path = Path(directory) / "line.png"
                    crop.save(path, format="PNG", compress_level=1)
                    lang = "fas+eng" if "fas" in self.options.languages else "eng"
                    candidate = runner._run(
                        [str(path), "stdout", "-l", lang,
                         "--psm", "7", "-c", "preserve_interword_spaces=1"],
                        cancel, timeout=30,
                    )
                crop.close()
                from .rapid import normalize_persian_line

                candidate = normalize_persian_line(normalize_persian_ocr(candidate).replace("\n", " ").strip())
                base_digits = len(digit_re.findall(line))
                cand_digits = len(digit_re.findall(candidate))
                if cand_digits > base_digits:
                    import difflib

                    base_letters = re.sub(r"[^A-Za-z\u0600-\u06ff]", "", line)
                    cand_letters = re.sub(r"[^A-Za-z\u0600-\u06ff]", "", candidate)
                    similarity = difflib.SequenceMatcher(None, base_letters, cand_letters).ratio()
                    if len(cand_letters) >= max(1, int(len(base_letters) * 0.7)) and similarity >= 0.75:
                        # Prefer Rapid's letters, but borrow the recovered digit
                        # groups from Tesseract in order (e.g. ۳۸ تا ۴ -> ۳۸ تا ۵۴).
                        base_groups = re.findall(r"[0-9۰-۹٠-٩]+", line)
                        cand_groups = re.findall(r"[0-9۰-۹٠-٩]+", candidate)
                        if len(cand_groups) == len(base_groups):
                            it = iter(cand_groups)
                            out[index] = re.sub(r"[0-9۰-۹٠-٩]+", lambda m: next(it), line)
                        elif similarity >= 0.88:
                            out[index] = candidate
            except Exception:
                continue
        return out

    def _extract_images(self, path, result, cancel, report) -> None:
        for number, total, image in iter_image_frames(path):
            report(number, total, False, f"Reading image {number} of {total}")
            prepared = None
            try:
                _check_cancel(cancel)
                prepared = _flatten(image)
                text = self._recognize(prepared, cancel)
                result.pages.append(PageResult(number, text, "ocr" if text else "empty"))
            except CancelledError:
                raise
            except Exception as exc:
                result.pages.append(PageResult(number, method="error", error=str(exc)))
            finally:
                image.close()
                if prepared is not None:
                    prepared.close()
            report(number, total, True, f"Finished image {number} of {total}")

    def _extract_pdf(self, path, result, cancel, report, password_provider) -> None:
        document = open_pdf(path, provider=password_provider, cancel=cancel)
        page = None
        textpage = None
        rendered = None
        prepared = None
        try:
            total = len(document)
            if total == 0:
                result.error = "This PDF has no pages."
                return
            try:
                document.init_forms()
            except Exception:
                pass
            for number in range(1, total + 1):
                report(number, total, False, f"Reading page {number} of {total}")
                _check_cancel(cancel)
                try:
                    page = document[number - 1]
                    native = ""
                    try:
                        textpage = page.get_textpage()
                        native = clean_text(textpage.get_text_range())
                    except Exception:
                        native = ""
                    finally:
                        if textpage is not None:
                            textpage.close()
                            textpage = None
                    useful = has_useful_text(native)
                    needs_ocr = not self.options.smart_pdf or not useful
                    if self.options.smart_pdf and useful:
                        needs_ocr = _large_image_coverage(page) >= 0.30
                    if needs_ocr:
                        _check_cancel(cancel)
                        rendered = render_pdf_page(page, self.options.dpi, self.options.max_pixels)
                        prepared = _flatten(rendered)
                        ocr = self._recognize(prepared, cancel)
                        if useful:
                            text = merge_native_and_ocr(native, ocr)
                            method = "native+ocr" if text else "empty"
                        else:
                            text = ocr
                            method = "ocr" if text else "empty"
                    else:
                        text, method = native, "native"
                    result.pages.append(PageResult(number, text, method))
                except CancelledError:
                    raise
                except Exception as exc:
                    result.pages.append(PageResult(number, method="error", error=str(exc)))
                finally:
                    for resource in (prepared, rendered, page):
                        if resource is not None:
                            resource.close()
                    prepared = rendered = page = None
                report(number, total, True, f"Finished page {number} of {total}")
        finally:
            document.close()
