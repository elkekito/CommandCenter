"""Shared constants for the UI and its dialogs."""

import re

KIND_LABELS = {"command": "Comando", "game": "Juego", "note": "Nota", "url": "Enlace"}
RUNNERS = ["PowerShell", "CMD", "Python"]
PARAMETER_PATTERN = re.compile(r"\{\{\s*([^{}\r\n]{1,64}?)\s*\}\}")
RISKY_VALUE_CHARS = frozenset("\"'`$;&|<>")
INTERFACE_LABELS = {
    "classic": "Clásica",
    "compact": "Compacta",
    "table": "Tabla",
    "terminal": "Consola",
}
