"""Dialogs and option screens for Command Center. Each one reads and writes through DataStore."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QUrl
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QInputDialog,
    QRadioButton,
    QFileDialog,
    QButtonGroup,
    QScrollArea,
)
from . import __version__
from .processes import ProcessLaunchError, enumerate_visible_windows
from .storage import DATABASE_FILENAME, DataStore, application_data_dir, resource_path
from .suggestions import (
    build_destination_index,
    build_organization_suggestions,
    normalize_text,
    plain_text_blocks,
    recommend_plain_text_destination,
)
from .ui import ScriptSyntaxHighlighter
from . import __version__
from .constants import INTERFACE_LABELS, KIND_LABELS, PARAMETER_PATTERN, RISKY_VALUE_CHARS, RUNNERS


class EntryDialog(QDialog):
    def __init__(self, kind: str, parent=None, entry: dict[str, Any] | None = None,
                 store: DataStore | None = None):
        super().__init__(parent)
        self.kind = kind
        self.store = store
        self.setWindowTitle(f"{'Editar' if entry else 'Nuevo'} {KIND_LABELS.get(kind, 'Elemento')}")
        self.setMinimumWidth(520)
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.title = QLineEdit(entry["title"] if entry else "")
        form.addRow("Título:", self.title)
        self.category = QLineEdit(entry["category"] if entry else "")
        category_label = "Juego:" if kind == "game" else "Categoría:"
        form.addRow(category_label, self.category)

        self.content = QTextEdit()
        self.content.setAcceptRichText(False)
        self.content.setMinimumHeight(150)
        self.content.setPlainText(entry["content"] if entry else "")
        if kind == "command":
            self.content_highlighter = ScriptSyntaxHighlighter(
                self.content.document(),
                runner=entry.get("runner", "PowerShell") if entry else "PowerShell"
            )
        content_label = {"command": "Comando / script:", "game": "Truco / comando:",
                         "url": "URL (http o https):", "note": "Contenido:"}[kind]
        form.addRow(content_label, self.content)
        if kind == "command":
            parameter_row = QHBoxLayout()
            parameter_help = QLabel("Usa {{nombre}} para pedir un valor al ejecutar.")
            parameter_help.setWordWrap(True)
            parameter_button = QPushButton("Insertar parámetro…")
            parameter_button.clicked.connect(self.insert_parameter)
            parameter_row.addWidget(parameter_help, 1)
            parameter_row.addWidget(parameter_button)
            form.addRow("Parámetros:", parameter_row)

        self.runner = QComboBox()
        self.runner.addItems(RUNNERS)
        if entry and entry.get("runner") in RUNNERS:
            self.runner.setCurrentText(entry["runner"])
        if kind == "command":
            self.runner.currentTextChanged.connect(
                lambda r: getattr(self, "content_highlighter", None) and self.content_highlighter.set_runner(r)
            )
        form.addRow("Ejecutar con:", self.runner)
        self.runner.setVisible(kind == "command")
        form.labelForField(self.runner).setVisible(kind == "command")

        layout.addLayout(form)
        if kind == "command" and entry is None and store is not None:
            suggest_button = QPushButton("Sugerir título y categoría")
            suggest_button.clicked.connect(self.suggest_command_metadata)
            layout.addWidget(suggest_button, 0, Qt.AlignmentFlag.AlignLeft)
            self.suggestion_preview = QLabel()
            self.suggestion_preview.setWordWrap(True)
            self.suggestion_preview.hide()
            layout.addWidget(self.suggestion_preview)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def insert_parameter(self):
        name, accepted = QInputDialog.getText(
            self, "Insertar parámetro", "Nombre del valor que se solicitará:"
        )
        name = name.strip()
        if accepted and name and not any(char in name for char in "{}\r\n"):
            self.content.insertPlainText("{{" + name + "}}")

    def suggest_command_metadata(self):
        content = self.content.toPlainText().strip()
        if not content:
            QMessageBox.information(self, "Falta el comando", "Escribe el comando para poder analizarlo.")
            return
        parsed = plain_text_blocks(content)
        suggested_title = parsed[0][0] if parsed else "Comando importado"
        current_title = self.title.text().strip()
        if current_title and normalize_text(current_title) not in {
            "comando", "nuevo comando", "sin titulo"
        }:
            suggested_title = current_title
        recommendation = recommend_plain_text_destination(
            content, suggested_title, build_destination_index(self.store)
        ) if self.store is not None else None
        if recommendation is None:
            QMessageBox.information(self, "Sin sugerencias", "No hay una colección de comandos disponible para comparar.")
            return
        if not self.title.text().strip() or normalize_text(self.title.text()) in {
            "comando", "nuevo comando", "sin titulo"
        }:
            self.title.setText(suggested_title)
        current_category = self.category.text().strip()
        if not current_category or normalize_text(current_category) == "general":
            self.category.setText(recommendation["category"])
        if recommendation["runner"] in RUNNERS:
            self.runner.setCurrentText(recommendation["runner"])
        self.suggestion_preview.setText(
            f"Propuesta: {self.title.text().strip()} · {self.category.text().strip() or 'General'} · "
            f"{recommendation['runner']}. Se han rellenado los campos vacíos o genéricos; puedes editarlos."
        )
        self.suggestion_preview.show()

    def values(self) -> tuple[str, str, str, str]:
        title = self.title.text().strip()
        category = self.category.text().strip() or "General"
        content = self.content.toPlainText().strip()
        runner = self.runner.currentText()
        return title, category, content, runner

    def accept(self):
        title, _, content, _ = self.values()
        if not title or not content:
            QMessageBox.warning(self, "Faltan datos", "El título y el contenido son obligatorios.")
            return
        if self.kind == "url":
            parsed = QUrl(content)
            if parsed.scheme().lower() not in {"http", "https"} or not parsed.host():
                QMessageBox.warning(self, "URL no válida", "Introduce una URL completa que empiece por http:// o https://.")
                return
        super().accept()

class CommandParametersDialog(QDialog):
    """Collect literal template values and require a preview before execution."""

    def __init__(self, title: str, template: str, runner: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Preparar comando · {title}")
        self.resize(760, 560)
        self.template = template
        self.command = template
        self.fields: dict[str, QLineEdit] = {}
        layout = QVBoxLayout(self)
        names = list(dict.fromkeys(match.group(1).strip()
                                   for match in PARAMETER_PATTERN.finditer(template)))
        layout.addWidget(QLabel(
            f"Introduce los valores para {runner}. Se insertan literalmente; revisa el comando completo "
            "y sus comillas antes de continuar."
        ))
        self.warning = QLabel()
        self.warning.setWordWrap(True)
        self.warning.setStyleSheet("color: #b45309; font-weight: 600;")
        self.warning.hide()
        layout.addWidget(self.warning)
        form = QFormLayout()
        for name in names:
            field = QLineEdit()
            field.setPlaceholderText(f"Valor para {name}")
            field.textChanged.connect(self.refresh_preview)
            self.fields[name] = field
            form.addRow(name + ":", field)
        layout.addLayout(form)
        layout.addWidget(QLabel("Vista previa exacta:"))
        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.preview.setMinimumHeight(180)
        layout.addWidget(self.preview, 1)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Continuar")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.refresh_preview()

    def refresh_preview(self, _value: str = ""):
        values = {name: field.text() for name, field in self.fields.items()}
        risky = sorted({char for value in values.values() for char in value if char in RISKY_VALUE_CHARS})
        self.warning.setVisible(bool(risky))
        if risky:
            self.warning.setText(
                "Revisa las comillas y los caracteres especiales (" + " ".join(risky)
                + "): el valor se inserta tal cual y el intérprete puede interpretarlo."
            )
        rendered = PARAMETER_PATTERN.sub(
            lambda match: values.get(match.group(1).strip(), match.group(0)), self.template
        )
        self.preview.setPlainText(rendered)
        self.command = rendered

    def accept(self):
        self.refresh_preview()
        super().accept()

class WindowPickerDialog(QDialog):
    """Choose a visible application window as a paste target."""

    def __init__(self, parent=None, command_title: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Pegar en una ventana abierta")
        self.resize(650, 480)
        self.selected_window: dict[str, Any] | None = None
        layout = QVBoxLayout(self)
        if command_title:
            command_label = QLabel(f"Texto que se va a pegar: «{command_title}»")
            command_label.setWordWrap(True)
            layout.addWidget(command_label)
        instructions = QLabel(
            "Elige una ventana. Se pegará el texto en el control que tenga el foco; "
            "Command Center no enviará Intro ni ejecutará el texto por sí mismo. "
            "El contenido se copiará al portapapeles para poder pegarlo y, después, se restaurará "
            "el contenido anterior del portapapeles. La aplicación elegida puede procesar lo pegado "
            "según su propio funcionamiento."
        )
        instructions.setWordWrap(True)
        layout.addWidget(instructions)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Filtrar por título o aplicación…")
        layout.addWidget(self.search)
        self.targets = QListWidget()
        layout.addWidget(self.targets, 1)
        try:
            self.windows = enumerate_visible_windows()
        except ProcessLaunchError as exc:
            self.windows = []
            QMessageBox.warning(self, "No se pudieron listar ventanas", str(exc))
        for target in self.windows:
            item = QListWidgetItem(
                f"{target['title']}   —   {target['process']} (PID {target['pid']})"
            )
            item.setData(Qt.ItemDataRole.UserRole, target)
            self.targets.addItem(item)
        self.search.textChanged.connect(self.filter_targets)
        self.targets.itemDoubleClicked.connect(lambda _item: self.accept_selection())
        buttons = QHBoxLayout()
        paste_button = QPushButton("Pegar en ventana seleccionada")
        paste_button.clicked.connect(self.accept_selection)
        cancel_button = QPushButton("Cancelar")
        cancel_button.clicked.connect(self.reject)
        buttons.addStretch(1)
        buttons.addWidget(paste_button)
        buttons.addWidget(cancel_button)
        layout.addLayout(buttons)
        if self.targets.count():
            self.targets.setCurrentRow(0)

    def filter_targets(self, query: str):
        terms = query.casefold().strip()
        first_visible = None
        for index in range(self.targets.count()):
            item = self.targets.item(index)
            hidden = bool(terms) and terms not in item.text().casefold()
            item.setHidden(hidden)
            if not hidden and first_visible is None:
                first_visible = item
        current = self.targets.currentItem()
        if current is None or current.isHidden():
            self.targets.setCurrentItem(first_visible)

    def accept_selection(self):
        item = self.targets.currentItem()
        if item is None or item.isHidden():
            QMessageBox.information(self, "Selecciona una ventana", "Elige una ventana visible de la lista.")
            return
        self.selected_window = item.data(Qt.ItemDataRole.UserRole)
        self.accept()

class SuggestionCard(QWidget):
    def __init__(self, suggestion: dict[str, Any], on_apply, on_dismiss, parent=None):
        super().__init__(parent)
        self.suggestion = suggestion
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(5)
        is_tab_suggestion = suggestion.get("action") == "create_tab"
        if is_tab_suggestion:
            header_text = f"Crear pestaña «{suggestion['tab_name']}»  ·  {suggestion['source_tab_name']}"
        else:
            header_text = f"{suggestion['entry']['title']}  ·  {suggestion['tab_name']}"
        header = QLabel(header_text)
        header.setStyleSheet("font-weight: 600;")
        header.setWordWrap(True)
        layout.addWidget(header)
        if is_tab_suggestion:
            value_text = f"Mover {suggestion['entry_count']} notas con esta categoría a la nueva pestaña."
        else:
            field_label = "Título" if suggestion["field"] == "title" else "Categoría"
            value_text = f"{field_label} sugerido: {suggestion['value']}"
        value = QLabel(value_text)
        value.setWordWrap(True)
        layout.addWidget(value)
        reason = QLabel(suggestion["reason"])
        reason.setWordWrap(True)
        layout.addWidget(reason)
        buttons = QHBoxLayout()
        apply_button = QPushButton(
            f"Crear pestaña y mover {suggestion['entry_count']} notas"
            if is_tab_suggestion else "Aplicar esta sugerencia"
        )
        apply_button.clicked.connect(lambda: on_apply(self))
        dismiss_button = QPushButton("Omitir")
        dismiss_button.clicked.connect(lambda: on_dismiss(self))
        buttons.addWidget(apply_button)
        buttons.addWidget(dismiss_button)
        buttons.addStretch(1)
        layout.addLayout(buttons)

class SuggestionsDialog(QDialog):
    """Separate actionable suggestions from informational guidance."""

    def __init__(self, window: "CommandCenterWindow"):
        super().__init__(window)
        self.window = window
        self.setWindowTitle("Sugerencias de organización")
        self.resize(780, 620)
        layout = QVBoxLayout(self)
        self.sections = QTabWidget()
        layout.addWidget(self.sections, 1)

        actionable = QWidget()
        actionable_layout = QVBoxLayout(actionable)
        explanation = QLabel(
            "Las propuestas se calculan en este equipo con los textos guardados. "
            "No se cambia nada automáticamente: aplica u omite cada propuesta por separado."
        )
        explanation.setWordWrap(True)
        actionable_layout.addWidget(explanation)
        import_text_button = QPushButton("Pegar o importar texto plano…")
        import_text_button.clicked.connect(self.import_plain_text)
        actionable_layout.addWidget(import_text_button)
        self.suggestion_list = QListWidget()
        self.suggestion_list.setSpacing(6)
        actionable_layout.addWidget(self.suggestion_list, 1)
        self.sections.addTab(actionable, "Sugerencias")

        guidance = QWidget()
        guidance_layout = QVBoxLayout(guidance)
        guidance_text = QLabel(
            "Las sugerencias son heurísticas, no instrucciones ni una validación del contenido. "
            "\n\n• Los títulos propuestos usan la primera línea de entradas con títulos genéricos."
            "\n\n• Las categorías se recomiendan por similitud con elementos de la misma pestaña."
            "\n\n• Se puede proponer una pestaña nueva cuando varias notas de una pestaña comparten una categoría y otras notas quedan fuera de ese grupo."
            "\n\n• Los archivos de texto se separan por líneas en blanco o encabezados Markdown. Puedes revisar y editar título, categoría y pestaña antes de añadir cada bloque."
            "\n\n• El análisis del archivo se realiza localmente; no se envía el texto a servicios externos."
            "\n\n• Revisa el valor sugerido antes de aplicarlo. Cada cambio se guarda de forma individual."
            "\n\n• El análisis no usa IA, red ni dependencias externas."
        )
        guidance_text.setWordWrap(True)
        guidance_layout.addWidget(guidance_text)
        guidance_layout.addStretch(1)
        self.sections.addTab(guidance, "Indicaciones")

        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.rejected.connect(self.accept)
        layout.addWidget(close)
        self.refresh_suggestions()

    def import_plain_text(self):
        source_dialog = PlainTextSourceDialog(self)
        if source_dialog.exec() != QDialog.DialogCode.Accepted:
            return
        text = source_dialog.text_edit.toPlainText()
        try:
            if len(text.encode("utf-8")) > 5 * 1024 * 1024:
                raise ValueError("El archivo supera el límite de 5 MB.")
            blocks = plain_text_blocks(text)
            if not blocks:
                raise ValueError("No se encontraron bloques con contenido en el texto pegado o cargado.")
            index = build_destination_index(self.window.store)
            recommendations = [
                recommendation
                for title, content in blocks
                if (recommendation := recommend_plain_text_destination(content, title, index))
            ]
            if not recommendations:
                raise ValueError("No hay pestañas activas de notas o comandos donde añadir el texto.")
        except (ValueError, UnicodeError) as exc:
            QMessageBox.warning(self, "No se pudo analizar el archivo", str(exc))
            return

        dialog = PlainTextImportDialog(
            self.window, source_dialog.source_name, recommendations, self
        )
        dialog.exec()
        self.refresh_suggestions()

    def refresh_suggestions(self):
        self.suggestion_list.clear()
        suggestions = build_organization_suggestions(self.window.store)
        for suggestion in suggestions:
            item = QListWidgetItem()
            card = SuggestionCard(suggestion, self.apply_suggestion, self.dismiss_suggestion)
            item.setSizeHint(card.sizeHint())
            self.suggestion_list.addItem(item)
            self.suggestion_list.setItemWidget(item, card)
        if not suggestions:
            item = QListWidgetItem("No se han encontrado sugerencias ahora.")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.suggestion_list.addItem(item)

    def _remove_card(self, card: SuggestionCard):
        for row in range(self.suggestion_list.count()):
            item = self.suggestion_list.item(row)
            if self.suggestion_list.itemWidget(item) is card:
                self.suggestion_list.takeItem(row)
                card.deleteLater()
                return

    def apply_suggestion(self, card: SuggestionCard):
        suggestion = card.suggestion
        if suggestion.get("action") == "create_tab":
            answer = QMessageBox.question(
                self, "Crear pestaña y mover notas",
                f"Se creará la pestaña «{suggestion['tab_name']}» y se moverán "
                f"{suggestion['entry_count']} notas desde «{suggestion['source_tab_name']}». "
                "El resto de las notas no cambiará de ubicación.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
            try:
                new_tab_id = self.window.store.create_tab_from_entries(
                    suggestion["tab_name"], suggestion["source_tab_id"], suggestion["entry_ids"]
                )
                self.window.populate_tabs(new_tab_id)
                self.window.statusBar().showMessage("Pestaña creada y notas organizadas", 3000)
                self._remove_card(card)
            except (OSError, ValueError, sqlite3.Error) as exc:
                QMessageBox.critical(self, "No se pudo crear la pestaña", str(exc))
            return

        entry = suggestion["entry"]
        title = suggestion["value"] if suggestion["field"] == "title" else entry["title"]
        category = suggestion["value"] if suggestion["field"] == "category" else entry["category"]
        try:
            self.window.store.save_entry(
                suggestion["tab_id"], entry["kind"], title, category, entry["content"],
                entry.get("runner", "PowerShell"), entry["id"],
            )
            page = self.window.pages.get(suggestion["tab_id"])
            if page:
                page.render()
            self.window.statusBar().showMessage("Sugerencia aplicada", 2200)
            self._remove_card(card)
        except (OSError, ValueError, sqlite3.Error) as exc:
            QMessageBox.critical(self, "No se pudo aplicar", str(exc))

    def dismiss_suggestion(self, card: SuggestionCard):
        self._remove_card(card)

class PlainTextImportCard(QWidget):
    def __init__(self, recommendation: dict[str, Any], tabs: list[dict[str, Any]],
                 on_add, on_dismiss, parent=None):
        super().__init__(parent)
        self.recommendation = recommendation
        self.tab_selector = QComboBox()
        self.tabs_by_id = {tab["id"]: tab for tab in tabs}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        self.heading = QLabel(
            f"Recomendación: {recommendation['tab_name']} · {recommendation['category']}"
        )
        self.heading.setStyleSheet("font-weight: 600;")
        self.heading.setWordWrap(True)
        layout.addWidget(self.heading)

        fields = QFormLayout()
        self.title_edit = QLineEdit(recommendation["title"])
        self.category_edit = QLineEdit(recommendation["category"])
        fields.addRow("Título:", self.title_edit)
        fields.addRow("Categoría:", self.category_edit)
        for tab in tabs:
            self.tab_selector.addItem(tab["name"], tab["id"])
        index = self.tab_selector.findData(recommendation["tab_id"])
        if index >= 0:
            self.tab_selector.setCurrentIndex(index)
        fields.addRow("Pestaña:", self.tab_selector)
        layout.addLayout(fields)

        preview = QTextEdit()
        preview.setReadOnly(True)
        preview.setAcceptRichText(False)
        preview.setPlainText(recommendation["content"])
        preview.setFixedHeight(110)
        layout.addWidget(preview)

        buttons = QHBoxLayout()
        self.add_button = QPushButton()
        self.add_button.clicked.connect(lambda: on_add(self))
        self.tab_selector.currentIndexChanged.connect(self.update_add_label)
        self.update_add_label()
        dismiss = QPushButton("Omitir")
        dismiss.clicked.connect(lambda: on_dismiss(self))
        buttons.addWidget(self.add_button)
        buttons.addWidget(dismiss)
        buttons.addStretch(1)
        layout.addLayout(buttons)

    def update_add_label(self, _index: int = -1):
        tab = self.tabs_by_id.get(self.tab_selector.currentData())
        kind_label = "comando" if tab and tab["kind"] == "command" else "nota"
        self.add_button.setText(f"Añadir {kind_label} a esta pestaña")

class PlainTextSourceDialog(QDialog):
    """Accept pasted text or load a local plain-text file for analysis."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Pegar o importar texto plano")
        self.resize(760, 560)
        self.source_name = "Texto pegado"
        layout = QVBoxLayout(self)
        instructions = QLabel(
            "Pega las notas o comandos en el recuadro. Separa cada elemento con una línea en blanco, "
            "o usa encabezados Markdown. También puedes cargar un archivo .txt. El análisis es local."
        )
        instructions.setWordWrap(True)
        layout.addWidget(instructions)
        self.text_edit = QPlainTextEdit()
        self.text_edit.setPlaceholderText("Pega aquí las notas o comandos que quieras organizar…")
        layout.addWidget(self.text_edit, 1)
        controls = QHBoxLayout()
        self.source_label = QLabel("Origen: texto pegado")
        controls.addWidget(self.source_label, 1)
        load_button = QPushButton("Cargar archivo .txt…")
        load_button.clicked.connect(self.load_file)
        controls.addWidget(load_button)
        layout.addLayout(controls)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Analizar texto")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    def load_file(self):
        filename, _ = QFileDialog.getOpenFileName(
            self, "Cargar notas de texto", "", "Archivos de texto (*.txt);;Todos los archivos (*)"
        )
        if not filename:
            return
        source = Path(filename)
        try:
            raw_text = source.read_bytes()
            if len(raw_text) > 5 * 1024 * 1024:
                raise ValueError("El archivo supera el límite de 5 MB.")
            try:
                text = raw_text.decode("utf-8-sig")
            except UnicodeDecodeError:
                text = raw_text.decode("cp1252")
        except (OSError, UnicodeError, ValueError) as exc:
            QMessageBox.warning(self, "No se pudo cargar el archivo", str(exc))
            return
        self.text_edit.setPlainText(text)
        self.source_name = source.name
        self.source_label.setText(f"Archivo: {source.name}")

    def accept(self):
        text = self.text_edit.toPlainText()
        if not text.strip():
            QMessageBox.information(self, "No hay texto", "Pega o carga texto antes de analizarlo.")
            return
        if len(text.encode("utf-8")) > 5 * 1024 * 1024:
            QMessageBox.warning(self, "Texto demasiado grande", "El límite es de 5 MB.")
            return
        super().accept()

