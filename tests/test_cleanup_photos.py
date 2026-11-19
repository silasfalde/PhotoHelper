from __future__ import annotations

import os
import subprocess
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "cleanup-photos.sh"


def run_cleanup(root: Path) -> subprocess.CompletedProcess[str]:
    bin_dir = root / "bin"
    bin_dir.mkdir()
    (bin_dir / "uname").write_text("#!/bin/sh\nprintf 'Linux\\n'\n")
    (bin_dir / "gio").write_text('#!/bin/sh\nmv -- "$3" "$3.trashed"\n')
    for executable in bin_dir.iterdir():
        executable.chmod(0o755)
    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"
    return subprocess.run(["bash", str(SCRIPT)], cwd=root, env=env, text=True, capture_output=True)


def test_cleanup_preserves_all_matching_dsc_files(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    nested = raw / "nested"
    nested.mkdir(parents=True)
    selected = tmp_path / "select-raws"
    selected.mkdir()
    (selected / "DSC_1234.NEF").write_bytes(b"selected raw")
    for name in ("DSC_1234.dsc", "dsc_1234_1.DSC", "DSC_1234_10.dsc"):
        (nested / name).write_bytes(name.encode())
    for name in ("DSC_12345.dsc", "DSC_1234_extra.dsc", "DSC_5678.dsc"):
        (raw / name).write_bytes(b"unselected")

    result = run_cleanup(tmp_path)

    assert result.returncode == 0, result.stderr
    kept = tmp_path / "raw"
    assert {path.name for path in kept.iterdir()} == {
        "DSC_1234.NEF", "DSC_1234.dsc", "dsc_1234_1.DSC", "DSC_1234_10.dsc"
    }
    assert (kept / "DSC_1234_10.dsc").read_bytes() == b"DSC_1234_10.dsc"
    assert (tmp_path / "raw.trashed" / "DSC_5678.dsc").exists()


def test_cleanup_does_not_overwrite_conflicting_edits(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    raw.mkdir()
    selected = tmp_path / "select-raws"
    selected.mkdir()
    (selected / "DSC_1234.NEF").write_bytes(b"raw")
    (selected / "DSC_1234.dsc").write_bytes(b"existing edit")
    (raw / "DSC_1234.dsc").write_bytes(b"different edit")

    result = run_cleanup(tmp_path)

    assert result.returncode != 0
    assert "DSC_1234.dsc" in result.stderr
    assert (raw / "DSC_1234.dsc").read_bytes() == b"different edit"
    assert (selected / "DSC_1234.dsc").read_bytes() == b"existing edit"
    assert not (tmp_path / "raw.trashed").exists()


def test_cleanup_accepts_existing_identical_sidecar(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    raw.mkdir()
    selected = tmp_path / "select-raws"
    selected.mkdir()
    (selected / "DSC_1234.NEF").write_bytes(b"raw")
    (selected / "DSC_1234.dsc").write_bytes(b"edit")
    (raw / "DSC_1234.dsc").write_bytes(b"edit")

    result = run_cleanup(tmp_path)

    assert result.returncode == 0, result.stderr
    assert (tmp_path / "raw" / "DSC_1234.dsc").read_bytes() == b"edit"


def test_cleanup_stops_on_conflicting_sidecars_in_raw_subdirectories(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    (raw / "one").mkdir(parents=True)
    (raw / "two").mkdir()
    selected = tmp_path / "select-raws"
    selected.mkdir()
    (selected / "DSC_1234.NEF").write_bytes(b"raw")
    (raw / "one" / "DSC_1234.dsc").write_bytes(b"first edit")
    (raw / "two" / "DSC_1234.dsc").write_bytes(b"second edit")

    result = run_cleanup(tmp_path)

    assert result.returncode != 0
    assert "Conflicting DSC files" in result.stderr
    assert (raw / "one" / "DSC_1234.dsc").exists()
    assert (raw / "two" / "DSC_1234.dsc").exists()
    assert not (selected / "DSC_1234.dsc").exists()
