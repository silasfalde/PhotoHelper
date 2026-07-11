from __future__ import annotations

from typing import Callable, Dict, List, Optional, Tuple

from PIL import Image

from .common import (
    AppConfig,
    BorderSpec,
    ProcessRecord,
    RunStats,
    classify_source_image,
    crop_to_aspect,
    ensure_output_dirs,
    list_source_images,
    load_image,
    load_image_and_metadata,
    resize_exact,
    save_jpeg,
    split_landscape_exact,
    split_landscape_into_three,
)
from .framing import (
    render_framed_full,
    render_framed_split_half,
    render_framed_split_third,
    run_basic_tests,
    size_diagnostics_lines,
    summarize_source_images,
    validate_outputs,
)


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


_PROCESS_ALL_EXEC = r'''
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
'''

exec(_PROCESS_ALL_EXEC, globals())
