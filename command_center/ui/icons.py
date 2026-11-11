"""Small line icons drawn with QPainter, so the UI ships no image files or emoji."""

from __future__ import annotations

import tempfile
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap, QPolygonF

# Every icon is drawn on a 16x16 grid with the same 1.5 px round stroke.
GRID = 16.0


def _play(painter: QPainter, color: QColor) -> None:
    painter.setBrush(color)
    painter.drawPolygon(QPolygonF([QPointF(5.2, 3.6), QPointF(12.2, 8.0), QPointF(5.2, 12.4)]))


def _plus(painter: QPainter, color: QColor) -> None:
    painter.drawLine(QPointF(8, 3.5), QPointF(8, 12.5))
    painter.drawLine(QPointF(3.5, 8), QPointF(12.5, 8))


def _copy(painter: QPainter, color: QColor) -> None:
    painter.drawRoundedRect(QRectF(5.5, 5.5, 8, 8), 1.5, 1.5)
    back = QPainterPath()
    back.moveTo(10.5, 5.5)
    back.lineTo(10.5, 3.5)
    back.quadTo(10.5, 2.5, 9.5, 2.5)
    back.lineTo(3.5, 2.5)
    back.quadTo(2.5, 2.5, 2.5, 3.5)
    back.lineTo(2.5, 9.5)
    back.quadTo(2.5, 10.5, 3.5, 10.5)
    back.lineTo(5.5, 10.5)
    painter.drawPath(back)


def _edit(painter: QPainter, color: QColor) -> None:
    body = QPainterPath()
    body.moveTo(3.0, 13.0)
    body.lineTo(3.6, 10.4)
    body.lineTo(10.6, 3.4)
    body.lineTo(12.6, 5.4)
    body.lineTo(5.6, 12.4)
    body.closeSubpath()
    painter.drawPath(body)
    painter.drawLine(QPointF(9.2, 4.8), QPointF(11.2, 6.8))


def _more(painter: QPainter, color: QColor) -> None:
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(color)
    for x in (3.5, 8.0, 12.5):
        painter.drawEllipse(QPointF(x, 8.0), 1.25, 1.25)


def _external(painter: QPainter, color: QColor) -> None:
    painter.drawPolyline(QPolygonF([QPointF(6.5, 4), QPointF(12, 4), QPointF(12, 9.5)]))
    painter.drawLine(QPointF(12, 4), QPointF(4.5, 11.5))


def _search(painter: QPainter, color: QColor) -> None:
    painter.drawEllipse(QPointF(7.0, 7.0), 4.0, 4.0)
    painter.drawLine(QPointF(10.0, 10.0), QPointF(13.0, 13.0))


def _chevron(painter: QPainter, color: QColor) -> None:
    painter.drawPolyline(QPolygonF([QPointF(4.5, 6.5), QPointF(8.0, 10.0), QPointF(11.5, 6.5)]))


_PAINTERS = {
    "chevron": _chevron,
    "play": _play,
    "plus": _plus,
    "copy": _copy,
    "edit": _edit,
    "more": _more,
    "external": _external,
    "search": _search,
}


def icon_file(name: str, color: str, size: int = 12) -> str:
    """Write the icon to the temp folder and return its path, for stylesheet rules that need a file."""
    folder = Path(tempfile.gettempdir()) / "CommandCenter-ui"
    target = folder / f"{name}-{color.lstrip('#')}-{size}.png"
    if not target.is_file():
        try:
            folder.mkdir(parents=True, exist_ok=True)
            _render(name, color, size).save(str(target), "PNG")
        except OSError:
            return ""
    return target.as_posix()


def make_icon(name: str, color: str, size: int = 16) -> QIcon:
    """Return the named icon in one colour, rendered at 2x for high-DPI screens."""
    return QIcon(_render(name, color, size))


def _render(name: str, color: str, size: int) -> QPixmap:
    ratio = 2
    pixmap = QPixmap(size * ratio, size * ratio)
    pixmap.setDevicePixelRatio(ratio)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.scale(size / GRID, size / GRID)
    qcolor = QColor(color)
    painter.setPen(QPen(qcolor, 1.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                        Qt.PenJoinStyle.RoundJoin))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    _PAINTERS[name](painter, qcolor)
    painter.end()
    return pixmap
