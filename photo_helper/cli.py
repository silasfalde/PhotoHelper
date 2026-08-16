from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from ._version import __version__
from .collage import build_collage, compute_collage_canvas_size, run_collage_tests, validate_collage_outputs
from .common import AppConfig, load_image, load_image_and_metadata, save_collage_output
from .framing_runtime import process_all, run_basic_tests, size_diagnostics_lines, summarize_source_images, validate_outputs
from .raw import copy_matched_raws, find_jpg_files

SUBCOMMANDS = {"framer", "collage", "panorama", "find-raws"}


class HelpFormatter(argparse.ArgumentDefaultsHelpFormatter, argparse.RawTextHelpFormatter):
    """Formatter that preserves example newlines while showing defaults."""


def parse_rgb_color(raw: str) -> tuple[int, int, int]:
    parts = [part.strip() for part in raw.split(",")]
    if len(parts) != 3:
        raise ValueError("Color must be three comma-separated integers like 255,203,5")

    values = tuple(int(part) for part in parts)
    if any(value < 0 or value > 255 for value in values):
        raise ValueError("Each color component must be between 0 and 255")
    return values


def parse_aspect_ratio(raw: str) -> tuple[int, int]:
    parts = [part.strip() for part in raw.split(":")]
    if len(parts) != 2:
        raise ValueError("Aspect ratio must be formatted like W:H, for example 1:1 or 3:4")

    width, height = (int(part) for part in parts)
    if width <= 0 or height <= 0:
        raise ValueError("Aspect ratio values must be positive integers")
    return width, height


def target_height_for_ratio(target_width: int, ratio: tuple[int, int]) -> int:
    ratio_width, ratio_height = ratio
    return int(round(target_width * ratio_height / ratio_width))


def print_heading(title: str) -> None:
    print()
    print(title)
    print("-" * len(title))


def print_kv(label: str, value: object, width: int = 20) -> None:
    print(f"{label:<{width}} {value}")


