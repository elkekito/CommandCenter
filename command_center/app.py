"""PySide6 user interface for Command Center."""

from __future__ import annotations

import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QTimer, QUrl, QSize, QPoint, QMimeData
from PySide6.QtGui import (
    QIcon,
    QKeySequence,
    QPalette,
    QColor,
    QDesktopServices,
    QShortcut,
    QFontMetrics,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QListView,
    QTabBar,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QInputDialog,
    QFileDialog,
    QSizePolicy,
    QHeaderView,
)
from . import __version__
from .processes import ProcessLaunchError, launch_script, paste_text_into_window
from .storage import (
    DATABASE_FILENAME,
    DataStore,
    application_data_dir,
    load_database_location,
    resource_path,
    save_database_location,
)
from .ui import (
    ReorderableList,
    EntryTextEdit,
    DragHandle,
    EmptyStateWidget,
    get_theme_colors,
    build_application_stylesheet,
    ScriptSyntaxHighlighter,
)
from .constants import INTERFACE_LABELS, KIND_LABELS, PARAMETER_PATTERN, RUNNERS
from .dialogs import (
    ArchivedTabsDialog,
    CommandParametersDialog,
    EntryDialog,
    EntryOrganizerDialog,
    InterfacePickerDialog,
    OptionsDialog,
    StorageLocationDialog,
    SuggestionsDialog,
    WindowPickerDialog,
)


"""PySide6 user interface for Command Center."""

# Cards are created only for rows within this many pixels of the visible area.
CARD_PREFETCH_PX = 400
# Table rows that get their action buttons beyond the visible area.
TABLE_PREFETCH_ROWS = 10
# Time given to the target window to read the pasted text before the previous clipboard comes back.
PASTE_RESTORE_DELAY_MS = 1500
class AddActionTabBar(QTabBar):
    """Native tab bar with extra horizontal room around its add action."""

    ADD_TAB_MARKER = "__add_tab__"

    def tabSizeHint(self, index: int) -> QSize:
        size = super().tabSizeHint(index)
        if 0 <= index < self.count() and self.tabData(index) == self.ADD_TAB_MARKER:
            return QSize(size.width() + 16, size.height())
        return size


