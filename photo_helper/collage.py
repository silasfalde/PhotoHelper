from __future__ import annotations

from pathlib import Path
from typing import List, Tuple

from PIL import Image, ImageOps

from .common import BorderSpec, crop_to_aspect, resize_exact, resize_to_fit


def compute_collage_canvas_size(panel_size: Tuple[int, int], panel_count: int) -> Tuple[int, int]:
    if panel_count <= 0:
        raise ValueError("Panel count must be positive")

    panel_w, panel_h = panel_size
    if panel_w <= 0 or panel_h <= 0:
        raise ValueError("Panel dimensions must be positive")

    return panel_w * panel_count, panel_h


def crop_background_for_collage(
    background: Image.Image,
    panel_size: Tuple[int, int],
    panel_count: int,
) -> Image.Image:
    canvas_w, canvas_h = compute_collage_canvas_size(panel_size, panel_count)
    cropped = crop_to_aspect(background, canvas_w, canvas_h)
    return resize_exact(cropped, canvas_w, canvas_h)


def render_collage_panel(
    background_slice: Image.Image,
    foreground: Image.Image,
    panel_size: Tuple[int, int],
    foreground_scale: float,
    foreground_border_width: int = 0,
    foreground_border_color: Tuple[int, int, int] = (255, 255, 255),
) -> Tuple[Image.Image, BorderSpec]:
    if foreground_scale <= 0:
        raise ValueError("Foreground scale must be positive")
    if foreground_border_width < 0:
        raise ValueError("Foreground border width must be non-negative")

    panel_w, panel_h = panel_size
    if background_slice.size != (panel_w, panel_h):
        raise ValueError("Background slice does not match panel size")

    fg_cropped = crop_to_aspect(foreground, 3, 4)
    max_w = max(1, int(round(panel_w * foreground_scale)) - (2 * foreground_border_width))
    max_h = max(1, int(round(panel_h * foreground_scale)) - (2 * foreground_border_width))
    fg_resized = resize_to_fit(fg_cropped, max_w, max_h, allow_upscale=False)
    if foreground_border_width > 0:
        fg_resized = ImageOps.expand(
            fg_resized,
            border=foreground_border_width,
            fill=foreground_border_color,
        )

    panel = background_slice.copy()
    x = (panel_w - fg_resized.width) // 2
    y = (panel_h - fg_resized.height) // 2
    panel.paste(fg_resized, (x, y))

    border = BorderSpec(
        left=x,
        top=y,
        right=panel_w - (x + fg_resized.width),
        bottom=panel_h - (y + fg_resized.height),
    )
    return panel, border


def build_collage(
    background: Image.Image,
    foregrounds: List[Image.Image],
    panel_size: Tuple[int, int],
    foreground_scale: float,
    foreground_border_width: int = 0,
    foreground_border_color: Tuple[int, int, int] = (255, 255, 255),
) -> Tuple[Image.Image, List[Image.Image], List[BorderSpec]]:
    if not foregrounds:
        raise ValueError("At least one foreground image is required")

    canvas_w, canvas_h = compute_collage_canvas_size(panel_size, len(foregrounds))
    background_canvas = crop_background_for_collage(background, panel_size, len(foregrounds))

    master = Image.new("RGB", (canvas_w, canvas_h))
    panel_images: List[Image.Image] = []
    borders: List[BorderSpec] = []
    panel_w, panel_h = panel_size

    for index, foreground in enumerate(foregrounds):
        x0 = index * panel_w
        background_slice = background_canvas.crop((x0, 0, x0 + panel_w, panel_h))
        panel_image, border = render_collage_panel(
            background_slice,
            foreground,
            panel_size=panel_size,
            foreground_scale=foreground_scale,
            foreground_border_width=foreground_border_width,
            foreground_border_color=foreground_border_color,
        )
        master.paste(panel_image, (x0, 0))
        panel_images.append(panel_image)
        borders.append(border)

    return master, panel_images, borders


def validate_collage_outputs(
    panel_size: Tuple[int, int],
    master_path: Path,
    panel_paths: List[Path],
) -> None:
    panel_w, panel_h = panel_size
    expected_size = (panel_w * len(panel_paths), panel_h)

    with Image.open(master_path) as master_img:
        assert master_img.size == expected_size, (
            f"Master collage is not {expected_size}: {master_path.name}, got {master_img.size}"
        )

    for panel_path in panel_paths:
        with Image.open(panel_path) as panel_img:
            assert panel_img.size == panel_size, (
                f"Panel is not {panel_size}: {panel_path.name}, got {panel_img.size}"
            )


def run_collage_tests() -> None:
    background = Image.new("RGB", (4000, 1440), (30, 40, 50))
    foregrounds = [
        Image.new("RGB", (1400, 1000), (200, 10, 10)),
        Image.new("RGB", (1600, 1200), (10, 200, 10)),
        Image.new("RGB", (1800, 1300), (10, 10, 200)),
    ]

    master, panels, borders = build_collage(background, foregrounds, (1080, 1440), 0.9)

    assert master.size == (3240, 1440)
    assert len(panels) == 3
    assert len(borders) == 3
    for panel in panels:
        assert panel.size == (1080, 1440)
    for border in borders:
        assert border.left >= 0
        assert border.top >= 0
        assert border.right >= 0
        assert border.bottom >= 0
