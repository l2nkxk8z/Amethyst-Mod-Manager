"""Qt theming — builds a QSS stylesheet from the existing theme palettes.

The palette data in ``gui/themes/*.py`` is plain ``{KEY: "#hex"}`` dicts
(toolkit-neutral), so the Qt app reuses it directly rather than duplicating
colours. Per-theme overrides flow through the same ``THEME_DEFAULTS_OVERRIDE``
mechanism the Tk app uses.
"""

from __future__ import annotations

from gui.themes import load_palettes
from Utils.ui_config import get_appearance_mode


# Fallback used if a palette is missing a key, so QSS never renders with an
# empty colour string.
_FALLBACK = "#1a1a1a"


def active_palette() -> dict[str, str]:
    """Return the {KEY: hex} palette for the user's current appearance mode."""
    palettes = load_palettes()
    mode = get_appearance_mode()
    return palettes.get(mode) or palettes.get("dark") or next(iter(palettes.values()), {})


def _c(pal: dict, key: str) -> str:
    val = pal.get(key, _FALLBACK)
    # Palette values may be (light, dark) tuples in some themes; take a string.
    if isinstance(val, (tuple, list)):
        val = val[-1]
    return str(val)


def build_qss(pal: dict | None = None) -> str:
    """Build the application QSS from a palette (default: active palette)."""
    p = pal or active_palette()
    c = lambda k: _c(p, k)
    return f"""
    QWidget {{
        background: {c('BG_DEEP')};
        color: {c('TEXT_MAIN')};
        font-size: 13px;
    }}
    QMainWindow, QDialog {{ background: {c('BG_DEEP')}; }}

    /* Toolbar */
    QToolBar {{
        background: {c('BG_HEADER')};
        border: none;
        spacing: 4px;
        padding: 4px 6px;
    }}
    QToolButton {{
        background: transparent;
        color: {c('TEXT_MAIN')};
        padding: 5px 10px;
        border-radius: 4px;
    }}
    QToolButton:hover {{ background: {c('BG_ROW_HOVER')}; }}
    QToolButton:pressed {{ background: {c('ACCENT')}; color: {c('TEXT_ON_ACCENT')}; }}
    QToolButton::menu-button {{ width: 16px; border-left: 1px solid {c('BORDER')}; }}
    QToolButton::menu-arrow {{ width: 8px; height: 8px; }}

    QMenu {{
        background: {c('BG_PANEL')};
        border: 1px solid {c('BORDER')};
        padding: 5px;
    }}
    QMenu::item {{
        padding: 7px 28px 7px 14px;
        border-radius: 4px;
        margin: 1px 2px;
    }}
    QMenu::item:selected {{ background: {c('BG_SELECT')}; color: {c('TEXT_ON_ACCENT')}; }}
    QMenu::item:checked {{ font-weight: 600; }}
    QMenu::indicator {{ width: 0px; }}  /* hide checkbox box; bold marks current */
    QMenu::separator {{ height: 1px; background: {c('BORDER')}; margin: 5px 8px; }}

    /* List / tree */
    QTreeView, QListView {{
        background: {c('BG_LIST')};
        alternate-background-color: {c('BG_ROW_ALT')};
        border: none;
        outline: none;
    }}
    QTreeView::item:selected, QListView::item:selected {{
        background: {c('BG_SELECT')};
        color: {c('TEXT_ON_ACCENT')};
    }}
    QHeaderView::section {{
        background: {c('BG_HEADER')};
        color: {c('TEXT_DIM')};
        padding: 5px 8px;
        border: none;
        border-right: 1px solid {c('BORDER')};
        border-bottom: 1px solid {c('BORDER')};
    }}

    /* Detachable tabs (overlay replacement) */
    QTabWidget::pane {{ border: none; }}
    QTabBar {{ background: {c('BG_HEADER')}; }}
    QTabBar::tab {{
        background: {c('BG_PANEL')};
        color: {c('TEXT_DIM')};
        padding: 6px 14px;
        border: 1px solid {c('BORDER')};
        border-bottom: none;
        margin-right: 2px;
    }}
    QTabBar::tab:selected {{
        background: {c('BG_DEEP')};
        color: {c('TEXT_MAIN')};
    }}
    QTabBar::tab:hover {{ color: {c('TEXT_MAIN')}; }}
    QTabBar::close-button {{ subcontrol-position: right; }}

    /* Slim modern scrollbars — applied globally (modlist, plugins, log, …) */
    QScrollBar:vertical {{
        background: transparent;
        width: 12px;
        margin: 0;
    }}
    QScrollBar:horizontal {{
        background: transparent;
        height: 12px;
        margin: 0;
    }}
    QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{
        background: {c('BORDER_FAINT')};
        border-radius: 5px;
        min-height: 28px;
        min-width: 28px;
        margin: 2px;
    }}
    QScrollBar::handle:hover {{ background: {c('TEXT_DIM')}; }}
    QScrollBar::add-line, QScrollBar::sub-line {{
        width: 0; height: 0; background: none; border: none;
    }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

    /* Status bar + bottom bar */
    QStatusBar {{
        background: {c('BG_HEADER')};
        color: {c('TEXT_DIM')};
        border-top: 1px solid {c('BORDER')};
    }}
    QStatusBar::item {{ border: none; }}
    #BottomBar {{
        background: {c('BG_PANEL')};
        border-top: 1px solid {c('BORDER')};
    }}

    /* Generic buttons / inputs */
    QPushButton {{
        background: {c('ACCENT')};
        color: {c('TEXT_ON_ACCENT')};
        border: none;
        padding: 6px 12px;
        border-radius: 4px;
    }}
    QPushButton:hover {{ background: {c('ACCENT_HOV')}; }}
    QComboBox, QLineEdit {{
        background: {c('BG_ROW')};
        border: 1px solid {c('BORDER')};
        border-radius: 4px;
        padding: 4px 8px;
    }}
    QSplitter::handle {{ background: {c('BORDER')}; }}
    QSplitter::handle:horizontal {{ width: 2px; }}

    #StatusChip {{
        background: {c('ACCENT')};
        color: {c('TEXT_ON_ACCENT')};
        border-radius: 3px;
        padding: 3px 8px;
    }}
    #PlaceholderPane {{
        background: {c('BG_PANEL')};
        color: {c('TEXT_FAINT')};
    }}

    /* Header bars (left two-tier header + right play bar) */
    #HeaderBar {{
        background: {c('BG_HEADER')};
        border-bottom: 1px solid {c('BORDER')};
    }}
    #GroupSep {{ background: {c('BORDER')}; border: none; }}
    #ActionButton {{
        background: {c('BG_ROW')};
        color: {c('TEXT_MAIN')};
        border: 1px solid {c('BORDER')};
        border-radius: 5px;
        padding: 6px 14px;
        font-size: 14px;
    }}
    #ActionButton:hover {{ background: {c('BG_ROW_HOVER')}; }}
    #ActionButton:pressed {{ background: {c('ACCENT')}; color: {c('TEXT_ON_ACCENT')}; }}
    #FooterButton {{
        background: {c('BG_ROW')};
        color: {c('TEXT_MAIN')};
        border: 1px solid {c('BORDER')};
        border-radius: 4px;
        padding: 4px 12px;
        font-size: 12px;
    }}
    #FooterButton:hover {{ background: {c('BG_ROW_HOVER')}; }}
    #FooterButton:pressed {{ background: {c('ACCENT')}; color: {c('TEXT_ON_ACCENT')}; }}
    #PlayButton {{
        background: {c('BTN_SUCCESS')};
        color: #fff;
        font-weight: 600;
        font-size: 14px;
        padding: 6px 18px;
        border: none;
        border-radius: 5px;
    }}
    #PlayButton:hover {{ background: {c('BTN_SUCCESS')}; }}

    /* Bottom log panel */
    #LogBar {{
        background: {c('BG_HEADER')};
        border-top: 1px solid {c('BORDER')};
    }}
    #LogView {{
        background: {c('BG_DEEP')};
        color: {c('TEXT_MAIN')};
        border: none;
        border-top: 1px solid {c('BORDER')};
        font-family: monospace;
        font-size: 12px;
    }}
    """


def apply_theme(app) -> None:
    """Apply the active palette's QSS to a QApplication."""
    app.setStyleSheet(build_qss())
