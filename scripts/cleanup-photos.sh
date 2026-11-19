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

if [ -d "./raw" ] && [ -d "./select-raws" ]; then
    echo "💾 Preserving DSC edits for selected raw files..."
    python3 - "./raw" "./select-raws" <<'PY'
import filecmp
import os
import shutil
import sys
from pathlib import Path

raw_dir, selected_dir = map(Path, sys.argv[1:])


def raise_walk_error(error):
    raise error


try:
    selected_entries = list(selected_dir.iterdir())
    kept_stems = {
        path.stem.casefold()
        for path in selected_entries
        if path.is_file() and path.suffix.casefold() == ".nef"
    }
    destinations = {path.name.casefold(): path for path in selected_entries}
    copies = []

    for root, _, files in os.walk(raw_dir, onerror=raise_walk_error):
        for name in files:
            source = Path(root) / name
            if source.suffix.casefold() != ".dsc":
                continue
            stem = source.stem.casefold()
            base, separator, duplicate = stem.rpartition("_")
            if stem not in kept_stems and not (
                separator and duplicate.isdecimal() and base in kept_stems
            ):
                continue

            key = name.casefold()
            existing = destinations.get(key)
            if existing is not None:
                if not existing.is_file() or not filecmp.cmp(source, existing, shallow=False):
                    raise ValueError(f"Conflicting DSC files: {source} and {existing}")
                continue
            destinations[key] = source
            copies.append((source, selected_dir / name))

    for source, destination in copies:
        with source.open("rb") as input_file, destination.open("xb") as output_file:
            shutil.copyfileobj(input_file, output_file)
        shutil.copystat(source, destination)
        print(f"Preserved {source} -> {destination}")
except (OSError, ValueError) as error:
    sys.exit(f"Error preserving DSC files: {error}")
PY
fi

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
