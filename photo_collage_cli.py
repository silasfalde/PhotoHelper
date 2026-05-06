#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from photo_framer.core import (
    build_collage,
    compute_collage_canvas_size,
    load_image,
    load_image_and_metadata,
    run_collage_tests,
    save_collage_output,
    validate_collage_outputs,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create Instagram-ready photo collages from one background and ordered foreground images.",
    )
    parser.add_argument(
        "background",
        type=Path,
        help="Background image used for the full collage.",
    )
    parser.add_argument(
        "foregrounds",
        type=Path,
        nargs="+",
        help="Ordered foreground images to place left-to-right.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Directory for collage outputs (default: background parent + '-collage').",
    )
    parser.add_argument("--panel-width", type=int, default=1080)
    parser.add_argument("--panel-height", type=int, default=1440)
    parser.add_argument(
        "--foreground-scale",
        type=float,
        default=0.82,
        help="Scale factor for foreground images inside each panel.",
    )
    parser.add_argument("--jpeg-quality", type=int, default=100)
    parser.add_argument("--jpeg-subsampling", type=int, default=0)
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate output dimensions after saving.",
    )
    parser.add_argument(
        "--run-tests",
        action="store_true",
        help="Run built-in collage sanity tests before processing.",
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

    background_path = args.background.resolve()
    foreground_paths = tuple(path.resolve() for path in args.foregrounds)
    output_dir = (args.output_dir or background_path.parent / f"{background_path.stem}-collage").resolve()
    panel_size = (args.panel_width, args.panel_height)

    if args.panel_width <= 0 or args.panel_height <= 0:
        parser.error("--panel-width and --panel-height must be positive")
    if args.foreground_scale <= 0:
        parser.error("--foreground-scale must be positive")

    if args.run_tests:
        run_collage_tests()
        print("Collage tests passed.")

    if not background_path.exists():
        parser.error(f"Background image does not exist: {background_path}")
    missing_foregrounds = [path for path in foreground_paths if not path.exists()]
    if missing_foregrounds:
        parser.error(f"Foreground image does not exist: {missing_foregrounds[0]}")

    background_img, exif_bytes, icc_profile = load_image_and_metadata(background_path)
    foreground_images = [load_image(path) for path in foreground_paths]

    master_image, panel_images, _ = build_collage(
        background_img,
        foreground_images,
        panel_size=panel_size,
        foreground_scale=args.foreground_scale,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    master_path = output_dir / "master.jpg"
    panel_paths = []

    save_collage_output(
        master_image,
        master_path,
        jpeg_quality=args.jpeg_quality,
        jpeg_subsampling=args.jpeg_subsampling,
        exif_bytes=exif_bytes,
        icc_profile=icc_profile,
    )

    if not args.quiet:
        print(f"Background: {background_path}")
        print(f"Foregrounds: {len(foreground_paths)}")
        print(f"Output dir: {output_dir}")
        print(f"Master size: {master_image.size[0]}x{master_image.size[1]}")

    panel_files = []
    for index, panel_image in enumerate(panel_images, start=1):
        panel_path = output_dir / f"panel_{index:02d}.jpg"
        save_collage_output(
            panel_image,
            panel_path,
            jpeg_quality=args.jpeg_quality,
            jpeg_subsampling=args.jpeg_subsampling,
            exif_bytes=exif_bytes,
            icc_profile=icc_profile,
        )
        panel_files.append(panel_path)
        if not args.quiet:
            print(f"Saved panel {index}: {panel_path.name}")

    if args.validate:
        validate_collage_outputs(panel_size, master_path, panel_files)
        print("Validation checks passed.")

    total_w, total_h = compute_collage_canvas_size(panel_size, len(foreground_paths))
    print(f"Created collage canvas: {total_w}x{total_h}")
    print(f"Saved master: {master_path}")
    print(f"Saved panels: {len(panel_files)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
