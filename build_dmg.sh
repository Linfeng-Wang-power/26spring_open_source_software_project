#!/usr/bin/env bash
# build_dmg.sh — Package Mercury into a macOS DMG
#
# 构建流程：
#   1. 创建独立 venv（隔离系统 Python，避免 conda 环境干扰）
#   2. 安装所有依赖 + PyInstaller
#   3. PyInstaller 打包成 Mercury.app
#   4. hdiutil 压缩成 Mercury.dmg
#
# Usage:
#   chmod +x build_dmg.sh
#   ./build_dmg.sh
#
# Output: dist/Mercury.dmg

set -euo pipefail

APP_NAME="Mercury"
ENTRY="mercury_gui.py"
DMG_OUT="dist/${APP_NAME}.dmg"
STAGING_DIR="dist/dmg_staging"
VENV_DIR=".venv_build"

# ---------------------------------------------------------------------------
# 0. 用系统 python3 创建隔离 venv（跳过 conda）
# ---------------------------------------------------------------------------
SYSTEM_PYTHON=$(command -v python3.11 || command -v python3.12 || command -v python3.13 || command -v python3)

echo "→ 使用 Python：${SYSTEM_PYTHON} ($(${SYSTEM_PYTHON} --version))"
echo "→ 创建构建用 venv：${VENV_DIR}"

if [ ! -d "${VENV_DIR}" ]; then
    "${SYSTEM_PYTHON}" -m venv "${VENV_DIR}"
fi

VENV_PY="${VENV_DIR}/bin/python"
VENV_PIP="${VENV_DIR}/bin/pip"

# ---------------------------------------------------------------------------
# 1. 安装依赖
# ---------------------------------------------------------------------------
echo "→ 安装 requirements.txt…"
"${VENV_PIP}" install --quiet --upgrade pip
"${VENV_PIP}" install --quiet -r requirements.txt
"${VENV_PIP}" install --quiet pyinstaller

echo "✓ PySide6 路径：$(${VENV_PY} -c 'import PySide6, os; print(os.path.dirname(PySide6.__file__))')"

# ---------------------------------------------------------------------------
# 2. 清理上次构建
# ---------------------------------------------------------------------------
echo "→ 清理上次构建产物…"
rm -rf build dist "${APP_NAME}.spec" 2>/dev/null || true

# ---------------------------------------------------------------------------
# 3. PyInstaller 打包
# ---------------------------------------------------------------------------
echo "→ 运行 PyInstaller…"
"${VENV_PY}" -m PyInstaller \
    --name "${APP_NAME}" \
    --windowed \
    --noconfirm \
    --clean \
    --add-data "migrations:migrations" \
    --add-data "reader:reader" \
    --hidden-import "pkg_resources" \
    --hidden-import "yoyo" \
    --hidden-import "yoyo.backends" \
    --hidden-import "yoyo.backends.base" \
    --hidden-import "yoyo.backends.sqlite" \
    --hidden-import "readability" \
    --hidden-import "bs4" \
    --collect-all "PySide6" \
    "${ENTRY}"

APP_BUNDLE="dist/${APP_NAME}.app"

if [ ! -d "${APP_BUNDLE}" ]; then
    echo "✗ PyInstaller 未生成 ${APP_BUNDLE}"
    exit 1
fi

# 快速冒烟测试：直接跑二进制，最多等 5 秒
echo "→ 冒烟测试（5 秒超时）…"
BINARY="${APP_BUNDLE}/Contents/MacOS/${APP_NAME}"
SMOKE=$(timeout 5 "${BINARY}" 2>&1 || true)
if echo "${SMOKE}" | grep -q "未安装\|ModuleNotFoundError\|ImportError"; then
    echo "✗ 启动失败，错误输出："
    echo "${SMOKE}"
    exit 1
fi
echo "✓ App bundle 启动正常"

# ---------------------------------------------------------------------------
# 4. 制作 DMG
# ---------------------------------------------------------------------------
echo "→ 打包 DMG…"
rm -rf "${STAGING_DIR}"
mkdir -p "${STAGING_DIR}"
cp -R "${APP_BUNDLE}" "${STAGING_DIR}/"
ln -s /Applications "${STAGING_DIR}/Applications"

rm -f "${DMG_OUT}"
hdiutil create \
    -volname "${APP_NAME}" \
    -srcfolder "${STAGING_DIR}" \
    -ov \
    -format UDZO \
    -imagekey zlib-level=9 \
    "${DMG_OUT}"

rm -rf "${STAGING_DIR}"

# ---------------------------------------------------------------------------
# 完成
# ---------------------------------------------------------------------------
echo ""
echo "✓ 完成：${DMG_OUT}"
echo "  大小：$(du -sh "${DMG_OUT}" | cut -f1)"
