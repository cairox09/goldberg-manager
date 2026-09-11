from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from contextlib import ExitStack
from dataclasses import asdict
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from rich.console import Console

from goldberg_manager.application.guided_configuration import GameAssistantStatus
from goldberg_manager.cli import (
    generate_emu_config_menu,
    goldberg_game_assistant_menu,
    show_emu_config_summary,
)
from goldberg_manager.config import AppConfig, GoldbergConfig
from goldberg_manager.core.game import Game
from goldberg_manager.emu_config import EmuConfigError, EmuConfigSummary
from goldberg_manager.presentation.i18n import load_translations


class RecordingTranslations:
    def __init__(self, messages: dict[str, str] | None = None) -> None:
        self.translations = messages or {}
        self.messages: list[str] = []

    def gettext(self, message: str) -> str:
        self.messages.append(message)
        return self.translations.get(message, message)


def make_summary(
    *,
    output_directory: Path = Path("/gse/_OUTPUT/2353060"),
    achievements_count: int = 12,
    achievement_images_count: int = 9,
    supported_languages_count: int = 4,
    dlc_count: int = 3,
    depots_count: int = 2,
    branches_count: int = 1,
    has_product_info: bool = True,
    has_app_details: bool = True,
) -> EmuConfigSummary:
    steam_settings = output_directory / "steam_settings"
    return EmuConfigSummary(
        app_id=2353060,
        output_directory=output_directory,
        steam_settings_directory=steam_settings,
        achievements_file=(
            steam_settings / "achievements.json" if achievements_count else None
        ),
        achievements_count=achievements_count,
        achievement_images_directory=steam_settings / "img",
        achievement_images_count=achievement_images_count,
        supported_languages_count=supported_languages_count,
        dlc_count=dlc_count,
        depots_count=depots_count,
        branches_count=branches_count,
        has_product_info=has_product_info,
        has_app_details=has_app_details,
    )


def make_game(
    root: Path = Path("/games/Example"),
    *,
    name: str = "Example Game",
) -> Game:
    return Game(
        name=name,
        root_directory=root,
        executable=root / "Game.exe",
        steam_api=root / "steam_api64.dll",
        steam_api_relative_path=Path("steam_api64.dll"),
        architecture="64-bit",
        source_directory=root.parent,
    )


def make_generation_config(
    generator: Path | None = Path("/gse/generate_emu_config"),
) -> AppConfig:
    return AppConfig(
        goldberg=GoldbergConfig(
            emu_config_generator=generator,
        )
    )


GENERATION_UNRELATED_MUTATIONS = (
    "apply_game_sentinel_repair",
    "backup_game",
    "create_settings_safety_backup",
    "create_steam_settings_backup",
    "generate_game_steam_interfaces",
    "generate_game_steam_settings",
    "import_generated_achievements",
    "restore_game_backup",
    "restore_steam_settings_backup",
    "save_appid_search_cache",
    "save_config",
    "update_game_steam_appid",
    "update_user_setting",
)


def render_summary(
    summary: EmuConfigSummary,
    *,
    translations=None,
) -> tuple[str, dict[str, object]]:
    output = StringIO()
    test_console = Console(file=output, width=240, color_system=None)
    boundary_names = (
        "questionary.select",
        "questionary.text",
        "questionary.confirm",
        "questionary.autocomplete",
        "pause",
        "run_generate_emu_config",
        "read_generated_emu_summary",
        "import_generated_achievements",
        "create_settings_safety_backup",
        "create_steam_settings_backup",
        "backup_game",
        "restore_game_backup",
        "restore_steam_settings_backup",
        "generate_game_steam_interfaces",
        "generate_game_steam_settings",
        "apply_game_sentinel_repair",
        "save_config",
        "save_appid_search_cache",
        "search_game_on_steam",
        "update_game_steam_appid",
        "update_user_setting",
    )
    path_mutation_names = (
        "mkdir",
        "rename",
        "replace",
        "rmdir",
        "touch",
        "unlink",
        "write_bytes",
        "write_text",
    )

    with ExitStack() as stack:
        stack.enter_context(patch("goldberg_manager.cli.console", test_console))
        boundaries = {
            name: stack.enter_context(patch(f"goldberg_manager.cli.{name}"))
            for name in boundary_names
        }
        boundaries.update(
            {
                f"Path.{name}": stack.enter_context(patch.object(Path, name))
                for name in path_mutation_names
            }
        )
        boundaries.update(
            {
                "shutil.copy": stack.enter_context(patch.object(shutil, "copy")),
                "shutil.copy2": stack.enter_context(patch.object(shutil, "copy2")),
                "shutil.move": stack.enter_context(patch.object(shutil, "move")),
                "shutil.rmtree": stack.enter_context(patch.object(shutil, "rmtree")),
            }
        )
        subprocess_run = stack.enter_context(patch.object(subprocess, "run"))

        if translations is None:
            show_emu_config_summary(summary)
        else:
            show_emu_config_summary(summary, translations=translations)

    boundaries["subprocess.run"] = subprocess_run
    return output.getvalue(), boundaries


