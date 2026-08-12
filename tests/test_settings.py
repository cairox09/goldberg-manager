import tempfile
import unittest
from pathlib import Path

from goldberg_manager.settings import (
    SteamUserSettings,
    generate_user_config,
)


class SteamSettingsTests(unittest.TestCase):
    def test_generates_user_config(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            steam_settings = Path(temp_directory) / "steam_settings"

            settings = SteamUserSettings(
                account_name="Davi",
                account_steamid=76561198000000000,
                language="brazilian",
                ip_country="BR",
            )

            output = generate_user_config(
                steam_settings,
                settings,
            )

            self.assertEqual(
                output,
                steam_settings / "configs.user.ini",
            )

            content = output.read_text(encoding="utf-8")

            self.assertIn(
                "account_name=Davi",
                content,
            )
            self.assertIn(
                "account_steamid=76561198000000000",
                content,
            )
            self.assertIn(
                "language=brazilian",
                content,
            )
            self.assertIn(
                "ip_country=BR",
                content,
            )

    def test_generates_local_save_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            steam_settings = Path(temp_directory) / "steam_settings"

            settings = SteamUserSettings(
                account_name="Player",
                local_save_path="./saves",
            )

            output = generate_user_config(
                steam_settings,
                settings,
            )

            content = output.read_text(encoding="utf-8")

            self.assertIn(
                "[user::saves]",
                content,
            )
            self.assertIn(
                "local_save_path=./saves",
                content,
            )

    def test_prefers_local_save_over_save_folder_name(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            steam_settings = Path(temp_directory) / "steam_settings"

            settings = SteamUserSettings(
                account_name="Player",
                local_save_path="./portable-saves",
                saves_folder_name="My Saves",
            )

            output = generate_user_config(
                steam_settings,
                settings,
            )

            content = output.read_text(encoding="utf-8")

            self.assertIn(
                "local_save_path=./portable-saves",
                content,
            )
            self.assertNotIn(
                "saves_folder_name=",
                content,
            )

    def test_rejects_invalid_steamid(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            steam_settings = Path(temp_directory) / "steam_settings"

            settings = SteamUserSettings(
                account_name="Player",
                account_steamid=0,
            )

            with self.assertRaises(ValueError):
                generate_user_config(
                    steam_settings,
                    settings,
                )


if __name__ == "__main__":
    unittest.main()
