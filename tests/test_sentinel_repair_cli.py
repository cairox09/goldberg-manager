from __future__ import annotations

import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from rich.console import Console

from goldberg_manager.cli import (
    repair_game_sentinel_integration,
    resolve_game_sentinel_repair,
    show_sentinel_config_write_result,
)
from goldberg_manager.gse_saves import GseSaveLocation, GseSaveResolution
from goldberg_manager.scanner import Game
from goldberg_manager.sentinel import (
    SENTINEL_GOLDBERG_EMULATOR_ID,
    SENTINEL_GSE_EMULATOR_ID,
    SentinelConfigStatus,
    SentinelEmulator,
    SentinelSaveRoot,
)
from goldberg_manager.sentinel_config_writer import (
    SentinelConfigWriteReason,
    SentinelConfigWriteResult,
    SentinelConfigWriteStatus,
)
from goldberg_manager.sentinel_integration import (
    SentinelGseCoverage,
    SentinelGseLocationCoverage,
)
from goldberg_manager.sentinel_repair import plan_sentinel_gse_repair

APP_ID = 212480
CONFIG_PATH = Path("/config/sentinel/config.json")


def make_game(root: Path) -> Game:
    return Game(
        name="Sonic & All-Stars Racing Transformed",
        root_directory=root,
        executable=root / "Game.exe",
        steam_api=root / "steam_api64.dll",
        steam_api_relative_path=Path("steam_api64.dll"),
        architecture="64-bit",
        source_directory=root,
    )


def make_status(
    *,
    exists: bool = True,
    valid_json: bool = True,
    schema_valid: bool = True,
    gse_enabled: bool = True,
) -> SentinelConfigStatus:
    emulator_id = (
        SENTINEL_GSE_EMULATOR_ID if gse_enabled else SENTINEL_GOLDBERG_EMULATOR_ID
    )
    return SentinelConfigStatus(
        path=CONFIG_PATH,
        exists=exists,
        valid_json=valid_json,
        schema_valid=schema_valid,
        prefix_paths=(),
        emulators=(SentinelEmulator(id=emulator_id, should_notify=True),),
    )


def standard_root(base: Path = Path("/games")) -> Path:
    return (
        base
        / "Game"
        / "pfx"
        / "drive_c"
        / "users"
        / "steamuser"
        / "AppData"
        / "Roaming"
        / "GSE Saves"
    )


def make_plan(
    roots: tuple[Path, ...],
    *,
    status: SentinelConfigStatus | None = None,
    covered_indexes: tuple[int, ...] = (),
):
    sentinel_status = make_status() if status is None else status
    locations = tuple(
        GseSaveLocation(source="test", root=root, app_id=APP_ID) for root in roots
    )
    save_resolution = GseSaveResolution(
        source="test",
        raw_value=None,
        locations=locations,
    )
    matching_roots = {
        index: SentinelSaveRoot(
            emulator_id=SENTINEL_GSE_EMULATOR_ID,
            prefix_path=Path("/prefixes"),
            drive_c=location.root,
            path=location.root,
        )
        for index, location in enumerate(locations)
        if index in covered_indexes
    }
    coverage = SentinelGseCoverage(
        app_id=APP_ID,
        sentinel_status=sentinel_status,
        save_resolution=save_resolution,
        gse_save_roots=tuple(matching_roots.values()),
        location_coverages=tuple(
            SentinelGseLocationCoverage(
                location=location,
                matching_roots=(matching_roots[index],)
                if index in matching_roots
                else (),
            )
            for index, location in enumerate(locations)
        ),
        runtime_matches=(),
        gse_runtime_matches=(),
        legacy_runtime_matches=(),
    )
    return plan_sentinel_gse_repair(coverage)


def make_result(
    status: SentinelConfigWriteStatus,
    reason: SentinelConfigWriteReason,
    **kwargs,
) -> SentinelConfigWriteResult:
    return SentinelConfigWriteResult(
        status=status,
        reason=reason,
        config_path=CONFIG_PATH,
        **kwargs,
    )


