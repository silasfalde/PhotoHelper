from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

from PIL import Image, ImageOps


ASPECT_RATIO_TOLERANCE = 0.02


@dataclass(frozen=True)
class AppConfig:
    source_dir: Path
    processed_dir: Path
    framed_dir: Path
    target_size: Tuple[int, int]
    baseline_frame_width: int
    frame_color: Tuple[int, int, int]
    allow_upscale: bool
    image_extensions: Tuple[str, ...]
    jpeg_quality: int
    jpeg_subsampling: int
    copy_portraits_without_reencode: bool


@dataclass
class BorderSpec:
    left: int
    top: int
    right: int
    bottom: int


@dataclass
class ProcessRecord:
    source_name: str
    mode: str
    processed_outputs: List[str]
    framed_outputs: List[str]


@dataclass
class RunStats:
    portraits: int = 0
    landscapes: int = 0
    processed_written: int = 0
    framed_written: int = 0
    errors: int = 0


@dataclass(frozen=True)
class CollageConfig:
    background_path: Path
    foreground_paths: Tuple[Path, ...]
    output_dir: Path
    panel_size: Tuple[int, int]
    foreground_scale: float
    jpeg_quality: int
    jpeg_subsampling: int


@dataclass
class CollageStats:
    panels: int = 0
    written: int = 0
    errors: int = 0


@dataclass
class CollageRecord:
    foreground_name: str
    panel_name: str
    output_name: str
    border: BorderSpec


def ensure_output_dirs(cfg: AppConfig) -> None:
    cfg.processed_dir.mkdir(parents=True, exist_ok=True)
    cfg.framed_dir.mkdir(parents=True, exist_ok=True)


def ensure_collage_output_dir(cfg: CollageConfig) -> None:
    cfg.output_dir.mkdir(parents=True, exist_ok=True)


def list_source_images(cfg: AppConfig) -> List[Path]:
    if not cfg.source_dir.exists():
        raise FileNotFoundError(f"Source directory does not exist: {cfg.source_dir}")

    extensions = {ext.lower() for ext in cfg.image_extensions}
    return [
        p
        for p in sorted(cfg.source_dir.iterdir())
        if p.is_file() and p.suffix.lower() in extensions
    ]


def load_image(path: Path) -> Image.Image:
    with Image.open(path) as img:
        return ImageOps.exif_transpose(img).convert("RGB")


def load_image_and_metadata(path: Path) -> Tuple[Image.Image, Optional[bytes], Optional[bytes]]:
    with Image.open(path) as img:
        normalized = ImageOps.exif_transpose(img).convert("RGB")
        exif_bytes = img.info.get("exif")
        icc_profile = img.info.get("icc_profile")
    return normalized, exif_bytes, icc_profile


def resize_exact(img: Image.Image, target_w: int, target_h: int) -> Image.Image:
    if target_w <= 0 or target_h <= 0:
        raise ValueError("Target dimensions must be positive")
    if img.size == (target_w, target_h):
        return img
    return img.resize((target_w, target_h), Image.Resampling.LANCZOS)


def crop_to_aspect(img: Image.Image, target_w: int, target_h: int) -> Image.Image:
    w, h = img.size
    if w <= 0 or h <= 0:
        raise ValueError("Invalid image dimensions for cropping")

    target_ratio = target_w / target_h
    src_ratio = w / h

    if abs(src_ratio - target_ratio) < 1e-9:
        return img

    if src_ratio > target_ratio:
        new_w = int(round(target_ratio * h))
        left = (w - new_w) // 2
        right = left + new_w
        return img.crop((left, 0, right, h))

    new_h = int(round(w / target_ratio))
    top = (h - new_h) // 2
    bottom = top + new_h
    return img.crop((0, top, w, bottom))


def split_landscape_exact(img: Image.Image) -> Tuple[Image.Image, Image.Image]:
    w, h = img.size
    mid = w // 2
    if w % 2 == 0:
        left = img.crop((0, 0, mid, h))
        right = img.crop((mid, 0, w, h))
    else:
        left = img.crop((0, 0, mid, h))
        right = img.crop((mid + 1, 0, w, h))
    return left, right


def fit_inside(
    width: int,
    height: int,
    max_width: int,
    max_height: int,
    allow_upscale: bool,
) -> Tuple[int, int]:
    if width <= 0 or height <= 0:
        raise ValueError("Image dimensions must be positive")
    if max_width <= 0 or max_height <= 0:
        raise ValueError("Bounding dimensions must be positive")

    scale = min(max_width / width, max_height / height)
    if not allow_upscale:
        scale = min(scale, 1.0)

    new_w = max(1, int(round(width * scale)))
    new_h = max(1, int(round(height * scale)))
    return new_w, new_h


def resize_to_fit(
    img: Image.Image,
    target_w: int,
    target_h: int,
    allow_upscale: bool,
) -> Image.Image:
    if target_w <= 0 or target_h <= 0:
        raise ValueError("Target dimensions must be positive")

    new_w, new_h = fit_inside(img.width, img.height, target_w, target_h, allow_upscale)
    if (new_w, new_h) == img.size:
        return img
    return img.resize((new_w, new_h), Image.Resampling.LANCZOS)


def split_frame_baseline(baseline: int) -> int:
    return baseline


def is_landscape(img: Image.Image) -> bool:
    return math.isclose(img.width / img.height, 2.0, rel_tol=ASPECT_RATIO_TOLERANCE, abs_tol=ASPECT_RATIO_TOLERANCE)


def is_portrait_or_square(img: Image.Image) -> bool:
    return math.isclose(img.width / img.height, 1.0, rel_tol=ASPECT_RATIO_TOLERANCE, abs_tol=ASPECT_RATIO_TOLERANCE)


def is_four_thirds(img: Image.Image) -> bool:
    return math.isclose(img.width / img.height, 4.0 / 3.0, rel_tol=ASPECT_RATIO_TOLERANCE, abs_tol=ASPECT_RATIO_TOLERANCE)


def is_three_fourths(img: Image.Image) -> bool:
    return math.isclose(img.width / img.height, 3.0 / 4.0, rel_tol=ASPECT_RATIO_TOLERANCE, abs_tol=ASPECT_RATIO_TOLERANCE)


def classify_source_image(img: Image.Image) -> str:
    if img.width > img.height:
        return "landscape_split"
    return "portrait_or_square"


def bytes_to_kb(path: Path) -> float:
    return path.stat().st_size / 1024.0


def save_jpeg(
    img: Image.Image,
    path: Path,
    cfg: AppConfig,
    exif_bytes: Optional[bytes] = None,
    icc_profile: Optional[bytes] = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    kwargs = {
        "format": "JPEG",
        "quality": cfg.jpeg_quality,
        "subsampling": cfg.jpeg_subsampling,
        "optimize": False,
        "progressive": False,
    }
    if exif_bytes is not None:
        kwargs["exif"] = exif_bytes
    if icc_profile is not None:
        kwargs["icc_profile"] = icc_profile
    img.save(path, **kwargs)


def save_collage_output(
    img: Image.Image,
    path: Path,
    jpeg_quality: int,
    jpeg_subsampling: int,
    exif_bytes: Optional[bytes] = None,
    icc_profile: Optional[bytes] = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    kwargs = {
        "format": "JPEG",
        "quality": jpeg_quality,
        "subsampling": jpeg_subsampling,
        "optimize": False,
        "progressive": False,
    }
    if exif_bytes is not None:
        kwargs["exif"] = exif_bytes
    if icc_profile is not None:
        kwargs["icc_profile"] = icc_profile
    img.save(path, **kwargs)
