#!/usr/bin/env python3
"""Create a panorama from a directory of images (NEF or common formats)."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

from photo_helper.panorama import list_images_sorted, stitch_images_from_paths, save_tiff


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Stitch NEF or image files in a directory into one panorama.")
    parser.add_argument("source_dir", type=Path, help="Directory containing ordered input images.")
    parser.add_argument("--output-dir", type=Path, help="Output directory (default: repository root/current working dir)")
    parser.add_argument("--output-name", type=str, default="panorama.tiff", help="Output filename (default: panorama.tiff)")
    parser.add_argument("--max-width", type=int, help="Optional max width to downscale inputs for memory savings")
    parser.add_argument("--max-height", type=int, help="Optional max height to downscale inputs for memory savings")
    parser.add_argument("--quiet", action="store_true")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    source = args.source_dir.resolve()
    if not source.exists():
        parser.error(f"Source directory does not exist: {source}")

    output_dir = (args.output_dir or Path.cwd()).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / args.output_name

    files = list_images_sorted(source)
    if not files:
        parser.error("No files found in source directory")

    if not args.quiet:
        print(f"Stitching {len(files)} images from {source}")

    pano, size = stitch_images_from_paths(files, max_width=args.max_width, max_height=args.max_height)
    save_tiff(pano, output_path)

    if not args.quiet:
        print(f"Wrote panorama: {output_path} ({size[0]}x{size[1]})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
