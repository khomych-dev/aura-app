from __future__ import annotations

import logging

from PySide6.QtGui import QAction, QActionGroup, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon, QWidget

from aura import config

logger = logging.getLogger(__name__)

# (language_code, display_label) — order defines the submenu order.
_LANGUAGE_OPTIONS: list[tuple[str, str]] = [
    ("auto", "Auto (System Layout)"),
    ("uk", "Ukrainian"),
    ("en", "English"),
    ("ru", "Russian"),
]


class TrayIcon(QSystemTrayIcon):
    """System tray icon with Language selection submenu and Exit action."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setIcon(self._make_icon())
        self.setToolTip("Aura — Voice to Text\nHold Right Ctrl to record")

        self._language: str = config.DEFAULT_LANGUAGE

        menu = QMenu()

        # Language submenu — QActionGroup enforces mutual exclusion.
        lang_menu = menu.addMenu("Language")
        self._lang_group = QActionGroup(lang_menu)
        self._lang_group.setExclusive(True)

        for code, label in _LANGUAGE_OPTIONS:
            action = QAction(label, lang_menu, checkable=True)
            action.setData(code)
            action.setChecked(code == config.DEFAULT_LANGUAGE)
            self._lang_group.addAction(action)
            lang_menu.addAction(action)

        self._lang_group.triggered.connect(self._on_language_selected)

        menu.addSeparator()

        exit_action = menu.addAction("Exit Aura")
        exit_action.triggered.connect(QApplication.quit)

        self.setContextMenu(menu)

        if not QSystemTrayIcon.isSystemTrayAvailable():
            logger.warning("System tray is not available on this platform")
        else:
            self.show()
            logger.debug("Tray icon shown")

    @property
    def language(self) -> str:
        """Currently selected language code, or ``'auto'`` for system layout detection."""
        return self._language

    def _on_language_selected(self, action: QAction) -> None:
        self._language = action.data()
        logger.info("Language preference set to: %s", self._language)

    @staticmethod
    def _make_icon() -> QIcon:
        pixmap = QPixmap(16, 16)
        pixmap.fill(QColor(0, 0, 0, 0))
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor(80, 80, 80))
        painter.setPen(QColor(0, 0, 0, 0))
        painter.drawEllipse(2, 2, 12, 12)
        painter.end()
        return QIcon(pixmap)