class EmuConfigSummaryCliTests(unittest.TestCase):
    def assert_read_only(self, boundaries: dict[str, object]) -> None:
        for name, boundary in boundaries.items():
            with self.subTest(boundary=name):
                boundary.assert_not_called()

    def test_default_invocation_loads_translations_exactly_once(self) -> None:
        translations = RecordingTranslations(
            {"Dados gerados pelo GSE": "Loaded summary title"}
        )

        with patch(
            "goldberg_manager.cli.load_translations",
            return_value=translations,
        ) as loader:
            rendered, boundaries = render_summary(make_summary())

        loader.assert_called_once_with()
        self.assertIn("Loaded summary title", rendered)
        self.assertIn("Dados gerados pelo GSE", translations.messages)
        self.assert_read_only(boundaries)

    def test_explicit_translations_bypass_loader_and_reuse_exact_object(self) -> None:
        translations = RecordingTranslations(
            {
                "Achievements": "Exact achievements",
                "Imagens": "Exact images",
            }
        )

        with patch("goldberg_manager.cli.load_translations") as loader:
            rendered, boundaries = render_summary(
                make_summary(),
                translations=translations,
            )

        loader.assert_not_called()
        self.assertIn("Exact achievements", rendered)
        self.assertIn("Exact images", rendered)
        self.assertEqual(
            translations.messages,
            [
                "Achievements",
                "Imagens",
                "Idiomas",
                "DLCs",
                "Depots",
                "Branches",
                "Product info",
                "Sim",
                "App details",
                "Sim",
                "Dados gerados pelo GSE",
                "Output:",
            ],
        )
        self.assert_read_only(boundaries)

    def test_portuguese_complete_summary_preserves_order_and_literal_values(
        self,
    ) -> None:
        summary = make_summary()
        summary_before = asdict(summary)

        rendered, boundaries = render_summary(summary)

        expected_in_order = (
            "Steam AppID",
            "Achievements",
            "Imagens",
            "Idiomas",
            "DLCs",
            "Depots",
            "Branches",
            "Product info",
            "App details",
        )
        positions = [rendered.index(value) for value in expected_in_order]
        self.assertEqual(positions, sorted(positions))
        for expected in (
            "Dados gerados pelo GSE",
            "2353060",
            "✓ 12",
            "✓ 9",
            "4",
            "3",
            "2",
            "1",
            "✓ Sim",
            "Output:",
            str(summary.output_directory),
        ):
            self.assertIn(expected, rendered)
        self.assertEqual(asdict(summary), summary_before)
        self.assert_read_only(boundaries)

    def test_english_complete_and_missing_states_preserve_semantics(self) -> None:
        translations = load_translations("en")
        complete, complete_boundaries = render_summary(
            make_summary(),
            translations=translations,
        )
        missing_summary = make_summary(
            achievements_count=0,
            achievement_images_count=0,
            supported_languages_count=0,
            dlc_count=0,
            depots_count=0,
            branches_count=0,
            has_product_info=False,
            has_app_details=False,
        )
        missing_before = asdict(missing_summary)
        missing, missing_boundaries = render_summary(
            missing_summary,
            translations=translations,
        )

        for expected in (
            "Data generated by GSE",
            "Achievements",
            "Images",
            "Languages",
            "✓ 12",
            "✓ 9",
            "✓ Yes",
            str(make_summary().output_directory),
        ):
            self.assertIn(expected, complete)
        for expected in (
            "⚠ Not found",
            "⚠ None",
            "⚠ No",
        ):
            self.assertIn(expected, missing)
        self.assertEqual(complete.count("✓ Yes"), 2)
        no_status_lines = [
            line
            for line in missing.splitlines()
            if "⚠ No" in line and "Not found" not in line and "None" not in line
        ]
        self.assertEqual(len(no_status_lines), 2)
        self.assertNotIn("Não encontrados", missing)
        self.assertNotIn("Nenhuma", missing)
        self.assertEqual(asdict(missing_summary), missing_before)
        self.assert_read_only(complete_boundaries)
        self.assert_read_only(missing_boundaries)

    def test_rich_like_translations_and_output_path_render_literally(self) -> None:
        output_directory = Path("/gse/[bold]literal-output[/bold]/2353060")
        translations = RecordingTranslations(
            {
                "Achievements": "[red]literal achievements[/red]",
                "Imagens": "[bold]literal images[/bold]",
                "Sim": "[green]literal yes[/green]",
                "Dados gerados pelo GSE": "[cyan]literal title[/cyan]",
                "Output:": "[magenta]literal output[/magenta]",
            }
        )

        rendered, boundaries = render_summary(
            make_summary(output_directory=output_directory),
            translations=translations,
        )

        for expected in (
            "[red]literal achievements[/red]",
            "[bold]literal images[/bold]",
            "[green]literal yes[/green]",
            "[cyan]literal title[/cyan]",
            "[magenta]literal output[/magenta]",
            str(output_directory),
        ):
            self.assertIn(expected, rendered)
        self.assert_read_only(boundaries)


