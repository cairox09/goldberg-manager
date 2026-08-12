import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from goldberg_manager.generators import (
    generate_game_steam_interfaces,
    generate_steam_appid,
    generate_steam_interfaces,
    select_interfaces_generator,
)
from goldberg_manager.scanner import Game


class GeneratorTests(unittest.TestCase):
    def test_generates_steam_appid(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            steam_settings = root / "steam_settings"

            output = generate_steam_appid(
                steam_settings,
                123456,
            )

            self.assertEqual(
                output,
                steam_settings / "steam_appid.txt",
            )

            self.assertTrue(output.is_file())
            self.assertEqual(
                output.read_text(encoding="utf-8"),
                "123456\n",
            )

    def test_creates_steam_settings_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            steam_settings = root / "nested" / "steam_settings"

            self.assertFalse(steam_settings.exists())

            generate_steam_appid(
                steam_settings,
                123456,
            )

            self.assertTrue(steam_settings.is_dir())

    def test_rejects_invalid_appid(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            steam_settings = Path(temp_directory) / "steam_settings"

            with self.assertRaises(ValueError):
                generate_steam_appid(
                    steam_settings,
                    0,
                )

            self.assertFalse(steam_settings.exists())

    @patch("goldberg_manager.generators.subprocess.run")
    def test_generates_steam_interfaces(self, run_mock) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)

            generator = root / "generate_interfaces_x64.exe"
            steam_api = root / "steam_api64.dll"
            steam_settings = root / "steam_settings"

            generator.write_bytes(b"generator")
            steam_api.write_bytes(b"steam api")

            def fake_run(command, **kwargs):
                working_directory = Path(kwargs["cwd"])

                (working_directory / "steam_interfaces.txt").write_text(
                    "SteamClient021\nSteamUser023\n",
                    encoding="utf-8",
                )

            run_mock.side_effect = fake_run

            output = generate_steam_interfaces(
                generator,
                steam_api,
                steam_settings,
                command_prefix=("wine",),
            )

            self.assertEqual(
                output,
                steam_settings / "steam_interfaces.txt",
            )

            self.assertEqual(
                output.read_text(encoding="utf-8"),
                "SteamClient021\nSteamUser023\n",
            )

            command = run_mock.call_args.args[0]

            self.assertEqual(
                command,
                [
                    "wine",
                    str(generator.resolve()),
                    str(steam_api.resolve()),
                ],
            )

    @patch("goldberg_manager.generators.subprocess.run")
    def test_rejects_failed_interfaces_generation(
        self,
        run_mock,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)

            generator = root / "generate_interfaces_x64.exe"
            steam_api = root / "steam_api64.dll"
            steam_settings = root / "steam_settings"

            generator.write_bytes(b"generator")
            steam_api.write_bytes(b"steam api")

            run_mock.side_effect = subprocess.CalledProcessError(
                1,
                ["generator"],
                stderr="No interfaces were found",
            )

            with self.assertRaisesRegex(
                RuntimeError,
                "No interfaces were found",
            ):
                generate_steam_interfaces(
                    generator,
                    steam_api,
                    steam_settings,
                )

            self.assertFalse(steam_settings.exists())

    @patch("goldberg_manager.generators.subprocess.run")
    def test_rejects_missing_generated_interfaces(
        self,
        run_mock,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)

            generator = root / "generate_interfaces_x64.exe"
            steam_api = root / "steam_api64.dll"
            steam_settings = root / "steam_settings"

            generator.write_bytes(b"generator")
            steam_api.write_bytes(b"steam api")

            with self.assertRaisesRegex(
                RuntimeError,
                "sem criar steam_interfaces.txt",
            ):
                generate_steam_interfaces(
                    generator,
                    steam_api,
                    steam_settings,
                )

            self.assertFalse(steam_settings.exists())

    def test_selects_x64_interfaces_generator(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)

            x64 = root / "generate_interfaces_x64.exe"
            x86 = root / "generate_interfaces_x86.exe"

            x64.write_bytes(b"x64")
            x86.write_bytes(b"x86")

            game = Game(
                name="Example Game",
                root_directory=root,
                executable=root / "Game.exe",
                steam_api=root / "steam_api64.dll",
                steam_api_relative_path=Path("steam_api64.dll"),
                architecture="64-bit",
                source_directory=root,
            )

            selected = select_interfaces_generator(
                game,
                x64,
                x86,
            )

            self.assertEqual(selected, x64)

    def test_selects_x86_interfaces_generator(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)

            x64 = root / "generate_interfaces_x64.exe"
            x86 = root / "generate_interfaces_x86.exe"

            x64.write_bytes(b"x64")
            x86.write_bytes(b"x86")

            game = Game(
                name="Example Game",
                root_directory=root,
                executable=root / "Game.exe",
                steam_api=root / "steam_api.dll",
                steam_api_relative_path=Path("steam_api.dll"),
                architecture="32-bit",
                source_directory=root,
            )

            selected = select_interfaces_generator(
                game,
                x64,
                x86,
            )

            self.assertEqual(selected, x86)

    @patch("goldberg_manager.generators.generate_steam_interfaces")
    @patch("goldberg_manager.generators.get_backup_path")
    @patch("goldberg_manager.generators.verify_backup")
    def test_generates_interfaces_for_game_from_verified_backup(
        self,
        verify_backup_mock,
        get_backup_path_mock,
        generate_mock,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)

            generator = root / "generate_interfaces_x64.exe"
            generator.write_bytes(b"generator")

            steam_api = root / "Binaries" / "Win64" / "steam_api64.dll"
            steam_api.parent.mkdir(parents=True)
            steam_api.write_bytes(b"current api")

            original_backup = root / "backup" / "steam_api64.dll"
            original_backup.parent.mkdir()
            original_backup.write_bytes(b"original api")

            game = Game(
                name="Example Game",
                root_directory=root,
                executable=steam_api.parent / "Game.exe",
                steam_api=steam_api,
                steam_api_relative_path=Path("Binaries/Win64/steam_api64.dll"),
                architecture="64-bit",
                source_directory=root,
            )

            verify_backup_mock.return_value = True
            get_backup_path_mock.return_value = original_backup

            expected_output = (
                steam_api.parent / "steam_settings" / "steam_interfaces.txt"
            )

            generate_mock.return_value = expected_output

            output = generate_game_steam_interfaces(
                game,
                generator,
                None,
                command_prefix=("wine",),
            )

            self.assertEqual(output, expected_output)

            generate_mock.assert_called_once_with(
                generator,
                original_backup,
                steam_api.parent / "steam_settings",
                command_prefix=("wine",),
            )

    @patch("goldberg_manager.generators.verify_backup")
    def test_rejects_interfaces_generation_without_verified_backup(
        self,
        verify_backup_mock,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)

            game = Game(
                name="Example Game",
                root_directory=root,
                executable=root / "Game.exe",
                steam_api=root / "steam_api64.dll",
                steam_api_relative_path=Path("steam_api64.dll"),
                architecture="64-bit",
                source_directory=root,
            )

            verify_backup_mock.return_value = False

            with self.assertRaisesRegex(
                ValueError,
                "backup íntegro",
            ):
                generate_game_steam_interfaces(
                    game,
                    root / "generate_interfaces_x64.exe",
                    None,
                )


if __name__ == "__main__":
    unittest.main()
