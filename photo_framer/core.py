from __future__ import annotations

import math
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

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


def compute_collage_canvas_size(panel_size: Tuple[int, int], panel_count: int) -> Tuple[int, int]:
    if panel_count <= 0:
        raise ValueError("Panel count must be positive")

    panel_w, panel_h = panel_size
    if panel_w <= 0 or panel_h <= 0:
        raise ValueError("Panel dimensions must be positive")

    return panel_w * panel_count, panel_h


def crop_background_for_collage(
    background: Image.Image,
    panel_size: Tuple[int, int],
    panel_count: int,
) -> Image.Image:
    canvas_w, canvas_h = compute_collage_canvas_size(panel_size, panel_count)
    cropped = crop_to_aspect(background, canvas_w, canvas_h)
    return resize_exact(cropped, canvas_w, canvas_h)


def render_collage_panel(
    background_slice: Image.Image,
    foreground: Image.Image,
    panel_size: Tuple[int, int],
    foreground_scale: float,
    foreground_border_width: int = 0,
    foreground_border_color: Tuple[int, int, int] = (255, 255, 255),
) -> Tuple[Image.Image, BorderSpec]:
    if foreground_scale <= 0:
        raise ValueError("Foreground scale must be positive")
    if foreground_border_width < 0:
        raise ValueError("Foreground border width must be non-negative")

    panel_w, panel_h = panel_size
    if background_slice.size != (panel_w, panel_h):
        raise ValueError("Background slice does not match panel size")

    fg_cropped = crop_to_aspect(foreground, 3, 4)
    max_w = max(1, int(round(panel_w * foreground_scale)) - (2 * foreground_border_width))
    max_h = max(1, int(round(panel_h * foreground_scale)) - (2 * foreground_border_width))
    fg_resized = resize_to_fit(fg_cropped, max_w, max_h, allow_upscale=False)
    if foreground_border_width > 0:
        fg_resized = ImageOps.expand(
            fg_resized,
            border=foreground_border_width,
            fill=foreground_border_color,
        )

    panel = background_slice.copy()
    x = (panel_w - fg_resized.width) // 2
    y = (panel_h - fg_resized.height) // 2
    panel.paste(fg_resized, (x, y))

    border = BorderSpec(
        left=x,
        top=y,
        right=panel_w - (x + fg_resized.width),
        bottom=panel_h - (y + fg_resized.height),
    )
    return panel, border


def build_collage(
    background: Image.Image,
    foregrounds: List[Image.Image],
    panel_size: Tuple[int, int],
    foreground_scale: float,
    foreground_border_width: int = 0,
    foreground_border_color: Tuple[int, int, int] = (255, 255, 255),
) -> Tuple[Image.Image, List[Image.Image], List[BorderSpec]]:
    if not foregrounds:
        raise ValueError("At least one foreground image is required")

    canvas_w, canvas_h = compute_collage_canvas_size(panel_size, len(foregrounds))
    background_canvas = crop_background_for_collage(background, panel_size, len(foregrounds))

    master = Image.new("RGB", (canvas_w, canvas_h))
    panel_images: List[Image.Image] = []
    borders: List[BorderSpec] = []
    panel_w, panel_h = panel_size

    for index, foreground in enumerate(foregrounds):
        x0 = index * panel_w
        background_slice = background_canvas.crop((x0, 0, x0 + panel_w, panel_h))
        panel_image, border = render_collage_panel(
            background_slice,
            foreground,
            panel_size=panel_size,
            foreground_scale=foreground_scale,
            foreground_border_width=foreground_border_width,
            foreground_border_color=foreground_border_color,
        )
        master.paste(panel_image, (x0, 0))
        panel_images.append(panel_image)
        borders.append(border)

    return master, panel_images, borders


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


