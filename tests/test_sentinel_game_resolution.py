from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from goldberg_manager.appid import AppIdCandidate
from goldberg_manager.cli import resolve_game_sentinel_runtime
from goldberg_manager.scanner import Game
from goldberg_manager.sentinel import (
    SentinelConfigStatus,
    SentinelRuntimeSave,
)


def make_game() -> Game:
    root = Path("/games/Sonic")

    return Game(
        name="Sonic All-Stars Racing Transformed",
        root_directory=root,
        executable=root / "ASN_App_PcDx9_Final.exe",
        steam_api=root / "steam_api.dll",
        steam_api_relative_path=Path("steam_api.dll"),
        architecture="x86",
        source_directory=root.parent,
    )


def make_status() -> SentinelConfigStatus:
    return SentinelConfigStatus(
        path=Path("/config/sentinel/config.json"),
        exists=True,
        valid_json=True,
        schema_valid=True,
        prefix_paths=(),
        emulators=(),
    )


def make_runtime(
    app_id: int,
) -> SentinelRuntimeSave:
    drive_c = Path("/prefix/pfx/drive_c")

    saves_directory = (
        drive_c / "users" / "steamuser" / "AppData" / "Roaming" / "GSE Saves"
    )

    app_directory = saves_directory / str(app_id)

    return SentinelRuntimeSave(
        emulator_id="gse",
        prefix_path=Path("/prefix"),
        drive_c=drive_c,
        saves_directory=saves_directory,
        app_id=app_id,
        app_directory=app_directory,
        achievements_path=(app_directory / "achievements.json"),
    )


class SentinelGameResolutionTests(
    unittest.TestCase,
):
    def test_prefers_candidate_with_runtime_save(
        self,
    ) -> None:
        candidates = [
            AppIdCandidate(
                app_id=111111,
                name="Wrong candidate",
                score=100,
                source="steam_manifest",
            ),
            AppIdCandidate(
                app_id=212480,
                name="Sonic All-Stars Racing Transformed",
                score=95,
                source="steam_manifest",
            ),
        ]

        runtime_save = make_runtime(212480)

        with (
            patch(
                "goldberg_manager.cli.resolve_local_appid",
                return_value=candidates,
            ),
            patch(
                "goldberg_manager.cli.resolve_sentinel_runtime_saves",
                return_value=(runtime_save,),
            ),
        ):
            resolution = resolve_game_sentinel_runtime(
                make_game(),
                status=make_status(),
            )

        self.assertEqual(
            resolution.app_id,
            212480,
        )

        self.assertEqual(
            resolution.app_id_confidence,
            95,
        )

        self.assertTrue(
            resolution.runtime_found,
        )

        self.assertEqual(
            resolution.runtime_saves,
            (runtime_save,),
        )

    def test_falls_back_to_best_local_appid_without_runtime(
        self,
    ) -> None:
        candidates = [
            AppIdCandidate(
                app_id=212480,
                name="Sonic All-Stars Racing Transformed",
                score=100,
                source="steam_appid.txt",
            )
        ]

        with (
            patch(
                "goldberg_manager.cli.resolve_local_appid",
                return_value=candidates,
            ),
            patch(
                "goldberg_manager.cli.resolve_sentinel_runtime_saves",
                return_value=(),
            ),
        ):
            resolution = resolve_game_sentinel_runtime(
                make_game(),
                status=make_status(),
            )

        self.assertEqual(
            resolution.app_id,
            212480,
        )

        self.assertEqual(
            resolution.app_id_source,
            "steam_appid.txt",
        )

        self.assertFalse(
            resolution.runtime_found,
        )

    def test_reports_missing_appid(
        self,
    ) -> None:
        with (
            patch(
                "goldberg_manager.cli.resolve_local_appid",
                return_value=[],
            ),
            patch(
                "goldberg_manager.cli.resolve_sentinel_runtime_saves",
                return_value=(),
            ),
        ):
            resolution = resolve_game_sentinel_runtime(
                make_game(),
                status=make_status(),
            )

        self.assertIsNone(
            resolution.app_id,
        )

        self.assertIsNone(
            resolution.app_id_confidence,
        )

        self.assertIsNone(
            resolution.app_id_source,
        )

        self.assertFalse(
            resolution.runtime_found,
        )


if __name__ == "__main__":
    unittest.main()
