# PhotoHelper Agent Instructions

PhotoHelper is a Python CLI for four distinct image processing workflows: **framing** (split & frame photos), **collage** (composite layered images), **panorama** (stitch sequences), and **raw file matching**.

## Quick Start for Agents

### Installation & Testing
```bash
# Initial setup
python -m pip install -r requirements.txt
python -m pip install -e .              # Installs CLI: photohelper, photo-helper

# Verify CLI works
photohelper --help

# Run tests
python -m pytest tests/
photohelper framer SOURCE --run-tests   # Built-in smoke tests
```

### Architecture at a Glance
- **[common.py](photo_helper/common.py)**: Shared image utilities (`crop_to_aspect`, `resize_exact`, `AppConfig`)
- **[framing.py](photo_helper/framing.py)** + **[framing_runtime.py](photo_helper/framing_runtime.py)**: Classify images (square/portrait/landscape pairs/triplets), split & frame, resize to exact target dimensions
- **[collage.py](photo_helper/collage.py)**: Composite N foregrounds onto a background, optional borders & scaling
- **[panorama.py](photo_helper/panorama.py)**: SIFT/ORB feature detection + OpenCV stitching; supports NEF (via rawpy) & standard formats
- **[raw.py](photo_helper/raw.py)**: Match JPGs to NEF files by suffix or base name; Google Drive cloud file handling
- **[cli.py](photo_helper/cli.py)**: Command dispatcher; auto-selects `framer` if first arg is a path

### Key Conventions
- **Aspect ratio tolerance**: ±0.02 (prevents misclassification near boundaries)
- **Panel naming**: 2-way split uses `_L`, `_R`; 3-way uses `_01`, `_02`, `_03`
- **Data classes**: All configs are frozen dataclasses (AppConfig, CollageConfig)
- **Metadata handling**: EXIF + ICC profiles extracted on load, reapplied on save (except panorama TIFF output)
- **Python version**: ≥3.10 required
- **Top-level [photo_helper.py](photo_helper.py)**: Compatibility wrapper; delegates to `photo_helper.cli:main()`

## Workflow Reference

### Framing (`framing`, `framing_runtime` modules)
**What it does**: Split wide images into 2–3 equal panels, optionally add decorative borders, resize to exact dimensions.
- **Inputs**: Source directory with images (square, portrait, or landscape)
- **Outputs**: `instagram/` (processed), `instagram-framed/` (with frame) subdirectories
- **Key CLI options**:
  - `--target-width` (default: 1080)
  - `--framed-aspect-ratio` W:H (default: 1:1)
  - `--baseline-frame-width` (default: 60)
  - `--frame-color R,G,B` (default: 255,255,255)
  - `--no-upscale`, `--reencode-portraits`, `--validate`
- **Entry point**: [framing_runtime.py](photo_helper/framing_runtime.py) → `process_all()`

### Collage (`collage` module)
**What it does**: Layer N foreground images on a background at fixed positions & sizes.
- **Inputs**: One background image + N foreground images (passed as positional args)
- **Outputs**: `master.jpg` + per-panel `panel_NN.jpg`
- **Key CLI options**:
  - `--output-dir` (required)
  - `--panel-width`, `--panel-height` (default: 1080×1440)
  - `--foreground-scale` (default: 0.78)
  - `--foreground-border-width`, `--foreground-border-color`
- **Entry point**: [collage.py](photo_helper/collage.py) → `build_collage()`

### Panorama (`panorama` module)
**What it does**: Stitch an ordered sequence of images into a single panorama.
- **Inputs**: Directory of images (auto-sorted by filename)
- **Outputs**: 16-bit TIFF in current working directory (EXIF not preserved)
- **Supports**: NEF (via rawpy) + PIL formats
- **Key CLI options**:
  - `--output` (default: `panorama.tiff`)
  - `--max-width`, `--max-height` (downscale before stitching to save memory)
  - `--blender` (alternative blending method)
- **Entry point**: [panorama.py](photo_helper/panorama.py) → `stitch_images_from_paths()`
- **Pitfall**: Requires opencv-python + rawpy + tifffile + numpy. Install with `pip install opencv-python rawpy tifffile numpy`.

### Raw Matching (`raw` module)
**What it does**: Find & copy NEF raw files matching a directory of JPGs.
- **Inputs**: JPG directory + raw source directory
- **Outputs**: Statistics + per-file matching report
- **Matching logic**: Tries suffix match (`DSC_3988_L.jpg` → `DSC_3988_L.nef`), then base name fallback
- **Key CLI options**:
  - `--validate`, `--timeout` (default: 30s for cloud file sync)
