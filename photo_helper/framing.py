from __future__ import annotations

from typing import Callable, Dict, List, Optional, Tuple

from PIL import Image, ImageOps

from .common import (
    AppConfig,
    BorderSpec,
    ProcessRecord,
    RunStats,
    bytes_to_kb,
    classify_source_image,
    crop_to_aspect,
    ensure_output_dirs,
    is_landscape,
    list_source_images,
    load_image,
    load_image_and_metadata,
    resize_exact,
    resize_to_fit,
    save_jpeg,
    split_frame_baseline,
    split_landscape_exact,
    split_landscape_into_three,
)


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
    gap_y = avail_h - new_h
    y = baseline + (gap_y // 2)

    if side == "left":
        x = target_w - new_w
        out.paste(resized, (x, y))
        border = BorderSpec(left=x, top=y, right=0, bottom=target_h - (y + new_h))
    else:
        x = 0
        out.paste(resized, (x, y))
        border = BorderSpec(left=0, top=y, right=target_w - new_w, bottom=target_h - (y + new_h))

    return out, border


def render_framed_split_third(
    img: Image.Image,
    position: str,
    target_size: Tuple[int, int],
    baseline: int,
    frame_color: Tuple[int, int, int],
    allow_upscale: bool,
) -> Tuple[Image.Image, BorderSpec]:
    if position not in {"left", "middle", "right"}:
        raise ValueError("position must be 'left', 'middle', or 'right'")

    target_w, target_h = target_size
    split_baseline = split_frame_baseline(baseline)
    avail_h = target_h - (2 * baseline)
    if position == "middle":
        avail_w = target_w
    else:
        avail_w = target_w - split_baseline
    if avail_w <= 0 or avail_h <= 0:
        raise ValueError("Baseline frame width is too large for target size")

    if position == "middle":
        resized = resize_exact(crop_to_aspect(img, target_w, avail_h), target_w, avail_h)
    else:
        resized = resize_to_fit(img, avail_w, avail_h, allow_upscale)
    new_w, new_h = resized.size

    out = Image.new("RGB", (target_w, target_h), frame_color)
    gap_y = avail_h - new_h
    y = baseline + (gap_y // 2)

    if position == "left":
        x = target_w - new_w
        out.paste(resized, (x, y))
        border = BorderSpec(left=x, top=y, right=0, bottom=target_h - (y + new_h))
    elif position == "middle":
        x = 0
        out.paste(resized, (x, y))
        border = BorderSpec(
            left=0,
            top=y,
            right=0,
            bottom=target_h - (y + new_h),
        )
    else:
        x = 0
        out.paste(resized, (x, y))
        border = BorderSpec(left=0, top=y, right=target_w - new_w, bottom=target_h - (y + new_h))

    return out, border


def summarize_source_images(cfg: AppConfig) -> Tuple[int, int, int]:
    source_files = list_source_images(cfg)
    landscapes = 0
    portraits = 0
    for path in source_files:
        img = load_image(path)
        mode = classify_source_image(img)
        if mode.startswith("landscape_"):
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

            if mode == "landscape_triplet":
                stats.landscapes += 1
                left_img, middle_img, right_img = split_landscape_into_three(img)
                target_w, target_h = cfg.target_size

                left_cropped = crop_to_aspect(left_img, target_w, target_h)
                left_proc = resize_exact(left_cropped, target_w, target_h)
                proc_left = cfg.processed_dir / f"{stem}_01{suffix}"
                save_jpeg(left_proc, proc_left, cfg, exif_bytes=exif_bytes, icc_profile=icc_profile)

                middle_cropped = crop_to_aspect(middle_img, target_w, target_h)
                middle_proc = resize_exact(middle_cropped, target_w, target_h)
                proc_middle = cfg.processed_dir / f"{stem}_02{suffix}"
                save_jpeg(middle_proc, proc_middle, cfg, exif_bytes=exif_bytes, icc_profile=icc_profile)

                right_cropped = crop_to_aspect(right_img, target_w, target_h)
                right_proc = resize_exact(right_cropped, target_w, target_h)
                proc_right = cfg.processed_dir / f"{stem}_03{suffix}"
                save_jpeg(right_proc, proc_right, cfg, exif_bytes=exif_bytes, icc_profile=icc_profile)

                stats.processed_written += 3

                framed_left, border_left = render_framed_split_third(
                    left_cropped,
                    position="left",
                    target_size=cfg.target_size,
                    baseline=cfg.baseline_frame_width,
                    frame_color=cfg.frame_color,
                    allow_upscale=cfg.allow_upscale,
                )
                framed_middle, border_middle = render_framed_split_third(
                    middle_cropped,
                    position="middle",
                    target_size=cfg.target_size,
                    baseline=cfg.baseline_frame_width,
                    frame_color=cfg.frame_color,
                    allow_upscale=cfg.allow_upscale,
                )
                framed_right, border_right = render_framed_split_third(
                    right_cropped,
                    position="right",
                    target_size=cfg.target_size,
                    baseline=cfg.baseline_frame_width,
                    frame_color=cfg.frame_color,
                    allow_upscale=cfg.allow_upscale,
                )

                fr_left = cfg.framed_dir / f"{stem}_01{suffix}"
                fr_middle = cfg.framed_dir / f"{stem}_02{suffix}"
                fr_right = cfg.framed_dir / f"{stem}_03{suffix}"
                save_jpeg(framed_left, fr_left, cfg, exif_bytes=exif_bytes, icc_profile=icc_profile)
                save_jpeg(framed_middle, fr_middle, cfg, exif_bytes=exif_bytes, icc_profile=icc_profile)
                save_jpeg(framed_right, fr_right, cfg, exif_bytes=exif_bytes, icc_profile=icc_profile)
                stats.framed_written += 3

                framed_borders[fr_left.name] = border_left
                framed_borders[fr_middle.name] = border_middle
                framed_borders[fr_right.name] = border_right

                records.append(
                    ProcessRecord(
                        source_name=src.name,
                        mode="landscape_triplet",
                        processed_outputs=[proc_left.name, proc_middle.name, proc_right.name],
                        framed_outputs=[fr_left.name, fr_middle.name, fr_right.name],
                    )
                )
            elif mode == "landscape_pair":
                stats.landscapes += 1
                left_img, right_img = split_landscape_exact(img)
                target_w, target_h = cfg.target_size

                left_cropped = crop_to_aspect(left_img, target_w, target_h)
                left_proc = resize_exact(left_cropped, target_w, target_h)
                proc_left = cfg.processed_dir / f"{stem}_L{suffix}"
                save_jpeg(left_proc, proc_left, cfg, exif_bytes=exif_bytes, icc_profile=icc_profile)

                right_cropped = crop_to_aspect(right_img, target_w, target_h)
                right_proc = resize_exact(right_cropped, target_w, target_h)
                proc_right = cfg.processed_dir / f"{stem}_R{suffix}"
                save_jpeg(right_proc, proc_right, cfg, exif_bytes=exif_bytes, icc_profile=icc_profile)

                stats.processed_written += 2

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
                        mode="landscape_pair",
                        processed_outputs=[proc_left.name, proc_right.name],
                        framed_outputs=[fr_left.name, fr_right.name],
                    )
                )
            else:
                stats.portraits += 1
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