def validate_collage_outputs(
    panel_size: Tuple[int, int],
    master_path: Path,
    panel_paths: List[Path],
) -> None:
    panel_w, panel_h = panel_size
    expected_size = (panel_w * len(panel_paths), panel_h)

    with Image.open(master_path) as master_img:
        assert master_img.size == expected_size, (
            f"Master collage is not {expected_size}: {master_path.name}, got {master_img.size}"
        )

    for panel_path in panel_paths:
        with Image.open(panel_path) as panel_img:
            assert panel_img.size == panel_size, (
                f"Panel is not {panel_size}: {panel_path.name}, got {panel_img.size}"
            )


def is_landscape(img: Image.Image) -> bool:
    return math.isclose(img.width / img.height, 2.0, rel_tol=ASPECT_RATIO_TOLERANCE, abs_tol=ASPECT_RATIO_TOLERANCE)


def is_portrait_or_square(img: Image.Image) -> bool:
    return math.isclose(img.width / img.height, 1.0, rel_tol=ASPECT_RATIO_TOLERANCE, abs_tol=ASPECT_RATIO_TOLERANCE)


def is_four_thirds(img: Image.Image) -> bool:
    return math.isclose(img.width / img.height, 4.0 / 3.0, rel_tol=ASPECT_RATIO_TOLERANCE, abs_tol=ASPECT_RATIO_TOLERANCE)


def is_three_fourths(img: Image.Image) -> bool:
    return math.isclose(img.width / img.height, 3.0 / 4.0, rel_tol=ASPECT_RATIO_TOLERANCE, abs_tol=ASPECT_RATIO_TOLERANCE)


def classify_source_image(img: Image.Image) -> str:
    # Split any horizontal image. Taller/square images are handled as
    # portrait/square for center-crop + framing.
    if img.width > img.height:
        return "landscape_split"
    return "portrait_or_square"


def resize_exact(img: Image.Image, target_w: int, target_h: int) -> Image.Image:
    if target_w <= 0 or target_h <= 0:
        raise ValueError("Target dimensions must be positive")
    if img.size == (target_w, target_h):
        return img
    return img.resize((target_w, target_h), Image.Resampling.LANCZOS)


def crop_to_aspect(img: Image.Image, target_w: int, target_h: int) -> Image.Image:
    """Center-crop `img` to match the aspect ratio of `target_w:target_h`.

    Returns a new Image (may be the original object if no cropping needed).
    """
    w, h = img.size
    if w <= 0 or h <= 0:
        raise ValueError("Invalid image dimensions for cropping")

    target_ratio = target_w / target_h
    src_ratio = w / h

    if abs(src_ratio - target_ratio) < 1e-9:
        return img

    if src_ratio > target_ratio:
        # source is wider than target -> crop left/right
        new_w = int(round(target_ratio * h))
        left = (w - new_w) // 2
        right = left + new_w
        return img.crop((left, 0, right, h))
    else:
        # source is taller than target -> crop top/bottom
        new_h = int(round(w / target_ratio))
        top = (h - new_h) // 2
        bottom = top + new_h
        return img.crop((0, top, w, bottom))


def split_landscape_exact(img: Image.Image) -> Tuple[Image.Image, Image.Image]:
    w, h = img.size
    # For even widths, split exactly in half. For odd widths, remove the
    # center column so both halves are identical width (center crop).
    mid = w // 2
    if w % 2 == 0:
        left = img.crop((0, 0, mid, h))
        right = img.crop((mid, 0, w, h))
    else:
        # left: 0..mid-1 (width = mid)
        # right: mid+1..w-1 (width = w - (mid+1) == mid)
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


