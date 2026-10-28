"""UI Theme tokens, colors and stylesheet definitions for CommandCenter."""

from __future__ import annotations

from typing import Any
from PySide6.QtGui import QPalette, QColor
from PySide6.QtWidgets import QApplication

LIGHT_THEME = {
    "window": "#f3f5f8",
    "surface": "#ffffff",
    "surface_subtle": "#f8f9fa",
    "raised": "#eef2f6",
    "raised_hover": "#e2e8f0",
    "text": "#1a202c",
    "muted": "#64748b",
    "border": "#d2d8e2",
    "border_subtle": "#e8ecf1",
    "accent": "#0d9478",
    "accent_hover": "#0a7a63",
    "accent_text": "#ffffff",
    "selection": "#c7ebd5",
    "danger": "#dc2626",
    "danger_bg": "#fee2e2",
    "tag": "#e2f5ee",
    "tag_text": "#09735d",
    "param_tag": "#e0f2fe",
    "param_tag_text": "#0369a1",
}

DARK_THEME = {
    "window": "#13161a",
    "surface": "#1c2026",
    "surface_subtle": "#22272f",
    "raised": "#272c35",
    "raised_hover": "#333a46",
    "text": "#f1f5f9",
    "muted": "#94a3b8",
    "border": "#333b47",
    "border_subtle": "#252b34",
    "accent": "#2dd4bf",
    "accent_hover": "#14b8a6",
    "accent_text": "#042f2e",
    "selection": "#134e4a",
    "danger": "#f87171",
    "danger_bg": "#451215",
    "tag": "#133a34",
    "tag_text": "#5eead4",
    "param_tag": "#0c3b5e",
    "param_tag_text": "#7dd3fc",
}


def get_theme_colors(dark: bool = False) -> dict[str, str]:
    """Return color tokens for dark or light theme."""
    return DARK_THEME if dark else LIGHT_THEME