def validate_outputs(cfg: AppConfig, framed_borders: Dict[str, BorderSpec]) -> None:
    src_files = list_source_images(cfg)

    landscapes: List[Path] = []
    portraits: List[Path] = []
    for path in src_files:
        img = load_image(path)
        mode = classify_source_image(img)
        (landscapes if mode.startswith("landscape_") else portraits).append(path)

    processed_files = sorted([p.name for p in cfg.processed_dir.glob("*.jpg")])
    framed_files = sorted([p.name for p in cfg.framed_dir.glob("*.jpg")])

    expected = len(portraits)
    for path in landscapes:
        mode = classify_source_image(load_image(path))
        expected += 3 if mode == "landscape_triplet" else 2
    assert len(processed_files) == expected, (
        f"Processed count mismatch: expected {expected}, got {len(processed_files)}"
    )
    assert len(framed_files) == expected, (
        f"Framed count mismatch: expected {expected}, got {len(framed_files)}"
    )

    for path in landscapes:
        assert path.name not in processed_files, f"Landscape original found in processed output: {path.name}"
        mode = classify_source_image(load_image(path))
        if mode == "landscape_triplet":
            assert f"{path.stem}_01.jpg" in processed_files
            assert f"{path.stem}_02.jpg" in processed_files
            assert f"{path.stem}_03.jpg" in processed_files
            assert f"{path.stem}_01.jpg" in framed_files
            assert f"{path.stem}_02.jpg" in framed_files
            assert f"{path.stem}_03.jpg" in framed_files
        else:
            assert f"{path.stem}_L.jpg" in processed_files
            assert f"{path.stem}_R.jpg" in processed_files
            assert f"{path.stem}_L.jpg" in framed_files
            assert f"{path.stem}_R.jpg" in framed_files

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

    for name, border in framed_borders.items():
        split_baseline = split_frame_baseline(cfg.baseline_frame_width)
        if name.endswith("_L.jpg"):
            assert border.right == 0, f"Left split must have zero right border: {name}"
            assert border.left >= split_baseline, f"Left split outer border below baseline: {name}, left={border.left}"
            assert border.top >= cfg.baseline_frame_width
            assert border.bottom >= cfg.baseline_frame_width
        elif name.endswith("_R.jpg"):
            assert border.left == 0, f"Right split must have zero left border: {name}"
            assert border.right >= split_baseline, f"Right split outer border below baseline: {name}, right={border.right}"
            assert border.top >= cfg.baseline_frame_width
            assert border.bottom >= cfg.baseline_frame_width
        elif name.endswith("_01.jpg"):
            assert border.right == 0, f"Left split must have zero right border: {name}"
            assert border.left >= split_baseline, f"Left split outer border below baseline: {name}, left={border.left}"
            assert border.top >= cfg.baseline_frame_width
            assert border.bottom >= cfg.baseline_frame_width
        elif name.endswith("_02.jpg"):
            assert border.left == 0, f"Middle split must have zero left border: {name}, left={border.left}"
            assert border.right == 0, f"Middle split must have zero right border: {name}, right={border.right}"
            assert border.top >= cfg.baseline_frame_width
            assert border.bottom >= cfg.baseline_frame_width
        elif name.endswith("_03.jpg"):
            assert border.left == 0, f"Right split must have zero left border: {name}"
            assert border.right >= split_baseline, f"Right split outer border below baseline: {name}, right={border.right}"
            assert border.top >= cfg.baseline_frame_width
            assert border.bottom >= cfg.baseline_frame_width
        else:
            assert border.left >= cfg.baseline_frame_width
            assert border.right >= cfg.baseline_frame_width
            assert border.top >= cfg.baseline_frame_width
            assert border.bottom >= cfg.baseline_frame_width


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
    assert left.width == right.width
    expected_sum = test_img.width - (1 if test_img.width % 2 == 1 else 0)
    assert left.width + right.width == expected_sum
    assert left.height == test_img.height
    assert right.height == test_img.height

    first, middle, third = split_landscape_into_three(Image.new("RGB", (2161, 1440), (10, 20, 30)))
    assert first.height == middle.height == third.height == 1440
    assert first.width + middle.width + third.width == 2161

    assert is_landscape(Image.new("RGB", (2000, 1000), (1, 2, 3)))
    assert not is_landscape(Image.new("RGB", (1000, 1000), (1, 2, 3)))
    assert classify_source_image(Image.new("RGB", (1000, 1000), (1, 2, 3))) == "portrait_or_square"
    assert classify_source_image(Image.new("RGB", (1960, 1000), (1, 2, 3))) == "landscape_triplet"
    assert classify_source_image(Image.new("RGB", (2000, 1000), (1, 2, 3))) == "landscape_triplet"
    assert classify_source_image(Image.new("RGB", (4000, 2000), (1, 2, 3))) == "landscape_triplet"
    assert classify_source_image(Image.new("RGB", (2400, 1400), (1, 2, 3))) == "landscape_pair"
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

    framed_odd, border_odd = render_framed_full(
        Image.new("RGB", (100, 100), (50, 60, 70)),
        target_size=(111, 111),
        baseline=0,
        frame_color=(255, 255, 255),
        allow_upscale=True,
    )
    assert framed_odd.size == (111, 111)
    assert abs(border_odd.right - border_odd.left) <= 1

    left_framed, left_border = render_framed_split_third(
        Image.new("RGB", (1080, 1080), (1, 1, 1)),
        position="left",
        target_size=(1080, 1080),
        baseline=40,
        frame_color=(255, 255, 255),
        allow_upscale=False,
    )
    middle_framed, middle_border = render_framed_split_third(
        Image.new("RGB", (1080, 1080), (1, 1, 1)),
        position="middle",
        target_size=(1080, 1080),
        baseline=40,
        frame_color=(255, 255, 255),
        allow_upscale=False,
    )
    right_framed, right_border = render_framed_split_third(
        Image.new("RGB", (1080, 1080), (1, 1, 1)),
        position="right",
        target_size=(1080, 1080),
        baseline=40,
        frame_color=(255, 255, 255),
        allow_upscale=False,
    )
    assert left_framed.size == (1080, 1080)
    assert middle_framed.size == (1080, 1080)
    assert right_framed.size == (1080, 1080)
    split_baseline = split_frame_baseline(40)
    assert left_border.right == 0
    assert left_border.left == 80
    assert left_border.top == 40
    assert left_border.bottom == 40
    assert middle_border.left >= split_baseline
    assert middle_border.right >= split_baseline
    assert middle_border.top == 40
    assert middle_border.bottom == 40
    assert right_border.left == 0
    assert right_border.right == 80
    assert right_border.top == 40
    assert right_border.bottom == 40

    try:
        render_framed_split_third(
            Image.new("RGB", (1080, 1080), (1, 1, 1)),
            position="bad",
            target_size=(1080, 1080),
            baseline=40,
            frame_color=(255, 255, 255),
            allow_upscale=True,
        )
        raise AssertionError("Expected ValueError for invalid side")
    except ValueError:
        pass