class PlainTextImportDialog(QDialog):
    """Review locally generated recommendations before importing text blocks."""

    def __init__(self, window: "CommandCenterWindow", source_name: str,
                 recommendations: list[dict[str, Any]], parent=None):
        super().__init__(parent or window)
        self.window = window
        self.setWindowTitle(f"Revisar importación · {source_name}")
        self.resize(820, 680)
        self.tabs = recommendations[0]["tabs"] if recommendations else []
        self.tab_by_id = {tab["id"]: tab for tab in self.tabs}

        layout = QVBoxLayout(self)
        intro = QLabel(
            f"Se encontraron {len(recommendations)} bloques. Revisa o edita cada recomendación y "
            "añade u omite los elementos uno a uno. El contenido original se conserva."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)
        self.items = QListWidget()
        self.items.setSpacing(6)
        layout.addWidget(self.items, 1)
        for recommendation in recommendations:
            item = QListWidgetItem()
            card = PlainTextImportCard(
                recommendation, self.tabs, self.add_recommendation, self.dismiss_recommendation
            )
            item.setSizeHint(card.sizeHint())
            self.items.addItem(item)
            self.items.setItemWidget(item, card)
        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.rejected.connect(self.accept)
        layout.addWidget(close)

    def _remove_card(self, card: PlainTextImportCard):
        for row in range(self.items.count()):
            item = self.items.item(row)
            if self.items.itemWidget(item) is card:
                self.items.takeItem(row)
                card.deleteLater()
                return

    def add_recommendation(self, card: PlainTextImportCard):
        title = card.title_edit.text().strip()
        category = card.category_edit.text().strip() or "General"
        tab_id = card.tab_selector.currentData()
        tab = self.tab_by_id.get(tab_id)
        if not title or tab is None:
            QMessageBox.warning(self, "Datos incompletos", "Escribe un título y selecciona una pestaña.")
            return
        try:
            self.window.store.save_entry(
                tab_id, tab["kind"], title, category, card.recommendation["content"],
                card.recommendation["runner"],
            )
            self.window.populate_tabs(tab_id)
            self.window.statusBar().showMessage(f"Elemento añadido a «{tab['name']}»", 2500)
            self._remove_card(card)
        except (OSError, ValueError, sqlite3.Error) as exc:
            QMessageBox.critical(self, "No se pudo añadir el elemento", str(exc))

    def dismiss_recommendation(self, card: PlainTextImportCard):
        self._remove_card(card)

