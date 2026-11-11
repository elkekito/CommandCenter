"""UI Theme tokens, colors and stylesheet definitions for CommandCenter."""

from __future__ import annotations

from .icons import icon_file

UI_FONT = '"Segoe UI Variable Text", "Segoe UI", sans-serif'
CODE_FONT = '"Cascadia Mono", "Cascadia Code", Consolas, monospace'

LIGHT_THEME = {
    "window": "#f3f5f7",
    "surface": "#ffffff",
    "surface_subtle": "#f6f8fa",
    "raised": "#eceff3",
    "raised_hover": "#e3e7ec",
    "text": "#1b2430",
    "muted": "#5a6675",
    "border": "#d9dee5",
    "border_subtle": "#e7ebf0",
    "border_strong": "#b9c1cc",
    "accent": "#0a7d67",
    "accent_hover": "#086a57",
    "accent_pressed": "#075a4a",
    "accent_text": "#ffffff",
    "selection": "#d3eee6",
    "danger": "#c22525",
    "danger_bg": "#fdecec",
    "warning": "#9a5b00",
    "tag": "#e9edf2",
    "tag_text": "#465364",
    "param_tag": "#e0f2fe",
    "param_tag_text": "#0369a1",
    "console": "#11161c",
    "console_text": "#dfe6ee",
    "console_border": "#232b35",
}

DARK_THEME = {
    "window": "#101317",
    "surface": "#181c22",
    "surface_subtle": "#12151a",
    "raised": "#20252d",
    "raised_hover": "#2a303a",
    "text": "#e8ecf1",
    "muted": "#9aa5b4",
    "border": "#2b313b",
    "border_subtle": "#21262e",
    "border_strong": "#434b58",
    "accent": "#2fb8a4",
    "accent_hover": "#49c9b6",
    "accent_pressed": "#27a391",
    "accent_text": "#04211d",
    "selection": "#17413a",
    "danger": "#f2766f",
    "danger_bg": "#3a1719",
    "warning": "#e5a94b",
    "tag": "#252b34",
    "tag_text": "#b4bdca",
    "param_tag": "#0c3b5e",
    "param_tag_text": "#7dd3fc",
    "console": "#0b0e12",
    "console_text": "#dfe6ee",
    "console_border": "#232b35",
}

_active_colors: dict[str, str] = dict(LIGHT_THEME)


def get_theme_colors(dark: bool = False) -> dict[str, str]:
    """Return color tokens for dark or light theme."""
    return DARK_THEME if dark else LIGHT_THEME


def set_active_colors(colors: dict[str, str]) -> None:
    """Remember the theme in use so widgets painted by hand can follow it."""
    _active_colors.clear()
    _active_colors.update(colors)


def active_colors() -> dict[str, str]:
    return _active_colors


def active_is_dark() -> bool:
    return _active_colors.get("window") == DARK_THEME["window"]


