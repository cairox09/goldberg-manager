from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from goldberg_manager.gse_saves import (
    GSE_DEFAULT_SAVES_FOLDER_NAME,
    resolve_game_gse_saves,
    resolve_gse_linux_data_home,
)
from goldberg_manager.scanner import Game
from goldberg_manager.settings import (
    SteamSettingsSnapshot,
)


def make_game(
    root: Path,
    *,
    steam_api_name: str = "steam_api64.dll",
) -> Game:
    binaries = root / "Binaries" / "Win64"
    binaries.mkdir(
        parents=True,
        exist_ok=True,
    )

    steam_api = binaries / steam_api_name
    steam_api.write_bytes(b"steam api")

    executable = binaries / "Game.exe"
    executable.write_bytes(b"game")

    return Game(
        name="Example Game",
        root_directory=root,
        executable=executable,
        steam_api=steam_api,
        steam_api_relative_path=(Path("Binaries") / "Win64" / steam_api_name),
        architecture="64-bit",
        source_directory=root,
    )


class GseSaveResolutionTests(
    unittest.TestCase,
):
    def test_uses_xdg_data_home_for_native_linux(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)

            game = make_game(
                root / "game",
                steam_api_name="libsteam_api.so",
            )

            data_home = root / "xdg-data"

            resolution = resolve_game_gse_saves(
                game,
                212480,
                settings=SteamSettingsSnapshot(),
                environment={
                    "XDG_DATA_HOME": str(data_home),
                },
                home=root / "home",
            )

            self.assertEqual(
                resolution.source,
                "default",
            )

            self.assertEqual(
                resolution.locations[0].root,
                (data_home / GSE_DEFAULT_SAVES_FOLDER_NAME),
            )

            self.assertEqual(
                resolution.locations[0].app_directory,
                (data_home / GSE_DEFAULT_SAVES_FOLDER_NAME / "212480"),
            )

    def test_falls_back_to_home_local_share(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            home = root / "home"

            data_home = resolve_gse_linux_data_home(
                environment={},
                home=home,
            )

            self.assertEqual(
                data_home,
                home / ".local" / "share",
            )

    def test_uses_custom_saves_folder_name(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)

            game = make_game(
                root / "game",
                steam_api_name="libsteam_api.so",
            )

            data_home = root / "data"

            resolution = resolve_game_gse_saves(
                game,
                883710,
                settings=SteamSettingsSnapshot(
                    saves_folder_name="My GSE Saves",
                ),
                environment={
                    "XDG_DATA_HOME": str(data_home),
                },
            )

            self.assertEqual(
                resolution.source,
                "saves_folder_name",
            )

            self.assertEqual(
                resolution.raw_value,
                "My GSE Saves",
            )

            self.assertEqual(
                resolution.locations[0].root,
                data_home / "My GSE Saves",
            )

    def test_local_save_path_takes_precedence(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)

            game = make_game(
                root / "game",
            )

            resolution = resolve_game_gse_saves(
                game,
                212480,
                settings=SteamSettingsSnapshot(
                    local_save_path="./portable-saves",
                    saves_folder_name="Ignored Saves",
                ),
                environment={},
            )

            self.assertEqual(
                resolution.source,
                "local_save_path",
            )

            self.assertEqual(
                resolution.locations[0].root,
                game.steam_api.parent / "portable-saves",
            )

    def test_maps_windows_c_drive_local_save(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)

            game = make_game(
                root / "game",
            )

            drive_c = root / "prefix" / "pfx" / "drive_c"

            resolution = resolve_game_gse_saves(
                game,
                212480,
                settings=SteamSettingsSnapshot(
                    local_save_path=(r"C:\Games\Portable Saves"),
                ),
                environment={},
                wine_drive_c_paths=(drive_c,),
            )

            self.assertEqual(
                resolution.locations[0].root,
                (drive_c / "Games" / "Portable Saves"),
            )

    def test_windows_global_save_uses_drive_c(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)

            game = make_game(
                root / "game",
            )

            drive_c = root / "prefix" / "pfx" / "drive_c"

            resolution = resolve_game_gse_saves(
                game,
                212480,
                settings=SteamSettingsSnapshot(),
                environment={},
                wine_drive_c_paths=(drive_c,),
            )

            self.assertEqual(
                resolution.locations[0].root,
                (drive_c / "users" / "steamuser" / "AppData" / "Roaming" / "GSE Saves"),
            )

    def test_gse_save_path_environment_has_priority(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)

            game = make_game(
                root / "game",
                steam_api_name="libsteam_api.so",
            )

            environment_root = root / "env-saves"

            resolution = resolve_game_gse_saves(
                game,
                212480,
                settings=SteamSettingsSnapshot(
                    local_save_path="./ignored",
                ),
                environment={
                    "GseSavePath": str(environment_root),
                },
            )

            self.assertEqual(
                resolution.source,
                "GseSavePath",
            )

            self.assertEqual(
                resolution.locations[0].root,
                environment_root,
            )

    def test_does_not_fall_back_when_windows_path_is_unresolved(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)

            game = make_game(
                root / "game",
            )

            resolution = resolve_game_gse_saves(
                game,
                212480,
                settings=SteamSettingsSnapshot(
                    local_save_path=(r"D:\Portable\Saves"),
                ),
                environment={},
                wine_drive_c_paths=(),
            )

            self.assertEqual(
                resolution.source,
                "local_save_path",
            )

            self.assertFalse(
                resolution.resolved,
            )

            self.assertEqual(
                resolution.locations,
                (),
            )

    def test_detects_runtime_achievements_file(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)

            game = make_game(
                root / "game",
                steam_api_name="libsteam_api.so",
            )

            data_home = root / "data"

            achievements = data_home / "GSE Saves" / "212480" / "achievements.json"

            achievements.parent.mkdir(
                parents=True,
            )

            achievements.write_text(
                "{}",
                encoding="utf-8",
            )

            resolution = resolve_game_gse_saves(
                game,
                212480,
                settings=SteamSettingsSnapshot(),
                environment={
                    "XDG_DATA_HOME": str(data_home),
                },
            )

            location = resolution.locations[0]

            self.assertTrue(
                resolution.runtime_found,
            )

            self.assertTrue(
                resolution.achievements_found,
            )

            self.assertTrue(
                location.achievements_exists,
            )

            self.assertEqual(
                location.achievements_path,
                achievements,
            )

    def test_rejects_invalid_appid(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)

            game = make_game(
                root / "game",
            )

            with self.assertRaises(ValueError):
                resolve_game_gse_saves(
                    game,
                    0,
                    settings=SteamSettingsSnapshot(),
                )


if __name__ == "__main__":
    unittest.main()
