"""Plugin-tab model — QAbstractTableModel over PluginRow list.

Columns: Plugin Name, Flags, Lock, Index (checkbox painted into col 0 by the
delegate). Toggling enable writes back to plugins.txt via plugin_state.save.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex

from gui_qt.plugin_state import PluginRow, save_plugins

COL_NAME = 0
COL_FLAGS = 1
COL_LOCK = 2
COL_INDEX = 3
COLUMNS = ["Plugin Name", "Flags", "", "Index"]

RowRole = Qt.UserRole + 1      # the PluginRow
PFlagsRole = Qt.UserRole + 2   # int flag bitmask


class PluginModel(QAbstractTableModel):
    def __init__(self, rows: list[PluginRow] | None = None):
        super().__init__()
        self._rows: list[PluginRow] = rows or []
        self._game = None
        self._profile = None
        self._locks: dict[str, bool] = {}     # plugin name (lower) → locked
        self._profile_dir = None

    def set_rows(self, rows, game=None, profile=None, profile_dir=None):
        self.beginResetModel()
        self._rows = rows
        self._game = game
        self._profile = profile
        self._profile_dir = profile_dir
        self._locks = {}
        if profile_dir is not None:
            try:
                from Utils.profile_state import read_plugin_locks
                self._locks = read_plugin_locks(profile_dir) or {}
            except Exception:
                self._locks = {}
        self.endResetModel()

    def is_locked(self, i: int) -> bool:
        return bool(self._locks.get(self._rows[i].name.lower(), False))

    def toggle_lock(self, i: int):
        name = self._rows[i].name.lower()
        self._locks[name] = not self._locks.get(name, False)
        idx = self.index(i, COL_LOCK)
        self.dataChanged.emit(idx, idx, [])
        if self._profile_dir is not None:
            try:
                from Utils.profile_state import write_plugin_locks
                write_plugin_locks(self._profile_dir, self._locks)
            except Exception as exc:
                print(f"[gui_qt] plugin locks save failed: {exc}", flush=True)

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent=QModelIndex()):
        return len(COLUMNS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return COLUMNS[section]
        return None

    def row(self, i: int) -> PluginRow:
        return self._rows[i]

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        r = self._rows[index.row()]
        col = index.column()
        if role == RowRole:
            return r
        if role == PFlagsRole:
            return r.flags
        if role == Qt.DisplayRole:
            if col == COL_NAME:
                return r.name
            if col == COL_INDEX:
                return f"{index.row():03d}"
            return ""
        return None

    def flags(self, index):
        if not index.isValid():
            return Qt.NoItemFlags
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable

    def toggle(self, i: int):
        r = self._rows[i]
        if r.vanilla:
            return   # vanilla plugins are always-on; can't be disabled
        r.enabled = not r.enabled
        idx = self.index(i, COL_NAME)
        self.dataChanged.emit(idx, idx, [RowRole, Qt.DisplayRole])
        self._save()

    def _save(self):
        if self._game is not None and self._profile:
            try:
                save_plugins(self._game, self._profile, self._rows)
            except Exception as exc:
                print(f"[gui_qt] plugins.txt save failed: {exc}", flush=True)
