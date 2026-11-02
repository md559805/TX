from __future__ import annotations

import threading
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot

from ..core.engine import ExtractionService
from ..core.language_setup import install_language_packs
from ..core.models import CancelledError, ExtractionOptions


class ExtractionWorker(QObject):
    file_started = Signal(int, str)
    page_finished = Signal(int, object)
    file_finished = Signal(int, object)
    progress = Signal(float, str)
    password_requested = Signal(object)
    finished = Signal(object, bool)
    failed = Signal(str)

    def __init__(self, paths: list[Path], options: ExtractionOptions):
        super().__init__()
        self.paths = paths
        self.options = options
        self.cancel_event = threading.Event()

    def cancel(self) -> None:
        self.cancel_event.set()

    @Slot()
    def run(self) -> None:
        results = []
        service = ExtractionService(self.options)
        cancelled = False
        try:
            for index, path in enumerate(self.paths):
                if self.cancel_event.is_set():
                    cancelled = True
                    break
                self.file_started.emit(index, str(path))

                def report(p, index=index) -> None:
                    overall = (index + max(0.0, min(1.0, p.fraction))) / max(1, len(self.paths))
                    self.progress.emit(overall, f"{path.name} · {p.message}")

                def page_done(page, index=index) -> None:
                    self.page_finished.emit(index, page)

                try:
                    result = service.extract(
                        path,
                        cancel=self.cancel_event,
                        progress=report,
                        password_provider=lambda request: self.password_requested.emit(request),
                        file_index=index,
                        file_count=len(self.paths),
                        page_callback=page_done,
                    )
                except CancelledError:
                    cancelled = True
                    break
                results.append(result)
                self.file_finished.emit(index, result)
        except Exception as exc:
            self.failed.emit(str(exc))
        if self.cancel_event.is_set():
            cancelled = True
        self.progress.emit(1.0 if not cancelled else 0.0, "Cancelled" if cancelled else "Done")
        self.finished.emit(results, cancelled)


class LanguageSetupWorker(QObject):
    progress = Signal(str, float)
    finished = Signal(str)
    failed = Signal(str)

    def __init__(self, destination: Path | None = None):
        super().__init__()
        self.destination = destination
        self.cancel_event = threading.Event()

    def cancel(self) -> None:
        self.cancel_event.set()

    @Slot()
    def run(self) -> None:
        try:
            path = install_language_packs(
                destination=self.destination,
                cancel=self.cancel_event,
                progress=lambda message, fraction: self.progress.emit(message, fraction),
            )
            self.finished.emit(str(path))
        except Exception as exc:
            self.failed.emit(str(exc))
