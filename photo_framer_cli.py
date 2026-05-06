#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Tuple

from photo_helper import (
    AppConfig,
    process_all,
    run_basic_tests,
    size_diagnostics_lines,
    summarize_source_images,
    validate_outputs,
)


def parse_frame_color(raw: str) -> Tuple[int, int, int]:
    parts = [p.strip() for p in raw.split(",")]
    if len(parts) != 3:
        raise ValueError("Frame color must be three comma-separated integers like 255,255,255")

    values = tuple(int(p) for p in parts)
    if any(v < 0 or v > 255 for v in values):
        raise ValueError("Each frame color component must be between 0 and 255")
    return values  # type: ignore[return-value]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Frame and process Instagram images from any source directory.",
    )
    parser.add_argument(
        "source_dir",
        type=Path,
        help="Directory containing input images.",
    )
    parser.add_argument(
        "--processed-dir",
        type=Path,
        help="Output directory for processed (split/copied) images.",
    )
    parser.add_argument(
        "--framed-dir",
        type=Path,
        help="Output directory for framed images.",
    )
    parser.add_argument("--target-width", type=int, default=1080)
    parser.add_argument(
        "--framed-aspect-ratio",
        choices=("1:1", "4:3", "3:4"),
        default="1:1",
        help="Aspect ratio for framed outputs when target height is not explicitly set.",
    )
    parser.add_argument(
        "--target-height",
        type=int,
        help="Explicit framed output height. If omitted, it is derived from --framed-aspect-ratio.",
    )
    parser.add_argument("--baseline-frame-width", type=int, default=30)
    parser.add_argument("--frame-color", default="255,255,255")
    parser.add_argument("--jpeg-quality", type=int, default=100)
    parser.add_argument("--jpeg-subsampling", type=int, default=0)
    parser.add_argument(
        "--extensions",
        default=".jpg,.jpeg",
        help="Comma-separated list of image extensions to include.",
    )
    parser.add_argument(
        "--no-upscale",
        action="store_true",
        help="Disable upscaling small images when framing.",
    )
    parser.add_argument(
        "--reencode-portraits",
        action="store_true",
        help="Re-encode portrait/square files instead of copying originals into processed output.",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Run output validation checks after processing.",
    )
    parser.add_argument(
        "--run-tests",
        action="store_true",
        help="Run built-in core function sanity tests before processing.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress per-file progress logs.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    source_dir = args.source_dir.resolve()
    processed_dir = (args.processed_dir or source_dir.parent / "instagram").resolve()
    framed_dir = (args.framed_dir or source_dir.parent / "instagram-framed").resolve()

    if args.target_height is None:
        if args.framed_aspect_ratio == "1:1":
            target_height = args.target_width
        elif args.framed_aspect_ratio == "4:3":
            target_height = int(round(args.target_width * 3 / 4))
        else:  # 3:4
            target_height = int(round(args.target_width * 4 / 3))
    else:
        target_height = args.target_height

    try:
        frame_color = parse_frame_color(args.frame_color)
    except ValueError as exc:
        parser.error(str(exc))

    if args.run_tests:
        run_basic_tests()
        print("Basic tests passed.")

    cfg = AppConfig(
        source_dir=source_dir,
        processed_dir=processed_dir,
        framed_dir=framed_dir,
        target_size=(args.target_width, target_height),
        baseline_frame_width=args.baseline_frame_width,
        frame_color=frame_color,
        allow_upscale=not args.no_upscale,
        image_extensions=tuple(ext.strip() for ext in args.extensions.split(",") if ext.strip()),
        jpeg_quality=args.jpeg_quality,
        jpeg_subsampling=args.jpeg_subsampling,
        copy_portraits_without_reencode=not args.reencode_portraits,
    )

    discovered, portraits, landscapes = summarize_source_images(cfg)
    print(f"Source dir: {cfg.source_dir}")
    print(f"Processed dir: {cfg.processed_dir}")
    print(f"Framed dir: {cfg.framed_dir}")
    print(f"Discovered source files: {discovered}")
    print(f"Portrait/square inputs: {portraits}")
    print(f"Landscape inputs: {landscapes}")

    log_callback = None if args.quiet else print
    records, stats, framed_borders = process_all(cfg, progress_callback=None, log_callback=log_callback)

    if args.validate:
        validate_outputs(cfg, framed_borders)
        print("Validation checks passed.")

    print("Final run summary:")
    print(f"Portrait/square inputs: {stats.portraits}")
    print(f"Landscape inputs: {stats.landscapes}")
    print(f"Processed files written: {stats.processed_written}")
    print(f"Framed files written: {stats.framed_written}")
    print(f"Errors: {stats.errors}")

    if records:
        print("\nFile size diagnostics (KB)")
        print("source -> processed -> framed")
        for line in size_diagnostics_lines(cfg, records):
            print(line)

    return 1 if stats.errors > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
