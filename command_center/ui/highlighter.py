"""Syntax and parameter highlighting for scripts, commands and notes."""

from __future__ import annotations

import re
from PySide6.QtGui import QSyntaxHighlighter, QTextCharFormat, QColor, QFont
from PySide6.QtCore import Qt

PARAMETER_PATTERN = re.compile(r"\{\{\s*([^{}\r\n]{1,64}?)\s*\}\}")


class ScriptSyntaxHighlighter(QSyntaxHighlighter):
    """Lightweight syntax and parameter highlighter for Command Center."""

    def __init__(self, parent=None, runner: str = "PowerShell", dark: bool = True):
        super().__init__(parent)
        self.runner = runner
        self.dark = dark
        self._rules = []
        self._init_rules()

    def set_dark(self, dark: bool):
        self.dark = dark
        self._rules.clear()
        self._init_rules()
        self.rehighlight()

    def set_runner(self, runner: str):
        self.runner = runner
        self._rules.clear()
        self._init_rules()
        self.rehighlight()

    def _init_rules(self):
        # Comments
        comment_format = QTextCharFormat()
        comment_format.setForeground(QColor("#71717a" if self.dark else "#a1a1aa"))
        comment_format.setFontItalic(True)
        self._rules.append((re.compile(r"#[^\n]*"), comment_format))
        if self.runner == "CMD":
            self._rules.append((re.compile(r"::[^\n]*|REM\b[^\n]*", re.IGNORECASE), comment_format))

        # Strings
        string_format = QTextCharFormat()
        string_format.setForeground(QColor("#a7f3d0" if self.dark else "#047857"))
        self._rules.append((re.compile(r'"[^"\n]*"|\'[^\'\n]*\''), string_format))

        # Keywords
        kw_format = QTextCharFormat()
        kw_format.setForeground(QColor("#93c5fd" if self.dark else "#1d4ed8"))
        kw_format.setFontWeight(QFont.Weight.Bold)

        if self.runner == "Python":
            keywords = [
                r"\bdef\b", r"\bclass\b", r"\breturn\b", r"\bimport\b", r"\bfrom\b",
                r"\bif\b", r"\belif\b", r"\belse\b", r"\bfor\b", r"\bwhile\b",
                r"\btry\b", r"\bexcept\b", r"\bfinally\b", r"\bwith\b", r"\bas\b",
                r"\bTrue\b", r"\bFalse\b", r"\bNone\b"
            ]
        elif self.runner == "CMD":
            keywords = [
                r"\becho\b", r"\bset\b", r"\bgoto\b", r"\bcall\b", r"\bpause\b",
                r"\bif\b", r"\belse\b", r"\bfor\b", r"\bdo\b", r"\bexit\b"
            ]
        else: # PowerShell
            keywords = [
                r"\bGet-[A-Za-z0-9_]+", r"\bSet-[A-Za-z0-9_]+", r"\bNew-[A-Za-z0-9_]+",
                r"\bRemove-[A-Za-z0-9_]+", r"\bStart-[A-Za-z0-9_]+", r"\bStop-[A-Za-z0-9_]+",
                r"\bfunction\b", r"\bparam\b", r"\bif\b", r"\belse\b", r"\belseif\b",
                r"\bforeach\b", r"\bwhile\b", r"\breturn\b"
            ]

        for pattern in keywords:
            self._rules.append((re.compile(pattern, re.IGNORECASE if self.runner != "Python" else 0), kw_format))

        # Parameter pill/tag format {{param}}
        self.param_format = QTextCharFormat()
        if self.dark:
            self.param_format.setForeground(QColor("#38bdf8"))
            self.param_format.setBackground(QColor("#082f49"))
        else:
            self.param_format.setForeground(QColor("#0369a1"))
            self.param_format.setBackground(QColor("#e0f2fe"))
        self.param_format.setFontWeight(QFont.Weight.Bold)

    def highlightBlock(self, text: str):
        for pattern, fmt in self._rules:
            for match in pattern.finditer(text):
                self.setFormat(match.start(), match.end() - match.start(), fmt)

        # Highlight parameters with highest priority
        for match in PARAMETER_PATTERN.finditer(text):
            self.setFormat(match.start(), match.end() - match.start(), self.param_format)
