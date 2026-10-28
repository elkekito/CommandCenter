"""SQLite persistence, JSON merging, backups, and database location management."""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

APP_DIR_NAME = "CommandCenter"
DATABASE_FILENAME = "command-center.sqlite3"
LOCATION_CONFIG_FILENAME = "storage-location.json"
BUILTIN_TABS = [
    ("commands", "⚡ Comandos", "command"),
    ("games", "🎮 Juegos", "game"),
    ("notes", "📝 Notas & Hardware", "note"),
    ("urls", "🌐 URLs Útiles", "url"),
    ("ai", "🤖 IA", "note"),
]
SCHEMA_VERSION = 2
BACKUP_DIRNAME = "backups"
BACKUP_RETENTION = 10


def application_data_dir() -> Path:
    """Return the per-user data directory without relying on the install path."""
    if os.name == "nt":
        root = os.environ.get("LOCALAPPDATA")
        if root:
            return Path(root) / APP_DIR_NAME
    return Path.home() / ".local" / "share" / APP_DIR_NAME.lower()


def storage_config_path() -> Path:
    """Keep the selected database location in a stable per-user config folder."""
    return application_data_dir() / LOCATION_CONFIG_FILENAME


def load_database_location() -> Path | None:
    config = storage_config_path()
    try:
        payload = json.loads(config.read_text(encoding="utf-8"))
        value = payload.get("database_path") if isinstance(payload, dict) else None
        return Path(value).expanduser() if isinstance(value, str) and value.strip() else None
    except (OSError, ValueError, TypeError):
        return None