class DuplicateReviewDialog(QDialog):
    def __init__(self, store: DataStore, tab: dict[str, Any], parent=None):
        super().__init__(parent)
        self.store = store
        self.tab = tab
        self.setWindowTitle("Revisar duplicados exactos")
        self.resize(820, 480)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            "Solo se muestran elementos con el mismo título, categoría, contenido y motor. "
            "Se conservará el más antiguo; los repetidos marcados se archivarán, nunca se borrarán."
        ))
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Archivar", "Título", "Categoría", "Motor"])
        self.table.setColumnWidth(0, 76)
        self.table.setColumnWidth(1, 270)
        self.table.setColumnWidth(2, 180)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table, 1)
        buttons = QHBoxLayout()
        self.archive_button = QPushButton("Archivar repetidos marcados")
        self.archive_button.clicked.connect(self.archive_selected)
        close = QPushButton("Cerrar")
        close.clicked.connect(self.accept)
        buttons.addWidget(self.archive_button)
        buttons.addStretch(1)
        buttons.addWidget(close)
        layout.addLayout(buttons)
        self.refresh()

    @staticmethod
    def _signature(entry: dict[str, Any]) -> tuple[str, str, str, str]:
        content = entry["content"].replace("\r\n", "\n").replace("\r", "\n").strip()
        return (
            normalize_text(entry["title"]).strip(),
            normalize_text(entry["category"]).strip(),
            content,
            entry.get("runner", "").casefold(),
        )

    def refresh(self):
        groups: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
        for entry in self.store.list_entries(self.tab["id"]):
            groups.setdefault(self._signature(entry), []).append(entry)
        duplicate_rows: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for entries in groups.values():
            if len(entries) < 2:
                continue
            entries.sort(key=lambda item: (item["created_at"], item["position"]))
            keeper = entries[0]
            duplicate_rows.extend((keeper, duplicate) for duplicate in entries[1:])

        self.table.setRowCount(len(duplicate_rows))
        for row, (keeper, duplicate) in enumerate(duplicate_rows):
            check = QTableWidgetItem()
            check.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
            check.setCheckState(Qt.CheckState.Checked)
            check.setData(Qt.ItemDataRole.UserRole, duplicate["id"])
            check.setToolTip(f"Se conservará: {keeper['title']} (el más antiguo).")
            self.table.setItem(row, 0, check)
            for column, key in ((1, "title"), (2, "category"), (3, "runner")):
                item = QTableWidgetItem(duplicate[key] or "")
                item.setToolTip(
                    f"Duplicado de «{keeper['title']}».\nContenido idéntico:\n{duplicate['content']}"
                )
                self.table.setItem(row, column, item)
        self.archive_button.setEnabled(bool(duplicate_rows))
        if not duplicate_rows:
            self.table.setRowCount(1)
            self.table.setItem(0, 0, QTableWidgetItem("No se encontraron duplicados exactos."))

    def archive_selected(self):
        entry_ids = [
            self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
            for row in range(self.table.rowCount())
            if self.table.item(row, 0)
            and self.table.item(row, 0).checkState() == Qt.CheckState.Checked
            and self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        ]
        if not entry_ids:
            QMessageBox.information(self, "Sin selección", "Marca los duplicados que quieras archivar.")
            return
        answer = QMessageBox.question(
            self, "Archivar duplicados",
            f"Se archivarán {len(entry_ids)} elementos repetidos. Se conservará el más antiguo de cada grupo.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self.store.set_entries_archived(self.tab["id"], entry_ids, True)
            self.refresh()
            QMessageBox.information(self, "Duplicados archivados", "Los elementos elegidos se pueden restaurar desde Organizar.")
        except (ValueError, sqlite3.Error) as exc:
            QMessageBox.warning(self, "No se pudieron archivar", str(exc))

class EntryOrganizerDialog(QDialog):
    """Bulk edit, categorize, archive, restore, and review duplicates."""

    def __init__(self, store: DataStore, tab: dict[str, Any], parent=None):
        super().__init__(parent)
        self.store = store
        self.tab = tab
        self.setWindowTitle(f"Organizar elementos · {tab['name']}")
        self.resize(940, 610)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            "Marca las filas para aplicar acciones en lote. Puedes editar títulos y categorías directamente en la tabla; "
            "pulsa Guardar cambios para conservar esas ediciones."
        ))
        view_row = QHBoxLayout()
        view_row.addWidget(QLabel("Mostrar:"))
        self.view = QComboBox()
        self.view.addItem("Activos", False)
        self.view.addItem("Archivados", True)
        self.view.currentIndexChanged.connect(self.refresh)
        view_row.addWidget(self.view)
        view_row.addStretch(1)
        layout.addLayout(view_row)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Seleccionar", "Título", "Categoría", "Contenido (vista previa)"])
        self.table.setColumnWidth(0, 84)
        self.table.setColumnWidth(1, 260)
        self.table.setColumnWidth(2, 190)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
            | QAbstractItemView.EditTrigger.SelectedClicked
        )
        layout.addWidget(self.table, 1)
        actions = QHBoxLayout()
        select_all = QPushButton("Seleccionar todo")
        select_all.clicked.connect(lambda: self.set_all_checked(True))
        select_none = QPushButton("Quitar selección")
        select_none.clicked.connect(lambda: self.set_all_checked(False))
        save = QPushButton("Guardar cambios")
        save.clicked.connect(self.save_edits)
        categorize = QPushButton("Cambiar categoría…")
        categorize.clicked.connect(self.categorize_selected)
        self.archive_button = QPushButton()
        self.archive_button.clicked.connect(self.toggle_archive_selected)
        duplicates = QPushButton("Detectar duplicados…")
        duplicates.clicked.connect(self.review_duplicates)
        close = QPushButton("Cerrar")
        close.clicked.connect(self.accept)
        for button in (select_all, select_none, save, categorize, self.archive_button, duplicates):
            actions.addWidget(button)
        actions.addStretch(1)
        actions.addWidget(close)
        layout.addLayout(actions)
        self.refresh()

    def refresh(self, *_args):
        archived_view = bool(self.view.currentData())
        self.archive_button.setText("Restaurar selección" if archived_view else "Archivar selección")
        entries = [
            entry for entry in self.store.list_entries(self.tab["id"], include_archived=True)
            if bool(entry["archived"]) == archived_view
        ]
        self.table.setRowCount(len(entries))
        for row, entry in enumerate(entries):
            check = QTableWidgetItem()
            check.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
            check.setCheckState(Qt.CheckState.Unchecked)
            check.setData(Qt.ItemDataRole.UserRole, entry["id"])
            self.table.setItem(row, 0, check)
            for column, key in ((1, "title"), (2, "category")):
                item = QTableWidgetItem(entry[key])
                item.setData(Qt.ItemDataRole.UserRole, entry["id"])
                self.table.setItem(row, column, item)
            content = QTableWidgetItem(entry["content"].replace("\n", " ↵ ")[:180])
            content.setFlags(content.flags() & ~Qt.ItemFlag.ItemIsEditable)
            content.setToolTip(entry["content"])
            self.table.setItem(row, 3, content)

    def selected_ids(self) -> list[str]:
        return [
            self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
            for row in range(self.table.rowCount())
            if self.table.item(row, 0)
            and self.table.item(row, 0).checkState() == Qt.CheckState.Checked
        ]

    def set_all_checked(self, checked: bool):
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        for row in range(self.table.rowCount()):
            if self.table.item(row, 0):
                self.table.item(row, 0).setCheckState(state)

    def save_edits(self, silent_if_clean: bool = False) -> bool:
        self.table.setCurrentCell(-1, -1)
        updates: dict[str, dict[str, str]] = {}
        originals = {
            entry["id"]: entry
            for entry in self.store.list_entries(self.tab["id"], include_archived=True)
        }
        for row in range(self.table.rowCount()):
            entry_id = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
            title = self.table.item(row, 1).text().strip()
            category = self.table.item(row, 2).text().strip()
            original = originals.get(entry_id)
            if original and (title != original["title"] or category != original["category"]):
                updates[entry_id] = {"title": title, "category": category}
        if not updates:
            if not silent_if_clean:
                QMessageBox.information(self, "Sin cambios", "No hay cambios de título o categoría pendientes.")
            return True
        try:
            self.store.bulk_update_entries(self.tab["id"], updates)
            self.refresh()
            QMessageBox.information(self, "Cambios guardados", f"Se actualizaron {len(updates)} elementos.")
            return True
        except (ValueError, sqlite3.Error) as exc:
            QMessageBox.warning(self, "No se pudieron guardar los cambios", str(exc))
            return False

    def categorize_selected(self):
        entry_ids = self.selected_ids()
        if not entry_ids:
            QMessageBox.information(self, "Sin selección", "Marca primero los elementos que quieras categorizar.")
            return
        if not self.save_edits(silent_if_clean=True):
            return
        category, accepted = QInputDialog.getText(self, "Cambiar categoría", "Nueva categoría:")
        if not accepted:
            return
        category = category.strip()
        if not category:
            QMessageBox.warning(self, "Categoría vacía", "La categoría no puede quedar vacía.")
            return
        try:
            self.store.bulk_update_entries(
                self.tab["id"], {entry_id: {"category": category} for entry_id in entry_ids}
            )
            self.refresh()
            QMessageBox.information(self, "Categorías actualizadas", f"Se actualizaron {len(entry_ids)} elementos.")
        except (ValueError, sqlite3.Error) as exc:
            QMessageBox.warning(self, "No se pudo cambiar la categoría", str(exc))

    def toggle_archive_selected(self):
        entry_ids = self.selected_ids()
        if not entry_ids:
            QMessageBox.information(self, "Sin selección", "Marca primero los elementos que quieras cambiar.")
            return
        if not self.save_edits(silent_if_clean=True):
            return
        archived_view = bool(self.view.currentData())
        if not archived_view:
            answer = QMessageBox.question(
                self, "Archivar elementos",
                f"Se archivarán {len(entry_ids)} elementos. Podrás restaurarlos desde esta ventana.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        try:
            self.store.set_entries_archived(self.tab["id"], entry_ids, not archived_view)
            self.refresh()
        except (ValueError, sqlite3.Error) as exc:
            QMessageBox.warning(self, "No se pudo completar la acción", str(exc))

    def review_duplicates(self):
        dialog = DuplicateReviewDialog(self.store, self.tab, self)
        dialog.exec()
        self.refresh()

class ArchivedTabsDialog(QDialog):
    def __init__(self, store: DataStore, parent=None):
        super().__init__(parent)
        self.store = store
        self.setWindowTitle("Pestañas archivadas")
        self.resize(480, 360)
        layout = QVBoxLayout(self)
        self.list = QListWidget()
        layout.addWidget(self.list, 1)
        buttons = QHBoxLayout()
        restore = QPushButton("Restaurar")
        restore.clicked.connect(self.restore_selected)
        delete = QPushButton("Eliminar permanentemente")
        delete.clicked.connect(self.delete_selected)
        close = QPushButton("Cerrar")
        close.clicked.connect(self.accept)
        buttons.addWidget(restore)
        buttons.addWidget(delete)
        buttons.addStretch(1)
        buttons.addWidget(close)
        layout.addLayout(buttons)
        self.refresh()

    def refresh(self):
        self.list.clear()
        for tab in self.store.list_tabs(include_archived=True):
            if tab["archived"]:
                item = QListWidgetItem(f"{tab['name']}  ·  {len(self.store.list_entries(tab['id']))} elementos")
                item.setData(Qt.ItemDataRole.UserRole, tab["id"])
                self.list.addItem(item)

    def selected_id(self) -> str | None:
        item = self.list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def restore_selected(self):
        tab_id = self.selected_id()
        if tab_id:
            try:
                self.store.restore_tab(tab_id)
            except (ValueError, sqlite3.Error) as exc:
                QMessageBox.critical(self, "No se pudo restaurar la pestaña", str(exc))
            self.refresh()

    def delete_selected(self):
        tab_id = self.selected_id()
        if not tab_id:
            return
        answer = QMessageBox.warning(self, "Borrado permanente",
                                     "Se eliminarán la pestaña y todos sus elementos. Esta acción no se puede deshacer.",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                                     QMessageBox.StandardButton.Cancel)
        if answer == QMessageBox.StandardButton.Yes:
            try:
                self.store.permanently_delete_tab(tab_id)
            except (ValueError, sqlite3.Error) as exc:
                QMessageBox.critical(self, "No se pudo eliminar la pestaña", str(exc))
            self.refresh()

def executable_directory() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(sys.argv[0]).resolve().parent

class StorageLocationDialog(QDialog):
    def __init__(self, parent=None, initial_directory: Path | None = None):
        super().__init__(parent)
        self.setWindowTitle("Ubicación de la base de datos")
        self.setMinimumWidth(560)
        layout = QVBoxLayout(self)
        description = QLabel(
            "Elige dónde guardar la base de datos de Command Center. "
            "Puedes cambiarla más adelante desde Opciones."
        )
        description.setWordWrap(True)
        layout.addWidget(description)

        self.user_radio = QRadioButton("En la carpeta del usuario")
        self.user_radio.setToolTip("Ubicación local de datos de Windows")
        self.executable_radio = QRadioButton("Junto al ejecutable")
        self.custom_radio = QRadioButton("En una carpeta a elección")
        layout.addWidget(self.user_radio)
        layout.addWidget(self.executable_radio)
        layout.addWidget(self.custom_radio)

        custom_row = QHBoxLayout()
        self.custom_directory = QLineEdit(str(initial_directory or ""))
        self.custom_directory.setPlaceholderText("Selecciona una carpeta")
        self.browse_button = QPushButton("Examinar…")
        self.browse_button.clicked.connect(self.browse)
        custom_row.addWidget(self.custom_directory, 1)
        custom_row.addWidget(self.browse_button)
        layout.addLayout(custom_row)

        self.path_preview = QLabel()
        self.path_preview.setWordWrap(True)
        layout.addWidget(self.path_preview)
        self.user_radio.toggled.connect(self.update_preview)
        self.executable_radio.toggled.connect(self.update_preview)
        self.custom_radio.toggled.connect(self.update_preview)
        self.custom_directory.textChanged.connect(self.update_preview)
        if initial_directory:
            self.custom_radio.setChecked(True)
        else:
            self.user_radio.setChecked(True)
        self.update_preview()

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def selected_directory(self) -> Path:
        if self.user_radio.isChecked():
            return application_data_dir()
        if self.executable_radio.isChecked():
            return executable_directory()
        selected = self.custom_directory.text().strip()
        if not selected:
            raise ValueError("Selecciona una carpeta para guardar la base de datos.")
        return Path(selected).expanduser()

    def database_path(self) -> Path:
        return self.selected_directory() / DATABASE_FILENAME

    def update_preview(self, *_args):
        try:
            path = self.database_path()
            self.path_preview.setText(f"Ruta de la base de datos:\n{path}")
        except (OSError, ValueError):
            self.path_preview.setText("Selecciona una carpeta para ver la ruta completa.")

    def browse(self):
        selected = QFileDialog.getExistingDirectory(
            self, "Elegir carpeta para la base de datos", self.custom_directory.text().strip()
        )
        if selected:
            self.custom_directory.setText(selected)
            self.custom_radio.setChecked(True)

class InterfacePickerDialog(QDialog):
    """Choose an interface with two embedded visual examples per option."""

    def __init__(self, initial: str = "classic", first_run: bool = False, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Elige la interfaz de Command Center")
        self.resize(1320, 900)
        self.setMinimumSize(1000, 700)
        self.setStyleSheet(
            "QDialog, QWidget { background: #15181c; color: #e7edf2; }"
            "QLabel, QRadioButton, QGroupBox { color: #e7edf2; }"
            "QGroupBox { background: #20252b; border: 1px solid #39434c; border-radius: 8px; }"
            "QPushButton { color: #e7edf2; background: #282e35; border: 1px solid #414b55;"
            " border-radius: 6px; padding: 7px 14px; }"
            "QPushButton:hover { background: #303941; border-color: #20a889; }"
            "QPushButton:pressed { background: #183b36; }"
            "QRadioButton::indicator { width: 16px; height: 16px; }"
            "QRadioButton::indicator:unchecked { border: 2px solid #74818b; border-radius: 9px; background: #15181c; }"
            "QRadioButton::indicator:checked { border: 2px solid #20a889; border-radius: 9px; background: #20a889; }"
            "QScrollArea { background: #15181c; border: 0; }"
            "QScrollBar:vertical { background: #20252b; width: 12px; margin: 0; }"
            "QScrollBar::handle:vertical { background: #56616b; min-height: 28px; border-radius: 5px; }"
            "QScrollBar::handle:vertical:hover { background: #20a889; }"
        )
        layout = QVBoxLayout(self)
        heading = QLabel("¿Cómo quieres organizar Command Center?")
        heading.setStyleSheet("font-size: 17pt; font-weight: 600;")
        layout.addWidget(heading)
        description = QLabel(
            "Todas las interfaces conservan las mismas funciones y datos."
        )
        description.setWordWrap(True)
        layout.addWidget(description)
        interface_notice = QLabel(
            "Nota: podrás cambiar la interfaz en cualquier momento desde Opciones > General."
        )
        interface_notice.setObjectName("interfaceChangeNotice")
        interface_notice.setWordWrap(True)
        interface_notice.setStyleSheet(
            "QLabel#interfaceChangeNotice { background: #183b36; color: #8ce0cf; "
            "border: 1px solid #287d6d; border-radius: 6px; padding: 9px 12px; font-weight: 600; }"
        )
        layout.addWidget(interface_notice)

        previews = {
            "classic": (
                "<div class='toolbar'><b>+ Nuevo comando</b><span>Renombrar pestaña</span>"
                "<span>Archivar pestaña</span><span>Sugerencias</span><span>Opciones</span></div>"
                "<div class='tabs'><b>Comandos</b>　 IA　 Juegos　 Notas Hardware　 URLs útiles　 +</div>"
                "<div class='sample'><b>Ejemplo 1 · pestañas arriba</b><br>Busca y ordena sin cambiar el espacio de trabajo.</div>"
                "<div class='sample'><b>Ejemplo 2 · tarjetas de comandos</b><br>Información del sistema　 ·　 Copiar　 Editar　 Eliminar</div>"
            ),
            "compact": (
                "<div class='toolbar'><b>Comandos　 IA　 Juegos　 Notas　 URLs</b><span>＋</span></div>"
                "<div class='sample'><b>Ejemplo 1 · filtros en una sola fila</b><br>Buscar…　 Todas las categorías　 Manual</div>"
                "<div class='row'><b>Información del sistema</b><code>systeminfo</code><span>Sistema</span><span>Ejecutar　 Copiar　 Editar</span></div>"
                "<div class='row'><b>Listar procesos</b><code>tasklist</code><span>Sistema</span><span>Ejecutar　 Copiar　 Editar</span></div>"
            ),
            "table": (
                "<div class='toolbar'><b>Título　 Categoría　 Tipo　 Motor　 Contenido　 Acciones</b></div>"
                "<div class='row'><b>Ver IP</b><code>Red</code><span>CMD　 Ejecutar　 Copiar</span></div>"
                "<div class='row'><b>Listar procesos</b><code>Sistema</code><span>CMD　 Ejecutar　 Copiar</span></div>"
            ),
            "terminal": (
                "<div class='toolbar'><code>COMMAND CENTER / COMANDOS</code><br><code>$ Buscar…　 Categoría: Todas</code></div>"
                "<div class='row'><code>&gt; ipconfig /all</code><span>Ejecutar　 Copiar　 Editar</span></div>"
                "<div class='row'><code>&gt; tasklist</code><span>Ejecutar　 Copiar　 Editar</span></div>"
            ),
        }
        descriptions = {
            "classic": "La distribución actual, con pestañas y acciones en la parte superior.",
            "compact": "Lista densa para revisar más comandos a la vez y actuar desde cada fila.",
            "table": "Vista tabular con los campos y accesos rápidos alineados por columna.",
            "terminal": "Catálogo inspirado en una consola, con comandos monoespaciados y tema oscuro.",
        }
        self._buttons: dict[str, QRadioButton] = {}
        group = QButtonGroup(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        preview_container = QWidget()
        grid = QGridLayout(preview_container)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)
        for index, key in enumerate(INTERFACE_LABELS):
            panel = QGroupBox()
            panel_layout = QVBoxLayout(panel)
            choice = QRadioButton(INTERFACE_LABELS[key])
            choice.setStyleSheet("font-size: 12pt; font-weight: 600;")
            group.addButton(choice)
            self._buttons[key] = choice
            panel_layout.addWidget(choice)
            detail = QLabel(descriptions[key])
            detail.setWordWrap(True)
            panel_layout.addWidget(detail)
            example = QTextBrowser()
            example.setReadOnly(True)
            example.setOpenExternalLinks(False)
            example.setMinimumHeight(145)
            example.setHtml(
                "<html><head><style>body{font-family:'Segoe UI',sans-serif;font-size:10pt;"
                "color:#e7edf2;background:#171b20;margin:8px}.toolbar{background:#272e35;border:1px solid #414b55;"
                "border-radius:6px;padding:8px;margin-bottom:7px}.toolbar span{margin-left:12px;color:#b8c3cc}"
                ".tabs{padding:6px;color:#8ce0cf;border-bottom:2px solid #20a889;margin-bottom:7px}"
                ".sample,.row{background:#222930;border:1px solid #39434c;border-radius:6px;padding:8px;margin:5px 0}"
                ".row code{margin-left:14px;color:#a9c2d2}.row span{float:right;color:#8ce0cf;margin-left:12px}"
                "</style></head><body>" + previews[key] + "</body></html>"
            )
            panel_layout.addWidget(example, 1)
            grid.addWidget(panel, index // 2, index % 2)
        scroll.setWidget(preview_container)
        layout.addWidget(scroll, 1)
        self._buttons.get(initial, self._buttons["classic"]).setChecked(True)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | (QDialogButtonBox.StandardButton.Cancel if not first_run else QDialogButtonBox.StandardButton.NoButton)
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        if first_run:
            buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Continuar")

    @property
    def selected_interface(self) -> str:
        return next((key for key, button in self._buttons.items() if button.isChecked()), "classic")

class OptionsDialog(QDialog):
    def __init__(self, window: "CommandCenterWindow"):
        super().__init__(window)
        self.window = window
        self.setWindowTitle("Opciones de Command Center")
        self.resize(720, 560)
        self.setMinimumSize(620, 460)
        layout = QVBoxLayout(self)
        self.sections = QTabWidget()
        layout.addWidget(self.sections, 1)

        general = QWidget()
        general_layout = QVBoxLayout(general)
        appearance = QGroupBox("Apariencia")
        appearance_layout = QFormLayout(appearance)
        self.theme = QComboBox()
        self.theme.addItems(["Sistema", "Claro", "Oscuro"])
        self.theme.setCurrentText(window.store.get_setting("theme", "Sistema"))
        self.theme.currentTextChanged.connect(window.apply_theme)
        appearance_layout.addRow("Tema:", self.theme)
        self.interface = QComboBox()
        for key, label in INTERFACE_LABELS.items():
            self.interface.addItem(label, key)
        current_interface = window.store.get_setting("interface", "classic")
        interface_index = self.interface.findData(current_interface)
        self.interface.setCurrentIndex(max(0, interface_index))
        self.interface.currentIndexChanged.connect(
            lambda _index: window.apply_interface(self.interface.currentData())
        )
        appearance_layout.addRow("Interfaz:", self.interface)
        interface_help = QLabel(
            "Cambia la distribución visual sin modificar las pestañas ni tus datos. "
            "En el primer inicio puedes previsualizar cada opción."
        )
        interface_help.setWordWrap(True)
        appearance_layout.addRow(interface_help)
        general_layout.addWidget(appearance)

        storage = QGroupBox("Almacenamiento")
        storage_layout = QVBoxLayout(storage)
        self.storage_path_label = QLabel(str(window.store.path))
        self.storage_path_label.setWordWrap(True)
        storage_layout.addWidget(self.storage_path_label)
        move_storage_button = QPushButton("Mover base de datos…")
        move_storage_button.clicked.connect(self.move_storage)
        storage_layout.addWidget(move_storage_button, 0, Qt.AlignmentFlag.AlignLeft)
        general_layout.addWidget(storage)

        archived = QGroupBox("Organización")
        archived_layout = QVBoxLayout(archived)
        archived_help = QLabel("Consulta, restaura o elimina pestañas archivadas.")
        archived_help.setWordWrap(True)
        archived_layout.addWidget(archived_help)
        archived_button = QPushButton("Gestionar pestañas archivadas…")
        archived_button.clicked.connect(window.show_archived)
        archived_layout.addWidget(archived_button, 0, Qt.AlignmentFlag.AlignLeft)
        general_layout.addWidget(archived)
        general_layout.addStretch(1)
        self.sections.addTab(general, "General")

        data = QWidget()
        data_layout = QVBoxLayout(data)
        data_help = QLabel(
            "La importación combina las colecciones del archivo con las actuales. "
            "No sustituye ni elimina tus datos; las entradas idénticas se omiten. "
            "Se crea una copia local antes de añadir información."
        )
        data_help.setWordWrap(True)
        data_layout.addWidget(data_help)
        backup_button = QPushButton("Crear copia de seguridad ahora")
        backup_button.clicked.connect(window.backup_database)
        data_layout.addWidget(backup_button, 0, Qt.AlignmentFlag.AlignLeft)
        import_button = QPushButton("Importar JSON y combinar colecciones…")
        import_button.clicked.connect(window.import_data)
        data_layout.addWidget(import_button, 0, Qt.AlignmentFlag.AlignLeft)
        export_button = QPushButton("Exportar datos JSON…")
        export_button.clicked.connect(window.export_data)
        data_layout.addWidget(export_button, 0, Qt.AlignmentFlag.AlignLeft)
        data_layout.addStretch(1)
        self.sections.addTab(data, "Datos")

        about = QTextBrowser()
        about.setOpenExternalLinks(True)
        about.setHtml(
            f"<h2>Command Center {__version__}</h2>"
            "<p>Aplicación de escritorio gratuita y local para organizar notas, enlaces "
            "y comandos útiles. No requiere una cuenta ni un servicio de IA.</p>"
            "<h3>Información y uso</h3>"
            "<p>Los comandos y scripts se ejecutan con los permisos de tu usuario y "
            "pueden modificar archivos, programas o ajustes del sistema. Revisa el "
            "contenido antes de ejecutarlo. La aplicación no aísla ni valida esos comandos.</p>"
            "<p>Los datos se guardan localmente. No se envían a un servicio remoto desde "
            "la aplicación. Las notas pueden contener información sensible; la base "
            "local no está cifrada.</p>"
            "<h3>Inteligencia artificial</h3>"
            "<p>La pestaña IA es únicamente una colección local de notas. No genera "
            "respuestas, no se conecta a modelos y no envía tus notas a proveedores de IA.</p>"
            "<h3>Licencias de terceros</h3>"
            f"<p>El código propio de Command Center se distribuye bajo MIT. Consulta el "
            f"<a href='{resource_path('LICENSE').as_uri()}'>texto de la licencia MIT</a>.</p>"
            "<p>Esta distribución usa PySide6/Qt for Python Community Edition bajo la "
            "vía LGPLv3. Se incluyen los textos LGPLv3 y GPLv3 y un resumen de "
            "componentes de terceros. Consulta también la "
            f"<a href='{resource_path('licenses/LGPL-3.0-only.txt').as_uri()}'>LGPLv3</a>, "
            f"<a href='{resource_path('licenses/GPL-3.0-only.txt').as_uri()}'>GPLv3</a> y "
            f"<a href='{resource_path('licenses/THIRD-PARTY-NOTICES.md').as_uri()}'>avisos de terceros</a>. "
            "El código fuente y las instrucciones de compilación están disponibles en "
            "<a href='https://github.com/elkekito/CommandCenter'>GitHub</a>. "
            "Las condiciones de redistribución de Qt, incluida la posibilidad de "
            "modificar o sustituir las bibliotecas LGPL, siguen siendo aplicables. "
            "Consulta la "
            "<a href='https://doc.qt.io/qtforpython-6/'>documentación de Qt for Python</a> "
            "y su <a href='https://doc.qt.io/qtforpython-6/licenses.html'>relación de licencias</a>.</p>"
            "<h3>Garantía</h3>"
            "<p>El software se ofrece sin garantía expresa, en la medida permitida por "
            "la legislación aplicable. El usuario es responsable de revisar los comandos "
            "que ejecuta y de mantener copias de sus datos.</p>"
        )
        self.sections.addTab(about, "Acerca de")

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def move_storage(self):
        if self.window.change_storage_location():
            self.storage_path_label.setText(str(self.window.store.path))
