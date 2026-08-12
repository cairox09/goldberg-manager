import tempfile
import unittest
from pathlib import Path

from goldberg_manager.generators import generate_steam_appid


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


if __name__ == "__main__":
    unittest.main()
