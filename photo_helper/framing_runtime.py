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
    load_image_and_metadata,
    resize_exact,
    save_jpeg,
)
from .framing import (
    render_framed_full,
    render_framed_split_half,
    render_framed_split_third,
    run_basic_tests,
    split_source_into_processed_panels,
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
                split_panels = split_source_into_processed_panels(img, cfg.target_size, panel_count=3)

                left_proc, middle_proc, right_proc = split_panels
                proc_left = cfg.processed_dir / f"{stem}_01{suffix}"
                save_jpeg(left_proc, proc_left, cfg, exif_bytes=exif_bytes, icc_profile=icc_profile)
                proc_middle = cfg.processed_dir / f"{stem}_02{suffix}"
                save_jpeg(middle_proc, proc_middle, cfg, exif_bytes=exif_bytes, icc_profile=icc_profile)
                proc_right = cfg.processed_dir / f"{stem}_03{suffix}"
                save_jpeg(right_proc, proc_right, cfg, exif_bytes=exif_bytes, icc_profile=icc_profile)

                stats.processed_written += 3

                framed_left, border_left = render_framed_split_third(
                    left_proc,
                    position="left",
                    target_size=cfg.target_size,
                    baseline=cfg.baseline_frame_width,
                    frame_color=cfg.frame_color,
                    allow_upscale=cfg.allow_upscale,
                )
                framed_middle, border_middle = render_framed_split_third(
                    middle_proc,
                    position="middle",
                    target_size=cfg.target_size,
                    baseline=cfg.baseline_frame_width,
                    frame_color=cfg.frame_color,
                    allow_upscale=cfg.allow_upscale,
                )
                framed_right, border_right = render_framed_split_third(
                    right_proc,
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
                split_panels = split_source_into_processed_panels(img, cfg.target_size, panel_count=2)

                left_proc, right_proc = split_panels
                proc_left = cfg.processed_dir / f"{stem}_L{suffix}"
                save_jpeg(left_proc, proc_left, cfg, exif_bytes=exif_bytes, icc_profile=icc_profile)
                proc_right = cfg.processed_dir / f"{stem}_R{suffix}"
                save_jpeg(right_proc, proc_right, cfg, exif_bytes=exif_bytes, icc_profile=icc_profile)

                stats.processed_written += 2

                framed_left, border_left = render_framed_split_half(
                    left_proc,
                    side="left",
                    target_size=cfg.target_size,
                    baseline=cfg.baseline_frame_width,
                    frame_color=cfg.frame_color,
                    allow_upscale=cfg.allow_upscale,
                )
                framed_right, border_right = render_framed_split_half(
                    right_proc,
                    side="right",
                    target_size=cfg.target_size,
                    baseline=cfg.baseline_frame_width,
                    frame_color=cfg.frame_color,
                    allow_upscale=cfg.allow_upscale,
                )
                framed_full, border_full = render_framed_full(
                    img,
                    target_size=cfg.target_size,
                    baseline=cfg.baseline_frame_width,
                    frame_color=cfg.frame_color,
                    allow_upscale=cfg.allow_upscale,
                )

                fr_left = cfg.framed_dir / f"{stem}_L{suffix}"
                fr_right = cfg.framed_dir / f"{stem}_R{suffix}"
                fr_full = cfg.framed_dir / f"{stem}_full{suffix}"
                save_jpeg(framed_left, fr_left, cfg, exif_bytes=exif_bytes, icc_profile=icc_profile)
                save_jpeg(framed_right, fr_right, cfg, exif_bytes=exif_bytes, icc_profile=icc_profile)
                save_jpeg(framed_full, fr_full, cfg, exif_bytes=exif_bytes, icc_profile=icc_profile)
                stats.framed_written += 3

                framed_borders[fr_left.name] = border_left
                framed_borders[fr_right.name] = border_right
                framed_borders[fr_full.name] = border_full

                records.append(
                    ProcessRecord(
                        source_name=src.name,
                        mode="landscape_pair",
                        processed_outputs=[proc_left.name, proc_right.name],
                        framed_outputs=[fr_left.name, fr_right.name, fr_full.name],
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
