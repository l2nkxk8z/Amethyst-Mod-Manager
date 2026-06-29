"""Plugin-tab view + delegate (Plugins tab, v1).

A QTreeView over PluginModel with a delegate that paints: enable checkbox, name
(dimmed when disabled), the ESL 'L' cyan badge + master indicator in the Flags
column, the lock column, and the load-order index. Single-click the checkbox to
toggle (persists to plugins.txt).
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QRect, QSize, QEvent
from PySide6.QtGui import QColor, QFont, QPen, QBrush
from PySide6.QtWidgets import (
    QTreeView, QStyledItemDelegate, QStyle, QAbstractItemView, QHeaderView,
)

from gui_qt.theme_qt import active_palette, _c
from gui_qt.icons import icon
from gui_qt.modlist_header import TkStyleHeader
from gui_qt.plugin_model import (
    PluginModel, RowRole, PFlagsRole, COL_NAME, COL_FLAGS, COL_LOCK, COL_INDEX,
)
from gui_qt.plugin_state import (
    PF_MISSING, PF_LATE, PF_VMM, PF_ESL, PF_LOOT, PF_DIRTY, PF_TAGS, PF_MASTER,
)

# Flag bit → icon filename, painted left→right (order matches the Tk app).
# ESL is drawn as a cyan "L" text badge (handled specially), not an icon.
_PLUGIN_FLAG_ICONS = [
    (PF_MISSING, "warning2.png"),
    (PF_LATE, "warning.png"),
    (PF_VMM, "info.png"),
    (PF_LOOT, "Loot_info.png"),
    (PF_DIRTY, "brush.png"),
    (PF_TAGS, "tag.png"),
]

ROW_H = 33
CHECK_BOX = 17
FONT_PX = 14
LOCK_SZ = 17

# Per-column min/default widths; Plugin Name (col 0) auto-fills like the modlist.
COL_DEFAULTS = {COL_FLAGS: 80, COL_LOCK: 40, COL_INDEX: 60}
COL_MINS = {COL_NAME: 120, COL_FLAGS: 60, COL_LOCK: 36, COL_INDEX: 50}
NAME_MIN = COL_MINS[COL_NAME]


class PluginDelegate(QStyledItemDelegate):
    def __init__(self, parent=None):
        super().__init__(parent)
        p = active_palette()
        self.c_row = QColor(_c(p, "BG_ROW"))
        self.c_row_alt = QColor(_c(p, "BG_ROW_ALT"))
        self.c_sel = QColor(_c(p, "BG_SELECT"))
        self.c_hover = QColor(_c(p, "BG_ROW_HOVER"))
        self.c_text = QColor(_c(p, "TEXT_MAIN"))
        self.c_text_dim = QColor(_c(p, "TEXT_DIM"))
        self.c_text_on_sel = QColor(_c(p, "TEXT_ON_ACCENT"))
        self.c_border = QColor(_c(p, "BORDER"))
        self.c_check = QColor(_c(p, "BTN_SUCCESS"))
        self.c_check_off = QColor(_c(p, "BG_DEEP"))
        self.c_esl = QColor(_c(p, "TONE_BLUE_SOFT"))
        self.c_master = QColor(_c(p, "TEXT_WARN"))

    def sizeHint(self, opt, index):
        return QSize(opt.rect.width(), ROW_H)

    def paint(self, p, opt, index):
        r = opt.rect
        row = index.data(RowRole)
        p.save()
        p.setRenderHint(p.RenderHint.Antialiasing, False)

        selected = bool(opt.state & QStyle.State_Selected)
        if selected:
            p.fillRect(r, self.c_sel)
        elif opt.state & QStyle.State_MouseOver:
            p.fillRect(r, self.c_hover)
        else:
            p.fillRect(r, self.c_row_alt if index.row() % 2 else self.c_row)

        enabled = bool(row and row.enabled)
        vanilla = bool(row and row.vanilla)
        # Vanilla plugins are greyed (dim) regardless of enabled state.
        text_color = self.c_text_on_sel if selected else (
            self.c_text_dim if (vanilla or not enabled) else self.c_text)
        col = index.column()

        if col == COL_NAME:
            self._paint_name(p, r, row, enabled, vanilla, text_color)
        elif col == COL_FLAGS:
            self._paint_flags(p, r, index.data(PFlagsRole) or 0)
        elif col == COL_LOCK:
            self._paint_lock(p, r, index.model().is_locked(index.row()))
        elif col == COL_INDEX:
            p.setPen(text_color)
            _f = QFont(); _f.setPixelSize(FONT_PX); p.setFont(_f)
            p.drawText(r, Qt.AlignVCenter | Qt.AlignHCenter,
                       index.data(Qt.DisplayRole) or "")
        p.restore()

    def _lock_rect(self, r):
        return QRect(r.center().x() - LOCK_SZ // 2,
                     r.top() + (r.height() - LOCK_SZ) // 2, LOCK_SZ, LOCK_SZ)

    def _paint_lock(self, p, r, locked):
        lk = self._lock_rect(r)
        p.setRenderHint(p.RenderHint.Antialiasing, True)
        p.setPen(QPen(self.c_border, 1))
        p.setBrush(QBrush(self.c_check_off))
        p.drawRoundedRect(lk, 3, 3)
        if locked:
            ic = icon("lock.png", LOCK_SZ - 2)
            if not ic.isNull():
                ic.paint(p, lk.adjusted(1, 1, -1, -1))
        p.setRenderHint(p.RenderHint.Antialiasing, False)

    def _paint_name(self, p, r, row, enabled, vanilla, text_color):
        box = QRect(r.left() + 10, r.top() + (r.height() - CHECK_BOX) // 2,
                    CHECK_BOX, CHECK_BOX)
        p.setRenderHint(p.RenderHint.Antialiasing, True)
        p.setPen(QPen(self.c_border, 1))
        # Vanilla: always-on but dimmed (greyed fill + grey tick) to read as
        # locked/non-interactive. Otherwise green when enabled, hollow when not.
        fill = (self.c_check_off if vanilla else
                (self.c_check if enabled else self.c_check_off))
        p.setBrush(QBrush(fill))
        p.drawRoundedRect(box, 3, 3)
        if enabled:
            p.setPen(QPen(self.c_text_dim if vanilla else QColor("white"), 2))
            p.drawLine(box.left() + 4, box.center().y() + 1,
                       box.center().x() - 1, box.bottom() - 4)
            p.drawLine(box.center().x() - 1, box.bottom() - 4,
                       box.right() - 3, box.top() + 4)
        p.setRenderHint(p.RenderHint.Antialiasing, False)

        tx = box.right() + 10
        p.setPen(text_color)
        _f = QFont(); _f.setPixelSize(FONT_PX); p.setFont(_f)
        name_rect = QRect(tx, r.top(), r.right() - tx - 6, r.height())
        elided = p.fontMetrics().elidedText(row.name if row else "",
                                            Qt.ElideRight, name_rect.width())
        p.drawText(name_rect, Qt.AlignVCenter | Qt.AlignLeft, elided)

    def _paint_flags(self, p, r, bits):
        # Ordered flag glyphs: the icon flags, then the ESL 'L' badge. (There is
        # no master indicator — Tk doesn't show one; masters are implied by ext.)
        items = []
        for bit, name in _PLUGIN_FLAG_ICONS:
            if bits & bit:
                items.append(("icon", name))
        if bits & PF_ESL:
            items.append(("esl", None))
        if not items:
            return
        sz = 18
        total = len(items) * sz + (len(items) - 1) * 4
        x = r.left() + max(4, (r.width() - total) // 2)
        cy = r.center().y()
        for kind, name in items:
            cell = QRect(x, cy - sz // 2, sz, sz)
            if kind == "esl":
                f = QFont(); f.setBold(True); f.setPixelSize(13); p.setFont(f)
                p.setPen(self.c_esl)
                p.drawText(cell, Qt.AlignCenter, "L")
            else:
                ic = icon(name, sz)
                if not ic.isNull():
                    ic.paint(p, cell)
            x += sz + 4

    def editorEvent(self, event, model, opt, index):
        if event.type() != QEvent.MouseButtonRelease:
            return False
        pos = event.position().toPoint()
        if index.column() == COL_NAME:
            box = QRect(opt.rect.left() + 6, opt.rect.top(), 26, opt.rect.height())
            if box.contains(pos):
                model.toggle(index.row())
                return True
        elif index.column() == COL_LOCK:
            if self._lock_rect(opt.rect).contains(pos):
                model.toggle_lock(index.row())
                return True
        return False


class PluginView(QTreeView):
    def __init__(self, model: PluginModel, parent=None):
        super().__init__(parent)
        self.setModel(model)
        self.setItemDelegate(PluginDelegate(self))
        self.setRootIsDecorated(False)
        self.setUniformRowHeights(True)
        self.setAlternatingRowColors(False)
        self.setMouseTracking(True)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)

        # Same Tk-style column resize as the modlist (boundary drag, fill-width,
        # no overflow). Plugin Name (col 0) is the fill column.
        h = TkStyleHeader(self, COL_MINS, COL_DEFAULTS)
        self.setHeader(h)
        h.setMinimumSectionSize(min(COL_MINS.values()))
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        for col, w in COL_DEFAULTS.items():
            self.setColumnWidth(col, w)

    def showEvent(self, event):
        super().showEvent(event)
        self._fit_name_to_width()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit_name_to_width()

    def _fit_name_to_width(self):
        vp = self.viewport().width()
        if vp <= 0:
            return
        from gui_qt.plugin_model import COLUMNS
        others = sum(self.columnWidth(c) for c in range(len(COLUMNS))
                     if c != COL_NAME and not self.isColumnHidden(c))
        target = vp - others
        h = self.header()
        if target >= NAME_MIN:
            if target != self.columnWidth(COL_NAME):
                h.resizeSection(COL_NAME, target)
            return
        h.resizeSection(COL_NAME, NAME_MIN)
        deficit = (NAME_MIN + others) - vp
        for c in reversed([c for c in range(len(COLUMNS))
                           if c != COL_NAME and not self.isColumnHidden(c)]):
            if deficit <= 0:
                break
            room = self.columnWidth(c) - COL_MINS.get(c, 40)
            if room <= 0:
                continue
            take = min(room, deficit)
            h.resizeSection(c, self.columnWidth(c) - take)
            deficit -= take
