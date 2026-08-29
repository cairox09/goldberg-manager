from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from rich.console import Console
from rich.table import Table

from goldberg_manager.cli import (
    GameGseResolution,
    GameSentinelIntegrationResolution,
    _add_sentinel_repair_rows,
    resolve_game_sentinel_integration,
    show_game_sentinel_integration_status,
)
from goldberg_manager.gse_saves import GseSaveLocation, GseSaveResolution
from goldberg_manager.presentation.i18n import load_translations
from goldberg_manager.scanner import Game
from goldberg_manager.sentinel import (
    SENTINEL_GOLDBERG_EMULATOR_ID,
    SENTINEL_GSE_EMULATOR_ID,
    SentinelConfigStatus,
    SentinelEmulator,
    SentinelInstallation,
    SentinelRuntimeSave,
    SentinelSaveRoot,
)
from goldberg_manager.sentinel_integration import (
    SentinelGseCoverage,
    SentinelGseLocationCoverage,
    resolve_sentinel_gse_coverage,
)

APP_ID = 212480


class RichLikeTranslations:
    def gettext(self, message: str) -> str:
        return f"[red]{message}[/red]"


def make_game(root: Path) -> Game:
    binaries = root / "Binaries" / "Win64"
    binaries.mkdir(parents=True)
    steam_api = binaries / "steam_api64.dll"
    steam_api.write_bytes(b"steam api")
    executable = binaries / "Game.exe"
    executable.write_bytes(b"game")
    return Game(
        name="Sonic & All-Stars Racing Transformed",
        root_directory=root,
        executable=executable,
        steam_api=steam_api,
        steam_api_relative_path=Path("Binaries/Win64/steam_api64.dll"),
        architecture="64-bit",
        source_directory=root,
    )


def make_status(
    *,
    exists: bool = True,
    valid_json: bool = True,
    schema_valid: bool = True,
    prefixes: tuple[Path, ...] = (Path("/prefixes"),),
    emulator_ids: tuple[str, ...] = (SENTINEL_GSE_EMULATOR_ID,),
    should_notify: bool = True,
) -> SentinelConfigStatus:
    return SentinelConfigStatus(
        path=Path("/config/sentinel/config.json"),
        exists=exists,
        valid_json=valid_json,
        schema_valid=schema_valid,
        prefix_paths=prefixes,
        emulators=tuple(
            SentinelEmulator(
                id=emulator_id,
                should_notify=should_notify,
            )
            for emulator_id in emulator_ids
        ),
    )


def make_integration(
    status: SentinelConfigStatus,
    effective_roots: tuple[Path, ...],
    *,
    covered_indexes: tuple[int, ...] = (),
    sentinel_root_paths: tuple[Path, ...] = (),
    runtime_emulator_ids: tuple[str, ...] = (),
    app_id: int | None = APP_ID,
) -> GameSentinelIntegrationResolution:
    locations = tuple(
        GseSaveLocation(source="test", root=root, app_id=APP_ID)
        for root in effective_roots
    )
    save_resolution = GseSaveResolution(
        source="test",
        raw_value=None,
        locations=locations,
    )
    sentinel_roots = tuple(
        SentinelSaveRoot(
            emulator_id=SENTINEL_GSE_EMULATOR_ID,
            prefix_path=Path("/prefixes"),
            drive_c=Path("/prefixes/Game/pfx/drive_c"),
            path=root,
        )
        for root in sentinel_root_paths
    )
    location_coverages = tuple(
        SentinelGseLocationCoverage(
            location=location,
            matching_roots=(sentinel_roots[index],) if index in covered_indexes else (),
        )
        for index, location in enumerate(locations)
    )
    runtime_matches = tuple(
        SentinelRuntimeSave(
            emulator_id=emulator_id,
            prefix_path=Path("/prefixes"),
            drive_c=Path("/prefixes/Game/pfx/drive_c"),
            saves_directory=Path("/runtime") / emulator_id,
            app_id=APP_ID,
            app_directory=Path("/runtime") / emulator_id / str(APP_ID),
            achievements_path=(
                Path("/runtime") / emulator_id / str(APP_ID) / "achievements.json"
            ),
        )
        for emulator_id in runtime_emulator_ids
    )
    coverage = SentinelGseCoverage(
        app_id=app_id,
        sentinel_status=status,
        save_resolution=(
            save_resolution
            if app_id is not None and len(effective_roots) <= 1
            else None
        ),
        gse_save_roots=sentinel_roots,
        location_coverages=location_coverages,
        runtime_matches=runtime_matches,
        gse_runtime_matches=tuple(
            match
            for match in runtime_matches
            if match.emulator_id == SENTINEL_GSE_EMULATOR_ID
        ),
        legacy_runtime_matches=tuple(
            match
            for match in runtime_matches
            if match.emulator_id == SENTINEL_GOLDBERG_EMULATOR_ID
        ),
    )
    return GameSentinelIntegrationResolution(
        gse_resolution=GameGseResolution(
            app_id=app_id,
            app_id_confidence=100 if app_id is not None else None,
            app_id_source="steam_appid.txt" if app_id is not None else None,
            save_resolution=save_resolution if app_id is not None else None,
        ),
        coverage=coverage,
    )


