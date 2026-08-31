from __future__ import annotations

import unittest
from contextlib import ExitStack
from io import StringIO
from pathlib import Path
from unittest.mock import Mock, patch

from rich.console import Console
from rich.text import Text

from goldberg_manager.cli import backup_game_menu, create_game_backup, start
from goldberg_manager.config import AppConfig, GamesConfig
from goldberg_manager.core.game import Game
from goldberg_manager.presentation.i18n import load_translations


class MappingTranslations:
    def __init__(self, messages: dict[str, str] | None = None) -> None:
        self.messages = messages or {}

    def gettext(self, message: str) -> str:
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
    "create_steam_settings_backup",
    "generate_game_steam_interfaces",
    "import_generated_achievements",
    "restore_game_backup",
    "restore_steam_settings_backup",
    "run_generate_emu_config",
    "save_appid_search_cache",
    "save_config",
    "update_game_steam_appid",
    "update_user_setting",
)


class SteamApiBackupMenuTests(unittest.TestCase):
    def test_main_menu_stable_route_five_dispatches_backup(self) -> None:
        config = AppConfig()

        with (
            patch("goldberg_manager.cli.load_config", return_value=config),
            patch(
                "goldberg_manager.cli.ask_menu_choice",
                side_effect=["5", "9"],
            ),
            patch("goldberg_manager.cli.backup_game_menu") as backup_menu,
            patch("goldberg_manager.cli.clear_screen"),
            patch("goldberg_manager.cli.render_header"),
            patch("goldberg_manager.cli.render_menu"),
            patch("goldberg_manager.cli.console.print"),
        ):
            result = start()

        self.assertEqual(result, 0)
        backup_menu.assert_called_once_with(config)
        self.assertIs(backup_menu.call_args.args[0], config)
        self.assertEqual(backup_menu.call_args.kwargs, {})

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
            patch("goldberg_manager.cli.create_game_backup") as create_backup,
            patch("goldberg_manager.cli.clear_screen"),
            patch("goldberg_manager.cli.render_header"),
        ):
            backup_game_menu(config)

        load_catalog.assert_called_once_with()
        get_games.assert_called_once_with(
            config,
            translations=translations,
        )
        select_game.assert_called_once_with(
            games,
            "Selecione o jogo para criar o backup:",
            translations=translations,
        )
        create_backup.assert_called_once_with(
            game,
            translations=translations,
        )
        self.assertIs(get_games.call_args.kwargs["translations"], translations)
        self.assertIs(select_game.call_args.kwargs["translations"], translations)
        self.assertIs(create_backup.call_args.kwargs["translations"], translations)

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
            patch("goldberg_manager.cli.create_game_backup") as create_backup,
            patch("goldberg_manager.cli.clear_screen"),
            patch("goldberg_manager.cli.render_header"),
        ):
            backup_game_menu(
                config,
                translations=translations,
            )

        load_catalog.assert_not_called()
        self.assertIs(get_games.call_args.kwargs["translations"], translations)
        self.assertIs(select_game.call_args.kwargs["translations"], translations)
        self.assertIs(create_backup.call_args.kwargs["translations"], translations)

    def test_detection_failure_does_not_select_or_create_backup(self) -> None:
        config = make_config()
        translations = MappingTranslations()

        with (
            patch(
                "goldberg_manager.cli.get_detected_games",
                return_value=None,
            ) as get_games,
            patch("goldberg_manager.cli.select_game") as select_game,
            patch("goldberg_manager.cli.create_game_backup") as create_backup,
            patch("goldberg_manager.cli.clear_screen"),
            patch("goldberg_manager.cli.render_header"),
        ):
            backup_game_menu(
                config,
                translations=translations,
            )

        get_games.assert_called_once_with(
            config,
            translations=translations,
        )
        select_game.assert_not_called()
        create_backup.assert_not_called()

    def test_selection_cancellation_does_not_create_backup(self) -> None:
        config = make_config(Path("/games"))
        games = [make_game()]
        translations = MappingTranslations()

        with (
            patch(
                "goldberg_manager.cli.get_detected_games",
                return_value=games,
            ),
            patch(
                "goldberg_manager.cli.select_game",
                return_value=None,
            ),
            patch("goldberg_manager.cli.create_game_backup") as create_backup,
            patch("goldberg_manager.cli.clear_screen"),
            patch("goldberg_manager.cli.render_header"),
        ):
            backup_game_menu(
                config,
                translations=translations,
            )

        create_backup.assert_not_called()

    def test_explicit_english_translates_selection_and_confirmation(self) -> None:
        game = make_game()

        with (
            patch(
                "goldberg_manager.cli.get_detected_games",
                return_value=[game],
            ),
            patch("goldberg_manager.cli.questionary.select") as select,
            patch("goldberg_manager.cli.questionary.confirm") as confirm,
            patch("goldberg_manager.cli.has_backup", return_value=False),
            patch("goldberg_manager.cli.backup_game") as writer,
            patch("goldberg_manager.cli.pause") as pause,
            patch("goldberg_manager.cli.clear_screen"),
            patch("goldberg_manager.cli.render_header"),
        ):
            select.return_value.ask.return_value = 0
            confirm.return_value.ask.return_value = False

            backup_game_menu(
                make_config(Path("/games")),
                translations=load_translations("en"),
            )

        self.assertEqual(select.call_args.args[0], "Select the game to back up:")
        self.assertEqual(select.call_args.kwargs["choices"][-1].title, "Back")
        confirm.assert_called_once_with(
            "Would you like to back up the original Steam API?",
            default=True,
        )
        writer.assert_not_called()
        pause.assert_not_called()


