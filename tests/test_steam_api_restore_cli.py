from __future__ import annotations

import unittest
from contextlib import ExitStack
from io import StringIO
from pathlib import Path
from unittest.mock import Mock, patch

from rich.console import Console
from rich.text import Text

from goldberg_manager.cli import restore_game_api, restore_game_menu, start
from goldberg_manager.config import AppConfig, GamesConfig
from goldberg_manager.core.game import Game
from goldberg_manager.presentation.i18n import load_translations


class MappingTranslations:
    def __init__(self, messages: dict[str, str] | None = None) -> None:
        self.messages = messages or {}
        self.calls: list[str] = []

    def gettext(self, message: str) -> str:
        self.calls.append(message)
        return self.messages.get(message, message)


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


def make_config(*directories: Path) -> AppConfig:
    return AppConfig(games=GamesConfig(directories=list(directories)))


UNRELATED_MUTATIONS = (
    "apply_game_sentinel_repair",
    "backup_game",
    "create_steam_settings_backup",
    "generate_game_steam_interfaces",
    "generate_game_steam_settings",
    "import_generated_achievements",
    "restore_steam_settings_backup",
    "run_generate_emu_config",
    "save_appid_search_cache",
    "save_config",
    "update_game_steam_appid",
    "update_user_setting",
)


class SteamApiRestoreMenuTests(unittest.TestCase):
    def test_main_menu_stable_route_six_preserves_start_call_contract(self) -> None:
        config = AppConfig()

        with (
            patch("goldberg_manager.cli.load_config", return_value=config),
            patch(
                "goldberg_manager.cli.ask_menu_choice",
                side_effect=["6", "9"],
            ),
            patch("goldberg_manager.cli.restore_game_menu") as restore_menu,
            patch("goldberg_manager.cli.clear_screen"),
            patch("goldberg_manager.cli.render_header"),
            patch("goldberg_manager.cli.render_menu"),
            patch("goldberg_manager.cli.console.print"),
        ):
            result = start()

        self.assertEqual(result, 0)
        restore_menu.assert_called_once_with(config)
        self.assertIs(restore_menu.call_args.args[0], config)
        self.assertEqual(restore_menu.call_args.kwargs, {})

    def test_default_wrapper_loads_once_and_propagates_exact_identity(self) -> None:
        config = make_config(Path("/games"))
        game = make_game()
        games = [game]
        translations = MappingTranslations()

        with (
            patch(
                "goldberg_manager.cli.load_translations",
                return_value=translations,
            ) as load_catalog,
            patch(
                "goldberg_manager.cli.get_detected_games",
                return_value=games,
            ) as get_games,
            patch(
                "goldberg_manager.cli.select_game",
                return_value=game,
            ) as select_game,
            patch("goldberg_manager.cli.restore_game_api") as restore,
            patch("goldberg_manager.cli.clear_screen"),
            patch("goldberg_manager.cli.render_header"),
        ):
            restore_game_menu(config)

        load_catalog.assert_called_once_with()
        get_games.assert_called_once_with(
            config,
            translations=translations,
        )
        select_game.assert_called_once_with(
            games,
            "Selecione o jogo que deseja restaurar:",
            translations=translations,
        )
        restore.assert_called_once_with(
            game,
            translations=translations,
        )
        self.assertIs(get_games.call_args.kwargs["translations"], translations)
        self.assertIs(select_game.call_args.kwargs["translations"], translations)
        self.assertIs(restore.call_args.args[0], game)
        self.assertIs(restore.call_args.kwargs["translations"], translations)

    def test_explicit_wrapper_translations_bypass_loader(self) -> None:
        config = make_config(Path("/games"))
        game = make_game()
        translations = MappingTranslations()

        with (
            patch("goldberg_manager.cli.load_translations") as load_catalog,
            patch(
                "goldberg_manager.cli.get_detected_games",
                return_value=[game],
            ) as get_games,
            patch(
                "goldberg_manager.cli.select_game",
                return_value=game,
            ) as select_game,
            patch("goldberg_manager.cli.restore_game_api") as restore,
            patch("goldberg_manager.cli.clear_screen"),
            patch("goldberg_manager.cli.render_header"),
        ):
            restore_game_menu(
                config,
                translations=translations,
            )

        load_catalog.assert_not_called()
        self.assertIs(get_games.call_args.kwargs["translations"], translations)
        self.assertIs(select_game.call_args.kwargs["translations"], translations)
        self.assertIs(restore.call_args.kwargs["translations"], translations)

    def test_detection_failure_does_not_select_or_restore(self) -> None:
        config = make_config()
        translations = MappingTranslations()

        with (
            patch(
                "goldberg_manager.cli.get_detected_games",
                return_value=None,
            ) as get_games,
            patch("goldberg_manager.cli.select_game") as select_game,
            patch("goldberg_manager.cli.restore_game_api") as restore,
            patch("goldberg_manager.cli.restore_game_backup") as writer,
            patch("goldberg_manager.cli.clear_screen"),
            patch("goldberg_manager.cli.render_header"),
        ):
            restore_game_menu(
                config,
                translations=translations,
            )

        get_games.assert_called_once_with(
            config,
            translations=translations,
        )
        select_game.assert_not_called()
        restore.assert_not_called()
        writer.assert_not_called()

    def test_selection_cancellation_does_not_restore(self) -> None:
        games = [make_game()]

        with (
            patch("goldberg_manager.cli.get_detected_games", return_value=games),
            patch("goldberg_manager.cli.select_game", return_value=None),
            patch("goldberg_manager.cli.restore_game_api") as restore,
            patch("goldberg_manager.cli.restore_game_backup") as writer,
            patch("goldberg_manager.cli.clear_screen"),
            patch("goldberg_manager.cli.render_header"),
        ):
            restore_game_menu(
                make_config(Path("/games")),
                translations=MappingTranslations(),
            )

        restore.assert_not_called()
        writer.assert_not_called()

    def test_english_selection_uses_stable_indices_and_exact_game_identity(
        self,
    ) -> None:
        translations = load_translations("en")
        games = [
            make_game(Path("/games/one"), name="Duplicate"),
            make_game(Path("/games/two"), name="Duplicate"),
        ]

        with (
            patch("goldberg_manager.cli.load_translations") as load_catalog,
            patch("goldberg_manager.cli.get_detected_games", return_value=games),
            patch("goldberg_manager.cli.questionary.select") as select,
            patch("goldberg_manager.cli.restore_game_api") as restore,
            patch("goldberg_manager.cli.clear_screen"),
            patch("goldberg_manager.cli.render_header"),
        ):
            select.return_value.ask.return_value = 1

            restore_game_menu(
                make_config(Path("/games")),
                translations=translations,
            )

        load_catalog.assert_not_called()
        self.assertEqual(
            select.call_args.args[0],
            "Select the game you want to restore:",
        )
        choices = select.call_args.kwargs["choices"]
        self.assertEqual(
            [choice.title for choice in choices],
            [
                "1 - Duplicate [64-bit]",
                "2 - Duplicate [64-bit]",
                "Back",
            ],
        )
        self.assertEqual([choice.value for choice in choices], [0, 1, "back"])
        restore.assert_called_once_with(
            games[1],
            translations=translations,
        )
        self.assertIs(restore.call_args.args[0], games[1])