def run_integration(
    game: Game,
    status: SentinelConfigStatus,
    resolution: GameSentinelIntegrationResolution,
    *,
    installed: bool = True,
    executable: Path = Path("/usr/bin/sentinel"),
    translations=None,
):
    installation = SentinelInstallation(
        executable=executable if installed else None,
        config_path=status.path,
        data_directory=Path("/data/sentinel"),
        state_directory=Path("/state/sentinel"),
        log_path=Path("/state/sentinel/logs/sentinel.log"),
    )
    output = StringIO()
    test_console = Console(
        file=output,
        width=200,
        color_system=None,
    )
    events: list[str] = []

    def clear() -> None:
        events.append("clear")

    def header() -> None:
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

    def wait(message):
        events.append("pause")

    with (
        patch("goldberg_manager.cli.detect_sentinel", side_effect=detect) as detector,
        patch(
            "goldberg_manager.cli.read_sentinel_config",
            side_effect=read_config,
        ) as config_reader,
        patch(
            "goldberg_manager.application.game_sentinel_repair."
            "resolve_game_sentinel_integration",
            side_effect=resolve,
        ) as resolver,
        patch("goldberg_manager.cli.console", test_console),
        patch("goldberg_manager.cli.clear_screen", side_effect=clear) as clear_screen,
        patch(
            "goldberg_manager.cli.render_header", side_effect=header
        ) as render_header,
        patch("goldberg_manager.cli.pause", side_effect=wait) as pause,
        patch(
            "goldberg_manager.cli._add_sentinel_repair_rows",
            wraps=_add_sentinel_repair_rows,
        ) as repair_rows,
        patch("goldberg_manager.cli.apply_game_sentinel_repair") as repair,
        patch("goldberg_manager.cli.save_config") as config_writer,
        patch("goldberg_manager.cli.backup_game") as backup,
        patch("goldberg_manager.cli.restore_game_backup") as restore,
        patch("goldberg_manager.cli.generate_game_steam_settings") as settings_writer,
        patch("goldberg_manager.cli.subprocess.run") as subprocess_run,
    ):
        if translations is None:
            show_game_sentinel_integration_status(game)
        else:
            show_game_sentinel_integration_status(game, translations=translations)

    resolver.assert_called_once_with(game, sentinel_status=status)
    return output.getvalue(), {
        "installation": installation,
        "clear_screen": clear_screen,
        "render_header": render_header,
        "detector": detector,
        "config_reader": config_reader,
        "resolver": resolver,
        "pause": pause,
        "repair_rows": repair_rows,
        "repair": repair,
        "config_writer": config_writer,
        "backup": backup,
        "restore": restore,
        "settings_writer": settings_writer,
        "subprocess_run": subprocess_run,
        "events": events,
    }


