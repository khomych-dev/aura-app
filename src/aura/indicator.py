from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QPainter
from PySide6.QtWidgets import QApplication, QWidget

from aura import config

logger = logging.getLogger(__name__)

_RED = QColor(220, 30, 30)


class RecordingIndicator(QWidget):
    """Small red dot shown at the top-centre of the screen while recording.

    The window is frameless, always on top, never steals focus, and is
    transparent to mouse input so it does not interfere with other apps.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._setup_window()

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def _setup_window(self) -> None:
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool               # excludes from taskbar
            | Qt.WindowType.WindowTransparentForInput  # click-through
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

        self.setFixedSize(config.INDICATOR_SIZE_PX, config.INDICATOR_SIZE_PX)
        self._reposition()

    def _reposition(self) -> None:
        screen = QApplication.primaryScreen()
        if screen is None:
            logger.warning("No primary screen detected — indicator may be misplaced")
            return
        geo = screen.geometry()
        x = geo.center().x() - self.width() // 2
        y = geo.top() + config.INDICATOR_TOP_MARGIN_PX
        self.move(x, y)

    # ------------------------------------------------------------------
    # Painting
    # ------------------------------------------------------------------

    def paintEvent(self, event) -> None:  # noqa: ANN001, N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QBrush(_RED))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(0, 0, self.width() - 1, self.height() - 1)
