#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/activate-photohelper.sh"

if [[ -d instagram-export ]]; then
    photohelper framer instagram-export
fi
photohelper find-raws standard raw

if [ -d "./raw" ] && [ -d "./select-raws" ]; then
    echo "💾 Preserving edit sidecars for selected raw files..."
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
            if source.suffix.casefold() == ".dsc":
                stem = source.stem.casefold()
            elif name.casefold().endswith(".nef.xmp"):
                stem = name[:-len(".nef.xmp")].casefold()
            else:
                continue
            base, separator, duplicate = stem.rpartition("_")
            if stem not in kept_stems and not (
                separator and duplicate.isdecimal() and base in kept_stems
            ):
                continue

            key = name.casefold()
            existing = destinations.get(key)
            if existing is not None:
                if not existing.is_file() or not filecmp.cmp(source, existing, shallow=False):
                    raise ValueError(f"Conflicting edit sidecar files: {source} and {existing}")
                continue
            destinations[key] = source
            copies.append((source, selected_dir / name))

    for source, destination in copies:
        with source.open("rb") as input_file, destination.open("xb") as output_file:
            shutil.copyfileobj(input_file, output_file)
        shutil.copystat(source, destination)
        print(f"Preserved {source} -> {destination}")
except (OSError, ValueError) as error:
    sys.exit(f"Error preserving edit sidecars: {error}")
PY
fi

photohelper crop-ratio ./standard --ratio 4:3 --in-place
