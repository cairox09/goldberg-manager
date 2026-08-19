from __future__ import annotations

import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import Mock, patch

from rich.console import Console

from goldberg_manager.appid import AppIdCandidate
from goldberg_manager.cli import (
    GameGseResolution,
    resolve_game_gse_runtime,
    show_game_gse_status,
)
from goldberg_manager.gse_saves import GseSaveLocation, GseSaveResolution
from goldberg_manager.scanner import Game
from goldberg_manager.sentinel import (
    SentinelConfigStatus,
)


def make_game(
    root: Path,
) -> Game:
    binaries = root / "Binaries" / "Win64"

    binaries.mkdir(
        parents=True,
    )

    steam_api = binaries / "steam_api64.dll"
    steam_api.write_bytes(b"steam api")

    executable = binaries / "Game.exe"
    executable.write_bytes(b"game")

    return Game(
        name="Example Game",
        root_directory=root,
        executable=executable,
        steam_api=steam_api,
        steam_api_relative_path=Path("Binaries/Win64/steam_api64.dll"),
        architecture="64-bit",
        source_directory=root,
    )


def make_sentinel_status(
    prefix_root: Path,
) -> SentinelConfigStatus:
    return SentinelConfigStatus(
        path=Path("/config/sentinel/config.json"),
        exists=True,
        valid_json=True,
        schema_valid=True,
        prefix_paths=(prefix_root,),
        emulators=(),
    )