class EmuConfigGenerationCliTests(unittest.TestCase):
    def test_default_invocation_loads_once_and_cancellation_is_isolated(
        self,
    ) -> None:
        config = make_generation_config()
        translations = RecordingTranslations()

        with ExitStack() as stack:
            loader = stack.enter_context(
                patch(
                    "goldberg_manager.cli.load_translations",
                    return_value=translations,
                )
            )
            get_game = stack.enter_context(
                patch("goldberg_manager.cli.get_menu_game", return_value=None)
            )
            settings_reader = stack.enter_context(
                patch("goldberg_manager.cli.read_game_steam_settings")
            )
            mode_select = stack.enter_context(
                patch("goldberg_manager.cli.questionary.select")
            )
            confirm = stack.enter_context(
                patch("goldberg_manager.cli.questionary.confirm")
            )
            runner = stack.enter_context(
                patch("goldberg_manager.cli.run_generate_emu_config")
            )
            readback = stack.enter_context(
                patch("goldberg_manager.cli.read_generated_emu_summary")
            )
            summary_renderer = stack.enter_context(
                patch("goldberg_manager.cli.show_emu_config_summary")
            )
            print_output = stack.enter_context(
                patch("goldberg_manager.cli.console.print")
            )
            pause = stack.enter_context(patch("goldberg_manager.cli.pause"))
            unrelated = [
                stack.enter_context(patch(f"goldberg_manager.cli.{name}"))
                for name in GENERATION_UNRELATED_MUTATIONS
            ]
            stack.enter_context(patch("goldberg_manager.cli.clear_screen"))
            stack.enter_context(patch("goldberg_manager.cli.render_header"))

            generate_emu_config_menu(config)

        loader.assert_called_once_with()
        get_game.assert_called_once_with(
            config,
            None,
            "Selecione o jogo para gerar dados Steam / achievements:",
            translations=translations,
        )
        self.assertIs(get_game.call_args.kwargs["translations"], translations)
        settings_reader.assert_not_called()
        mode_select.assert_not_called()
        confirm.assert_not_called()
        runner.assert_not_called()
        readback.assert_not_called()
        summary_renderer.assert_not_called()
        print_output.assert_not_called()
        pause.assert_not_called()
        for mutation in unrelated:
            mutation.assert_not_called()

    def test_explicit_translations_and_positional_game_bypass_selection(
        self,
    ) -> None:
        config = make_generation_config(None)
        game = make_game()
        translations = RecordingTranslations(
            {"Pressione Enter para continuar...": "Continue"}
        )

        with (
            patch("goldberg_manager.cli.load_translations") as loader,
            patch("goldberg_manager.cli.get_detected_games") as detect_games,
            patch("goldberg_manager.cli.select_game") as select_game,
            patch("goldberg_manager.cli.questionary.select") as mode_select,
            patch("goldberg_manager.cli.read_game_steam_settings") as settings_reader,
            patch("goldberg_manager.cli.run_generate_emu_config") as runner,
            patch("goldberg_manager.cli.console.print"),
            patch("goldberg_manager.cli.pause") as pause,
            patch("goldberg_manager.cli.clear_screen"),
            patch("goldberg_manager.cli.render_header"),
        ):
            generate_emu_config_menu(
                config,
                game,
                translations=translations,
            )

        loader.assert_not_called()
        detect_games.assert_not_called()
        select_game.assert_not_called()
        mode_select.assert_not_called()
        settings_reader.assert_not_called()
        runner.assert_not_called()
        pause.assert_called_once_with("Continue")

    def test_missing_generator_translates_and_stops_before_settings_or_mode(
        self,
    ) -> None:
        game = make_game()
        output = StringIO()
        test_console = Console(file=output, width=240, color_system=None)
        translations = load_translations("en")

        with (
            patch("goldberg_manager.cli.get_menu_game", return_value=game),
            patch("goldberg_manager.cli.read_game_steam_settings") as settings_reader,
            patch("goldberg_manager.cli.questionary.select") as mode_select,
            patch("goldberg_manager.cli.questionary.confirm") as confirm,
            patch("goldberg_manager.cli.run_generate_emu_config") as runner,
            patch("goldberg_manager.cli.console", test_console),
            patch("goldberg_manager.cli.pause") as pause,
            patch("goldberg_manager.cli.clear_screen"),
            patch("goldberg_manager.cli.render_header"),
        ):
            generate_emu_config_menu(
                make_generation_config(None),
                translations=translations,
            )

        settings_reader.assert_not_called()
        mode_select.assert_not_called()
        confirm.assert_not_called()
        runner.assert_not_called()
        pause.assert_called_once_with("Press Enter to continue...")
        rendered = output.getvalue()
        self.assertIn(
            "generate_emu_config is not configured or could not be found.",
            rendered,
        )
        self.assertIn(
            "Go to Settings and use 'Detect generate_emu_config'.",
            rendered,
        )

    def test_handled_settings_read_errors_stop_before_mode_and_runner(self) -> None:
        game = make_game()
        translations = load_translations("en")

        for error in (
            OSError("unreadable [red]settings[/red]"),
            ValueError("invalid [bold]settings[/bold]"),
        ):
            with self.subTest(error_type=type(error).__name__):
                output = StringIO()
                test_console = Console(file=output, width=240, color_system=None)

                with (
                    patch("goldberg_manager.cli.get_menu_game", return_value=game),
                    patch.object(Path, "is_file", return_value=True),
                    patch(
                        "goldberg_manager.cli.read_game_steam_settings",
                        side_effect=error,
                    ) as settings_reader,
                    patch("goldberg_manager.cli.questionary.select") as mode_select,
                    patch("goldberg_manager.cli.questionary.confirm") as confirm,
                    patch("goldberg_manager.cli.run_generate_emu_config") as runner,
                    patch("goldberg_manager.cli.console", test_console),
                    patch("goldberg_manager.cli.pause") as pause,
                    patch("goldberg_manager.cli.clear_screen"),
                    patch("goldberg_manager.cli.render_header"),
                ):
                    generate_emu_config_menu(
                        make_generation_config(),
                        translations=translations,
                    )

                settings_reader.assert_called_once_with(game)
                mode_select.assert_not_called()
                confirm.assert_not_called()
                runner.assert_not_called()
                pause.assert_called_once_with("Press Enter to continue...")
                rendered = output.getvalue()
                self.assertIn("Could not read steam_settings:", rendered)
                self.assertIn(str(error), rendered)

    def test_missing_appid_stops_before_mode_and_runner(self) -> None:
        game = make_game()
        output = StringIO()
        test_console = Console(file=output, width=240, color_system=None)
        translations = load_translations("en")

        with (
            patch("goldberg_manager.cli.get_menu_game", return_value=game),
            patch.object(Path, "is_file", return_value=True),
            patch(
                "goldberg_manager.cli.read_game_steam_settings",
                return_value=SimpleNamespace(app_id=None),
            ) as settings_reader,
            patch("goldberg_manager.cli.questionary.select") as mode_select,
            patch("goldberg_manager.cli.questionary.confirm") as confirm,
            patch("goldberg_manager.cli.run_generate_emu_config") as runner,
            patch("goldberg_manager.cli.console", test_console),
            patch("goldberg_manager.cli.pause") as pause,
            patch("goldberg_manager.cli.clear_screen"),
            patch("goldberg_manager.cli.render_header"),
        ):
            generate_emu_config_menu(
                make_generation_config(),
                translations=translations,
            )

        settings_reader.assert_called_once_with(game)
        mode_select.assert_not_called()
        confirm.assert_not_called()
        runner.assert_not_called()
        pause.assert_called_once_with("Press Enter to continue...")
        rendered = output.getvalue()
        self.assertIn(
            "This game does not yet have a configured Steam AppID.",
            rendered,
        )
        self.assertIn(
            "Configure the AppID through the Assistant first.",
            rendered,
        )

    def test_mode_choices_use_translated_titles_and_stable_values(self) -> None:
        game = make_game()
        translations = RecordingTranslations(
            {
                "Autenticado (recomendado para achievements)": "duplicate title",
                "Anônimo": "duplicate title",
                "Cancelar": "duplicate title",
            }
        )

        with (
            patch("goldberg_manager.cli.get_menu_game", return_value=game),
            patch.object(Path, "is_file", return_value=True),
            patch(
                "goldberg_manager.cli.read_game_steam_settings",
                return_value=SimpleNamespace(app_id=2353060),
            ),
            patch("goldberg_manager.cli.questionary.select") as mode_select,
            patch("goldberg_manager.cli.questionary.confirm") as confirm,
            patch("goldberg_manager.cli.run_generate_emu_config") as runner,
            patch("goldberg_manager.cli.console.print"),
            patch("goldberg_manager.cli.pause") as pause,
            patch("goldberg_manager.cli.clear_screen"),
            patch("goldberg_manager.cli.render_header"),
        ):
            mode_select.return_value.ask.return_value = "duplicate title"
            generate_emu_config_menu(
                make_generation_config(),
                translations=translations,
            )

        choices = mode_select.call_args.kwargs["choices"]
        self.assertEqual(
            [choice.title for choice in choices],
            ["duplicate title", "duplicate title", "duplicate title"],
        )
        self.assertEqual(
            [choice.value for choice in choices],
            ["authenticated", "anonymous", "cancel"],
        )
        confirm.assert_not_called()
        runner.assert_not_called()
        pause.assert_not_called()

    def test_none_and_cancel_mode_return_without_confirmation_or_mutation(
        self,
    ) -> None:
        game = make_game()

        for answer in (None, "cancel"):
            with self.subTest(answer=answer), ExitStack() as stack:
                stack.enter_context(
                    patch("goldberg_manager.cli.get_menu_game", return_value=game)
                )
                stack.enter_context(patch.object(Path, "is_file", return_value=True))
                stack.enter_context(
                    patch(
                        "goldberg_manager.cli.read_game_steam_settings",
                        return_value=SimpleNamespace(app_id=2353060),
                    )
                )
                mode_select = stack.enter_context(
                    patch("goldberg_manager.cli.questionary.select")
                )
                confirm = stack.enter_context(
                    patch("goldberg_manager.cli.questionary.confirm")
                )
                runner = stack.enter_context(
                    patch("goldberg_manager.cli.run_generate_emu_config")
                )
                readback = stack.enter_context(
                    patch("goldberg_manager.cli.read_generated_emu_summary")
                )
                pause = stack.enter_context(patch("goldberg_manager.cli.pause"))
                unrelated = [
                    stack.enter_context(patch(f"goldberg_manager.cli.{name}"))
                    for name in GENERATION_UNRELATED_MUTATIONS
                ]
                stack.enter_context(patch("goldberg_manager.cli.console.print"))
                stack.enter_context(patch("goldberg_manager.cli.clear_screen"))
                stack.enter_context(patch("goldberg_manager.cli.render_header"))
                mode_select.return_value.ask.return_value = answer

                generate_emu_config_menu(
                    make_generation_config(),
                    translations=RecordingTranslations(),
                )

            confirm.assert_not_called()
            runner.assert_not_called()
            readback.assert_not_called()
            pause.assert_not_called()
            for mutation in unrelated:
                mutation.assert_not_called()

    def test_false_and_none_confirmation_preserve_default_true_and_do_not_run(
        self,
    ) -> None:
        game = make_game()
        translations = RecordingTranslations(
            {"Executar generate_emu_config agora?": "Translated confirmation"}
        )

        for answer in (False, None):
            with self.subTest(answer=answer), ExitStack() as stack:
                stack.enter_context(
                    patch("goldberg_manager.cli.get_menu_game", return_value=game)
                )
                stack.enter_context(patch.object(Path, "is_file", return_value=True))
                stack.enter_context(
                    patch(
                        "goldberg_manager.cli.read_game_steam_settings",
                        return_value=SimpleNamespace(app_id=2353060),
                    )
                )
                mode_select = stack.enter_context(
                    patch("goldberg_manager.cli.questionary.select")
                )
                confirm = stack.enter_context(
                    patch("goldberg_manager.cli.questionary.confirm")
                )
                runner = stack.enter_context(
                    patch("goldberg_manager.cli.run_generate_emu_config")
                )
                readback = stack.enter_context(
                    patch("goldberg_manager.cli.read_generated_emu_summary")
                )
                summary_renderer = stack.enter_context(
                    patch("goldberg_manager.cli.show_emu_config_summary")
                )
                pause = stack.enter_context(patch("goldberg_manager.cli.pause"))
                stack.enter_context(patch("goldberg_manager.cli.console.print"))
                stack.enter_context(patch("goldberg_manager.cli.clear_screen"))
                stack.enter_context(patch("goldberg_manager.cli.render_header"))
                mode_select.return_value.ask.return_value = "authenticated"
                confirm.return_value.ask.return_value = answer

                generate_emu_config_menu(
                    make_generation_config(),
                    translations=translations,
                )

            confirm.assert_called_once_with(
                "Translated confirmation",
                default=True,
            )
            runner.assert_not_called()
            readback.assert_not_called()
            summary_renderer.assert_not_called()
            pause.assert_not_called()

    def test_modes_preserve_exact_run_readback_summary_and_safety_contracts(
        self,
    ) -> None:
        cases = (
            ("authenticated", False),
            ("anonymous", True),
        )

        for mode, anonymous in cases:
            with self.subTest(mode=mode), ExitStack() as stack:
                config = make_generation_config()
                game = make_game()
                summary = make_summary()
                translations = RecordingTranslations(
                    {"Pressione Enter para continuar...": "Continue"}
                )
                config_before = asdict(config)
                game_before = asdict(game)
                summary_before = asdict(summary)
                events: list[str] = []

                get_game = stack.enter_context(
                    patch(
                        "goldberg_manager.cli.get_menu_game",
                        side_effect=lambda *_args, _events=events, _game=game, **_kwargs: (
                            _events.append("game") or _game
                        ),
                    )
                )
                stack.enter_context(patch.object(Path, "is_file", return_value=True))
                settings_reader = stack.enter_context(
                    patch(
                        "goldberg_manager.cli.read_game_steam_settings",
                        side_effect=lambda supplied, _events=events: (
                            _events.append("settings")
                            or SimpleNamespace(app_id=2353060)
                        ),
                    )
                )
                mode_question = Mock()
                mode_question.ask.side_effect = lambda _events=events, _mode=mode: (
                    _events.append("mode-ask") or _mode
                )
                mode_select = stack.enter_context(
                    patch(
                        "goldberg_manager.cli.questionary.select",
                        side_effect=lambda *_args, _events=events, _question=mode_question, **_kwargs: (
                            _events.append("mode-select") or _question
                        ),
                    )
                )
                confirmation = Mock()
                confirmation.ask.side_effect = lambda _events=events: (
                    _events.append("confirm-ask") or True
                )
                confirm = stack.enter_context(
                    patch(
                        "goldberg_manager.cli.questionary.confirm",
                        side_effect=lambda *_args, _events=events, _confirmation=confirmation, **_kwargs: (
                            _events.append("confirm") or _confirmation
                        ),
                    )
                )
                runner = stack.enter_context(
                    patch(
                        "goldberg_manager.cli.run_generate_emu_config",
                        side_effect=lambda *_args, _events=events, **_kwargs: (
                            _events.append("run")
                        ),
                    )
                )
                readback = stack.enter_context(
                    patch(
                        "goldberg_manager.cli.read_generated_emu_summary",
                        side_effect=lambda *_args, _events=events, _summary=summary, **_kwargs: (
                            _events.append("readback") or _summary
                        ),
                    )
                )
                summary_renderer = stack.enter_context(
                    patch(
                        "goldberg_manager.cli.show_emu_config_summary",
                        side_effect=lambda *_args, _events=events, **_kwargs: (
                            _events.append("summary")
                        ),
                    )
                )
                pause = stack.enter_context(
                    patch(
                        "goldberg_manager.cli.pause",
                        side_effect=lambda _message, _events=events: _events.append(
                            "pause"
                        ),
                    )
                )
                credential_prompt = stack.enter_context(
                    patch("goldberg_manager.cli.questionary.text")
                )
                unrelated = [
                    stack.enter_context(patch(f"goldberg_manager.cli.{name}"))
                    for name in GENERATION_UNRELATED_MUTATIONS
                ]
                stack.enter_context(patch("goldberg_manager.cli.console.print"))
                stack.enter_context(patch("goldberg_manager.cli.clear_screen"))
                stack.enter_context(patch("goldberg_manager.cli.render_header"))

                generate_emu_config_menu(
                    config,
                    game,
                    translations=translations,
                )

            get_game.assert_called_once_with(
                config,
                game,
                "Selecione o jogo para gerar dados Steam / achievements:",
                translations=translations,
            )
            self.assertIs(get_game.call_args.args[1], game)
            self.assertIs(get_game.call_args.kwargs["translations"], translations)
            settings_reader.assert_called_once_with(game)
            self.assertEqual(mode_select.call_count, 1)
            confirm.assert_called_once_with(
                "Executar generate_emu_config agora?",
                default=True,
            )
            runner.assert_called_once_with(
                config.goldberg.emu_config_generator,
                2353060,
                anonymous=anonymous,
            )
            readback.assert_called_once_with(
                config.goldberg.emu_config_generator,
                2353060,
            )
            summary_renderer.assert_called_once_with(
                summary,
                translations=translations,
            )
            self.assertIs(summary_renderer.call_args.args[0], summary)
            self.assertIs(
                summary_renderer.call_args.kwargs["translations"],
                translations,
            )
            pause.assert_called_once_with("Continue")
            credential_prompt.assert_not_called()
            self.assertEqual(
                events,
                [
                    "game",
                    "settings",
                    "mode-select",
                    "mode-ask",
                    "confirm",
                    "confirm-ask",
                    "run",
                    "readback",
                    "summary",
                    "pause",
                ],
            )
            for mutation in unrelated:
                mutation.assert_not_called()
            self.assertEqual(asdict(config), config_before)
            self.assertEqual(asdict(game), game_before)
            self.assertEqual(asdict(summary), summary_before)

    def test_default_portuguese_success_and_authenticated_warning(self) -> None:
        config = make_generation_config()
        game = make_game()
        summary = make_summary()
        output = StringIO()
        test_console = Console(file=output, width=240, color_system=None)

        with (
            patch("goldberg_manager.cli.get_menu_game", return_value=game),
            patch.object(Path, "is_file", return_value=True),
            patch(
                "goldberg_manager.cli.read_game_steam_settings",
                return_value=SimpleNamespace(app_id=2353060),
            ),
            patch("goldberg_manager.cli.questionary.select") as mode_select,
            patch("goldberg_manager.cli.questionary.confirm") as confirm,
            patch("goldberg_manager.cli.run_generate_emu_config"),
            patch(
                "goldberg_manager.cli.read_generated_emu_summary",
                return_value=summary,
            ),
            patch("goldberg_manager.cli.show_emu_config_summary") as summary_renderer,
            patch("goldberg_manager.cli.console", test_console),
            patch("goldberg_manager.cli.pause") as pause,
            patch("goldberg_manager.cli.clear_screen"),
            patch("goldberg_manager.cli.render_header"),
        ):
            mode_select.return_value.ask.return_value = "authenticated"
            confirm.return_value.ask.return_value = True
            generate_emu_config_menu(config, game)

        choices = mode_select.call_args.kwargs["choices"]
        self.assertEqual(
            [choice.title for choice in choices],
            [
                "Autenticado (recomendado para achievements)",
                "Anônimo",
                "Cancelar",
            ],
        )
        confirm.assert_called_once_with(
            "Executar generate_emu_config agora?",
            default=True,
        )
        rendered = output.getvalue()
        for expected in (
            "Geração de dados Steam",
            "O diretório _OUTPUT deste AppID será recriado.",
            "Nenhum arquivo do jogo será alterado nesta etapa.",
            "O generate_emu_config poderá solicitar login, senha e Steam Guard",
            "O Goldberg Manager não salvará essas credenciais.",
            "Iniciando generate_emu_config...",
            "Dados Steam gerados com sucesso!",
            "Os dados ainda não foram importados para o jogo.",
        ):
            self.assertIn(expected, rendered)
        supplied_translations = summary_renderer.call_args.kwargs["translations"]
        self.assertEqual(
            supplied_translations.gettext("Dados Steam gerados com sucesso!"),
            "Dados Steam gerados com sucesso!",
        )
        pause.assert_called_once_with("Pressione Enter para continuar...")

    def test_compiled_english_exercises_real_settings_readback_and_summary(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            generator = root / "gse" / "generate_emu_config"
            generator.parent.mkdir(parents=True)
            generator.write_text("", encoding="utf-8")

            game_root = root / "games" / "Example"
            settings_directory = game_root / "steam_settings"
            settings_directory.mkdir(parents=True)
            (settings_directory / "steam_appid.txt").write_text(
                "2353060\n",
                encoding="utf-8",
            )
            output_settings = (
                generator.parent / "_OUTPUT" / "2353060" / "steam_settings"
            )
            output_settings.mkdir(parents=True)
            (output_settings / "supported_languages.txt").write_text(
                "english\nbrazilian\n",
                encoding="utf-8",
            )

            config = make_generation_config(generator)
            game = make_game(game_root)
            translations = load_translations("en")
            config_before = asdict(config)
            game_before = asdict(game)
            output = StringIO()
            test_console = Console(file=output, width=240, color_system=None)

            with (
                patch("goldberg_manager.cli.questionary.select") as mode_select,
                patch("goldberg_manager.cli.questionary.confirm") as confirm,
                patch("goldberg_manager.cli.run_generate_emu_config") as runner,
                patch("goldberg_manager.cli.console", test_console),
                patch("goldberg_manager.cli.pause") as pause,
                patch("goldberg_manager.cli.clear_screen"),
                patch("goldberg_manager.cli.render_header"),
            ):
                mode_select.return_value.ask.return_value = "anonymous"
                confirm.return_value.ask.return_value = True
                generate_emu_config_menu(
                    config,
                    game,
                    translations=translations,
                )

            runner.assert_called_once_with(
                generator,
                2353060,
                anonymous=True,
            )
            pause.assert_called_once_with("Press Enter to continue...")
            rendered = output.getvalue()
            for expected in (
                "Steam data generation",
                "Mode",
                "Anonymous",
                "The _OUTPUT directory for this AppID will be recreated.",
                "Starting generate_emu_config...",
                "Steam data generated successfully!",
                "Data generated by GSE",
                "Languages",
                "The data has not yet been imported into the game.",
            ):
                self.assertIn(expected, rendered)
            self.assertNotIn("não", rendered.casefold())
            self.assertEqual(asdict(config), config_before)
            self.assertEqual(asdict(game), game_before)

    def test_anonymous_mode_omits_authenticated_credential_warning(self) -> None:
        game = make_game()
        output = StringIO()
        test_console = Console(file=output, width=240, color_system=None)

        with (
            patch("goldberg_manager.cli.get_menu_game", return_value=game),
            patch.object(Path, "is_file", return_value=True),
            patch(
                "goldberg_manager.cli.read_game_steam_settings",
                return_value=SimpleNamespace(app_id=2353060),
            ),
            patch("goldberg_manager.cli.questionary.select") as mode_select,
            patch("goldberg_manager.cli.questionary.confirm") as confirm,
            patch("goldberg_manager.cli.run_generate_emu_config"),
            patch(
                "goldberg_manager.cli.read_generated_emu_summary",
                return_value=make_summary(),
            ),
            patch("goldberg_manager.cli.show_emu_config_summary"),
            patch("goldberg_manager.cli.questionary.text") as credential_prompt,
            patch("goldberg_manager.cli.console", test_console),
            patch("goldberg_manager.cli.pause"),
            patch("goldberg_manager.cli.clear_screen"),
            patch("goldberg_manager.cli.render_header"),
        ):
            mode_select.return_value.ask.return_value = "anonymous"
            confirm.return_value.ask.return_value = True
            generate_emu_config_menu(
                make_generation_config(),
                translations=load_translations("en"),
            )

        credential_prompt.assert_not_called()
        rendered = output.getvalue()
        self.assertNotIn("request your login", rendered)
        self.assertNotIn("credentials", rendered)

    def test_all_handled_run_and_readback_errors_are_literal_without_success(
        self,
    ) -> None:
        errors = (
            FileNotFoundError("missing [bold]generator[/bold]"),
            EmuConfigError("failed [red]generation[/red]"),
            OSError("unavailable [cyan]output[/cyan]"),
            ValueError("invalid [green]summary[/green]"),
        )
        game = make_game()
        translations = load_translations("en")

        for boundary in ("run", "readback"):
            for error in errors:
                with self.subTest(
                    boundary=boundary,
                    error_type=type(error).__name__,
                ):
                    output = StringIO()
                    test_console = Console(file=output, width=240, color_system=None)

                    with (
                        patch("goldberg_manager.cli.get_menu_game", return_value=game),
                        patch.object(Path, "is_file", return_value=True),
                        patch(
                            "goldberg_manager.cli.read_game_steam_settings",
                            return_value=SimpleNamespace(app_id=2353060),
                        ),
                        patch("goldberg_manager.cli.questionary.select") as mode_select,
                        patch("goldberg_manager.cli.questionary.confirm") as confirm,
                        patch("goldberg_manager.cli.run_generate_emu_config") as runner,
                        patch(
                            "goldberg_manager.cli.read_generated_emu_summary"
                        ) as readback,
                        patch(
                            "goldberg_manager.cli.show_emu_config_summary"
                        ) as summary_renderer,
                        patch("goldberg_manager.cli.console", test_console),
                        patch("goldberg_manager.cli.pause") as pause,
                        patch("goldberg_manager.cli.clear_screen"),
                        patch("goldberg_manager.cli.render_header"),
                    ):
                        mode_select.return_value.ask.return_value = "anonymous"
                        confirm.return_value.ask.return_value = True
                        if boundary == "run":
                            runner.side_effect = error
                        else:
                            readback.side_effect = error

                        generate_emu_config_menu(
                            make_generation_config(),
                            translations=translations,
                        )

                    runner.assert_called_once_with(
                        Path("/gse/generate_emu_config"),
                        2353060,
                        anonymous=True,
                    )
                    if boundary == "run":
                        readback.assert_not_called()
                    else:
                        readback.assert_called_once_with(
                            Path("/gse/generate_emu_config"),
                            2353060,
                        )
                    summary_renderer.assert_not_called()
                    pause.assert_called_once_with("Press Enter to continue...")
                    rendered = output.getvalue()
                    self.assertIn("Failed to generate Steam data.", rendered)
                    self.assertIn(str(error), rendered)
                    self.assertNotIn("generated successfully", rendered)

    def test_unexpected_run_and_readback_errors_propagate_without_false_success(
        self,
    ) -> None:
        game = make_game()

        for boundary in ("run", "readback"):
            with self.subTest(boundary=boundary):
                output = StringIO()
                test_console = Console(file=output, width=240, color_system=None)

                with (
                    patch("goldberg_manager.cli.get_menu_game", return_value=game),
                    patch.object(Path, "is_file", return_value=True),
                    patch(
                        "goldberg_manager.cli.read_game_steam_settings",
                        return_value=SimpleNamespace(app_id=2353060),
                    ),
                    patch("goldberg_manager.cli.questionary.select") as mode_select,
                    patch("goldberg_manager.cli.questionary.confirm") as confirm,
                    patch("goldberg_manager.cli.run_generate_emu_config") as runner,
                    patch(
                        "goldberg_manager.cli.read_generated_emu_summary"
                    ) as readback,
                    patch(
                        "goldberg_manager.cli.show_emu_config_summary"
                    ) as summary_renderer,
                    patch("goldberg_manager.cli.console", test_console),
                    patch("goldberg_manager.cli.pause") as pause,
                    patch("goldberg_manager.cli.clear_screen"),
                    patch("goldberg_manager.cli.render_header"),
                ):
                    mode_select.return_value.ask.return_value = "anonymous"
                    confirm.return_value.ask.return_value = True
                    if boundary == "run":
                        runner.side_effect = LookupError("unexpected run")
                    else:
                        readback.side_effect = LookupError("unexpected readback")

                    with self.assertRaisesRegex(LookupError, "unexpected"):
                        generate_emu_config_menu(
                            make_generation_config(),
                            translations=RecordingTranslations(),
                        )

                runner.assert_called_once()
                if boundary == "run":
                    readback.assert_not_called()
                else:
                    readback.assert_called_once()
                summary_renderer.assert_not_called()
                pause.assert_not_called()
                rendered = output.getvalue()
                self.assertNotIn("Dados Steam gerados com sucesso", rendered)
                self.assertNotIn("Falha ao gerar os dados Steam", rendered)

    def test_rich_like_translations_game_and_generator_path_are_literal(
        self,
    ) -> None:
        generator = Path("/gse/[bold]generator[/bold]")
        game = make_game(name="Game [red]name[/red]")
        translations = RecordingTranslations(
            {
                "Jogo": "[cyan]game label[/cyan]",
                "Modo": "[blue]mode label[/blue]",
                "Autenticado": "[green]authenticated[/green]",
                "Geração de dados Steam": "[magenta]generation title[/magenta]",
                "O diretório _OUTPUT deste AppID será recriado.": (
                    "[yellow]literal warning[/yellow]"
                ),
                "Nenhum arquivo do jogo será alterado nesta etapa.": (
                    "[dim]literal safety[/dim]"
                ),
                "O generate_emu_config poderá solicitar login, senha e Steam Guard diretamente no terminal.": (
                    "[bold]literal credential warning[/bold]"
                ),
                "O Goldberg Manager não salvará essas credenciais.": (
                    "[italic]literal credential safety[/italic]"
                ),
                "Iniciando generate_emu_config...": "[red]literal start[/red]",
                "Dados Steam gerados com sucesso!": "[green]literal success[/green]",
                "Os dados ainda não foram importados para o jogo.": (
                    "[blue]literal final note[/blue]"
                ),
            }
        )
        output = StringIO()
        test_console = Console(file=output, width=300, color_system=None)

        with (
            patch("goldberg_manager.cli.get_menu_game", return_value=game),
            patch.object(Path, "is_file", return_value=True),
            patch(
                "goldberg_manager.cli.read_game_steam_settings",
                return_value=SimpleNamespace(app_id=2353060),
            ),
            patch("goldberg_manager.cli.questionary.select") as mode_select,
            patch("goldberg_manager.cli.questionary.confirm") as confirm,
            patch("goldberg_manager.cli.run_generate_emu_config"),
            patch(
                "goldberg_manager.cli.read_generated_emu_summary",
                return_value=make_summary(),
            ),
            patch("goldberg_manager.cli.show_emu_config_summary"),
            patch("goldberg_manager.cli.console", test_console),
            patch("goldberg_manager.cli.pause"),
            patch("goldberg_manager.cli.clear_screen"),
            patch("goldberg_manager.cli.render_header"),
        ):
            mode_select.return_value.ask.return_value = "authenticated"
            confirm.return_value.ask.return_value = True
            generate_emu_config_menu(
                make_generation_config(generator),
                translations=translations,
            )

        rendered = output.getvalue()
        for expected in (
            "Game [red]name[/red]",
            str(generator),
            "[cyan]game label[/cyan]",
            "[blue]mode label[/blue]",
            "[green]authenticated[/green]",
            "[magenta]generation title[/magenta]",
            "[yellow]literal warning[/yellow]",
            "[dim]literal safety[/dim]",
            "[bold]literal credential warning[/bold]",
            "[italic]literal credential safety[/italic]",
            "[red]literal start[/red]",
            "[green]literal success[/green]",
            "[blue]literal final note[/blue]",
        ):
            self.assertIn(expected, rendered)

    def test_rich_like_error_translation_and_detail_are_literal(self) -> None:
        game = make_game()
        error = EmuConfigError("[bold]literal error detail[/bold]")
        translations = RecordingTranslations(
            {
                "Falha ao gerar os dados Steam.": "[red]literal error frame[/red]",
                "Pressione Enter para continuar...": "Continue",
            }
        )
        output = StringIO()
        test_console = Console(file=output, width=240, color_system=None)

        with (
            patch("goldberg_manager.cli.get_menu_game", return_value=game),
            patch.object(Path, "is_file", return_value=True),
            patch(
                "goldberg_manager.cli.read_game_steam_settings",
                return_value=SimpleNamespace(app_id=2353060),
            ),
            patch("goldberg_manager.cli.questionary.select") as mode_select,
            patch("goldberg_manager.cli.questionary.confirm") as confirm,
            patch(
                "goldberg_manager.cli.run_generate_emu_config",
                side_effect=error,
            ),
            patch("goldberg_manager.cli.read_generated_emu_summary") as readback,
            patch("goldberg_manager.cli.console", test_console),
            patch("goldberg_manager.cli.pause") as pause,
            patch("goldberg_manager.cli.clear_screen"),
            patch("goldberg_manager.cli.render_header"),
        ):
            mode_select.return_value.ask.return_value = "anonymous"
            confirm.return_value.ask.return_value = True
            generate_emu_config_menu(
                make_generation_config(),
                translations=translations,
            )

        readback.assert_not_called()
        pause.assert_called_once_with("Continue")
        rendered = output.getvalue()
        self.assertIn("[red]literal error frame[/red]", rendered)
        self.assertIn("[bold]literal error detail[/bold]", rendered)

    def test_assistant_generation_route_preserves_unchanged_call_contract(
        self,
    ) -> None:
        config = make_generation_config()
        game = make_game()
        status = GameAssistantStatus(
            app_id=None,
            app_id_confidence=None,
            app_id_configured=False,
            backup_exists=False,
            backup_valid=False,
            steam_settings_exists=False,
            steam_interfaces_exists=False,
            gbe_configured=False,
        )

        with (
            patch("goldberg_manager.cli.get_detected_games", return_value=[game]),
            patch("goldberg_manager.cli.select_game", return_value=game),
            patch(
                "goldberg_manager.cli.get_game_assistant_status",
                return_value=status,
            ),
            patch.object(Path, "is_file", return_value=True),
            patch(
                "goldberg_manager.cli.read_installed_achievements_status",
                return_value=SimpleNamespace(installed=False),
            ),
            patch("goldberg_manager.cli.questionary.select") as select,
            patch("goldberg_manager.cli.generate_emu_config_menu") as generation,
            patch("goldberg_manager.cli.console.print"),
            patch("goldberg_manager.cli.clear_screen"),
            patch("goldberg_manager.cli.render_header"),
        ):
            select.return_value.ask.side_effect = [
                "Gerar dados Steam / achievements",
                "Voltar",
            ]
            goldberg_game_assistant_menu(config)

        generation.assert_called_once_with(
            config,
            game=game,
        )
        self.assertEqual(generation.call_args.kwargs, {"game": game})


if __name__ == "__main__":
    unittest.main()
