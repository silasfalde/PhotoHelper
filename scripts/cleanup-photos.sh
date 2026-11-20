#!/bin/bash

set -euo pipefail

move_to_trash() {
    case "$(uname -s)" in
        Darwin)
            osascript \
                -e 'on run argv' \
                -e 'set itemAlias to POSIX file (item 1 of argv) as alias' \
                -e 'tell application "Finder" to delete itemAlias' \
                -e 'end run' \
                "$PWD/${1#./}"
            ;;
        Linux)
            if command -v gio >/dev/null 2>&1; then
                gio trash -- "$1"
            elif command -v trash-put >/dev/null 2>&1; then
                trash-put -- "$1"
            else
                echo "Error: 'gio' or 'trash-put' is required to move files to trash." >&2
                return 1
            fi
            ;;
        *)
            echo "Error: moving files to trash is unsupported on $(uname -s)." >&2
            return 1
            ;;
    esac
}

echo "📸 Starting photo directory cleanup..."

# 1. Move the old ./raw folder to trash if it exists
if [ -d "./raw" ]; then
    echo "🧹 Moving old raw folder to trash..."
    move_to_trash "./raw"
fi

# 2. Move the ./instagram-export folder to trash if it exists
if [ -d "./instagram-export" ]; then
    echo "🧹 Moving instagram-export folder to trash..."
    move_to_trash "./instagram-export"
fi

# 3. Rename ./select-raws to ./raw
if [ -d "./select-raws" ]; then
    echo "🔄 Renaming select-raws to raw..."
    mv -- "./select-raws" "./raw"
else
    echo "⚠️ Warning: './select-raws' directory not found. Skipping rename."
fi

echo "✅ Done! Cleanup complete."
