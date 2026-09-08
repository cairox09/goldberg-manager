from __future__ import annotations

import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from rich.console import Console

from goldberg_manager.application.game_sentinel_repair import (
    GameSentinelRepairOutcome,
)
from goldberg_manager.application.game_sentinel_repair import (
    resolve_game_sentinel_repair as resolve_game_sentinel_repair_application,
)
from goldberg_manager.cli import (
    repair_game_sentinel_integration,
    resolve_game_sentinel_repair,
    show_sentinel_config_write_result,
)
from goldberg_manager.gse_saves import GseSaveLocation, GseSaveResolution
from goldberg_manager.presentation.i18n import load_translations
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
    resolve_sentinel_gse_coverage,
)
from goldberg_manager.sentinel_repair import plan_sentinel_gse_repair

APP_ID = 212480
CONFIG_PATH = Path("/config/sentinel/config.json")


class MappingTranslations:
    def __init__(self, translations: dict[str, str] | None = None) -> None:
        self.translations = translations or {}

    def gettext(self, message: str) -> str:
        return self.translations.get(message, message)


def make_game(
    root: Path,
    *,
    name: str = "Sonic & All-Stars Racing Transformed",
) -> Game:
    return Game(
        name=name,
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
    path: Path = CONFIG_PATH,
) -> SentinelConfigStatus:
    emulator_id = (
        SENTINEL_GSE_EMULATOR_ID if gse_enabled else SENTINEL_GOLDBERG_EMULATOR_ID
    )
    return SentinelConfigStatus(
        path=path,
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
        save_resolution=save_resolution if len(roots) <= 1 else None,
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
    config_path = kwargs.pop("config_path", CONFIG_PATH)
    return SentinelConfigWriteResult(
        status=status,
        reason=reason,
        config_path=config_path,
        **kwargs,
    )


def render_result(
    result: SentinelConfigWriteResult,
    *,
    translations=None,
) -> str:
    output = StringIO()
    test_console = Console(file=output, width=200, color_system=None)

    with patch("goldberg_manager.cli.console", test_console):
        if translations is None:
            show_sentinel_config_write_result(result)
        else:
            show_sentinel_config_write_result(result, translations=translations)

    return output.getvalue()


def rendered_row_value(rendered: str, label: str) -> str:
    line = next(line for line in rendered.splitlines() if label in line)
    return line.split(label, 1)[1].strip(" │")


def run_repair(
    game: Game,
    plan,
    *,
    confirmed: bool | None = None,
    result: SentinelConfigWriteResult | None = None,
    post_plan=None,
    post_error: Exception | None = None,
    translations=None,
):
    output = StringIO()
    test_console = Console(file=output, width=200, color_system=None)

    with (
        patch(
            "goldberg_manager.cli.resolve_game_sentinel_repair",
            return_value=plan,
        ) as resolver,
        patch("goldberg_manager.cli.apply_game_sentinel_repair") as writer,
        patch("goldberg_manager.cli.questionary.confirm") as confirm,
        patch("goldberg_manager.cli.console", test_console),
        patch("goldberg_manager.cli.clear_screen"),
        patch("goldberg_manager.cli.render_header"),
        patch("goldberg_manager.cli.pause"),
    ):
        confirm.return_value.ask.return_value = confirmed

        if result is not None:
            writer.return_value = GameSentinelRepairOutcome(
                write_result=result,
                post_plan=post_plan,
                post_resolution_error=post_error,
            )

        if translations is None:
            repair_game_sentinel_integration(game)
        else:
            repair_game_sentinel_integration(game, translations=translations)

    return output.getvalue(), resolver, writer, confirm


class SentinelRepairCliTests(unittest.TestCase):
    def test_resolver_remains_available_from_cli(self) -> None:
        self.assertIs(
            resolve_game_sentinel_repair,
            resolve_game_sentinel_repair_application,
        )

    def test_default_invocation_loads_translations_exactly_once(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            translations = MappingTranslations()
            game = make_game(Path(temp_directory))
            plan = make_plan((standard_root(),), covered_indexes=(0,))

            with patch(
                "goldberg_manager.cli.load_translations",
                return_value=translations,
            ) as loader:
                run_repair(game, plan)

        loader.assert_called_once_with()

    def test_explicit_translations_bypass_loader(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            translations = MappingTranslations()
            game = make_game(Path(temp_directory))
            plan = make_plan((standard_root(),), covered_indexes=(0,))

            with patch("goldberg_manager.cli.load_translations") as loader:
                run_repair(game, plan, translations=translations)

        loader.assert_not_called()

    def test_english_plan_uses_translated_repair_rows(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            game = make_game(Path(temp_directory))
            plan = make_plan((standard_root(),), covered_indexes=(0,))

            rendered, _, writer, confirm = run_repair(
                game,
                plan,
                translations=load_translations("en"),
            )

        self.assertIn("Sentinel • Repair plan", rendered)
        self.assertIn("Game", rendered)
        self.assertIn("Configuration", rendered)
        self.assertIn("Repair needed", rendered)
        self.assertIn("Full coverage", rendered)
        self.assertIn("No repair is needed", rendered)
        self.assertNotIn("Fully watched", rendered)
        confirm.assert_not_called()
        writer.assert_not_called()

    def test_english_early_gates_do_not_reach_consent_or_writer(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            game = make_game(root)
            ambiguous_resolution = GseSaveResolution(
                source="default",
                raw_value=None,
                locations=tuple(
                    GseSaveLocation(source="default", root=possible, app_id=APP_ID)
                    for possible in (
                        root / "Game One" / "GSE Saves",
                        root / "Game Two" / "GSE Saves",
                    )
                ),
            )
            ambiguous_plan = plan_sentinel_gse_repair(
                resolve_sentinel_gse_coverage(
                    make_status(),
                    APP_ID,
                    ambiguous_resolution,
                )
            )
            cases = (
                (
                    make_plan(
                        (standard_root(),),
                        status=make_status(valid_json=False, schema_valid=False),
                    ),
                    "contains invalid JSON",
                ),
                (
                    make_plan(
                        (standard_root(),),
                        status=make_status(gse_enabled=False),
                    ),
                    "does not enable it automatically",
                ),
                (
                    ambiguous_plan,
                    "could not be determined safely",
                ),
                (
                    make_plan(()),
                    "could not be resolved safely",
                ),
                (
                    make_plan((Path("/games/custom/saves"),)),
                    "There is no safe candidate prefix",
                ),
            )

            for plan, expected in cases:
                with self.subTest(expected=expected):
                    rendered, _, writer, confirm = run_repair(
                        game,
                        plan,
                        translations=load_translations("en"),
                    )
                    self.assertIn(expected, rendered)
                    confirm.assert_not_called()
                    writer.assert_not_called()

    def test_no_repair_does_not_confirm_or_call_writer(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            game = make_game(Path(temp_directory))
            plan = make_plan((standard_root(),), covered_indexes=(0,))

            rendered, _, writer, confirm = run_repair(game, plan)

            self.assertIn("Nenhuma correção é necessária", rendered)
            self.assertEqual(
                rendered_row_value(rendered, "Reparo necessário"),
                "✓ Não",
            )
            self.assertEqual(
                rendered_row_value(rendered, "Cobertura completa"),
                "✓ Sim",
            )
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
            self.assertEqual(
                rendered_row_value(rendered, "Reparo necessário"),
                "⚠ Sim",
            )
            self.assertEqual(
                rendered_row_value(rendered, "Requer mudança no GSE"),
                "⚠ Sim",
            )
            confirm.assert_not_called()
            writer.assert_not_called()

    def test_ambiguous_resolution_does_not_confirm_or_call_writer(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            game = make_game(root / "game")
            save_resolution = GseSaveResolution(
                source="default",
                raw_value=None,
                locations=tuple(
                    GseSaveLocation(source="default", root=possible, app_id=APP_ID)
                    for possible in (
                        root / "Resident Evil 2" / "GSE Saves",
                        root / "Assassins Creed II" / "GSE Saves",
                    )
                ),
            )
            coverage = resolve_sentinel_gse_coverage(
                make_status(),
                APP_ID,
                save_resolution,
            )
            plan = plan_sentinel_gse_repair(coverage)

            rendered, _, writer, confirm = run_repair(game, plan)

            self.assertTrue(save_resolution.ambiguous)
            self.assertFalse(plan.needs_repair)
            self.assertFalse(plan.requires_gse_change)
            self.assertEqual(plan.candidate_prefixes, ())
            self.assertIn(
                "save GSE efetivo não pôde ser determinado com segurança",
                rendered,
            )
            self.assertIn("Nenhuma correção automática", rendered)
            self.assertIn(
                "Não determinado",
                rendered_row_value(rendered, "Reparo necessário"),
            )
            self.assertIn(
                "Não determinado",
                rendered_row_value(rendered, "Requer mudança no GSE"),
            )
            confirm.assert_not_called()
            writer.assert_not_called()

    def test_unresolved_without_locations_does_not_claim_no_repair(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            game = make_game(Path(temp_directory))
            plan = make_plan(())

            rendered, _, writer, confirm = run_repair(game, plan)

            save_resolution = plan.coverage.save_resolution
            assert save_resolution is not None
            self.assertFalse(save_resolution.ambiguous)
            self.assertFalse(plan.coverage.effective_save_resolved)
            self.assertIn(
                "save GSE efetivo não pôde ser resolvido com segurança",
                rendered,
            )
            self.assertIn("Nenhuma correção automática será proposta", rendered)
            self.assertNotIn("Nenhuma correção é necessária", rendered)
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
            self.assertEqual(
                rendered_row_value(rendered, "Reparo necessário"),
                "⚠ Sim",
            )
            self.assertEqual(
                rendered_row_value(rendered, "Corrigível apenas no Sentinel"),
                "✓ Sim",
            )
            self.assertFalse(confirm.call_args.kwargs["default"])
            self.assertNotIn("parcial", confirm.call_args.args[0].casefold())
            self.assertIn("cancelada", rendered)
            writer.assert_not_called()

    def test_english_full_repair_confirmation_defaults_false(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            game = make_game(Path(temp_directory))
            plan = make_plan((standard_root(),))

            rendered, _, writer, confirm = run_repair(
                game,
                plan,
                confirmed=False,
                translations=load_translations("en"),
            )

        self.assertEqual(
            confirm.call_args.args[0],
            "Apply this Sentinel repair?",
        )
        self.assertFalse(confirm.call_args.kwargs["default"])
        self.assertIn("Repair canceled. No changes were made.", rendered)
        writer.assert_not_called()

    def test_none_confirmation_cancels_without_writing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            game = make_game(Path(temp_directory))
            plan = make_plan((standard_root(),))

            rendered, _, writer, confirm = run_repair(
                game,
                plan,
                confirmed=None,
                translations=load_translations("en"),
            )

        self.assertFalse(confirm.call_args.kwargs["default"])
        self.assertIn("Repair canceled", rendered)
        writer.assert_not_called()

    def test_full_repair_confirmed_delegates_exact_plan_without_partial(self) -> None:
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

            writer.assert_called_once_with(
                game,
                plan,
                allow_partial=False,
            )
            self.assertIs(writer.call_args.args[1], plan)

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

    def test_english_partial_repair_confirmation_defaults_false(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            game = make_game(Path(temp_directory))
            plan = make_plan((standard_root(), Path("/games/custom/saves")))

            rendered, _, writer, confirm = run_repair(
                game,
                plan,
                confirmed=False,
                translations=load_translations("en"),
            )

        self.assertIn("This repair is PARTIAL", rendered)
        self.assertEqual(
            confirm.call_args.args[0],
            "Apply this partial Sentinel repair?",
        )
        self.assertFalse(confirm.call_args.kwargs["default"])
        writer.assert_not_called()

    def test_partial_repair_confirmed_delegates_exact_plan_with_partial(self) -> None:
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

            writer.assert_called_once_with(
                game,
                plan,
                allow_partial=True,
            )
            self.assertIs(writer.call_args.args[1], plan)

    def test_exact_translation_object_reaches_all_repair_renderers(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            translations = MappingTranslations()
            game = make_game(Path(temp_directory))
            plan = make_plan((standard_root(),))
            post_plan = make_plan((standard_root(),), covered_indexes=(0,))
            result = make_result(
                SentinelConfigWriteStatus.APPLIED,
                SentinelConfigWriteReason.APPLIED,
            )

            with (
                patch("goldberg_manager.cli._show_sentinel_repair_plan") as plans,
                patch(
                    "goldberg_manager.cli.show_sentinel_config_write_result"
                ) as write_result,
            ):
                run_repair(
                    game,
                    plan,
                    confirmed=True,
                    result=result,
                    post_plan=post_plan,
                    translations=translations,
                )

        self.assertEqual(plans.call_count, 2)
        self.assertTrue(
            all(
                call.kwargs["translations"] is translations
                for call in plans.call_args_list
            )
        )
        self.assertIs(write_result.call_args.kwargs["translations"], translations)

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

    def test_english_result_keeps_technical_statuses_and_reasons_literal(self) -> None:
        translations = load_translations("en")
        cases = (
            (
                SentinelConfigWriteStatus.APPLIED,
                SentinelConfigWriteReason.APPLIED,
            ),
            (
                SentinelConfigWriteStatus.NO_CHANGE,
                SentinelConfigWriteReason.ALREADY_CURRENT,
            ),
            (
                SentinelConfigWriteStatus.REJECTED,
                SentinelConfigWriteReason.CONFIG_INVALID,
            ),
            (
                SentinelConfigWriteStatus.FAILED,
                SentinelConfigWriteReason.WRITE_FAILED,
            ),
        )

        for status, reason in cases:
            with self.subTest(status=status):
                rendered = render_result(
                    make_result(status, reason),
                    translations=translations,
                )
                self.assertIn("Sentinel repair result", rendered)
                self.assertIn(status.name, rendered)
                self.assertIn(reason.name, rendered)
                self.assertIn("Reason", rendered)
                self.assertIn("Rollback performed", rendered)

    def test_stable_writer_message_is_translated_but_unknown_message_is_literal(
        self,
    ) -> None:
        translations = load_translations("en")
        stable = render_result(
            make_result(
                SentinelConfigWriteStatus.APPLIED,
                SentinelConfigWriteReason.APPLIED,
                message="Prefixes do Sentinel atualizados com segurança.",
            ),
            translations=translations,
        )
        unknown = render_result(
            make_result(
                SentinelConfigWriteStatus.FAILED,
                SentinelConfigWriteReason.WRITE_FAILED,
                message="detalhe técnico arbitrário",
            ),
            translations=MappingTranslations(
                {"detalhe técnico arbitrário": "must not be translated"}
            ),
        )

        self.assertIn("Sentinel prefixes were updated safely", stable)
        self.assertIn("detalhe técnico arbitrário", unknown)
        self.assertNotIn("must not be translated", unknown)

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

    def test_conflict_is_presented_in_english(self) -> None:
        rendered = render_result(
            make_result(
                SentinelConfigWriteStatus.CONFLICT,
                SentinelConfigWriteReason.CONCURRENT_MODIFICATION,
            ),
            translations=load_translations("en"),
        )

        self.assertIn("CONFLICT", rendered)
        self.assertIn("configuration changed during the operation", rendered)

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

    def test_rolled_back_reports_original_restored_in_english(self) -> None:
        rendered = render_result(
            make_result(
                SentinelConfigWriteStatus.ROLLED_BACK,
                SentinelConfigWriteReason.POST_VALIDATION_FAILED,
                rolled_back=True,
            ),
            translations=load_translations("en"),
        )

        self.assertIn("ROLLED_BACK", rendered)
        self.assertIn("original configuration was restored", rendered)

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

    def test_rollback_failure_is_critical_in_english(self) -> None:
        rendered = render_result(
            make_result(
                SentinelConfigWriteStatus.FAILED,
                SentinelConfigWriteReason.ROLLBACK_FAILED,
            ),
            translations=load_translations("en"),
        )

        self.assertIn("rollback FAILED", rendered)
        self.assertIn("could not be confirmed", rendered)
        self.assertNotIn("was restored by rollback", rendered)

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
                translations=load_translations("en"),
            )

            resolver.assert_called_once_with(game)
            self.assertIn("Post-operation state", rendered)
            before_post_state, post_state = rendered.split(
                "Post-operation state",
                maxsplit=1,
            )
            self.assertEqual(
                rendered_row_value(before_post_state, "Repair needed"),
                "⚠ Yes",
            )
            self.assertEqual(
                rendered_row_value(post_state, "Repair needed"),
                "✓ No",
            )
            self.assertEqual(
                rendered_row_value(post_state, "Full coverage"),
                "✓ Yes",
            )
            self.assertNotIn("⚠ Yes", post_state)

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

            resolver.assert_called_once_with(game)
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
                translations=load_translations("en"),
            )

            resolver.assert_called_once_with(game)
            self.assertIn("integration could not be checked again", rendered)
            self.assertIn("consulta indisponível", rendered)

    def test_initial_resolution_error_is_handled_and_rendered_literally(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            output = StringIO()
            test_console = Console(file=output, width=200, color_system=None)
            game = make_game(Path(temp_directory))
            error = RuntimeError("[bold]resolver detail[/bold]")

            with (
                patch(
                    "goldberg_manager.cli.resolve_game_sentinel_repair",
                    side_effect=error,
                ),
                patch("goldberg_manager.cli.apply_game_sentinel_repair") as writer,
                patch("goldberg_manager.cli.questionary.confirm") as confirm,
                patch("goldberg_manager.cli.console", test_console),
                patch("goldberg_manager.cli.clear_screen"),
                patch("goldberg_manager.cli.render_header"),
                patch("goldberg_manager.cli.pause") as pause_mock,
            ):
                repair_game_sentinel_integration(
                    game,
                    translations=load_translations("en"),
                )

        rendered = output.getvalue()
        self.assertIn("Could not resolve the Sentinel repair", rendered)
        self.assertIn("[bold]resolver detail[/bold]", rendered)
        pause_mock.assert_called_once_with("Press Enter to continue...")
        confirm.assert_not_called()
        writer.assert_not_called()

    def test_unexpected_confirmation_exception_propagates_without_writing(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            game = make_game(Path(temp_directory))
            plan = make_plan((standard_root(),))
            error = RuntimeError("confirmation failed")
            translations = load_translations("en")

            with (
                patch(
                    "goldberg_manager.cli.resolve_game_sentinel_repair",
                    return_value=plan,
                ),
                patch("goldberg_manager.cli.questionary.confirm") as confirm,
                patch("goldberg_manager.cli.apply_game_sentinel_repair") as writer,
                patch(
                    "goldberg_manager.cli.show_sentinel_config_write_result"
                ) as write_result,
                patch(
                    "goldberg_manager.cli._show_sentinel_repair_plan"
                ) as plan_renderer,
                patch("goldberg_manager.cli.console.print"),
                patch("goldberg_manager.cli.clear_screen"),
                patch("goldberg_manager.cli.render_header"),
                patch("goldberg_manager.cli.pause"),
                self.assertRaises(RuntimeError) as raised,
            ):
                confirm.return_value.ask.side_effect = error
                repair_game_sentinel_integration(
                    game,
                    translations=translations,
                )

        self.assertIs(raised.exception, error)
        confirm.assert_called_once_with(
            "Apply this Sentinel repair?",
            default=False,
        )
        confirm.return_value.ask.assert_called_once_with()
        writer.assert_not_called()
        write_result.assert_not_called()
        plan_renderer.assert_called_once_with(
            game,
            plan,
            title="Sentinel • Plano de reparo",
            translations=translations,
        )

    def test_unexpected_writer_exception_propagates_after_affirmative_consent(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            game = make_game(Path(temp_directory))
            plan = make_plan((standard_root(),))
            error = RuntimeError("writer failed")

            with (
                patch(
                    "goldberg_manager.cli.resolve_game_sentinel_repair",
                    return_value=plan,
                ),
                patch("goldberg_manager.cli.questionary.confirm") as confirm,
                patch(
                    "goldberg_manager.cli.apply_game_sentinel_repair",
                    side_effect=error,
                ) as writer,
                patch("goldberg_manager.cli.console.print"),
                patch("goldberg_manager.cli.clear_screen"),
                patch("goldberg_manager.cli.render_header"),
                patch("goldberg_manager.cli.pause"),
                self.assertRaises(RuntimeError) as raised,
            ):
                confirm.return_value.ask.return_value = True
                repair_game_sentinel_integration(
                    game,
                    translations=load_translations("en"),
                )

        self.assertIs(raised.exception, error)
        writer.assert_called_once_with(game, plan, allow_partial=False)

    def test_plan_translations_game_paths_and_prefixes_render_literally(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            game = make_game(
                Path(temp_directory),
                name="[bold]literal game[/bold]",
            )
            config_path = Path("/config/[red]literal config[/red].json")
            save_root = standard_root(Path("/games/[link]literal prefix[/link]"))
            plan = make_plan((save_root,), status=make_status(path=config_path))
            translations = MappingTranslations(
                {
                    "Sentinel • Plano de reparo": (
                        "[italic]literal translated title[/italic]"
                    ),
                    "Será adicionado": "[underline]literal label[/underline]",
                }
            )

            rendered, _, writer, _ = run_repair(
                game,
                plan,
                confirmed=False,
                translations=translations,
            )

        self.assertIn("[italic]literal translated title[/italic]", rendered)
        self.assertIn("[underline]literal label[/underline]", rendered)
        self.assertIn("[bold]literal game[/bold]", rendered)
        self.assertIn(str(config_path), rendered)
        self.assertIn("[link]literal prefix[/link]", rendered)
        writer.assert_not_called()

    def test_result_translations_paths_and_unknown_messages_render_literally(
        self,
    ) -> None:
        config_path = Path("/config/[red]literal config[/red].json")
        prefix = Path("/games/[link]literal prefix[/link]")
        backup = Path("/backup/[bold]literal backup[/bold].json")
        raw_message = "[italic]literal writer detail[/italic]"
        translations = MappingTranslations(
            {
                "Resultado do reparo Sentinel": (
                    "[underline]literal result title[/underline]"
                ),
                "Mensagem": "[reverse]literal message label[/reverse]",
                raw_message: "must not replace arbitrary writer detail",
            }
        )
        rendered = render_result(
            make_result(
                SentinelConfigWriteStatus.APPLIED,
                SentinelConfigWriteReason.APPLIED,
                config_path=config_path,
                added_prefixes=(prefix,),
                backup_path=backup,
                message=raw_message,
            ),
            translations=translations,
        )

        self.assertIn("[underline]literal result title[/underline]", rendered)
        self.assertIn("[reverse]literal message label[/reverse]", rendered)
        self.assertIn(str(config_path), rendered)
        self.assertIn(str(prefix), rendered)
        self.assertIn(str(backup), rendered)
        self.assertIn(raw_message, rendered)
        self.assertNotIn("must not replace arbitrary writer detail", rendered)


if __name__ == "__main__":
    unittest.main()
