from __future__ import annotations

from typing import Tuple

from PIL import Image

from .common import crop_to_aspect, resize_exact


def combine_pair(left: Image.Image, right: Image.Image, ratio: Tuple[int, int] = (6, 4)) -> Image.Image:
    """Center-crop both images to half of `ratio`, then place them side by side."""
    ratio_w, ratio_h = ratio
    if ratio_w <= 0 or ratio_h <= 0:
        raise ValueError("Aspect ratio values must be positive")

    # Each half has aspect ratio ratio_w : (2 * ratio_h).
    half_w, half_h = ratio_w, 2 * ratio_h
    cropped = [crop_to_aspect(img.convert("RGB"), half_w, half_h) for img in (left, right)]

    # Match the smaller crop so neither image is upscaled.
    height = min(img.height for img in cropped)
    width = max(1, round(height * half_w / half_h))
    halves = [resize_exact(img, width, height) for img in cropped]

    combined = Image.new("RGB", (width * 2, height))
    combined.paste(halves[0], (0, 0))
    combined.paste(halves[1], (width, 0))
    return combined
