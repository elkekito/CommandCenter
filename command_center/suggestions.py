"""Local, rule-based organization suggestions and plain-text import analysis.

Nothing in this module touches Qt or the network. The functions take a DataStore
(or an index built from one) and return plain values, so they can be tested directly.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .storage import DataStore


@dataclass(frozen=True)
class DestinationIndex:
    """Note and command tabs plus their entries, loaded once for a batch of recommendations."""

    tabs: list[dict[str, Any]]
    entries_by_tab: dict[str, list[dict[str, Any]]]


def build_destination_index(store: "DataStore") -> DestinationIndex:
    tabs = [tab for tab in store.list_tabs() if tab["kind"] in {"note", "command"}]
    return DestinationIndex(tabs, {tab["id"]: store.list_entries(tab["id"]) for tab in tabs})


def suggestion_words(value: str) -> set[str]:
    ignored = {"para", "como", "desde", "cuando", "donde", "esta", "este", "esto",
               "con", "por", "que", "las", "los", "una", "uno", "del", "the", "and",
               "set", "item", "property", "path", "name", "value", "type", "word", "dword"}
    return {word for word in re.findall(r"[a-z0-9]{3,}", normalize_text(value)) if word not in ignored}


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.casefold())
    return "".join(character for character in normalized if not unicodedata.combining(character))


def build_organization_suggestions(store: "DataStore") -> list[dict[str, Any]]:
    """Create local, explainable title/category/tab proposals; never mutate data."""
    suggestions: list[dict[str, Any]] = []
    generic_titles = {"nota", "sin titulo", "comando", "nuevo comando", "truco", "enlace"}
    generic_categories = {"", "general", "sin categoria"}
    existing_tab_names = {
        normalize_text(tab["name"]).strip()
        for tab in store.list_tabs(include_archived=True)
    }

    for tab in store.list_tabs():
        entries = store.list_entries(tab["id"])
        title_groups: dict[str, list[dict[str, Any]]] = {}
        existing_titles = {normalize_text(entry["title"]).strip() for entry in entries}
        for entry in entries:
            title_groups.setdefault(normalize_text(entry["title"]).strip(), []).append(entry)
        for normalized_title, duplicates in title_groups.items():
            if len(duplicates) < 2 or normalized_title in generic_titles:
                continue
            for duplicate_index, entry in enumerate(duplicates[1:], start=2):
                suffix = entry["category"].strip() or f"copia {duplicate_index}"
                if any(normalize_text(other["category"]).strip()
                       == normalize_text(entry["category"]).strip()
                       for other in duplicates[:duplicate_index - 1]):
                    suffix = f"copia {duplicate_index}"
                proposal = f"{entry['title']} — {suffix}"
                serial = 2
                while normalize_text(proposal).strip() in existing_titles:
                    proposal = f"{entry['title']} — {suffix} ({serial})"
                    serial += 1
                suggestions.append({
                    "tab_id": tab["id"], "tab_name": tab["name"], "entry": entry,
                    "field": "title", "value": proposal,
                    "reason": "Este título aparece varias veces en la pestaña. La propuesta ayuda a distinguir esta entrada.",
                })

        categorized = [entry for entry in entries
                       if normalize_text(entry["category"]).strip() not in generic_categories]
        candidate_tokens = {
            entry["id"]: suggestion_words(f"{entry['title']} {entry['content'][:800]}")
            for entry in categorized
        }
        token_index: dict[str, list[dict[str, Any]]] = {}
        for candidate in categorized:
            for token in candidate_tokens[candidate["id"]]:
                token_index.setdefault(token, []).append(candidate)

        for entry in entries:
            title_normalized = normalize_text(entry["title"]).strip()
            if title_normalized in generic_titles:
                first_line = next((line.strip(" \t#-*•") for line in entry["content"].splitlines()
                                   if line.strip()), "")
                if len(first_line) > 72:
                    first_line = first_line[:69].rstrip() + "…"
                if len(first_line) >= 4 and first_line.casefold() != entry["title"].casefold():
                    suggestions.append({
                        "tab_id": tab["id"], "tab_name": tab["name"], "entry": entry,
                        "field": "title", "value": first_line,
                        "reason": "El título es genérico. Esta propuesta usa la primera línea del contenido.",
                    })

            category_normalized = normalize_text(entry["category"]).strip()
            if category_normalized not in generic_categories:
                continue
            source_words = suggestion_words(f"{entry['title']} {entry['content'][:800]}")
            if len(source_words) < 2:
                continue
            possible: dict[str, tuple[dict[str, Any], int]] = {}
            for token in source_words:
                for other in token_index.get(token, []):
                    if other["id"] == entry["id"]:
                        continue
                    current = possible.get(other["id"], (other, 0))
                    possible[other["id"]] = (other, current[1] + 1)
            candidates: list[tuple[float, dict[str, Any], int]] = []
            for other, shared in possible.values():
                other_words = candidate_tokens[other["id"]]
                if shared < 2:
                    continue
                similarity = shared / max(1, len(source_words | other_words))
                title_similarity = SequenceMatcher(
                    None, entry["title"].casefold(), other["title"].casefold()
                ).ratio()
                score = max(similarity, title_similarity * 0.72)
                if score >= 0.18:
                    candidates.append((score, other, shared))
            if candidates:
                score, best, shared = max(candidates, key=lambda item: item[0])
                if score >= 0.22:
                    suggestions.append({
                        "tab_id": tab["id"], "tab_name": tab["name"], "entry": entry,
                        "field": "category", "value": best["category"],
                        "reason": (f"Comparte {shared} términos con «{best['title']}», "
                                   f"que pertenece a «{best['category']}» (coincidencia aproximada {score:.0%})."),
                    })

        if tab["kind"] == "note":
            note_entries = [entry for entry in entries if entry["kind"] == "note"]
            category_groups: dict[str, list[dict[str, Any]]] = {}
            category_names: dict[str, str] = {}
            for entry in note_entries:
                category = entry["category"].strip()
                normalized_category = normalize_text(category).strip()
                if normalized_category in generic_categories or not 2 <= len(category) <= 48:
                    continue
                category_groups.setdefault(normalized_category, []).append(entry)
                category_names.setdefault(normalized_category, category)

            for normalized_category, group in category_groups.items():
                if len(group) < 3 or len(group) >= len(note_entries):
                    continue
                if normalized_category in existing_tab_names:
                    continue
                category = category_names[normalized_category]
                suggestions.append({
                    "action": "create_tab",
                    "source_tab_id": tab["id"],
                    "source_tab_name": tab["name"],
                    "tab_name": category,
                    "entry_ids": [entry["id"] for entry in group],
                    "entry_count": len(group),
                    "reason": (
                        f"{len(group)} notas de «{tab['name']}» comparten la categoría "
                        f"«{category}». Crear una pestaña propia puede facilitar su consulta; "
                        "las demás notas permanecerán donde están."
                    ),
                })
    return suggestions


def looks_like_command(content: str) -> bool:
    first_line = next((line.strip() for line in content.splitlines() if line.strip()), "")
    first_line = re.sub(r"^(?:PS\s+[^>]*>|[>$]\s*)", "", first_line, flags=re.IGNORECASE)
    command_pattern = (
        r"(?i)^(?:winget|choco|scoop|docker|git|python(?:\d+(?:\.\d+)*)?|pip(?:3)?|npm|npx|"
        r"Get-|Set-|Remove-|New-|Start-|Stop-|Restart-|Test-|Enable-|Disable-|"
        r"reg(?:\.exe)?\b|sfc(?:\.exe)?\b|dism(?:\.exe)?\b|"
        r"robocopy\b|copy\b|move\b|del\b|erase\b|dir\b|ipconfig\b|"
        r"net\b|taskkill\b|shutdown\b|ffmpeg\b|sudo\b|apt\b|"
        r"import\s+\w|from\s+\w+\s+import\b|print\s*\(|def\s+\w+|"
        r"#!/|\$[A-Za-z_])"
    )
    return bool(re.match(command_pattern, first_line))


def plain_text_blocks(text: str) -> list[tuple[str, str]]:
    """Split a text file into blank-line or Markdown-heading separated items."""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    groups: list[list[str]] = []
    current: list[str] = []

    def is_title_line(line: str) -> bool:
        return bool(
            re.match(r"^\s{0,3}#{1,3}\s+\S", line)
            or re.match(r"(?i)^\s*(?:t[ií]tulo|title|nombre|name)\s*:\s*\S", line)
        )

    for line in lines:
        if is_title_line(line) and any(part.strip() for part in current):
            groups.append(current)
            current = []
        if not line.strip():
            nonempty = [part for part in current if part.strip()]
            if nonempty and not (len(nonempty) == 1 and is_title_line(nonempty[0])):
                groups.append(current)
                current = []
                continue
        current.append(line)
    if current:
        groups.append(current)

    blocks: list[tuple[str, str]] = []
    for group in groups:
        block = "\n".join(group).strip()
        if not block:
            continue
        block_lines = block.splitlines()
        proposed_title = ""
        first_line = block_lines[0].strip()
        heading = re.match(r"^#{1,3}\s+(.+?)\s*#*$", first_line)
        labeled_title = re.match(r"(?i)^(?:t[ií]tulo|title|nombre|name)\s*:\s*(.+)$", first_line)
        if heading or labeled_title:
            proposed_title = (heading or labeled_title).group(1).strip()
            content = "\n".join(block_lines[1:]).strip()
        else:
            content = block

        if not content:
            continue
        if not proposed_title:
            first_content_line = next((line.strip() for line in content.splitlines() if line.strip()), "")
            if looks_like_command(content):
                cleaned = re.sub(r"^(?:PS\s+[^>]*>|[>$]\s*)", "", first_content_line, flags=re.IGNORECASE)
                tokens = re.findall(r"[\w.-]+", cleaned)
                proposed_title = " ".join(tokens[:3]) or cleaned
            else:
                proposed_title = first_content_line.lstrip("# -*•\t")
            if len(proposed_title) > 72:
                proposed_title = proposed_title[:69].rstrip() + "…"
        blocks.append((proposed_title or "Nota importada", content))
    return blocks


def recommend_plain_text_destination(content: str, title: str,
                                     index: DestinationIndex) -> dict[str, Any] | None:
    """Recommend a local title, category, runner, and active note/command tab."""
    tabs = list(index.tabs)
    if not tabs:
        return None
    is_command = looks_like_command(content)
    matching_tabs = [tab for tab in tabs if tab["kind"] == ("command" if is_command else "note")]
    if matching_tabs:
        tabs = matching_tabs
    content_words = suggestion_words(f"{title} {content[:1200]}")
    best_match: tuple[float, dict[str, Any], dict[str, Any]] | None = None
    for tab in tabs:
        for entry in index.entries_by_tab[tab["id"]]:
            entry_words = suggestion_words(
                f"{entry['title']} {entry['category']} {entry['content'][:1200]}"
            )
            shared = content_words & entry_words
            if not shared:
                continue
            similarity = len(shared) / max(1, len(content_words | entry_words))
            title_similarity = SequenceMatcher(
                None, normalize_text(title), normalize_text(entry["title"])
            ).ratio()
            score = max(similarity, title_similarity * 0.70)
            if best_match is None or score > best_match[0]:
                best_match = (score, tab, entry)

    category = "General"
    destination = None
    if best_match and best_match[0] >= 0.12:
        _, destination, entry = best_match
        if entry["category"].strip():
            category = entry["category"].strip()

    if destination is None:
        if is_command:
            destination = next((tab for tab in tabs if tab["kind"] == "command"), None)
        else:
            destination = next((tab for tab in tabs if tab.get("builtin_key") == "notes"), None)
            if destination is None:
                destination = next((tab for tab in tabs if tab["kind"] == "note"), None)
        destination = destination or tabs[0]

    if category == "General":
        normalized = normalize_text(f"{title} {content[:800]}")
        category_hints = (
            ("Docker", ("docker", "container", "image")),
            ("PowerShell", ("powershell", "get-item", "set-item", "cmdlet")),
            ("Red", ("network", "red", "dns", "ipconfig", "router")),
            ("Windows", ("windows", "registry", "registro", "dism", "winget")),
            ("Python", ("python", "pip", "import", "def ")),
        )
        category = next((name for name, hints in category_hints
                         if any(hint in normalized for hint in hints)), category)

    first_line = next((line.strip() for line in content.splitlines() if line.strip()), "")
    if re.match(r"(?i)^(?:python|python\d+(?:\.\d+)*)\b|^(?:import|from|def|print\s*\()", first_line):
        runner = "Python"
    elif re.match(r"(?i)^(?:winget|choco|scoop|docker|git|reg(?:\.exe)?|sfc|dism|del|dir|copy|move|ipconfig|net|taskkill|shutdown|robocopy)\b", first_line):
        runner = "CMD"
    else:
        runner = "PowerShell"
    return {
        "title": title,
        "category": category,
        "tab_id": destination["id"],
        "tab_name": destination["name"],
        "runner": runner,
        "tabs": tabs,
        "content": content,
    }

