from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QFontMetrics, QMouseEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .icons import make_icon
from .theme import repolish, set_surface


def human_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GB"


class DropZone(QFrame):
    files_dropped = Signal(list)
    clicked = Signal()

    def __init__(self, colors: dict, parent=None):
        super().__init__(parent)
        self.colors = colors
        self.setObjectName("DropZone")
        self.setAcceptDrops(True)
        self.setMinimumHeight(118)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 18, 16, 18)
        layout.setSpacing(7)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon = QLabel()
        self.icon.setPixmap(make_icon("upload", colors["accent"], 28).pixmap(28, 28))
        self.icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title = QLabel("Drop files here")
        title.setObjectName("H2")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle = QLabel("or click to browse · images & PDF")
        subtitle.setObjectName("Muted")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.icon)
        layout.addWidget(title)
        layout.addWidget(subtitle)

    def set_active(self, active: bool) -> None:
        self.setProperty("active", active)
        repolish(self)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.set_active(True)
        else:
            event.ignore()

    def dragLeaveEvent(self, event) -> None:
        self.set_active(False)
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        self.set_active(False)
        paths = [Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()]
        if paths:
            self.files_dropped.emit(paths)
            event.acceptProposedAction()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class FileRow(QFrame):
    clicked = Signal(object)
    remove_requested = Signal(object)

    def __init__(self, path: Path, colors: dict, parent=None):
        super().__init__(parent)
        self.path = path
        self.colors = colors
        self.setObjectName("FileRow")
        self.setProperty("selected", False)
        self.setFixedHeight(64)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 8, 8)
        layout.setSpacing(10)
        is_pdf = path.suffix.lower() == ".pdf"
        self.type_icon = QLabel()
        self.type_icon.setPixmap(
            make_icon("file" if is_pdf else "image", colors["accent"] if is_pdf else colors["muted"], 22).pixmap(22, 22)
        )
        self.type_icon.setFixedSize(28, 28)
        self.type_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.type_icon.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        text_box = QVBoxLayout()
        text_box.setSpacing(2)
        self.name_label = QLabel(path.name)
        self.name_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.name_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        font = self.name_label.font()
        font.setWeight(font.Weight.DemiBold)
        self.name_label.setFont(font)
        self.meta_label = QLabel()
        self.meta_label.setObjectName("Tiny")
        self.meta_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        try:
            size = human_size(path.stat().st_size)
        except OSError:
            size = "missing"
        self.meta_label.setText(f"{'PDF' if is_pdf else path.suffix.lstrip('.').upper() or 'IMAGE'} · {size}")
        text_box.addWidget(self.name_label)
        text_box.addWidget(self.meta_label)
        self.dot = QLabel()
        self.dot.setFixedSize(8, 8)
        self.dot.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.remove_button = QPushButton()
        self.remove_button.setObjectName("IconOnly")
        self.remove_button.setIcon(make_icon("close", colors["muted"], 14))
        self.remove_button.setFixedSize(26, 26)
        self.remove_button.setToolTip("Remove file")
        self.remove_button.setCursor(Qt.CursorShape.ArrowCursor)
        self.remove_button.clicked.connect(lambda: self.remove_requested.emit(self.path))
        layout.addWidget(self.type_icon)
        layout.addLayout(text_box, 1)
        layout.addWidget(self.dot)
        layout.addWidget(self.remove_button)
        self.set_status("queued")

    def resizeEvent(self, event) -> None:
        metrics = QFontMetrics(self.name_label.font())
        self.name_label.setText(metrics.elidedText(self.path.name, Qt.TextElideMode.ElideMiddle, max(40, self.name_label.width())))
        super().resizeEvent(event)

    def set_selected(self, selected: bool) -> None:
        self.setProperty("selected", selected)
        repolish(self)

    def set_status(self, status: str, detail: str | None = None) -> None:
        self.status = status
        color = {
            "queued": self.colors["muted"],
            "reading": self.colors["accent"],
            "done": self.colors["accent"],
            "warning": self.colors["warning"],
            "error": self.colors["danger"],
        }.get(status, self.colors["muted"])
        self.dot.setStyleSheet(f"background: {color}; border-radius: 4px;")
        self.dot.setToolTip(detail or status.capitalize())
        if detail:
            self.meta_label.setText(detail)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.path)
        super().mousePressEvent(event)


class FileList(QWidget):
    files_changed = Signal()
    selection_changed = Signal(object)

    def __init__(self, colors: dict, parent=None):
        super().__init__(parent)
        self.colors = colors
        self.rows: dict[Path, FileRow] = {}
        self.selected: Path | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.scroll = QScrollArea()
        self.scroll.setObjectName("FileListScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.container = QWidget()
        self.container.setObjectName("FileListContainer")
        set_surface(self.container, colors["surface"])
        set_surface(self.scroll.viewport(), colors["surface"])
        self.box = QVBoxLayout(self.container)
        self.box.setContentsMargins(0, 0, 4, 0)
        self.box.setSpacing(6)
        self.box.addStretch(1)
        self.scroll.setWidget(self.container)
        layout.addWidget(self.scroll)
        self.empty = QLabel("Your files will appear here")
        self.empty.setObjectName("Muted")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty.setMinimumHeight(90)
        self.box.insertWidget(0, self.empty)
        self.setMinimumHeight(88)

    def add_paths(self, paths: list[Path]) -> int:
        added = 0
        for raw in paths:
            path = Path(raw).expanduser().resolve()
            if not path.is_file() or path in self.rows:
                continue
            row = FileRow(path, self.colors)
            row.clicked.connect(self.select)
            row.remove_requested.connect(self.remove)
            self.rows[path] = row
            self.box.insertWidget(self.box.count() - 1, row)
            added += 1
        if added:
            self.empty.hide()
            if self.selected is None:
                self.select(next(iter(self.rows)))
            self.files_changed.emit()
        return added

    def select(self, path: Path) -> None:
        if path not in self.rows:
            return
        self.selected = path
        for key, row in self.rows.items():
            row.set_selected(key == path)
        self.selection_changed.emit(path)

    def remove(self, path: Path) -> None:
        row = self.rows.pop(path, None)
        if row is None:
            return
        self.box.removeWidget(row)
        row.deleteLater()
        if self.selected == path:
            self.selected = next(iter(self.rows), None)
            if self.selected:
                self.select(self.selected)
            else:
                self.selection_changed.emit(None)
        if not self.rows:
            self.empty.show()
        self.files_changed.emit()

    def clear(self) -> None:
        for path in list(self.rows):
            self.remove(path)

    def paths(self) -> list[Path]:
        return list(self.rows)

    def set_status(self, path: Path, status: str, detail: str | None = None) -> None:
        row = self.rows.get(Path(path).resolve())
        if row:
            row.set_status(status, detail)

    def sizeHint(self) -> QSize:
        return QSize(320, 220)


class EmptyState(QWidget):
    def __init__(self, colors: dict, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(12)
        icon = QLabel()
        icon.setPixmap(make_icon("text", colors["muted"], 44).pixmap(44, 44))
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title = QLabel("Drop a file. Keep the words.")
        self.title.setObjectName("H1")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.subtitle = QLabel("Images and PDFs · English + فارسی\nProcessed on your device, not in the cloud.")
        self.subtitle.setObjectName("Muted")
        self.subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon)
        layout.addWidget(self.title)
        layout.addWidget(self.subtitle)

    def set_message(self, title: str, subtitle: str) -> None:
        self.title.setText(title)
        self.subtitle.setText(subtitle)
