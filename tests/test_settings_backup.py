import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from goldberg_manager.scanner import Game
from goldberg_manager.settings_backup import (
    create_steam_settings_backup,
    list_steam_settings_backups,
    restore_steam_settings_backup,
    verify_steam_settings_backup,
)


class SteamSettingsBackupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.backup_directory = tempfile.TemporaryDirectory()

        self.backup_root_patcher = patch(
            "goldberg_manager.settings_backup.BACKUP_ROOT",
            Path(self.backup_directory.name),
        )

        self.backup_root_patcher.start()

    def tearDown(self) -> None:
        self.backup_root_patcher.stop()
        self.backup_directory.cleanup()

    def _create_game(
        self,
        root: Path,
        name: str = "Example Game",
    ) -> Game:
        binaries = root / "Binaries" / "Win64"

        binaries.mkdir(
            parents=True,
            exist_ok=True,
        )

        steam_api = binaries / "steam_api64.dll"

        executable = binaries / "Game.exe"

        steam_api.write_bytes(b"steam api")

        executable.write_bytes(b"game")

        return Game(
            name=name,
            root_directory=root,
            executable=executable,
            steam_api=steam_api,
            steam_api_relative_path=Path("Binaries/Win64/steam_api64.dll"),
            architecture="64-bit",
            source_directory=root,
        )

    def test_creates_complete_settings_backup(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)

            game = self._create_game(root)

            steam_settings = game.steam_api.parent / "steam_settings"

            nested = steam_settings / "custom"

            nested.mkdir(parents=True)

            (steam_settings / "steam_appid.txt").write_text(
                "883710\n",
                encoding="utf-8",
            )

            (steam_settings / "configs.user.ini").write_text(
                "[user::general]\naccount_name=Davi\n",
                encoding="utf-8",
            )

            (nested / "unknown.ini").write_text(
                "keep=this\n",
                encoding="utf-8",
            )

            snapshot = create_steam_settings_backup(
                game,
                created_at=datetime(
                    2026,
                    8,
                    12,
                    23,
                    30,
                    tzinfo=UTC,
                ),
            )

            self.assertTrue((snapshot / "files" / "steam_appid.txt").is_file())

            self.assertTrue((snapshot / "files" / "configs.user.ini").is_file())

            self.assertEqual(
                (snapshot / "files" / "custom" / "unknown.ini").read_text(
                    encoding="utf-8"
                ),
                "keep=this\n",
            )

            self.assertTrue(verify_steam_settings_backup(snapshot))

    def test_detects_corrupted_settings_backup(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)

            game = self._create_game(root)

            steam_settings = game.steam_api.parent / "steam_settings"

            steam_settings.mkdir()

            (steam_settings / "steam_appid.txt").write_text(
                "883710\n",
                encoding="utf-8",
            )

            snapshot = create_steam_settings_backup(game)

            (snapshot / "files" / "steam_appid.txt").write_text(
                "999999\n",
                encoding="utf-8",
            )

            self.assertFalse(verify_steam_settings_backup(snapshot))

    def test_lists_newest_backup_first(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)

            game = self._create_game(root)

            steam_settings = game.steam_api.parent / "steam_settings"

            steam_settings.mkdir()

            (steam_settings / "steam_appid.txt").write_text(
                "883710\n",
                encoding="utf-8",
            )

            older = create_steam_settings_backup(
                game,
                created_at=datetime(
                    2026,
                    8,
                    12,
                    20,
                    0,
                    tzinfo=UTC,
                ),
            )

            newer = create_steam_settings_backup(
                game,
                created_at=datetime(
                    2026,
                    8,
                    12,
                    21,
                    0,
                    tzinfo=UTC,
                ),
            )

            backups = list_steam_settings_backups(game)

            self.assertEqual(
                len(backups),
                2,
            )

            self.assertEqual(
                backups[0].path,
                newer,
            )

            self.assertEqual(
                backups[1].path,
                older,
            )

            self.assertTrue(backups[0].valid)

    def test_restores_exact_settings_snapshot(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)

            game = self._create_game(root)

            steam_settings = game.steam_api.parent / "steam_settings"

            steam_settings.mkdir()

            config_path = steam_settings / "configs.user.ini"

            config_path.write_text(
                "[user::general]\naccount_name=Davi\n",
                encoding="utf-8",
            )

            snapshot = create_steam_settings_backup(game)

            config_path.write_text(
                "[user::general]\naccount_name=Changed\n",
                encoding="utf-8",
            )

            (steam_settings / "temporary.ini").write_text(
                "remove=me\n",
                encoding="utf-8",
            )

            restore_steam_settings_backup(
                game,
                snapshot,
            )

            self.assertEqual(
                config_path.read_text(encoding="utf-8"),
                "[user::general]\naccount_name=Davi\n",
            )

            self.assertFalse((steam_settings / "temporary.ini").exists())

    def test_rejects_backup_from_another_game(
        self,
    ) -> None:
        with (
            tempfile.TemporaryDirectory() as first_directory,
            tempfile.TemporaryDirectory() as second_directory,
        ):
            first_root = Path(first_directory)
            second_root = Path(second_directory)

            first_game = self._create_game(
                first_root,
                "First Game",
            )

            second_game = self._create_game(
                second_root,
                "Second Game",
            )

            first_settings = first_game.steam_api.parent / "steam_settings"

            first_settings.mkdir()

            (first_settings / "steam_appid.txt").write_text(
                "123456\n",
                encoding="utf-8",
            )

            snapshot = create_steam_settings_backup(first_game)

            with self.assertRaisesRegex(
                ValueError,
                "outro jogo",
            ):
                restore_steam_settings_backup(
                    second_game,
                    snapshot,
                )


if __name__ == "__main__":
    unittest.main()