def build_application_stylesheet(colors: dict[str, str]) -> str:
    """Build modern Windows 11 Fluent-inspired QSS for the application."""
    return f"""
    QWidget {{
        color: {colors['text']};
        font-size: 10pt;
        font-family: "Segoe UI Variable Text", "Segoe UI", -apple-system, sans-serif;
    }}
    QMainWindow, QDialog, QWidget#mainContainer {{
        background: {colors['window']};
    }}
    
    /* Entradas y controles de edición */
    QLineEdit, QComboBox, QPlainTextEdit, QTextEdit, QTextBrowser, QTableWidget, QListWidget {{
        color: {colors['text']};
        background: {colors['surface']};
        border: 1px solid {colors['border']};
        border-radius: 6px;
        padding: 5px 8px;
        selection-background-color: {colors['accent']};
        selection-color: {colors['accent_text']};
    }}
    QLineEdit:focus, QComboBox:focus, QTextEdit:focus, QPlainTextEdit:focus {{
        border: 1.5px solid {colors['accent']};
        background: {colors['surface']};
    }}
    QComboBox QAbstractItemView {{
        color: {colors['text']};
        background: {colors['surface']};
        border: 1px solid {colors['border']};
        selection-background-color: {colors['selection']};
        selection-color: {colors['text']};
        padding: 4px;
        border-radius: 6px;
    }}
    
    /* Botones generales (secundarios) */
    QPushButton, QToolButton {{
        color: {colors['text']};
        background: {colors['surface']};
        border: 1px solid {colors['border']};
        border-radius: 6px;
        padding: 6px 14px;
        font-weight: 500;
    }}
    QPushButton:hover, QToolButton:hover {{
        background: {colors['raised_hover']};
        border-color: {colors['muted']};
    }}
    QPushButton:pressed, QToolButton:pressed {{
        background: {colors['selection']};
    }}
    QPushButton:disabled, QToolButton:disabled {{
        color: {colors['muted']};
        border-color: {colors['border_subtle']};
        background: {colors['raised']};
    }}

    /* Botón de Acción Principal (Primary) */
    QPushButton#primaryButton {{
        background: {colors['accent']};
        color: {colors['accent_text']};
        border: 1px solid {colors['accent']};
        font-weight: 600;
        border-radius: 6px;
        padding: 6px 14px;
    }}
    QPushButton#primaryButton:hover {{
        background: {colors['accent_hover']};
        border-color: {colors['accent_hover']};
    }}
    QPushButton#primaryButton:pressed {{
        background: {colors['accent']};
    }}

    /* Botón de Peligro (Danger) */
    QPushButton#dangerButton {{
        color: {colors['danger']};
        background: {colors['surface']};
        border: 1px solid {colors['border']};
        border-radius: 6px;
    }}
    QPushButton#dangerButton:hover {{
        background: {colors['danger_bg']};
        border-color: {colors['danger']};
    }}

    /* Botón Ghost (más sutil) */
    QPushButton#ghostButton {{
        background: transparent;
        border: 1px solid transparent;
        border-radius: 6px;
        padding: 5px 8px;
    }}
    QPushButton#ghostButton:hover {{
        background: {colors['raised_hover']};
        border-color: {colors['border']};
    }}

    /* Pestañas (TabWorkspace) */
    QTabWidget::pane {{
        border: 1px solid {colors['border']};
        background: {colors['window']};
        border-radius: 6px;
    }}
    QTabBar::tab {{
        color: {colors['muted']};
        background: transparent;
        border: 1px solid transparent;
        border-bottom: 2px solid transparent;
        padding: 8px 14px;
        font-weight: 500;
        margin-right: 2px;
        border-top-left-radius: 6px;
        border-top-right-radius: 6px;
    }}
    QTabBar::tab:hover {{
        color: {colors['text']};
        background: {colors['raised']};
    }}
    QTabBar::tab:selected {{
        color: {colors['text']};
        background: {colors['surface']};
        border: 1px solid {colors['border']};
        border-bottom: 2px solid {colors['accent']};
        font-weight: 600;
    }}

    /* Grupos y paneles */
    QGroupBox {{
        color: {colors['text']};
        border: 1px solid {colors['border']};
        border-radius: 8px;
        margin-top: 12px;
        padding-top: 10px;
        background: {colors['surface']};
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        left: 10px;
        padding: 0 6px;
        color: {colors['text']};
        font-weight: 600;
    }}

    QStatusBar {{
        color: {colors['muted']};
        background: {colors['window']};
        border-top: 1px solid {colors['border_subtle']};
        font-size: 9pt;
    }}

    QToolTip {{
        color: {colors['text']};
        background: {colors['surface']};
        border: 1px solid {colors['border']};
        border-radius: 4px;
        padding: 4px 6px;
    }}

    QListWidget::item {{
        background: transparent;
    }}

    /* Tarjetas de elemento (EntryCard) */
    QWidget#entryCard {{
        color: {colors['text']};
        background: {colors['surface']};
        border: 1px solid {colors['border']};
        border-radius: 8px;
    }}
    QWidget#entryCard:hover {{
        border-color: {colors['muted']};
    }}
    QWidget#entryCard[interface="compact"] {{
        background: transparent;
        border: 0;
        border-bottom: 1px solid {colors['border_subtle']};
        border-radius: 0;
    }}
    QWidget#entryCard[dragging="true"] {{
        background: {colors['tag']};
        border: 2px dashed {colors['accent']};
    }}

    QLabel#entryTitle {{
        font-size: 11pt;
        font-weight: 600;
        color: {colors['text']};
    }}
    QLabel#categoryTag {{
        color: {colors['tag_text']};
        padding: 2px 8px;
        border-radius: 10px;
        background: {colors['tag']};
        font-size: 9pt;
        font-weight: 500;
    }}
    QLabel#runnerTag {{
        color: {colors['param_tag_text']};
        padding: 2px 8px;
        border-radius: 10px;
        background: {colors['param_tag']};
        font-size: 8.5pt;
        font-weight: 500;
    }}

    QTextEdit#entryBody {{
        color: {colors['text']};
        padding: 4px;
        background: {colors['surface_subtle']};
        border: 1px solid {colors['border_subtle']};
        border-radius: 5px;
        font-family: Consolas, "Cascadia Code", monospace;
        font-size: 9.5pt;
    }}

    /* Estados vacíos */
    QWidget#emptyStateContainer {{
        background: transparent;
    }}
    QLabel#emptyStateTitle {{
        font-size: 13pt;
        font-weight: 600;
        color: {colors['text']};
    }}
    QLabel#emptyStateSubtitle {{
        font-size: 10pt;
        color: {colors['muted']};
    }}

    /* Barra de herramientas compacta */
    QWidget#mainContainer[interface="compact"] QPushButton {{
        border-radius: 4px;
        padding: 4px 8px;
    }}

    /* Consola (terminal mode) */
    QWidget#mainContainer[interface="terminal"] QWidget#entryCard {{
        background: #0d1317;
        border: 1px solid #1e3b37;
        border-radius: 4px;
    }}
    QWidget#mainContainer[interface="terminal"] QLabel#entryTitle,
    QWidget#mainContainer[interface="terminal"] QTextEdit#entryBody {{
        font-family: Consolas, 'Cascadia Mono', monospace;
    }}
    QWidget#mainContainer[interface="terminal"] QLineEdit {{
        font-family: Consolas, 'Cascadia Mono', monospace;
        border-radius: 4px;
    }}
    """