class RestoreSteamApiTests(unittest.TestCase):
    def test_missing_backup_default_loads_once_warns_and_pauses_in_portuguese(
        self,
    ) -> None:
        output = StringIO()
        test_console = Console(file=output, width=200, color_system=None)
        game = make_game()
        translations = MappingTranslations()

        with (
            patch(
                "goldberg_manager.cli.load_translations",
                return_value=translations,
            ) as load_catalog,
            patch("goldberg_manager.cli.has_backup", return_value=False) as has_backup,
            patch("goldberg_manager.cli.questionary.confirm") as confirm,
            patch("goldberg_manager.cli.restore_game_backup") as writer,
            patch("goldberg_manager.cli.console", test_console),
            patch("goldberg_manager.cli.pause") as pause,
        ):
            restore_game_api(game)

        load_catalog.assert_called_once_with()
        has_backup.assert_called_once_with(game)
        self.assertIs(has_backup.call_args.args[0], game)
        self.assertIn(
            "Nenhum backup foi encontrado para este jogo.",
            output.getvalue(),
        )
        pause.assert_called_once_with("Pressione Enter para continuar...")
        confirm.assert_not_called()
        writer.assert_not_called()
        self.assertNotIn("restaurada com sucesso", output.getvalue())

    def test_missing_backup_explicit_english_bypasses_loader(self) -> None:
        output = StringIO()
        test_console = Console(file=output, width=200, color_system=None)
        translations = load_translations("en")

        with (
            patch("goldberg_manager.cli.load_translations") as load_catalog,
            patch("goldberg_manager.cli.has_backup", return_value=False),
            patch("goldberg_manager.cli.questionary.confirm") as confirm,
            patch("goldberg_manager.cli.restore_game_backup") as writer,
            patch("goldberg_manager.cli.console", test_console),
            patch("goldberg_manager.cli.pause") as pause,
        ):
            restore_game_api(
                make_game(),
                translations=translations,
            )

        load_catalog.assert_not_called()
        self.assertIn("No backup was found for this game.", output.getvalue())
        pause.assert_called_once_with("Press Enter to continue...")
        confirm.assert_not_called()
        writer.assert_not_called()

    def test_default_success_preserves_order_writer_contract_and_isolation(
        self,
    ) -> None:
        game = make_game()
        translations = MappingTranslations()
        events: list[tuple[str, object]] = []
        answer = Mock()
        answer.ask.side_effect = lambda: events.append(("ask", None)) or True

        def record_has_backup(supplied_game):
            events.append(("has_backup", supplied_game))
            return True

        def record_confirm(message, *, default):
            events.append(("confirm", (message, default)))
            return answer

        def record_writer(supplied_game):
            events.append(("restore_game_backup", supplied_game))

        def record_print(value):
            self.assertIsInstance(value, Text)
            events.append(("print", value.plain))

        with ExitStack() as stack:
            load_catalog = stack.enter_context(
                patch(
                    "goldberg_manager.cli.load_translations",
                    side_effect=lambda: events.append(("load", None)) or translations,
                )
            )
            has_backup = stack.enter_context(
                patch(
                    "goldberg_manager.cli.has_backup",
                    side_effect=record_has_backup,
                )
            )
            confirm = stack.enter_context(
                patch(
                    "goldberg_manager.cli.questionary.confirm",
                    side_effect=record_confirm,
                )
            )
            writer = stack.enter_context(
                patch(
                    "goldberg_manager.cli.restore_game_backup",
                    side_effect=record_writer,
                )
            )
            verify_backup = stack.enter_context(
                patch("goldberg_manager.cli.verify_backup")
            )
            console_print = stack.enter_context(
                patch(
                    "goldberg_manager.cli.console.print",
                    side_effect=record_print,
                )
            )
            pause = stack.enter_context(
                patch(
                    "goldberg_manager.cli.pause",
                    side_effect=lambda message: events.append(("pause", message)),
                )
            )
            unrelated = [
                stack.enter_context(patch(f"goldberg_manager.cli.{name}"))
                for name in UNRELATED_MUTATIONS
            ]

            restore_game_api(game)

        load_catalog.assert_called_once_with()
        has_backup.assert_called_once_with(game)
        confirm.assert_called_once_with(
            "Restaurar a Steam API original?",
            default=False,
        )
        writer.assert_called_once_with(game)
        self.assertIs(writer.call_args.args[0], game)
        self.assertEqual(writer.call_args.kwargs, {})
        verify_backup.assert_not_called()
        console_print.assert_called_once()
        pause.assert_called_once_with("Pressione Enter para continuar...")
        for mutation in unrelated:
            mutation.assert_not_called()
        self.assertEqual(
            events,
            [
                ("load", None),
                ("has_backup", game),
                (
                    "confirm",
                    ("Restaurar a Steam API original?", False),
                ),
                ("ask", None),
                ("restore_game_backup", game),
                (
                    "print",
                    "Steam API original restaurada com sucesso.",
                ),
                ("pause", "Pressione Enter para continuar..."),
            ],
        )

    def test_explicit_english_success_bypasses_loader(self) -> None:
        output = StringIO()
        test_console = Console(file=output, width=200, color_system=None)
        game = make_game(name="Technical Steam API Game")
        translations = load_translations("en")

        with (
            patch("goldberg_manager.cli.load_translations") as load_catalog,
            patch("goldberg_manager.cli.has_backup", return_value=True),
            patch("goldberg_manager.cli.questionary.confirm") as confirm,
            patch("goldberg_manager.cli.restore_game_backup") as writer,
            patch("goldberg_manager.cli.console", test_console),
            patch("goldberg_manager.cli.pause") as pause,
        ):
            confirm.return_value.ask.return_value = True

            restore_game_api(
                game,
                translations=translations,
            )

        load_catalog.assert_not_called()
        confirm.assert_called_once_with(
            "Restore the original Steam API?",
            default=False,
        )
        writer.assert_called_once_with(game)
        self.assertIs(writer.call_args.args[0], game)
        self.assertEqual(writer.call_args.kwargs, {})
        self.assertIn(
            "Original Steam API restored successfully.",
            output.getvalue(),
        )
        pause.assert_called_once_with("Press Enter to continue...")

    def test_false_and_none_confirmation_cancel_without_output_or_pause(
        self,
    ) -> None:
        game = make_game()

        for answer in (False, None):
            with self.subTest(answer=answer):
                with (
                    patch("goldberg_manager.cli.has_backup", return_value=True),
                    patch("goldberg_manager.cli.questionary.confirm") as confirm,
                    patch("goldberg_manager.cli.restore_game_backup") as writer,
                    patch("goldberg_manager.cli.verify_backup") as verify_backup,
                    patch("goldberg_manager.cli.console.print") as console_print,
                    patch("goldberg_manager.cli.pause") as pause,
                ):
                    confirm.return_value.ask.return_value = answer

                    restore_game_api(
                        game,
                        translations=MappingTranslations(),
                    )

                confirm.assert_called_once_with(
                    "Restaurar a Steam API original?",
                    default=False,
                )
                writer.assert_not_called()
                verify_backup.assert_not_called()
                console_print.assert_not_called()
                pause.assert_not_called()

    def test_default_portuguese_oserror_is_literal_and_has_no_false_success(
        self,
    ) -> None:
        output = StringIO()
        test_console = Console(file=output, width=200, color_system=None)
        error = OSError("falha técnica")
        translations = MappingTranslations()

        with (
            patch(
                "goldberg_manager.cli.load_translations",
                return_value=translations,
            ) as load_catalog,
            patch("goldberg_manager.cli.has_backup", return_value=True),
            patch("goldberg_manager.cli.questionary.confirm") as confirm,
            patch(
                "goldberg_manager.cli.restore_game_backup",
                side_effect=error,
            ) as writer,
            patch("goldberg_manager.cli.console", test_console),
            patch("goldberg_manager.cli.pause") as pause,
        ):
            confirm.return_value.ask.return_value = True
            restore_game_api(make_game())

        load_catalog.assert_called_once_with()
        writer.assert_called_once()
        self.assertIn("Erro ao restaurar backup: falha técnica", output.getvalue())
        self.assertNotIn("restaurada com sucesso", output.getvalue())
        pause.assert_called_once_with("Pressione Enter para continuar...")

    def test_english_handles_oserror_and_valueerror_with_literal_details(
        self,
    ) -> None:
        translations = load_translations("en")
        errors = (
            OSError("/games/steam_api64.dll"),
            ValueError("SHA-256 mismatch"),
        )

        for error in errors:
            with self.subTest(error=type(error).__name__):
                output = StringIO()
                test_console = Console(file=output, width=200, color_system=None)

                with (
                    patch("goldberg_manager.cli.load_translations") as load_catalog,
                    patch("goldberg_manager.cli.has_backup", return_value=True),
                    patch("goldberg_manager.cli.questionary.confirm") as confirm,
                    patch(
                        "goldberg_manager.cli.restore_game_backup",
                        side_effect=error,
                    ) as writer,
                    patch("goldberg_manager.cli.console", test_console),
                    patch("goldberg_manager.cli.pause") as pause,
                ):
                    confirm.return_value.ask.return_value = True
                    restore_game_api(
                        make_game(),
                        translations=translations,
                    )

                load_catalog.assert_not_called()
                writer.assert_called_once()
                self.assertIn("Error restoring backup: ", output.getvalue())
                self.assertIn(str(error), output.getvalue())
                self.assertNotIn(
                    "Original Steam API restored successfully.",
                    output.getvalue(),
                )
                pause.assert_called_once_with("Press Enter to continue...")

    def test_unexpected_writer_exception_propagates_without_output_or_pause(
        self,
    ) -> None:
        error = RuntimeError("unexpected")

        with (
            patch("goldberg_manager.cli.has_backup", return_value=True),
            patch("goldberg_manager.cli.questionary.confirm") as confirm,
            patch(
                "goldberg_manager.cli.restore_game_backup",
                side_effect=error,
            ) as writer,
            patch("goldberg_manager.cli.console.print") as console_print,
            patch("goldberg_manager.cli.pause") as pause,
        ):
            confirm.return_value.ask.return_value = True

            with self.assertRaises(RuntimeError) as raised:
                restore_game_api(
                    make_game(),
                    translations=MappingTranslations(),
                )

        self.assertIs(raised.exception, error)
        writer.assert_called_once()
        console_print.assert_not_called()
        pause.assert_not_called()

    def test_pre_writer_exceptions_preserve_existing_propagation_boundaries(
        self,
    ) -> None:
        game = make_game()
        translations = MappingTranslations()

        with (
            patch(
                "goldberg_manager.cli.has_backup",
                side_effect=RuntimeError("guard"),
            ),
            patch("goldberg_manager.cli.questionary.confirm") as confirm,
            patch("goldberg_manager.cli.restore_game_backup") as writer,
            patch("goldberg_manager.cli.console.print") as console_print,
            patch("goldberg_manager.cli.pause") as pause,
            self.assertRaisesRegex(RuntimeError, "guard"),
        ):
            restore_game_api(game, translations=translations)

        confirm.assert_not_called()
        writer.assert_not_called()
        console_print.assert_not_called()
        pause.assert_not_called()

        with (
            patch("goldberg_manager.cli.has_backup", return_value=True),
            patch(
                "goldberg_manager.cli.questionary.confirm",
                side_effect=RuntimeError("construct"),
            ),
            patch("goldberg_manager.cli.restore_game_backup") as writer,
            patch("goldberg_manager.cli.console.print") as console_print,
            patch("goldberg_manager.cli.pause") as pause,
            self.assertRaisesRegex(RuntimeError, "construct"),
        ):
            restore_game_api(game, translations=translations)

        writer.assert_not_called()
        console_print.assert_not_called()
        pause.assert_not_called()

        with (
            patch("goldberg_manager.cli.has_backup", return_value=True),
            patch("goldberg_manager.cli.questionary.confirm") as confirm,
            patch("goldberg_manager.cli.restore_game_backup") as writer,
            patch("goldberg_manager.cli.console.print") as console_print,
            patch("goldberg_manager.cli.pause") as pause,
        ):
            confirm.return_value.ask.side_effect = RuntimeError("ask")

            with self.assertRaisesRegex(RuntimeError, "ask"):
                restore_game_api(game, translations=translations)

        writer.assert_not_called()
        console_print.assert_not_called()
        pause.assert_not_called()

    def test_rich_like_missing_backup_translation_renders_literally(self) -> None:
        output = StringIO()
        test_console = Console(file=output, width=200, color_system=None)
        translations = MappingTranslations(
            {
                "Nenhum backup foi encontrado para este jogo.": (
                    "[red]literal warning[/red]"
                ),
                "Pressione Enter para continuar...": "[cyan]literal pause[/cyan]",
            }
        )

        with (
            patch("goldberg_manager.cli.has_backup", return_value=False),
            patch("goldberg_manager.cli.console", test_console),
            patch("goldberg_manager.cli.pause") as pause,
        ):
            restore_game_api(
                make_game(),
                translations=translations,
            )

        self.assertIn("[red]literal warning[/red]", output.getvalue())
        pause.assert_called_once_with("[cyan]literal pause[/cyan]")

    def test_rich_like_confirmation_and_success_remain_literal(self) -> None:
        output = StringIO()
        test_console = Console(file=output, width=200, color_system=None)
        translations = MappingTranslations(
            {
                "Restaurar a Steam API original?": "[blue]literal consent[/blue]",
                "Steam API original restaurada com sucesso.": (
                    "[green]literal success[/green]"
                ),
                "Pressione Enter para continuar...": "[cyan]literal pause[/cyan]",
            }
        )

        with (
            patch("goldberg_manager.cli.has_backup", return_value=True),
            patch("goldberg_manager.cli.questionary.confirm") as confirm,
            patch("goldberg_manager.cli.restore_game_backup") as writer,
            patch("goldberg_manager.cli.console", test_console),
            patch("goldberg_manager.cli.pause") as pause,
        ):
            confirm.return_value.ask.return_value = True
            restore_game_api(
                make_game(),
                translations=translations,
            )

        confirm.assert_called_once_with(
            "[blue]literal consent[/blue]",
            default=False,
        )
        writer.assert_called_once()
        self.assertIn("[green]literal success[/green]", output.getvalue())
        pause.assert_called_once_with("[cyan]literal pause[/cyan]")

    def test_rich_like_error_translation_and_exception_render_literally(self) -> None:
        output = StringIO()
        test_console = Console(file=output, width=200, color_system=None)
        error = OSError("[yellow]literal exception[/yellow]")
        translations = MappingTranslations(
            {
                "Erro ao restaurar backup": "[red]literal error[/red]",
            }
        )

        with (
            patch("goldberg_manager.cli.has_backup", return_value=True),
            patch("goldberg_manager.cli.questionary.confirm") as confirm,
            patch(
                "goldberg_manager.cli.restore_game_backup",
                side_effect=error,
            ),
            patch("goldberg_manager.cli.console", test_console),
            patch("goldberg_manager.cli.pause"),
        ):
            confirm.return_value.ask.return_value = True
            restore_game_api(
                make_game(),
                translations=translations,
            )

        rendered = output.getvalue()
        self.assertIn("[red]literal error[/red]", rendered)
        self.assertIn("[yellow]literal exception[/yellow]", rendered)


if __name__ == "__main__":
    unittest.main()