- **Entry point**: [raw.py](photo_helper/raw.py) → `copy_matched_raws()`
- **macOS-specific**: Handles Google Drive cloud files via xattr; logs warnings on Windows/Linux if files offloaded

## Testing Strategy

| Test Type | Command | Notes |
|-----------|---------|-------|
| **Unit & integration** | `pytest tests/` | Covers framing, collage, raw matching |
| **Panorama** | `pytest tests/test_panorama.py` | Skipped if cv2/rawpy/tifffile missing |
| **Framing smoke** | `photohelper framer SRC --run-tests` | Runs internal framing_runtime tests |
| **Collage smoke** | `photohelper collage BG FG --run-tests` | Runs internal collage tests |
| **Legacy namespace** | Tests in test_photo_helper.py | Verifies backward-compat exports from `__init__.py` |

## Common Pitfalls & Solutions

| Issue | Root Cause | Mitigation |
|-------|-----------|-----------|
| Panorama stitching fails | Missing cv2/rawpy/tifffile/numpy | `pip install opencv-python rawpy tifffile numpy` |
| Memory exhaustion (panorama) | Loads full u16 RGB (4× u8 size) | Use `--max-width`/`--max-height` to downscale |
| Aspect ratio misclassification | Image near boundary (±0.02 tolerance) | Check `size_diagnostics_lines()` output with `--validate` |
| EXIF/ICC not preserved (panorama) | TIFF output doesn't embed | By design; apply profiles externally if needed |
| Raw matching finds no files | Wrong suffix or base name mismatch | Use `--validate` on JPG dir; check naming against raw files |
| Google Drive cloud files timeout | Files not synced; macOS-only handling | Increase `--timeout`; ensure full local sync first |
| Panel output confusion | Default paths vary per workflow | Framer: parent/instagram; Collage: explicit --output-dir required |
| `--no-upscale` centering artifacts | Small images enlarged then centered | This is expected; use `--no-upscale` to disable enlargement |

## Module Dependency Map

```
CLI (cli.py)
  ├─→ framing_runtime.py → framing.py → common.py
  ├─→ collage.py → common.py
  ├─→ panorama.py (cv2, rawpy, tifffile, numpy)
  └─→ raw.py (PIL, pathlib)
```

## File Organization

```
photo_helper/
  __init__.py          # Public API exports (framing, collage, raw modules)
  _version.py          # Version constant
  cli.py               # Command dispatcher & argument parsing
  common.py            # Shared image utilities (crop, resize, classify)
  framing.py           # Framing logic (split + render functions)
  framing_runtime.py   # Framing orchestration (process_all)
  collage.py           # Collage rendering (build_collage)
  panorama.py          # Panorama stitching (stitch_images_from_paths)
  raw.py               # Raw file matching (copy_matched_raws)

tests/
  test_photo_helper.py # Framing, collage, raw matching tests
  test_panorama.py     # Panorama-specific tests

pyproject.toml         # Project metadata & dependencies
requirements.txt       # Pinned versions for reproducibility
photo_helper.py        # Top-level compatibility wrapper
README.md              # User-facing documentation
```

## When to Use CLI vs. Direct Module Import

**CLI** (`photohelper framer ...`):
- Best for end-user workflows
- Handles argument parsing, validation, diagnostics
- Provides progress feedback

**Direct import** (`from photo_helper import process_all`):
- Best for scripts, tests, programmatic reuse
- Fine-grained control over AppConfig
- No CLI overhead

Both are equally valid; check [__init__.py](photo_helper/__init__.py) for public exports.

## Debugging Tips

1. **Use `--validate`** on any workflow for detailed per-file diagnostics
2. **Check `size_diagnostics_lines()`** output to understand image classification
3. **Test with small batches first** when adjusting JPEG quality or scaling factors
4. **Inspect `ProcessRecord` objects** (framing) for detailed metadata about each panel
5. **Raw matching**: Run with `--validate` to see which JPGs found matches and which didn't
6. **Panorama memory**: Monitor with `--max-width`/`--max-height` on large image sequences

## See Also
- [README.md](README.md) — User-facing workflow examples & CLI reference
- [RAW_FINDER_README.md](RAW_FINDER_README.md) — Raw matching workflow documentation
