_photohelper_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
_photohelper_activate="$_photohelper_root/.venv/bin/activate"

if [[ ! -f "$_photohelper_activate" ]]; then
    printf 'Error: PhotoHelper virtual environment not found at %s\n' "$_photohelper_activate" >&2
    unset _photohelper_root _photohelper_activate
    return 1
fi

source "$_photohelper_activate"

if ! _photohelper_err="$(python -c 'import photo_helper' 2>&1)"; then
    _photohelper_cfg="$_photohelper_root/.venv/pyvenv.cfg"
    {
        printf 'Error: the PhotoHelper virtual environment at %s/.venv is broken.\n' "$_photohelper_root"
        printf '%s\n\n' "$_photohelper_err"
        printf 'Venv was built with: %s\n' "$(grep -E '^version' "$_photohelper_cfg" 2>/dev/null || echo 'unknown version')"
        printf 'Interpreter now resolves to: %s\n' "$(readlink -f "$_photohelper_root/.venv/bin/python" 2>/dev/null || echo unknown)"
        printf 'This usually happens after a system Python upgrade. Rebuild it with:\n'
        printf '  %s/scripts/rebuild-venv.sh\n' "$_photohelper_root"
        printf 'See "Troubleshooting" in README.md.\n'
    } >&2
    deactivate 2>/dev/null || true
    unset _photohelper_root _photohelper_activate _photohelper_err _photohelper_cfg
    return 1
fi

unset _photohelper_root _photohelper_activate _photohelper_err
