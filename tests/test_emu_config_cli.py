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
    create_settings_safety_backup,
    generate_emu_config_menu,
    goldberg_game_assistant_menu,
    import_generated_achievements_menu,
    show_emu_config_summary,
)
from goldberg_manager.config import AppConfig, GoldbergConfig
from goldberg_manager.core.game import Game
from goldberg_manager.emu_config import (
    AchievementsImportResult,
    EmuConfigError,
    EmuConfigSummary,
)
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

IMPORT_UNRELATED_MUTATIONS = (
    "apply_game_sentinel_repair",
    "backup_game",
    "create_steam_settings_backup",
    "generate_game_steam_interfaces",
    "generate_game_steam_settings",
    "restore_game_backup",
    "restore_steam_settings_backup",
    "run_generate_emu_config",
    "save_appid_search_cache",
    "save_config",
    "search_game_on_steam",
    "update_game_steam_appid",
    "update_user_setting",
)


def make_import_environment(
    root: Path,
) -> tuple[AppConfig, Game, EmuConfigSummary]:
    generator = root / "gse" / "generate_emu_config"
    generator.parent.mkdir(parents=True)
    generator.write_text("", encoding="utf-8")
    game = make_game(root / "game")
    return (
        make_generation_config(generator),
        game,
        make_summary(output_directory=generator.parent / "_OUTPUT" / "2353060"),
    )