def save_database_location(path: Path) -> None:
    config = storage_config_path()
    config.parent.mkdir(parents=True, exist_ok=True)
    temporary = config.with_suffix(".tmp")
    temporary.write_text(
        json.dumps({"database_path": str(path.resolve())}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary.replace(config)


def resource_path(name: str) -> Path:
    """Resolve a bundled resource in source and PyInstaller one-file runs."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / name


def prune_backups(backup_dir: Path, keep: int) -> list[Path]:
    """Delete the oldest automatic snapshots, keeping the newest `keep`. Names sort by time."""
    copies = sorted(backup_dir.glob("command-center-*.sqlite3"))
    removed = copies[:-keep] if keep > 0 else []
    for old in removed:
        old.unlink(missing_ok=True)
    return removed


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def new_id() -> str:
    return str(uuid.uuid4())


class DataStore:
    """Local database repository. Every mutating operation uses a transaction."""

    def __init__(self, database_path: Path | None = None):
        self.directory = (database_path.parent if database_path else application_data_dir())
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = database_path or self.directory / DATABASE_FILENAME
        self.connection = self._open_connection(self.path)
        self._create_schema()
        self._initialize_defaults()

    @staticmethod
    def _open_connection(path: Path) -> sqlite3.Connection:
        connection = sqlite3.connect(path, timeout=15)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def _create_schema(self) -> None:
        with self.connection:
            self.connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS app_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS tabs (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    position INTEGER NOT NULL,
                    builtin_key TEXT UNIQUE,
                    archived INTEGER NOT NULL DEFAULT 0 CHECK (archived IN (0, 1))
                );
                CREATE TABLE IF NOT EXISTS entries (
                    id TEXT PRIMARY KEY,
                    tab_id TEXT NOT NULL REFERENCES tabs(id),
                    kind TEXT NOT NULL,
                    title TEXT NOT NULL,
                    category TEXT NOT NULL DEFAULT '',
                    content TEXT NOT NULL DEFAULT '',
                    runner TEXT NOT NULL DEFAULT 'PowerShell',
                    position INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    archived INTEGER NOT NULL DEFAULT 0 CHECK (archived IN (0, 1))
                );
                CREATE INDEX IF NOT EXISTS entries_tab_position ON entries(tab_id, position);
                CREATE INDEX IF NOT EXISTS entries_tab_category ON entries(tab_id, category);
                CREATE TABLE IF NOT EXISTS app_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                """
            )
            columns = {row["name"] for row in self.connection.execute("PRAGMA table_info(entries)")}
            if "archived" not in columns:
                self.connection.execute(
                    "ALTER TABLE entries ADD COLUMN archived INTEGER NOT NULL DEFAULT 0 CHECK (archived IN (0, 1))"
                )
            self.connection.execute(
                "INSERT OR IGNORE INTO app_meta(key, value) VALUES ('schema_version', ?)",
                (str(SCHEMA_VERSION),),
            )
            self.connection.execute(
                "UPDATE app_meta SET value=? WHERE key='schema_version'", (str(SCHEMA_VERSION),)
            )

    def _initialize_defaults(self) -> None:
        """Create empty built-in collections without reading bundled JSON data."""
        count = self.connection.execute("SELECT COUNT(*) FROM tabs").fetchone()[0]
        if not count:
            self.seed_defaults()

    def seed_defaults(self) -> None:
        with self.connection:
            for position, (key, name, kind) in enumerate(BUILTIN_TABS):
                self.connection.execute(
                    "INSERT OR IGNORE INTO tabs(id, name, kind, position, builtin_key) VALUES (?, ?, ?, ?, ?)",
                    (key, name, kind, position, key),
                )

    def import_legacy_payload(self, payload: Any) -> str:
        if not isinstance(payload, dict):
            raise ValueError("la raíz del JSON debe ser un objeto")

        raw_tabs = payload.get("tabs")
        if not isinstance(raw_tabs, list):
            raw_tabs = []
            custom = payload.get("custom_tabs", [])
            custom_map = {item.get("name"): item for item in custom if isinstance(item, dict) and item.get("name")}
            defaults = {name: {"name": name, "key": key, "type": "notes" if kind == "note" else kind}
                        for key, name, kind in BUILTIN_TABS}
            pool = {**defaults, **{item["name"]: {"name": item["name"], "key": item["key"], "type": "notes"}
                                    for item in custom_map.values() if item.get("key")}}
            for name in payload.get("tabs_order", []):
                if name in pool:
                    raw_tabs.append(pool.pop(name))
            raw_tabs.extend(pool.values())

        normalized_tabs: list[dict[str, Any]] = []
        seen_names: set[str] = set()
        for tab in raw_tabs:
            if not isinstance(tab, dict):
                continue
            name = str(tab.get("name", "")).strip()
            key = str(tab.get("key", "")).strip()
            raw_type = str(tab.get("type", "notes"))
            kind = {"cmd": "command", "games": "game", "urls": "url", "notes": "note"}.get(raw_type, raw_type)
            if not name or not key or kind not in {"command", "game", "note", "url"} or name.casefold() in seen_names:
                continue
            seen_names.add(name.casefold())
            normalized_tabs.append({"name": name, "key": key, "kind": kind,
                                    "archived": bool(tab.get("archived", False))})

        if not normalized_tabs:
            normalized_tabs = [
                {"name": name, "key": key, "kind": kind, "archived": False}
                for key, name, kind in BUILTIN_TABS
            ]

        messages: list[str] = []
        with self.connection:
            tab_lookup: dict[str, str] = {}
            for position, tab in enumerate(normalized_tabs):
                builtin = tab["key"] if tab["key"] in {key for key, _, _ in BUILTIN_TABS} else None
                tab_id = builtin or f"custom:{new_id()}"
                self.connection.execute(
                    "INSERT OR IGNORE INTO tabs(id, name, kind, position, builtin_key, archived) VALUES (?, ?, ?, ?, ?, ?)",
                    (tab_id, tab["name"], tab["kind"], position, builtin, int(tab["archived"])),
                )
                # A repeated legacy key maps its records to the first matching visible tab.
                existing = self.connection.execute("SELECT id FROM tabs WHERE id = ?", (tab_id,)).fetchone()
                tab_lookup[tab["key"]] = existing["id"]

            by_key = {tab["key"]: tab for tab in normalized_tabs}
            for key in ("commands", "games", "notes", "urls", "ai"):
                by_key.setdefault(key, {"name": key, "key": key, "kind": {"commands": "command", "games": "game", "urls": "url"}.get(key, "note")})
            reserved_keys = {"tabs", "custom_tabs", "tabs_order", "commands", "games", "notes", "urls", "ai"}
            for key, value in payload.items():
                if key in reserved_keys or key in by_key or not isinstance(value, list):
                    continue
                # Older versions kept data after a custom tab was hidden/deleted.
                # Recover orphan collections into an archived tab instead of dropping them.
                legacy_key = str(key)
                by_key[legacy_key] = {"name": f"Recuperado: {legacy_key[:64]}", "key": legacy_key,
                                     "kind": "note", "archived": True}
            for key, tab in by_key.items():
                if key not in tab_lookup:
                    builtin = key if key in {item[0] for item in BUILTIN_TABS} else None
                    tab_id = builtin or f"custom:{new_id()}"
                    position = self.connection.execute("SELECT COALESCE(MAX(position), -1) + 1 FROM tabs").fetchone()[0]
                    self.connection.execute(
                        "INSERT OR IGNORE INTO tabs(id, name, kind, position, builtin_key, archived) VALUES (?, ?, ?, ?, ?, 1)",
                        (tab_id, tab["name"], tab["kind"], position, builtin),
                    )
                    tab_lookup[key] = tab_id

            for key, tab in by_key.items():
                raw_items = payload.get(key, [])
                if not isinstance(raw_items, list):
                    messages.append(f"{key}: colección ignorada porque no es una lista")
                    continue
                for position, item in enumerate(raw_items):
                    if not isinstance(item, dict):
                        messages.append(f"{key}: entrada {position + 1} ignorada por formato no válido")
                        continue
                    kind = tab["kind"]
                    if kind == "command":
                        title = item.get("name", "Sin título")
                        content = item.get("command", "")
                        category = item.get("category", "General")
                        runner = item.get("runner", "PowerShell")
                    elif kind == "game":
                        title = item.get("title", "Truco")
                        content = item.get("command", "")
                        category = item.get("game", "General")
                        runner = "PowerShell"
                    elif kind == "url":
                        title = item.get("title", "Enlace")
                        content = item.get("url", "")
                        category = item.get("category", "General")
                        runner = "PowerShell"
                    else:
                        title = item.get("title", "Nota")
                        content = item.get("content", "")
                        category = item.get("category", "General")
                        runner = "PowerShell"
                    is_archived = bool(item.get("archived", False))
                    timestamp = now_utc()
                    self.connection.execute(
                        """INSERT INTO entries
                           (id, tab_id, kind, title, category, content, runner, position, created_at, updated_at, archived)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (new_id(), tab_lookup[key], kind, str(title or ""), str(category or ""),
                         str(content or ""), str(runner or "PowerShell"), position, timestamp, timestamp,
                         int(is_archived)),
                    )

        return "; ".join(messages[:6])

    def list_tabs(self, include_archived: bool = False) -> list[dict[str, Any]]:
        where = "" if include_archived else "WHERE archived = 0"
        rows = self.connection.execute(
            f"SELECT id, name, kind, position, builtin_key, archived FROM tabs {where} ORDER BY position, name"
        ).fetchall()
        return [dict(row) for row in rows]

    def list_entries(self, tab_id: str, include_archived: bool = False) -> list[dict[str, Any]]:
        archived_clause = "" if include_archived else " AND archived=0"
        rows = self.connection.execute(
            f"SELECT * FROM entries WHERE tab_id = ?{archived_clause} ORDER BY position, created_at", (tab_id,)
        ).fetchall()
        return [dict(row) for row in rows]

    def bulk_update_entries(self, tab_id: str, updates: dict[str, dict[str, str]]) -> None:
        """Update selected entry titles/categories as one transaction."""
        timestamp = now_utc()
        with self.connection:
            for entry_id, fields in updates.items():
                current = self.connection.execute(
                    "SELECT title, category FROM entries WHERE id=? AND tab_id=?",
                    (entry_id, tab_id),
                ).fetchone()
                if current is None:
                    raise ValueError("Uno de los elementos seleccionados ya no existe")
                title = fields.get("title", current["title"]).strip()
                category = fields.get("category", current["category"]).strip()
                if not title:
                    raise ValueError("El título no puede quedar vacío")
                self.connection.execute(
                    "UPDATE entries SET title=?, category=?, updated_at=? WHERE id=? AND tab_id=?",
                    (title, category, timestamp, entry_id, tab_id),
                )

    def set_entries_archived(self, tab_id: str, entry_ids: list[str], archived: bool) -> None:
        unique_ids = list(dict.fromkeys(entry_ids))
        if not unique_ids:
            return
        with self.connection:
            next_position = self.connection.execute(
                "SELECT COALESCE(MAX(position), -1) + 1 FROM entries WHERE tab_id=? AND archived=0",
                (tab_id,),
            ).fetchone()[0]
            for entry_id in unique_ids:
                if archived:
                    cursor = self.connection.execute(
                        "UPDATE entries SET archived=1 WHERE id=? AND tab_id=? AND archived=0",
                        (entry_id, tab_id),
                    )
                else:
                    cursor = self.connection.execute(
                        "UPDATE entries SET archived=0, position=? WHERE id=? AND tab_id=? AND archived=1",
                        (next_position, entry_id, tab_id),
                    )
                    next_position += 1
                if cursor.rowcount != 1:
                    raise ValueError("Uno de los elementos seleccionados ya cambió o no está disponible")

    def save_entry(self, tab_id: str, kind: str, title: str, category: str, content: str,
                   runner: str, entry_id: str | None = None) -> str:
        timestamp = now_utc()
        with self.connection:
            if entry_id:
                self.connection.execute(
                    """UPDATE entries SET title=?, category=?, content=?, runner=?, updated_at=?
                       WHERE id=? AND tab_id=?""",
                    (title, category, content, runner, timestamp, entry_id, tab_id),
                )
                if self.connection.execute("SELECT changes()").fetchone()[0] == 0:
                    raise ValueError("El elemento ya no existe en esta pestaña")
                return entry_id
            position = self.connection.execute(
                "SELECT COALESCE(MAX(position), -1) + 1 FROM entries WHERE tab_id = ?", (tab_id,)
            ).fetchone()[0]
            new_entry_id = new_id()
            self.connection.execute(
                """INSERT INTO entries(id, tab_id, kind, title, category, content, runner, position, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (new_entry_id, tab_id, kind, title, category, content, runner, position, timestamp, timestamp),
            )
            return new_entry_id

    def delete_entry(self, entry_id: str) -> None:
        with self.connection:
            self.connection.execute("DELETE FROM entries WHERE id = ?", (entry_id,))

    def reorder_entries(self, tab_id: str, ordered_ids: list[str]) -> None:
        with self.connection:
            for position, entry_id in enumerate(ordered_ids):
                self.connection.execute(
                    "UPDATE entries SET position=? WHERE id=? AND tab_id=?",
                    (position, entry_id, tab_id),
                )

    def reorder_tabs(self, ordered_ids: list[str]) -> None:
        with self.connection:
            for position, tab_id in enumerate(ordered_ids):
                self.connection.execute("UPDATE tabs SET position=? WHERE id=?", (position, tab_id))

    def create_tab(self, name: str) -> str:
        tab_id = f"custom:{new_id()}"
        position = self.connection.execute("SELECT COALESCE(MAX(position), -1) + 1 FROM tabs WHERE archived=0").fetchone()[0]
        with self.connection:
            self.connection.execute(
                "INSERT INTO tabs(id, name, kind, position, archived) VALUES (?, ?, 'note', ?, 0)",
                (tab_id, name, position),
            )
        return tab_id

    def create_tab_from_entries(self, name: str, source_tab_id: str, entry_ids: list[str]) -> str:
        """Create a note tab and move selected notes in one transaction."""
        name = name.strip()
        unique_ids = list(dict.fromkeys(entry_ids))
        if not name:
            raise ValueError("El nombre de la pestaña no puede estar vacío")
        if not unique_ids:
            raise ValueError("No hay notas seleccionadas para mover")

        tab_names = self.connection.execute("SELECT name FROM tabs").fetchall()
        if any(row["name"].casefold() == name.casefold() for row in tab_names):
            raise ValueError("Ya existe una pestaña con ese nombre")
        source = self.connection.execute(
            "SELECT kind, archived FROM tabs WHERE id=?", (source_tab_id,)
        ).fetchone()
        if source is None or source["kind"] != "note" or source["archived"]:
            raise ValueError("La pestaña de origen ya no está disponible")

        tab_id = f"custom:{new_id()}"
        with self.connection:
            position = self.connection.execute(
                "SELECT COALESCE(MAX(position), -1) + 1 FROM tabs WHERE archived=0"
            ).fetchone()[0]
            self.connection.execute(
                "INSERT INTO tabs(id, name, kind, position, archived) VALUES (?, ?, 'note', ?, 0)",
                (tab_id, name, position),
            )
            for position, entry_id in enumerate(unique_ids):
                cursor = self.connection.execute(
                    "UPDATE entries SET tab_id=?, position=? "
                    "WHERE id=? AND tab_id=? AND kind='note'",
                    (tab_id, position, entry_id, source_tab_id),
                )
                if cursor.rowcount != 1:
                    raise ValueError("Una de las notas ya no pertenece a la pestaña de origen")
        return tab_id

    def rename_tab(self, tab_id: str, name: str) -> None:
        with self.connection:
            self.connection.execute("UPDATE tabs SET name=? WHERE id=?", (name, tab_id))

    def archive_tab(self, tab_id: str) -> None:
        with self.connection:
            self.connection.execute("UPDATE tabs SET archived=1 WHERE id=?", (tab_id,))

    def restore_tab(self, tab_id: str) -> None:
        position = self.connection.execute("SELECT COALESCE(MAX(position), -1) + 1 FROM tabs WHERE archived=0").fetchone()[0]
        with self.connection:
            self.connection.execute("UPDATE tabs SET archived=0, position=? WHERE id=?", (position, tab_id))

    def permanently_delete_tab(self, tab_id: str) -> None:
        with self.connection:
            self.connection.execute("DELETE FROM entries WHERE tab_id=?", (tab_id,))
            self.connection.execute("DELETE FROM tabs WHERE id=?", (tab_id,))

    def get_setting(self, key: str, default: Any = None) -> Any:
        row = self.connection.execute("SELECT value FROM app_settings WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def set_setting(self, key: str, value: Any) -> None:
        with self.connection:
            self.connection.execute(
                "INSERT INTO app_settings(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, json.dumps(value, ensure_ascii=False)),
            )

    def backup(self, destination: Path | None = None) -> Path:
        """Write a verified snapshot. The automatic folder keeps only the newest BACKUP_RETENTION copies."""
        backup_dir = destination or self.directory / BACKUP_DIRNAME
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        target = backup_dir / f"command-center-{stamp}.sqlite3"
        backup_connection = sqlite3.connect(target)
        try:
            self.connection.backup(backup_connection)
        finally:
            backup_connection.close()
        check_connection = sqlite3.connect(target)
        try:
            result = check_connection.execute("PRAGMA quick_check").fetchone()
        finally:
            check_connection.close()
        if not result or result[0] != "ok":
            target.unlink(missing_ok=True)
            raise sqlite3.DatabaseError("La copia de seguridad no superó la comprobación de integridad.")
        if destination is None:
            prune_backups(backup_dir, BACKUP_RETENTION)
        return target

    def move_database(self, destination: Path) -> Path:
        """Move the active database after making and validating a snapshot."""
        destination = destination.expanduser().resolve()
        current_path = self.path.resolve()
        if destination == current_path:
            raise ValueError("La base de datos ya está en esa ubicación.")
        if destination.exists():
            raise FileExistsError("Ya existe una base de datos en la carpeta elegida; no se sobrescribirá.")

        destination.parent.mkdir(parents=True, exist_ok=True)
        safety_copy = self.backup()
        target_connection: sqlite3.Connection | None = None
        try:
            target_connection = sqlite3.connect(destination, timeout=15)
            self.connection.backup(target_connection)
            result = target_connection.execute("PRAGMA quick_check").fetchone()
            if not result or result[0] != "ok":
                raise sqlite3.DatabaseError("La copia de destino no superó la comprobación de integridad.")
            target_connection.close()
            target_connection = None

            self.connection.close()
            try:
                moved_connection = self._open_connection(destination)
                save_database_location(destination)
            except Exception:
                try:
                    moved_connection.close()
                except (UnboundLocalError, sqlite3.Error):
                    pass
                self.connection = self._open_connection(current_path)
                for suffix in ("", "-wal", "-shm"):
                    candidate = Path(f"{destination}{suffix}")
                    if candidate.exists():
                        try:
                            candidate.unlink()
                        except OSError:
                            pass
                raise

            self.connection = moved_connection
            self.path = destination
            self.directory = destination.parent
            for suffix in ("", "-wal", "-shm"):
                candidate = Path(f"{current_path}{suffix}")
                if candidate.exists():
                    try:
                        candidate.unlink()
                    except OSError:
                        pass
            return safety_copy
        except Exception:
            if target_connection is not None:
                target_connection.close()
            raise

    def export_json(self, destination: Path) -> None:
        tabs = self.list_tabs(include_archived=True)
        payload: dict[str, Any] = {"tabs": [], "commands": [], "games": [], "notes": [], "urls": [], "ai": []}
        for tab in tabs:
            legacy_type = {"command": "cmd", "game": "games", "url": "urls", "note": "notes"}[tab["kind"]]
            tab_key = tab["builtin_key"] or tab["id"]
            payload["tabs"].append({"name": tab["name"], "key": tab_key, "type": legacy_type, "archived": bool(tab["archived"])})
            bucket = tab["builtin_key"] if tab["builtin_key"] in payload else tab_key
            if bucket not in payload:
                payload[bucket] = []
            for entry in self.list_entries(tab["id"], include_archived=True):
                if tab["kind"] == "command":
                    item = {"name": entry["title"], "command": entry["content"], "runner": entry["runner"], "category": entry["category"], "archived": bool(entry["archived"])}
                elif tab["kind"] == "game":
                    item = {"game": entry["category"], "title": entry["title"], "command": entry["content"], "archived": bool(entry["archived"])}
                elif tab["kind"] == "url":
                    item = {"title": entry["title"], "url": entry["content"], "category": entry["category"], "archived": bool(entry["archived"])}
                else:
                    item = {"title": entry["title"], "category": entry["category"], "content": entry["content"], "archived": bool(entry["archived"])}
                payload[bucket].append(item)
        destination.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def merge_from_json(self, source: Path) -> tuple[Path, str]:
        """Add JSON collections without replacing current tabs or entries.

        Existing tabs are matched by built-in key or by custom name and kind.
        Exact duplicate entries are skipped, making repeated imports safe.
        """
        payload = json.loads(source.read_text(encoding="utf-8-sig"))
        if not isinstance(payload, dict):
            raise ValueError("La raíz del JSON debe ser un objeto")

        with tempfile.TemporaryDirectory(prefix="command-center-import-") as temporary:
            staged = DataStore(Path(temporary) / "staged.sqlite3")
            try:
                report = staged.import_legacy_payload(payload)
                incoming_tabs = staged.list_tabs(include_archived=True)
                incoming_entries = {
                    tab["id"]: staged.list_entries(tab["id"], include_archived=True)
                    for tab in incoming_tabs
                }

                # The snapshot precedes every write to the user's database.
                safety_copy = self.backup()
                existing_tabs = self.list_tabs(include_archived=True)
                by_builtin = {tab["builtin_key"]: tab for tab in existing_tabs if tab["builtin_key"]}
                by_name_kind = {
                    (tab["name"].casefold(), tab["kind"]): tab
                    for tab in existing_tabs if not tab["builtin_key"]
                }
                next_position = max((tab["position"] for tab in existing_tabs), default=-1) + 1
                added_tabs = 0
                added_entries = 0
                skipped_duplicates = 0

                with self.connection:
                    target_ids: dict[str, str] = {}
                    for tab in incoming_tabs:
                        target = by_builtin.get(tab["builtin_key"]) if tab["builtin_key"] else None
                        if target is None and not tab["builtin_key"]:
                            target = by_name_kind.get((tab["name"].casefold(), tab["kind"]))
                        if target is None:
                            tab_id = tab["builtin_key"] or f"custom:{new_id()}"
                            builtin_key = tab["builtin_key"]
                            self.connection.execute(
                                """INSERT INTO tabs(id, name, kind, position, builtin_key, archived)
                                   VALUES (?, ?, ?, ?, ?, ?)""",
                                (tab_id, tab["name"], tab["kind"], next_position, builtin_key, tab["archived"]),
                            )
                            target = {**tab, "id": tab_id, "position": next_position}
                            next_position += 1
                            added_tabs += 1
                            if builtin_key:
                                by_builtin[builtin_key] = target
                            else:
                                by_name_kind[(tab["name"].casefold(), tab["kind"])] = target
                        target_ids[tab["id"]] = target["id"]

                    seen_by_target: dict[str, set[tuple[str, str, str, str]]] = {}
                    next_entry_position: dict[str, int] = {}
                    for target_id in set(target_ids.values()):
                        rows = self.connection.execute(
                            "SELECT title, category, content, runner, position FROM entries WHERE tab_id = ?",
                            (target_id,),
                        ).fetchall()
                        seen_by_target[target_id] = {
                            (row["title"], row["category"], row["content"], row["runner"])
                            for row in rows
                        }
                        next_entry_position[target_id] = max((row["position"] for row in rows), default=-1) + 1

                    for source_tab in incoming_tabs:
                        target_id = target_ids[source_tab["id"]]
                        seen = seen_by_target[target_id]
                        for entry in incoming_entries[source_tab["id"]]:
                            identity = (entry["title"], entry["category"], entry["content"], entry["runner"])
                            if identity in seen:
                                skipped_duplicates += 1
                                continue
                            position = next_entry_position[target_id]
                            timestamp = now_utc()
                            self.connection.execute(
                                """INSERT INTO entries
                                   (id, tab_id, kind, title, category, content, runner, position, created_at, updated_at, archived)
                                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                                (new_id(), target_id, entry["kind"], entry["title"], entry["category"],
                                 entry["content"], entry["runner"], position, timestamp, timestamp,
                                 int(bool(entry.get("archived", False)))),
                            )
                            next_entry_position[target_id] = position + 1
                            seen.add(identity)
                            added_entries += 1
            finally:
                staged.close()
        summary = f"Añadidas {added_tabs} pestañas y {added_entries} elementos; omitidos {skipped_duplicates} duplicados."
        details = "; ".join(part for part in (summary, report) if part)
        return safety_copy, details

    def close(self) -> None:
        self.connection.close()
