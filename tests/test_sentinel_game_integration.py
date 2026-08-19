from __future__ import annotations

import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from rich.console import Console

from goldberg_manager.cli import (
    GameGseResolution,
    GameSentinelIntegrationResolution,
    resolve_game_sentinel_integration,
    show_game_sentinel_integration_status,
)
from goldberg_manager.gse_saves import GseSaveLocation, GseSaveResolution
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
)

APP_ID = 212480


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
        save_resolution=save_resolution if app_id is not None else None,
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


def render_integration(
    game: Game,
    status: SentinelConfigStatus,
    resolution: GameSentinelIntegrationResolution,
    *,
    installed: bool = True,
) -> str:
    installation = SentinelInstallation(
        executable=Path("/usr/bin/sentinel") if installed else None,
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

    with (
        patch("goldberg_manager.cli.detect_sentinel", return_value=installation),
        patch("goldberg_manager.cli.read_sentinel_config", return_value=status),
        patch(
            "goldberg_manager.cli.resolve_game_sentinel_integration",
            return_value=resolution,
        ) as resolver,
        patch("goldberg_manager.cli.console", test_console),
        patch("goldberg_manager.cli.clear_screen"),
        patch("goldberg_manager.cli.render_header"),
        patch("goldberg_manager.cli.pause"),
    ):
        show_game_sentinel_integration_status(game)

    resolver.assert_called_once_with(game, sentinel_status=status)
    return output.getvalue()


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
                "O Sentinel não possui o emulator GSE habilitado.",
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
                "O watcher do Sentinel não possui prefixes configurados.",
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

            self.assertIn("Unwatched", rendered)
            self.assertIn("Não determinado", rendered)
            self.assertIn(
                "O save efetivo usado pelo GSE não pôde ser resolvido.",
                rendered,
            )
            self.assertNotIn("não é observado", rendered)

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

            self.assertIn("Fully watched", rendered)
            self.assertIn("Coberta", rendered)
            self.assertIn("Notificações GSE", rendered)
            self.assertIn("Desabilitadas", rendered)
            self.assertIn(
                "Todas as locations efetivas do GSE estão cobertas.",
                rendered,
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

            self.assertIn("Partially watched", rendered)
            self.assertIn("A cobertura do Sentinel é parcial.", rendered)
            self.assertIn("Effective root #1", rendered)
            self.assertIn("Effective root #2", rendered)
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

            self.assertIn("Unwatched", rendered)
            self.assertIn(
                "O save efetivamente usado pelo GSE não é observado.",
                rendered,
            )
            self.assertIn(
                "Será necessária uma correção de cobertura do Sentinel.",
                rendered,
            )
            self.assertNotIn("adicione", rendered.casefold())

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
