#!/bin/sh
# POSIX-compatible installer for pve-storage-info

set -eu

SCRIPT_NAME="pve-storage-info.py"
INSTALL_DIR="/opt/pve-tools"
TARGET_SCRIPT="$INSTALL_DIR/$SCRIPT_NAME"
LINK_NAME="/usr/local/bin/pve-storage-info"

RAW_BASE_URL="https://raw.githubusercontent.com/xoppepop/pve-tools/main"
SCRIPT_URL="$RAW_BASE_URL/$SCRIPT_NAME"

echo "=== pve-storage-info installer (POSIX sh) ==="
echo "Script URL:        $SCRIPT_URL"
echo "Install directory: $INSTALL_DIR"
echo "Symlink:           $LINK_NAME"
echo

# --------------------------
# Check for curl
# --------------------------
if ! command -v curl >/dev/null 2>&1 ; then
    echo "Error: curl not found." >&2
    exit 1
fi

# --------------------------
# Create directory
# --------------------------
echo "[+] Creating directory: $INSTALL_DIR"
mkdir -p "$INSTALL_DIR"

# --------------------------
# Download script
# --------------------------
echo "[+] Downloading pve-storage-info.py ..."
curl -fsSL "$SCRIPT_URL" -o "$TARGET_SCRIPT"

# --------------------------
# Make executable
# --------------------------
echo "[+] Making script executable"
chmod +x "$TARGET_SCRIPT"

# --------------------------
# Remove old symlink
# --------------------------
if [ -L "$LINK_NAME" ] || [ -f "$LINK_NAME" ] ; then
    echo "[+] Removing old link/file: $LINK_NAME"
    rm -f "$LINK_NAME"
fi

# --------------------------
# Create symlink
# --------------------------
echo "[+] Creating symlink: $LINK_NAME -> $TARGET_SCRIPT"
ln -s "$TARGET_SCRIPT" "$LINK_NAME"

echo
echo "=== Installation complete ==="
echo "Run:"
echo "  pve-storage-info --help"
echo "  pve-storage-info --version"
echo
