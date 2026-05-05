#!/usr/bin/env python3
"""Find and copy raw NEF photos matching JPGs in a directory."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from photo_framer.raw_finder import (
    copy_matched_raws,
    find_jpg_files,
    summarize_results,
)


def build_parser() -> argparse.ArgumentParser:
    """Build argument parser for the CLI."""
    # Determine default raw source (Google Drive path)
    google_drive_root = Path.home() / "Library" / "CloudStorage" / "GoogleDrive-sfalde@umich.edu" / "My Drive"
    
    parser = argparse.ArgumentParser(
        description="Find and copy raw NEF photos matching JPGs from a Google Drive directory.",
    )
    parser.add_argument(
        "--jpg-dir",
        type=Path,
        default=Path.cwd() / "maize-and-blue",
        help="Directory containing JPG files to match (default: ./maize-and-blue)",
    )
    parser.add_argument(
        "--raw-source",
        type=Path,
        default=google_drive_root,
        help=f"Root directory to search for NEF files (default: {google_drive_root})",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Output directory for copied NEF files (default: jpg-dir parent + '-raws')",
    )
    parser.add_argument(
        "--google-drive-root",
        type=Path,
        dest="google_drive_root_arg",
        help="Override the Google Drive root path (if mounted differently)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging for debugging.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="Timeout in seconds for downloading offloaded files (default: 30)",
    )
    return parser


def main() -> int:
    """Main CLI entry point."""
    parser = build_parser()
    args = parser.parse_args()
    
    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(levelname)s: %(message)s",
    )
    logger = logging.getLogger(__name__)
    
    # Resolve paths
    jpg_dir = args.jpg_dir.resolve()
    raw_source = args.google_drive_root_arg.resolve() if args.google_drive_root_arg else args.raw_source.resolve()
    
    # Determine output directory
    if args.output_dir:
        output_dir = args.output_dir.resolve()
    else:
        # Default: jpg_dir parent + "-raws"
        output_dir = jpg_dir.parent / f"{jpg_dir.name}-raws"
    
    try:
        # Validate input directories
        if not jpg_dir.exists():
            logger.error(f"JPG directory does not exist: {jpg_dir}")
            return 1
        
        if not raw_source.exists():
            logger.error(f"Raw source directory does not exist: {raw_source}")
            return 1
        
        logger.info(f"JPG directory:     {jpg_dir}")
        logger.info(f"Raw source:        {raw_source}")
        logger.info(f"Output directory:  {output_dir}")
        logger.info("")
        
        # Find JPGs to process
        jpg_files = find_jpg_files(jpg_dir)
        jpg_count = len(jpg_files)
        
        if jpg_count == 0:
            logger.warning(f"No JPG files found in {jpg_dir}")
            return 0
        
        logger.info(f"Found {jpg_count} JPG files to process")
        logger.info("")
        
        # Copy matched raws
        stats = copy_matched_raws(
            jpg_dir=jpg_dir,
            raw_source=raw_source,
            output_dir=output_dir,
            verbose=args.verbose,
        )
        
        # Print summary
        summarize_results(stats, jpg_count)
        
        return 0
    
    except Exception as e:
        logger.error(f"Error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