def render_integration(
    game: Game,
    status: SentinelConfigStatus,
    resolution: GameSentinelIntegrationResolution,
    *,
    installed: bool = True,
    executable: Path = Path("/usr/bin/sentinel"),
    translations=None,
) -> str:
    rendered, _ = run_integration(
        game,
        status,
        resolution,
        installed=installed,
        executable=executable,
        translations=translations,
    )
    return rendered


def rendered_row_value(rendered: str, label: str) -> str:
    line = next(line for line in rendered.splitlines() if label in line)
    return line.split(label, 1)[1].strip(" │")


class SentinelGameIntegrationTests(unittest.TestCase):
    def test_orchestration_reuses_gse_resolution_and_selected_appid(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            game = make_game(Path(temp_directory) / "game")
            status = make_status()
            save_resolution = GseSaveResolution(
                source="local_save_path",
                raw_value="./saves",
                locations=(
                    GseSaveLocation(
                        source="local_save_path",
                        root=game.steam_api.parent / "saves",
                        app_id=APP_ID,
                    ),
                ),
            )
            gse_resolution = GameGseResolution(
                app_id=APP_ID,
                app_id_confidence=100,
                app_id_source="steam_appid.txt",
                save_resolution=save_resolution,
            )
            expected_coverage = make_integration(
                status,
                (save_resolution.locations[0].root,),
            ).coverage

            with (
                patch(
                    "goldberg_manager.cli.resolve_game_gse_runtime",
                    return_value=gse_resolution,
                ) as gse_resolver,
                patch(
                    "goldberg_manager.cli.resolve_sentinel_gse_coverage",
                    return_value=expected_coverage,
                ) as coverage_resolver,
            ):
                resolution = resolve_game_sentinel_integration(
                    game,
                    sentinel_status=status,
                )

            gse_resolver.assert_called_once_with(
                game,
                sentinel_status=status,
            )
            coverage_resolver.assert_called_once_with(
                status,
                APP_ID,
                save_resolution,
            )
            self.assertIs(resolution.gse_resolution, gse_resolution)
            self.assertIs(resolution.coverage, expected_coverage)

    def test_orchestration_detects_config_when_status_is_not_provided(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            game = make_game(Path(temp_directory) / "game")
            status = make_status()
            installation = SentinelInstallation(
                executable=Path("/usr/bin/sentinel"),
                config_path=status.path,
                data_directory=Path("/data/sentinel"),
                state_directory=Path("/state/sentinel"),
                log_path=Path("/state/sentinel/logs/sentinel.log"),
            )
            gse_resolution = GameGseResolution(
                app_id=None,
                app_id_confidence=None,
                app_id_source=None,
                save_resolution=None,
            )

            with (
                patch(
                    "goldberg_manager.cli.detect_sentinel",
                    return_value=installation,
                ) as detector,
                patch(
                    "goldberg_manager.cli.read_sentinel_config",
                    return_value=status,
                ) as config_reader,
                patch(
                    "goldberg_manager.cli.resolve_game_gse_runtime",
                    return_value=gse_resolution,
                ),
                patch("goldberg_manager.cli.resolve_sentinel_gse_coverage"),
            ):
                resolve_game_sentinel_integration(game)

            detector.assert_called_once_with()
            config_reader.assert_called_once_with(installation.config_path)

    def test_portuguese_default_loads_once_and_preserves_read_only_sequence(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            game = make_game(Path(temp_directory) / "game")
            status = make_status()
            root = Path(
                "/games/Game/pfx/drive_c/users/steamuser/AppData/Roaming/GSE Saves"
            )
            resolution = make_integration(status, (root,))
            default_translations = load_translations()

            with patch(
                "goldberg_manager.cli.load_translations",
                return_value=default_translations,
            ) as translations_loader:
                rendered, mocks = run_integration(game, status, resolution)

        translations_loader.assert_called_once_with()
        self.assertEqual(
            mocks["events"],
            ["clear", "header", "detect", "read_config", "resolve", "pause"],
        )
        mocks["clear_screen"].assert_called_once_with()
        mocks["render_header"].assert_called_once_with()
        mocks["detector"].assert_called_once_with()
        mocks["config_reader"].assert_called_once_with(
            mocks["installation"].config_path
        )
        self.assertIs(mocks["resolver"].call_args.kwargs["sentinel_status"], status)
        mocks["pause"].assert_called_once_with("Pressione Enter para continuar...")

        plan = mocks["repair_rows"].call_args.args[1]
        self.assertIs(plan.coverage, resolution.coverage)
        self.assertIs(plan.coverage.sentinel_status, status)
        self.assertIs(
            mocks["repair_rows"].call_args.kwargs["translations"],
            default_translations,
        )
        self.assertIn("Configuração existente", rendered)
        self.assertIn("Cobertura", rendered)
        self.assertIn("Prefixos candidatos", rendered)
        self.assertIn(str(APP_ID), rendered)
        self.assertIn(str(plan.candidate_prefixes[0]), rendered)

        for mutation in (
            "repair",
            "config_writer",
            "backup",
            "restore",
            "settings_writer",
            "subprocess_run",
        ):
            mocks[mutation].assert_not_called()

    def test_explicit_english_reuses_translation_and_translates_pause(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            game = make_game(Path(temp_directory) / "game")
            status = make_status(
                exists=False,
                valid_json=False,
                schema_valid=False,
                prefixes=(),
                emulator_ids=(),
            )
            translations = load_translations("en")

            with patch("goldberg_manager.cli.load_translations") as loader:
                rendered, mocks = run_integration(
                    game,
                    status,
                    make_integration(status, (), app_id=None),
                    installed=False,
                    translations=translations,
                )

        loader.assert_not_called()
        self.assertIs(
            mocks["repair_rows"].call_args.kwargs["translations"],
            translations,
        )
        mocks["pause"].assert_called_once_with("Press Enter to continue...")
        for expected in (
            "Game",
            "Not detected",
            "Existing configuration",
            "Not evaluated",
            "Unresolved",
            "GSE notifications",
            "Not available",
            "Coverage",
            "Repair",
            "Not determined",
            "The Sentinel configuration was not found.",
            "Read-only • no Sentinel file or save was changed.",
        ):
            self.assertIn(expected, rendered)

    def test_notification_states_are_presented_without_changing_gse_semantics(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            game = make_game(Path(temp_directory) / "game")

            cases = (
                (make_status(should_notify=True), "Habilitadas"),
                (make_status(should_notify=False), "Desabilitadas"),
                (
                    make_status(emulator_ids=(SENTINEL_GOLDBERG_EMULATOR_ID,)),
                    "Não disponível",
                ),
            )

            for status, expected in cases:
                with self.subTest(expected=expected):
                    rendered = render_integration(
                        game,
                        status,
                        make_integration(status, (Path("/game/saves"),)),
                    )
                    self.assertIn(expected, rendered)

    def test_multiple_matches_and_derived_roots_use_python_owned_indexes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            game = make_game(Path(temp_directory) / "game")
            status = make_status()
            root = Path("/prefixes/Game/pfx/drive_c/GSE Saves")
            resolution = make_integration(
                status,
                (root,),
                covered_indexes=(0,),
                sentinel_root_paths=(root, root / "second"),
            )
            first_coverage = resolution.coverage.location_coverages[0]
            coverage = replace(
                resolution.coverage,
                location_coverages=(
                    replace(
                        first_coverage,
                        matching_roots=resolution.coverage.gse_save_roots,
                    ),
                ),
            )
            resolution = replace(resolution, coverage=coverage)

            rendered = render_integration(game, status, resolution)

        self.assertIn("Correspondência no Sentinel #1", rendered)
        self.assertIn("Correspondência no Sentinel #2", rendered)
        self.assertIn("Raiz GSE do Sentinel #1", rendered)
        self.assertIn("Raiz GSE do Sentinel #2", rendered)
        self.assertIn(str(root / "second"), rendered)

    def test_status_renders_rich_like_translations_and_values_literally(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory) / "[bold]literal-root[/bold]"
            original = make_game(root)
            game = replace(original, name="[bold]Literal Game[/bold]")
            status = make_status()
            save_root = Path("/saves/[yellow]literal[/yellow]")
            sentinel_root = Path("/sentinel/[magenta]root[/magenta]")

            rendered = render_integration(
                game,
                status,
                make_integration(
                    status,
                    (save_root,),
                    covered_indexes=(0,),
                    sentinel_root_paths=(sentinel_root,),
                ),
                executable=Path("/usr/bin/[cyan]sentinel[/cyan]"),
                translations=RichLikeTranslations(),
            )

        for expected in (
            "[red]Jogo[/red]",
            "[red]Integração GSE[/red]",
            "[red]Somente leitura[/red]",
            "[bold]Literal Game[/bold]",
            "/usr/bin/[cyan]sentinel[/cyan]",
            "/saves/[yellow]literal[/yellow]",
            "/sentinel/[magenta]root[/magenta]",
        ):
            self.assertIn(expected, rendered)

    def test_default_helper_call_preserves_legacy_repair_presentation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            status = make_status()
            root = Path("/prefixes/Game/pfx/drive_c/GSE Saves")
            resolution = make_integration(
                status,
                (root,),
                covered_indexes=(0,),
                sentinel_root_paths=(root,),
            )
            _, mocks = run_integration(
                make_game(Path(temp_directory) / "game"),
                status,
                resolution,
            )
        plan = mocks["repair_rows"].call_args.args[1]
        table = Table.grid(padding=(0, 2))
        table.add_column()
        table.add_column()
        _add_sentinel_repair_rows(table, plan)
        output = StringIO()
        Console(file=output, width=200, color_system=None).print(table)
        rendered = output.getvalue()

        self.assertIn("Fully watched", rendered)
        self.assertIn("Candidate prefixes", rendered)
        self.assertIn("Location de reparo", rendered)
        self.assertNotIn("Prefixos candidatos", rendered)

    def test_detector_config_and_resolver_errors_propagate_without_pause(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            game = make_game(Path(temp_directory) / "game")
            status = make_status()
            installation = SentinelInstallation(
                executable=Path("/usr/bin/sentinel"),
                config_path=status.path,
                data_directory=Path("/data/sentinel"),
                state_directory=Path("/state/sentinel"),
                log_path=Path("/state/sentinel/logs/sentinel.log"),
            )
            cases = (
                ("detect_sentinel", OSError("detect failure")),
                ("read_sentinel_config", ValueError("config failure")),
                ("resolve_game_sentinel_repair", RuntimeError("resolver failure")),
            )

            for target, error in cases:
                with (
                    self.subTest(target=target),
                    patch("goldberg_manager.cli.clear_screen"),
                    patch("goldberg_manager.cli.render_header"),
                    patch("goldberg_manager.cli.load_translations"),
                    patch(
                        "goldberg_manager.cli.detect_sentinel",
                        return_value=installation,
                        side_effect=error if target == "detect_sentinel" else None,
                    ),
                    patch(
                        "goldberg_manager.cli.read_sentinel_config",
                        return_value=status,
                        side_effect=error if target == "read_sentinel_config" else None,
                    ),
                    patch(
                        "goldberg_manager.cli.resolve_game_sentinel_repair",
                        side_effect=(
                            error if target == "resolve_game_sentinel_repair" else None
                        ),
                    ),
                    patch("goldberg_manager.cli.pause") as pause,
                    self.assertRaisesRegex(type(error), str(error)),
                ):
                    show_game_sentinel_integration_status(game)

                pause.assert_not_called()

    def test_invalid_config_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            game = make_game(Path(temp_directory) / "game")
            status = make_status(
                valid_json=False,
                schema_valid=False,
                prefixes=(),
                emulator_ids=(),
            )

            rendered = render_integration(
                game,
                status,
                make_integration(status, ()),
            )

            self.assertIn("JSON", rendered)
            self.assertIn("Inválido", rendered)
            self.assertIn(
                "A configuração do Sentinel contém JSON inválido.",
                rendered,
            )

    def test_missing_and_schema_invalid_configs_are_distinct(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            game = make_game(Path(temp_directory) / "game")
            missing_status = make_status(
                exists=False,
                valid_json=False,
                schema_valid=False,
                prefixes=(),
                emulator_ids=(),
            )
            schema_status = make_status(schema_valid=False)

            missing_rendered = render_integration(
                game,
                missing_status,
                make_integration(missing_status, ()),
            )
            schema_rendered = render_integration(
                game,
                schema_status,
                make_integration(schema_status, ()),
            )

            self.assertIn(
                "A configuração do Sentinel não foi encontrada.",
                missing_rendered,
            )
            self.assertIn("Não avaliado", missing_rendered)
            self.assertIn(
                "O schema da configuração do Sentinel é inválido.",
                schema_rendered,
            )
            self.assertIn("Válido", schema_rendered)

    def test_missing_sentinel_installation_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            game = make_game(Path(temp_directory) / "game")
            status = make_status()

            rendered = render_integration(
                game,
                status,
                make_integration(status, ()),
                installed=False,
            )

            self.assertIn("Instalação", rendered)
            self.assertIn("Não detectada", rendered)
            self.assertIn("O Sentinel não foi detectado neste sistema.", rendered)

    def test_gse_disabled_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            game = make_game(Path(temp_directory) / "game")
            status = make_status(
                emulator_ids=(SENTINEL_GOLDBERG_EMULATOR_ID,),
            )

            rendered = render_integration(
                game,
                status,
                make_integration(status, (Path("/game/saves"),)),
            )

            self.assertIn("GSE habilitado", rendered)
            self.assertIn(
                "O Sentinel não possui o emulador GSE habilitado.",
                rendered,
            )

    def test_watcher_without_prefixes_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            game = make_game(Path(temp_directory) / "game")
            status = make_status(prefixes=())

            rendered = render_integration(
                game,
                status,
                make_integration(status, (Path("/game/saves"),)),
            )

            self.assertIn("Watcher configurado", rendered)
            self.assertIn(
                "O watcher do Sentinel não possui prefixos configurados.",
                rendered,
            )

    def test_unresolved_save_is_not_reported_as_confirmed_unwatched(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            game = make_game(Path(temp_directory) / "game")
            status = make_status()

            rendered = render_integration(
                game,
                status,
                make_integration(status, ()),
            )

            self.assertIn("Save efetivo não coberto", rendered)
            self.assertIn("Não determinado", rendered)
            self.assertIn(
                "O save efetivo usado pelo GSE não pôde ser resolvido.",
                rendered,
            )
            self.assertNotIn("não é observado", rendered)
            self.assertIn(
                "Não determinado",
                rendered_row_value(rendered, "Reparo necessário"),
            )
            self.assertIn(
                "Não determinado",
                rendered_row_value(rendered, "Requer mudança no GSE"),
            )

    def test_ambiguous_cross_prefix_roots_are_listed_only_as_possible(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            game = make_game(root / "The Last of Us")
            status = make_status()
            possible_roots = tuple(
                root / prefix / user / "AppData" / "Roaming" / "GSE Saves"
                for prefix in (
                    "Resident Evil 2",
                    "Assassins Creed II",
                    "sideload",
                    "Sonic All Stars",
                )
                for user in ("davica", "steamuser")
            )
            save_resolution = GseSaveResolution(
                source="default",
                raw_value=None,
                locations=tuple(
                    GseSaveLocation(source="default", root=possible, app_id=APP_ID)
                    for possible in possible_roots
                ),
            )
            coverage = resolve_sentinel_gse_coverage(
                status,
                APP_ID,
                save_resolution,
            )
            resolution = GameSentinelIntegrationResolution(
                gse_resolution=GameGseResolution(
                    app_id=APP_ID,
                    app_id_confidence=100,
                    app_id_source="steam_appid.txt",
                    save_resolution=save_resolution,
                ),
                coverage=coverage,
            )

            rendered = render_integration(game, status, resolution)

            self.assertTrue(save_resolution.ambiguous)
            self.assertEqual(coverage.location_coverages, ())
            self.assertIn("Ambíguo", rendered)
            self.assertIn("Raiz efetiva", rendered)
            self.assertIn("Não determinado", rendered)
            self.assertEqual(rendered.count("Raiz efetiva"), 1)
            for index, possible_root in enumerate(possible_roots, start=1):
                self.assertIn(f"Raiz possível #{index}", rendered)
                self.assertIn(str(possible_root), rendered)
            self.assertIn("Há múltiplas raízes Wine possíveis", rendered)
            self.assertNotIn("save customizado fora do layout observado", rendered)
            repair_needed = rendered_row_value(rendered, "Reparo necessário")
            requires_gse_change = rendered_row_value(
                rendered,
                "Requer mudança no GSE",
            )
            self.assertIn("Não determinado", repair_needed)
            self.assertIn("ambíguo", repair_needed)
            self.assertNotEqual(repair_needed, "✓ Não")
            self.assertIn("Não determinado", requires_gse_change)
            self.assertNotEqual(requires_gse_change, "✓ Não")

    def test_multiple_runtime_roots_are_reported_as_ambiguous(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            game = make_game(root / "Invincible")
            status = make_status()
            possible_roots = (root / "first", root / "second")
            save_resolution = GseSaveResolution(
                source="default",
                raw_value=None,
                locations=tuple(
                    GseSaveLocation(source="default", root=possible, app_id=APP_ID)
                    for possible in possible_roots
                ),
            )
            for location in save_resolution.locations:
                location.app_directory.mkdir(parents=True)
            coverage = resolve_sentinel_gse_coverage(
                status,
                APP_ID,
                save_resolution,
            )
            resolution = GameSentinelIntegrationResolution(
                gse_resolution=GameGseResolution(
                    app_id=APP_ID,
                    app_id_confidence=100,
                    app_id_source="steam_appid.txt",
                    save_resolution=save_resolution,
                ),
                coverage=coverage,
            )

            rendered = render_integration(game, status, resolution)

            self.assertTrue(save_resolution.ambiguous)
            self.assertIn("Múltiplos runtimes para este AppID", rendered)
            self.assertIn("raiz efetiva permanece ambígua", rendered)

    def test_fully_watched_locations_are_reported(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            game = make_game(Path(temp_directory) / "game")
            status = make_status(should_notify=False)
            root = Path("/prefixes/Game/pfx/drive_c/GSE Saves")

            rendered = render_integration(
                game,
                status,
                make_integration(
                    status,
                    (root,),
                    covered_indexes=(0,),
                    sentinel_root_paths=(root,),
                ),
            )

            self.assertIn("Cobertura completa", rendered)
            self.assertIn("Coberta", rendered)
            self.assertIn("Notificações GSE", rendered)
            self.assertIn("Desabilitadas", rendered)
            self.assertIn(
                "Todas as localizações efetivas do GSE estão cobertas.",
                rendered,
            )
            self.assertEqual(
                rendered_row_value(rendered, "Reparo necessário"),
                "✓ Não",
            )
            self.assertEqual(
                rendered_row_value(rendered, "Cobertura completa"),
                "✓ Sim",
            )

    def test_partial_coverage_lists_each_location(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            game = make_game(Path(temp_directory) / "game")
            status = make_status()
            watched = Path("/prefixes/Game/pfx/drive_c/GSE Saves")
            custom = Path("/game/saves")

            rendered = render_integration(
                game,
                status,
                make_integration(
                    status,
                    (watched, custom),
                    covered_indexes=(0,),
                    sentinel_root_paths=(watched,),
                ),
            )

            self.assertIn("Cobertura parcial", rendered)
            self.assertIn("A cobertura do Sentinel é parcial.", rendered)
            self.assertIn("Raiz efetiva #1", rendered)
            self.assertIn("Raiz efetiva #2", rendered)
            self.assertIn(str(watched), rendered)
            self.assertIn(str(custom), rendered)
            self.assertIn("Não coberta", rendered)

    def test_unwatched_save_reports_safe_diagnostic(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            game = make_game(Path(temp_directory) / "game")
            status = make_status()

            rendered = render_integration(
                game,
                status,
                make_integration(
                    status,
                    (Path("/game/saves"),),
                    sentinel_root_paths=(Path("/prefixes/GSE Saves"),),
                ),
            )

            self.assertIn("Save efetivo não coberto", rendered)
            self.assertIn(
                "O save efetivamente usado pelo GSE não é observado.",
                rendered,
            )
            self.assertIn(
                "Será necessária uma correção de cobertura do Sentinel.",
                rendered,
            )
            self.assertIn("Reparo necessário", rendered)
            self.assertIn("Corrigível apenas no Sentinel", rendered)
            self.assertIn("Requer mudança no GSE", rendered)
            self.assertIn("save customizado fora do layout observado", rendered)
            self.assertIn("Nenhum seguro", rendered)
            self.assertNotIn("adicione", rendered.casefold())
            self.assertEqual(
                rendered_row_value(rendered, "Reparo necessário"),
                "⚠ Sim",
            )
            self.assertEqual(
                rendered_row_value(rendered, "Corrigível apenas no Sentinel"),
                "✗ Não",
            )
            self.assertEqual(
                rendered_row_value(rendered, "Requer mudança no GSE"),
                "⚠ Sim",
            )

    def test_recognized_but_unwatched_is_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            game = make_game(Path(temp_directory) / "game")
            status = make_status()

            rendered = render_integration(
                game,
                status,
                make_integration(
                    status,
                    (Path("/game/saves"),),
                    sentinel_root_paths=(Path("/prefixes/GSE Saves"),),
                    runtime_emulator_ids=(SENTINEL_GSE_EMULATOR_ID,),
                ),
            )

            self.assertIn(
                "O Sentinel reconhece este AppID em outro runtime, mas não está "
                "observando o save atualmente usado pelo GSE.",
                rendered,
            )

    def test_legacy_only_recognition_is_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            game = make_game(Path(temp_directory) / "game")
            status = make_status(
                emulator_ids=(
                    SENTINEL_GSE_EMULATOR_ID,
                    SENTINEL_GOLDBERG_EMULATOR_ID,
                ),
            )

            rendered = render_integration(
                game,
                status,
                make_integration(
                    status,
                    (Path("/game/saves"),),
                    sentinel_root_paths=(Path("/prefixes/GSE Saves"),),
                    runtime_emulator_ids=(SENTINEL_GOLDBERG_EMULATOR_ID,),
                ),
            )

            self.assertIn("somente Goldberg legacy", rendered)
            self.assertIn(
                "O AppID foi reconhecido somente no runtime Goldberg legacy, "
                "não no runtime GSE atual.",
                rendered,
            )


if __name__ == "__main__":
    unittest.main()
