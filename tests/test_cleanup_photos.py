from __future__ import annotations

import os
import subprocess
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "cleanup-photos.sh"


def test_cleanup_trashes_old_folders_and_keeps_selected_files(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "old.NEF").write_bytes(b"old raw")
    export = tmp_path / "instagram-export"
    export.mkdir()
    selected = tmp_path / "select-raws"
    selected.mkdir()
    (selected / "DSC_1234.NEF").write_bytes(b"selected raw")
    (selected / "DSC_1234.dsc").write_bytes(b"selected edit")

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "uname").write_text("#!/bin/sh\nprintf 'Linux\\n'\n")
    (bin_dir / "gio").write_text('#!/bin/sh\nmv -- "$3" "$3.trashed"\n')
    for executable in bin_dir.iterdir():
        executable.chmod(0o755)
    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"

    result = subprocess.run(
        ["bash", str(SCRIPT)], cwd=tmp_path, env=env, text=True, capture_output=True
    )

    assert result.returncode == 0, result.stderr
    assert (tmp_path / "raw.trashed" / "old.NEF").read_bytes() == b"old raw"
    assert (tmp_path / "instagram-export.trashed").is_dir()
    assert (raw / "DSC_1234.NEF").read_bytes() == b"selected raw"
    assert (raw / "DSC_1234.dsc").read_bytes() == b"selected edit"
    assert not selected.exists()
