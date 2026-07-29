"""Raw photo finder and copier for matching NEF files to JPGs."""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Callable, Optional


def find_jpg_files(jpg_dir: Path) -> list[Path]:
    jpg_dir = jpg_dir.resolve()
    if not jpg_dir.exists():
        raise FileNotFoundError(f"JPG directory does not exist: {jpg_dir}")

    return sorted([f for f in jpg_dir.iterdir() if f.suffix.lower() == ".jpg"])


def find_all_raw_files(raw_source: Path) -> dict[str, Path]:
    raw_source = raw_source.resolve()
    if not raw_source.exists():
        raise FileNotFoundError(f"Raw source directory does not exist: {raw_source}")

    raw_files: dict[str, Path] = {}
    for root, dirs, files in os.walk(raw_source):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for file in files:
            if file.lower().endswith(".nef"):
                raw_files[file.lower()] = Path(root) / file
    return raw_files


def extract_base_name(jpg_filename: str) -> tuple[str, Optional[str]]:
    name_without_ext = jpg_filename.rsplit(".", 1)[0]
    common_suffixes = ["_L", "_R", "_01", "_02", "_03", "_A", "_B", "_1", "_2"]

    for suffix in common_suffixes:
        if name_without_ext.endswith(suffix):
            return name_without_ext[: -len(suffix)], suffix

    return name_without_ext, None


def match_raw_to_jpg(jpg_filename: str, raw_files: dict[str, Path]) -> Optional[Path]:
    base_name, suffix = extract_base_name(jpg_filename)

    if suffix:
        exact_match = f"{base_name}{suffix}.nef".lower()
        if exact_match in raw_files:
            return raw_files[exact_match]

    base_match = f"{base_name}.nef".lower()
    if base_match in raw_files:
        return raw_files[base_match]

    return None


def is_file_offloaded(file_path: Path) -> bool:
    try:
        os.stat(file_path)
        try:
            result = subprocess.run(
                ["xattr", "-l", str(file_path)],
                capture_output=True,
                text=True,
                timeout=2,
            )
            attrs = result.stdout.lower()
            if "com.apple.resourcetype=com.apple.cloudkit.file" in attrs:
                if "com.apple.ubiquity-stalled" in attrs or "com.apple.ubiquity-placeholder" in attrs:
                    return True
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
            pass
        return False
    except Exception:
        return False


def ensure_file_downloaded(file_path: Path, timeout_seconds: int = 30) -> bool:
    start_time = time.time()
    retry_count = 0
    base_delay = 0.5

    while time.time() - start_time < timeout_seconds:
        try:
            with open(file_path, "rb") as handle:
                handle.read(1)
            return True
        except (IOError, OSError):
            elapsed = time.time() - start_time
            delay = min(base_delay * (2 ** retry_count), 5.0)
            remaining = timeout_seconds - elapsed

            if remaining > 0:
                sleep_time = min(delay, remaining)
                logger.debug(
                    "Waiting for %s to download (attempt %s, %.1fs elapsed)...",
                    file_path.name,
                    retry_count + 1,
                    elapsed,
                )
                time.sleep(sleep_time)
                retry_count += 1
            else:
                return False

    return False


def copy_matched_raws(
    jpg_dir: Path,
    raw_source: Path,
    output_dir: Path,
    verbose: bool = False,
    timeout_seconds: int = 30,
    status_callback: Optional[Callable[[str], None]] = None,
) -> dict[str, int]:
    jpg_dir = jpg_dir.resolve()
    raw_source = raw_source.resolve()
    output_dir = output_dir.resolve()

    if not jpg_dir.exists():
        raise FileNotFoundError(f"JPG directory does not exist: {jpg_dir}")
    if not raw_source.exists():
        raise FileNotFoundError(f"Raw source directory does not exist: {raw_source}")

    output_dir.mkdir(parents=True, exist_ok=True)

    jpg_files = find_jpg_files(jpg_dir)
    raw_files = find_all_raw_files(raw_source)

    def emit(message: str) -> None:
        if verbose and status_callback is not None:
            status_callback(message)

    stats = {
        "matched": 0,
        "copied": 0,
        "skipped_offloaded": 0,
        "missing": 0,
        "duplicate": 0,
    }

    copied_nebs = set()

    for jpg_file in jpg_files:
        matched_raw = match_raw_to_jpg(jpg_file.name, raw_files)

        if matched_raw is None:
            emit(f"No matching NEF found for {jpg_file.name}")
            stats["missing"] += 1
            continue

        stats["matched"] += 1
        nef_key = matched_raw.name.lower()
        if nef_key in copied_nebs:
            emit(f"Skipping {jpg_file.name}: already copied matching NEF {matched_raw.name}")
            stats["duplicate"] += 1
            continue

        emit(f"Checking if {matched_raw.name} is downloaded...")

        if not ensure_file_downloaded(matched_raw, timeout_seconds=timeout_seconds):
            emit(f"Skipping {matched_raw.name}: still offloaded after timeout")
            stats["skipped_offloaded"] += 1
            continue

        output_path = output_dir / matched_raw.name
        try:
            shutil.copy2(matched_raw, output_path)
            emit(f"Copied {matched_raw.name} to {output_dir}")
            stats["copied"] += 1
            copied_nebs.add(nef_key)
        except Exception:
            continue

    return stats


def summarize_results(stats: dict[str, int], jpg_count: int) -> None:
    matched = stats["matched"]
    copied = stats["copied"]
    skipped = stats["skipped_offloaded"]
    missing = stats["missing"]
    duplicate = stats.get("duplicate", 0)

    print("\n" + "=" * 60)
    print("Raw Photo Copy Summary")
    print("=" * 60)
    print(f"Total JPG files processed:      {jpg_count}")
    print(f"Matched with NEF files:         {matched} ({100 * matched // jpg_count if jpg_count else 0}%)")
    print(f"Successfully copied:            {copied}")
    print(f"Skipped (duplicate NEF):        {duplicate}")
    print(f"Skipped (still offloaded):      {skipped}")
    print(f"No matching NEF found:          {missing}")
    print("=" * 60)
