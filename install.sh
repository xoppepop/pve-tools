#!/usr/bin/env bash
# Installer for pve-storage-info

set -euo pipefail

SCRIPT_NAME="pve-storage-info.py"
INSTALL_DIR="/opt/pve-tools"
TARGET_SCRIPT="$INSTALL_DIR/$SCRIPT_NAME"
LINK_NAME="/usr/local/bin/pve-storage-info"

# ======================================================================
#  GitHub RAW base URL — тут мають лежати install.sh і pve-storage-info.py
# ======================================================================
RAW_BASE_URL="https://raw.githubusercontent.com/xoppepop/pve-tools/main"
SCRIPT_URL="$RAW_BASE_URL/$SCRIPT_NAME"

echo "=== pve-storage-info installer ==="
echo "Script URL:       $SCRIPT_URL"
echo "Install directory: $INSTALL_DIR"
echo "Symlink:           $LINK_NAME"
echo

# --------------------------
# Check for curl
# --------------------------
if ! command -v curl >/dev/null 2>&1; then
    echo "Error: curl is not installed or not in PATH." >&2
    exit 1
fi

# --------------------------
# Create install directory
# --------------------------
echo "[+] Creating directory (if missing): $INSTALL_DIR"
sudo mkdir -p "$INSTALL_DIR"

# --------------------------
# Download main script
# --------------------------
echo "[+] Downloading pve-storage-info.py from GitHub..."
sudo curl -fsSL "$SCRIPT_URL" -o "$TARGET_SCRIPT"

# --------------------------
# Set executable permissions
# --------------------------
echo "[+] Setting executable bit on $TARGET_SCRIPT"
sudo chmod +x "$TARGET_SCRIPT"

# --------------------------
# Remove old symlink if exists
# --------------------------
if [ -L "$LINK_NAME" ] || [ -f "$LINK_NAME" ]; then
    echo "[+] Removing existing link/file: $LINK_NAME"
    sudo rm -f "$LINK_NAME"
fi

# --------------------------
# Create symlink
# --------------------------
echo "[+] Creating symlink: $LINK_NAME -> $TARGET_SCRIPT"
sudo ln -s "$TARGET_SCRIPT" "$LINK_NAME"

echo
echo "=== Installation complete! ==="
echo "You can now run:"
echo "  pve-storage-info --help"
echo "  pve-storage-info --version"
echo
