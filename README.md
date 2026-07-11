# Photo Helper

Photo Helper processes images from any input directory and produces:
- processed outputs (split landscape images or center-cropped portraits)
- framed outputs sized for Instagram-style posting
- collage outputs from a background image and ordered foreground images
- raw-photo copies matched to JPG names

The implementation now lives in the `photo_helper` package, with compatibility wrappers preserved under `photo_framer` for older notebook imports and scripts.

Input directories should contain images that are square, taller, or moderately wide. Standard landscape images are split into two contiguous panels, while images that are approximately 2:1 are split into three contiguous panels. All processed and framed outputs are resized to the exact target dimensions (e.g., 1080x1440 for 3:4).

The core logic lives in the Python package and is reused by both:
- a command line script
- the notebook

## Requirements

- Python 3.10+
- pip

Install dependencies:

python -m pip install -r requirements.txt

## Quick Start

Run against any directory of images:

python photo_framer_cli.py /path/to/source-images

You can also run the executable form:

./photo_framer_cli.py /path/to/source-images

Default outputs are created next to the source directory:
- instagram (processed images at exact target size)
- instagram-framed (framed images at exact target size with baseline)

## CLI Usage

Basic form:

python photo_framer_cli.py SOURCE_DIR [options]

Common options:
- --processed-dir PATH
- --framed-dir PATH
- --target-width INT (default 1080)
- --framed-aspect-ratio 1:1|4:3|3:4 (default 1:1, 3:4 is vertical)
- --target-height INT (optional explicit override)
- --baseline-frame-width INT (default 60)
- --frame-color R,G,B (default 255,255,255)
- --extensions .jpg,.jpeg
- --no-upscale
- --reencode-portraits
- --validate
- --run-tests
- --quiet

Example with explicit output folders:

python photo_framer_cli.py ./instagram --processed-dir ./instagram-processed --framed-dir ./instagram-framed --validate

Example flags for maize borders: 
--foreground-border-width 13 --foreground-border-color 255,203,5

By default, framed outputs are square. Use `--framed-aspect-ratio 4:3` for landscape or `--framed-aspect-ratio 3:4` for portrait framing.

## Collage CLI

Create a master collage and per-panel outputs from one background image and one or more foreground images.

Basic form:

python photo_collage_cli.py BACKGROUND FOREGROUND [FOREGROUND ...] [options]

The foreground images are placed left-to-right in the order you pass them.

Common options:
- --output-dir PATH
- --panel-width INT (default 1080)
- --panel-height INT (default 1440)
- --foreground-scale FLOAT (default 0.78)
- --foreground-border-width INT (default 0)
- --foreground-border-color R,G,B (default 255,255,255)
- --jpeg-quality INT
- --jpeg-subsampling INT
- --validate
- --run-tests
- --quiet

Example:

python photo_collage_cli.py --foreground-border-color 255,255,255 --foreground-border-width 40 ...

Example using the included test images:

python photo_collage_cli.py ./collage-test-images/background.jpg ./collage-test-images/foreground-1.jpg ./collage-test-images/foreground-2.jpg ./collage-test-images/foreground-3.jpg --output-dir ./collage-test-images/test-collage --validate

Example with maize foreground borders:

python photo_collage_cli.py ./collage-test-images/background.jpg ./collage-test-images/foreground-1.jpg ./collage-test-images/foreground-2.jpg ./collage-test-images/foreground-3.jpg --output-dir ./collage-test-images/test-collage --foreground-border-width 18 --foreground-border-color 255,203,5 --validate

The tool crops the background to an aspect ratio of roughly N:4, where N is the number of foreground images, then slices it into N vertical 1080x1440 panels. Each foreground is center-cropped to 3:4, scaled down slightly, and centered in its panel so some background remains visible.

Outputs are written to a folder next to the background image by default, using:
- master.jpg for the full-width collage
- panel_01.jpg, panel_02.jpg, and so on for the individual 1080x1440 panel images

## Panorama CLI

Create a single center-focused rectangular panorama from an ordered sequence of images (NEF or common formats) in a directory. Images are ordered using natural numeric sorting (so DSC_2 comes before DSC_10).

Basic usage:

python photo_panorama_cli.py /path/to/source-nefs --output-dir ./panorama-out --output-name panorama.tiff

Options:
- `--output-dir PATH` : Directory to write the panorama (default: current working directory).
- `--output-name NAME` : Output filename (default: `panorama.tiff`).
- `--max-width INT` / `--max-height INT` : Optionally downscale inputs for memory/CPU savings.
- `--quiet` : Suppress progress logs.

Notes and limitations:
- The CLI reads Nikon NEF files via `rawpy` and stitches using OpenCV feature matching. By default the output is a 16-bit TIFF (`.tiff`) to preserve pixel detail. Writing a native Nikon NEF is not supported by this tool; producing a DNG or NEF would require external/proprietary converters or SDKs.
- Stitching full-resolution NEF files can use a lot of memory and CPU. Use `--max-width`/`--max-height` to limit resource use if needed.
- The stitcher centers the panorama on the middle image, aligns images pairwise, blends seams using a simple feathering approach, and crops to a rectangular region that preserves as many input pixels as possible.


## Notebook Usage

Open and run [photo_framer.ipynb](photo_framer.ipynb).

Suggested order:
1. Run Cell 3 (imports)
2. Run Cell 5 (configuration)
3. Run Cell 11 (source summary)
4. Run Cell 13 (basic tests, optional)
5. Run Cells 15 and 16 (processing, validation, diagnostics, preview)

The notebook imports shared logic from the compatibility wrapper [photo_framer/core.py](photo_framer/core.py), which forwards to the new `photo_helper` submodules so notebook and CLI behavior stay aligned.

## Supported Files

By default, the tool processes:
- .jpg
- .jpeg

Use --extensions to customize accepted suffixes.

## Typical Workflow

1. Place source images in any folder.
2. Run the CLI with that folder path.
3. Check processed outputs in the processed folder.
4. Check framed outputs in the framed folder.
5. Use --validate when you want structural checks after processing.

## Project Structure

- [photo_helper/common.py](photo_helper/common.py): shared dataclasses and image/file helpers
- [photo_helper/framing.py](photo_helper/framing.py): framing and processing pipeline
- [photo_helper/collage.py](photo_helper/collage.py): collage rendering and validation
- [photo_helper/raw.py](photo_helper/raw.py): raw-photo finder and copier
- [photo_framer/core.py](photo_framer/core.py): legacy compatibility wrapper
- [photo_framer_cli.py](photo_framer_cli.py): framing command line entrypoint
- [photo_collage_cli.py](photo_collage_cli.py): collage command line entrypoint
- [find_raw_photos_cli.py](find_raw_photos_cli.py): raw-photo command line entrypoint
- [photo_framer.ipynb](photo_framer.ipynb): interactive workflow and preview
- [requirements.txt](requirements.txt): dependencies
