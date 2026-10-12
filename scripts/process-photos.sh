#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/activate-photohelper.sh"

if [[ -d instagram-export ]]; then
    photohelper framer instagram-export
fi
photohelper find-raws standard raw
photohelper crop-ratio ./standard --ratio 4:3 --in-place