def make_import_result(
    destination: Path,
    *,
    achievements_count: int = 12,
    images_count: int = 9,
    write_achievements: bool = True,
) -> AchievementsImportResult:
    destination.mkdir(parents=True, exist_ok=True)
    achievements_file = destination / "achievements.json"
    if write_achievements:
        achievements_file.write_text("[]", encoding="utf-8")

    images_directory = destination / "img" if images_count else None
    if images_directory is not None:
        images_directory.mkdir(exist_ok=True)

    return AchievementsImportResult(
        destination_directory=destination,
        achievements_file=achievements_file,
        images_directory=images_directory,
        achievements_count=achievements_count,
        images_count=images_count,
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


class EmuConfigImportCliTests(unittest.TestCase):
    def test_default_invocation_loads_once_and_selection_cancellation_is_isolated(
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
            summary_reader = stack.enter_context(
                patch("goldberg_manager.cli.read_generated_emu_summary")
            )
            summary_renderer = stack.enter_context(
                patch("goldberg_manager.cli.show_emu_config_summary")
            )
            confirm = stack.enter_context(
                patch("goldberg_manager.cli.questionary.confirm")
            )
            safety_backup = stack.enter_context(
                patch("goldberg_manager.cli.create_settings_safety_backup")
            )
            importer = stack.enter_context(
                patch("goldberg_manager.cli.import_generated_achievements")
            )
            pause = stack.enter_context(patch("goldberg_manager.cli.pause"))
            stack.enter_context(patch("goldberg_manager.cli.console.print"))
            stack.enter_context(patch("goldberg_manager.cli.clear_screen"))
            stack.enter_context(patch("goldberg_manager.cli.render_header"))

            import_generated_achievements_menu(config)

        loader.assert_called_once_with()
        get_game.assert_called_once_with(
            config,
            None,
            "Selecione o jogo para importar achievements gerados:",
            translations=translations,
        )
        self.assertIs(get_game.call_args.kwargs["translations"], translations)
        settings_reader.assert_not_called()
        summary_reader.assert_not_called()
        summary_renderer.assert_not_called()
        confirm.assert_not_called()
        safety_backup.assert_not_called()
        importer.assert_not_called()
        pause.assert_not_called()

    def test_explicit_english_and_positional_game_bypass_discovery(
        self,
    ) -> None:
        game = make_game()
        translations = load_translations("en")
        output = StringIO()
        test_console = Console(file=output, width=240, color_system=None)

        with (
            patch("goldberg_manager.cli.load_translations") as loader,
            patch("goldberg_manager.cli.get_detected_games") as detect_games,
            patch("goldberg_manager.cli.select_game") as select_game,
            patch("goldberg_manager.cli.read_game_steam_settings") as settings_reader,
            patch("goldberg_manager.cli.console", test_console),
            patch("goldberg_manager.cli.pause") as pause,
            patch("goldberg_manager.cli.clear_screen"),
            patch("goldberg_manager.cli.render_header"),
        ):
            import_generated_achievements_menu(
                make_generation_config(None),
                game,
                translations=translations,
            )

        loader.assert_not_called()
        detect_games.assert_not_called()
        select_game.assert_not_called()
        settings_reader.assert_not_called()
        pause.assert_called_once_with("Press Enter to continue...")
        self.assertIn(
            "generate_emu_config is not configured or could not be found.",
            output.getvalue(),
        )
        self.assertIn(
            "Go to Settings and use 'Detect generate_emu_config'.",
            output.getvalue(),
        )

    def test_handled_settings_read_errors_stop_before_generated_data(self) -> None:
        translations = load_translations("en")

        for error in (
            OSError("unreadable [red]settings[/red]"),
            ValueError("invalid [bold]settings[/bold]"),
        ):
            with self.subTest(error_type=type(error).__name__):
                with tempfile.TemporaryDirectory() as temp_directory:
                    config, game, _ = make_import_environment(Path(temp_directory))
                    output = StringIO()
                    test_console = Console(
                        file=output,
                        width=240,
                        color_system=None,
                    )

                    with (
                        patch("goldberg_manager.cli.get_menu_game", return_value=game),
                        patch(
                            "goldberg_manager.cli.read_game_steam_settings",
                            side_effect=error,
                        ) as settings_reader,
                        patch(
                            "goldberg_manager.cli.read_generated_emu_summary"
                        ) as summary_reader,
                        patch(
                            "goldberg_manager.cli.create_settings_safety_backup"
                        ) as safety_backup,
                        patch(
                            "goldberg_manager.cli.import_generated_achievements"
                        ) as importer,
                        patch("goldberg_manager.cli.console", test_console),
                        patch("goldberg_manager.cli.pause") as pause,
                        patch("goldberg_manager.cli.clear_screen"),
                        patch("goldberg_manager.cli.render_header"),
                    ):
                        import_generated_achievements_menu(
                            config,
                            translations=translations,
                        )

                settings_reader.assert_called_once_with(game)
                summary_reader.assert_not_called()
                safety_backup.assert_not_called()
                importer.assert_not_called()
                pause.assert_called_once_with("Press Enter to continue...")
                self.assertIn("Could not read steam_settings:", output.getvalue())
                self.assertIn(str(error), output.getvalue())

    def test_unexpected_settings_reader_error_propagates_without_pause(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            config, game, _ = make_import_environment(Path(temp_directory))
            error = LookupError("unexpected settings reader")

            with (
                patch("goldberg_manager.cli.get_menu_game", return_value=game),
                patch(
                    "goldberg_manager.cli.read_game_steam_settings",
                    side_effect=error,
                ),
                patch(
                    "goldberg_manager.cli.read_generated_emu_summary"
                ) as summary_reader,
                patch("goldberg_manager.cli.pause") as pause,
                patch("goldberg_manager.cli.clear_screen"),
                patch("goldberg_manager.cli.render_header"),
                self.assertRaises(LookupError) as raised,
            ):
                import_generated_achievements_menu(
                    config,
                    translations=RecordingTranslations(),
                )

        self.assertIs(raised.exception, error)
        summary_reader.assert_not_called()
        pause.assert_not_called()

    def test_missing_appid_stops_before_generated_data(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            config, game, _ = make_import_environment(Path(temp_directory))
            output = StringIO()
            test_console = Console(file=output, width=240, color_system=None)

            with (
                patch("goldberg_manager.cli.get_menu_game", return_value=game),
                patch(
                    "goldberg_manager.cli.read_game_steam_settings",
                    return_value=SimpleNamespace(app_id=None),
                ) as settings_reader,
                patch(
                    "goldberg_manager.cli.read_generated_emu_summary"
                ) as summary_reader,
                patch(
                    "goldberg_manager.cli.create_settings_safety_backup"
                ) as safety_backup,
                patch("goldberg_manager.cli.import_generated_achievements") as importer,
                patch("goldberg_manager.cli.console", test_console),
                patch("goldberg_manager.cli.pause") as pause,
                patch("goldberg_manager.cli.clear_screen"),
                patch("goldberg_manager.cli.render_header"),
            ):
                import_generated_achievements_menu(
                    config,
                    translations=load_translations("en"),
                )

        settings_reader.assert_called_once_with(game)
        summary_reader.assert_not_called()
        safety_backup.assert_not_called()
        importer.assert_not_called()
        pause.assert_called_once_with("Press Enter to continue...")
        self.assertIn(
            "This game does not yet have a configured Steam AppID.",
            output.getvalue(),
        )
        self.assertIn(
            "Configure the AppID through the Assistant first.",
            output.getvalue(),
        )

    def test_handled_generated_summary_errors_are_literal_without_mutation(
        self,
    ) -> None:
        translations = load_translations("en")

        for error in (
            EmuConfigError("invalid [red]generated data[/red]"),
            OSError("unreadable [bold]output[/bold]"),
            ValueError("invalid [cyan]summary[/cyan]"),
        ):
            with self.subTest(error_type=type(error).__name__):
                with tempfile.TemporaryDirectory() as temp_directory:
                    config, game, _ = make_import_environment(Path(temp_directory))
                    output = StringIO()
                    test_console = Console(
                        file=output,
                        width=240,
                        color_system=None,
                    )

                    with (
                        patch("goldberg_manager.cli.get_menu_game", return_value=game),
                        patch(
                            "goldberg_manager.cli.read_game_steam_settings",
                            return_value=SimpleNamespace(app_id=2353060),
                        ),
                        patch(
                            "goldberg_manager.cli.read_generated_emu_summary",
                            side_effect=error,
                        ) as summary_reader,
                        patch(
                            "goldberg_manager.cli.show_emu_config_summary"
                        ) as summary_renderer,
                        patch(
                            "goldberg_manager.cli.create_settings_safety_backup"
                        ) as safety_backup,
                        patch(
                            "goldberg_manager.cli.import_generated_achievements"
                        ) as importer,
                        patch("goldberg_manager.cli.console", test_console),
                        patch("goldberg_manager.cli.pause") as pause,
                        patch("goldberg_manager.cli.clear_screen"),
                        patch("goldberg_manager.cli.render_header"),
                    ):
                        import_generated_achievements_menu(
                            config,
                            translations=translations,
                        )

                summary_reader.assert_called_once_with(
                    config.goldberg.emu_config_generator,
                    2353060,
                )
                summary_renderer.assert_not_called()
                safety_backup.assert_not_called()
                importer.assert_not_called()
                pause.assert_called_once_with("Press Enter to continue...")
                self.assertIn(
                    "Could not read the data generated by GSE.", output.getvalue()
                )
                self.assertIn(str(error), output.getvalue())

    def test_unexpected_generated_summary_error_propagates(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            config, game, _ = make_import_environment(Path(temp_directory))
            error = LookupError("unexpected generated summary")

            with (
                patch("goldberg_manager.cli.get_menu_game", return_value=game),
                patch(
                    "goldberg_manager.cli.read_game_steam_settings",
                    return_value=SimpleNamespace(app_id=2353060),
                ),
                patch(
                    "goldberg_manager.cli.read_generated_emu_summary",
                    side_effect=error,
                ),
                patch("goldberg_manager.cli.pause") as pause,
                patch("goldberg_manager.cli.clear_screen"),
                patch("goldberg_manager.cli.render_header"),
                self.assertRaises(LookupError) as raised,
            ):
                import_generated_achievements_menu(
                    config,
                    translations=RecordingTranslations(),
                )

        self.assertIs(raised.exception, error)
        pause.assert_not_called()

    def test_missing_generated_achievements_stops_before_preview_and_mutation(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            config, game, _ = make_import_environment(Path(temp_directory))
            summary = make_summary(achievements_count=0)
            output = StringIO()
            test_console = Console(file=output, width=240, color_system=None)

            with (
                patch("goldberg_manager.cli.get_menu_game", return_value=game),
                patch(
                    "goldberg_manager.cli.read_game_steam_settings",
                    return_value=SimpleNamespace(app_id=2353060),
                ),
                patch(
                    "goldberg_manager.cli.read_generated_emu_summary",
                    return_value=summary,
                ),
                patch("goldberg_manager.cli.show_emu_config_summary") as renderer,
                patch("goldberg_manager.cli.questionary.confirm") as confirm,
                patch(
                    "goldberg_manager.cli.create_settings_safety_backup"
                ) as safety_backup,
                patch("goldberg_manager.cli.import_generated_achievements") as importer,
                patch("goldberg_manager.cli.console", test_console),
                patch("goldberg_manager.cli.pause") as pause,
                patch("goldberg_manager.cli.clear_screen"),
                patch("goldberg_manager.cli.render_header"),
            ):
                import_generated_achievements_menu(
                    config,
                    translations=load_translations("en"),
                )

        renderer.assert_not_called()
        confirm.assert_not_called()
        safety_backup.assert_not_called()
        importer.assert_not_called()
        pause.assert_called_once_with("Press Enter to continue...")
        self.assertIn(
            "No achievements were found in the output for this AppID.",
            output.getvalue(),
        )
        self.assertIn(
            "First use the 'Generate Steam data / achievements' option.",
            output.getvalue(),
        )

    def test_default_portuguese_preview_propagates_identity_and_defaults_true(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            config, game, summary = make_import_environment(Path(temp_directory))
            translations = RecordingTranslations()
            output = StringIO()
            test_console = Console(file=output, width=240, color_system=None)

            with (
                patch(
                    "goldberg_manager.cli.load_translations",
                    return_value=translations,
                ) as loader,
                patch(
                    "goldberg_manager.cli.get_menu_game",
                    return_value=game,
                ) as get_game,
                patch(
                    "goldberg_manager.cli.read_game_steam_settings",
                    return_value=SimpleNamespace(app_id=2353060),
                ),
                patch(
                    "goldberg_manager.cli.read_generated_emu_summary",
                    return_value=summary,
                ),
                patch(
                    "goldberg_manager.cli.show_emu_config_summary"
                ) as summary_renderer,
                patch("goldberg_manager.cli.questionary.confirm") as confirm,
                patch(
                    "goldberg_manager.cli.create_settings_safety_backup"
                ) as safety_backup,
                patch("goldberg_manager.cli.import_generated_achievements") as importer,
                patch("goldberg_manager.cli.console", test_console),
                patch("goldberg_manager.cli.pause") as pause,
                patch("goldberg_manager.cli.clear_screen"),
                patch("goldberg_manager.cli.render_header"),
            ):
                confirm.return_value.ask.return_value = False
                import_generated_achievements_menu(config)

        loader.assert_called_once_with()
        self.assertIs(get_game.call_args.kwargs["translations"], translations)
        summary_renderer.assert_called_once_with(
            summary,
            translations=translations,
        )
        self.assertIs(
            summary_renderer.call_args.kwargs["translations"],
            translations,
        )
        confirm.assert_called_once_with(
            "Importar 12 achievements para Example Game?",
            default=True,
        )
        safety_backup.assert_not_called()
        importer.assert_not_called()
        pause.assert_not_called()
        rendered = output.getvalue()
        for expected in (
            "Destino",
            str(game.steam_api.parent / "steam_settings"),
            "Achievements",
            "12",
            "Imagens",
            "9",
            "Importação",
            "Nenhum achievement instalado foi encontrado.",
        ):
            self.assertIn(expected, rendered)

    def test_existing_targets_translate_and_preserve_default_false(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            config, game, summary = make_import_environment(Path(temp_directory))
            destination = game.steam_api.parent / "steam_settings"
            destination.mkdir(parents=True)
            achievements = destination / "achievements.json"
            achievements.write_text("[]", encoding="utf-8")
            images = destination / "img"
            images.mkdir()
            output = StringIO()
            test_console = Console(file=output, width=240, color_system=None)

            with (
                patch("goldberg_manager.cli.get_menu_game", return_value=game),
                patch(
                    "goldberg_manager.cli.read_game_steam_settings",
                    return_value=SimpleNamespace(app_id=2353060),
                ),
                patch(
                    "goldberg_manager.cli.read_generated_emu_summary",
                    return_value=summary,
                ),
                patch("goldberg_manager.cli.show_emu_config_summary"),
                patch("goldberg_manager.cli.questionary.confirm") as confirm,
                patch(
                    "goldberg_manager.cli.create_settings_safety_backup"
                ) as safety_backup,
                patch("goldberg_manager.cli.import_generated_achievements") as importer,
                patch("goldberg_manager.cli.console", test_console),
                patch("goldberg_manager.cli.pause") as pause,
                patch("goldberg_manager.cli.clear_screen"),
                patch("goldberg_manager.cli.render_header"),
            ):
                confirm.return_value.ask.return_value = False
                import_generated_achievements_menu(
                    config,
                    translations=load_translations("en"),
                )

        confirm.assert_called_once_with(
            "Import 12 achievements into Example Game?",
            default=False,
        )
        safety_backup.assert_not_called()
        importer.assert_not_called()
        pause.assert_not_called()
        rendered = output.getvalue()
        self.assertIn(
            "Warning: achievement data already exists in steam_settings.",
            rendered,
        )
        self.assertIn(str(achievements), rendered)
        self.assertIn(str(images), rendered)
        self.assertIn(
            "A complete steam_settings snapshot will be created before import.",
            rendered,
        )

    def test_false_and_none_confirmation_do_not_back_up_import_or_pause(self) -> None:
        for answer in (False, None):
            with self.subTest(answer=answer):
                with tempfile.TemporaryDirectory() as temp_directory:
                    config, game, summary = make_import_environment(
                        Path(temp_directory)
                    )

                    with (
                        patch("goldberg_manager.cli.get_menu_game", return_value=game),
                        patch(
                            "goldberg_manager.cli.read_game_steam_settings",
                            return_value=SimpleNamespace(app_id=2353060),
                        ),
                        patch(
                            "goldberg_manager.cli.read_generated_emu_summary",
                            return_value=summary,
                        ),
                        patch("goldberg_manager.cli.show_emu_config_summary"),
                        patch("goldberg_manager.cli.questionary.confirm") as confirm,
                        patch(
                            "goldberg_manager.cli.create_settings_safety_backup"
                        ) as safety_backup,
                        patch(
                            "goldberg_manager.cli.import_generated_achievements"
                        ) as importer,
                        patch("goldberg_manager.cli.console.print"),
                        patch("goldberg_manager.cli.pause") as pause,
                        patch("goldberg_manager.cli.clear_screen"),
                        patch("goldberg_manager.cli.render_header"),
                    ):
                        confirm.return_value.ask.return_value = answer
                        import_generated_achievements_menu(
                            config,
                            translations=RecordingTranslations(),
                        )

                self.assertTrue(confirm.call_args.kwargs["default"])
                safety_backup.assert_not_called()
                importer.assert_not_called()
                pause.assert_not_called()

    def test_safety_backup_failure_prevents_import(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            config, game, summary = make_import_environment(Path(temp_directory))
            translations = RecordingTranslations()

            with (
                patch("goldberg_manager.cli.get_menu_game", return_value=game),
                patch(
                    "goldberg_manager.cli.read_game_steam_settings",
                    return_value=SimpleNamespace(app_id=2353060),
                ),
                patch(
                    "goldberg_manager.cli.read_generated_emu_summary",
                    return_value=summary,
                ),
                patch("goldberg_manager.cli.show_emu_config_summary"),
                patch("goldberg_manager.cli.questionary.confirm") as confirm,
                patch(
                    "goldberg_manager.cli.create_settings_safety_backup",
                    return_value=False,
                ) as safety_backup,
                patch("goldberg_manager.cli.import_generated_achievements") as importer,
                patch("goldberg_manager.cli.console.print"),
                patch("goldberg_manager.cli.pause") as pause,
                patch("goldberg_manager.cli.clear_screen"),
                patch("goldberg_manager.cli.render_header"),
            ):
                confirm.return_value.ask.return_value = True
                import_generated_achievements_menu(
                    config,
                    translations=translations,
                )

        safety_backup.assert_called_once_with(
            game,
            translations=translations,
        )
        self.assertIs(safety_backup.call_args.kwargs["translations"], translations)
        importer.assert_not_called()
        pause.assert_not_called()

    def test_success_with_images_preserves_order_arguments_identity_and_isolation(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            config, game, summary = make_import_environment(Path(temp_directory))
            destination = game.steam_api.parent / "steam_settings"
            translations = RecordingTranslations(
                {"Pressione Enter para continuar...": "Continue"}
            )
            config_before = asdict(config)
            game_before = asdict(game)
            summary_before = asdict(summary)
            events: list[str] = []
            confirmation = Mock()
            confirmation.ask.side_effect = lambda: events.append("confirm-ask") or True

            with ExitStack() as stack:
                get_game = stack.enter_context(
                    patch(
                        "goldberg_manager.cli.get_menu_game",
                        side_effect=lambda *_args, **_kwargs: (
                            events.append("game") or game
                        ),
                    )
                )
                settings_reader = stack.enter_context(
                    patch(
                        "goldberg_manager.cli.read_game_steam_settings",
                        side_effect=lambda supplied: (
                            events.append("settings") or SimpleNamespace(app_id=2353060)
                        ),
                    )
                )
                summary_reader = stack.enter_context(
                    patch(
                        "goldberg_manager.cli.read_generated_emu_summary",
                        side_effect=lambda *_args: (
                            events.append("summary-read") or summary
                        ),
                    )
                )
                summary_renderer = stack.enter_context(
                    patch(
                        "goldberg_manager.cli.show_emu_config_summary",
                        side_effect=lambda *_args, **_kwargs: events.append(
                            "summary-render"
                        ),
                    )
                )
                confirm = stack.enter_context(
                    patch(
                        "goldberg_manager.cli.questionary.confirm",
                        side_effect=lambda *_args, **_kwargs: (
                            events.append("confirm") or confirmation
                        ),
                    )
                )
                safety_backup = stack.enter_context(
                    patch(
                        "goldberg_manager.cli.create_settings_safety_backup",
                        side_effect=lambda *_args, **_kwargs: (
                            events.append("backup") or True
                        ),
                    )
                )

                def import_result(
                    supplied_summary: EmuConfigSummary,
                    supplied_destination: Path,
                ) -> AchievementsImportResult:
                    events.append("import")
                    return make_import_result(supplied_destination)

                importer = stack.enter_context(
                    patch(
                        "goldberg_manager.cli.import_generated_achievements",
                        side_effect=import_result,
                    )
                )
                pause = stack.enter_context(
                    patch(
                        "goldberg_manager.cli.pause",
                        side_effect=lambda _message: events.append("pause"),
                    )
                )
                unrelated = [
                    stack.enter_context(patch(f"goldberg_manager.cli.{name}"))
                    for name in IMPORT_UNRELATED_MUTATIONS
                ]
                subprocess_run = stack.enter_context(patch.object(subprocess, "run"))
                stack.enter_context(patch("goldberg_manager.cli.console.print"))
                stack.enter_context(patch("goldberg_manager.cli.clear_screen"))
                stack.enter_context(patch("goldberg_manager.cli.render_header"))

                import_generated_achievements_menu(
                    config,
                    game,
                    translations=translations,
                )

        get_game.assert_called_once_with(
            config,
            game,
            "Selecione o jogo para importar achievements gerados:",
            translations=translations,
        )
        settings_reader.assert_called_once_with(game)
        summary_reader.assert_called_once_with(
            config.goldberg.emu_config_generator,
            2353060,
        )
        summary_renderer.assert_called_once_with(
            summary,
            translations=translations,
        )
        self.assertIs(
            summary_renderer.call_args.kwargs["translations"],
            translations,
        )
        confirm.assert_called_once_with(
            "Importar 12 achievements para Example Game?",
            default=True,
        )
        safety_backup.assert_called_once_with(
            game,
            translations=translations,
        )
        self.assertIs(safety_backup.call_args.kwargs["translations"], translations)
        importer.assert_called_once_with(summary, destination)
        self.assertIs(importer.call_args.args[0], summary)
        pause.assert_called_once_with("Continue")
        self.assertEqual(
            events,
            [
                "game",
                "settings",
                "summary-read",
                "summary-render",
                "confirm",
                "confirm-ask",
                "backup",
                "import",
                "pause",
            ],
        )
        subprocess_run.assert_not_called()
        for mutation in unrelated:
            mutation.assert_not_called()
        self.assertEqual(asdict(config), config_before)
        self.assertEqual(asdict(game), game_before)
        self.assertEqual(asdict(summary), summary_before)

    def test_compiled_english_success_without_images(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            config, game, _ = make_import_environment(Path(temp_directory))
            summary = make_summary(achievement_images_count=0)
            output = StringIO()
            test_console = Console(file=output, width=240, color_system=None)

            with (
                patch("goldberg_manager.cli.get_menu_game", return_value=game),
                patch(
                    "goldberg_manager.cli.read_game_steam_settings",
                    return_value=SimpleNamespace(app_id=2353060),
                ),
                patch(
                    "goldberg_manager.cli.read_generated_emu_summary",
                    return_value=summary,
                ),
                patch("goldberg_manager.cli.show_emu_config_summary"),
                patch("goldberg_manager.cli.questionary.confirm") as confirm,
                patch(
                    "goldberg_manager.cli.create_settings_safety_backup",
                    return_value=True,
                ),
                patch(
                    "goldberg_manager.cli.import_generated_achievements",
                    side_effect=lambda _summary, destination: make_import_result(
                        destination,
                        images_count=0,
                    ),
                ),
                patch("goldberg_manager.cli.console", test_console),
                patch("goldberg_manager.cli.pause") as pause,
                patch("goldberg_manager.cli.clear_screen"),
                patch("goldberg_manager.cli.render_header"),
            ):
                confirm.return_value.ask.return_value = True
                import_generated_achievements_menu(
                    config,
                    translations=load_translations("en"),
                )

        confirm.assert_called_once_with(
            "Import 12 achievements into Example Game?",
            default=True,
        )
        pause.assert_called_once_with("Press Enter to continue...")
        rendered = output.getvalue()
        for expected in (
            "Destination",
            "Import",
            "No installed achievements were found.",
            "Imported achievements",
            "None",
            "Import completed successfully!",
        ):
            self.assertIn(expected, rendered)

    def test_handled_import_errors_are_literal_without_false_success(self) -> None:
        translations = load_translations("en")

        for error in (
            EmuConfigError("failed [red]import[/red]"),
            OSError("unwritable [bold]destination[/bold]"),
            ValueError("invalid [cyan]result[/cyan]"),
        ):
            with self.subTest(error_type=type(error).__name__):
                with tempfile.TemporaryDirectory() as temp_directory:
                    config, game, summary = make_import_environment(
                        Path(temp_directory)
                    )
                    output = StringIO()
                    test_console = Console(
                        file=output,
                        width=240,
                        color_system=None,
                    )

                    with (
                        patch("goldberg_manager.cli.get_menu_game", return_value=game),
                        patch(
                            "goldberg_manager.cli.read_game_steam_settings",
                            return_value=SimpleNamespace(app_id=2353060),
                        ),
                        patch(
                            "goldberg_manager.cli.read_generated_emu_summary",
                            return_value=summary,
                        ),
                        patch("goldberg_manager.cli.show_emu_config_summary"),
                        patch("goldberg_manager.cli.questionary.confirm") as confirm,
                        patch(
                            "goldberg_manager.cli.create_settings_safety_backup",
                            return_value=True,
                        ),
                        patch(
                            "goldberg_manager.cli.import_generated_achievements",
                            side_effect=error,
                        ) as importer,
                        patch("goldberg_manager.cli.console", test_console),
                        patch("goldberg_manager.cli.pause") as pause,
                        patch("goldberg_manager.cli.clear_screen"),
                        patch("goldberg_manager.cli.render_header"),
                    ):
                        confirm.return_value.ask.return_value = True
                        import_generated_achievements_menu(
                            config,
                            translations=translations,
                        )

                importer.assert_called_once_with(
                    summary,
                    game.steam_api.parent / "steam_settings",
                )
                pause.assert_called_once_with("Press Enter to continue...")
                rendered = output.getvalue()
                self.assertIn("Failed to import achievements.", rendered)
                self.assertIn(str(error), rendered)
                self.assertNotIn("Import completed successfully!", rendered)

    def test_unexpected_import_error_propagates_without_success_or_pause(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            config, game, summary = make_import_environment(Path(temp_directory))
            error = LookupError("unexpected import writer")
            output = StringIO()
            test_console = Console(file=output, width=240, color_system=None)

            with (
                patch("goldberg_manager.cli.get_menu_game", return_value=game),
                patch(
                    "goldberg_manager.cli.read_game_steam_settings",
                    return_value=SimpleNamespace(app_id=2353060),
                ),
                patch(
                    "goldberg_manager.cli.read_generated_emu_summary",
                    return_value=summary,
                ),
                patch("goldberg_manager.cli.show_emu_config_summary"),
                patch("goldberg_manager.cli.questionary.confirm") as confirm,
                patch(
                    "goldberg_manager.cli.create_settings_safety_backup",
                    return_value=True,
                ),
                patch(
                    "goldberg_manager.cli.import_generated_achievements",
                    side_effect=error,
                ),
                patch("goldberg_manager.cli.console", test_console),
                patch("goldberg_manager.cli.pause") as pause,
                patch("goldberg_manager.cli.clear_screen"),
                patch("goldberg_manager.cli.render_header"),
                self.assertRaises(LookupError) as raised,
            ):
                confirm.return_value.ask.return_value = True
                import_generated_achievements_menu(
                    config,
                    translations=load_translations("en"),
                )

        self.assertIs(raised.exception, error)
        pause.assert_not_called()
        self.assertNotIn("Import completed successfully!", output.getvalue())

    def test_missing_post_import_file_suppresses_success(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            config, game, summary = make_import_environment(Path(temp_directory))
            output = StringIO()
            test_console = Console(file=output, width=240, color_system=None)

            with (
                patch("goldberg_manager.cli.get_menu_game", return_value=game),
                patch(
                    "goldberg_manager.cli.read_game_steam_settings",
                    return_value=SimpleNamespace(app_id=2353060),
                ),
                patch(
                    "goldberg_manager.cli.read_generated_emu_summary",
                    return_value=summary,
                ),
                patch("goldberg_manager.cli.show_emu_config_summary"),
                patch("goldberg_manager.cli.questionary.confirm") as confirm,
                patch(
                    "goldberg_manager.cli.create_settings_safety_backup",
                    return_value=True,
                ),
                patch(
                    "goldberg_manager.cli.import_generated_achievements",
                    side_effect=lambda _summary, destination: make_import_result(
                        destination,
                        write_achievements=False,
                    ),
                ),
                patch("goldberg_manager.cli.console", test_console),
                patch("goldberg_manager.cli.pause") as pause,
                patch("goldberg_manager.cli.clear_screen"),
                patch("goldberg_manager.cli.render_header"),
            ):
                confirm.return_value.ask.return_value = True
                import_generated_achievements_menu(
                    config,
                    translations=load_translations("en"),
                )

        pause.assert_called_once_with("Press Enter to continue...")
        rendered = output.getvalue()
        self.assertIn(
            "The import finished, but achievements.json was not found at the destination.",
            rendered,
        )
        self.assertNotIn("Import completed successfully!", rendered)

    def test_rich_like_translations_game_paths_and_results_are_literal(self) -> None:
        with tempfile.TemporaryDirectory(prefix="[bold]literal-root") as directory:
            config, game, summary = make_import_environment(Path(directory))
            game.name = "Game [red]literal[/red]"
            translations = RecordingTranslations(
                {
                    "Destino": "[cyan]literal destination[/cyan]",
                    "Achievements": "[blue]literal achievements[/blue]",
                    "Imagens": "[magenta]literal images[/magenta]",
                    "Importação": "[yellow]literal import[/yellow]",
                    "Nenhum achievement instalado foi encontrado.": (
                        "[green]literal empty state[/green]"
                    ),
                    "Jogo": "[bold]literal game label[/bold]",
                    "Nenhuma": "[italic]literal none[/italic]",
                    "Achievements importados": "[red]literal result title[/red]",
                    "Importação concluída com sucesso!": (
                        "[cyan]literal success[/cyan]"
                    ),
                    "Importar {count} achievements para {game}?": (
                        "[blue]Import {count} into {game}[/blue]"
                    ),
                    "Pressione Enter para continuar...": "Continue",
                }
            )
            output = StringIO()
            test_console = Console(file=output, width=300, color_system=None)

            with (
                patch("goldberg_manager.cli.get_menu_game", return_value=game),
                patch(
                    "goldberg_manager.cli.read_game_steam_settings",
                    return_value=SimpleNamespace(app_id=2353060),
                ),
                patch(
                    "goldberg_manager.cli.read_generated_emu_summary",
                    return_value=summary,
                ),
                patch("goldberg_manager.cli.show_emu_config_summary"),
                patch("goldberg_manager.cli.questionary.confirm") as confirm,
                patch(
                    "goldberg_manager.cli.create_settings_safety_backup",
                    return_value=True,
                ),
                patch(
                    "goldberg_manager.cli.import_generated_achievements",
                    side_effect=lambda _summary, destination: make_import_result(
                        destination,
                        images_count=0,
                    ),
                ),
                patch("goldberg_manager.cli.console", test_console),
                patch("goldberg_manager.cli.pause") as pause,
                patch("goldberg_manager.cli.clear_screen"),
                patch("goldberg_manager.cli.render_header"),
            ):
                confirm.return_value.ask.return_value = True
                import_generated_achievements_menu(
                    config,
                    game,
                    translations=translations,
                )

        confirm.assert_called_once_with(
            "[blue]Import 12 into Game [red]literal[/red][/blue]",
            default=True,
        )
        pause.assert_called_once_with("Continue")
        rendered = output.getvalue()
        for expected in (
            "[cyan]literal destination[/cyan]",
            "[blue]literal achievements[/blue]",
            "[magenta]literal images[/magenta]",
            "[yellow]literal import[/yellow]",
            "[green]literal empty state[/green]",
            "[bold]literal game label[/bold]",
            "Game [red]literal[/red]",
            "[italic]literal none[/italic]",
            "[red]literal result title[/red]",
            "[cyan]literal success[/cyan]",
            str(game.steam_api.parent / "steam_settings"),
        ):
            self.assertIn(expected, rendered)


class SettingsSafetyBackupI18nTests(unittest.TestCase):
    def test_standalone_default_loads_once_and_missing_settings_are_silent(
        self,
    ) -> None:
        translations = RecordingTranslations()

        with (
            patch(
                "goldberg_manager.cli.load_translations",
                return_value=translations,
            ) as loader,
            patch(
                "goldberg_manager.cli.get_steam_settings_directory",
                return_value=Path("/missing/steam_settings"),
            ),
            patch("goldberg_manager.cli.create_steam_settings_backup") as writer,
            patch("goldberg_manager.cli.console.print") as print_output,
            patch("goldberg_manager.cli.pause") as pause,
        ):
            result = create_settings_safety_backup(make_game())

        self.assertTrue(result)
        loader.assert_called_once_with()
        writer.assert_not_called()
        print_output.assert_not_called()
        pause.assert_not_called()

    def test_explicit_translations_bypass_loader_and_render_success_path_literally(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            settings_directory = Path(temp_directory) / "steam_settings"
            settings_directory.mkdir()
            (settings_directory / "steam_appid.txt").write_text(
                "2353060",
                encoding="utf-8",
            )
            snapshot = Path("/backup/[red]literal-snapshot[/red]")
            translations = RecordingTranslations(
                {"Backup de segurança criado:": "[bold]literal backup[/bold]"}
            )
            output = StringIO()
            test_console = Console(file=output, width=240, color_system=None)

            with (
                patch("goldberg_manager.cli.load_translations") as loader,
                patch(
                    "goldberg_manager.cli.get_steam_settings_directory",
                    return_value=settings_directory,
                ),
                patch(
                    "goldberg_manager.cli.create_steam_settings_backup",
                    return_value=snapshot,
                ) as writer,
                patch("goldberg_manager.cli.console", test_console),
                patch("goldberg_manager.cli.pause") as pause,
            ):
                result = create_settings_safety_backup(
                    make_game(),
                    translations=translations,
                )

        self.assertTrue(result)
        loader.assert_not_called()
        writer.assert_called_once()
        pause.assert_not_called()
        self.assertIn("[bold]literal backup[/bold]", output.getvalue())
        self.assertIn(str(snapshot), output.getvalue())

    def test_handled_writer_errors_translate_and_remain_literal(self) -> None:
        for error in (
            FileNotFoundError("missing [red]source[/red]"),
            OSError("unwritable [bold]backup[/bold]"),
            ValueError("invalid [cyan]settings[/cyan]"),
        ):
            with self.subTest(error_type=type(error).__name__):
                with tempfile.TemporaryDirectory() as temp_directory:
                    settings_directory = Path(temp_directory) / "steam_settings"
                    settings_directory.mkdir()
                    (settings_directory / "steam_appid.txt").write_text(
                        "2353060",
                        encoding="utf-8",
                    )
                    translations = RecordingTranslations(
                        {
                            "Não foi possível criar o backup de segurança:": (
                                "[red]literal failure frame[/red]"
                            ),
                            "A alteração foi cancelada para proteger a configuração atual.": (
                                "[yellow]literal cancellation[/yellow]"
                            ),
                            "Pressione Enter para continuar...": "Continue",
                        }
                    )
                    output = StringIO()
                    test_console = Console(
                        file=output,
                        width=240,
                        color_system=None,
                    )

                    with (
                        patch("goldberg_manager.cli.load_translations") as loader,
                        patch(
                            "goldberg_manager.cli.get_steam_settings_directory",
                            return_value=settings_directory,
                        ),
                        patch(
                            "goldberg_manager.cli.create_steam_settings_backup",
                            side_effect=error,
                        ) as writer,
                        patch("goldberg_manager.cli.console", test_console),
                        patch("goldberg_manager.cli.pause") as pause,
                    ):
                        result = create_settings_safety_backup(
                            make_game(),
                            translations=translations,
                        )

                self.assertFalse(result)
                loader.assert_not_called()
                writer.assert_called_once()
                pause.assert_called_once_with("Continue")
                rendered = output.getvalue()
                self.assertIn("[red]literal failure frame[/red]", rendered)
                self.assertIn(str(error), rendered)
                self.assertIn("[yellow]literal cancellation[/yellow]", rendered)

    def test_unexpected_writer_error_propagates_without_pause(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            settings_directory = Path(temp_directory) / "steam_settings"
            settings_directory.mkdir()
            (settings_directory / "steam_appid.txt").write_text(
                "2353060",
                encoding="utf-8",
            )
            error = RuntimeError("unexpected safety backup writer")

            with (
                patch(
                    "goldberg_manager.cli.get_steam_settings_directory",
                    return_value=settings_directory,
                ),
                patch(
                    "goldberg_manager.cli.create_steam_settings_backup",
                    side_effect=error,
                ),
                patch("goldberg_manager.cli.pause") as pause,
                self.assertRaises(RuntimeError) as raised,
            ):
                create_settings_safety_backup(
                    make_game(),
                    translations=RecordingTranslations(),
                )

        self.assertIs(raised.exception, error)
        pause.assert_not_called()


if __name__ == "__main__":
    unittest.main()
