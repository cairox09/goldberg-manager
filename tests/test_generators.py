import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from goldberg_manager.generators import (
    generate_steam_appid,
    generate_steam_interfaces,
)


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


if __name__ == "__main__":
    unittest.main()