class GseGameResolutionTests(
    unittest.TestCase,
):
    def test_resolves_windows_global_save_from_sentinel_prefix(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)

            game = make_game(
                root / "game",
            )

            prefix_root = root / "prefixes"

            drive_c = prefix_root / "Example" / "pfx" / "drive_c"

            drive_c.mkdir(
                parents=True,
            )

            candidate = AppIdCandidate(
                app_id=212480,
                name="Example Game",
                score=100,
                source="steam_appid.txt",
            )

            with patch(
                "goldberg_manager.cli.resolve_local_appid",
                return_value=[candidate],
            ):
                resolution = resolve_game_gse_runtime(
                    game,
                    sentinel_status=make_sentinel_status(
                        prefix_root,
                    ),
                )

            self.assertEqual(
                resolution.app_id,
                212480,
            )

            self.assertTrue(
                resolution.resolved,
            )

            assert resolution.save_resolution is not None

            self.assertEqual(
                resolution.save_resolution.locations[0].root,
                (drive_c / "users" / "steamuser" / "AppData" / "Roaming" / "GSE Saves"),
            )

    def test_prefers_appid_with_existing_runtime(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)

            game = make_game(
                root / "game",
            )

            prefix_root = root / "prefixes"

            drive_c = prefix_root / "Example" / "pfx" / "drive_c"

            runtime_directory = (
                drive_c
                / "users"
                / "steamuser"
                / "AppData"
                / "Roaming"
                / "GSE Saves"
                / "212480"
            )

            runtime_directory.mkdir(
                parents=True,
            )

            candidates = [
                AppIdCandidate(
                    app_id=111111,
                    name="Wrong",
                    score=100,
                    source="manifest",
                ),
                AppIdCandidate(
                    app_id=212480,
                    name="Example Game",
                    score=95,
                    source="manifest",
                ),
            ]

            with patch(
                "goldberg_manager.cli.resolve_local_appid",
                return_value=candidates,
            ):
                resolution = resolve_game_gse_runtime(
                    game,
                    sentinel_status=make_sentinel_status(
                        prefix_root,
                    ),
                )

            self.assertEqual(
                resolution.app_id,
                212480,
            )

            self.assertTrue(
                resolution.runtime_found,
            )

    def test_prefers_appid_with_achievements_file(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)

            game = make_game(
                root / "game",
            )

            prefix_root = root / "prefixes"

            drive_c = prefix_root / "Example" / "pfx" / "drive_c"

            first_runtime = (
                drive_c
                / "users"
                / "steamuser"
                / "AppData"
                / "Roaming"
                / "GSE Saves"
                / "111111"
            )

            first_runtime.mkdir(
                parents=True,
            )

            achievements = (
                drive_c
                / "users"
                / "steamuser"
                / "AppData"
                / "Roaming"
                / "GSE Saves"
                / "212480"
                / "achievements.json"
            )

            achievements.parent.mkdir(
                parents=True,
            )

            achievements.write_text(
                "{}",
                encoding="utf-8",
            )

            candidates = [
                AppIdCandidate(
                    app_id=111111,
                    name="Candidate A",
                    score=100,
                    source="manifest",
                ),
                AppIdCandidate(
                    app_id=212480,
                    name="Candidate B",
                    score=90,
                    source="manifest",
                ),
            ]

            with patch(
                "goldberg_manager.cli.resolve_local_appid",
                return_value=candidates,
            ):
                resolution = resolve_game_gse_runtime(
                    game,
                    sentinel_status=make_sentinel_status(
                        prefix_root,
                    ),
                )

            self.assertEqual(
                resolution.app_id,
                212480,
            )

            self.assertTrue(
                resolution.achievements_found,
            )

    def test_falls_back_to_best_local_appid(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)

            game = make_game(
                root / "game",
            )

            candidate = AppIdCandidate(
                app_id=883710,
                name="Example Game",
                score=100,
                source="steam_appid.txt",
            )

            with patch(
                "goldberg_manager.cli.resolve_local_appid",
                return_value=[candidate],
            ):
                resolution = resolve_game_gse_runtime(
                    game,
                    sentinel_status=make_sentinel_status(
                        root / "empty-prefixes",
                    ),
                )

            self.assertEqual(
                resolution.app_id,
                883710,
            )

            self.assertFalse(
                resolution.resolved,
            )

    def test_reports_missing_appid(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)

            game = make_game(
                root / "game",
            )

            with patch(
                "goldberg_manager.cli.resolve_local_appid",
                return_value=[],
            ):
                resolution = resolve_game_gse_runtime(
                    game,
                    sentinel_status=make_sentinel_status(
                        root / "prefixes",
                    ),
                )

            self.assertIsNone(
                resolution.app_id,
            )

            self.assertIsNone(
                resolution.save_resolution,
            )

            self.assertFalse(
                resolution.resolved,
            )

            self.assertFalse(
                resolution.runtime_found,
            )

    def test_status_lists_ambiguous_roots_as_possible(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            game = make_game(root / "game")
            status = make_sentinel_status(root / "prefixes")
            save_resolution = GseSaveResolution(
                source="default",
                raw_value=None,
                locations=tuple(
                    GseSaveLocation(source="default", root=possible, app_id=212480)
                    for possible in (root / "first", root / "second")
                ),
            )
            resolution = GameGseResolution(
                app_id=212480,
                app_id_confidence=100,
                app_id_source="steam_appid.txt",
                save_resolution=save_resolution,
            )
            output = StringIO()
            test_console = Console(file=output, width=200, color_system=None)

            with (
                patch(
                    "goldberg_manager.cli.detect_sentinel",
                    return_value=Mock(config_path=status.path),
                ),
                patch("goldberg_manager.cli.read_sentinel_config", return_value=status),
                patch(
                    "goldberg_manager.cli.resolve_game_gse_runtime",
                    return_value=resolution,
                ),
                patch("goldberg_manager.cli.console", test_console),
                patch("goldberg_manager.cli.clear_screen"),
                patch("goldberg_manager.cli.render_header"),
                patch("goldberg_manager.cli.pause"),
            ):
                show_game_gse_status(game)

            rendered = output.getvalue()
            self.assertIn("Ambígua", rendered)
            self.assertIn("Effective root", rendered)
            self.assertIn("Não determinado", rendered)
            self.assertIn("Possible root #1", rendered)
            self.assertIn("Possible root #2", rendered)


if __name__ == "__main__":
    unittest.main()
