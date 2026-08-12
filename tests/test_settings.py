import tempfile
import unittest
from pathlib import Path

from goldberg_manager.scanner import Game
from goldberg_manager.settings import (
    SteamUserSettings,
    generate_game_steam_settings,
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

    def test_generates_complete_game_settings(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)

            steam_api = root / "Binaries" / "Win64" / "steam_api64.dll"
            steam_api.parent.mkdir(parents=True)
            steam_api.write_bytes(b"steam api")

            game = Game(
                name="Example Game",
                root_directory=root,
                executable=steam_api.parent / "Game.exe",
                steam_api=steam_api,
                steam_api_relative_path=Path("Binaries/Win64/steam_api64.dll"),
                architecture="64-bit",
                source_directory=root,
            )

            user_settings = SteamUserSettings(
                account_name="Player",
                account_steamid=76561198000000000,
                language="brazilian",
                ip_country="BR",
                local_save_path="./saves",
            )

            app_id_path, user_config_path = generate_game_steam_settings(
                game,
                123456,
                user_settings,
            )

            steam_settings = steam_api.parent / "steam_settings"

            self.assertEqual(
                app_id_path,
                steam_settings / "steam_appid.txt",
            )

            self.assertEqual(
                user_config_path,
                steam_settings / "configs.user.ini",
            )

            self.assertEqual(
                app_id_path.read_text(encoding="utf-8"),
                "123456\n",
            )

            content = user_config_path.read_text(encoding="utf-8")

            self.assertIn(
                "account_name=Player",
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

            self.assertIn(
                "local_save_path=./saves",
                content,
            )

    def test_preserves_existing_steam_interfaces(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)

            steam_api = root / "steam_api64.dll"
            steam_api.write_bytes(b"steam api")

            steam_settings = root / "steam_settings"
            steam_settings.mkdir()

            steam_interfaces = steam_settings / "steam_interfaces.txt"

            steam_interfaces.write_text(
                "SteamClient021\n",
                encoding="utf-8",
            )

            game = Game(
                name="Example Game",
                root_directory=root,
                executable=root / "Game.exe",
                steam_api=steam_api,
                steam_api_relative_path=Path("steam_api64.dll"),
                architecture="64-bit",
                source_directory=root,
            )

            generate_game_steam_settings(
                game,
                123456,
                SteamUserSettings(
                    account_name="Player",
                ),
            )

            self.assertEqual(
                steam_interfaces.read_text(encoding="utf-8"),
                "SteamClient021\n",
            )


if __name__ == "__main__":
    unittest.main()
