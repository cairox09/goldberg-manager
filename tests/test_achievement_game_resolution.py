from __future__ import annotations

import json
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from rich.console import Console

from goldberg_manager.cli import (
    GameGseResolution,
    resolve_game_achievement_progress,
    show_game_achievement_status,
    show_game_details,
)
from goldberg_manager.gse_saves import (
    GseSaveLocation,
    GseSaveResolution,
)
from goldberg_manager.scanner import Game
from goldberg_manager.sentinel import SentinelConfigStatus
from goldberg_manager.settings import SteamSettingsSnapshot


def make_game(root: Path) -> Game:
    binaries = root / "Binaries" / "Win64"
    binaries.mkdir(parents=True)

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


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def write_metadata(game: Game) -> Path:
    path = game.steam_api.parent / "steam_settings" / "achievements.json"
    write_json(
        path,
        [
            {
                "name": "ACH_ONE",
                "displayName": {
                    "english": "First achievement",
                    "brazilian": "Primeira conquista",
                },
            },
            {
                "name": "ACH_TWO",
                "displayName": "Second achievement",
            },
        ],
    )
    return path


def make_gse_resolution(
    app_id: int,
    roots: tuple[Path, ...],
) -> GameGseResolution:
    return GameGseResolution(
        app_id=app_id,
        app_id_confidence=100,
        app_id_source="steam_appid.txt",
        save_resolution=GseSaveResolution(
            source="default",
            raw_value=None,
            locations=tuple(
                GseSaveLocation(
                    source="default",
                    root=root,
                    app_id=app_id,
                )
                for root in roots
            ),
        ),
    )


def make_sentinel_status() -> SentinelConfigStatus:
    return SentinelConfigStatus(
        path=Path("/config/sentinel/config.json"),
        exists=True,
        valid_json=True,
        schema_valid=True,
        prefix_paths=(),
        emulators=(),
    )


