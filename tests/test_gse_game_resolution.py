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
from goldberg_manager.presentation.i18n import load_translations
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


class RichLikeTranslations:
    def gettext(self, message: str) -> str:
        return f"[red]{message}[/red]"


def render_status(
    game: Game,
    status: SentinelConfigStatus,
    resolution: GameGseResolution,
    *,
    translations=None,
):
    output = StringIO()
    test_console = Console(file=output, width=300, color_system=None)
    installation = Mock(config_path=status.path)
    events: list[str] = []

    def clear() -> None:
        events.append("clear")

    def render_header() -> None:
        events.append("header")

    def detect():
        events.append("detect")
        return installation

    def read_config(path):
        events.append("read_config")
        return status

    def resolve(selected_game, *, sentinel_status):
        events.append("resolve")
        return resolution

    def pause(message):
        events.append("pause")

    with (
        patch("goldberg_manager.cli.console", test_console),
        patch("goldberg_manager.cli.clear_screen", side_effect=clear) as clear_screen,
        patch(
            "goldberg_manager.cli.render_header", side_effect=render_header
        ) as header,
        patch("goldberg_manager.cli.detect_sentinel", side_effect=detect) as detector,
        patch(
            "goldberg_manager.cli.read_sentinel_config",
            side_effect=read_config,
        ) as config_reader,
        patch(
            "goldberg_manager.cli.resolve_game_gse_runtime",
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
            show_game_gse_status(game)
        else:
            show_game_gse_status(game, translations=translations)

    return output.getvalue(), {
        "installation": installation,
        "clear_screen": clear_screen,
        "header": header,
        "detector": detector,
        "config_reader": config_reader,
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


class GseGameStatusPresentationTests(unittest.TestCase):
    def test_portuguese_default_is_read_only_and_preserves_orchestration(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            game = make_game(root / "game")
            status = SentinelConfigStatus(
                path=root / "sentinel" / "config.json",
                exists=True,
                valid_json=True,
                schema_valid=True,
                prefix_paths=(),
                emulators=(),
            )
            save_resolution = GseSaveResolution(
                source="default",
                raw_value=None,
                locations=(
                    GseSaveLocation(
                        source="default",
                        root=root / "not-created",
                        app_id=212480,
                    ),
                ),
            )
            resolution = GameGseResolution(
                app_id=212480,
                app_id_confidence=100,
                app_id_source="steam_appid.txt",
                save_resolution=save_resolution,
            )

            default_translations = load_translations()
            with patch(
                "goldberg_manager.cli.load_translations",
                return_value=default_translations,
            ) as translations_loader:
                rendered, mocks = render_status(game, status, resolution)

        for expected in (
            "Jogo",
            "AppID",
            "GSE padrão",
            "Origem do save",
            "Resolução",
            "Determinada",
            "Raiz efetiva",
            "Diretório do AppID",
            "Ainda não criado",
            "achievements.json",
            "GSE • Resolução de saves",
            "Somente leitura • nenhum save ou arquivo de configuração foi alterado.",
            "steam_appid.txt",
            "212480",
            "100%",
        ):
            self.assertIn(expected, rendered)

        for mixed_label in (
            "GSE save",
            "Effective root",
            "Possible root",
            "AppID dir",
        ):
            self.assertNotIn(mixed_label, rendered)

        translations_loader.assert_called_once_with()
        self.assertEqual(
            mocks["events"],
            ["clear", "header", "detect", "read_config", "resolve", "pause"],
        )
        mocks["clear_screen"].assert_called_once_with()
        mocks["header"].assert_called_once_with()
        mocks["detector"].assert_called_once_with()
        mocks["config_reader"].assert_called_once_with(
            mocks["installation"].config_path
        )
        mocks["resolver"].assert_called_once_with(game, sentinel_status=status)
        self.assertIs(mocks["resolver"].call_args.kwargs["sentinel_status"], status)
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

    def test_explicit_english_translates_missing_appid_and_pause(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            game = make_game(root / "game")
            status = make_sentinel_status(root / "prefixes")
            resolution = GameGseResolution(
                app_id=None,
                app_id_confidence=None,
                app_id_source=None,
                save_resolution=None,
            )

            rendered, mocks = render_status(
                game,
                status,
                resolution,
                translations=load_translations("en"),
            )

        for expected in (
            "Game",
            "Unresolved",
            "GSE save",
            "Could not be resolved",
            "GSE • Save resolution",
            "Read-only • no save or configuration file was changed.",
            "AppID",
        ):
            self.assertIn(expected, rendered)

        mocks["pause"].assert_called_once_with("Press Enter to continue...")

    def test_ambiguous_roots_list_every_possible_location(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            game = make_game(root / "game")
            status = make_sentinel_status(root / "prefixes")
            possible_roots = (root / "first", root / "second")
            save_resolution = GseSaveResolution(
                source="local_save_path",
                raw_value="[cyan]./configured[/cyan]",
                locations=tuple(
                    GseSaveLocation(
                        source="local_save_path",
                        root=possible,
                        app_id=212480,
                    )
                    for possible in possible_roots
                ),
            )
            resolution = GameGseResolution(
                app_id=212480,
                app_id_confidence=100,
                app_id_source="steam_appid.txt",
                save_resolution=save_resolution,
            )

            rendered, _ = render_status(game, status, resolution)

        for expected in (
            "Ambígua",
            "Raiz efetiva",
            "Não determinado",
            "Raiz possível #1",
            "Raiz possível #2",
            "Diretório possível do AppID #1",
            "Diretório possível do AppID #2",
            "Caminho possível de achievements.json #1",
            "Caminho possível de achievements.json #2",
            "local_save_path",
            "[cyan]./configured[/cyan]",
        ):
            self.assertIn(expected, rendered)

        for possible in possible_roots:
            self.assertIn(str(possible), rendered)
            self.assertIn(str(possible / "212480"), rendered)
            self.assertIn(str(possible / "212480" / "achievements.json"), rendered)

    def test_existing_runtime_selects_effective_root_and_found_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            game = make_game(root / "game")
            status = make_sentinel_status(root / "prefixes")
            locations = tuple(
                GseSaveLocation(source="GseSavePath", root=possible, app_id=212480)
                for possible in (root / "first", root / "second")
            )
            selected = locations[1]
            selected.app_directory.mkdir(parents=True)
            selected.achievements_path.write_text("{}", encoding="utf-8")
            resolution = GameGseResolution(
                app_id=212480,
                app_id_confidence=95,
                app_id_source="steam_manifest",
                save_resolution=GseSaveResolution(
                    source="GseSavePath",
                    raw_value=str(root / "configured"),
                    locations=locations,
                ),
            )

            rendered, _ = render_status(
                game,
                status,
                resolution,
                translations=load_translations("en"),
            )

        self.assertIn("Determined", rendered)
        self.assertIn("Effective root", rendered)
        self.assertIn(str(selected.root), rendered)
        self.assertIn("Possible root #1", rendered)
        self.assertIn("Possible root #2", rendered)
        self.assertIn("Exists", rendered)
        self.assertIn("Found", rendered)
        self.assertIn("Not created yet", rendered)
        self.assertIn("GseSavePath", rendered)
        self.assertIn("achievements.json", rendered)

    def test_known_and_unknown_sources_preserve_technical_identifiers(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            game = make_game(root / "game")
            status = SentinelConfigStatus(
                path=root / "sentinel" / "config.json",
                exists=True,
                valid_json=True,
                schema_valid=True,
                prefix_paths=(),
                emulators=(),
            )

            for source, expected in (
                ("GseSavePath", "GseSavePath"),
                ("local_save_path", "local_save_path"),
                ("saves_folder_name", "saves_folder_name"),
                ("default", "GSE default"),
                (
                    "[magenta]unknown-source[/magenta]",
                    "[magenta]unknown-source[/magenta]",
                ),
            ):
                with self.subTest(source=source):
                    resolution = GameGseResolution(
                        app_id=212480,
                        app_id_confidence=None,
                        app_id_source=None,
                        save_resolution=GseSaveResolution(
                            source=source,
                            raw_value=None,
                            locations=(),
                        ),
                    )

                    rendered, _ = render_status(
                        game,
                        status,
                        resolution,
                        translations=load_translations("en"),
                    )

                    self.assertIn(expected, rendered)
                    self.assertIn("Path unresolved", rendered)
                    self.assertIn("Likely reason", rendered)
                    self.assertIn(
                        "No Wine/Proton prefix was found in Sentinel.", rendered
                    )

    def test_rich_like_dynamic_and_translated_values_render_literally(self) -> None:
        root = Path("/games/[bold]literal-root[/bold]")
        game = Game(
            name="[bold]Literal Game[/bold]",
            root_directory=root,
            executable=root / "game.exe",
            steam_api=root / "steam_api.dll",
            steam_api_relative_path=Path("steam_api.dll"),
            architecture="x86",
            source_directory=root.parent,
        )
        status = make_sentinel_status(Path("/prefixes"))
        save_root = Path("/saves/[yellow]literal[/yellow]")
        resolution = GameGseResolution(
            app_id=212480,
            app_id_confidence=95,
            app_id_source="[magenta]source[/magenta]",
            save_resolution=GseSaveResolution(
                source="[blue]unknown[/blue]",
                raw_value="[cyan]configured[/cyan]",
                locations=(
                    GseSaveLocation(
                        source="[blue]unknown[/blue]",
                        root=save_root,
                        app_id=212480,
                    ),
                ),
            ),
        )

        rendered, _ = render_status(
            game,
            status,
            resolution,
            translations=RichLikeTranslations(),
        )

        for expected in (
            "[red]Jogo[/red]",
            "[red]Resolução de saves[/red]",
            "[red]Somente leitura[/red]",
            "[bold]Literal Game[/bold]",
            "[magenta]source[/magenta]",
            "[blue]unknown[/blue]",
            "[cyan]configured[/cyan]",
            "/saves/[yellow]literal[/yellow]",
        ):
            self.assertIn(expected, rendered)

    def test_detector_config_and_resolver_exceptions_propagate_without_pause(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            game = make_game(Path(temp_directory) / "game")
            status = make_sentinel_status(Path(temp_directory) / "prefixes")
            installation = Mock(config_path=status.path)

            cases = (
                ("detect_sentinel", OSError("detect failure")),
                ("read_sentinel_config", ValueError("config failure")),
                ("resolve_game_gse_runtime", RuntimeError("resolver failure")),
            )

            for target, error in cases:
                with (
                    self.subTest(target=target),
                    patch("goldberg_manager.cli.clear_screen"),
                    patch("goldberg_manager.cli.render_header"),
                    patch(
                        "goldberg_manager.cli.detect_sentinel",
                        return_value=installation,
                        side_effect=error if target == "detect_sentinel" else None,
                    ),
                    patch(
                        "goldberg_manager.cli.read_sentinel_config",
                        return_value=status,
                        side_effect=(
                            error if target == "read_sentinel_config" else None
                        ),
                    ),
                    patch(
                        "goldberg_manager.cli.resolve_game_gse_runtime",
                        side_effect=(
                            error if target == "resolve_game_gse_runtime" else None
                        ),
                    ),
                    patch("goldberg_manager.cli.pause") as pause_mock,
                    self.assertRaisesRegex(type(error), str(error)),
                ):
                    show_game_gse_status(game)

                pause_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
