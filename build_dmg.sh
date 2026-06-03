#!/usr/bin/env bash
# build_dmg.sh — Package Mercury into a macOS DMG
#
# Usage:
#   chmod +x build_dmg.sh
#   ./build_dmg.sh
#
# Requirements (installed automatically if missing):
#   pip install pyinstaller
#
# Output:
#   dist/Mercury.dmg

set -euo pipefail

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
APP_NAME="Mercury"
ENTRY="mercury_gui.py"
DMG_OUT="dist/${APP_NAME}.dmg"
VOLUME_NAME="${APP_NAME}"
BUILD_DIR="build"
DIST_DIR="dist"
STAGING_DIR="dist/dmg_staging"

# ---------------------------------------------------------------------------
# 0. Ensure PyInstaller is available
# ---------------------------------------------------------------------------
if ! python -m PyInstaller --version &>/dev/null; then
    echo "→ Installing PyInstaller…"
    pip install pyinstaller --quiet
fi

# ---------------------------------------------------------------------------
# 1. Clean previous build artifacts
# ---------------------------------------------------------------------------
echo "→ Cleaning previous build…"
rm -rf "${BUILD_DIR}" "${DIST_DIR}" "${APP_NAME}.spec"

# ---------------------------------------------------------------------------
# 2. PyInstaller: freeze the app into a .app bundle
# ---------------------------------------------------------------------------
echo "→ Running PyInstaller…"
python -m PyInstaller \
    --name "${APP_NAME}" \
    --windowed \
    --noconfirm \
    --clean \
    --add-data "migrations:migrations" \
    --add-data "reader:reader" \
    --hidden-import "yoyo" \
    --hidden-import "yoyo.backends" \
    --hidden-import "yoyo.backends.base" \
    --hidden-import "yoyo.backends.sqlite" \
    --hidden-import "readability" \
    --hidden-import "bs4" \
    --collect-all "PySide6" \
    "${ENTRY}"

APP_BUNDLE="${DIST_DIR}/${APP_NAME}.app"

if [ ! -d "${APP_BUNDLE}" ]; then
    echo "✗ PyInstaller did not produce ${APP_BUNDLE}"
    exit 1
fi

echo "✓ App bundle: ${APP_BUNDLE}"

# ---------------------------------------------------------------------------
# 3. Prepare DMG staging folder
# ---------------------------------------------------------------------------
echo "→ Preparing DMG staging area…"
rm -rf "${STAGING_DIR}"
mkdir -p "${STAGING_DIR}"

# Copy .app into staging
cp -R "${APP_BUNDLE}" "${STAGING_DIR}/"

# Create an Applications symlink so users can drag-and-drop to install
ln -s /Applications "${STAGING_DIR}/Applications"

# ---------------------------------------------------------------------------
# 4. Build DMG with hdiutil (macOS built-in)
# ---------------------------------------------------------------------------
echo "→ Building DMG…"
rm -f "${DMG_OUT}"

hdiutil create \
    -volname "${VOLUME_NAME}" \
    -srcfolder "${STAGING_DIR}" \
    -ov \
    -format UDZO \
    -imagekey zlib-level=9 \
    "${DMG_OUT}"

# ---------------------------------------------------------------------------
# 5. Clean up staging
# ---------------------------------------------------------------------------
rm -rf "${STAGING_DIR}"

echo ""
echo "✓ Done: ${DMG_OUT}"
echo "  Size: $(du -sh "${DMG_OUT}" | cut -f1)"
