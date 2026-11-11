"""Shared constants for the UI and its dialogs."""

import re

KIND_LABELS = {"command": "Comando", "game": "Juego", "note": "Nota", "url": "Enlace"}
# Button text for adding an entry, with the article agreeing in gender.
NEW_ENTRY_LABELS = {
    "command": "Nuevo comando",
    "game": "Nuevo juego",
    "note": "Nueva nota",
    "url": "Nuevo enlace",
}
KIND_PLURALS = {"command": "comandos", "game": "juegos", "note": "notas", "url": "enlaces"}
RUNNERS = ["PowerShell", "CMD", "Python"]
PARAMETER_PATTERN = re.compile(r"\{\{\s*([^{}\r\n]{1,64}?)\s*\}\}")
RISKY_VALUE_CHARS = frozenset("\"'`$;&|<>")
INTERFACE_LABELS = {
    "classic": "Clásica",
    "compact": "Compacta",
    "table": "Tabla",
    "terminal": "Consola",
}
