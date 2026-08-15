import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from goldberg_manager.emu_config import (
    EmuConfigGenerationError,
    EmuConfigOutputError,
    build_generate_emu_config_command,
    get_emu_output_directory,
    read_generated_emu_summary,
    run_generate_emu_config,
)


class EmuConfigTests(unittest.TestCase):
    def test_builds_authenticated_command(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)

            generator = root / "generate_emu_config"

            command = build_generate_emu_config_command(
                generator,
                2353060,
            )

            self.assertEqual(
                command,
                [
                    str(generator.resolve()),
                    "-rel_out",
                    "-clr",
                    "2353060",
                ],
            )

    def test_builds_anonymous_command(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)

            generator = root / "generate_emu_config"

            command = build_generate_emu_config_command(
                generator,
                883710,
                anonymous=True,
            )

            self.assertEqual(
                command,
                [
                    str(generator.resolve()),
                    "-anon",
                    "-rel_out",
                    "-clr",
                    "883710",
                ],
            )

    def test_rejects_invalid_appid(
        self,
    ) -> None:
        with self.assertRaises(ValueError):
            build_generate_emu_config_command(
                Path("generate_emu_config"),
                0,
            )

    def test_gets_relative_output_directory(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)

            generator = root / "generate_emu_config"

            output = get_emu_output_directory(
                generator,
                2353060,
            )

            self.assertEqual(
                output,
                (root / "_OUTPUT" / "2353060"),
            )

    def test_reads_generated_summary(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)

            generator = root / "generate_emu_config"

            generator.write_bytes(b"generator")

            output = root / "_OUTPUT" / "2353060"

            steam_settings = output / "steam_settings"

            images = steam_settings / "img"

            images.mkdir(parents=True)

            achievements = [
                {
                    "name": "ACH_ONE",
                    "displayName": "One",
                },
                {
                    "name": "ACH_TWO",
                    "displayName": "Two",
                },
            ]

            (steam_settings / "achievements.json").write_text(
                json.dumps(achievements),
                encoding="utf-8",
            )

            (images / "one.jpg").write_bytes(b"image")

            (images / "two.png").write_bytes(b"image")

            (images / "three.jpeg").write_bytes(b"image")

            (steam_settings / "supported_languages.txt").write_text(
                "english\nbrazilian\n",
                encoding="utf-8",
            )

            (steam_settings / "configs.app.ini").write_text(
                "[app::general]\n"
                "branch_name=public\n"
                "\n"
                "[app::dlcs]\n"
                "unlock_all=0\n"
                "4229700=Deluxe Edition\n"
                "4439940=Additional Fighter\n"
                "\n"
                "[app::paths]\n",
                encoding="utf-8",
            )

            (steam_settings / "depots.txt").write_text(
                "100\n200\n",
                encoding="utf-8",
            )

            (steam_settings / "branches.json").write_text(
                json.dumps(
                    {
                        "public": {},
                        "beta": {},
                    }
                ),
                encoding="utf-8",
            )

            app_info = output / "steam_misc" / "app_info"

            app_info.mkdir(parents=True)

            (app_info / "app_product_info.json").write_text(
                "{}",
                encoding="utf-8",
            )

            (app_info / "app_details.json").write_text(
                "{}",
                encoding="utf-8",
            )

            summary = read_generated_emu_summary(
                generator,
                2353060,
            )

            self.assertEqual(
                summary.app_id,
                2353060,
            )

            self.assertTrue(summary.has_achievements)

            self.assertEqual(
                summary.achievements_count,
                2,
            )

            self.assertEqual(
                summary.achievement_images_count,
                3,
            )

            self.assertEqual(
                summary.supported_languages_count,
                2,
            )

            self.assertEqual(
                summary.dlc_count,
                2,
            )

            self.assertEqual(
                summary.depots_count,
                2,
            )

            self.assertEqual(
                summary.branches_count,
                2,
            )

            self.assertTrue(summary.has_product_info)

            self.assertTrue(summary.has_app_details)

    def test_reads_missing_achievements_as_empty(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)

            generator = root / "generate_emu_config"

            generator.write_bytes(b"generator")

            steam_settings = root / "_OUTPUT" / "883710" / "steam_settings"

            steam_settings.mkdir(parents=True)

            summary = read_generated_emu_summary(
                generator,
                883710,
            )

            self.assertFalse(summary.has_achievements)

            self.assertEqual(
                summary.achievements_count,
                0,
            )

            self.assertIsNone(summary.achievements_file)

    def test_rejects_invalid_achievements_json(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)

            generator = root / "generate_emu_config"

            generator.write_bytes(b"generator")

            steam_settings = root / "_OUTPUT" / "2353060" / "steam_settings"

            steam_settings.mkdir(parents=True)

            (steam_settings / "achievements.json").write_text(
                "{invalid json",
                encoding="utf-8",
            )

            with self.assertRaises(EmuConfigOutputError):
                read_generated_emu_summary(
                    generator,
                    2353060,
                )

    @patch("goldberg_manager.emu_config.subprocess.run")
    def test_runs_generator_in_its_directory(
        self,
        run_mock,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)

            generator = root / "generate_emu_config"

            generator.write_bytes(b"generator")

            output = root / "_OUTPUT" / "2353060"

            output.mkdir(parents=True)

            result = run_generate_emu_config(
                generator,
                2353060,
            )

            self.assertEqual(
                result,
                output,
            )

            run_mock.assert_called_once_with(
                [
                    str(generator.resolve()),
                    "-rel_out",
                    "-clr",
                    "2353060",
                ],
                cwd=root.resolve(),
                check=True,
            )

    def test_rejects_missing_generator(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)

            with self.assertRaises(FileNotFoundError):
                run_generate_emu_config(
                    root / "generate_emu_config",
                    2353060,
                )

    @patch("goldberg_manager.emu_config.subprocess.run")
    def test_reports_failed_generation(
        self,
        run_mock,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)

            generator = root / "generate_emu_config"

            generator.write_bytes(b"generator")

            run_mock.side_effect = subprocess.CalledProcessError(
                1,
                ["generate_emu_config"],
            )

            with self.assertRaises(EmuConfigGenerationError):
                run_generate_emu_config(
                    generator,
                    2353060,
                )

    def test_detects_metadata_with_backslash_paths(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)

            generator = root / "generate_emu_config"

            generator.write_bytes(b"generator")

            output = root / "_OUTPUT" / "2353060"

            steam_settings = output / "steam_settings"

            steam_settings.mkdir(parents=True)

            (output / ("steam_misc\\app_info\\app_product_info.json")).write_text(
                "{}",
                encoding="utf-8",
            )

            (output / ("steam_misc\\app_info\\app_details.json")).write_text(
                "{}",
                encoding="utf-8",
            )

            summary = read_generated_emu_summary(
                generator,
                2353060,
            )

            self.assertTrue(summary.has_product_info)

            self.assertTrue(summary.has_app_details)


if __name__ == "__main__":
    unittest.main()
