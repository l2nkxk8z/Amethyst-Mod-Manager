"""Theme editor — a full-screen tab for authoring custom colour themes.

Opened from Settings ▸ User Interface ("Edit / Create Theme…") via
``app._open_theme_editor_tab`` → ``DetachableTabWidget.open_tab(..., key=
"theme_editor")``. The user picks a "Start from" theme (any built-in or existing
custom theme), edits colours grouped by role, and saves the result as a JSON
theme in ``<config>/themes/`` (see ``Utils.custom_themes``). Saving selects the
new theme as the active ``appearance_mode``.

Grouping + derivation come from ``theme_editor_groups``: editing a *base* colour
(e.g. ``BTN_CANCEL``) recomputes its variants (``BTN_CANCEL_HOV``) automatically
unless "Advanced" is ticked, which reveals and unlocks every individual key.

There is no live preview: ~72 widgets snapshot the palette at build time and set
inline stylesheets, so a partial live re-style looked broken (some elements
updated, others didn't). Instead the theme is applied on a full app restart —
the top bar has a **Restart to apply** button, and Save offers the same. The
swatches in the editor always reflect the working palette so the user can still
see their choices before committing.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QScrollArea, QFrame,
    QLabel, QComboBox, QPushButton, QCheckBox, QGroupBox,
)

from gui_qt.theme_qt import active_palette, _c
from gui_qt.color_picker_overlay import ColorPickerOverlay
from gui_qt.confirm_overlay import ConfirmOverlay
from gui_qt.wheel_guard import no_wheel
from gui_qt import theme_editor_groups as teg
from Utils.themes import load_palettes, load_display_names, get_ctk_appearance
from Utils import custom_themes as ct
from Utils import ui_config as uc


class ThemeEditorView(QWidget):
    _SWATCH_W = 130

    def __init__(self, window):
        super().__init__()
        self._window = window
        self._pal = active_palette()            # for styling THIS view
        self.setObjectName("ThemeEditorView")

        # Working state -----------------------------------------------------
        self._palettes = load_palettes()
        self._names = load_display_names()
        self._advanced = False
        # id of the theme currently being edited (None until Save As on a
        # built-in; a custom id once loaded/saved) — controls Save vs Save As.
        self._editing_id: str | None = None
        self._working: dict = {}                 # palette being edited
        self._swatches: dict[str, QPushButton] = {}
        self._dirty = False                      # unsaved edits since last save

        # UI ----------------------------------------------------------------
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.setStyleSheet(self._qss())

        outer.addWidget(self._build_top_bar())

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        outer.addWidget(self._scroll, 1)

        # Seed from the current active theme.
        start_id = uc.get_appearance_mode() or "dark"
        if start_id not in self._palettes:
            start_id = "dark" if "dark" in self._palettes else next(
                iter(self._palettes), "dark")
        self._load_theme(start_id)

    # ---- styling ----------------------------------------------------------
    def _qss(self) -> str:
        c = lambda k: _c(self._pal, k)
        return f"""
        #ThemeEditorView {{ background:{c('BG_DEEP')}; }}
        QLabel {{ color:{c('TEXT_MAIN')}; }}
        QGroupBox {{
            color:{c('TEXT_MAIN')}; border:1px solid {c('BORDER')};
            border-radius:6px; margin-top:14px; font-weight:600;
        }}
        QGroupBox::title {{
            subcontrol-origin:margin; left:10px; padding:0 4px;
        }}
        #ThemeTopBar {{ background:{c('BG_HEADER')};
            border-bottom:1px solid {c('BORDER')}; }}
        QComboBox, QLineEdit {{
            background:{c('BG_ENTRY')}; color:{c('TEXT_MAIN')};
            border:1px solid {c('BORDER')}; border-radius:4px; padding:3px 6px;
        }}
        """

    # ---- top bar ----------------------------------------------------------
    def _build_top_bar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("ThemeTopBar")
        h = QHBoxLayout(bar)
        h.setContentsMargins(14, 10, 14, 10)
        h.setSpacing(10)

        title = QLabel(self.tr("Theme Editor"))
        f = title.font(); f.setPointSize(f.pointSize() + 3); f.setBold(True)
        title.setFont(f)
        h.addWidget(title)

        h.addSpacing(12)
        h.addWidget(QLabel(self.tr("Start from:")))
        self._start_combo = QComboBox()
        no_wheel(self._start_combo)
        for tid, disp in self._names.items():
            self._start_combo.addItem(disp, tid)
        self._start_combo.activated.connect(self._on_start_changed)
        h.addWidget(self._start_combo)

        self._advanced_cb = QCheckBox(self.tr("Advanced (show all colours)"))
        self._advanced_cb.toggled.connect(self._on_advanced_toggled)
        h.addWidget(self._advanced_cb)

        h.addStretch(1)

        self._save_btn = QPushButton(self.tr("Save"))
        self._save_btn.setObjectName("PrimaryButton")
        self._save_btn.setCursor(Qt.PointingHandCursor)
        self._save_btn.clicked.connect(lambda: self._save(save_as=False))
        h.addWidget(self._save_btn)

        save_as = QPushButton(self.tr("Save As…"))
        save_as.setObjectName("FormButton")
        save_as.setCursor(Qt.PointingHandCursor)
        save_as.clicked.connect(lambda: self._save(save_as=True))
        h.addWidget(save_as)

        self._delete_btn = QPushButton(self.tr("Delete"))
        self._delete_btn.setObjectName("FormButton")
        self._delete_btn.setCursor(Qt.PointingHandCursor)
        self._delete_btn.clicked.connect(self._delete)
        h.addWidget(self._delete_btn)

        # Applying a theme touches ~72 widgets that cache their colours at build
        # time, so it's applied by a full restart rather than a partial live
        # re-style. This button saves (if needed) then restarts.
        self._restart_btn = QPushButton(self.tr("Restart to apply"))
        self._restart_btn.setObjectName("PrimaryButton")
        self._restart_btn.setCursor(Qt.PointingHandCursor)
        self._restart_btn.clicked.connect(self._restart_to_apply)
        h.addWidget(self._restart_btn)

        close = QPushButton(self.tr("✕ Close"))
        close.setObjectName("FormButton")
        close.setCursor(Qt.PointingHandCursor)
        close.clicked.connect(self._close_tab)
        h.addWidget(close)

        return bar

    # ---- body -------------------------------------------------------------
    def _load_theme(self, theme_id: str):
        """Seed the working palette from *theme_id* and rebuild the swatch grid."""
        base = self._palettes.get(theme_id, {})
        self._working = {k: v for k, v in base.items()}
        self._editing_id = theme_id if ct.is_custom_theme(theme_id) else None
        # keep the combo in sync
        idx = self._start_combo.findData(theme_id)
        if idx >= 0:
            self._start_combo.setCurrentIndex(idx)
        self._delete_btn.setVisible(ct.is_custom_theme(theme_id))
        self._save_btn.setText(self.tr("Save") if self._editing_id
                               else self.tr("Save As New…"))
        self._dirty = False
        self._rebuild_body()

    def _rebuild_body(self):
        body = QWidget()
        v = QVBoxLayout(body)
        v.setContentsMargins(16, 12, 16, 24)
        v.setSpacing(14)

        note = QLabel(self.tr(
            "Editing a base colour adjusts its hover/variants automatically. "
            "Tick Advanced to edit every colour individually. Use \"Restart to "
            "apply\" to save your theme and see it across the whole app."))
        note.setWordWrap(True)
        note.setStyleSheet(f"color:{_c(self._pal, 'TEXT_DIM')};")
        v.addWidget(note)

        self._swatches.clear()
        for title, keys in teg.grouped_for_palette(self._working):
            visible_keys = [(k, lbl) for k, lbl in keys
                            if self._advanced or k not in teg.DERIVED_KEYS]
            if not visible_keys:
                continue
            box = QGroupBox(title)
            grid = QGridLayout(box)
            grid.setContentsMargins(12, 8, 12, 12)
            grid.setHorizontalSpacing(12)
            grid.setVerticalSpacing(6)
            for row, (key, label) in enumerate(visible_keys):
                grid.addWidget(QLabel(label), row, 0)
                grid.addWidget(self._make_swatch(key), row, 1, Qt.AlignLeft)
            grid.setColumnStretch(2, 1)
            v.addWidget(box)

        v.addStretch(1)
        self._scroll.setWidget(body)

    def _make_swatch(self, key: str) -> QPushButton:
        btn = QPushButton()
        btn.setFixedWidth(self._SWATCH_W)
        btn.setCursor(Qt.PointingHandCursor)
        self._swatches[key] = btn
        self._paint_swatch(key)
        btn.clicked.connect(lambda _=False, k=key: self._pick_color(k))
        return btn

    def _paint_swatch(self, key: str):
        btn = self._swatches.get(key)
        if btn is None:
            return
        hexval = str(self._working.get(key, "#000000"))
        # readable text colour on the swatch
        rgb = teg._rgb(hexval) or (0, 0, 0)
        lum = 0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]
        fg = "#000000" if lum > 140 else "#ffffff"
        btn.setText(hexval)
        btn.setStyleSheet(
            f"QPushButton{{background:{hexval}; color:{fg};"
            f" border:1px solid {_c(self._pal,'BORDER')}; border-radius:4px;"
            f" padding:4px; font-family:monospace;}}")

    # ---- editing ----------------------------------------------------------
    def _pick_color(self, key: str):
        initial = QColor(str(self._working.get(key, "#000000")))
        ColorPickerOverlay.show_over(
            self, self.tr("Pick colour: {0}").format(key), initial,
            lambda col, k=key: self._on_color_picked(k, col))

    def _on_color_picked(self, key: str, color):
        if color is None or not color.isValid():
            return
        hexval = color.name()  # #rrggbb
        if self._advanced:
            self._working[key] = hexval
            self._paint_swatch(key)
        else:
            for k, v in teg.derive(key, hexval).items():
                self._working[k] = v
                self._paint_swatch(k)
        self._dirty = True

    def _on_advanced_toggled(self, on: bool):
        self._advanced = bool(on)
        self._rebuild_body()

    def _on_start_changed(self, idx: int):
        tid = self._start_combo.itemData(idx)
        if tid:
            self._load_theme(tid)

    # ---- save / delete ----------------------------------------------------
    def _save(self, save_as: bool, then_restart: bool = False):
        if not save_as and self._editing_id:
            self._do_save(self._editing_id,
                          self._names.get(self._editing_id, "Theme"),
                          then_restart=then_restart)
            return
        # Save As (or a first save on a built-in): ask for a name.
        from gui_qt.text_input_overlay import TextInputOverlay
        suggestion = self._names.get(self._start_combo.currentData(), "My Theme")
        TextInputOverlay.show_over(
            self, self.tr("Save Theme"), self.tr("Theme name:"),
            lambda name: self._on_name_entered(name, then_restart),
            initial=suggestion, ok_label=self.tr("Save"))

    def _on_name_entered(self, name, then_restart: bool = False):
        if not name or not name.strip():
            return
        self._do_save(None, name.strip(), then_restart=then_restart)

    def _do_save(self, theme_id, name, then_restart: bool = False,
                 overwrite: bool = False) -> str | None:
        # Base clone from the palette we started from guarantees a full key set.
        start_id = self._start_combo.currentData() or "dark"
        base = self._palettes.get(start_id, {})
        appearance = get_ctk_appearance(start_id)
        try:
            new_id = ct.save_custom_theme(
                name, self._working, ctk_appearance=appearance,
                base_palette=base, theme_id=theme_id, overwrite=overwrite)
        except Exception as exc:
            ConfirmOverlay.show_message(
                self, self.tr("Save failed"), str(exc))
            return None
        # Refresh discovery so the new theme is selectable everywhere.
        self._palettes = load_palettes()
        self._names = load_display_names()
        self._editing_id = new_id
        self._dirty = False
        # Make the saved theme the active one (applied on next launch).
        try:
            uc.save_appearance_mode(new_id)
        except Exception:
            pass
        self._refresh_start_combo(new_id)
        self._delete_btn.setVisible(True)
        self._save_btn.setText(self.tr("Save"))
        if then_restart:
            self._request_restart()
        return new_id

    def _restart_to_apply(self):
        """Apply the palette CURRENTLY on screen and restart — no name prompt.

        Whatever colours are shown are written verbatim and made the active
        theme, so "Restart to apply" always applies exactly what you're editing:
          * editing an existing custom theme  → overwrite it in place;
          * a pristine custom theme selected  → just re-select + restart;
          * editing a built-in (or unsaved)   → write to an auto-named custom
            theme (e.g. "Dark (edited)") so the on-screen palette applies as-is
            and stays re-editable. Use Save As to give it a different name.
        """
        # Pristine existing custom theme: nothing to write, just select it.
        if self._editing_id is not None and not self._dirty:
            try:
                uc.save_appearance_mode(self._editing_id)
            except Exception:
                pass
            self._request_restart()
            return

        # Editing an existing custom theme: overwrite it in place.
        if self._editing_id is not None:
            self._do_save(self._editing_id,
                          self._names.get(self._editing_id, "Theme"),
                          then_restart=True)
            return

        # Editing a built-in / unsaved: apply verbatim to an auto-named theme,
        # overwriting a prior auto-theme of the same name in place.
        start_id = self._start_combo.currentData() or "dark"
        base_name = self._names.get(start_id, "Custom")
        self._do_save(None, self.tr("{0} (edited)").format(base_name),
                      then_restart=True, overwrite=True)

    def _request_restart(self):
        fn = getattr(self._window, "_request_restart", None)
        if callable(fn):
            fn()

    def _refresh_start_combo(self, select_id):
        self._start_combo.blockSignals(True)
        self._start_combo.clear()
        for tid, disp in self._names.items():
            self._start_combo.addItem(disp, tid)
        idx = self._start_combo.findData(select_id)
        if idx >= 0:
            self._start_combo.setCurrentIndex(idx)
        self._start_combo.blockSignals(False)

    def _delete(self):
        tid = self._editing_id
        if not tid or not ct.is_custom_theme(tid):
            return
        name = self._names.get(tid, tid)
        ConfirmOverlay.show_over(
            self, self.tr("Delete theme?"),
            self.tr("Delete the custom theme \"{0}\"? This cannot be undone.")
                .format(name),
            lambda ok: self._do_delete(tid) if ok else None,
            confirm_label=self.tr("Delete"), danger=True)

    def _do_delete(self, tid):
        ct.delete_custom_theme(tid)
        # If the deleted theme was active, fall back to dark.
        try:
            if uc.get_appearance_mode() == tid:
                uc.save_appearance_mode("dark")
        except Exception:
            pass
        self._palettes = load_palettes()
        self._names = load_display_names()
        self._refresh_start_combo("dark")
        self._load_theme("dark" if "dark" in self._palettes
                         else next(iter(self._palettes), "dark"))

    # ---- lifecycle --------------------------------------------------------
    def _close_tab(self):
        tabs = getattr(self._window, "_tabs", None)
        if tabs is not None:
            try:
                tabs.close_tab("theme_editor")
                return
            except Exception:
                pass
        self.hide()
