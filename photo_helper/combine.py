from __future__ import annotations

from PIL import Image


def combine_portrait_pair(left: Image.Image, right: Image.Image) -> Image.Image:
    if left.size != right.size:
        raise ValueError("Input images must have identical dimensions")

    width, height = left.size
    if width * 4 != height * 3:
        raise ValueError("Input images must have a 3:4 aspect ratio")

    combined = Image.new("RGB", (width * 2, height))
    combined.paste(left.convert("RGB"), (0, 0))
    combined.paste(right.convert("RGB"), (width, 0))
    return combined