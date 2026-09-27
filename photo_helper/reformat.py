"""Center-crop utilities for normalizing horizontal images to a target aspect ratio."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from .common import crop_to_aspect, load_image_and_metadata, save_collage_output

ASPECT_RATIO_MATCH_TOLERANCE = 0.005


@dataclass(frozen=True)
class ReformatConfig:
    source_dir: Path
    output_dir: Path
    ratio: Tuple[int, int]
    image_extensions: Tuple[str, ...]
    jpeg_quality: int
    jpeg_subsampling: int


@dataclass
class ReformatRecord:
    source_name: str
    action: str
    original_size: Tuple[int, int]
    output_size: Tuple[int, int]


@dataclass
class ReformatStats:
    discovered: int = 0
    cropped: int = 0
    already_matching: int = 0
    skipped_non_horizontal: int = 0
    errors: int = 0


def list_reformat_source_images(cfg: ReformatConfig) -> List[Path]:
    if not cfg.source_dir.exists():
        raise FileNotFoundError(f"Source directory does not exist: {cfg.source_dir}")

    extensions = {ext.lower() for ext in cfg.image_extensions}
    return [
        p
        for p in sorted(cfg.source_dir.iterdir())
        if p.is_file() and p.suffix.lower() in extensions
    ]


def crop_horizontal_images_to_ratio(
    cfg: ReformatConfig,
    log_callback: Optional[Callable[[str], None]] = None,
) -> Tuple[List[ReformatRecord], ReformatStats]:
    cfg.output_dir.mkdir(parents=True, exist_ok=True)
    source_files = list_reformat_source_images(cfg)

    ratio_w, ratio_h = cfg.ratio
    target_ratio = ratio_w / ratio_h

    records: List[ReformatRecord] = []
    stats = ReformatStats(discovered=len(source_files))

    for path in source_files:
        output_path = cfg.output_dir / path.name
        try:
            img, exif_bytes, icc_profile = load_image_and_metadata(path)
            original_size = img.size

            if img.width <= img.height:
                if output_path != path:
                    shutil.copy2(path, output_path)
                stats.skipped_non_horizontal += 1
                records.append(ReformatRecord(path.name, "skipped_non_horizontal", original_size, original_size))
                if log_callback:
                    log_callback(f"skip (not horizontal): {path.name}")
                continue

            src_ratio = img.width / img.height
            if abs(src_ratio - target_ratio) < ASPECT_RATIO_MATCH_TOLERANCE:
                if output_path != path:
                    shutil.copy2(path, output_path)
                stats.already_matching += 1
                records.append(ReformatRecord(path.name, "already_matching", original_size, original_size))
                if log_callback:
                    log_callback(f"already {ratio_w}:{ratio_h}: {path.name}")
                continue

            cropped = crop_to_aspect(img, ratio_w, ratio_h)
            save_collage_output(
                cropped,
                output_path,
                jpeg_quality=cfg.jpeg_quality,
                jpeg_subsampling=cfg.jpeg_subsampling,
                exif_bytes=exif_bytes,
                icc_profile=icc_profile,
            )
            stats.cropped += 1
            records.append(ReformatRecord(path.name, "cropped", original_size, cropped.size))
            if log_callback:
                log_callback(f"cropped {original_size[0]}x{original_size[1]} -> {cropped.size[0]}x{cropped.size[1]}: {path.name}")
        except Exception as exc:  # noqa: BLE001
            stats.errors += 1
            if log_callback:
                log_callback(f"error processing {path.name}: {exc}")

    return records, stats
