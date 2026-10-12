_photohelper_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
_photohelper_activate="$_photohelper_root/.venv/bin/activate"

if [[ ! -f "$_photohelper_activate" ]]; then
    printf 'Error: PhotoHelper virtual environment not found at %s\n' "$_photohelper_activate" >&2
    unset _photohelper_root _photohelper_activate
    return 1
fi

source "$_photohelper_activate"
unset _photohelper_root _photohelper_activate
