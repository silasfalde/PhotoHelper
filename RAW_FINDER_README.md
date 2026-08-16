# Raw Photo Finder

Find and copy raw NEF photos from Google Drive Cloud Storage that match JPGs in a directory.

## Overview

This tool scans a directory of JPG files and matches them with corresponding raw NEF (Nikon) files stored in your Google Drive. It then copies the matched raw files to an output directory. This is useful for archiving or processing raw versions of edited photos.

**Key Features:**
- Flexible name matching: matches `DSC_3988_L.jpg` to both `DSC_3988_L.nef` and `DSC_3988.nef`
- Automatic handling of offloaded Google Drive files (triggers download via macOS file system API)
- Recursive search through Google Drive subdirectories
- Prevents duplicate copies when multiple JPGs match the same raw file
- Detailed reporting with matching statistics

## Usage

### Basic usage (uses defaults):
```bash
photohelper find-raws
```

Default behavior:
- JPG directory: `./maize-and-blue/`
- Raw source: `/Users/silasfaldenew/Library/CloudStorage/GoogleDrive-sfalde@umich.edu/My Drive`
- Output: `./select-raws/`

### Custom JPG directory:
```bash
photohelper find-raws --jpg-dir /path/to/jpgs
```

### Custom output directory:
```bash
photohelper find-raws --output-dir /path/to/output
```

### Custom Google Drive location:
```bash
photohelper find-raws --raw-source /path/to/google/drive
```

Or override the detected path:
```bash
photohelper find-raws --google-drive-root /path/to/google/drive
```

### Verbose mode (detailed logging):
```bash
photohelper find-raws --verbose
```

### Adjust offloaded file download timeout:
```bash
photohelper find-raws --timeout 60  # 60 seconds instead of default 30
```

## How It Works

1. **JPG Discovery**: Scans the JPG directory for all `.jpg` files
2. **NEF Discovery**: Recursively scans the Google Drive directory for all `.nef` files
3. **Matching**: For each JPG, attempts to find a matching NEF:
   - First tries exact match with suffix (e.g., `DSC_3988_L.nef` for `DSC_3988_L.jpg`)
   - Falls back to base name match (e.g., `DSC_3988.nef` for `DSC_3988_L.jpg`)
4. **Download Handling**: For offloaded files, triggers automatic download by attempting to read the file
5. **Copy**: Copies matched NEF files to the output directory
6. **Deduplication**: Prevents copying the same NEF file multiple times if multiple JPGs match it

## Matching Logic

The tool uses flexible name matching to handle various photography workflows:

- `DSC_3988.jpg` → `DSC_3988.nef` ✓
- `DSC_3988_L.jpg` → `DSC_3988_L.nef` (preferred) or `DSC_3988.nef` (fallback)
- `DSC_3988_R.jpg` → `DSC_3988_R.nef` (preferred) or `DSC_3988.nef` (fallback)
- `DSC_3988_01.jpg` → `DSC_3988_01.nef` (preferred) or `DSC_3988.nef` (fallback)

## Google Drive Offloaded Files

The tool automatically handles Google Drive offloaded files (files not downloaded locally):

- Detects offloaded state using macOS file system attributes
- Triggers automatic download by attempting to read the file
- Waits up to 30 seconds (configurable) for the download to complete
- Logs warnings for files that remain offloaded after timeout
- **Does not fail** — continues processing other files

## Output Statistics

After processing, the tool displays a summary:

```
============================================================
Raw Photo Copy Summary
============================================================
Total JPG files processed:      30
Matched with NEF files:         29 (96%)
Successfully copied:            27
Skipped (duplicate NEF):        2
Skipped (still offloaded):      0
No matching NEF found:          1
============================================================
```

- **Matched**: JPGs that found a matching NEF file
- **Successfully copied**: NEF files actually copied to output
- **Skipped (duplicate NEF)**: JPGs that matched to an already-copied NEF (e.g., `DSC_3988_L.jpg` and `DSC_3988_R.jpg` both matching `DSC_3988.nef`)
- **Skipped (still offloaded)**: NEF files that remained offloaded despite auto-recall attempts
- **No matching NEF found**: JPGs with no corresponding NEF file

## Implementation Notes

- Uses recursive directory traversal for finding NEF files (handles nested Google Drive folders)
- Case-insensitive filename matching (handles filename variations)
- Preserves original NEF filename, modification time, and permissions
- Non-fatal error handling — missing matches are logged as warnings, not errors
- Supports all Nikon NEF raw formats and variations (`.nef`, `.NEF`, `.Nef`)

## Integration with Photo Framer

This tool is designed to complement the Photo Framer project. After using this tool to gather raw files:

1. JPGs are processed through Photo Framer for editing/framing
2. Corresponding NEFs are archived/backed up via this tool
3. Both processed and raw files are kept together in organized directories