def build_application_stylesheet(colors: dict[str, str]) -> str:
    """Build the application QSS from the theme tokens."""
    c = colors
    # Stylesheets can only draw the combo arrow from an image file.
    chevron = icon_file("chevron", c["muted"])
    return f"""
    QWidget {{
        color: {c['text']};
        font-size: 10pt;
        font-family: {UI_FONT};
    }}
    QMainWindow, QDialog, QWidget#mainContainer {{
        background: {c['window']};
    }}

    /* Campos de texto y desplegables */
    QLineEdit, QComboBox, QPlainTextEdit, QTextEdit, QTextBrowser {{
        color: {c['text']};
        background: {c['surface']};
        border: 1px solid {c['border']};
        border-radius: 6px;
        padding: 5px 9px;
        selection-background-color: {c['accent']};
        selection-color: {c['accent_text']};
    }}
    QLineEdit:hover, QComboBox:hover, QPlainTextEdit:hover, QTextEdit:hover {{
        border-color: {c['border_strong']};
    }}
    QLineEdit:focus, QComboBox:focus, QTextEdit:focus, QPlainTextEdit:focus {{
        border-color: {c['accent']};
    }}
    QLineEdit:disabled, QComboBox:disabled, QPlainTextEdit:disabled, QTextEdit:disabled {{
        color: {c['muted']};
        background: {c['raised']};
    }}
    QPlainTextEdit, QTextEdit {{
        font-family: {CODE_FONT};
        font-size: 9.5pt;
    }}
    QTextBrowser {{
        font-family: {UI_FONT};
        font-size: 10pt;
    }}
    QComboBox {{
        padding-right: 26px;
    }}
    QComboBox::drop-down {{
        subcontrol-origin: padding;
        subcontrol-position: center right;
        width: 24px;
        border: 0;
    }}
    QComboBox::down-arrow {{
        image: url("{chevron}");
        width: 12px;
        height: 12px;
        margin-right: 8px;
    }}
    QComboBox QAbstractItemView {{
        color: {c['text']};
        background: {c['surface']};
        border: 1px solid {c['border']};
        selection-background-color: {c['selection']};
        selection-color: {c['text']};
        padding: 4px;
        outline: 0;
    }}

    /* Botones: secundario por defecto */
    QPushButton, QToolButton {{
        color: {c['text']};
        background: {c['surface']};
        border: 1px solid {c['border']};
        border-radius: 6px;
        padding: 5px 12px;
        font-weight: 500;
    }}
    QPushButton:hover, QToolButton:hover {{
        background: {c['raised']};
        border-color: {c['border_strong']};
    }}
    QPushButton:pressed, QToolButton:pressed {{
        background: {c['raised_hover']};
    }}
    QPushButton:focus, QToolButton:focus {{
        border-color: {c['accent']};
    }}
    QPushButton:disabled, QToolButton:disabled {{
        color: {c['muted']};
        border-color: {c['border_subtle']};
        background: {c['raised']};
    }}
    QToolButton::menu-indicator {{
        image: none;
        width: 0;
    }}

    QPushButton#primaryButton {{
        background: {c['accent']};
        color: {c['accent_text']};
        border: 1px solid {c['accent']};
        font-weight: 600;
    }}
    QPushButton#primaryButton:hover {{
        background: {c['accent_hover']};
        border-color: {c['accent_hover']};
    }}
    QPushButton#primaryButton:pressed {{
        background: {c['accent_pressed']};
        border-color: {c['accent_pressed']};
    }}
    QPushButton#primaryButton:focus {{
        border-color: {c['text']};
    }}

    QPushButton#dangerButton {{
        color: {c['danger']};
    }}
    QPushButton#dangerButton:hover {{
        background: {c['danger_bg']};
        border-color: {c['danger']};
    }}

    QPushButton#ghostButton, QToolButton#ghostButton {{
        background: transparent;
        border: 1px solid transparent;
        padding: 5px 9px;
    }}
    QPushButton#ghostButton:hover, QToolButton#ghostButton:hover {{
        background: {c['raised_hover']};
    }}
    QPushButton#ghostButton:pressed, QToolButton#ghostButton:pressed {{
        background: {c['border']};
    }}
    QPushButton#ghostButton:focus, QToolButton#ghostButton:focus {{
        border-color: {c['accent']};
    }}

    /* Menús */
    QMenu {{
        background: {c['surface']};
        border: 1px solid {c['border']};
        padding: 4px;
    }}
    QMenu::item {{
        padding: 6px 22px 6px 12px;
        border-radius: 4px;
    }}
    QMenu::item:selected {{
        background: {c['raised_hover']};
        color: {c['text']};
    }}
    QMenu::item:disabled {{
        color: {c['muted']};
    }}
    QMenu::separator {{
        height: 1px;
        background: {c['border_subtle']};
        margin: 4px 6px;
    }}

    /* Pestañas */
    QFrame#tabStrip {{
        border: 0;
        border-bottom: 1px solid {c['border']};
    }}
    QTabWidget::pane {{
        border: 1px solid {c['border']};
        background: {c['surface']};
        border-radius: 6px;
        top: -1px;
    }}
    QTabBar {{
        background: transparent;
    }}
    QTabBar::tab {{
        color: {c['muted']};
        background: transparent;
        border: 0;
        border-bottom: 2px solid transparent;
        padding: 8px 14px 7px 14px;
        font-weight: 500;
    }}
    QTabBar::tab:hover {{
        color: {c['text']};
        border-bottom-color: {c['border_strong']};
    }}
    QTabBar::tab:selected {{
        color: {c['text']};
        border-bottom-color: {c['accent']};
    }}
    QTabBar QToolButton {{
        background: {c['window']};
        border: 0;
        border-radius: 0;
        padding: 2px;
    }}

    /* Grupos y paneles */
    QGroupBox {{
        border: 1px solid {c['border']};
        border-radius: 8px;
        margin-top: 12px;
        padding-top: 10px;
        background: {c['surface']};
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        left: 10px;
        padding: 0 6px;
        color: {c['muted']};
        font-weight: 600;
    }}

    QStatusBar {{
        color: {c['muted']};
        background: {c['window']};
        border-top: 1px solid {c['border_subtle']};
        font-size: 9pt;
    }}
    QStatusBar::item {{
        border: 0;
    }}

    QToolTip {{
        color: {c['text']};
        background: {c['surface']};
        border: 1px solid {c['border_strong']};
        padding: 4px 6px;
    }}

    /* Barras de desplazamiento */
    QScrollBar:vertical {{
        background: transparent;
        width: 12px;
        margin: 2px;
    }}
    QScrollBar:horizontal {{
        background: transparent;
        height: 12px;
        margin: 2px;
    }}
    QScrollBar::handle {{
        background: {c['border_strong']};
        border-radius: 4px;
    }}
    QScrollBar::handle:vertical {{
        min-height: 36px;
    }}
    QScrollBar::handle:horizontal {{
        min-width: 36px;
    }}
    QScrollBar::handle:hover, QScrollBar::handle:pressed {{
        background: {c['muted']};
    }}
    QScrollBar::add-line, QScrollBar::sub-line {{
        width: 0;
        height: 0;
    }}
    QScrollBar::add-page, QScrollBar::sub-page {{
        background: transparent;
    }}
    QAbstractScrollArea::corner {{
        background: transparent;
    }}

    /* Listas y tablas */
    QListWidget, QTableWidget, QTreeWidget {{
        color: {c['text']};
        background: {c['surface']};
        alternate-background-color: {c['surface_subtle']};
        border: 1px solid {c['border']};
        border-radius: 6px;
        gridline-color: {c['border_subtle']};
        selection-background-color: {c['selection']};
        selection-color: {c['text']};
        outline: 0;
    }}
    QTableWidget::item {{
        padding: 0 8px;
        border: 0;
    }}
    QTableWidget::item:selected, QListWidget::item:selected {{
        background: {c['selection']};
        color: {c['text']};
    }}
    QHeaderView {{
        background: transparent;
    }}
    QHeaderView::section {{
        color: {c['muted']};
        background: {c['surface_subtle']};
        border: 0;
        border-bottom: 1px solid {c['border']};
        padding: 7px 8px;
        font-size: 9pt;
        font-weight: 600;
    }}
    QTableCornerButton::section {{
        background: {c['surface_subtle']};
        border: 0;
        border-bottom: 1px solid {c['border']};
    }}
    QListWidget#entryList {{
        border: 0;
        background: transparent;
        padding: 0;
    }}
    QListWidget#entryList::item, QListWidget#entryList::item:selected,
    QListWidget#entryList::item:hover {{
        background: transparent;
        border: 0;
    }}

    /* Tarjetas de elemento */
    QWidget#entryCard {{
        background: {c['surface']};
        border: 1px solid {c['border']};
        border-radius: 8px;
    }}
    QWidget#entryCard:hover {{
        border-color: {c['border_strong']};
    }}
    QWidget#entryCard[dragging="true"] {{
        background: {c['selection']};
        border: 1px dashed {c['accent']};
    }}
    QLabel#entryTitle {{
        font-size: 10.5pt;
        font-weight: 600;
        color: {c['text']};
        background: transparent;
    }}
    QLabel#categoryTag {{
        color: {c['tag_text']};
        background: {c['tag']};
        border-radius: 5px;
        padding: 0 8px;
        font-size: 8.5pt;
        font-weight: 500;
    }}
    QLabel#runnerTag {{
        color: {c['muted']};
        background: transparent;
        font-family: {CODE_FONT};
        font-size: 8.5pt;
    }}
    QTextEdit#entryBody {{
        color: {c['text']};
        padding: 4px;
        background: {c['surface_subtle']};
        border: 1px solid {c['border_subtle']};
        border-radius: 6px;
        font-family: {CODE_FONT};
        font-size: 9.5pt;
    }}

    /* Compacta: lista densa separada por líneas */
    QWidget#entryCard[interface="compact"] {{
        background: transparent;
        border: 0;
        border-bottom: 1px solid {c['border_subtle']};
        border-radius: 0;
    }}
    QWidget#entryCard[interface="compact"]:hover {{
        background: {c['surface']};
        border-bottom-color: {c['border']};
    }}
    QWidget#entryCard[interface="compact"] QTextEdit#entryBody {{
        background: transparent;
        border: 1px solid transparent;
        color: {c['muted']};
    }}
    QWidget#entryCard[interface="compact"] QPushButton,
    QWidget#entryCard[interface="compact"] QToolButton,
    QWidget#entryCard[interface="compact"] QComboBox {{
        padding-top: 2px;
        padding-bottom: 2px;
    }}

    /* Consola: bloque de comando oscuro y tipografía monoespaciada */
    QWidget#entryCard[interface="terminal"] {{
        border-radius: 4px;
    }}
    QWidget#entryCard[interface="terminal"] QLabel#entryTitle {{
        font-family: {CODE_FONT};
        font-size: 10pt;
    }}
    QWidget#entryCard[interface="terminal"] QTextEdit#entryBody {{
        color: {c['console_text']};
        background: {c['console']};
        border: 1px solid {c['console_border']};
        border-radius: 3px;
    }}

    /* Estados vacíos */
    QWidget#emptyStateContainer {{
        background: transparent;
    }}
    QLabel#emptyStateTitle {{
        font-size: 12pt;
        font-weight: 600;
        color: {c['text']};
    }}
    QLabel#emptyStateSubtitle {{
        color: {c['muted']};
    }}
    QLabel#mutedLabel {{
        color: {c['muted']};
    }}
    """
