#!/usr/bin/env bash
set -euo pipefail

# Get the name of the current directory (e.g., "20260918-game-night")
DIR_NAME="$(basename -- "$PWD")"
DESTINATION="gdrive:student-life-photos/$DIR_NAME"

# 4. Upload the current directory into its own subfolder on Google Drive
echo "🚀 Uploading current directory into '$DESTINATION'..."
rclone copy . "$DESTINATION" --transfers 8 --drive-chunk-size 64M --checkers 16 -P

echo "Upload complete!"
