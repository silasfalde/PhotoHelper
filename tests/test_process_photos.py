from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]


def run_process(root: Path) -> subprocess.CompletedProcess[str]:
    scripts = root / "scripts"
    scripts.mkdir()
    shutil.copy2(ROOT / "scripts" / "process-photos.sh", scripts)
    (scripts / "activate-photohelper.sh").write_text(
        'export PATH="$TEST_BIN:$PATH"\nexport PYTHONPATH="$TEST_ROOT"\n'
    )
    bin_dir = root / "bin"
    bin_dir.mkdir()
    executable = bin_dir / "photohelper"
    executable.write_text(
        '#!/bin/sh\nexec "$TEST_PYTHON" -c '
        "'import sys; from photo_helper.cli import main; sys.exit(main())' \"$@\"\n"
    )
    executable.chmod(0o755)
    env = os.environ.copy()
    env.update(TEST_BIN=str(bin_dir), TEST_ROOT=str(ROOT), TEST_PYTHON=sys.executable)
    return subprocess.run(
        ["bash", str(scripts / "process-photos.sh")],
        cwd=root,
        env=env,
        text=True,
        capture_output=True,
    )


def setup_selection(root: Path) -> tuple[Path, Path]:
    standard = root / "standard"
    standard.mkdir()
    Image.new("RGB", (40, 20)).save(standard / "DSC_1234_L.jpg")
    raw = root / "raw"
    raw.mkdir()
    (raw / "DSC_1234.NEF").write_bytes(b"selected raw")
    return standard, raw


def test_process_selects_matching_dsc_files(tmp_path: Path) -> None:
    standard, raw = setup_selection(tmp_path)
    nested = raw / "nested"
    nested.mkdir()
    for name in ("DSC_1234.dsc", "dsc_1234_1.DSC", "DSC_1234_10.dsc"):
        (nested / name).write_bytes(name.encode())
    for name in ("DSC_12345.dsc", "DSC_1234_extra.dsc", "DSC_5678.dsc"):
        (raw / name).write_bytes(b"unselected")

    result = run_process(tmp_path)

    assert result.returncode == 0, result.stderr
    selected = tmp_path / "select-raws"
    assert {path.name for path in selected.iterdir()} == {
        "DSC_1234.NEF", "DSC_1234.dsc", "dsc_1234_1.DSC", "DSC_1234_10.dsc"
    }
    assert (selected / "DSC_1234_10.dsc").read_bytes() == b"DSC_1234_10.dsc"
    assert (raw / "DSC_5678.dsc").exists()
    with Image.open(standard / "DSC_1234_L.jpg") as image:
        assert image.size == (27, 20)


def test_process_selects_xmp_sidecars_for_selected_raws(tmp_path: Path) -> None:
    _, raw = setup_selection(tmp_path)
    nested = raw / "nested"
    nested.mkdir()
    for name in ("DSC_1234.NEF.xmp", "dsc_1234_01.nef.XMP", "DSC_1234_10.NEF.xmp"):
        (nested / name).write_bytes(name.encode())
    for name in ("DSC_12345.NEF.xmp", "DSC_1234_extra.NEF.xmp", "DSC_5678.NEF.xmp"):
        (raw / name).write_bytes(b"unselected")

    result = run_process(tmp_path)

    assert result.returncode == 0, result.stderr
    selected = tmp_path / "select-raws"
    assert {path.name for path in selected.iterdir()} == {
        "DSC_1234.NEF", "DSC_1234.NEF.xmp", "dsc_1234_01.nef.XMP", "DSC_1234_10.NEF.xmp"
    }
    assert (selected / "DSC_1234_10.NEF.xmp").read_bytes() == b"DSC_1234_10.NEF.xmp"


def test_process_stops_on_conflicting_xmp_sidecars(tmp_path: Path) -> None:
    _, raw = setup_selection(tmp_path)
    selected = tmp_path / "select-raws"
    selected.mkdir()
    (selected / "DSC_1234.NEF.xmp").write_bytes(b"existing edit")
    (raw / "DSC_1234.NEF.xmp").write_bytes(b"different edit")

    result = run_process(tmp_path)

    assert result.returncode != 0
    assert "DSC_1234.NEF.xmp" in result.stderr
    assert (selected / "DSC_1234.NEF.xmp").read_bytes() == b"existing edit"
    assert (raw / "DSC_1234.NEF.xmp").read_bytes() == b"different edit"


def test_process_does_not_overwrite_conflicting_edits(tmp_path: Path) -> None:
    standard, raw = setup_selection(tmp_path)
    selected = tmp_path / "select-raws"
    selected.mkdir()
    (selected / "DSC_1234.dsc").write_bytes(b"existing edit")
    (raw / "DSC_1234.dsc").write_bytes(b"different edit")

    result = run_process(tmp_path)

    assert result.returncode != 0
    assert "DSC_1234.dsc" in result.stderr
    assert (raw / "DSC_1234.dsc").read_bytes() == b"different edit"
    assert (selected / "DSC_1234.dsc").read_bytes() == b"existing edit"
    with Image.open(standard / "DSC_1234_L.jpg") as image:
        assert image.size == (40, 20)


def test_process_accepts_existing_identical_sidecar(tmp_path: Path) -> None:
    _, raw = setup_selection(tmp_path)
    selected = tmp_path / "select-raws"
    selected.mkdir()
    (selected / "DSC_1234.dsc").write_bytes(b"edit")
    (raw / "DSC_1234.dsc").write_bytes(b"edit")

    result = run_process(tmp_path)

    assert result.returncode == 0, result.stderr
    assert (selected / "DSC_1234.dsc").read_bytes() == b"edit"


def test_process_stops_on_conflicting_sidecars_in_raw_subdirectories(tmp_path: Path) -> None:
    _, raw = setup_selection(tmp_path)
    (raw / "one").mkdir()
    (raw / "two").mkdir()
    (raw / "one" / "DSC_1234.dsc").write_bytes(b"first edit")
    (raw / "two" / "DSC_1234.dsc").write_bytes(b"second edit")

    result = run_process(tmp_path)

    assert result.returncode != 0
    assert "Conflicting edit sidecar files" in result.stderr
    assert (raw / "one" / "DSC_1234.dsc").exists()
    assert (raw / "two" / "DSC_1234.dsc").exists()
    assert not (tmp_path / "select-raws" / "DSC_1234.dsc").exists()


def test_process_without_jpgs_does_not_require_selection_directory(tmp_path: Path) -> None:
    (tmp_path / "standard").mkdir()
    (tmp_path / "raw").mkdir()

    result = run_process(tmp_path)

    assert result.returncode == 0, result.stderr
    assert not (tmp_path / "select-raws").exists()