class CreateSteamApiBackupTests(unittest.TestCase):
    def test_existing_backup_precedes_confirmation_and_writer(self) -> None:
        game = make_game()
        translations = MappingTranslations()
        events: list[str] = []

        with (
            patch(
                "goldberg_manager.cli.has_backup",
                side_effect=lambda supplied_game: events.append("has_backup") or True,
            ) as has_backup,
            patch("goldberg_manager.cli.questionary.confirm") as confirm,
            patch("goldberg_manager.cli.backup_game") as writer,
            patch(
                "goldberg_manager.cli.console.print",
                side_effect=lambda value: events.append(f"print:{value.plain}"),
            ),
            patch(
                "goldberg_manager.cli.pause",
                side_effect=lambda message: events.append(f"pause:{message}"),
            ) as pause,
        ):
            create_game_backup(
                game,
                translations=translations,
            )

        has_backup.assert_called_once_with(game)
        self.assertIs(has_backup.call_args.args[0], game)
        confirm.assert_not_called()
        writer.assert_not_called()
        pause.assert_called_once_with("Pressione Enter para continuar...")
        self.assertEqual(
            events,
            [
                "has_backup",
                "print:Já existe um backup da Steam API para este jogo.",
                "pause:Pressione Enter para continuar...",
            ],
        )

    def test_existing_backup_renders_english_and_loads_no_catalog(self) -> None:
        output = StringIO()
        test_console = Console(file=output, width=200, color_system=None)

        with (
            patch("goldberg_manager.cli.load_translations") as load_catalog,
            patch("goldberg_manager.cli.has_backup", return_value=True),
            patch("goldberg_manager.cli.questionary.confirm") as confirm,
            patch("goldberg_manager.cli.backup_game") as writer,
            patch("goldberg_manager.cli.console", test_console),
            patch("goldberg_manager.cli.pause") as pause,
        ):
            create_game_backup(
                make_game(),
                translations=load_translations("en"),
            )

        load_catalog.assert_not_called()
        self.assertIn(
            "A Steam API backup already exists for this game.",
            output.getvalue(),
        )
        pause.assert_called_once_with("Press Enter to continue...")
        confirm.assert_not_called()
        writer.assert_not_called()

    def test_false_and_none_confirmation_cancel_without_mutation_or_pause(
        self,
    ) -> None:
        game = make_game()

        for answer in (False, None):
            with self.subTest(answer=answer):
                with (
                    patch("goldberg_manager.cli.has_backup", return_value=False),
                    patch("goldberg_manager.cli.questionary.confirm") as confirm,
                    patch("goldberg_manager.cli.backup_game") as writer,
                    patch("goldberg_manager.cli.console.print") as console_print,
                    patch("goldberg_manager.cli.pause") as pause,
                ):
                    confirm.return_value.ask.return_value = answer

                    create_game_backup(
                        game,
                        translations=MappingTranslations(),
                    )

                confirm.assert_called_once_with(
                    "Deseja criar um backup da Steam API original?",
                    default=True,
                )
                writer.assert_not_called()
                console_print.assert_not_called()
                pause.assert_not_called()

    def test_default_call_loads_once_and_preserves_success_sequence(self) -> None:
        game = make_game()
        backup_path = Path("/backups/Example/steam_api64.dll")
        translations = MappingTranslations()
        events: list[tuple[str, object]] = []
        answer = Mock()
        answer.ask.side_effect = lambda: events.append(("ask", None)) or True

        def record_has_backup(supplied_game):
            events.append(("has_backup", supplied_game))
            return False

        def record_confirm(message, *, default):
            events.append(("confirm", (message, default)))
            return answer

        def record_writer(supplied_game):
            events.append(("backup_game", supplied_game))
            return backup_path

        def record_print(value):
            self.assertIsInstance(value, Text)
            events.append(("print", value.plain))

        with ExitStack() as stack:
            load_catalog = stack.enter_context(
                patch(
                    "goldberg_manager.cli.load_translations",
                    return_value=translations,
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
                    "goldberg_manager.cli.backup_game",
                    side_effect=record_writer,
                )
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

            create_game_backup(game)

        load_catalog.assert_called_once_with()
        has_backup.assert_called_once_with(game)
        confirm.assert_called_once_with(
            "Deseja criar um backup da Steam API original?",
            default=True,
        )
        writer.assert_called_once_with(game)
        self.assertIs(writer.call_args.args[0], game)
        self.assertEqual(writer.call_args.kwargs, {})
        self.assertEqual(console_print.call_count, 2)
        pause.assert_called_once_with("Pressione Enter para continuar...")
        for mutation in unrelated:
            mutation.assert_not_called()
        self.assertEqual(
            events,
            [
                ("has_backup", game),
                (
                    "confirm",
                    ("Deseja criar um backup da Steam API original?", True),
                ),
                ("ask", None),
                ("backup_game", game),
                ("print", "Backup criado com sucesso."),
                ("print", str(backup_path)),
                ("pause", "Pressione Enter para continuar..."),
            ],
        )

    def test_explicit_english_translates_success_and_pause(self) -> None:
        output = StringIO()
        test_console = Console(file=output, width=200, color_system=None)
        game = make_game()
        backup_path = Path("/backups/Example/steam_api64.dll")

        with (
            patch("goldberg_manager.cli.has_backup", return_value=False),
            patch("goldberg_manager.cli.questionary.confirm") as confirm,
            patch(
                "goldberg_manager.cli.backup_game",
                return_value=backup_path,
            ) as writer,
            patch("goldberg_manager.cli.console", test_console),
            patch("goldberg_manager.cli.pause") as pause,
        ):
            confirm.return_value.ask.return_value = True

            create_game_backup(
                game,
                translations=load_translations("en"),
            )

        confirm.assert_called_once_with(
            "Would you like to back up the original Steam API?",
            default=True,
        )
        writer.assert_called_once_with(game)
        rendered = output.getvalue()
        self.assertIn("Backup created successfully.", rendered)
        self.assertIn(str(backup_path), rendered)
        pause.assert_called_once_with("Press Enter to continue...")

    def test_handled_writer_errors_are_translated_literal_and_pause_once(self) -> None:
        errors = (
            OSError("[green]literal OSError[/green]"),
            FileExistsError("[blue]literal existing backup[/blue]"),
        )

        for error in errors:
            with self.subTest(error=type(error).__name__):
                output = StringIO()
                test_console = Console(file=output, width=200, color_system=None)
                translations = MappingTranslations(
                    {
                        "Erro ao criar backup": "[bold]Translated error[/bold]",
                        "Pressione Enter para continuar...": "Translated pause",
                    }
                )

                with (
                    patch("goldberg_manager.cli.has_backup", return_value=False),
                    patch("goldberg_manager.cli.questionary.confirm") as confirm,
                    patch(
                        "goldberg_manager.cli.backup_game",
                        side_effect=error,
                    ) as writer,
                    patch("goldberg_manager.cli.console", test_console),
                    patch("goldberg_manager.cli.pause") as pause,
                ):
                    confirm.return_value.ask.return_value = True

                    create_game_backup(
                        make_game(),
                        translations=translations,
                    )

                writer.assert_called_once()
                rendered = output.getvalue()
                self.assertIn("[bold]Translated error[/bold]", rendered)
                self.assertIn(str(error), rendered)
                self.assertNotIn("Backup criado com sucesso.", rendered)
                pause.assert_called_once_with("Translated pause")

    def test_unexpected_writer_exception_propagates_without_success_or_pause(
        self,
    ) -> None:
        game = make_game()
        error = RuntimeError("unexpected")

        with (
            patch("goldberg_manager.cli.has_backup", return_value=False),
            patch("goldberg_manager.cli.questionary.confirm") as confirm,
            patch(
                "goldberg_manager.cli.backup_game",
                side_effect=error,
            ) as writer,
            patch("goldberg_manager.cli.console.print") as console_print,
            patch("goldberg_manager.cli.pause") as pause,
        ):
            confirm.return_value.ask.return_value = True

            with self.assertRaises(RuntimeError) as raised:
                create_game_backup(
                    game,
                    translations=MappingTranslations(),
                )

        self.assertIs(raised.exception, error)
        writer.assert_called_once_with(game)
        self.assertEqual(writer.call_args.kwargs, {})
        console_print.assert_not_called()
        pause.assert_not_called()

    def test_translated_and_dynamic_rich_content_renders_literally(self) -> None:
        output = StringIO()
        test_console = Console(file=output, width=200, color_system=None)
        backup_path = Path("/backups/[red]literal[/red]/steam_api64.dll")
        translations = MappingTranslations(
            {
                "Backup criado com sucesso.": "[green]literal success[/green]",
                "Pressione Enter para continuar...": "[cyan]literal pause[/cyan]",
            }
        )

        with (
            patch("goldberg_manager.cli.has_backup", return_value=False),
            patch("goldberg_manager.cli.questionary.confirm") as confirm,
            patch("goldberg_manager.cli.backup_game", return_value=backup_path),
            patch("goldberg_manager.cli.console", test_console),
            patch("goldberg_manager.cli.pause") as pause,
        ):
            confirm.return_value.ask.return_value = True

            create_game_backup(
                make_game(),
                translations=translations,
            )

        rendered = output.getvalue()
        self.assertIn("[green]literal success[/green]", rendered)
        self.assertIn(str(backup_path), rendered)
        pause.assert_called_once_with("[cyan]literal pause[/cyan]")


if __name__ == "__main__":
    unittest.main()
