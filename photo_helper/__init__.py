"""Top-level PhotoHelper package.

This package provides a lightweight, forward-facing API that groups the
project's capabilities (framing, collage, raw-finding) under a single
`photo_helper` namespace while delegating implementation to the existing
`photo_framer` modules for backward compatibility.
"""

from ._version import __version__

# Re-export framing/collage core
from photo_framer.core import (  # noqa: F401
    AppConfig,
    CollageConfig,
    CollageRecord,
    CollageStats,
    BorderSpec,
    ProcessRecord,
    RunStats,
    bytes_to_kb,
    build_collage,
    compute_collage_canvas_size,
    fit_inside,
    is_landscape,
    list_source_images,
    load_image,
    load_image_and_metadata,
    process_all,
    render_collage_panel,
    render_framed_full,
    render_framed_split_half,
    run_collage_tests,
    run_basic_tests,
    save_collage_output,
    save_jpeg,
    size_diagnostics_lines,
    split_landscape_exact,
    summarize_source_images,
    validate_collage_outputs,
    validate_outputs,
)

# Re-export raw finder
from photo_framer.raw_finder import (  # noqa: F401
    copy_matched_raws,
    ensure_file_downloaded,
    extract_base_name,
    find_all_raw_files,
    find_jpg_files,
    is_file_offloaded,
    match_raw_to_jpg,
    summarize_results,
)

__all__ = [
    # version
    "__version__",
    # framing/collage
    "AppConfig",
    "CollageConfig",
    "CollageRecord",
    "CollageStats",
    "BorderSpec",
    "ProcessRecord",
    "RunStats",
    "bytes_to_kb",
    "build_collage",
    "compute_collage_canvas_size",
    "fit_inside",
    "is_landscape",
    "list_source_images",
    "load_image",
    "load_image_and_metadata",
    "process_all",
    "render_collage_panel",
    "render_framed_full",
    "render_framed_split_half",
    "run_collage_tests",
    "run_basic_tests",
    "save_collage_output",
    "save_jpeg",
    "size_diagnostics_lines",
    "split_landscape_exact",
    "summarize_source_images",
    "validate_collage_outputs",
    "validate_outputs",
    # raw finder
    "copy_matched_raws",
    "ensure_file_downloaded",
    "extract_base_name",
    "find_all_raw_files",
    "find_jpg_files",
    "is_file_offloaded",
    "match_raw_to_jpg",
    "summarize_results",
]
