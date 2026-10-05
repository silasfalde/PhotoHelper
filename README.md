# Photo Helper

Photo Helper is a single installable CLI for six workflows:

- framing and splitting Instagram-style source photos
- building collages from one background and ordered foregrounds
- stitching panoramas from ordered image folders
- center-cropping horizontal images to a target ratio
- combining two images side by side at a target ratio
- finding and copying matching raw NEF files

The reusable image logic lives in the `photo_helper` package, and the CLI dispatches to subcommands such as `framer`, `collage`, `combine`, `crop-ratio`, `panorama`, and `find-raws`.

Input directories should contain images that are square, taller, or moderately wide. Standard landscape images are split into two contiguous panels, while images that are approximately 2:1 are split into three contiguous panels. Standard landscape images also get a `_full.jpg` framed output containing the complete source image with vertical white space. All processed and framed outputs are resized to the exact target dimensions.

## Requirements

- Python 3.10+
- pip

Install dependencies:

python -m pip install -r requirements.txt

Install the CLI so it is executable from anywhere:

python -m pip install -e .

After that, run:

photohelper --help

## Quick Start

Run against any directory of images:

photohelper framer /path/to/source-images

You can still run the compatibility script form:

./photo_helper.py framer /path/to/source-images

Default outputs are created next to the source directory:

- instagram (processed images at exact target size)
- instagram-framed (framed images at exact target size with baseline)

## CLI Usage

Basic form:

photohelper framer SOURCE_DIR [options]

Discover help directly in CLI:

- photohelper --help
- photohelper framer --help
- photohelper collage --help
- photohelper combine --help
- photohelper crop-ratio --help
- photohelper panorama --help
- photohelper find-raws --help

Common options:

- --processed PATH
- --framed PATH
- --width INT (default 1080)
- --ratio W:H (default 3:4, for example 3:4 or 4:3)
- --height INT (optional explicit override)
- --frame-width INT (default 30)
- --color R,G,B (default 255,255,255)
- --extensions .jpg,.jpeg
- --no-upscale
- --reencode-portraits
- --validate
- --run-tests
- --quiet

Example with explicit output folders:

photohelper framer ./instagram --processed ./instagram-processed --framed ./instagram-framed --validate

Example flags for maize borders:
--border-width 13 --border-color 255,203,5

By default, framed outputs are portrait `3:4` (`1080x1440`). Use `--ratio 4:3` for landscape framing. The normal landscape split still produces `_L.jpg` and `_R.jpg`, plus `_full.jpg` containing the complete horizontal source. Approximately 2:1 images continue to produce three split outputs.

## Collage CLI

Create a master collage and per-panel outputs from one background image and one or more foreground images.

Basic form:

photohelper collage BACKGROUND FOREGROUND [FOREGROUND ...] [options]

The foreground images are placed left-to-right in the order you pass them.

Common options:

- --output PATH
- --width INT (default 1080)
- --height INT (default 1440)
- --scale FLOAT (default 0.78)
- --border-width INT (default 0)
- --border-color R,G,B (default 255,255,255)
- --jpeg-quality INT
- --jpeg-subsampling INT
- --validate
- --run-tests
- --quiet

Example:

photohelper collage --border-color 255,255,255 --border-width 40 ...

Example using the included test images:

photohelper collage ./collage-test-images/background.jpg ./collage-test-images/foreground-1.jpg ./collage-test-images/foreground-2.jpg ./collage-test-images/foreground-3.jpg --output ./collage-test-images/test-collage --validate

Example with maize foreground borders:

photohelper collage ./collage-test-images/background.jpg ./collage-test-images/foreground-1.jpg ./collage-test-images/foreground-2.jpg ./collage-test-images/foreground-3.jpg --output ./collage-test-images/test-collage --border-width 18 --border-color 255,203,5 --validate

The tool crops the background to an aspect ratio of roughly N:4, where N is the number of foreground images, then slices it into N vertical 1080x1440 panels. Each foreground is center-cropped to 3:4, scaled down slightly, and centered in its panel so some background remains visible.

