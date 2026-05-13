import numpy as np
from pathlib import Path
import tempfile
from PIL import Image, ImageDraw

from photo_helper.panorama import stitch_images_from_paths


def _make_test_image(color, size=(200, 150)):
    arr = np.zeros((size[1], size[0], 3), dtype=np.uint8)
    arr[:, :] = color
    return Image.fromarray(arr)


def test_simple_two_panel_stitch():
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        # create two images with overlap: left (blue) and right (green)
        left = _make_test_image((0, 0, 200), size=(300, 200))
        right = _make_test_image((0, 200, 0), size=(300, 200))

        # add a distinct feature (yellow rectangle) on the right side of left
        draw_l = ImageDraw.Draw(left)
        draw_l.rectangle([180, 40, 260, 160], fill=(255, 255, 0))

        # add the same feature near the left side of right so matching is possible
        draw_r = ImageDraw.Draw(right)
        draw_r.rectangle([20, 40, 100, 160], fill=(255, 255, 0))

        # shift right image left by 100 pixels to create overlap
        right_shifted = Image.new("RGB", (300, 200), (0, 200, 0))
        right_shifted.paste(right, (-100, 0))

        p1 = d / "IMG_0001.png"
        p2 = d / "IMG_0002.png"
        left.save(p1)
        right_shifted.save(p2)

        out, size = stitch_images_from_paths([p1, p2])
        assert out.ndim == 3
        assert size[0] > 300  # stitched width should exceed single image width