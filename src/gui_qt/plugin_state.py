"""Plugin list loading for the Qt Plugins tab.

Produces the ordered, flagged plugin list for the active game/profile by reusing
the backend: Utils.plugins (read_plugins / read_loadorder / write_plugins) and
Utils.plugin_parser (ESL / master header flags). Vanilla plugins are pinned to
the top, then mods follow saved loadorder.txt order.

v1 scope: list + order + enable-toggle + ESL/master flags. The deeper Tk logic
(orphan detection, Data_Core pruning, LOOT messages, bash tags, missing-master
checks) is deferred — the Flags column is structured to receive them later.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from Utils.plugins import read_plugins, read_loadorder, write_plugins, PluginEntry

# Flag bits for the plugin Flags column (drawn left→right in this order).
PF_MISSING = 1 << 0    # missing masters (red warning)
PF_LATE = 1 << 1       # master loads after a dependent (late master)
PF_VMM = 1 << 2        # version-mismatched master
PF_ESL = 1 << 3        # ESL / light-flagged
PF_LOOT = 1 << 4       # LOOT masterlist messages/requirements/incompatibilities
PF_DIRTY = 1 << 5      # dirty edits (needs cleaning)
PF_TAGS = 1 << 6       # bash tags
PF_MASTER = 1 << 7     # master (.esm or master-flagged)


@dataclass
class PluginRow:
    name: str
    enabled: bool
    flags: int = 0
    vanilla: bool = False


_EXT_ORDER = {".esm": 0, ".esp": 1, ".esl": 2}


def plugins_path(game, profile: str) -> Path | None:
    if game is None or not profile:
        return None
    return game.get_profile_root() / "profiles" / profile / "plugins.txt"


def load_plugins(game, profile: str) -> list[PluginRow]:
    """Return the ordered plugin rows for *game*/*profile*, or [] if none."""
    p = plugins_path(game, profile)
    if p is None or not p.is_file():
        return []
    star = getattr(game, "plugins_use_star_prefix", True)
    entries = read_plugins(p, star_prefix=star)
    saved_order = read_loadorder(p.parent / "loadorder.txt")

    # Full vanilla set: base + DLC + Creation Club (.ccc), filtered to files
    # present in Data — same resolver the Tk app uses.
    try:
        from gui.game_helpers import _vanilla_plugins_for_game
        vanilla = _vanilla_plugins_for_game(game)
    except Exception:
        vanilla = {n.lower(): n for n in getattr(game, "vanilla_plugins", [])}
    mod_map = {e.name.lower(): e for e in entries}

    ordered: list[PluginEntry] = []
    seen: set[str] = set()

    # Vanilla pinned first (in saved order where known, else ext-sorted).
    for name in saved_order:
        low = name.lower()
        if low in seen:
            continue
        if low in vanilla:
            ordered.append(PluginEntry(vanilla[low], True)); seen.add(low)
    for low, orig in sorted(vanilla.items(),
                            key=lambda kv: (_EXT_ORDER.get(Path(kv[0]).suffix, 9), kv[0])):
        if low not in seen:
            ordered.append(PluginEntry(orig, True)); seen.add(low)

    # Mods in saved loadorder order, then any leftovers from plugins.txt.
    for name in saved_order:
        low = name.lower()
        if low in seen:
            continue
        if low in mod_map:
            ordered.append(mod_map[low]); seen.add(low)
    for e in entries:
        if e.name.lower() not in seen:
            ordered.append(e); seen.add(e.name.lower())

    data_dir = (game.get_vanilla_plugins_path()
                if hasattr(game, "get_vanilla_plugins_path") else None)
    rows = [_to_row(e, vanilla, data_dir) for e in ordered]
    _apply_master_checks(rows, data_dir)
    _apply_loot_flags(rows, p.parent)
    return rows


def _to_row(e: PluginEntry, vanilla: dict, data_dir: Path | None) -> PluginRow:
    low = e.name.lower()
    flags = 0
    path = (data_dir / e.name) if data_dir else None
    if path and path.is_file():
        try:
            from Utils.plugin_parser import is_esl_flagged, is_master_flagged
            if is_esl_flagged(path) or low.endswith(".esl"):
                flags |= PF_ESL
            if is_master_flagged(path) or low.endswith(".esm"):
                flags |= PF_MASTER
        except Exception:
            if low.endswith(".esl"):
                flags |= PF_ESL
            if low.endswith(".esm"):
                flags |= PF_MASTER
    else:
        if low.endswith(".esl"):
            flags |= PF_ESL
        if low.endswith(".esm"):
            flags |= PF_MASTER
    return PluginRow(e.name, e.enabled, flags, low in vanilla)


def _apply_master_checks(rows: list[PluginRow], data_dir: Path | None) -> None:
    """Flag missing / late / version-mismatched masters using the deployed
    plugin files in the Data dir."""
    if data_dir is None or not data_dir.is_dir():
        return
    names = [r.name for r in rows]
    paths = {r.name: data_dir / r.name for r in rows}
    try:
        from Utils.plugin_parser import (
            check_missing_masters, check_late_masters,
            check_version_mismatched_masters)
        missing = check_missing_masters(names, paths)
        late = check_late_masters(names, paths)
        vmm = check_version_mismatched_masters(names, paths, data_dir)
    except Exception:
        return
    for r in rows:
        if missing.get(r.name):
            r.flags |= PF_MISSING
        if late.get(r.name):
            r.flags |= PF_LATE
        if vmm.get(r.name):
            r.flags |= PF_VMM


def _apply_loot_flags(rows: list[PluginRow], profile_dir: Path) -> None:
    """Flag LOOT messages / dirty edits / bash tags from the cached loot.json."""
    try:
        from LOOT.loot_sorter import read_loot_info
        data = read_loot_info(profile_dir)
    except Exception:
        return
    plugins = data.get("plugins", {}) if isinstance(data, dict) else {}
    version = data.get("version", 1) if isinstance(data, dict) else 1
    info: dict[str, dict] = {}
    if version >= 2:
        info = {k.lower(): v for k, v in plugins.items() if isinstance(v, dict) and v}
    else:
        info = {k.lower(): {"messages": v} for k, v in plugins.items()
                if isinstance(v, list) and v}
    for r in rows:
        d = info.get(r.name.lower())
        if not d:
            continue
        if d.get("messages") or d.get("requirements") or d.get("incompatibilities"):
            r.flags |= PF_LOOT
        if d.get("dirty"):
            r.flags |= PF_DIRTY
        if d.get("tags"):
            r.flags |= PF_TAGS


def save_plugins(game, profile: str, rows: list[PluginRow]) -> None:
    """Write enable/disable state back to plugins.txt (order preserved)."""
    p = plugins_path(game, profile)
    if p is None:
        return
    star = getattr(game, "plugins_use_star_prefix", True)
    entries = [PluginEntry(r.name, r.enabled) for r in rows]
    write_plugins(p, entries, star_prefix=star)