def add_framer_subcommand(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser(
        "framer",
        help="Frame and process images from a source directory.",
        description="Frame and process Instagram images from any source directory.",
        formatter_class=HelpFormatter,
        epilog=(
            "Examples:\n"
            "  photohelper framer /path/to/source-images\n"
            "  photohelper framer ./instagram --framed-aspect-ratio 4:3 --validate\n"
            "  photohelper framer ./src --processed-dir ./instagram --framed-dir ./instagram-framed"
        ),
    )
    parser.add_argument("source_dir", type=Path, help="Directory containing input images.")
    parser.add_argument("--processed-dir", type=Path, help="Output directory for processed images.")
    parser.add_argument("--framed-dir", type=Path, help="Output directory for framed images.")
    parser.add_argument("--target-width", type=int, default=1080)
    parser.add_argument(
        "--framed-aspect-ratio",
        default="1:1",
        help="Aspect ratio for framed outputs when target height is not explicitly set, in W:H form.",
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
    parser.add_argument("--validate", action="store_true", help="Run output validation checks after processing.")
    parser.add_argument("--run-tests", action="store_true", help="Run built-in core function sanity tests before processing.")
    parser.add_argument("--quiet", action="store_true", help="Suppress per-file progress logs.")
    parser.set_defaults(handler=run_framer)


def add_collage_subcommand(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser(
        "collage",
        help="Create a master collage and panel outputs.",
        description="Create Instagram-ready photo collages from one background and ordered foreground images.",
        formatter_class=HelpFormatter,
        epilog=(
            "Examples:\n"
            "  photohelper collage bg.jpg fg1.jpg fg2.jpg fg3.jpg --output-dir ./collage-out\n"
            "  photohelper collage bg.jpg fg1.jpg fg2.jpg --foreground-border-width 18 --foreground-border-color 255,203,5"
        ),
    )
    parser.add_argument("background", type=Path, help="Background image used for the full collage.")
    parser.add_argument("foregrounds", type=Path, nargs="+", help="Ordered foreground images to place left-to-right.")
    parser.add_argument("--output-dir", type=Path, help="Directory for collage outputs.")
    parser.add_argument("--panel-width", type=int, default=1080)
    parser.add_argument("--panel-height", type=int, default=1440)
    parser.add_argument(
        "--foreground-scale",
        type=float,
        default=0.78,
        help="Scale factor for foreground images inside each panel.",
    )
    parser.add_argument(
        "--foreground-border-width",
        type=int,
        default=0,
        help="Optional border width to add around each foreground image. Set to 0 to disable.",
    )
    parser.add_argument(
        "--foreground-border-color",
        default="255,255,255",
        help="Border color as R,G,B.",
    )
    parser.add_argument("--jpeg-quality", type=int, default=100)
    parser.add_argument("--jpeg-subsampling", type=int, default=0)
    parser.add_argument("--validate", action="store_true", help="Validate output dimensions after saving.")
    parser.add_argument("--run-tests", action="store_true", help="Run built-in collage sanity tests before processing.")
    parser.add_argument("--quiet", action="store_true", help="Suppress per-file progress logs.")
    parser.set_defaults(handler=run_collage)


def add_panorama_subcommand(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser(
        "panorama",
        help="Stitch an ordered directory of images into one panorama.",
        description="Stitch NEF or image files in a directory into one panorama.",
        formatter_class=HelpFormatter,
        epilog=(
            "Examples:\n"
            "  photohelper panorama ./ordered-nefs --output-dir ./panorama-out\n"
            "  photohelper panorama ./ordered-nefs --output-name trip-pano.tiff --max-width 3200"
        ),
    )
    parser.add_argument("source_dir", type=Path, help="Directory containing ordered input images.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Output directory (default: current working directory)",
    )
    parser.add_argument("--output-name", type=str, default="panorama.tiff", help="Output filename")
    parser.add_argument("--max-width", type=int, help="Optional max width to downscale inputs for memory savings")
    parser.add_argument("--max-height", type=int, help="Optional max height to downscale inputs for memory savings")
    parser.add_argument("--quiet", action="store_true")
    parser.set_defaults(handler=run_panorama)


def add_find_raws_subcommand(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser(
        "find-raws",
        help="Find and copy raw NEF photos matching JPGs.",
        description="Find and copy raw NEF photos matching JPGs from a source tree.",
        formatter_class=HelpFormatter,
        epilog=(
            "Examples:\n"
            "  photohelper find-raws ./maize-and-blue /mnt/archive --output-dir ./select-raws\n"
            "  photohelper find-raws ./jpgs /mnt/archive --timeout 60 -v"
        ),
    )
    parser.add_argument("jpg_dir", type=Path, help="Directory containing JPG files to match")
    parser.add_argument("raw_source", type=Path, help="Root directory to search for NEF files")
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Output directory for copied NEF files (default: jpg-dir parent + '/select-raws')",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging for debugging.")
    parser.add_argument("--timeout", type=int, default=30, help="Timeout in seconds for downloading offloaded files")
    parser.set_defaults(handler=run_find_raws)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="photohelper",
        description="One CLI for framing, collages, panoramas, and raw matching.",
        formatter_class=HelpFormatter,
        epilog=(
            "Quick examples:\n"
            "  photohelper framer /path/to/source-images\n"
            "  photohelper collage background.jpg fg1.jpg fg2.jpg\n"
            "  photohelper panorama ./ordered-nefs --output-dir ./out\n"
            "  photohelper find-raws ./maize-and-blue /mnt/archive --output-dir ./select-raws\n\n"
            "Run 'photohelper <subcommand> --help' for subcommand-specific options."
        ),
    )
    parser.add_argument("--version", action="version", version=f"Photo Helper {__version__}")
    subparsers = parser.add_subparsers(dest="command")
    add_framer_subcommand(subparsers)
    add_collage_subcommand(subparsers)
    add_panorama_subcommand(subparsers)
    add_find_raws_subcommand(subparsers)
    return parser


def run_framer(parser: argparse.ArgumentParser, args: argparse.Namespace) -> int:
    source_dir = args.source_dir.resolve()
    processed_dir = (args.processed_dir or source_dir.parent / "instagram").resolve()
    framed_dir = (args.framed_dir or source_dir.parent / "instagram-framed").resolve()

    if args.target_width <= 0:
        parser.error("--target-width must be positive")

    if args.target_height is None:
        try:
            aspect_ratio = parse_aspect_ratio(args.framed_aspect_ratio)
        except ValueError as exc:
            parser.error(str(exc))
        target_height = target_height_for_ratio(args.target_width, aspect_ratio)
    else:
        target_height = args.target_height

    if target_height <= 0:
        parser.error("--target-height must be positive")

    if args.baseline_frame_width < 0:
        parser.error("--baseline-frame-width must be non-negative")

    try:
        frame_color = parse_rgb_color(args.frame_color)
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
    print_heading("Framer")
    print_kv("Source directory", cfg.source_dir)
    print_kv("Processed directory", cfg.processed_dir)
    print_kv("Framed directory", cfg.framed_dir)
    print_kv("Discovered files", discovered)
    print_kv("Portraits / squares", portraits)
    print_kv("Landscape files", landscapes)

    log_callback = None if args.quiet else print
    records, stats, framed_borders = process_all(cfg, progress_callback=None, log_callback=log_callback)

    if args.validate:
        validate_outputs(cfg, framed_borders)
        print("Validation passed.")

    print_heading("Results")
    print_kv("Portraits / squares", stats.portraits)
    print_kv("Landscape files", stats.landscapes)
    print_kv("Processed written", stats.processed_written)
    print_kv("Framed written", stats.framed_written)
    print_kv("Errors", stats.errors)

    if records:
        print_heading("File size diagnostics (KB)")
        print("source -> processed -> framed")
        for line in size_diagnostics_lines(cfg, records):
            print(line)

    return 1 if stats.errors > 0 else 0


def run_collage(parser: argparse.ArgumentParser, args: argparse.Namespace) -> int:
    background_path = args.background.resolve()
    foreground_paths = tuple(path.resolve() for path in args.foregrounds)
    output_dir = (args.output_dir or background_path.parent / f"{background_path.stem}-collage").resolve()
    panel_size = (args.panel_width, args.panel_height)

    if args.panel_width <= 0 or args.panel_height <= 0:
        parser.error("--panel-width and --panel-height must be positive")
    if args.foreground_scale <= 0:
        parser.error("--foreground-scale must be positive")
    if args.foreground_border_width < 0:
        parser.error("--foreground-border-width must be non-negative")

    try:
        foreground_border_color = parse_rgb_color(args.foreground_border_color)
    except ValueError as exc:
        parser.error(str(exc))

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
        foreground_border_width=args.foreground_border_width,
        foreground_border_color=foreground_border_color,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    master_path = output_dir / "master.jpg"

    save_collage_output(
        master_image,
        master_path,
        jpeg_quality=args.jpeg_quality,
        jpeg_subsampling=args.jpeg_subsampling,
        exif_bytes=exif_bytes,
        icc_profile=icc_profile,
    )

    if not args.quiet:
        print_heading("Collage")
        print_kv("Background", background_path)
        print_kv("Foregrounds", len(foreground_paths))
        print_kv("Output directory", output_dir)
        print_kv("Master size", f"{master_image.size[0]}x{master_image.size[1]}")

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

    if args.validate:
        validate_collage_outputs(panel_size, master_path, panel_files)
        print("Validation passed.")

    total_w, total_h = compute_collage_canvas_size(panel_size, len(foreground_paths))
    print_heading("Results")
    print_kv("Canvas size", f"{total_w}x{total_h}")
    print_kv("Master file", master_path)
    print_kv("Panel files", len(panel_files))

    return 0


def run_panorama(parser: argparse.ArgumentParser, args: argparse.Namespace) -> int:
    from .panorama import list_images_sorted, save_tiff, stitch_images_from_paths

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
        print_heading("Panorama")
        print_kv("Source directory", source)
        print_kv("Input files", len(files))

    pano, size = stitch_images_from_paths(files, max_width=args.max_width, max_height=args.max_height)
    save_tiff(pano, output_path)

    if not args.quiet:
        print_heading("Results")
        print_kv("Output file", output_path)
        print_kv("Panorama size", f"{size[0]}x{size[1]}")
    return 0


def run_find_raws(parser: argparse.ArgumentParser, args: argparse.Namespace) -> int:
    jpg_dir = args.jpg_dir.resolve()
    raw_source = args.raw_source.resolve()

    if args.output_dir:
        output_dir = args.output_dir.resolve()
    else:
        output_dir = jpg_dir.parent / "select-raws"

    try:
        if not jpg_dir.exists():
            parser.error(f"JPG directory does not exist: {jpg_dir}")

        if not raw_source.exists():
            parser.error(f"Raw source directory does not exist: {raw_source}")

        print_heading("Raw Finder")
        print_kv("JPG directory", jpg_dir)
        print_kv("Raw source", raw_source)
        print_kv("Output directory", output_dir)

        jpg_files = find_jpg_files(jpg_dir)
        jpg_count = len(jpg_files)

        if jpg_count == 0:
            print("No JPG files found.")
            return 0

        print_kv("JPG files found", jpg_count)
        print()

        stats = copy_matched_raws(
            jpg_dir=jpg_dir,
            raw_source=raw_source,
            output_dir=output_dir,
            verbose=args.verbose,
            timeout_seconds=args.timeout,
            status_callback=print,
        )

        print_heading("Results")
        print_kv("JPG files processed", jpg_count)
        print_kv("Matched with NEF", f"{stats['matched']} ({100 * stats['matched'] // jpg_count if jpg_count else 0}%)")
        print_kv("Copied", stats["copied"])
        print_kv("Skipped duplicates", stats["duplicate"])
        print_kv("Skipped offloaded", stats["skipped_offloaded"])
        print_kv("No match found", stats["missing"])
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"Error: {exc}", file=sys.stderr)
        if args.verbose:
            import traceback

            traceback.print_exc()
        return 1


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = list(sys.argv[1:] if argv is None else argv)

    if not args:
        parser.print_help()
        return 0

    if args[0] not in SUBCOMMANDS and not args[0].startswith("-"):
        args = ["framer", *args]

    parsed = parser.parse_args(args)
    if not hasattr(parsed, "handler"):
        parser.error("A subcommand is required: framer, collage, panorama, or find-raws")

    return parsed.handler(parser, parsed)