Outputs are written to a folder next to the background image by default, using:

- master.jpg for the full-width collage
- panel_01.jpg, panel_02.jpg, and so on for the individual 1080x1440 panel images

## Combine CLI

Place two images of any dimensions side by side. Each image is center-cropped to half of the target ratio (for the default 6:4, each becomes 3:4), so a 2:3 photo and a 3:4 photo combine cleanly.

```text
photohelper combine LEFT.jpg RIGHT.jpg [--output COMBINED.jpg] [--ratio 6:4]
```

The output is a single JPEG with the first image on the left. Both halves are scaled to the smaller crop's height, so nothing is upscaled. By default it is written next to the left input as `LEFT_combined.jpg`.

## Panorama CLI

Create a single center-focused rectangular panorama from an ordered sequence of images (NEF or common formats) in a directory. Images are ordered using natural numeric sorting (so DSC_2 comes before DSC_10).

Basic usage:

photohelper panorama /path/to/source-nefs --output ./panorama-out --name panorama.tiff

Options:

- `--output PATH` : Directory to write the panorama (default: current working directory).
- `--name NAME` : Output filename (default: `panorama.tiff`).
- `--max-width INT` / `--max-height INT` : Optionally downscale inputs for memory/CPU savings.
- `--quiet` : Suppress progress logs.

Notes and limitations:

- The CLI reads Nikon NEF files via `rawpy` and stitches using OpenCV feature matching. By default the output is a 16-bit TIFF (`.tiff`) to preserve pixel detail. Writing a native Nikon NEF is not supported by this tool; producing a DNG or NEF would require external/proprietary converters or SDKs.
- Stitching full-resolution NEF files can use a lot of memory and CPU. Use `--max-width`/`--max-height` to limit resource use if needed.
- The stitcher centers the panorama on the middle image, aligns images pairwise, blends seams using a simple feathering approach, and crops to a rectangular region that preserves as many input pixels as possible.

## Crop Ratio CLI

Center-crop every horizontal (width > height) image in a directory to a target aspect ratio (default `4:3`). Portrait and square images, and images already matching the target ratio, are copied through unchanged.

Basic form:

photohelper crop-ratio SOURCE_DIR [options]

Common options:

- --output PATH (write to a new directory)
- --in-place (allow writing back into SOURCE_DIR, overwriting originals)
- --ratio W:H (default 4:3)
- --extensions .jpg,.jpeg
- --jpeg-quality INT
- --jpeg-subsampling INT
- --quiet

Example: convert a `standard` export folder of mixed horizontal formats (e.g. 6x4 / 3:2) into 4:3, overwriting the originals in place:

photohelper crop-ratio ./standard --ratio 4:3 --in-place

Example writing to a new folder instead of overwriting:

photohelper crop-ratio ./standard --output ./standard-4x3 --ratio 4:3

## Raw Finder CLI

Find and copy NEF files that match JPG names:

photohelper find-raws ./maize-and-blue /path/to/raw-source --output ./select-raws

Common options:

- --output PATH
- --timeout INT
- -v / --verbose

## Notebook Usage

Open and run [photo_framer.ipynb](photo_framer.ipynb).

Suggested order:

1. Run Cell 3 (imports)
2. Run Cell 5 (configuration)
3. Run Cell 11 (source summary)
4. Run Cell 13 (basic tests, optional)
5. Run Cells 15 and 16 (processing, validation, diagnostics, preview)

The notebook imports shared logic from the `photo_helper` package so notebook and CLI behavior stay aligned.

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
- [photo_helper/panorama.py](photo_helper/panorama.py): panorama stitching
- [photo_helper/reformat.py](photo_helper/reformat.py): center-crop horizontal images to a target aspect ratio
- [photo_helper.py](photo_helper.py): consolidated CLI entrypoint
- [photo_framer.ipynb](photo_framer.ipynb): interactive workflow and preview
- [requirements.txt](requirements.txt): dependencies
