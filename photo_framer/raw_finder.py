"""Raw photo finder and copier for matching NEF files to JPGs."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def find_jpg_files(jpg_dir: Path) -> list[Path]:
    """Find all JPG files in the given directory (non-recursive)."""
    jpg_dir = jpg_dir.resolve()
    if not jpg_dir.exists():
        raise FileNotFoundError(f"JPG directory does not exist: {jpg_dir}")
    
    jpg_files = sorted([f for f in jpg_dir.iterdir() if f.suffix.lower() == ".jpg"])
    return jpg_files


def find_all_raw_files(raw_source: Path) -> dict[str, Path]:
    """
    Recursively find all NEF files in raw_source directory.
    Returns a dict mapping lowercase filename -> full path.
    """
    raw_source = raw_source.resolve()
    if not raw_source.exists():
        raise FileNotFoundError(f"Raw source directory does not exist: {raw_source}")
    
    raw_files: dict[str, Path] = {}
    
    for root, dirs, files in os.walk(raw_source):
        # Skip certain directories to improve performance
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        
        for file in files:
            if file.lower().endswith(".nef"):
                full_path = Path(root) / file
                # Use lowercase filename as key for case-insensitive matching
                raw_files[file.lower()] = full_path
    
    return raw_files


def extract_base_name(jpg_filename: str) -> tuple[str, Optional[str]]:
    """
    Extract base name and suffix from JPG filename.
    E.g., "DSC_3988_L.jpg" -> ("DSC_3988", "_L")
           "DSC_3988.jpg" -> ("DSC_3988", None)
    """
    name_without_ext = jpg_filename.rsplit(".", 1)[0]
    
    # Check for common suffixes like _L, _R, _01, etc.
    common_suffixes = ["_L", "_R", "_01", "_02", "_03", "_A", "_B", "_1", "_2"]
    
    for suffix in common_suffixes:
        if name_without_ext.endswith(suffix):
            base_name = name_without_ext[: -len(suffix)]
            return (base_name, suffix)
    
    return (name_without_ext, None)


def match_raw_to_jpg(
    jpg_filename: str, raw_files: dict[str, Path]
) -> Optional[Path]:
    """
    Find matching NEF file for a JPG filename.
    
    Matching strategy (in order of preference):
    1. Exact match with suffix: DSC_3988_L.nef for DSC_3988_L.jpg
    2. Base name only: DSC_3988.nef for DSC_3988_L.jpg
    """
    base_name, suffix = extract_base_name(jpg_filename)
    
    # Try exact match first (with suffix)
    if suffix:
        exact_match = f"{base_name}{suffix}.nef".lower()
        if exact_match in raw_files:
            return raw_files[exact_match]
    
    # Try base name only
    base_match = f"{base_name}.nef".lower()
    if base_match in raw_files:
        return raw_files[base_match]
    
    return None


def is_file_offloaded(file_path: Path) -> bool:
    """
    Check if a file is offloaded in Google Drive Cloud Storage.
    
    Returns True if file is offloaded (not fully downloaded), False if available.
    Uses macOS file system attributes and file size heuristics.
    """
    try:
        # Get file stats
        stat_info = os.stat(file_path)
        file_size = stat_info.st_size
        
        # Offloaded files typically have size 0 or very small placeholder size
        # Try to check for Cloud Storage attributes
        try:
            result = subprocess.run(
                ["xattr", "-l", str(file_path)],
                capture_output=True,
                text=True,
                timeout=2,
            )
            attrs = result.stdout.lower()
            
            # Check for Cloud Storage offload indicators
            if "com.apple.resourcetype=com.apple.cloudkit.file" in attrs:
                # Check if it's a placeholder (has the ubiquitous "pinned" attribute missing)
                if "com.apple.ubiquity-stalled" in attrs or "com.apple.ubiquity-placeholder" in attrs:
                    return True
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
            # If xattr fails, fall back to size heuristic
            pass
        
        # Offloaded files are typically very small (< 1KB placeholder)
        # But we should be more conservative and actually try to read
        return False
    except Exception as e:
        logger.warning(f"Error checking offload status for {file_path}: {e}")
        return False


def ensure_file_downloaded(file_path: Path, timeout_seconds: int = 30) -> bool:
    """
    Ensure a file is fully downloaded by triggering macOS Cloud Storage recall.
    
    Attempts to open the file, which triggers automatic download for offloaded files.
    Retries with exponential backoff up to timeout_seconds.
    
    Returns True if file is available (downloaded), False if still offloaded after timeout.
    """
    start_time = time.time()
    retry_count = 0
    base_delay = 0.5  # Start with 500ms delay
    
    while time.time() - start_time < timeout_seconds:
        try:
            # Try to read the first byte to trigger download
            with open(file_path, "rb") as f:
                f.read(1)
            # If successful, file is downloaded
            return True
        except (IOError, OSError) as e:
            # File might still be offloaded, wait and retry
            elapsed = time.time() - start_time
            delay = min(base_delay * (2 ** retry_count), 5.0)  # Cap at 5 seconds
            remaining = timeout_seconds - elapsed
            
            if remaining > 0:
                sleep_time = min(delay, remaining)
                logger.debug(
                    f"Waiting for {file_path.name} to download (attempt {retry_count + 1}, "
                    f"{elapsed:.1f}s elapsed)..."
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
) -> dict[str, int]:
    """
    Match JPGs to NEF files and copy all matched NEFs to output directory.
    
    Returns a dict with stats: {
        "matched": count of jpg->nef pairs found,
        "copied": count of files successfully copied,
        "skipped_offloaded": count of files still offloaded after timeout,
        "missing": count of jpgs with no matching nef,
        "duplicate": count of jpgs that matched to already-copied NEF,
    }
    """
    # Validate input directories
    jpg_dir = jpg_dir.resolve()
    raw_source = raw_source.resolve()
    output_dir = output_dir.resolve()
    
    if not jpg_dir.exists():
        raise FileNotFoundError(f"JPG directory does not exist: {jpg_dir}")
    if not raw_source.exists():
        raise FileNotFoundError(f"Raw source directory does not exist: {raw_source}")
    
    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Find all files
    jpg_files = find_jpg_files(jpg_dir)
    raw_files = find_all_raw_files(raw_source)
    
    if verbose:
        logger.info(f"Found {len(jpg_files)} JPG files in {jpg_dir}")
        logger.info(f"Found {len(raw_files)} NEF files in {raw_source}")
    
    stats = {
        "matched": 0,
        "copied": 0,
        "skipped_offloaded": 0,
        "missing": 0,
        "duplicate": 0,
    }
    
    # Track which NEF files have already been copied to avoid duplicates
    # (e.g., DSC_3988_L.jpg and DSC_3988_R.jpg both match to DSC_3988.nef)
    copied_nebs = set()
    
    for jpg_file in jpg_files:
        matched_raw = match_raw_to_jpg(jpg_file.name, raw_files)
        
        if matched_raw is None:
            if verbose:
                logger.warning(f"No matching NEF found for {jpg_file.name}")
            stats["missing"] += 1
            continue
        
        stats["matched"] += 1
        
        # Check if we've already copied this NEF file
        nef_key = matched_raw.name.lower()
        if nef_key in copied_nebs:
            if verbose:
                logger.info(
                    f"Skipping {jpg_file.name}: already copied matching NEF {matched_raw.name}"
                )
            stats["duplicate"] += 1
            continue
        
        # Ensure file is downloaded
        if verbose:
            logger.info(f"Checking if {matched_raw.name} is downloaded...")
        
        if not ensure_file_downloaded(matched_raw):
            logger.warning(
                f"Skipping {matched_raw.name}: still offloaded after timeout"
            )
            stats["skipped_offloaded"] += 1
            continue
        
        # Copy file to output directory
        output_path = output_dir / matched_raw.name
        try:
            shutil.copy2(matched_raw, output_path)
            if verbose:
                logger.info(f"Copied {matched_raw.name} to {output_dir}")
            stats["copied"] += 1
            copied_nebs.add(nef_key)
        except Exception as e:
            logger.error(f"Failed to copy {matched_raw.name}: {e}")
    
    return stats


def summarize_results(stats: dict[str, int], jpg_count: int) -> None:
    """Print a summary of the raw copy operation."""
    matched = stats["matched"]
    copied = stats["copied"]
    skipped = stats["skipped_offloaded"]
    missing = stats["missing"]
    duplicate = stats.get("duplicate", 0)
    
    print("\n" + "=" * 60)
    print("Raw Photo Copy Summary")
    print("=" * 60)
    print(f"Total JPG files processed:      {jpg_count}")
    print(f"Matched with NEF files:         {matched} ({100*matched//jpg_count if jpg_count else 0}%)")
    print(f"Successfully copied:            {copied}")
    print(f"Skipped (duplicate NEF):        {duplicate}")
    print(f"Skipped (still offloaded):      {skipped}")
    print(f"No matching NEF found:          {missing}")
    print("=" * 60)
