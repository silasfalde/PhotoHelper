"""Panorama stitching utilities.

Reads NEF files (via rawpy) or common image formats and stitches them into
a single rectangular, center-focused panorama. Saves output as a 16-bit
TIFF by default (DNG/NEF writing is not implemented here).
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import List, Tuple

import numpy as np

try:
    import rawpy
except Exception:  # pragma: no cover - optional dependency
    rawpy = None

import cv2
from PIL import Image
import tifffile


def _natural_sort_key(s: str):
    parts = re.split(r"(\d+)", s)
    return [int(p) if p.isdigit() else p.lower() for p in parts]


def list_images_sorted(dir_path: Path) -> List[Path]:
    p = dir_path.resolve()
    if not p.exists():
        raise FileNotFoundError(p)
    files = [f for f in sorted(p.iterdir(), key=lambda x: _natural_sort_key(x.name)) if f.is_file()]
    return files


def _load_nef_to_rgb16(path: Path) -> np.ndarray:
    if rawpy is None:
        raise RuntimeError("rawpy is required to read NEF files")
    with rawpy.imread(str(path)) as raw:
        rgb = raw.postprocess(output_bps=16, use_camera_wb=True, no_auto_bright=True)
    # rawpy returns uint16 HxWx3
    return rgb.astype(np.uint16)


def _load_image_any(path: Path) -> np.ndarray:
    """Load NEF via rawpy if available, otherwise use PIL and return uint16 RGB."""
    if path.suffix.lower() == ".nef":
        return _load_nef_to_rgb16(path)
    img = Image.open(path)
    arr = np.array(img.convert("RGB"), dtype=np.uint8)
    # promote to 16-bit by scaling
    arr16 = (arr.astype(np.uint16) << 8) | arr.astype(np.uint16)
    return arr16


def _detect_and_match(img1_gray: np.ndarray, img2_gray: np.ndarray):
    # Ensure images are 8-bit for OpenCV feature detectors
    def _to_uint8(img: np.ndarray) -> np.ndarray:
        if img.dtype == np.uint8:
            return img
        # normalize to 0-255 then convert
        img8 = cv2.normalize(img, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
        return img8

    img1_gray = _to_uint8(img1_gray)
    img2_gray = _to_uint8(img2_gray)

    sift = None
    try:
        sift = cv2.SIFT_create()
    except Exception:
        sift = None

    if sift is not None:
        kp1, des1 = sift.detectAndCompute(img1_gray, None)
        kp2, des2 = sift.detectAndCompute(img2_gray, None)
        matcher = cv2.BFMatcher(cv2.NORM_L2, crossCheck=False)
    else:
        orb = cv2.ORB_create(5000)
        kp1, des1 = orb.detectAndCompute(img1_gray, None)
        kp2, des2 = orb.detectAndCompute(img2_gray, None)
        matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=False)

    if des1 is None or des2 is None:
        return [], kp1, kp2

    matches = matcher.knnMatch(des1, des2, k=2)
    good = []
    for m_n in matches:
        if len(m_n) != 2:
            continue
        m, n = m_n
        if m.distance < 0.75 * n.distance:
            good.append(m)
    return good, kp1, kp2


def _find_homography(img1: np.ndarray, img2: np.ndarray):
    g, kp1, kp2 = _detect_and_match(img1, img2)
    if len(g) < 4:
        return None
    pts1 = np.float32([kp1[m.queryIdx].pt for m in g]).reshape(-1, 1, 2)
    pts2 = np.float32([kp2[m.trainIdx].pt for m in g]).reshape(-1, 1, 2)
    H, mask = cv2.findHomography(pts2, pts1, cv2.RANSAC, 5.0)
    return H


def stitch_images_from_paths(paths: List[Path], max_width: int | None = None, max_height: int | None = None) -> Tuple[np.ndarray, Tuple[int, int]]:
    """Stitch input images (NEF or common formats) ordered by the list of paths.

    Returns a uint16 RGB image and its (width, height).
    """
    if not paths:
        raise ValueError("No input images")

    imgs = [ _load_image_any(p) for p in paths ]

    if max_width or max_height:
        # optionally rescale images to fit budget while preserving aspect ratio
        scaled = []
        for im in imgs:
            h, w = im.shape[:2]
            scale = 1.0
            if max_width:
                scale = min(scale, max_width / w)
            if max_height:
                scale = min(scale, max_height / h)
            if scale < 1.0:
                im_small = cv2.resize(im, (max(1, int(w * scale)), max(1, int(h * scale))), interpolation=cv2.INTER_LANCZOS4)
                scaled.append(im_small)
            else:
                scaled.append(im)
        imgs = scaled

    # convert to grayscale for feature detection
    grays = [cv2.cvtColor(im, cv2.COLOR_RGB2GRAY) for im in imgs]

    n = len(imgs)
    homos = [None] * (n - 1)
    for i in range(n - 1):
        H = _find_homography(grays[i], grays[i + 1])
        if H is None:
            # Fallback: estimate pure translation via phase correlation
            try:
                f1 = grays[i].astype(np.float32)
                f2 = grays[i + 1].astype(np.float32)
                shift, resp = cv2.phaseCorrelate(f1, f2)
                dx, dy = shift
                H = np.array([[1.0, 0.0, dx], [0.0, 1.0, dy], [0.0, 0.0, 1.0]], dtype=np.float64)
            except Exception:
                H = None
        homos[i] = H

    # compute cumulative transforms to center image
    center = n // 2
    transforms = [np.eye(3, dtype=np.float64) for _ in range(n)]

    # from center to left
    for i in range(center - 1, -1, -1):
        H = homos[i]
        if H is None:
            transforms[i] = transforms[i + 1]
        else:
            transforms[i] = transforms[i + 1] @ np.linalg.inv(H)

    # from center to right
    for i in range(center, n - 1):
        H = homos[i]
        if H is None:
            transforms[i + 1] = transforms[i]
        else:
            transforms[i + 1] = transforms[i] @ H

    # determine bounding box
    corners = []
    for im, T in zip(imgs, transforms):
        h, w = im.shape[:2]
        pts = np.array([[0,0,1],[w,0,1],[w,h,1],[0,h,1]]).T
        warped = T @ pts
        warped = warped[:2] / warped[2]
        corners.append(warped.T)

    all_pts = np.vstack(corners)
    min_x, min_y = np.floor(all_pts.min(axis=0)).astype(int)
    max_x, max_y = np.ceil(all_pts.max(axis=0)).astype(int)

    canvas_w = int(max_x - min_x)
    canvas_h = int(max_y - min_y)

    offset = np.array([[1,0,-min_x],[0,1,-min_y],[0,0,1]])

    acc = np.zeros((canvas_h, canvas_w, 3), dtype=np.float64)
    weight = np.zeros((canvas_h, canvas_w), dtype=np.float64)

    for im, T in zip(imgs, transforms):
        H = offset @ T
        h, w = im.shape[:2]
        warped = cv2.warpPerspective(im, H, (canvas_w, canvas_h), flags=cv2.INTER_LANCZOS4)
        mask = cv2.warpPerspective(np.ones((h, w), dtype=np.uint8), H, (canvas_w, canvas_h), flags=cv2.INTER_NEAREST)

        # feather mask using distance transform
        mask8 = (mask * 255).astype(np.uint8)
        dist = cv2.distanceTransform(mask8, cv2.DIST_L2, 5)
        if dist.max() > 0:
            alpha = dist / dist.max()
        else:
            alpha = mask
        alpha = alpha.astype(np.float64)

        for c in range(3):
            acc[:, :, c] += warped[:, :, c].astype(np.float64) * alpha
        weight += alpha

    # avoid division by zero
    nonzero = weight > 0
    out = np.zeros_like(acc, dtype=np.uint16)
    for c in range(3):
        channel = np.zeros((canvas_h, canvas_w), dtype=np.float64)
        channel[nonzero] = acc[:, :, c][nonzero] / weight[nonzero]
        # clip to uint16
        channel = np.clip(np.round(channel), 0, 65535).astype(np.uint16)
        out[:, :, c] = channel

    # crop to bounding rectangle of nonzero weight
    ys, xs = np.where(nonzero)
    if ys.size == 0 or xs.size == 0:
        raise RuntimeError("No valid stitched pixels")
    top, left = ys.min(), xs.min()
    bottom, right = ys.max(), xs.max()
    cropped = out[top:bottom+1, left:right+1]

    return cropped, (cropped.shape[1], cropped.shape[0])


def save_tiff(image: np.ndarray, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # image expected uint16 HxWx3
    tifffile.imwrite(str(path), image, photometric='rgb')
