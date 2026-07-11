from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

import photo_framer
import photo_helper
from photo_helper import (
    AppConfig,
    build_collage,
    copy_matched_raws,
    load_image,
    process_all,
    run_basic_tests,
    run_collage_tests,
    summarize_source_images,
    validate_outputs,
)


class PhotoHelperTests(unittest.TestCase):
    def _make_image(self, path: Path, size: tuple[int, int], color: tuple[int, int, int]) -> None:
        Image.new("RGB", size, color).save(path, quality=95)

    def test_legacy_namespace_still_works(self) -> None:
        self.assertTrue(hasattr(photo_framer, "process_all"))
        self.assertTrue(hasattr(photo_framer, "copy_matched_raws"))
        self.assertTrue(hasattr(photo_helper, "build_collage"))

    def test_builtin_smoke_tests(self) -> None:
        run_basic_tests()
        run_collage_tests()

    def test_framing_pipeline_processes_and_validates(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_dir = root / "source"
            processed_dir = root / "processed"
            framed_dir = root / "framed"
            source_dir.mkdir()

            self._make_image(source_dir / "portrait.jpg", (800, 1200), (10, 20, 30))
            self._make_image(source_dir / "landscape.jpg", (4000, 3000), (40, 50, 60))

            cfg = AppConfig(
                source_dir=source_dir,
                processed_dir=processed_dir,
                framed_dir=framed_dir,
                target_size=(600, 800),
                baseline_frame_width=40,
                frame_color=(255, 255, 255),
                allow_upscale=True,
                image_extensions=(".jpg",),
                jpeg_quality=95,
                jpeg_subsampling=0,
                copy_portraits_without_reencode=True,
            )

            discovered, portraits, landscapes = summarize_source_images(cfg)
            self.assertEqual((discovered, portraits, landscapes), (2, 1, 1))

            records, stats, borders = process_all(cfg, log_callback=None)
            self.assertEqual(stats.errors, 0)
            self.assertEqual(len(records), 2)
            self.assertEqual(stats.portraits, 1)
            self.assertEqual(stats.landscapes, 1)
            self.assertEqual(stats.processed_written, 3)
            self.assertEqual(stats.framed_written, 3)
            self.assertEqual(len(borders), 3)
            self.assertEqual(borders["wide_02.jpg"].left, 0)
            self.assertEqual(borders["wide_02.jpg"].right, 0)

            validate_outputs(cfg, borders)

            processed_files = sorted(p.name for p in processed_dir.glob("*.jpg"))
            framed_files = sorted(p.name for p in framed_dir.glob("*.jpg"))
            self.assertEqual(
                processed_files,
                ["landscape_L.jpg", "landscape_R.jpg", "portrait.jpg"],
            )
            self.assertEqual(
                framed_files,
                ["landscape_L.jpg", "landscape_R.jpg", "portrait.jpg"],
            )

    def test_two_to_one_landscape_is_split_into_three(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_dir = root / "source"
            processed_dir = root / "processed"
            framed_dir = root / "framed"
            source_dir.mkdir()

            self._make_image(source_dir / "wide.jpg", (2400, 1200), (70, 80, 90))

            cfg = AppConfig(
                source_dir=source_dir,
                processed_dir=processed_dir,
                framed_dir=framed_dir,
                target_size=(600, 800),
                baseline_frame_width=40,
                frame_color=(255, 255, 255),
                allow_upscale=True,
                image_extensions=(".jpg",),
                jpeg_quality=95,
                jpeg_subsampling=0,
                copy_portraits_without_reencode=True,
            )

            discovered, portraits, landscapes = summarize_source_images(cfg)
            self.assertEqual((discovered, portraits, landscapes), (1, 0, 1))

            records, stats, borders = process_all(cfg, log_callback=None)
            self.assertEqual(stats.errors, 0)
            self.assertEqual(len(records), 1)
            self.assertEqual(stats.portraits, 0)
            self.assertEqual(stats.landscapes, 1)
            self.assertEqual(stats.processed_written, 3)
            self.assertEqual(stats.framed_written, 3)
            self.assertEqual(len(borders), 3)

            validate_outputs(cfg, borders)

            processed_files = sorted(p.name for p in processed_dir.glob("*.jpg"))
            framed_files = sorted(p.name for p in framed_dir.glob("*.jpg"))
            self.assertEqual(processed_files, ["wide_01.jpg", "wide_02.jpg", "wide_03.jpg"])
            self.assertEqual(framed_files, ["wide_01.jpg", "wide_02.jpg", "wide_03.jpg"])

    def test_four_three_landscape_is_split_in_half(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_dir = root / "source"
            processed_dir = root / "processed"
            framed_dir = root / "framed"
            source_dir.mkdir()

            self._make_image(source_dir / "four_three.jpg", (4000, 3000), (20, 40, 60))

            cfg = AppConfig(
                source_dir=source_dir,
                processed_dir=processed_dir,
                framed_dir=framed_dir,
                target_size=(600, 800),
                baseline_frame_width=40,
                frame_color=(255, 255, 255),
                allow_upscale=True,
                image_extensions=(".jpg",),
                jpeg_quality=95,
                jpeg_subsampling=0,
                copy_portraits_without_reencode=True,
            )

            discovered, portraits, landscapes = summarize_source_images(cfg)
            self.assertEqual((discovered, portraits, landscapes), (1, 0, 1))

            records, stats, borders = process_all(cfg, log_callback=None)
            self.assertEqual(stats.errors, 0)
            self.assertEqual(len(records), 1)
            self.assertEqual(stats.portraits, 0)
            self.assertEqual(stats.landscapes, 1)
            self.assertEqual(stats.processed_written, 2)
            self.assertEqual(stats.framed_written, 2)
            self.assertEqual(len(borders), 2)

            validate_outputs(cfg, borders)

            processed_files = sorted(p.name for p in processed_dir.glob("*.jpg"))
            framed_files = sorted(p.name for p in framed_dir.glob("*.jpg"))
            self.assertEqual(processed_files, ["four_three_L.jpg", "four_three_R.jpg"])
            self.assertEqual(framed_files, ["four_three_L.jpg", "four_three_R.jpg"])

    def test_collage_builder_creates_expected_canvas(self) -> None:
        background = Image.new("RGB", (500, 300), (20, 30, 40))
        foregrounds = [
            Image.new("RGB", (300, 400), (200, 10, 10)),
            Image.new("RGB", (350, 450), (10, 200, 10)),
        ]

        master, panels, borders = build_collage(background, foregrounds, (120, 150), 0.8)
        self.assertEqual(master.size, (240, 150))
        self.assertEqual(len(panels), 2)
        self.assertEqual(len(borders), 2)
        self.assertTrue(all(panel.size == (120, 150) for panel in panels))

    def test_raw_copy_matches_duplicates_once(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            jpg_dir = root / "jpgs"
            raw_dir = root / "raws"
            output_dir = root / "output"
            jpg_dir.mkdir()
            raw_dir.mkdir()

            (jpg_dir / "IMG_0001_L.jpg").write_bytes(b"jpg-1")
            (jpg_dir / "IMG_0001_R.jpg").write_bytes(b"jpg-2")
            (raw_dir / "IMG_0001.nef").write_bytes(b"raw-data")

            with patch("photo_helper.raw.ensure_file_downloaded", return_value=True):
                stats = copy_matched_raws(jpg_dir, raw_dir, output_dir, verbose=False)

            self.assertEqual(stats["matched"], 2)
            self.assertEqual(stats["copied"], 1)
            self.assertEqual(stats["duplicate"], 1)
            self.assertTrue((output_dir / "IMG_0001.nef").exists())


if __name__ == "__main__":
    unittest.main()
