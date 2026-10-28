"""Reusable custom widgets and components for CommandCenter UI."""

from __future__ import annotations

from typing import Any
from PySide6.QtCore import Qt, QPoint, Signal
from PySide6.QtGui import QPainter, QPen, QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QListWidget, QTextEdit,
    QApplication, QAbstractItemView, QSizePolicy
)


class ReorderableList(QListWidget):
    """List with optimized pixel scrolling for cards."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragDropMode(QAbstractItemView.DragDropMode.NoDragDrop)
        self.setDragEnabled(False)
        self.setAcceptDrops(False)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setSpacing(8)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        # Cards are sized to the viewport width, so a horizontal bar would only show a few stray pixels.
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.verticalScrollBar().setSingleStep(24)


class EntryTextEdit(QTextEdit):
    """Read-only card text that forwards mouse wheel input to parent list."""

    def wheelEvent(self, event):
        parent = self.parentWidget()
        while parent is not None:
            if isinstance(parent, ReorderableList):
                parent.wheelEvent(event)
                return
            parent = parent.parentWidget()
        super().wheelEvent(event)


class DragHandle(QWidget):
    """Grip widget that tracks press-move-release gesture to reorder cards."""

    def __init__(self, entry_id: str, on_start, on_move, on_finish, parent=None):
        super().__init__(parent)
        self.entry_id = entry_id
        self.on_start = on_start
        self.on_move = on_move
        self.on_finish = on_finish
        self._press_position: QPoint | None = None
        self._mouse_grabbed = False
        self._drag_started = False
        self.setObjectName("dragHandle")
        self.setFixedSize(38, 28)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setMouseTracking(True)
        self.setToolTip("Arrastra para cambiar el orden")
        self.setAccessibleName("Reordenar nota")

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        is_hover = self.underMouse()
        
        bg_color = QColor("#14b8a6" if self._mouse_grabbed else ("#0f766e" if is_hover else "#0d4c46"))
        border_color = QColor("#2dd4bf" if is_hover else "#14b8a6")
        
        painter.setPen(QPen(border_color, 1.2))
        painter.setBrush(bg_color)
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 4, 4)
        
        # Grip dots/lines
        painter.setPen(QPen(QColor("#ffffff"), 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        center_x = self.width() / 2
        center_y = self.height() / 2
        for offset in (-4, 0, 4):
            y = int(center_y + offset)
            painter.drawLine(QPoint(int(center_x - 6), y), QPoint(int(center_x + 6), y))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            self._press_position = event.globalPosition().toPoint()
            self.grabMouse()
            self._mouse_grabbed = True
            self.update()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._press_position is not None and event.buttons() & Qt.MouseButton.LeftButton:
            position = event.globalPosition().toPoint()
            if (not self._drag_started
                    and (position - self._press_position).manhattanLength()
                    >= QApplication.startDragDistance()):
                self._drag_started = True
                self.on_start(self.entry_id, position)
            if self._drag_started:
                self.on_move(self.entry_id, position)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        position = event.globalPosition().toPoint()
        drag_started = self._drag_started
        self._press_position = None
        self._drag_started = False
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self._release_mouse()
        self.update()
        if drag_started:
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0, lambda: self.on_finish(self.entry_id, position))
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _release_mouse(self):
        if self._mouse_grabbed:
            self._mouse_grabbed = False
            self.releaseMouse()
            self.update()


class EmptyStateWidget(QWidget):
    """Displays a clean empty state with an icon, title, subtitle and action button."""

    action_clicked = Signal()

    def __init__(self, title: str, subtitle: str, button_text: str | None = None, parent=None):
        super().__init__(parent)
        self.setObjectName("emptyStateContainer")
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(10)
        layout.setContentsMargins(30, 40, 30, 40)

        icon_label = QLabel("📋")
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_label.setStyleSheet("font-size: 32pt; margin-bottom: 5px;")
        layout.addWidget(icon_label)

        self.title_label = QLabel(title)
        self.title_label.setObjectName("emptyStateTitle")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.title_label)

        self.subtitle_label = QLabel(subtitle)
        self.subtitle_label.setObjectName("emptyStateSubtitle")
        self.subtitle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.subtitle_label.setWordWrap(True)
        layout.addWidget(self.subtitle_label)

        if button_text:
            self.action_btn = QPushButton(button_text)
            self.action_btn.setObjectName("primaryButton")
            self.action_btn.setFixedWidth(200)
            self.action_btn.clicked.connect(self.action_clicked.emit)
            layout.addWidget(self.action_btn, 0, Qt.AlignmentFlag.AlignCenter)
