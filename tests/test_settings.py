import tempfile
import unittest
from pathlib import Path

from goldberg_manager.scanner import Game
from goldberg_manager.settings import (
    SteamSettingsSnapshot,
    SteamUserSettings,
    generate_game_steam_settings,
    generate_user_config,
    read_game_steam_settings,
    read_steam_appid,
    read_user_config,
    update_game_steam_appid,
    update_user_setting,
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

    def test_reads_existing_game_settings(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)

            steam_api = root / "steam_api64.dll"
            steam_api.write_bytes(b"steam api")

            steam_settings = root / "steam_settings"
            steam_settings.mkdir()

            (steam_settings / "steam_appid.txt").write_text(
                "883710\n",
                encoding="utf-8",
            )

            (steam_settings / "configs.user.ini").write_text(
                "[user::general]\n"
                "account_name=Davi\n"
                "account_steamid=76561198000000000\n"
                "language=brazilian\n"
                "ip_country=BR\n"
                "\n"
                "[user::saves]\n"
                "local_save_path=./saves\n",
                encoding="utf-8",
            )

            (steam_settings / "steam_interfaces.txt").write_text(
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

            snapshot = read_game_steam_settings(game)

            self.assertEqual(snapshot.app_id, 883710)
            self.assertEqual(
                snapshot.account_name,
                "Davi",
            )
            self.assertEqual(
                snapshot.account_steamid,
                76561198000000000,
            )
            self.assertEqual(
                snapshot.language,
                "brazilian",
            )
            self.assertEqual(
                snapshot.ip_country,
                "BR",
            )
            self.assertEqual(
                snapshot.local_save_path,
                "./saves",
            )
            self.assertIsNone(snapshot.saves_folder_name)
            self.assertTrue(snapshot.has_steam_interfaces)

    def test_reads_missing_settings_as_empty_snapshot(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)

            steam_api = root / "steam_api64.dll"
            steam_api.write_bytes(b"steam api")

            game = Game(
                name="Example Game",
                root_directory=root,
                executable=root / "Game.exe",
                steam_api=steam_api,
                steam_api_relative_path=Path("steam_api64.dll"),
                architecture="64-bit",
                source_directory=root,
            )

            snapshot = read_game_steam_settings(game)

            self.assertIsInstance(
                snapshot,
                SteamSettingsSnapshot,
            )

            self.assertIsNone(snapshot.app_id)
            self.assertIsNone(snapshot.account_name)
            self.assertIsNone(snapshot.account_steamid)
            self.assertIsNone(snapshot.language)
            self.assertIsNone(snapshot.ip_country)
            self.assertIsNone(snapshot.local_save_path)
            self.assertIsNone(snapshot.saves_folder_name)
            self.assertFalse(snapshot.has_steam_interfaces)

    def test_rejects_invalid_existing_appid(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            steam_settings = Path(temp_directory) / "steam_settings"

            steam_settings.mkdir()

            (steam_settings / "steam_appid.txt").write_text(
                "banana\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                ValueError,
                "Steam AppID inválido",
            ):
                read_steam_appid(
                    steam_settings,
                )

    def test_reads_partial_user_config(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            steam_settings = Path(temp_directory) / "steam_settings"

            steam_settings.mkdir()

            (steam_settings / "configs.user.ini").write_text(
                "[user::general]\n"
                "language=english\n"
                "\n"
                "[user::saves]\n"
                "saves_folder_name=Custom Saves\n",
                encoding="utf-8",
            )

            snapshot = read_user_config(
                steam_settings,
            )

            self.assertIsNone(snapshot.account_name)
            self.assertIsNone(snapshot.account_steamid)
            self.assertEqual(
                snapshot.language,
                "english",
            )
            self.assertIsNone(snapshot.ip_country)
            self.assertIsNone(snapshot.local_save_path)
            self.assertEqual(
                snapshot.saves_folder_name,
                "Custom Saves",
            )

    def test_updates_nick_without_removing_other_options(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            steam_settings = Path(temp_directory) / "steam_settings"
            steam_settings.mkdir()

            config_path = steam_settings / "configs.user.ini"

            config_path.write_text(
                "[user::general]\n"
                "account_name=Davi\n"
                "language=brazilian\n"
                "custom_option=keep-me\n"
                "\n"
                "[overlay::general]\n"
                "# keep this comment\n"
                "enable_overlay=1\n",
                encoding="utf-8",
            )

            update_user_setting(
                steam_settings,
                "account_name",
                "cairox09",
            )

            content = config_path.read_text(encoding="utf-8")

            self.assertIn(
                "account_name=cairox09",
                content,
            )
            self.assertIn(
                "language=brazilian",
                content,
            )
            self.assertIn(
                "custom_option=keep-me",
                content,
            )
            self.assertIn(
                "[overlay::general]",
                content,
            )
            self.assertIn(
                "# keep this comment",
                content,
            )
            self.assertIn(
                "enable_overlay=1",
                content,
            )

    def test_removes_existing_steamid(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            steam_settings = Path(temp_directory) / "steam_settings"
            steam_settings.mkdir()

            config_path = steam_settings / "configs.user.ini"

            config_path.write_text(
                "[user::general]\n"
                "account_name=Player\n"
                "account_steamid=76561198000000000\n",
                encoding="utf-8",
            )

            update_user_setting(
                steam_settings,
                "account_steamid",
                None,
            )

            content = config_path.read_text(encoding="utf-8")

            self.assertIn(
                "account_name=Player",
                content,
            )

            self.assertNotIn(
                "account_steamid=",
                content,
            )

    def test_switches_to_local_save(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            steam_settings = Path(temp_directory) / "steam_settings"
            steam_settings.mkdir()

            config_path = steam_settings / "configs.user.ini"

            config_path.write_text(
                "[user::general]\n"
                "account_name=Player\n"
                "\n"
                "[user::saves]\n"
                "saves_folder_name=Old Saves\n",
                encoding="utf-8",
            )

            update_user_setting(
                steam_settings,
                "local_save_path",
                "./saves",
            )

            content = config_path.read_text(encoding="utf-8")

            self.assertIn(
                "local_save_path=./saves",
                content,
            )

            self.assertNotIn(
                "saves_folder_name=",
                content,
            )

    def test_rejects_invalid_country_update(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            steam_settings = Path(temp_directory) / "steam_settings"

            with self.assertRaisesRegex(
                ValueError,
                "duas letras",
            ):
                update_user_setting(
                    steam_settings,
                    "ip_country",
                    "BRA",
                )

            self.assertFalse(steam_settings.exists())

    def test_updates_existing_game_appid(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)

            steam_api = root / "steam_api64.dll"
            steam_api.write_bytes(b"steam api")

            steam_settings = root / "steam_settings"
            steam_settings.mkdir()

            app_id_path = steam_settings / "steam_appid.txt"

            app_id_path.write_text(
                "111111\n",
                encoding="utf-8",
            )

            interfaces_path = steam_settings / "steam_interfaces.txt"

            interfaces_path.write_text(
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

            output = update_game_steam_appid(
                game,
                222222,
            )

            self.assertEqual(
                output,
                app_id_path,
            )

            self.assertEqual(
                app_id_path.read_text(encoding="utf-8"),
                "222222\n",
            )

            self.assertEqual(
                interfaces_path.read_text(encoding="utf-8"),
                "SteamClient021\n",
            )

    def test_rejects_unknown_country_code(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            steam_settings = Path(temp_directory) / "steam_settings"

            with self.assertRaises(ValueError):
                update_user_setting(
                    steam_settings,
                    "ip_country",
                    "ZZ",
                )

    def test_rejects_unknown_language_update(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            steam_settings = Path(temp_directory) / "steam_settings"

            with self.assertRaises(ValueError):
                update_user_setting(
                    steam_settings,
                    "language",
                    "portugues-br",
                )

    def test_normalizes_language_update(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            steam_settings = Path(temp_directory) / "steam_settings"

            update_user_setting(
                steam_settings,
                "language",
                "BRAZILIAN",
            )

            snapshot = read_user_config(steam_settings)

            self.assertEqual(
                snapshot.language,
                "brazilian",
            )


if __name__ == "__main__":
    unittest.main()