class AchievementGameResolutionTests(unittest.TestCase):
    def resolve(
        self,
        game: Game,
        gse_resolution: GameGseResolution,
        *,
        language: str | None = None,
    ):
        with (
            patch(
                "goldberg_manager.cli.resolve_game_gse_runtime",
                return_value=gse_resolution,
            ) as gse_resolver,
            patch(
                "goldberg_manager.cli.read_game_steam_settings",
                return_value=SteamSettingsSnapshot(language=language),
            ) as settings_reader,
        ):
            resolution = resolve_game_achievement_progress(game)

        return resolution, gse_resolver, settings_reader

    def test_reads_metadata_and_existing_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            game = make_game(root / "game")
            metadata_path = write_metadata(game)
            gse_resolution = make_gse_resolution(
                212480,
                (root / "saves",),
            )
            runtime_path = gse_resolution.save_resolution.locations[0].achievements_path
            write_json(
                runtime_path,
                {
                    "ACH_ONE": {
                        "earned": True,
                    }
                },
            )

            resolution, _, _ = self.resolve(game, gse_resolution)

            self.assertEqual(resolution.metadata_path, metadata_path)
            self.assertEqual(resolution.runtime_paths, (runtime_path,))
            self.assertEqual(len(resolution.reports), 1)
            self.assertEqual(resolution.reports[0].unlocked, 1)
            self.assertEqual(resolution.reports[0].locked, 1)
            self.assertEqual(resolution.errors, ())

    def test_metadata_only_when_runtime_file_was_not_created(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            game = make_game(root / "game")
            write_metadata(game)
            gse_resolution = make_gse_resolution(
                212480,
                (root / "saves",),
            )

            resolution, _, _ = self.resolve(game, gse_resolution)

            self.assertTrue(resolution.runtime_resolved)
            self.assertEqual(resolution.runtime_paths, ())
            self.assertEqual(len(resolution.reports), 1)
            self.assertIsNone(resolution.reports[0].runtime_path)
            self.assertEqual(resolution.reports[0].unlocked, 0)
            self.assertEqual(resolution.reports[0].locked, 2)

    def test_reports_missing_metadata_without_inventing_achievements(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            game = make_game(root / "game")
            gse_resolution = make_gse_resolution(
                212480,
                (root / "saves",),
            )

            resolution, _, _ = self.resolve(game, gse_resolution)

            self.assertFalse(resolution.metadata_exists)
            self.assertEqual(resolution.reports, ())
            self.assertEqual(resolution.errors, ())

    def test_uses_language_from_steam_settings(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            game = make_game(root / "game")
            write_metadata(game)
            gse_resolution = make_gse_resolution(
                212480,
                (root / "saves",),
            )

            resolution, _, _ = self.resolve(
                game,
                gse_resolution,
                language="brazilian",
            )

            self.assertEqual(resolution.language, "brazilian")
            self.assertEqual(
                resolution.reports[0].achievements[0].definition.display_name,
                "Primeira conquista",
            )

    def test_unresolved_runtime_is_not_presented_as_confirmed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            game = make_game(root / "game")
            write_metadata(game)
            gse_resolution = make_gse_resolution(212480, ())

            resolution, _, _ = self.resolve(game, gse_resolution)

            self.assertFalse(resolution.runtime_resolved)
            self.assertEqual(resolution.reports[0].total, 2)

            output = StringIO()
            test_console = Console(
                file=output,
                width=120,
                color_system=None,
            )

            with (
                patch(
                    "goldberg_manager.cli.resolve_game_achievement_progress",
                    return_value=resolution,
                ),
                patch("goldberg_manager.cli.console", test_console),
                patch("goldberg_manager.cli.clear_screen"),
                patch("goldberg_manager.cli.render_header"),
                patch("goldberg_manager.cli.pause"),
            ):
                show_game_achievement_status(game)

            rendered = output.getvalue()

            self.assertIn("N\u00e3o resolvido", rendered)
            self.assertIn("Dispon\u00edveis", rendered)
            self.assertNotIn("Desbloqueadas", rendered)
            self.assertNotIn("Bloqueadas", rendered)
            self.assertNotIn("Conclus\u00e3o", rendered)

    def test_preserves_multiple_runtimes_as_separate_reports(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            game = make_game(root / "game")
            write_metadata(game)
            gse_resolution = make_gse_resolution(
                212480,
                (
                    root / "prefix-a" / "GSE Saves",
                    root / "prefix-b" / "GSE Saves",
                ),
            )
            first_path = gse_resolution.save_resolution.locations[0].achievements_path
            second_path = gse_resolution.save_resolution.locations[1].achievements_path
            write_json(
                first_path,
                {
                    "ACH_ONE": {
                        "earned": True,
                    }
                },
            )
            write_json(
                second_path,
                {
                    "ACH_TWO": {
                        "earned": True,
                    }
                },
            )

            resolution, _, _ = self.resolve(game, gse_resolution)

            self.assertEqual(
                resolution.runtime_paths,
                (first_path, second_path),
            )
            self.assertEqual(len(resolution.reports), 2)
            self.assertEqual(
                tuple(report.runtime_path for report in resolution.reports),
                (first_path, second_path),
            )
            self.assertEqual(
                tuple(report.unlocked for report in resolution.reports),
                (1, 1),
            )
            self.assertFalse(resolution.runtime_resolved)

            output = StringIO()
            test_console = Console(file=output, width=160, color_system=None)

            with (
                patch(
                    "goldberg_manager.cli.resolve_game_achievement_progress",
                    return_value=resolution,
                ),
                patch("goldberg_manager.cli.console", test_console),
                patch("goldberg_manager.cli.clear_screen"),
                patch("goldberg_manager.cli.render_header"),
                patch("goldberg_manager.cli.pause"),
            ):
                show_game_achievement_status(game)

            rendered = output.getvalue()
            self.assertIn("2 arquivos encontrados", rendered)
            self.assertIn("Runtime #1", rendered)
            self.assertIn("Runtime #2", rendered)

    def test_records_invalid_runtime_without_raising(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            game = make_game(root / "game")
            write_metadata(game)
            gse_resolution = make_gse_resolution(
                212480,
                (root / "saves",),
            )
            runtime_path = gse_resolution.save_resolution.locations[0].achievements_path
            runtime_path.parent.mkdir(parents=True)
            runtime_path.write_text("{invalid", encoding="utf-8")

            resolution, _, _ = self.resolve(game, gse_resolution)

            self.assertEqual(resolution.runtime_paths, (runtime_path,))
            self.assertEqual(resolution.reports, ())
            self.assertEqual(len(resolution.errors), 1)
            self.assertEqual(resolution.errors[0].path, runtime_path)
            self.assertIn("JSON inv\u00e1lido", resolution.errors[0].message)

    def test_keeps_valid_report_when_another_runtime_is_invalid(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            game = make_game(root / "game")
            write_metadata(game)
            gse_resolution = make_gse_resolution(
                212480,
                (
                    root / "valid-saves",
                    root / "invalid-saves",
                ),
            )
            valid_path = gse_resolution.save_resolution.locations[0].achievements_path
            invalid_path = gse_resolution.save_resolution.locations[1].achievements_path
            write_json(
                valid_path,
                {
                    "ACH_ONE": {
                        "earned": True,
                    }
                },
            )
            invalid_path.parent.mkdir(parents=True)
            invalid_path.write_text("{invalid", encoding="utf-8")

            resolution, _, _ = self.resolve(game, gse_resolution)

            self.assertEqual(len(resolution.reports), 1)
            self.assertEqual(resolution.reports[0].runtime_path, valid_path)
            self.assertEqual(resolution.reports[0].unlocked, 1)
            self.assertEqual(len(resolution.errors), 1)
            self.assertEqual(resolution.errors[0].path, invalid_path)

    def test_records_invalid_metadata_without_reading_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            game = make_game(root / "game")
            metadata_path = (
                game.steam_api.parent / "steam_settings" / "achievements.json"
            )
            metadata_path.parent.mkdir(parents=True)
            metadata_path.write_text("{invalid", encoding="utf-8")
            gse_resolution = make_gse_resolution(
                212480,
                (root / "saves",),
            )

            resolution, _, _ = self.resolve(game, gse_resolution)

            self.assertEqual(resolution.reports, ())
            self.assertEqual(len(resolution.errors), 1)
            self.assertEqual(resolution.errors[0].path, metadata_path)

    def test_reuses_existing_gse_resolution(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            game = make_game(root / "game")
            gse_resolution = make_gse_resolution(
                212480,
                (root / "saves",),
            )
            sentinel_status = make_sentinel_status()

            with (
                patch(
                    "goldberg_manager.cli.resolve_game_gse_runtime",
                    return_value=gse_resolution,
                ) as gse_resolver,
                patch(
                    "goldberg_manager.cli.read_game_steam_settings",
                    return_value=SteamSettingsSnapshot(),
                ) as settings_reader,
            ):
                resolve_game_achievement_progress(
                    game,
                    sentinel_status=sentinel_status,
                )

            gse_resolver.assert_called_once_with(
                game,
                sentinel_status=sentinel_status,
            )
            settings_reader.assert_called_once_with(game)

    def test_game_details_routes_each_action_correctly(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            game = make_game(Path(temp_directory) / "game")
            choices = [
                "Ver perfil do jogo",
                "Verificar achievements / progresso",
                "Verificar GSE saves",
                "Verificar Sentinel",
                "Verificar integração Sentinel",
                "Corrigir integração Sentinel",
                "Fazer backup da Steam API",
                "Restaurar Steam API original",
                "Voltar",
            ]

            with (
                patch("goldberg_manager.cli.questionary.select") as select,
                patch("goldberg_manager.cli.show_game_profile") as profile,
                patch("goldberg_manager.cli.show_game_achievement_status") as progress,
                patch("goldberg_manager.cli.show_game_gse_status") as gse_status,
                patch("goldberg_manager.cli.show_game_sentinel_status") as sentinel,
                patch(
                    "goldberg_manager.cli.show_game_sentinel_integration_status"
                ) as integration,
                patch(
                    "goldberg_manager.cli.repair_game_sentinel_integration"
                ) as repair_integration,
                patch("goldberg_manager.cli.create_game_backup") as backup,
                patch("goldberg_manager.cli.restore_game_api") as restore,
                patch("goldberg_manager.cli.has_backup", return_value=False),
                patch("goldberg_manager.cli.clear_screen"),
                patch("goldberg_manager.cli.render_header"),
                patch("goldberg_manager.cli.console.print"),
            ):
                select.return_value.ask.side_effect = choices

                show_game_details(game)

            self.assertEqual(
                select.call_args_list[0].kwargs["choices"],
                choices,
            )
            profile.assert_called_once_with(game)
            progress.assert_called_once_with(game)
            gse_status.assert_called_once_with(game)
            sentinel.assert_called_once_with(game)
            integration.assert_called_once_with(game)
            repair_integration.assert_called_once_with(game)
            backup.assert_called_once_with(game)
            restore.assert_called_once_with(game)


if __name__ == "__main__":
    unittest.main()
