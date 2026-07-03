#!/bin/bash
# Build the Amethyst Mod Manager AppImage.
#
# CI-only build path: build a real Arch package via makepkg, install it to
# the host's /usr, then run quick-sharun. quick-sharun's `/usr → "$APPDIR"`
# path-rewriting catches hardcoded paths inside vendored deps that an
# AppDir-staged build would miss.
#
# Runs in the ghcr.io/pkgforge-dev/archlinux container (see
# .github/workflows/build.yml). For local testing, run the manual
# "Test Build" workflow on GitHub and download the artifact instead —
# there is no local staging mode anymore.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"   # = src/
SRC_TREE="$(dirname "$PROJECT_DIR")"     # = repo root

export PATH="$HOME/.local/bin:$PATH"

ARCH=$(uname -m)
VERSION=$(sed -n 's/^__version__ = "\(.*\)"$/\1/p' "${PROJECT_DIR}/version.py")
[ -n "$VERSION" ] || { echo "ERROR: cannot read __version__" >&2; exit 1; }

WORK_DIR="${TMPDIR:-/tmp}/amethyst-mm-build"
OUTPATH="${WORK_DIR}/dist"
APPDIR="${WORK_DIR}/AppDir"
FINAL_OUTPATH="${SCRIPT_DIR}/dist"

# ── Tooling check ────────────────────────────────────────────────────
for tool in quick-sharun cc awk find ldd strings wget makepkg pacman; do
    command -v "$tool" >/dev/null || {
        echo "ERROR: '$tool' not found in PATH" >&2
        exit 1
    }
done

if ! /usr/bin/python3 -c 'import PySide6.QtCore' 2>/dev/null; then
    echo "ERROR: /usr/bin/python3 cannot import PySide6." >&2
    echo "Install the system 'pyside6' package (Arch: pacman -S pyside6)." >&2
    exit 1
fi

# ── Clean ────────────────────────────────────────────────────────────
echo "=== Cleaning previous build ==="
rm -rf "$WORK_DIR" "$FINAL_OUTPATH"
mkdir -p "$APPDIR/bin" "$OUTPATH" "$FINAL_OUTPATH"

# ── Aux staging (bsdtar) ─────────────────────────────────────────────
# 7zzs and zenity-rs are bundled by the PKGBUILD itself. Only bsdtar lives
# here: it would conflict with the libarchive package.
AUX_DIR="${WORK_DIR}/aux"
mkdir -p "$AUX_DIR/bin"

echo "=== Bundling bsdtar ==="
BSDTAR_BIN="$(command -v bsdtar 2>/dev/null || true)"
if [ -n "$BSDTAR_BIN" ]; then
    cp "$BSDTAR_BIN" "$AUX_DIR/bin/bsdtar"
    chmod +x "$AUX_DIR/bin/bsdtar"
fi

# Desktop / icon — quick-sharun reads these via env vars.
ASSETS_DIR="${WORK_DIR}/assets"
mkdir -p "$ASSETS_DIR"
cp "${SCRIPT_DIR}/mod-manager.desktop" "$ASSETS_DIR/mod-manager.desktop"
cp "${SCRIPT_DIR}/mod-manager.png"     "$ASSETS_DIR/mod-manager.png"

# ── Locate the libloot extension (built by the separate CI job or by
# running src/LOOT/rebuild_libloot.sh locally).
LIBLOOT_SO="$(find "${PROJECT_DIR}/LOOT" -maxdepth 1 -name 'loot.cpython-*-x86_64-linux-gnu.so' 2>/dev/null | head -1 || true)"
if [ -z "$LIBLOOT_SO" ]; then
    echo "WARN: no libloot .so found in src/LOOT/ — the AppImage will lack LOOT support" >&2
fi

# ── quick-sharun env ─────────────────────────────────────────────────
# DEPLOY_PYTHON=1   pulls /usr/bin/python3 + stdlib + site-packages (PySide6)
# DEPLOY_QT=1       Qt plugins (platforms/wayland/imageformats/styles/tls).
#                   Auto-detection via traced libQt6Core would fire anyway;
#                   forcing it is cheap insurance.
# ALWAYS_SOFTWARE=1 forces software rendering (matches upstream)
# ANYLINUX_LIB=1    builds anylinux.so (LD_PRELOAD env-scrubber for child procs)
export ARCH VERSION OUTPATH APPDIR
export ICON="${ASSETS_DIR}/mod-manager.png"
export DESKTOP="${ASSETS_DIR}/mod-manager.desktop"
export DEPLOY_PYTHON=1
export DEPLOY_QT=1
export ALWAYS_SOFTWARE=1
export ANYLINUX_LIB=1

# SteamOS strips glibc headers from /usr/include; quick-sharun's anylinux.so
# build needs dlfcn.h. Sysroot at ~/sdk/include works around that.
if [ -f "$HOME/sdk/include/dlfcn.h" ]; then
    export C_INCLUDE_PATH="$HOME/sdk/include${C_INCLUDE_PATH:+:$C_INCLUDE_PATH}"
elif [ ! -f /usr/include/dlfcn.h ]; then
    echo "  NOTE: ~/sdk/include not found and /usr/include/dlfcn.h missing — disabling anylinux.so." >&2
    export ANYLINUX_LIB=0
fi