class TabWorkspace(QWidget):
    """Tab strip and page stack with a final, tab-shaped add control."""

    ADD_TAB_MARKER = AddActionTabBar.ADD_TAB_MARKER

    def __init__(self, on_add, parent=None):
        super().__init__(parent)
        self._on_add = on_add
        self._normalizing_tabs = False
        self._row = QHBoxLayout()
        self._row.setContentsMargins(0, 0, 0, 0)
        self._row.setSpacing(0)
        self._tab_bar = AddActionTabBar(self)
        self._tab_bar.setExpanding(False)
        self._tab_bar.setUsesScrollButtons(True)
        self._tab_bar.setElideMode(Qt.TextElideMode.ElideRight)
        self._tab_bar.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._tab_bar.setStyleSheet("QTabBar::tab:last { margin-left: 6px; }")
        self._add_tab_index = self._tab_bar.addTab("+")
        self._tab_bar.setTabToolTip(self._add_tab_index, "Nueva pestaña")
        self._tab_bar.setTabData(self._add_tab_index, self.ADD_TAB_MARKER)
        self._row.addWidget(self._tab_bar)
        self._row.addStretch(1)
        self._stack = QStackedWidget(self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addLayout(self._row)
        layout.addWidget(self._stack, 1)
        self._last_page_index = -1
        self._tab_bar.currentChanged.connect(self._tab_selection_changed)
        self._tab_bar.tabBarClicked.connect(self._tab_clicked)
        self._tab_bar.tabMoved.connect(self._move_page)

    def tabBar(self) -> QTabBar:
        return self._tab_bar

    def setMovable(self, movable: bool):
        self._tab_bar.setMovable(movable)

    def count(self) -> int:
        return self._stack.count()

    def widget(self, index: int) -> QWidget | None:
        return self._stack.widget(index)

    def currentWidget(self) -> QWidget | None:
        return self._stack.currentWidget()

    def currentIndex(self) -> int:
        return self._stack.currentIndex()

    def setCurrentIndex(self, index: int):
        if 0 <= index < self._stack.count():
            self._last_page_index = index
            self._tab_bar.setCurrentIndex(index)
            self._stack.setCurrentIndex(index)

    def setCurrentWidget(self, widget: QWidget):
        index = self._stack.indexOf(widget)
        if index >= 0:
            self.setCurrentIndex(index)

    def addTab(self, widget: QWidget, title: str) -> int:
        index = self._stack.addWidget(widget)
        self._tab_bar.insertTab(index, title)
        self._sync_tab_width()
        return index

    def clear(self):
        while self._stack.count():
            self._tab_bar.removeTab(0)
            widget = self._stack.widget(0)
            self._stack.removeWidget(widget)
            widget.deleteLater()
        self._last_page_index = -1
        self._sync_tab_width()

    def blockSignals(self, block: bool) -> bool:
        previous = self._tab_bar.blockSignals(block)
        self._stack.blockSignals(block)
        if not block and self._stack.count():
            self._tab_selection_changed(self._tab_bar.currentIndex())
        return previous

    def _tab_selection_changed(self, index: int):
        is_add_tab = (
            0 <= index < self._tab_bar.count()
            and self._tab_bar.tabData(index) == self.ADD_TAB_MARKER
        )
        if is_add_tab:
            if self._last_page_index >= 0:
                self._tab_bar.setCurrentIndex(self._last_page_index)
            elif self._stack.count():
                self.setCurrentIndex(0)
        elif 0 <= index < self._stack.count():
            self._last_page_index = index
            self._stack.setCurrentIndex(index)
        elif self._last_page_index >= 0:
            self._tab_bar.setCurrentIndex(self._last_page_index)

    def _tab_clicked(self, index: int):
        if (0 <= index < self._tab_bar.count()
                and self._tab_bar.tabData(index) == self.ADD_TAB_MARKER):
            if self._last_page_index >= 0:
                self._tab_bar.setCurrentIndex(self._last_page_index)
            self._on_add()

    def _move_page(self, source: int, destination: int):
        if self._normalizing_tabs:
            return
        page_count = self._stack.count()
        source_is_add_tab = (
            0 <= source < self._tab_bar.count()
            and self._tab_bar.tabData(source) == self.ADD_TAB_MARKER
        )
        if not source_is_add_tab and 0 <= source < page_count and source != destination:
            page = self._stack.widget(source)
            self._stack.removeWidget(page)
            self._stack.insertWidget(min(destination, page_count - 1), page)
        add_index = next(
            (i for i in range(self._tab_bar.count())
             if self._tab_bar.tabData(i) == self.ADD_TAB_MARKER),
            -1,
        )
        if add_index != page_count:
            self._normalizing_tabs = True
            self._tab_bar.moveTab(add_index, page_count)
            self._normalizing_tabs = False
        self._add_tab_index = page_count
        current_index = self._tab_bar.currentIndex()
        if (0 <= current_index < self._tab_bar.count()
                and self._tab_bar.tabData(current_index) == self.ADD_TAB_MARKER):
            current_index = self._last_page_index if self._last_page_index >= 0 else 0
            if page_count:
                self._tab_bar.setCurrentIndex(current_index)
        if page_count:
            current_index = min(current_index, page_count - 1)
            self._last_page_index = current_index
            self._stack.setCurrentIndex(current_index)
        else:
            self._last_page_index = -1
        self._sync_tab_width()

    def _sync_tab_width(self):
        natural_width = sum(self._tab_bar.tabSizeHint(i).width() for i in range(self._tab_bar.count()))
        self._tab_bar.setFixedWidth(min(natural_width, max(0, self.width())))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._sync_tab_width()


class EntryCard(QWidget):
    def __init__(self, entry: dict[str, Any], kind: str, callbacks: dict[str, Any],
                 parent=None, interface: str = "classic"):
        super().__init__(parent)
        self.entry = entry
        self.kind = kind
        self.setObjectName("entryCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(5)

        heading = QHBoxLayout()
        heading.setSpacing(8)
        title = QLabel(entry["title"])
        title.setObjectName("entryTitle")
        title.setTextFormat(Qt.TextFormat.PlainText)
        title.setWordWrap(False)
        title.setFixedHeight(28)
        title.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        title.setToolTip(entry["title"])
        title.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        heading.addWidget(title, 1)
        if kind == "command" and entry.get("runner"):
            runner_tag = QLabel(entry["runner"])
            runner_tag.setObjectName("runnerTag")
            runner_tag.setAlignment(Qt.AlignmentFlag.AlignCenter)
            runner_tag.setFixedHeight(26)
            runner_tag.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
            heading.addWidget(runner_tag)
        if entry["category"]:
            category = QLabel(entry["category"])
            category.setTextFormat(Qt.TextFormat.PlainText)
            category.setText(category.fontMetrics().elidedText(
                entry["category"], Qt.TextElideMode.ElideRight, 220
            ))
            category.setObjectName("categoryTag")
            category.setAlignment(Qt.AlignmentFlag.AlignCenter)
            category.setFixedHeight(28)
            category.setMaximumWidth(240)
            category.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
            category.setToolTip(entry["category"])
            heading.addWidget(category)
        body = EntryTextEdit()
        body.setObjectName("entryBody")
        body.setReadOnly(True)
        body.setAcceptRichText(False)
        body.setPlainText(entry["content"])
        body.setFrameShape(QFrame.Shape.NoFrame)
        body.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        body.setContentsMargins(6, 6, 6, 6)
        body.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.body = body
        self.highlighter = ScriptSyntaxHighlighter(
            self.body.document(),
            runner=entry.get("runner", "PowerShell") if kind == "command" else "None"
        )

        actions = QHBoxLayout()
        actions.setSpacing(6)
        if kind == "command":
            runner_choice = QComboBox()
            runner_choice.addItems(RUNNERS)
            if entry.get("runner") in RUNNERS:
                runner_choice.setCurrentText(entry["runner"])
            runner_choice.insertSeparator(len(RUNNERS))
            runner_choice.addItem("Pegar en ventana…")
            runner_choice.setFixedWidth(145)
            runner_choice.setToolTip("Ejecutar con el motor elegido o pegar en una ventana abierta")
            runner_choice.setAccessibleName("Motor de ejecución")
            run = QPushButton("▶ Ejecutar")
            run.setObjectName("primaryButton")
            runner_choice.currentTextChanged.connect(
                lambda value: run.setText("Pegar…" if value == "Pegar en ventana…" else "▶ Ejecutar")
            )
            run.clicked.connect(lambda: callbacks["run"](entry, runner_choice.currentText()))
            actions.addWidget(runner_choice)
            actions.addWidget(run)
        if kind == "url":
            open_button = QPushButton("🌐 Abrir")
            open_button.setObjectName("primaryButton")
            open_button.clicked.connect(lambda: callbacks["open"](entry))
            actions.addWidget(open_button)

        copy_button = QPushButton("Copiar")
        copy_button.clicked.connect(lambda: callbacks["copy"](entry["content"]))
        actions.addWidget(copy_button)

        edit_button = QPushButton("Editar")
        edit_button.clicked.connect(lambda: callbacks["edit"](entry))
        actions.addWidget(edit_button)

        more_button = QToolButton()
        more_button.setText("•••")
        more_button.setObjectName("ghostButton")
        more_button.setToolTip("Más opciones")
        more_button.setAccessibleName("Más opciones")
        more_menu = QMenu(more_button)
        delete_action = more_menu.addAction("Eliminar entrada")
        delete_action.triggered.connect(lambda: callbacks["delete"](entry))
        more_button.setMenu(more_menu)
        more_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        actions.addWidget(more_button)

        if callbacks.get("drag_start"):
            actions.addWidget(DragHandle(
                entry["id"], callbacks["drag_start"], callbacks["drag_move"],
                callbacks["drag_finish"], self,
            ))
        actions.addStretch(1)
        self.actions_layout = actions
        if interface == "compact":
            content_column = QVBoxLayout()
            content_column.setContentsMargins(0, 0, 0, 0)
            content_column.setSpacing(3)
            content_column.addLayout(heading)
            content_column.addWidget(body, 1)
            layout.addLayout(content_column, 1)
            layout.addLayout(actions)
        else:
            layout.addLayout(heading)
            layout.addWidget(body)
            layout.addLayout(actions)
        self.card_layout = layout
        self.set_interface(interface)

    def set_interface(self, interface: str) -> None:
        margins = {
            "classic": (12, 10, 12, 10),
            "compact": (8, 5, 8, 5),
        }.get(interface, (12, 10, 12, 10))
        self.card_layout.setContentsMargins(*margins)
        self.card_layout.setSpacing(3 if interface == "compact" else 6)
        self.setProperty("interface", interface)
        self.style().unpolish(self)
        self.style().polish(self)

    def set_dragging(self, dragging: bool) -> None:
        self.setProperty("dragging", dragging)
        style = self.style()
        style.unpolish(self)
        style.polish(self)
        self.update()

    def size_for_width(self, width: int) -> QSize:
        """Calculate a card's exact row size for the current list viewport."""
        width = max(1, width)
        left, top, right, bottom = self.card_layout.getContentsMargins()
        reserved_actions = (self.actions_layout.sizeHint().width() + self.card_layout.spacing()
                            if self.property("interface") == "compact" else 0)
        body_width = max(1, width - left - right - reserved_actions)
        self.body.setFixedWidth(body_width)
        self.body.ensurePolished()
        document = self.body.document()
        document.setDefaultFont(self.body.font())
        document.setDocumentMargin(0)
        text_width = max(1, body_width - self.body.contentsMargins().left()
                         - self.body.contentsMargins().right())
        document.setTextWidth(text_width)
        content_height = int(document.size().height() + 0.99)
        content_height += self.body.contentsMargins().top() + self.body.contentsMargins().bottom()
        self.body.setFixedHeight(max(content_height, self.body.fontMetrics().height() + 12))
        self.card_layout.activate()
        height = self.card_layout.sizeHint().height()
        self.setFixedSize(width, height)
        return QSize(width, height)


class CollectionPage(QWidget):
    def __init__(self, store: DataStore, tab: dict[str, Any], parent_window: "CommandCenterWindow"):
        super().__init__()
        self.store = store
        self.tab = tab
        self.parent_window = parent_window
        self.kind = tab["kind"]
        self._visible_entries: list[dict[str, Any]] = []
        self._manual_drag: dict[str, Any] | None = None
        # Card heights measured so far, keyed by entry and interface, so filtering stays cheap.
        self._height_cache: dict[tuple[str, str, str], tuple[int, int]] = {}
        self._entries_by_id: dict[str, dict[str, Any]] = {}
        self._card_callbacks: dict[str, Any] = {}
        self._table_entries: list[dict[str, Any]] = []

        layout = QVBoxLayout(self)
        toolbar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Buscar por título, contenido o categoría…")
        self.category = QComboBox()
        self.category.setMinimumWidth(170)
        self.sort_order = QComboBox()
        for label, key in (
            ("Manual", "manual"),
            ("Título A–Z", "title_asc"),
            ("Título Z–A", "title_desc"),
            ("Categoría A–Z", "category_asc"),
            ("Categoría Z–A", "category_desc"),
            ("Modificación más reciente", "updated_desc"),
            ("Creación más reciente", "created_desc"),
            ("Creación más antigua", "created_asc"),
        ):
            self.sort_order.addItem(label, key)
        sort_setting = f"entry_sort:{self.tab['id']}"
        saved_sort = self.store.get_setting(sort_setting, "manual")
        if saved_sort == "default":
            saved_sort = "manual"
            self.store.set_setting(sort_setting, saved_sort)
        saved_index = self.sort_order.findData(saved_sort)
        self.sort_order.setCurrentIndex(max(0, saved_index))
        self.sort_order.setToolTip(
            "Manual conserva el orden guardado. Arrastra desde el asa junto a Eliminar."
        )
        toolbar.addWidget(self.search, 1)
        toolbar.addWidget(self.category)
        toolbar.addWidget(QLabel("Orden:"))
        toolbar.addWidget(self.sort_order)
        organize = QPushButton("Organizar…")
        organize.clicked.connect(self.organize_entries)
        toolbar.addWidget(organize)
        if self.kind != "command":
            self.add_button = QPushButton(f"+ Nuevo {KIND_LABELS[self.kind]}")
            self.add_button.setObjectName("primaryButton")
            self.add_button.clicked.connect(self.add_entry)
            toolbar.addWidget(self.add_button)
        layout.addLayout(toolbar)

        self.items = ReorderableList()
        self.items.setObjectName("entryList")
        self.items.setSpacing(0)
        self.items.setStyleSheet("QListWidget#entryList { border: 0; background: transparent; }")
        self.list_page = QWidget()
        list_layout = QHBoxLayout(self.list_page)
        list_layout.setContentsMargins(0, 0, 0, 0)
        list_layout.addWidget(self.items, 1)
        self.mode_stack = QStackedWidget()
        self.mode_stack.addWidget(self.list_page)

        self.table = QTableWidget(0, 5)
        self.table.setObjectName("entryTable")
        self.table.setHorizontalHeaderLabels(["Título", "Categoría", "Contenido", "Motor", "Acciones"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(False)
        # Fixed widths keep every column readable; the table scrolls sideways when they do not fit.
        header = self.table.horizontalHeader()
        for column, width in ((0, 280), (1, 170), (2, 260)):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Interactive)
            header.resizeSection(column, width)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.mode_stack.addWidget(self.table)
        layout.addWidget(self.mode_stack, 1)

        # Rebuilding every card costs most of the time, so wait for a pause in typing.
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(180)
        self._search_timer.timeout.connect(self.render)
        self.search.textChanged.connect(lambda _text: self._search_timer.start())
        self.category.currentTextChanged.connect(self.render)
        self.sort_order.currentIndexChanged.connect(self.change_sort_mode)
        self.items.verticalScrollBar().valueChanged.connect(lambda _value: self._materialize_visible())
        # The vertical bar appearing or disappearing changes the card width, so measure again.
        self.items.verticalScrollBar().rangeChanged.connect(lambda *_: QTimer.singleShot(0, self.refresh_item_size_hints))
        self.table.verticalScrollBar().valueChanged.connect(lambda _value: self._materialize_table_actions())
        self.apply_interface(self.parent_window.interface_name)

    def apply_interface(self, interface: str):
        self.parent_window.interface_name = interface
        self.items.setProperty("interface", interface)
        self.items.setViewMode(QListView.ViewMode.ListMode)
        self.items.setFlow(QListView.Flow.TopToBottom)
        self.items.setWrapping(False)
        self.items.setResizeMode(QListView.ResizeMode.Fixed)
        self.items.setMovement(QListView.Movement.Static)
        spacing = {"classic": 5, "compact": 1, "table": 0, "terminal": 4}.get(interface, 5)
        self.items.setSpacing(spacing)
        if interface == "table":
            self.mode_stack.setCurrentWidget(self.table)
        else:
            self.mode_stack.setCurrentWidget(self.list_page)
        self.render()

    def _card_width(self, viewport_width: int) -> int:
        return max(1, viewport_width)

    def move_selected_entry(self, delta: int, entry_id: str | None = None):
        if not self._visible_entries:
            return
        if entry_id is None:
            current = self.items.currentItem()
            entry_id = current.data(Qt.ItemDataRole.UserRole) if current else self._visible_entries[0]["id"]
        ids = [entry["id"] for entry in self._visible_entries]
        if entry_id not in ids:
            return
        old_index = ids.index(entry_id)
        new_index = max(0, min(len(ids) - 1, old_index + delta))
        if old_index == new_index:
            return
        ids.insert(new_index, ids.pop(old_index))
        self.persist_visible_order(ids)
        if self.sort_order.currentData() != "manual":
            self.sort_order.setCurrentIndex(self.sort_order.findData("manual"))
        else:
            self.render()

    def _render_table(self, entries: list[dict[str, Any]]):
        # Clearing the rows first also deletes the previous action widgets, so no row keeps a stale entry.
        self.table.setRowCount(0)
        self.table.setRowCount(len(entries))
        self._table_entries = entries
        for row, entry in enumerate(entries):
            values = (entry["title"], entry["category"], entry["content"].replace("\n", "  ·  "),
                      entry.get("runner", ""))
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 2:
                    item.setToolTip(entry["content"])
                item.setData(Qt.ItemDataRole.UserRole, entry["id"])
                self.table.setItem(row, column, item)
            self.table.setRowHeight(row, 42)
        self._materialize_table_actions()

    def _materialize_table_actions(self) -> None:
        """Create action buttons only for rows near the viewport; rows have a fixed height."""
        row_count = self.table.rowCount()
        if row_count == 0:
            return
        first = max(0, self.table.rowAt(0))
        last = self.table.rowAt(self.table.viewport().height())
        last = row_count - 1 if last < 0 else last
        first = max(0, first - TABLE_PREFETCH_ROWS)
        last = min(row_count - 1, last + TABLE_PREFETCH_ROWS)
        for row in range(first, last + 1):
            if self.table.cellWidget(row, 4) is None:
                self.table.setCellWidget(row, 4, self._table_actions(self._table_entries[row]))

    def _table_actions(self, entry: dict[str, Any]) -> QWidget:
        actions = QWidget()
        action_layout = QHBoxLayout(actions)
        action_layout.setContentsMargins(2, 1, 2, 1)
        action_layout.setSpacing(3)
        if self.kind == "command":
            runner = QComboBox()
            runner.addItems(RUNNERS)
            if entry.get("runner") in RUNNERS:
                runner.setCurrentText(entry["runner"])
            runner.insertSeparator(len(RUNNERS))
            runner.addItem("Pegar en ventana…")
            runner.setFixedWidth(132)
            action_layout.addWidget(runner)
            run = QPushButton("Ejecutar")
            run.clicked.connect(lambda _checked=False, e=entry, r=runner:
                                self.parent_window.run_entry(e, r.currentText()))
            action_layout.addWidget(run)
        elif self.kind == "url":
            open_button = QPushButton("Abrir")
            open_button.clicked.connect(lambda _checked=False, e=entry:
                                        self.parent_window.open_url(e))
            action_layout.addWidget(open_button)
        for label, callback in (
            ("Copiar", lambda e=entry: self.parent_window.copy_text(e["content"])),
            ("Editar", lambda e=entry: self.edit_entry(e)),
            ("Eliminar", lambda e=entry: self.delete_entry(e)),
            ("↑", lambda e=entry: self.move_selected_entry(-1, e["id"])),
            ("↓", lambda e=entry: self.move_selected_entry(1, e["id"])),
        ):
            button = QPushButton(label)
            button.clicked.connect(lambda _checked=False, fn=callback: fn())
            action_layout.addWidget(button)
        action_layout.addStretch(1)
        return actions

    def change_sort_mode(self, _index: int):
        mode = self.sort_order.currentData() or "manual"
        self.store.set_setting(f"entry_sort:{self.tab['id']}", mode)
        self.render()

    def organize_entries(self):
        dialog = EntryOrganizerDialog(self.store, self.tab, self)
        dialog.exec()
        self.render()

    def render(self):
        all_entries = self.store.list_entries(self.tab["id"])
        categories = sorted({entry["category"] for entry in all_entries if entry["category"]})
        selected = self.category.currentText()
        self.category.blockSignals(True)
        self.category.clear()
        self.category.addItem("Todas las categorías")
        self.category.addItems(categories)
        if selected in categories:
            self.category.setCurrentText(selected)
        self.category.blockSignals(False)

        query = self.search.text().casefold().strip()
        selected = self.category.currentText()
        filtered = [entry for entry in all_entries
                    if (selected == "Todas las categorías" or entry["category"] == selected)
                    and (not query or query in " ".join((entry["title"], entry["category"], entry["content"])).casefold())]
        sort_mode = self.sort_order.currentData() or "manual"
        def timestamp(entry: dict[str, Any], field: str) -> float:
            value = entry.get(field, "")
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
            except (AttributeError, TypeError, ValueError, OverflowError):
                return 0.0

        if sort_mode == "title_asc":
            filtered.sort(key=lambda entry: (entry["title"].casefold(), entry["category"].casefold()))
        elif sort_mode == "title_desc":
            filtered.sort(key=lambda entry: (entry["title"].casefold(), entry["category"].casefold()),
                          reverse=True)
        elif sort_mode == "category_asc":
            filtered.sort(key=lambda entry: (
                not bool(entry["category"].strip()), entry["category"].casefold(), entry["title"].casefold()
            ))
        elif sort_mode == "category_desc":
            filtered.sort(key=lambda entry: entry["title"].casefold())
            filtered.sort(key=lambda entry: entry["category"].casefold(), reverse=True)
        elif sort_mode == "updated_desc":
            filtered.sort(key=lambda entry: timestamp(entry, "updated_at"), reverse=True)
        elif sort_mode == "created_desc":
            filtered.sort(key=lambda entry: (-timestamp(entry, "created_at"), entry.get("position", 0)))
        elif sort_mode == "created_asc":
            filtered.sort(key=lambda entry: (timestamp(entry, "created_at"), entry.get("position", 0)))
        self._visible_entries = filtered
        self._entries_by_id = {entry["id"]: entry for entry in filtered}
        self._card_callbacks = {"run": self.parent_window.run_entry, "copy": self.parent_window.copy_text,
                                "edit": self.edit_entry, "delete": self.delete_entry,
                                "open": self.parent_window.open_url,
                                "drag_start": self.start_manual_drag, "drag_move": self.update_manual_drag,
                                "drag_finish": self.finish_manual_drag}
        self.items.clear()
        card_width = self._card_width(max(1, self.items.viewport().width()))
        for entry in filtered:
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, entry["id"])
            item.setSizeHint(QSize(card_width, self._estimated_height(entry, card_width)))
            self.items.addItem(item)
        QTimer.singleShot(0, self.refresh_item_size_hints)
        if not filtered:
            item = QListWidgetItem()
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            empty_title = "No se encontraron elementos" if (query or selected != "Todas las categorías") else f"No hay {KIND_LABELS.get(self.kind, 'elementos').lower()}s"
            empty_sub = "Prueba a cambiar los términos de búsqueda o el filtro de categoría." if (query or selected != "Todas las categorías") else "Comienza agregando un elemento a esta pestaña usando el botón."
            button_label = f"+ Nuevo {KIND_LABELS.get(self.kind, 'elemento')}"
            empty_widget = EmptyStateWidget(empty_title, empty_sub, button_label)
            empty_widget.action_clicked.connect(self.add_entry)
            item.setSizeHint(QSize(max(300, self.items.viewport().width()), 220))
            self.items.addItem(item)
            self.items.setItemWidget(item, empty_widget)
        if self.parent_window.interface_name == "table":
            self._render_table(filtered)

    def _card_key(self, entry: dict[str, Any]) -> tuple[str, str, str]:
        return (entry["id"], entry["updated_at"], self.parent_window.interface_name)

    def _estimated_height(self, entry: dict[str, Any], width: int) -> int:
        """Height for a row whose card does not exist yet: measured earlier, or estimated from the text."""
        cached = self._height_cache.get(self._card_key(entry))
        if cached is not None and cached[0] == width:
            return cached[1]
        metrics = QFontMetrics(self.items.font())
        chars_per_line = max(20, (width - 60) // max(1, metrics.averageCharWidth()))
        lines = sum(max(1, -(-len(line) // chars_per_line)) for line in entry["content"].splitlines()) or 1
        return max(120, lines * metrics.lineSpacing() + 110)

    def _materialize_visible(self) -> None:
        """Create card widgets only for rows near the viewport; other rows keep their sized placeholder."""
        viewport = self.items.viewport()
        if viewport.height() <= 0:
            return
        width = self._card_width(max(1, viewport.width()))
        window = viewport.rect().adjusted(0, -CARD_PREFETCH_PX, 0, CARD_PREFETCH_PX)
        for row in range(self.items.count()):
            item = self.items.item(row)
            rect = self.items.visualItemRect(item)
            if rect.top() > window.bottom():
                break
            if not rect.intersects(window) or self.items.itemWidget(item) is not None:
                continue
            entry = self._entries_by_id.get(item.data(Qt.ItemDataRole.UserRole))
            if entry is None:
                continue
            card = EntryCard(entry, self.kind, self._card_callbacks,
                             interface=self.parent_window.interface_name)
            size = card.size_for_width(width)
            item.setSizeHint(size)
            self._height_cache[self._card_key(entry)] = (width, size.height())
            self.items.setItemWidget(item, card)

    def refresh_item_size_hints(self):
        """Re-measure the existing cards at the list's width, then create the ones now visible."""
        width = self._card_width(max(1, self.items.viewport().width()))
        is_dark = self.parent_window.store.get_setting("theme", "Sistema") in {"Oscuro", "Sistema"}
        for index in range(self.items.count()):
            item = self.items.item(index)
            card = self.items.itemWidget(item)
            if card is not None and hasattr(card, "size_for_width"):
                if hasattr(card, "highlighter"):
                    card.highlighter.set_dark(is_dark)
                card.ensurePolished()
                size = card.size_for_width(width)
                item.setSizeHint(size)
                self._height_cache[self._card_key(card.entry)] = (width, size.height())
        self._materialize_visible()
        self._materialize_table_actions()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        QTimer.singleShot(0, self.refresh_item_size_hints)

    def start_manual_drag(self, entry_id: str, global_position: QPoint) -> None:
        if self._manual_drag is not None:
            return
        item = next((self.items.item(row) for row in range(self.items.count())
                     if self.items.item(row).data(Qt.ItemDataRole.UserRole) == entry_id), None)
        card = self.items.itemWidget(item) if item is not None else None
        if card is None:
            return
        card.set_dragging(True)
        preview = QLabel(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowDoesNotAcceptFocus
                         | Qt.WindowType.WindowTransparentForInput
                         | Qt.WindowType.WindowStaysOnTopHint)
        preview.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        preview.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        preview.setPixmap(card.grab())
        preview.setWindowOpacity(0.88)
        preview.adjustSize()
        marker = QFrame(self.items.viewport())
        marker.setFixedHeight(4)
        marker.setStyleSheet("QFrame { background-color: #20a889; border: 0; border-radius: 2px; }")
        self._manual_drag = {"entry_id": entry_id, "card": card, "preview": preview,
                             "marker": marker, "drop_index": None}
        preview.show()
        self.update_manual_drag(entry_id, global_position)

    def update_manual_drag(self, entry_id: str, global_position: QPoint) -> None:
        state = self._manual_drag
        if state is None or state["entry_id"] != entry_id:
            return
        state["preview"].move(global_position + QPoint(18, 18))
        viewport = self.items.viewport()
        position = viewport.mapFromGlobal(global_position)
        if not (0 <= position.x() < viewport.width() and 0 <= position.y() < viewport.height()):
            state["drop_index"] = None
            state["marker"].hide()
            return

        scrollbar = self.items.verticalScrollBar()
        if position.y() < 18:
            scrollbar.setValue(scrollbar.value() - 14)
        elif position.y() >= viewport.height() - 18:
            scrollbar.setValue(scrollbar.value() + 14)

        drop_index = self.items.count()
        marker_y = viewport.height() - state["marker"].height()
        for row in range(self.items.count()):
            rect = self.items.visualItemRect(self.items.item(row))
            if position.y() < rect.center().y():
                drop_index = row
                marker_y = rect.top() - state["marker"].height() // 2
                break
        state["drop_index"] = drop_index
        state["marker"].setGeometry(
            0, max(0, marker_y), viewport.width(), state["marker"].height()
        )
        state["marker"].show()
        state["marker"].raise_()

    def finish_manual_drag(self, entry_id: str, global_position: QPoint) -> None:
        state = self._manual_drag
        if state is None or state["entry_id"] != entry_id:
            return
        self.update_manual_drag(entry_id, global_position)
        state = self._manual_drag
        drop_index = state["drop_index"] if state else None
        visible_ids = [self.items.item(index).data(Qt.ItemDataRole.UserRole)
                       for index in range(self.items.count())
                       if self.items.item(index).data(Qt.ItemDataRole.UserRole)]
        self._clear_manual_drag()

        if drop_index is None or entry_id not in visible_ids:
            return
        source_index = visible_ids.index(entry_id)
        target_index = min(drop_index, len(visible_ids))
        if target_index > source_index:
            target_index -= 1
        reordered_ids = list(visible_ids)
        reordered_ids.pop(source_index)
        reordered_ids.insert(max(0, min(target_index, len(reordered_ids))), entry_id)
        if reordered_ids == visible_ids:
            return

        self.persist_visible_order(reordered_ids)
        if self.sort_order.currentData() != "manual":
            self.sort_order.setCurrentIndex(self.sort_order.findData("manual"))
            return
        self.render()

    def _clear_manual_drag(self) -> None:
        state = self._manual_drag
        self._manual_drag = None
        if state is None:
            return
        state["marker"].hide()
        state["marker"].deleteLater()
        state["preview"].close()
        state["preview"].deleteLater()
        try:
            state["card"].set_dragging(False)
        except RuntimeError:
            pass

    def persist_visible_order(self, visible_ids: list[str]) -> None:
        if len(visible_ids) < 2:
            return
        all_entries = self.store.list_entries(self.tab["id"])
        entry_by_id = {entry["id"]: entry for entry in all_entries}
        visible_id_set = set(visible_ids)
        occupied_positions = [index for index, entry in enumerate(all_entries)
                              if entry["id"] in visible_id_set]
        reordered = list(all_entries)
        for position, entry_id in zip(occupied_positions, visible_ids):
            reordered[position] = entry_by_id[entry_id]
        try:
            self.store.reorder_entries(self.tab["id"], [entry["id"] for entry in reordered])
        except (ValueError, sqlite3.Error) as exc:
            QMessageBox.critical(self, "No se pudo guardar el orden", str(exc))
            self.render()

    def add_entry(self):
        dialog = EntryDialog(self.kind, self, store=self.store)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        title, category, content, runner = dialog.values()
        try:
            self.store.save_entry(self.tab["id"], self.kind, title, category, content, runner)
        except (ValueError, sqlite3.Error) as exc:
            QMessageBox.critical(self, "No se pudo guardar", str(exc))
        self.render()

    def edit_entry(self, entry: dict[str, Any]):
        dialog = EntryDialog(self.kind, self, entry)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        title, category, content, runner = dialog.values()
        try:
            self.store.save_entry(self.tab["id"], self.kind, title, category, content, runner, entry["id"])
        except (ValueError, sqlite3.Error) as exc:
            QMessageBox.critical(self, "No se pudo guardar", str(exc))
        self.render()

    def delete_entry(self, entry: dict[str, Any]):
        result = QMessageBox.question(self, "Eliminar elemento", f"¿Eliminar «{entry['title']}»?",
                                      QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                      QMessageBox.StandardButton.No)
        if result == QMessageBox.StandardButton.Yes:
            try:
                self.store.delete_entry(entry["id"])
            except sqlite3.Error as exc:
                QMessageBox.critical(self, "No se pudo eliminar", str(exc))
            self.render()


def copy_mime_data(source: QMimeData | None) -> QMimeData:
    """Deep-copy clipboard contents so they survive the clipboard being overwritten."""
    copy = QMimeData()
    if source is not None:
        for fmt in source.formats():
            copy.setData(fmt, source.data(fmt))
    return copy


def restore_clipboard(previous: QMimeData, pasted_text: str) -> None:
    """Put the previous clipboard back, unless the user copied something else in the meantime."""
    clipboard = QApplication.clipboard()
    if clipboard.text() != pasted_text:
        return
    if previous.formats():
        clipboard.setMimeData(copy_mime_data(previous))
    else:
        clipboard.clear()


class CommandCenterWindow(QMainWindow):
    def __init__(self, store: DataStore):
        super().__init__()
        self.store = store
        self.pages: dict[str, CollectionPage] = {}
        self.setWindowTitle("Command Center")
        self.interface_name = store.get_setting("interface", "classic")
        if self.interface_name not in INTERFACE_LABELS:
            self.interface_name = "classic"
        self.menuBar().hide()
        self.setMinimumSize(900, 620)
        self.resize(1150, 800)
        icon = resource_path("app_icon.ico")
        if icon.is_file():
            self.setWindowIcon(QIcon(str(icon)))

        central = QWidget()
        central.setObjectName("mainContainer")
        layout = QVBoxLayout(central)
        toolbar = QHBoxLayout()
        self.new_command_button = QPushButton("+ Nuevo comando")
        self.new_command_button.setObjectName("primaryButton")
        self.new_command_button.clicked.connect(self.add_command)
        self.rename_tab_button = QPushButton("Renombrar pestaña")
        self.rename_tab_button.clicked.connect(self.rename_tab)
        self.archive_tab_button = QPushButton("Archivar pestaña")
        self.archive_tab_button.clicked.connect(self.archive_tab)
        self.suggestions_button = QPushButton("Sugerencias")
        self.suggestions_button.clicked.connect(self.open_suggestions)
        self.options_button = QPushButton("Opciones")
        self.options_button.clicked.connect(self.open_options)
        hints = QApplication.styleHints()
        if hasattr(hints, "colorSchemeChanged"):
            hints.colorSchemeChanged.connect(self.system_theme_changed)
        for button in (self.new_command_button, self.rename_tab_button, self.archive_tab_button,
                       self.suggestions_button, self.options_button):
            toolbar.addWidget(button)
        layout.addLayout(toolbar)

        self.tabs = TabWorkspace(self.add_tab)
        self.tabs.setMovable(True)
        self.tabs.tabBar().tabMoved.connect(self.tabs_moved)
        self.tabs.tabBar().setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tabs.tabBar().customContextMenuRequested.connect(self.show_tab_context_menu)
        layout.addWidget(self.tabs, 1)
        self.setCentralWidget(central)
        self.statusBar().showMessage("Listo", 3000)
        self.populate_tabs()
        self.apply_interface(self.interface_name, persist=False)
        self.apply_theme(self.store.get_setting("theme", "Sistema"), persist=False)
        self._restore_geometry()
        self._add_shortcuts()

    def open_options(self):
        OptionsDialog(self).exec()

    def apply_interface(self, interface: str, persist: bool = True):
        if interface not in INTERFACE_LABELS:
            interface = "classic"
        self.interface_name = interface
        if persist:
            self.store.set_setting("interface", interface)
        central = self.centralWidget()
        central.setProperty("interface", interface)
        self.tabs.tabBar().setProperty("interface", interface)
        for page in self.pages.values():
            page.apply_interface(interface)
        for widget in (central, *central.findChildren(QWidget)):
            widget.style().unpolish(widget)
            widget.style().polish(widget)
            widget.update()
        self.refresh_entry_card_sizes()

    def open_suggestions(self):
        SuggestionsDialog(self).exec()

    def _add_shortcuts(self):
        QShortcut(QKeySequence.StandardKey.New, self, activated=self.current_page_add)
        QShortcut(QKeySequence("Ctrl+Shift+N"), self, activated=self.add_tab)

    def populate_tabs(self, select_id: str | None = None):
        self.pages.clear()
        self.tabs.blockSignals(True)
        self.tabs.clear()
        for tab in self.store.list_tabs():
            page = CollectionPage(self.store, tab, self)
            self.pages[tab["id"]] = page
            self.tabs.addTab(page, tab["name"])
            page.tab = tab
        self.tabs.blockSignals(False)
        if select_id in self.pages:
            self.tabs.setCurrentWidget(self.pages[select_id])

    def current_page(self) -> CollectionPage | None:
        page = self.tabs.currentWidget()
        return page if isinstance(page, CollectionPage) else None

    def current_page_add(self):
        page = self.current_page()
        if page:
            page.add_entry()

    def add_command(self):
        for index in range(self.tabs.count()):
            page = self.tabs.widget(index)
            if isinstance(page, CollectionPage) and page.kind == "command":
                self.tabs.setCurrentIndex(index)
                page.add_entry()
                return
        QMessageBox.warning(self, "No hay colección de comandos", "No se encontró la pestaña Comandos.")

    def add_tab(self):
        name, accepted = QInputDialog.getText(self, "Nueva pestaña", "Nombre de la pestaña:")
        name = name.strip()
        if not accepted:
            return
        if not name:
            QMessageBox.warning(self, "Nombre vacío", "Escribe un nombre para la pestaña.")
            return
        if any(tab["name"].casefold() == name.casefold() for tab in self.store.list_tabs(include_archived=True)):
            QMessageBox.warning(self, "Nombre duplicado", "Ya existe una pestaña con ese nombre.")
            return
        try:
            tab_id = self.store.create_tab(name)
        except (ValueError, sqlite3.Error) as exc:
            QMessageBox.critical(self, "No se pudo crear la pestaña", str(exc))
            return
        self.populate_tabs(tab_id)

    def rename_tab(self):
        page = self.current_page()
        if not page:
            return
        name, accepted = QInputDialog.getText(self, "Renombrar pestaña", "Nombre:", text=page.tab["name"])
        name = name.strip()
        if not accepted:
            return
        if not name:
            QMessageBox.warning(self, "Nombre vacío", "El nombre no puede estar vacío.")
            return
        duplicate = any(tab["id"] != page.tab["id"] and tab["name"].casefold() == name.casefold()
                        for tab in self.store.list_tabs(include_archived=True))
        if duplicate:
            QMessageBox.warning(self, "Nombre duplicado", "Ya existe una pestaña con ese nombre.")
            return
        try:
            self.store.rename_tab(page.tab["id"], name)
        except (ValueError, sqlite3.Error) as exc:
            QMessageBox.critical(self, "No se pudo renombrar la pestaña", str(exc))
            return
        self.populate_tabs(page.tab["id"])

    def archive_tab(self):
        page = self.current_page()
        if not page:
            return
        count = len(self.store.list_entries(page.tab["id"]))
        dialog = QMessageBox(self)
        dialog.setWindowTitle("Archivar pestaña")
        dialog.setText(f"Se ocultará «{page.tab['name']}» y sus {count} elementos.")
        dialog.setInformativeText("Podrás restaurarla desde Pestañas archivadas.")
        archive = dialog.addButton("Archivar", QMessageBox.ButtonRole.AcceptRole)
        dialog.addButton("Cancelar", QMessageBox.ButtonRole.RejectRole)
        dialog.exec()
        if dialog.clickedButton() == archive:
            try:
                self.store.archive_tab(page.tab["id"])
            except (ValueError, sqlite3.Error) as exc:
                QMessageBox.critical(self, "No se pudo archivar la pestaña", str(exc))
                return
            self.populate_tabs()

    def show_archived(self):
        dialog = ArchivedTabsDialog(self.store, self)
        dialog.exec()
        self.populate_tabs()

    def tabs_moved(self, _from: int, _to: int):
        ordered_ids = [self.tabs.widget(index).tab["id"] for index in range(self.tabs.count())]
        try:
            self.store.reorder_tabs(ordered_ids)
        except (ValueError, sqlite3.Error) as exc:
            QMessageBox.critical(self, "No se pudo guardar el orden", str(exc))
            self.populate_tabs()

    def show_tab_context_menu(self, point):
        index = self.tabs.tabBar().tabAt(point)
        if index < 0 or index >= self.tabs.count():
            return
        self.tabs.setCurrentIndex(index)
        menu = QMenu(self)
        menu.addAction("Renombrar", self.rename_tab)
        menu.addAction("Archivar", self.archive_tab)
        menu.exec(self.tabs.tabBar().mapToGlobal(point))

    def apply_theme(self, theme: str, persist: bool = True):
        app = QApplication.instance()
        if persist:
            self.store.set_setting("theme", theme)
        system_is_dark = False
        if theme == "Sistema":
            try:
                system_is_dark = app.styleHints().colorScheme() == Qt.ColorScheme.Dark
            except AttributeError:
                system_is_dark = False
        dark = theme == "Oscuro" or system_is_dark
        colors = get_theme_colors(dark)
        palette = QPalette(app.style().standardPalette())
        role_values = {
            QPalette.ColorRole.Window: colors["window"],
            QPalette.ColorRole.WindowText: colors["text"],
            QPalette.ColorRole.Base: colors["surface"],
            QPalette.ColorRole.AlternateBase: colors["raised"],
            QPalette.ColorRole.ToolTipBase: colors["surface"],
            QPalette.ColorRole.ToolTipText: colors["text"],
            QPalette.ColorRole.Text: colors["text"],
            QPalette.ColorRole.Button: colors["surface"],
            QPalette.ColorRole.ButtonText: colors["text"],
            QPalette.ColorRole.BrightText: colors["danger"],
            QPalette.ColorRole.Highlight: colors["accent" if dark else "selection"],
            QPalette.ColorRole.HighlightedText: colors["accent_text"] if dark else colors["text"],
            QPalette.ColorRole.Link: colors["accent"],
            QPalette.ColorRole.PlaceholderText: colors["muted"],
        }
        for role, color in role_values.items():
            palette.setColor(role, QColor(color))
        app.setPalette(palette)
        app.setStyleSheet(build_application_stylesheet(colors))
        QTimer.singleShot(0, self.refresh_entry_card_sizes)

    def refresh_entry_card_sizes(self):
        """Recalculate entry rows after the active theme changes their metrics."""
        for page in self.pages.values():
            page.refresh_item_size_hints()

    def system_theme_changed(self, _scheme=None):
        if self.store.get_setting("theme", "Sistema") == "Sistema":
            self.apply_theme("Sistema", persist=False)

    def copy_text(self, text: str):
        QApplication.clipboard().setText(text)
        self.statusBar().showMessage("Copiado al portapapeles", 1800)

    def run_entry(self, entry: dict[str, Any], runner: str | None = None):
        runner = runner or entry.get("runner", "PowerShell")
        command_text = entry["content"]
        if PARAMETER_PATTERN.search(command_text):
            dialog = CommandParametersDialog(entry["title"], command_text, runner, self)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            command_text = dialog.command
        if runner == "Pegar en ventana…":
            dialog = WindowPickerDialog(self, entry["title"])
            if dialog.exec() != QDialog.DialogCode.Accepted or not dialog.selected_window:
                return
            self.paste_into_window(dialog.selected_window["handle"], command_text)
            return
        try:
            launch_script(runner, command_text)
            self.statusBar().showMessage(f"Consola {runner} iniciada", 2500)
        except ProcessLaunchError as exc:
            QMessageBox.critical(self, "No se pudo iniciar", str(exc))

    def paste_into_window(self, handle: int, text: str) -> None:
        """Paste text through the clipboard, then give the user's previous clipboard back."""
        clipboard = QApplication.clipboard()
        previous = copy_mime_data(clipboard.mimeData())
        clipboard.setText(text)
        try:
            title = paste_text_into_window(handle, text)
        except ProcessLaunchError as exc:
            restore_clipboard(previous, text)
            QMessageBox.warning(self, "No se pudo pegar", str(exc))
            return
        self.statusBar().showMessage(f"Texto pegado en {title}; no se envió Intro", 4500)
        QTimer.singleShot(PASTE_RESTORE_DELAY_MS, lambda: restore_clipboard(previous, text))

    def open_url(self, entry: dict[str, Any]):
        url = QUrl(entry["content"])
        if url.scheme().lower() not in {"http", "https"} or not url.host():
            QMessageBox.warning(self, "Enlace bloqueado", "Por seguridad solo se abren enlaces http y https válidos.")
            return
        if not QDesktopServices.openUrl(url):
            QMessageBox.warning(self, "No se pudo abrir", "Windows no pudo abrir el enlace.")

    def backup_database(self):
        try:
            path = self.store.backup()
            QMessageBox.information(self, "Copia creada", f"Se creó la copia de seguridad:\n{path.name}")
        except OSError as exc:
            QMessageBox.critical(self, "Error de copia", str(exc))

    def change_storage_location(self) -> bool:
        dialog = StorageLocationDialog(self, initial_directory=self.store.directory)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return False
        try:
            destination = dialog.database_path().resolve()
            if destination == self.store.path.resolve():
                QMessageBox.information(self, "Ubicación sin cambios", "La base de datos ya está en esa carpeta.")
                return False
            safety_copy = self.store.move_database(destination)
            QMessageBox.information(
                self, "Base de datos movida",
                f"La base de datos ahora está en:\n{self.store.path}\n\n"
                f"Se conservó una copia de seguridad en la ubicación anterior: {safety_copy.name}",
            )
            return True
        except (OSError, ValueError, sqlite3.Error) as exc:
            QMessageBox.critical(self, "No se pudo mover la base de datos", str(exc))
            return False

    def export_data(self):
        from PySide6.QtWidgets import QFileDialog
        filename, _ = QFileDialog.getSaveFileName(self, "Exportar datos", "command-center-export.json", "JSON (*.json)")
        if not filename:
            return
        try:
            self.store.export_json(Path(filename))
            QMessageBox.information(self, "Exportación terminada", "Los datos se exportaron correctamente.")
        except OSError as exc:
            QMessageBox.critical(self, "Error de exportación", str(exc))

    def import_data(self):
        from PySide6.QtWidgets import QFileDialog
        filename, _ = QFileDialog.getOpenFileName(self, "Importar datos JSON", "", "JSON (*.json)")
        if not filename:
            return
        self.import_json_file(Path(filename))

    def import_json_file(self, source: Path):
        answer = QMessageBox.warning(
            self, "Combinar colecciones",
            "La importación añadirá las colecciones del archivo a las actuales. No sustituirá ni eliminará datos. "
            "Las entradas idénticas se omitirán y se creará antes una copia de seguridad local.\n\n"
            "Los JSON de versiones anteriores también son compatibles.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            safety_copy, report = self.store.merge_from_json(source)
            self.populate_tabs()
            detail = f"\nAvisos: {report}" if report else ""
            QMessageBox.information(self, "Importación terminada",
                                    f"Los datos se importaron. Copia anterior: {safety_copy.name}{detail}")
        except (OSError, ValueError, sqlite3.Error) as exc:
            QMessageBox.critical(self, "Error de importación", str(exc))

    def _restore_geometry(self):
        geometry = self.store.get_setting("window_geometry")
        if geometry:
            self.restoreGeometry(bytes.fromhex(geometry))

    def closeEvent(self, event):
        self.store.set_setting("window_geometry", bytes(self.saveGeometry()).hex())
        self.store.close()
        event.accept()


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Command Center")
    app.setOrganizationName("CommandCenter")
    app.setApplicationVersion(__version__)

    configured_path = load_database_location()
    if configured_path:
        try:
            store = DataStore(configured_path)
        except (OSError, sqlite3.Error) as exc:
            QMessageBox.critical(None, "No se pudo abrir la base de datos", f"{configured_path}\n\n{exc}")
            return 1
    else:
        location_dialog = StorageLocationDialog()
        if location_dialog.exec() != QDialog.DialogCode.Accepted:
            return 0
        try:
            selected_path = location_dialog.database_path().resolve()
            default_path = (application_data_dir() / DATABASE_FILENAME).resolve()
            if selected_path.exists() and selected_path != default_path:
                use_existing = QMessageBox.question(
                    None, "Base de datos existente",
                    "Ya existe una base de datos en la carpeta seleccionada. ¿Quieres usarla?\n\n"
                    "La base anterior de la carpeta del usuario, si existe, se conservará separada y no se fusionará.",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                    QMessageBox.StandardButton.Cancel,
                )
                if use_existing != QMessageBox.StandardButton.Yes:
                    return 0
                store = DataStore(selected_path)
                save_database_location(selected_path)
            else:
                store = DataStore(default_path)
                if selected_path != default_path:
                    store.move_database(selected_path)
                else:
                    save_database_location(selected_path)
        except (OSError, ValueError, sqlite3.Error) as exc:
            QMessageBox.critical(None, "No se pudo preparar la base de datos", str(exc))
            return 1
    saved_interface = store.get_setting("interface")
    if saved_interface in {"fluent", "sidebar", "board", "launcher", "explorer"}:
        saved_interface = "classic"
        store.set_setting("interface", saved_interface)
    if saved_interface not in INTERFACE_LABELS:
        interface_dialog = InterfacePickerDialog(first_run=True)
        if interface_dialog.exec() != QDialog.DialogCode.Accepted:
            store.close()
            return 0
        store.set_setting("interface", interface_dialog.selected_interface)
    window = CommandCenterWindow(store)
    window.show()
    return app.exec()
