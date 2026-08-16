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
    import_generated_achievements,
    read_generated_emu_summary,
    read_generated_supported_languages,
    read_installed_achievements_status,
    run_generate_emu_config,
)


class EmuConfigTests(unittest.TestCase):
    def test_reads_generated_supported_languages(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)

            generator = root / "generate_emu_config"

            generator.write_bytes(b"generator")

            steam_settings = root / "_OUTPUT" / "883710" / "steam_settings"

            steam_settings.mkdir(parents=True)

            (steam_settings / "supported_languages.txt").write_text(
                "english\nfrench\nBRAZILIAN\n\n# comentário\nenglish\n",
                encoding="utf-8",
            )

            languages = read_generated_supported_languages(
                generator,
                883710,
            )

            self.assertEqual(
                languages,
                (
                    "english",
                    "french",
                    "brazilian",
                ),
            )

    def test_missing_generated_languages_returns_empty(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            generator = Path(temp_directory) / "generate_emu_config"

            generator.write_bytes(b"generator")

            languages = read_generated_supported_languages(
                generator,
                883710,
            )

            self.assertEqual(
                languages,
                (),
            )

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

    def test_imports_generated_achievements(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)

            generator = root / "generate_emu_config"

            generator.write_bytes(b"generator")

            steam_settings = root / "_OUTPUT" / "2353060" / "steam_settings"

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

            (images / "one.jpg").write_bytes(b"image-one")

            (images / "two.jpg").write_bytes(b"image-two")

            summary = read_generated_emu_summary(
                generator,
                2353060,
            )

            destination = root / "game" / "steam_settings"

            result = import_generated_achievements(
                summary,
                destination,
            )

            self.assertTrue((destination / "achievements.json").is_file())

            self.assertTrue((destination / "img" / "one.jpg").is_file())

            self.assertTrue((destination / "img" / "two.jpg").is_file())

            self.assertEqual(
                result.achievements_count,
                2,
            )

            self.assertEqual(
                result.images_count,
                2,
            )

    def test_import_preserves_other_steam_settings(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)

            generator = root / "generate_emu_config"

            generator.write_bytes(b"generator")

            generated_settings = root / "_OUTPUT" / "2353060" / "steam_settings"

            generated_settings.mkdir(parents=True)

            (generated_settings / "achievements.json").write_text(
                json.dumps(
                    [
                        {
                            "name": "ACH_ONE",
                        }
                    ]
                ),
                encoding="utf-8",
            )

            summary = read_generated_emu_summary(
                generator,
                2353060,
            )

            destination = root / "game" / "steam_settings"

            destination.mkdir(parents=True)

            user_config = destination / "configs.user.ini"

            interfaces = destination / "steam_interfaces.txt"

            app_id = destination / "steam_appid.txt"

            user_config.write_text(
                "account_name=Davi",
                encoding="utf-8",
            )

            interfaces.write_text(
                "SteamUser",
                encoding="utf-8",
            )

            app_id.write_text(
                "2353060",
                encoding="utf-8",
            )

            import_generated_achievements(
                summary,
                destination,
            )

            self.assertEqual(
                user_config.read_text(encoding="utf-8"),
                "account_name=Davi",
            )

            self.assertEqual(
                interfaces.read_text(encoding="utf-8"),
                "SteamUser",
            )

            self.assertEqual(
                app_id.read_text(encoding="utf-8"),
                "2353060",
            )

    def test_rejects_import_without_achievements(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)

            generator = root / "generate_emu_config"

            generator.write_bytes(b"generator")

            (root / "_OUTPUT" / "883710" / "steam_settings").mkdir(parents=True)

            summary = read_generated_emu_summary(
                generator,
                883710,
            )

            with self.assertRaises(EmuConfigOutputError):
                import_generated_achievements(
                    summary,
                    root / "game" / "steam_settings",
                )

    def test_imports_achievements_without_images(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)

            generator = root / "generate_emu_config"

            generator.write_bytes(b"generator")

            generated_settings = root / "_OUTPUT" / "2353060" / "steam_settings"

            generated_settings.mkdir(parents=True)

            (generated_settings / "achievements.json").write_text(
                json.dumps(
                    [
                        {
                            "name": "ACH_ONE",
                        }
                    ]
                ),
                encoding="utf-8",
            )

            summary = read_generated_emu_summary(
                generator,
                2353060,
            )

            result = import_generated_achievements(
                summary,
                root / "game" / "steam_settings",
            )

            self.assertEqual(
                result.achievements_count,
                1,
            )

            self.assertEqual(
                result.images_count,
                0,
            )

            self.assertIsNone(result.images_directory)

    def test_reads_installed_achievements_status(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)

            steam_settings = root / "steam_settings"

            images = steam_settings / "img"

            images.mkdir(parents=True)

            (steam_settings / "achievements.json").write_text(
                json.dumps(
                    [
                        {
                            "name": "ACH_ONE",
                        },
                        {
                            "name": "ACH_TWO",
                        },
                    ]
                ),
                encoding="utf-8",
            )

            (images / "one.jpg").write_bytes(b"image")

            (images / "two.png").write_bytes(b"image")

            status = read_installed_achievements_status(steam_settings)

            self.assertTrue(status.installed)

            self.assertEqual(
                status.achievements_count,
                2,
            )

            self.assertEqual(
                status.images_count,
                2,
            )

            self.assertEqual(
                status.achievements_file,
                (steam_settings / "achievements.json"),
            )

    def test_reads_missing_installed_achievements_as_empty(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            steam_settings = Path(temp_directory) / "steam_settings"

            status = read_installed_achievements_status(steam_settings)

            self.assertFalse(status.installed)

            self.assertEqual(
                status.achievements_count,
                0,
            )

            self.assertEqual(
                status.images_count,
                0,
            )

            self.assertIsNone(status.achievements_file)

    def test_rejects_invalid_installed_achievements_json(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            steam_settings = Path(temp_directory) / "steam_settings"

            steam_settings.mkdir()

            (steam_settings / "achievements.json").write_text(
                "{invalid json",
                encoding="utf-8",
            )

            with self.assertRaises(EmuConfigOutputError):
                read_installed_achievements_status(steam_settings)

    def test_reimport_removes_stale_achievement_images(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)

            generator = root / "generate_emu_config"

            generator.write_bytes(b"generator")

            generated_settings = root / "_OUTPUT" / "2353060" / "steam_settings"

            generated_images = generated_settings / "img"

            generated_images.mkdir(parents=True)

            (generated_settings / "achievements.json").write_text(
                json.dumps(
                    [
                        {
                            "name": "ACH_ONE",
                        },
                        {
                            "name": "ACH_TWO",
                        },
                    ]
                ),
                encoding="utf-8",
            )

            (generated_images / "one.jpg").write_bytes(b"new-one")

            (generated_images / "two.jpg").write_bytes(b"new-two")

            summary = read_generated_emu_summary(
                generator,
                2353060,
            )

            destination = root / "game" / "steam_settings"

            installed_images = destination / "img"

            installed_images.mkdir(parents=True)

            (installed_images / "one.jpg").write_bytes(b"old-one")

            (installed_images / "stale.jpg").write_bytes(b"stale")

            import_generated_achievements(
                summary,
                destination,
            )

            self.assertFalse((installed_images / "stale.jpg").exists())

            self.assertEqual(
                (installed_images / "one.jpg").read_bytes(),
                b"new-one",
            )

            self.assertEqual(
                (installed_images / "two.jpg").read_bytes(),
                b"new-two",
            )

            self.assertEqual(
                {path.name for path in installed_images.iterdir() if path.is_file()},
                {
                    "one.jpg",
                    "two.jpg",
                },
            )


if __name__ == "__main__":
    unittest.main()
