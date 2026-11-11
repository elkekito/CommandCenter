"""Spanish labels for the standard buttons Qt adds to dialogs and message boxes."""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication, QTranslator

BUTTON_TEXTS = {
    "OK": "Aceptar",
    "&OK": "Aceptar",
    "Cancel": "Cancelar",
    "&Cancel": "Cancelar",
    "Yes": "Sí",
    "&Yes": "&Sí",
    "No": "No",
    "&No": "&No",
    "Save": "Guardar",
    "&Save": "&Guardar",
    "Close": "Cerrar",
    "&Close": "&Cerrar",
    "Apply": "Aplicar",
    "Discard": "Descartar",
    "Open": "Abrir",
    "Retry": "Reintentar",
    "Ignore": "Ignorar",
    "Abort": "Anular",
    "Help": "Ayuda",
    "Reset": "Restablecer",
}
BUTTON_CONTEXTS = {"QPlatformTheme", "QDialogButtonBox", "QMessageBox"}


class DialogButtonTranslator(QTranslator):
    """Translates only the standard button captions; the rest of the UI is written in Spanish."""

    def translate(self, context, source_text, disambiguation=None, n=-1):
        if context in BUTTON_CONTEXTS:
            return BUTTON_TEXTS.get(source_text, "")
        return ""

    def isEmpty(self) -> bool:
        return False


def install_button_translator(app: QCoreApplication) -> DialogButtonTranslator:
    translator = DialogButtonTranslator(app)
    app.installTranslator(translator)
    return translator