# ── Build + install the package ──────────────────────────────────────
echo "=== Building amethyst-mod-manager package via makepkg ==="
PKG_BUILD_DIR="${WORK_DIR}/pkgbuild"
mkdir -p "$PKG_BUILD_DIR"
cp "${SCRIPT_DIR}/PKGBUILD" "$PKG_BUILD_DIR/PKGBUILD"

# makepkg refuses to run as root. If we are root, drop to a non-root
# user. The CI workflow creates a 'builder' user with passwordless sudo;
# locally, the script is presumably already non-root.
_makepkg_uid=""
if [ "$(id -u)" = "0" ]; then
    if id builder >/dev/null 2>&1; then
        _makepkg_uid=builder
    else
        echo "ERROR: makepkg cannot run as root; create a 'builder' user first" >&2
        exit 1
    fi
    # The build user needs read access to both the PKGBUILD scratch dir
    # and the source tree (PKGBUILD reads $SRC_TREE/src/version.py and
    # package() copies from there).
    chown -R "$_makepkg_uid":"$_makepkg_uid" "$PKG_BUILD_DIR"
    chmod -R a+rX "$SRC_TREE"
fi

# Pass SRC_TREE / LIBLOOT_SO through the env so the PKGBUILD picks them up.
_libloot_arg=""
[ -n "$LIBLOOT_SO" ] && _libloot_arg="LIBLOOT_SO=$LIBLOOT_SO"
if [ -n "$_makepkg_uid" ]; then
    sudo -u "$_makepkg_uid" \
         env SRC_TREE="$SRC_TREE" $_libloot_arg \
         bash -c "cd '$PKG_BUILD_DIR' && makepkg --noconfirm --nodeps"
else
    ( cd "$PKG_BUILD_DIR" && SRC_TREE="$SRC_TREE" ${_libloot_arg:+env $_libloot_arg} makepkg --noconfirm --nodeps )
fi

PKG_FILE=$(find "$PKG_BUILD_DIR" -maxdepth 1 -name 'amethyst-mod-manager-*.pkg.tar.*' -type f | head -1)
[ -n "$PKG_FILE" ] || { echo "ERROR: makepkg produced no package" >&2; exit 1; }

echo "=== Installing $PKG_FILE ==="
# --overwrite for re-runs that hit the same version; --nodeps because
# we vendor everything pip-installed and depend only on python/pyside6
# which are already present in the container.
pacman -U --noconfirm --overwrite '*' --nodeps "$PKG_FILE"

echo "=== Running quick-sharun ==="
# Stdlib extension modules in lib-dynload are dlopened at runtime, so
# quick-sharun's per-binary ldd trace never sees their DT_NEEDED entries
# and silently drops the underlying libs. Each line below covers a stdlib
# ext we actually import (directly or transitively):
#   libssl/libcrypto -> _ssl.so      (HTTPS — Nexus, GitHub, updates)
#   libuuid          -> _uuid.so     (uuid.uuid4 used by Nexus SSO)
#   libmpdec         -> _decimal.so  (transitive deps may import decimal)
quick-sharun \
    /usr/bin/mod-manager               \
    /usr/share/amethyst-mod-manager    \
    /usr/bin/7zzs                      \
    /usr/bin/zenity                    \
    /usr/lib/libssl.so*                \
    /usr/lib/libcrypto.so*             \
    /usr/lib/libuuid.so*               \
    /usr/lib/libmpdec.so*              \
    $( [ -f "$AUX_DIR/bin/bsdtar" ] && printf %s "$AUX_DIR/bin/bsdtar" )

# Rewrite the wrapper's /usr/share path to "$APPDIR"/share — quick-sharun's
# built-in /usr → "$APPDIR" rewrite only fires for dotnet scripts, so plain
# shell wrappers need this manual step.
sed -i -e 's|/usr/share|"$APPDIR"/share|g' "$APPDIR/bin/mod-manager"

# Strip __pycache__ from our app tree. The PKGBUILD's package() cleans these,
# but Arch's python ALPM hook re-generates .pyc files on `pacman -U`; quick-
# sharun's DEBLOAT_SYS_PYTHON only touches $APPDIR/shared/lib/python*. ~4M.
find "$APPDIR/share/amethyst-mod-manager" -type d -name '__pycache__' \
    -exec rm -rf {} + 2>/dev/null || true

# ── Hicolor icon for AppImageLauncher / appimaged integration ────────
# libappimage resolves Icon=mod-manager via the FreeDesktop spec, i.e.
# usr/share/icons/hicolor/<size>/apps/<name>.png. Without it AppImageLauncher
# logs "no icon to set" and refuses to write a host .desktop file.
# quick-sharun deploys binaries + libs but doesn't propagate icon themes,
# so we install the icon into the AppDir explicitly here.
install -Dm644 "${ASSETS_DIR}/mod-manager.png" \
    "$APPDIR/usr/share/icons/hicolor/256x256/apps/mod-manager.png"

# ── Build the AppImage ───────────────────────────────────────────────
echo "=== Building AppImage ==="
quick-sharun --make-appimage

RAW_OUT=$(find "$OUTPATH" -maxdepth 2 -name '*.AppImage' -type f | head -1)
FINAL="${FINAL_OUTPATH}/AmethystModManager-${VERSION}-${ARCH}.AppImage"
if [ -n "$RAW_OUT" ]; then
    mv "$RAW_OUT" "$FINAL"
fi

echo ""
echo "=== Build complete ==="
[ -f "$FINAL" ] && {
    echo "AppImage: $FINAL"
    echo "Size: $(du -h "$FINAL" | cut -f1)"
}