def render_result(result: SentinelConfigWriteResult) -> str:
    output = StringIO()
    test_console = Console(file=output, width=200, color_system=None)

    with patch("goldberg_manager.cli.console", test_console):
        show_sentinel_config_write_result(result)

    return output.getvalue()


def run_repair(
    game: Game,
    plan,
    *,
    confirmed: bool | None = None,
    result: SentinelConfigWriteResult | None = None,
    post_plan=None,
    post_error: Exception | None = None,
):
    output = StringIO()
    test_console = Console(file=output, width=200, color_system=None)
    resolver_results: list[object] = [plan]

    if result is not None and result.status is SentinelConfigWriteStatus.APPLIED:
        resolver_results.append(post_error if post_error is not None else post_plan)

    with (
        patch(
            "goldberg_manager.cli.resolve_game_sentinel_repair",
            side_effect=resolver_results,
        ) as resolver,
        patch("goldberg_manager.cli.apply_sentinel_config_repair") as writer,
        patch("goldberg_manager.cli.questionary.confirm") as confirm,
        patch("goldberg_manager.cli.console", test_console),
        patch("goldberg_manager.cli.clear_screen"),
        patch("goldberg_manager.cli.render_header"),
        patch("goldberg_manager.cli.pause"),
    ):
        confirm.return_value.ask.return_value = confirmed

        if result is not None:
            writer.return_value = result

        repair_game_sentinel_integration(game)

    return output.getvalue(), resolver, writer, confirm