def render_framed_full(
    img: Image.Image,
    target_size: Tuple[int, int],
    baseline: int,
    frame_color: Tuple[int, int, int],
    allow_upscale: bool,
) -> Tuple[Image.Image, BorderSpec]:
    target_w, target_h = target_size
    avail_w = target_w - (2 * baseline)
    avail_h = target_h - (2 * baseline)
    if avail_w <= 0 or avail_h <= 0:
        raise ValueError("Baseline frame width is too large for target size")

    out = Image.new("RGB", (target_w, target_h), frame_color)
    resized = resize_to_fit(img, avail_w, avail_h, allow_upscale)
    new_w, new_h = resized.size

    # Symmetric centering: split the leftover gap evenly; when gap is odd
    # the extra pixel will be placed on the right/bottom side.
    gap_x = avail_w - new_w
    gap_y = avail_h - new_h
    x = baseline + (gap_x // 2)
    y = baseline + (gap_y // 2)
    out.paste(resized, (x, y))

    border = BorderSpec(
        left=x,
        top=y,
        right=target_w - (x + new_w),
        bottom=target_h - (y + new_h),
    )
    return out, border


def render_framed_split_half(
    img: Image.Image,
    side: str,
    target_size: Tuple[int, int],
    baseline: int,
    frame_color: Tuple[int, int, int],
    allow_upscale: bool,
) -> Tuple[Image.Image, BorderSpec]:
    if side not in {"left", "right"}:
        raise ValueError("side must be 'left' or 'right'")

    target_w, target_h = target_size
    split_baseline = split_frame_baseline(baseline)
    avail_w = target_w - split_baseline
    avail_h = target_h - (2 * baseline)
    if avail_w <= 0 or avail_h <= 0:
        raise ValueError("Baseline frame width is too large for target size")

    resized = resize_to_fit(img, avail_w, avail_h, allow_upscale)
    new_w, new_h = resized.size

    out = Image.new("RGB", (target_w, target_h), frame_color)
    # Symmetric vertical centering
    gap_y = avail_h - new_h
    y = baseline + (gap_y // 2)

    if side == "left":
        x = target_w - new_w
        out.paste(resized, (x, y))
        border = BorderSpec(
            left=x,
            top=y,
            right=0,
            bottom=target_h - (y + new_h),
        )
    else:
        x = 0
        out.paste(resized, (x, y))
        border = BorderSpec(
            left=0,
            top=y,
            right=target_w - new_w,
            bottom=target_h - (y + new_h),
        )

    return out, border


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


def summarize_source_images(cfg: AppConfig) -> Tuple[int, int, int]:
    source_files = list_source_images(cfg)
    landscapes = 0
    portraits = 0
    for p in source_files:
        img = load_image(p)
        mode = classify_source_image(img)
        if mode == "landscape_split":
            landscapes += 1
        else:
            portraits += 1
    return len(source_files), portraits, landscapes


def process_all(
    cfg: AppConfig,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
    log_callback: Optional[Callable[[str], None]] = print,
) -> Tuple[List[ProcessRecord], RunStats, Dict[str, BorderSpec]]:
    ensure_output_dirs(cfg)
    files = list_source_images(cfg)

    records: List[ProcessRecord] = []
    stats = RunStats()
    framed_borders: Dict[str, BorderSpec] = {}

    total = len(files)
    for idx, src in enumerate(files, start=1):
        try:
            img, exif_bytes, icc_profile = load_image_and_metadata(src)
            stem = src.stem
            suffix = ".jpg"

            mode = classify_source_image(img)

            if mode == "landscape_split":
                stats.landscapes += 1
                left_img, right_img = split_landscape_exact(img)
                # For landscape splits, process each half into portrait 3:4
                # orientation by center-cropping to the framed aspect ratio,
                # then resize processed outputs to the exact target size
                # (e.g., 1080x1440 for 3:4). Framed outputs remain the
                # configured `target_size` with baseline frames applied.
                target_w, target_h = cfg.target_size

                # Left half -> process
                left_cropped = crop_to_aspect(left_img, target_w, target_h)
                left_proc = resize_exact(left_cropped, target_w, target_h)
                proc_left = cfg.processed_dir / f"{stem}_L{suffix}"
                save_jpeg(left_proc, proc_left, cfg, exif_bytes=exif_bytes, icc_profile=icc_profile)

                # Right half -> process
                right_cropped = crop_to_aspect(right_img, target_w, target_h)
                right_proc = resize_exact(right_cropped, target_w, target_h)
                proc_right = cfg.processed_dir / f"{stem}_R{suffix}"
                save_jpeg(right_proc, proc_right, cfg, exif_bytes=exif_bytes, icc_profile=icc_profile)

                stats.processed_written += 2

                # Create framed outputs (these will be target_size images with
                # frame baseline applied). Use the cropped halves (not the
                # resized full-target images) so the framing produces the
                # expected inner padding and baseline behavior.
                framed_left, border_left = render_framed_split_half(
                    left_cropped,
                    side="left",
                    target_size=cfg.target_size,
                    baseline=cfg.baseline_frame_width,
                    frame_color=cfg.frame_color,
                    allow_upscale=cfg.allow_upscale,
                )
                framed_right, border_right = render_framed_split_half(
                    right_cropped,
                    side="right",
                    target_size=cfg.target_size,
                    baseline=cfg.baseline_frame_width,
                    frame_color=cfg.frame_color,
                    allow_upscale=cfg.allow_upscale,
                )

                fr_left = cfg.framed_dir / f"{stem}_L{suffix}"
                fr_right = cfg.framed_dir / f"{stem}_R{suffix}"
                save_jpeg(framed_left, fr_left, cfg, exif_bytes=exif_bytes, icc_profile=icc_profile)
                save_jpeg(framed_right, fr_right, cfg, exif_bytes=exif_bytes, icc_profile=icc_profile)
                stats.framed_written += 2

                framed_borders[fr_left.name] = border_left
                framed_borders[fr_right.name] = border_right

                records.append(
                    ProcessRecord(
                        source_name=src.name,
                        mode="landscape_split",
                        processed_outputs=[proc_left.name, proc_right.name],
                        framed_outputs=[fr_left.name, fr_right.name],
                    )
                )
            else:
                stats.portraits += 1
                # For portrait/square inputs, center-crop to the framed aspect
                # ratio first so taller images are trimmed equally top/bottom
                # (and wider images trimmed left/right) before encoding.
                target_w, target_h = cfg.target_size
                cropped = crop_to_aspect(img, target_w, target_h)
                proc_img = resize_exact(cropped, target_w, target_h)

                proc_out = cfg.processed_dir / f"{stem}{suffix}"
                save_jpeg(proc_img, proc_out, cfg, exif_bytes=exif_bytes, icc_profile=icc_profile)
                stats.processed_written += 1

                framed_img, border = render_framed_full(
                    cropped,
                    target_size=cfg.target_size,
                    baseline=cfg.baseline_frame_width,
                    frame_color=cfg.frame_color,
                    allow_upscale=cfg.allow_upscale,
                )
                fr_out = cfg.framed_dir / f"{stem}{suffix}"
                save_jpeg(framed_img, fr_out, cfg, exif_bytes=exif_bytes, icc_profile=icc_profile)
                stats.framed_written += 1

                framed_borders[fr_out.name] = border

                records.append(
                    ProcessRecord(
                        source_name=src.name,
                        mode="portrait_or_square",
                        processed_outputs=[proc_out.name],
                        framed_outputs=[fr_out.name],
                    )
                )

            if progress_callback is not None:
                progress_callback(idx, total, src.name)
            elif log_callback is not None:
                log_callback(f"OK: {src.name}")
        except Exception as exc:  # noqa: BLE001
            stats.errors += 1
            if log_callback is not None:
                log_callback(f"ERROR: {src.name}: {exc}")

    if progress_callback is not None:
        progress_callback(total, total, "Complete")

    return records, stats, framed_borders


def validate_outputs(
    cfg: AppConfig,
    framed_borders: Dict[str, BorderSpec],
) -> None:
    src_files = list_source_images(cfg)

    landscapes: List[Path] = []
    portraits: List[Path] = []
    for p in src_files:
        img = load_image(p)
        mode = classify_source_image(img)
        (landscapes if mode == "landscape_split" else portraits).append(p)

    processed_files = sorted([p.name for p in cfg.processed_dir.glob("*.jpg")])
    framed_files = sorted([p.name for p in cfg.framed_dir.glob("*.jpg")])

    expected = len(portraits) + 2 * len(landscapes)
    assert len(processed_files) == expected, (
        f"Processed count mismatch: expected {expected}, got {len(processed_files)}"
    )
    assert len(framed_files) == expected, (
        f"Framed count mismatch: expected {expected}, got {len(framed_files)}"
    )

    for p in landscapes:
        assert p.name not in processed_files, (
            f"Landscape original found in processed output: {p.name}"
        )
        assert f"{p.stem}_L.jpg" in processed_files
        assert f"{p.stem}_R.jpg" in processed_files
        assert f"{p.stem}_L.jpg" in framed_files
        assert f"{p.stem}_R.jpg" in framed_files

    for framed_name in framed_files:
        with Image.open(cfg.framed_dir / framed_name) as img:
            assert img.size == cfg.target_size, (
                f"Framed output is not {cfg.target_size}: {framed_name}, got {img.size}"
            )

    for processed_name in processed_files:
        with Image.open(cfg.processed_dir / processed_name) as img:
            assert img.size == cfg.target_size, (
                f"Processed output is not {cfg.target_size}: {processed_name}, got {img.size}"
            )

    for name, b in framed_borders.items():
        split_baseline = split_frame_baseline(cfg.baseline_frame_width)
        if name.endswith("_L.jpg"):
            assert b.right == 0, f"Left split must have zero right border: {name}"
            assert b.left >= split_baseline, (
                f"Left split outer border below baseline: {name}, left={b.left}"
            )
            assert b.top >= cfg.baseline_frame_width
            assert b.bottom >= cfg.baseline_frame_width
        elif name.endswith("_R.jpg"):
            assert b.left == 0, f"Right split must have zero left border: {name}"
            assert b.right >= split_baseline, (
                f"Right split outer border below baseline: {name}, right={b.right}"
            )
            assert b.top >= cfg.baseline_frame_width
            assert b.bottom >= cfg.baseline_frame_width
        else:
            assert b.left >= cfg.baseline_frame_width
            assert b.right >= cfg.baseline_frame_width
            assert b.top >= cfg.baseline_frame_width
            assert b.bottom >= cfg.baseline_frame_width


def bytes_to_kb(path: Path) -> float:
    return path.stat().st_size / 1024.0


def size_diagnostics_lines(
    cfg: AppConfig,
    records: List[ProcessRecord],
    sample_count: int = 8,
) -> List[str]:
    lines: List[str] = []
    for rec in records[:sample_count]:
        src = cfg.source_dir / rec.source_name
        proc = cfg.processed_dir / rec.processed_outputs[0]
        frm = cfg.framed_dir / rec.framed_outputs[0]
        lines.append(
            f"{rec.source_name}: {bytes_to_kb(src):.1f} -> {bytes_to_kb(proc):.1f} -> {bytes_to_kb(frm):.1f}"
        )
    return lines


def run_basic_tests() -> None:
    test_img = Image.new("RGB", (2161, 1440), (10, 20, 30))
    left, right = split_landscape_exact(test_img)
    # For odd widths we remove the center column so both halves are equal.
    assert left.width == right.width
    expected_sum = test_img.width - (1 if test_img.width % 2 == 1 else 0)
    assert left.width + right.width == expected_sum
    assert left.height == test_img.height
    assert right.height == test_img.height

    assert is_landscape(Image.new("RGB", (2000, 1000), (1, 2, 3)))
    assert not is_landscape(Image.new("RGB", (1000, 1000), (1, 2, 3)))
    assert classify_source_image(Image.new("RGB", (1000, 1000), (1, 2, 3))) == "portrait_or_square"
    assert classify_source_image(Image.new("RGB", (2000, 1000), (1, 2, 3))) == "landscape_split"
    assert classify_source_image(Image.new("RGB", (4000, 2666), (1, 2, 3))) == "landscape_split"
    assert classify_source_image(Image.new("RGB", (1001, 1000), (1, 2, 3))) == "landscape_split"
    assert classify_source_image(Image.new("RGB", (2001, 1000), (1, 2, 3))) == "landscape_split"
    # Square and taller images are treated as portraits
    assert classify_source_image(Image.new("RGB", (1000, 1000), (1, 2, 3))) == "portrait_or_square"
    assert classify_source_image(Image.new("RGB", (1000, 1300), (1, 2, 3))) == "portrait_or_square"

    framed, border = render_framed_full(
        Image.new("RGB", (960, 960), (50, 60, 70)),
        target_size=(1080, 1080),
        baseline=60,
        frame_color=(255, 255, 255),
        allow_upscale=True,
    )
    assert framed.size == (1080, 1080)
    assert border.left == 60
    assert border.right == 60
    assert border.top == 60
    assert border.bottom == 60

    # Symmetric padding with odd gap: a 100x100 image into 111x111 target
    framed_odd, border_odd = render_framed_full(
        Image.new("RGB", (100, 100), (50, 60, 70)),
        target_size=(111, 111),
        baseline=0,
        frame_color=(255, 255, 255),
        allow_upscale=True,
    )
    assert framed_odd.size == (111, 111)
    # gap = 11 -> left = 5, right = 6 (right gets the extra pixel)
    assert abs(border_odd.right - border_odd.left) <= 1

    left_framed, left_border = render_framed_split_half(
        Image.new("RGB", (1080, 1080), (1, 1, 1)),
        side="left",
        target_size=(1080, 1080),
        baseline=40,
        frame_color=(255, 255, 255),
        allow_upscale=False,
    )
    right_framed, right_border = render_framed_split_half(
        Image.new("RGB", (1080, 1080), (1, 1, 1)),
        side="right",
        target_size=(1080, 1080),
        baseline=40,
        frame_color=(255, 255, 255),
        allow_upscale=False,
    )
    assert left_framed.size == (1080, 1080)
    assert right_framed.size == (1080, 1080)
    split_baseline = split_frame_baseline(40)
    assert left_border.right == 0
    assert left_border.left == 80
    assert left_border.top == 40
    assert left_border.bottom == 40
    assert right_border.left == 0
    assert right_border.right == 80
    assert right_border.top == 40
    assert right_border.bottom == 40

    try:
        render_framed_split_half(
            Image.new("RGB", (1080, 1080), (1, 1, 1)),
            side="bad",
            target_size=(1080, 1080),
            baseline=40,
            frame_color=(255, 255, 255),
            allow_upscale=True,
        )
        raise AssertionError("Expected ValueError for invalid side")
    except ValueError:
        pass


def run_collage_tests() -> None:
    background = Image.new("RGB", (4000, 1440), (30, 40, 50))
    foregrounds = [
        Image.new("RGB", (1400, 1000), (200, 10, 10)),
        Image.new("RGB", (1600, 1200), (10, 200, 10)),
        Image.new("RGB", (1800, 1300), (10, 10, 200)),
    ]

    master, panels, borders = build_collage(background, foregrounds, (1080, 1440), 0.9)

    assert master.size == (3240, 1440)
    assert len(panels) == 3
    assert len(borders) == 3
    for panel in panels:
        assert panel.size == (1080, 1440)
    for border in borders:
        assert border.left >= 0
        assert border.top >= 0
        assert border.right >= 0
        assert border.bottom >= 0
