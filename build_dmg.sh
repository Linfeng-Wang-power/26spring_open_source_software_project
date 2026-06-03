#!/usr/bin/env bash
# build_dmg.sh — Package Lumen into a macOS DMG
#
# 构建流程：
#   1. 创建独立 venv（隔离 conda 环境干扰）
#   2. 安装所有依赖 + setuptools + PyInstaller
#   3. PyInstaller 打包成 Lumen.app
#   4. hdiutil 压缩成 Lumen.dmg
#
# Usage:
#   chmod +x build_dmg.sh
#   ./build_dmg.sh
#
# Output: dist/Lumen.dmg

set -euo pipefail

APP_NAME="Lumen"
ENTRY="mercury_gui.py"
DMG_OUT="dist/${APP_NAME}.dmg"
STAGING_DIR="dist/dmg_staging"
VENV_DIR=".venv_build"

# ---------------------------------------------------------------------------
# 0. 创建隔离 venv
# ---------------------------------------------------------------------------
SYSTEM_PYTHON=$(command -v python3.11 || command -v python3.12 || command -v python3.13 || command -v python3)
echo "→ 使用 Python：${SYSTEM_PYTHON} ($(${SYSTEM_PYTHON} --version))"

if [ ! -d "${VENV_DIR}" ]; then
    echo "→ 创建构建用 venv：${VENV_DIR}"
    "${SYSTEM_PYTHON}" -m venv "${VENV_DIR}"
fi

VENV_PY="${VENV_DIR}/bin/python"
VENV_PIP="${VENV_DIR}/bin/pip"
BUILD_TOOLS_DIR=".build_tools"

mkdir -p "${BUILD_TOOLS_DIR}"
if command -v arm64-apple-darwin20.0.0-lipo >/dev/null 2>&1; then
    cat > "${BUILD_TOOLS_DIR}/lipo" <<'EOF'
#!/usr/bin/env bash
exec arm64-apple-darwin20.0.0-lipo "$@"
EOF
    chmod +x "${BUILD_TOOLS_DIR}/lipo"
fi
if command -v arm64-apple-darwin20.0.0-install_name_tool >/dev/null 2>&1; then
    cat > "${BUILD_TOOLS_DIR}/install_name_tool" <<'EOF'
#!/usr/bin/env bash
exec arm64-apple-darwin20.0.0-install_name_tool "$@"
EOF
    chmod +x "${BUILD_TOOLS_DIR}/install_name_tool"
fi
export PATH="${PWD}/${BUILD_TOOLS_DIR}:${PATH}"

# ---------------------------------------------------------------------------
# 1. 安装依赖
#    setuptools 需要显式安装：Python 3.12+ 的 venv 不再自动包含它，
#    但 yoyo-migrations 在运行时依赖 pkg_resources（setuptools 提供）。
# ---------------------------------------------------------------------------
echo "→ 安装依赖…"
"${VENV_PIP}" install --quiet --upgrade pip
"${VENV_PIP}" install --quiet "setuptools<71"     # yoyo 依赖 pkg_resources；setuptools 71+ 移除了它
"${VENV_PIP}" install --quiet -r requirements.txt
"${VENV_PIP}" install --quiet pyinstaller

echo "✓ PySide6：$(${VENV_PY} -c 'import PySide6; print(PySide6.__version__)')"
echo "✓ pkg_resources：$(${VENV_PY} -c 'import pkg_resources; print(1)')"

# ---------------------------------------------------------------------------
# 2. 清理上次构建
# ---------------------------------------------------------------------------
echo "→ 清理上次构建…"
rm -rf build dist "${APP_NAME}.spec" || true

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
    --collect-all "setuptools" \
    --collect-all "yoyo" \
    --collect-all "importlib_metadata" \
    --copy-metadata "yoyo-migrations" \
    --hidden-import "yoyo" \
    --hidden-import "yoyo.backends" \
    --hidden-import "yoyo.backends.base" \
    --hidden-import "yoyo.internalmigrations" \
    --hidden-import "readability" \
    --hidden-import "bs4" \
    "${ENTRY}"

APP_BUNDLE="dist/${APP_NAME}.app"

if [ ! -d "${APP_BUNDLE}" ]; then
    echo "✗ PyInstaller 未生成 ${APP_BUNDLE}"
    exit 1
fi

# ---------------------------------------------------------------------------
# 4. 冒烟测试
#    --windowed 模式下输出不走终端，用非 windowed 的同名二进制测试
# ---------------------------------------------------------------------------
echo "→ 冒烟测试…"
SMOKE=$("${VENV_PY}" -c '
import subprocess
import sys
try:
    proc = subprocess.Popen([sys.argv[1]], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        out, _ = proc.communicate(timeout=8)
    except subprocess.TimeoutExpired:
        proc.terminate()
        out, _ = proc.communicate(timeout=3)
        out = out or ""
    print(out, end="")
except Exception as exc:
    print(exc)
' "${APP_BUNDLE}/Contents/MacOS/${APP_NAME}" || true)
if echo "${SMOKE}" | grep -qiE "ModuleNotFoundError|ImportError|No module named|未安装"; then
    echo "✗ 启动失败："
    echo "${SMOKE}"
    exit 1
fi
echo "✓ 冒烟测试通过"

# ---------------------------------------------------------------------------
# 5. 制作 DMG
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

echo ""
echo "✓ 完成：${DMG_OUT}  ($(du -sh "${DMG_OUT}" | cut -f1))"
