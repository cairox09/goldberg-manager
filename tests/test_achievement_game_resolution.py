from __future__ import annotations

import json
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import ANY, patch

from rich.console import Console

from goldberg_manager.achievements import read_achievement_report
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
from goldberg_manager.presentation.i18n import load_translations
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


class RichLikeTranslations:
    def gettext(self, message: str) -> str:
        return f"[red]{message}[/red]"


def render_achievement_status(
    game: Game,
    resolution,
    *,
    translations=None,
):
    output = StringIO()
    test_console = Console(file=output, width=300, color_system=None)
    events: list[str] = []

    def clear() -> None:
        events.append("clear")

    def render_header() -> None:
        events.append("header")

    def resolve(selected_game):
        events.append("resolve")
        if isinstance(resolution, BaseException):
            raise resolution
        return resolution

    def pause(message):
        events.append("pause")

    with (
        patch("goldberg_manager.cli.console", test_console),
        patch("goldberg_manager.cli.clear_screen", side_effect=clear) as clear_screen,
        patch(
            "goldberg_manager.cli.render_header",
            side_effect=render_header,
        ) as header,
        patch(
            "goldberg_manager.cli.resolve_game_achievement_progress",
            side_effect=resolve,
        ) as resolver,
        patch("goldberg_manager.cli.pause", side_effect=pause) as pause_mock,
        patch("goldberg_manager.cli.apply_game_sentinel_repair") as repair,
        patch("goldberg_manager.cli.save_config") as config_writer,
        patch("goldberg_manager.cli.backup_game") as backup,
        patch("goldberg_manager.cli.restore_game_backup") as restore,
        patch("goldberg_manager.cli.generate_game_steam_settings") as settings_writer,
        patch("goldberg_manager.cli.subprocess.run") as subprocess_run,
    ):
        if translations is None:
            show_game_achievement_status(game)
        else:
            show_game_achievement_status(game, translations=translations)

    return output.getvalue(), {
        "clear_screen": clear_screen,
        "header": header,
        "resolver": resolver,
        "pause": pause_mock,
        "repair": repair,
        "config_writer": config_writer,
        "backup": backup,
        "restore": restore,
        "settings_writer": settings_writer,
        "subprocess_run": subprocess_run,
        "events": events,
    }


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

    def test_default_portuguese_loads_once_and_preserves_read_only_sequence(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            game = make_game(root / "game")
            write_metadata(game)
            gse_resolution = make_gse_resolution(212480, (root / "saves",))
            resolution, _, _ = self.resolve(game, gse_resolution)
            default_translations = load_translations()

            with patch(
                "goldberg_manager.cli.load_translations",
                return_value=default_translations,
            ) as translations_loader:
                rendered, mocks = render_achievement_status(game, resolution)

        for expected in (
            "Conquistas • Progresso",
            "Metadados",
            "Encontrada",
            "achievements.json • Ainda não criado",
            "Runtime esperado",
            "Somente leitura • nenhum arquivo de conquistas foi alterado.",
        ):
            self.assertIn(expected, rendered)

        translations_loader.assert_called_once_with()
        self.assertEqual(mocks["events"], ["clear", "header", "resolve", "pause"])
        mocks["clear_screen"].assert_called_once_with()
        mocks["header"].assert_called_once_with()
        mocks["resolver"].assert_called_once_with(game)
        mocks["pause"].assert_called_once_with("Pressione Enter para continuar...")
        for mutation in (
            "repair",
            "config_writer",
            "backup",
            "restore",
            "settings_writer",
            "subprocess_run",
        ):
            mocks[mutation].assert_not_called()

    def test_explicit_english_translates_missing_appid_and_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            game = make_game(root / "game")
            resolution, _, _ = self.resolve(
                game,
                GameGseResolution(
                    app_id=None,
                    app_id_confidence=None,
                    app_id_source=None,
                    save_resolution=None,
                ),
            )

            with patch("goldberg_manager.cli.load_translations") as loader:
                rendered, mocks = render_achievement_status(
                    game,
                    resolution,
                    translations=load_translations("en"),
                )

        for expected in (
            "Game",
            "Unresolved",
            "Metadata",
            "Not found",
            "Language",
            "Achievements • Progress",
            "Read-only • no achievement file was changed.",
        ):
            self.assertIn(expected, rendered)

        loader.assert_not_called()
        mocks["pause"].assert_called_once_with("Press Enter to continue...")

    def test_english_runtime_report_preserves_aggregate_counts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            game = make_game(root / "game")
            write_metadata(game)
            gse_resolution = make_gse_resolution(212480, (root / "saves",))
            runtime_path = gse_resolution.save_resolution.locations[0].achievements_path
            write_json(
                runtime_path,
                {
                    "ACH_ONE": {"earned": True},
                    "ACH_TWO": {
                        "earned": False,
                        "progress": 1,
                        "max_progress": 2,
                    },
                    "[cyan]ACH_UNKNOWN[/cyan]": {"earned": False},
                },
            )
            resolution, _, _ = self.resolve(game, gse_resolution)

            rendered, mocks = render_achievement_status(
                game,
                resolution,
                translations=load_translations("en"),
            )

        self.assertIn("1 file found", rendered)
        self.assertRegex(rendered, r"Available\s+2")
        self.assertRegex(rendered, r"Unlocked\s+1")
        self.assertRegex(rendered, r"Locked\s+1")
        self.assertRegex(rendered, r"Partial\s+1")
        self.assertRegex(rendered, r"Completion\s+50\.0%")
        self.assertRegex(rendered, r"Runtime without metadata\s+1")
        self.assertNotIn("[cyan]ACH_UNKNOWN[/cyan]", rendered)
        mocks["resolver"].assert_called_once_with(game)

    def test_english_ui_does_not_override_steam_metadata_language(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            game = make_game(root / "game")
            metadata_path = write_metadata(game)
            gse_resolution = make_gse_resolution(212480, (root / "saves",))
            reports = []

            def read_report(*args, **kwargs):
                report = read_achievement_report(*args, **kwargs)
                reports.append(report)
                return report

            output = StringIO()
            test_console = Console(file=output, width=300, color_system=None)

            with (
                patch("goldberg_manager.cli.console", test_console),
                patch("goldberg_manager.cli.clear_screen"),
                patch("goldberg_manager.cli.render_header"),
                patch("goldberg_manager.cli.pause"),
                patch(
                    "goldberg_manager.cli.resolve_game_gse_runtime",
                    return_value=gse_resolution,
                ),
                patch(
                    "goldberg_manager.cli.read_game_steam_settings",
                    return_value=SteamSettingsSnapshot(language="brazilian"),
                ),
                patch(
                    "goldberg_manager.game_resolution.read_achievement_report",
                    side_effect=read_report,
                ) as achievement_reader,
                patch(
                    "goldberg_manager.cli.resolve_game_achievement_progress",
                    wraps=resolve_game_achievement_progress,
                ) as resolver,
            ):
                show_game_achievement_status(
                    game,
                    translations=load_translations("en"),
                )

        rendered = output.getvalue()
        self.assertIn("Language", rendered)
        self.assertIn("brazilian", rendered)
        self.assertIn("Achievements • Progress", rendered)
        resolver.assert_called_once_with(game)
        achievement_reader.assert_called_once_with(
            metadata_path,
            language="brazilian",
        )
        self.assertEqual(reports[0].metadata_path, metadata_path)
        self.assertEqual(
            reports[0].achievements[0].definition.display_name,
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

            rendered, mocks = render_achievement_status(game, resolution)

            self.assertIn("N\u00e3o resolvido", rendered)
            self.assertIn("Dispon\u00edveis", rendered)
            self.assertNotIn("Desbloqueadas", rendered)
            self.assertNotIn("Bloqueadas", rendered)
            self.assertNotIn("Conclus\u00e3o", rendered)
            mocks["resolver"].assert_called_once_with(game)

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

            rendered, _ = render_achievement_status(game, resolution)
            self.assertIn("2 arquivos encontrados", rendered)
            self.assertIn("Runtime #1", rendered)
            self.assertIn("Runtime #2", rendered)

    def test_renders_valid_and_invalid_runtimes_independently_in_english(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            game = make_game(root / "game")
            write_metadata(game)
            gse_resolution = make_gse_resolution(
                212480,
                (
                    root / "valid-saves",
                    root / "[yellow]invalid-saves[/yellow]",
                ),
            )
            valid_path = gse_resolution.save_resolution.locations[0].achievements_path
            invalid_path = gse_resolution.save_resolution.locations[1].achievements_path
            write_json(valid_path, {"ACH_ONE": {"earned": True}})
            invalid_path.parent.mkdir(parents=True)
            invalid_path.write_text("{invalid", encoding="utf-8")
            resolution, _, _ = self.resolve(game, gse_resolution)

            rendered, mocks = render_achievement_status(
                game,
                resolution,
                translations=load_translations("en"),
            )

        self.assertIn("2 files found", rendered)
        self.assertIn("Achievements • Runtime #1", rendered)
        self.assertIn("Achievements • Runtime #2", rendered)
        self.assertIn("Invalid runtime: ", rendered)
        self.assertIn(str(invalid_path), rendered)
        self.assertIn("JSON inválido", rendered)
        mocks["pause"].assert_called_once_with("Press Enter to continue...")

    def test_invalid_metadata_translates_only_error_framing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            game = make_game(root / "game")
            metadata_path = (
                game.steam_api.parent / "steam_settings" / "achievements.json"
            )
            metadata_path.parent.mkdir(parents=True)
            metadata_path.write_text("{invalid", encoding="utf-8")
            gse_resolution = make_gse_resolution(212480, (root / "saves",))
            resolution, _, _ = self.resolve(game, gse_resolution)

            rendered, mocks = render_achievement_status(
                game,
                resolution,
                translations=load_translations("en"),
            )

        self.assertIn("Invalid", rendered)
        self.assertIn("Could not read metadata.", rendered)
        self.assertIn("JSON inválido", rendered)
        self.assertIn(str(metadata_path), rendered)
        mocks["pause"].assert_called_once_with("Press Enter to continue...")

    def test_handled_resolver_error_is_translated_and_renders_literal_text(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            game = make_game(Path(temp_directory) / "game")
            error = ValueError("[bold]literal resolver error[/bold]")

            rendered, mocks = render_achievement_status(
                game,
                error,
                translations=load_translations("en"),
            )

        self.assertIn("Could not resolve achievement progress.", rendered)
        self.assertIn("[bold]literal resolver error[/bold]", rendered)
        self.assertEqual(mocks["events"], ["clear", "header", "resolve", "pause"])
        mocks["pause"].assert_called_once_with("Press Enter to continue...")

    def test_unexpected_resolver_error_still_propagates_without_pause(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            game = make_game(Path(temp_directory) / "game")

            with (
                patch("goldberg_manager.cli.clear_screen"),
                patch("goldberg_manager.cli.render_header"),
                patch(
                    "goldberg_manager.cli.resolve_game_achievement_progress",
                    side_effect=RuntimeError("unexpected"),
                ) as resolver,
                patch("goldberg_manager.cli.pause") as pause_mock,
                self.assertRaisesRegex(RuntimeError, "unexpected"),
            ):
                show_game_achievement_status(
                    game,
                    translations=load_translations("en"),
                )

        resolver.assert_called_once_with(game)
        pause_mock.assert_not_called()

    def test_rich_like_dynamic_and_translated_values_render_literally(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory) / "[blue]achievement-status-root[/blue]"
            original = make_game(root)
            game = Game(
                name="[bold]Literal Game[/bold]",
                root_directory=original.root_directory,
                executable=original.executable,
                steam_api=original.steam_api,
                steam_api_relative_path=original.steam_api_relative_path,
                architecture=original.architecture,
                source_directory=original.source_directory,
            )
            metadata_path = write_metadata(game)
            gse_resolution = make_gse_resolution(212480, ())
            resolution, _, _ = self.resolve(
                game,
                gse_resolution,
                language="[magenta]brazilian[/magenta]",
            )

            rendered, _ = render_achievement_status(
                game,
                resolution,
                translations=RichLikeTranslations(),
            )

        for expected in (
            "[bold]Literal Game[/bold]",
            str(metadata_path),
            "[magenta]brazilian[/magenta]",
            "[red]Jogo[/red]",
            "[red]Conquistas[/red] • [red]Progresso[/red]",
            (
                "[red]Somente leitura[/red] • "
                "[red]nenhum arquivo de conquistas foi alterado.[/red]"
            ),
        ):
            self.assertIn(expected, rendered)

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
                "profile",
                "achievement_progress",
                "gse_saves",
                "sentinel_status",
                "sentinel_integration",
                "sentinel_repair",
                "steam_api_backup",
                "steam_api_restore",
                "back",
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
                [choice.value for choice in select.call_args_list[0].kwargs["choices"]],
                choices,
            )
            profile.assert_called_once_with(game)
            progress.assert_called_once_with(game, translations=ANY)
            gse_status.assert_called_once_with(game, translations=ANY)
            sentinel.assert_called_once_with(game, translations=ANY)
            integration.assert_called_once_with(game)
            repair_integration.assert_called_once_with(game)
            backup.assert_called_once_with(game)
            restore.assert_called_once_with(game)


if __name__ == "__main__":
    unittest.main()
