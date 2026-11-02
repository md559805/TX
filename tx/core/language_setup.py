from __future__ import annotations

import hashlib
import json
import tempfile
import threading
import urllib.request
from pathlib import Path
from typing import Callable

from .engine import managed_tessdata_dir
from .models import ExtractionError

SetupProgress = Callable[[str, float], None]


def install_language_packs(
    destination: Path | None = None,
    cancel: threading.Event | None = None,
    progress: SetupProgress | None = None,
) -> Path:
    """Explicit, consent-based download of pinned official Tesseract fast models.

    Files are checksummed and atomically replaced. Document contents are never
    sent anywhere. Existing valid packs are reused, so retries are inexpensive.
    """
    destination = Path(destination) if destination else managed_tessdata_dir()
    destination.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(Path(__file__).with_name("language_packs.json").read_text(encoding="utf-8"))
    total_bytes = sum(item["bytes"] for item in manifest.values())
    completed_bytes = 0
    for index, (language, item) in enumerate(manifest.items()):
        if cancel is not None and cancel.is_set():
            raise ExtractionError("Language download cancelled.", "cancelled")
        target = destination / f"{language}.traineddata"
        label = {"eng": "English", "fas": "Persian", "osd": "Orientation"}[language]
        if target.is_file() and _sha256(target) == item["sha256"]:
            completed_bytes += item["bytes"]
            if progress:
                progress(f"{label} is already installed.", completed_bytes / total_bytes)
            continue
        if progress:
            progress(f"Downloading {label} language pack…", completed_bytes / total_bytes)
        temporary: Path | None = None
        try:
            request = urllib.request.Request(
                item["url"], headers={"User-Agent": "TX/1.1 language-pack-setup"}
            )
            digest = hashlib.sha256()
            received = 0
            with urllib.request.urlopen(request, timeout=45) as response:
                with tempfile.NamedTemporaryFile(
                    dir=destination, prefix=f".{language}-", suffix=".part", delete=False
                ) as stream:
                    temporary = Path(stream.name)
                    while chunk := response.read(256 * 1024):
                        if cancel is not None and cancel.is_set():
                            raise ExtractionError("Language download cancelled.", "cancelled")
                        received += len(chunk)
                        if received > item["bytes"] + 1024:
                            raise ExtractionError("The language download was larger than expected.")
                        digest.update(chunk)
                        stream.write(chunk)
                        if progress:
                            progress(
                                f"Downloading {label} language pack…",
                                min(0.99, (completed_bytes + received) / total_bytes),
                            )
            if received != item["bytes"] or digest.hexdigest() != item["sha256"]:
                raise ExtractionError(
                    f"The {label} pack failed its integrity check. Nothing was replaced; please retry."
                )
            temporary.replace(target)
            temporary = None
            completed_bytes += item["bytes"]
            if progress:
                progress(f"{label} installed.", completed_bytes / total_bytes)
        except ExtractionError:
            raise
        except Exception as exc:
            raise ExtractionError(
                f"Could not download {label}. Check your internet connection and try again. {exc}"
            ) from exc
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    if progress:
        progress("English, Persian, and orientation packs are ready.", 1.0)
    return destination


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(256 * 1024):
            digest.update(chunk)
    return digest.hexdigest()