class SentinelRepairCliTests(unittest.TestCase):
    def test_resolver_reuses_game_integration_and_planner(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            game = make_game(Path(temp_directory))
            plan = make_plan((standard_root(),))
            integration = unittest.mock.Mock(coverage=plan.coverage)

            with (
                patch(
                    "goldberg_manager.cli.resolve_game_sentinel_integration",
                    return_value=integration,
                ) as integration_resolver,
                patch(
                    "goldberg_manager.cli.plan_sentinel_gse_repair",
                    return_value=plan,
                ) as planner,
            ):
                resolved = resolve_game_sentinel_repair(game)

            self.assertIs(resolved, plan)
            integration_resolver.assert_called_once_with(
                game,
                sentinel_status=None,
            )
            planner.assert_called_once_with(plan.coverage)

    def test_no_repair_does_not_confirm_or_call_writer(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            game = make_game(Path(temp_directory))
            plan = make_plan((standard_root(),), covered_indexes=(0,))

            rendered, _, writer, confirm = run_repair(game, plan)

            self.assertIn("Nenhuma correção é necessária", rendered)
            confirm.assert_not_called()
            writer.assert_not_called()

    def test_invalid_config_does_not_confirm_or_call_writer(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            game = make_game(Path(temp_directory))
            status = make_status(valid_json=False, schema_valid=False)
            plan = make_plan((standard_root(),), status=status)

            rendered, _, writer, confirm = run_repair(game, plan)

            self.assertIn("JSON inválido", rendered)
            confirm.assert_not_called()
            writer.assert_not_called()

    def test_gse_disabled_does_not_confirm_or_call_writer(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            game = make_game(Path(temp_directory))
            plan = make_plan(
                (standard_root(),),
                status=make_status(gse_enabled=False),
            )

            rendered, _, writer, confirm = run_repair(game, plan)

            self.assertIn("não o habilita automaticamente", rendered)
            confirm.assert_not_called()
            writer.assert_not_called()

    def test_custom_only_does_not_confirm_or_call_writer(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            game = make_game(Path(temp_directory))
            plan = make_plan((Path("/games/custom/saves"),))

            rendered, _, writer, confirm = run_repair(game, plan)

            self.assertIn("Não existe candidate prefix seguro", rendered)
            self.assertIn("mudança na configuração de saves do GSE", rendered)
            confirm.assert_not_called()
            writer.assert_not_called()

    def test_sonic_custom_root_is_explained_without_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            game = make_game(Path(temp_directory))
            sonic_root = Path(
                "/games/Sonic & All-Stars Racing Transformed Collection/saves"
            )

            rendered, _, writer, confirm = run_repair(
                game,
                make_plan((sonic_root,)),
            )

            self.assertIn("Reparo necessário", rendered)
            self.assertIn("save customizado fora do layout observado", rendered)
            self.assertIn("Requer mudança no GSE", rendered)
            self.assertIn("Nenhum seguro", rendered)
            confirm.assert_not_called()
            writer.assert_not_called()

    def test_full_repair_cancel_uses_default_false_without_writing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            game = make_game(Path(temp_directory))
            plan = make_plan((standard_root(),))

            rendered, _, writer, confirm = run_repair(
                game,
                plan,
                confirmed=False,
            )

            self.assertIn("Nenhum prefix existente será removido", rendered)
            self.assertIn("backup será criado automaticamente", rendered)
            self.assertFalse(confirm.call_args.kwargs["default"])
            self.assertNotIn("parcial", confirm.call_args.args[0].casefold())
            self.assertIn("cancelada", rendered)
            writer.assert_not_called()

    def test_full_repair_confirmed_calls_writer_without_partial(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            game = make_game(Path(temp_directory))
            plan = make_plan((standard_root(),))
            result = make_result(
                SentinelConfigWriteStatus.NO_CHANGE,
                SentinelConfigWriteReason.ALREADY_CURRENT,
                message="Já atualizado.",
            )

            _, _, writer, _ = run_repair(
                game,
                plan,
                confirmed=True,
                result=result,
            )

            writer.assert_called_once_with(plan, allow_partial=False)

    def test_partial_repair_cancel_is_explicit_and_defaults_false(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            game = make_game(Path(temp_directory))
            plan = make_plan((standard_root(), Path("/games/custom/saves")))

            rendered, _, writer, confirm = run_repair(
                game,
                plan,
                confirmed=False,
            )

            self.assertIn("Esta correção é PARCIAL", rendered)
            self.assertIn("continuarão sem cobertura", rendered)
            self.assertIn("mudança no GSE", rendered)
            self.assertIn("parcial", confirm.call_args.args[0].casefold())
            self.assertFalse(confirm.call_args.kwargs["default"])
            writer.assert_not_called()

    def test_partial_repair_confirmed_calls_writer_with_partial(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            game = make_game(Path(temp_directory))
            plan = make_plan((standard_root(), Path("/games/custom/saves")))
            result = make_result(
                SentinelConfigWriteStatus.REJECTED,
                SentinelConfigWriteReason.NO_SAFE_PREFIXES,
                partial=True,
                message="Revalidado.",
            )

            _, _, writer, _ = run_repair(
                game,
                plan,
                confirmed=True,
                result=result,
            )

            writer.assert_called_once_with(plan, allow_partial=True)

    def test_applied_shows_added_prefixes_and_backup(self) -> None:
        prefix = Path("/games/Game/pfx")
        backup = Path("/config/sentinel/config.json.backup")
        rendered = render_result(
            make_result(
                SentinelConfigWriteStatus.APPLIED,
                SentinelConfigWriteReason.APPLIED,
                added_prefixes=(prefix,),
                backup_path=backup,
                message="Aplicado.",
            )
        )

        self.assertIn("APPLIED", rendered)
        self.assertIn(str(prefix), rendered)
        self.assertIn(str(backup), rendered)

    def test_no_change_is_presented(self) -> None:
        rendered = render_result(
            make_result(
                SentinelConfigWriteStatus.NO_CHANGE,
                SentinelConfigWriteReason.ALREADY_CURRENT,
            )
        )

        self.assertIn("NO_CHANGE", rendered)
        self.assertIn("ALREADY_CURRENT", rendered)

    def test_rejected_is_presented(self) -> None:
        rendered = render_result(
            make_result(
                SentinelConfigWriteStatus.REJECTED,
                SentinelConfigWriteReason.CONFIG_INVALID,
            )
        )

        self.assertIn("REJECTED", rendered)
        self.assertIn("CONFIG_INVALID", rendered)

    def test_conflict_is_presented_clearly(self) -> None:
        rendered = render_result(
            make_result(
                SentinelConfigWriteStatus.CONFLICT,
                SentinelConfigWriteReason.CONCURRENT_MODIFICATION,
            )
        )

        self.assertIn("CONFLICT", rendered)
        self.assertIn("configuração mudou", rendered)

    def test_failed_is_presented(self) -> None:
        rendered = render_result(
            make_result(
                SentinelConfigWriteStatus.FAILED,
                SentinelConfigWriteReason.WRITE_FAILED,
                message="Falha de escrita.",
            )
        )

        self.assertIn("FAILED", rendered)
        self.assertIn("Falha de escrita", rendered)

    def test_rolled_back_reports_original_restored(self) -> None:
        rendered = render_result(
            make_result(
                SentinelConfigWriteStatus.ROLLED_BACK,
                SentinelConfigWriteReason.POST_VALIDATION_FAILED,
                rolled_back=True,
            )
        )

        self.assertIn("ROLLED_BACK", rendered)
        self.assertIn("configuração original foi restaurada", rendered)

    def test_rollback_failure_is_not_presented_as_success(self) -> None:
        rendered = render_result(
            make_result(
                SentinelConfigWriteStatus.FAILED,
                SentinelConfigWriteReason.ROLLBACK_FAILED,
                rolled_back=False,
            )
        )

        self.assertIn("rollback FALHOU", rendered)
        self.assertNotIn("foi restaurada pelo rollback", rendered)

    def test_applied_recalculates_and_shows_full_post_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            game = make_game(Path(temp_directory))
            plan = make_plan((standard_root(),))
            post_plan = make_plan((standard_root(),), covered_indexes=(0,))
            result = make_result(
                SentinelConfigWriteStatus.APPLIED,
                SentinelConfigWriteReason.APPLIED,
                added_prefixes=plan.candidate_prefixes,
            )

            rendered, resolver, _, _ = run_repair(
                game,
                plan,
                confirmed=True,
                result=result,
                post_plan=post_plan,
            )

            self.assertEqual(resolver.call_count, 2)
            self.assertIn("Estado pós-operação", rendered)
            self.assertIn("Fully watched", rendered)
            self.assertIn("Reparo necessário", rendered)

    def test_partial_post_state_keeps_unsupported_location_visible(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            game = make_game(Path(temp_directory))
            roots = (standard_root(), Path("/games/custom/saves"))
            plan = make_plan(roots)
            post_plan = make_plan(roots, covered_indexes=(0,))
            result = make_result(
                SentinelConfigWriteStatus.APPLIED,
                SentinelConfigWriteReason.APPLIED,
                added_prefixes=plan.candidate_prefixes,
                partial=True,
            )

            rendered, resolver, _, _ = run_repair(
                game,
                plan,
                confirmed=True,
                result=result,
                post_plan=post_plan,
            )

            self.assertEqual(resolver.call_count, 2)
            self.assertIn("Estado pós-operação", rendered)
            self.assertIn("save customizado fora do layout observado", rendered)
            self.assertIn("Reparo necessário", rendered)

    def test_post_apply_resolution_failure_does_not_crash(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            game = make_game(Path(temp_directory))
            plan = make_plan((standard_root(),))
            result = make_result(
                SentinelConfigWriteStatus.APPLIED,
                SentinelConfigWriteReason.APPLIED,
            )

            rendered, resolver, _, _ = run_repair(
                game,
                plan,
                confirmed=True,
                result=result,
                post_error=RuntimeError("consulta indisponível"),
            )

            self.assertEqual(resolver.call_count, 2)
            self.assertIn("não foi possível reconsultar", rendered)
            self.assertIn("consulta indisponível", rendered)


if __name__ == "__main__":
    unittest.main()
