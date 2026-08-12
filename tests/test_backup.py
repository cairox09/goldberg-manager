from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from goldberg_manager.backup import (
    backup_game,
    current_file_matches_backup,
    get_backup_path,
    has_backup,
    restore_game_backup,
    verify_backup,
)
from goldberg_manager.scanner import Game


class BackupTests(unittest.TestCase):
    def test_backup_and_restore(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_path = Path(temporary_directory)

            game_root = temporary_path / "Test Game"
            game_data = game_root / "gamedata"

            game_data.mkdir(parents=True)

            executable = game_data / "game.exe"
            steam_api = game_data / "steam_api64.dll"

            executable.write_bytes(b"fake executable")
            steam_api.write_bytes(b"original steam api")

            game = Game(
                name="Test Game",
                root_directory=game_root,
                executable=executable,
                steam_api=steam_api,
                steam_api_relative_path=Path("gamedata/steam_api64.dll"),
                architecture="64-bit",
                source_directory=temporary_path,
            )

            backup_root = temporary_path / "backups"

            with patch("goldberg_manager.backup.BACKUP_ROOT", backup_root):
                backup_path = backup_game(game)

                self.assertTrue(backup_path.is_file())
                self.assertTrue(has_backup(game))
                self.assertTrue(verify_backup(game))
                self.assertTrue(current_file_matches_backup(game))

                steam_api.write_bytes(b"modified steam api")

                self.assertFalse(current_file_matches_backup(game))

                restore_game_backup(game)

                self.assertEqual(
                    steam_api.read_bytes(),
                    b"original steam api",
                )
                self.assertTrue(current_file_matches_backup(game))

    def test_corrupted_backup_is_not_restored(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_path = Path(temporary_directory)

            game_root = temporary_path / "Test Game"
            game_data = game_root / "gamedata"

            game_data.mkdir(parents=True)

            executable = game_data / "game.exe"
            steam_api = game_data / "steam_api64.dll"

            executable.write_bytes(b"fake executable")
            steam_api.write_bytes(b"original steam api")

            game = Game(
                name="Test Game",
                root_directory=game_root,
                executable=executable,
                steam_api=steam_api,
                steam_api_relative_path=Path("gamedata/steam_api64.dll"),
                architecture="64-bit",
                source_directory=temporary_path,
            )

            backup_root = temporary_path / "backups"

            with patch("goldberg_manager.backup.BACKUP_ROOT", backup_root):
                backup_game(game)

                backup_path = get_backup_path(game)
                backup_path.write_bytes(b"corrupted backup")

                self.assertFalse(verify_backup(game))

                with self.assertRaises(ValueError):
                    restore_game_backup(game)

                self.assertEqual(
                    steam_api.read_bytes(),
                    b"original steam api",
                )


if __name__ == "__main__":
    unittest.main()
