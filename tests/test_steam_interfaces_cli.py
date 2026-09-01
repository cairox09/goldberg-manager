from __future__ import annotations

import unittest
from contextlib import ExitStack
from io import StringIO
from pathlib import Path
from unittest.mock import Mock, patch

from rich.console import Console
from rich.text import Text

from goldberg_manager.cli import generate_steam_interfaces_menu, start
from goldberg_manager.config import AppConfig, GoldbergConfig
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


def make_config() -> AppConfig:
    return AppConfig(
        goldberg=GoldbergConfig(
            interfaces_generator_x64=Path("/generators/generate_interfaces_x64.exe"),
            interfaces_generator_x86=Path("/generators/generate_interfaces_x86.exe"),
        )
    )


UNRELATED_MUTATIONS = (
    "apply_game_sentinel_repair",
    "backup_game",
    "create_steam_settings_backup",
    "generate_game_steam_settings",
    "import_generated_achievements",
    "restore_game_backup",
    "restore_steam_settings_backup",
    "run_generate_emu_config",
    "save_appid_search_cache",
    "save_config",
    "update_game_steam_appid",
    "update_user_setting",
)


class SteamInterfacesMenuTests(unittest.TestCase):
    def test_main_menu_stable_route_three_preserves_dispatch_call(self) -> None:
        config = AppConfig()

        with (
            patch("goldberg_manager.cli.load_config", return_value=config),
            patch(
                "goldberg_manager.cli.ask_menu_choice",
                side_effect=["3", "9"],
            ),
            patch(
                "goldberg_manager.cli.generate_steam_interfaces_menu"
            ) as interfaces_menu,
            patch("goldberg_manager.cli.clear_screen"),
            patch("goldberg_manager.cli.render_header"),
            patch("goldberg_manager.cli.render_menu"),
            patch("goldberg_manager.cli.console.print"),
        ):
            result = start()

        self.assertEqual(result, 0)
        interfaces_menu.assert_called_once_with(config)
        self.assertIs(interfaces_menu.call_args.args[0], config)
        self.assertEqual(interfaces_menu.call_args.kwargs, {})

    def test_default_loads_once_and_propagates_exact_translation_identity(
        self,
    ) -> None:
        config = make_config()
        translations = MappingTranslations()

        with (
            patch(
                "goldberg_manager.cli.load_translations",
                return_value=translations,
            ) as load_catalog,
            patch(
                "goldberg_manager.cli.get_menu_game",
                return_value=None,
            ) as get_game,
            patch("goldberg_manager.cli.has_backup") as has_backup,
            patch("goldberg_manager.cli.verify_backup") as verify_backup,
            patch("goldberg_manager.cli.questionary.confirm") as confirm,
            patch("goldberg_manager.cli.generate_game_steam_interfaces") as writer,
            patch("goldberg_manager.cli.pause") as pause,
            patch("goldberg_manager.cli.clear_screen"),
            patch("goldberg_manager.cli.render_header"),
        ):
            generate_steam_interfaces_menu(config)

        load_catalog.assert_called_once_with()
        get_game.assert_called_once_with(
            config,
            None,
            "Selecione o jogo para gerar steam_interfaces:",
            translations=translations,
        )
        self.assertIs(get_game.call_args.kwargs["translations"], translations)
        has_backup.assert_not_called()
        verify_backup.assert_not_called()
        confirm.assert_not_called()
        writer.assert_not_called()
        pause.assert_not_called()

    def test_explicit_translations_bypass_loader_and_preserve_supplied_game(
        self,
    ) -> None:
        config = make_config()
        game = make_game()
        translations = MappingTranslations()

        with (
            patch("goldberg_manager.cli.load_translations") as load_catalog,
            patch(
                "goldberg_manager.cli.get_menu_game",
                return_value=game,
            ) as get_game,
            patch("goldberg_manager.cli.has_backup", return_value=False),
            patch("goldberg_manager.cli.console.print"),
            patch("goldberg_manager.cli.pause"),
            patch("goldberg_manager.cli.clear_screen"),
            patch("goldberg_manager.cli.render_header"),
        ):
            generate_steam_interfaces_menu(
                config,
                game,
                translations=translations,
            )

        load_catalog.assert_not_called()
        get_game.assert_called_once_with(
            config,
            game,
            "Selecione o jogo para gerar steam_interfaces:",
            translations=translations,
        )
        self.assertIs(get_game.call_args.args[1], game)
        self.assertIs(get_game.call_args.kwargs["translations"], translations)

    def test_selection_cancellation_has_no_side_effects_or_leaf_output(self) -> None:
        config = make_config()

        with ExitStack() as stack:
            get_game = stack.enter_context(
                patch("goldberg_manager.cli.get_menu_game", return_value=None)
            )
            has_backup = stack.enter_context(patch("goldberg_manager.cli.has_backup"))
            verify_backup = stack.enter_context(
                patch("goldberg_manager.cli.verify_backup")
            )
            confirm = stack.enter_context(
                patch("goldberg_manager.cli.questionary.confirm")
            )
            writer = stack.enter_context(
                patch("goldberg_manager.cli.generate_game_steam_interfaces")
            )
            print_output = stack.enter_context(
                patch("goldberg_manager.cli.console.print")
            )
            pause = stack.enter_context(patch("goldberg_manager.cli.pause"))
            unrelated = [
                stack.enter_context(patch(f"goldberg_manager.cli.{name}"))
                for name in UNRELATED_MUTATIONS
            ]
            stack.enter_context(patch("goldberg_manager.cli.clear_screen"))
            stack.enter_context(patch("goldberg_manager.cli.render_header"))

            generate_steam_interfaces_menu(
                config,
                translations=MappingTranslations(),
            )

        get_game.assert_called_once()
        has_backup.assert_not_called()
        verify_backup.assert_not_called()
        confirm.assert_not_called()
        writer.assert_not_called()
        print_output.assert_not_called()
        pause.assert_not_called()
        for mutation in unrelated:
            mutation.assert_not_called()

    def test_missing_backup_stops_before_integrity_confirmation_and_writer(
        self,
    ) -> None:
        game = make_game()
        translations = MappingTranslations()
        output = StringIO()
        test_console = Console(file=output, width=200, color_system=None)
        events: list[str] = []

        with (
            patch(
                "goldberg_manager.cli.load_translations",
                return_value=translations,
            ) as load_catalog,
            patch(
                "goldberg_manager.cli.get_menu_game",
                side_effect=lambda *_args, **_kwargs: (
                    events.append("selection") or game
                ),
            ),
            patch(
                "goldberg_manager.cli.has_backup",
                side_effect=lambda supplied: events.append("has_backup") or False,
            ) as has_backup,
            patch("goldberg_manager.cli.verify_backup") as verify_backup,
            patch("goldberg_manager.cli.questionary.confirm") as confirm,
            patch("goldberg_manager.cli.generate_game_steam_interfaces") as writer,
            patch(
                "goldberg_manager.cli.pause",
                side_effect=lambda message: events.append(f"pause:{message}"),
            ) as pause,
            patch("goldberg_manager.cli.console", test_console),
            patch("goldberg_manager.cli.clear_screen"),
            patch("goldberg_manager.cli.render_header"),
        ):
            generate_steam_interfaces_menu(make_config())

        load_catalog.assert_called_once_with()
        has_backup.assert_called_once_with(game)
        self.assertIs(has_backup.call_args.args[0], game)
        verify_backup.assert_not_called()
        confirm.assert_not_called()
        writer.assert_not_called()
        pause.assert_called_once_with("Pressione Enter para continuar...")
        self.assertEqual(
            events,
            ["selection", "has_backup", "pause:Pressione Enter para continuar..."],
        )
        rendered = output.getvalue()
        self.assertIn(
            "Este jogo ainda não possui backup da Steam API original.", rendered
        )
        self.assertIn(
            "Crie primeiro um backup usando a opção Backup do jogo.", rendered
        )

    def test_missing_backup_guidance_bolds_literal_translated_option(self) -> None:
        game = make_game()
        cases = (
            (
                load_translations("en"),
                "First create a backup using the Back up game option.",
                "Back up game",
            ),
            (
                MappingTranslations(
                    {
                        "Crie primeiro um backup usando a opção Backup do jogo.": (
                            "Choose [red]literally[/red] [blue]Backup[/blue]."
                        ),
                        "Backup do jogo": "[blue]Backup[/blue]",
                    }
                ),
                "Choose [red]literally[/red] [blue]Backup[/blue].",
                "[blue]Backup[/blue]",
            ),
        )

        for translations, expected_text, expected_option in cases:
            with self.subTest(expected_option=expected_option), ExitStack() as stack:
                stack.enter_context(
                    patch("goldberg_manager.cli.get_menu_game", return_value=game)
                )
                stack.enter_context(
                    patch("goldberg_manager.cli.has_backup", return_value=False)
                )
                print_output = stack.enter_context(
                    patch("goldberg_manager.cli.console.print")
                )
                stack.enter_context(patch("goldberg_manager.cli.pause"))
                stack.enter_context(patch("goldberg_manager.cli.clear_screen"))
                stack.enter_context(patch("goldberg_manager.cli.render_header"))

                generate_steam_interfaces_menu(
                    make_config(),
                    translations=translations,
                )

            guidance = print_output.call_args_list[1].args[0]
            self.assertIsInstance(guidance, Text)
            self.assertEqual(guidance.plain, expected_text)
            option_start = expected_text.index(expected_option)
            self.assertEqual(len(guidance.spans), 1)
            self.assertEqual(guidance.spans[0].start, option_start)
            self.assertEqual(
                guidance.spans[0].end,
                option_start + len(expected_option),
            )
            self.assertEqual(guidance.spans[0].style, "bold")

    def test_explicit_english_translates_game_selection_prompt(self) -> None:
        game = make_game()
        translations = load_translations("en")

        with (
            patch("goldberg_manager.cli.load_translations") as load_catalog,
            patch(
                "goldberg_manager.cli.get_detected_games",
                return_value=[game],
            ),
            patch("goldberg_manager.cli.questionary.select") as select,
            patch("goldberg_manager.cli.has_backup") as has_backup,
            patch("goldberg_manager.cli.verify_backup") as verify_backup,
            patch("goldberg_manager.cli.generate_game_steam_interfaces") as writer,
            patch("goldberg_manager.cli.pause") as pause,
            patch("goldberg_manager.cli.clear_screen"),
            patch("goldberg_manager.cli.render_header"),
        ):
            select.return_value.ask.return_value = "back"
            generate_steam_interfaces_menu(
                make_config(),
                translations=translations,
            )

        load_catalog.assert_not_called()
        self.assertEqual(
            select.call_args.args[0],
            "Select the game to generate steam_interfaces:",
        )
        self.assertEqual(select.call_args.kwargs["choices"][-1].title, "Back")
        has_backup.assert_not_called()
        verify_backup.assert_not_called()
        writer.assert_not_called()
        pause.assert_not_called()

    def test_corrupt_backup_stops_before_confirmation_and_writer(self) -> None:
        game = make_game()
        output = StringIO()
        test_console = Console(file=output, width=200, color_system=None)
        events: list[str] = []

        with (
            patch(
                "goldberg_manager.cli.get_menu_game",
                side_effect=lambda *_args, **_kwargs: (
                    events.append("selection") or game
                ),
            ),
            patch(
                "goldberg_manager.cli.has_backup",
                side_effect=lambda supplied: events.append("has_backup") or True,
            ) as has_backup,
            patch(
                "goldberg_manager.cli.verify_backup",
                side_effect=lambda supplied: events.append("verify_backup") or False,
            ) as verify_backup,
            patch("goldberg_manager.cli.questionary.confirm") as confirm,
            patch("goldberg_manager.cli.generate_game_steam_interfaces") as writer,
            patch(
                "goldberg_manager.cli.pause",
                side_effect=lambda message: events.append(f"pause:{message}"),
            ) as pause,
            patch("goldberg_manager.cli.console", test_console),
            patch("goldberg_manager.cli.clear_screen"),
            patch("goldberg_manager.cli.render_header"),
        ):
            generate_steam_interfaces_menu(
                make_config(),
                translations=MappingTranslations(),
            )

        has_backup.assert_called_once_with(game)
        verify_backup.assert_called_once_with(game)
        confirm.assert_not_called()
        writer.assert_not_called()
        pause.assert_called_once_with("Pressione Enter para continuar...")
        self.assertEqual(
            events,
            [
                "selection",
                "has_backup",
                "verify_backup",
                "pause:Pressione Enter para continuar...",
            ],
        )
        self.assertIn(
            "O backup da Steam API não passou pela verificação de integridade.",
            output.getvalue(),
        )

    def test_false_and_none_confirmation_cancel_without_writer_or_pause(self) -> None:
        for answer in (False, None):
            with self.subTest(answer=answer), ExitStack() as stack:
                game = make_game(name="Game [bold]literal[/bold]")
                get_game = stack.enter_context(
                    patch("goldberg_manager.cli.get_menu_game", return_value=game)
                )
                has_backup = stack.enter_context(
                    patch("goldberg_manager.cli.has_backup", return_value=True)
                )
                verify_backup = stack.enter_context(
                    patch("goldberg_manager.cli.verify_backup", return_value=True)
                )
                confirm = stack.enter_context(
                    patch("goldberg_manager.cli.questionary.confirm")
                )
                writer = stack.enter_context(
                    patch("goldberg_manager.cli.generate_game_steam_interfaces")
                )
                print_output = stack.enter_context(
                    patch("goldberg_manager.cli.console.print")
                )
                pause = stack.enter_context(patch("goldberg_manager.cli.pause"))
                stack.enter_context(patch("goldberg_manager.cli.clear_screen"))
                stack.enter_context(patch("goldberg_manager.cli.render_header"))
                confirm.return_value.ask.return_value = answer

                generate_steam_interfaces_menu(
                    make_config(),
                    translations=MappingTranslations(),
                )

            get_game.assert_called_once()
            has_backup.assert_called_once_with(game)
            verify_backup.assert_called_once_with(game)
            confirm.assert_called_once_with(
                "Gerar steam_interfaces.txt para Game [bold]literal[/bold]?",
                default=True,
            )
            writer.assert_not_called()
            print_output.assert_not_called()
            pause.assert_not_called()

    def test_success_preserves_order_exact_writer_arguments_and_identity(self) -> None:
        config = make_config()
        game = make_game()
        output_path = Path("/games/Example/steam_settings/steam_interfaces.txt")
        translations = MappingTranslations()
        events: list[str] = []
        confirmation = Mock()

        def confirm_ask() -> bool:
            events.append("ask")
            return True

        confirmation.ask.side_effect = confirm_ask

        with (
            patch(
                "goldberg_manager.cli.get_menu_game",
                side_effect=lambda *_args, **_kwargs: (
                    events.append("selection") or game
                ),
            ) as get_game,
            patch(
                "goldberg_manager.cli.has_backup",
                side_effect=lambda supplied: events.append("has_backup") or True,
            ) as has_backup,
            patch(
                "goldberg_manager.cli.verify_backup",
                side_effect=lambda supplied: events.append("verify_backup") or True,
            ) as verify_backup,
            patch(
                "goldberg_manager.cli.questionary.confirm",
                side_effect=lambda *_args, **_kwargs: (
                    events.append("confirm") or confirmation
                ),
            ) as confirm,
            patch(
                "goldberg_manager.cli.generate_game_steam_interfaces",
                side_effect=lambda *_args, **_kwargs: (
                    events.append("writer") or output_path
                ),
            ) as writer,
            patch(
                "goldberg_manager.cli.console.print",
                side_effect=lambda value: events.append(f"print:{value.plain}"),
            ),
            patch(
                "goldberg_manager.cli.pause",
                side_effect=lambda message: events.append(f"pause:{message}"),
            ) as pause,
            patch("goldberg_manager.cli.clear_screen"),
            patch("goldberg_manager.cli.render_header"),
        ):
            generate_steam_interfaces_menu(
                config,
                game,
                translations=translations,
            )

        get_game.assert_called_once_with(
            config,
            game,
            "Selecione o jogo para gerar steam_interfaces:",
            translations=translations,
        )
        self.assertIs(get_game.call_args.args[1], game)
        self.assertIs(get_game.call_args.kwargs["translations"], translations)
        has_backup.assert_called_once_with(game)
        verify_backup.assert_called_once_with(game)
        confirm.assert_called_once_with(
            "Gerar steam_interfaces.txt para Example Game?",
            default=True,
        )
        writer.assert_called_once_with(
            game,
            config.goldberg.interfaces_generator_x64,
            config.goldberg.interfaces_generator_x86,
            command_prefix=("wine",),
        )
        self.assertIs(writer.call_args.args[0], game)
        pause.assert_called_once_with("Pressione Enter para continuar...")
        self.assertEqual(
            events,
            [
                "selection",
                "has_backup",
                "verify_backup",
                "confirm",
                "ask",
                "writer",
                "print:steam_interfaces.txt gerado com sucesso.",
                f"print:{output_path}",
                "pause:Pressione Enter para continuar...",
            ],
        )

    def test_handled_writer_exceptions_render_details_without_false_success(
        self,
    ) -> None:
        handled_errors = (
            FileNotFoundError("missing [bold]generator[/bold]"),
            RuntimeError("failed [red]process[/red]"),
            ValueError("invalid [cyan]backup[/cyan]"),
            OSError("unavailable [green]path[/green]"),
        )

        for error in handled_errors:
            with self.subTest(error_type=type(error).__name__):
                game = make_game()
                translations = MappingTranslations(
                    {
                        "Erro ao gerar steam_interfaces.txt:": (
                            "[blue]error literal[/blue]"
                        )
                    }
                )
                output = StringIO()
                test_console = Console(file=output, width=200, color_system=None)

                with (
                    patch("goldberg_manager.cli.get_menu_game", return_value=game),
                    patch("goldberg_manager.cli.has_backup", return_value=True),
                    patch("goldberg_manager.cli.verify_backup", return_value=True),
                    patch("goldberg_manager.cli.questionary.confirm") as confirm,
                    patch(
                        "goldberg_manager.cli.generate_game_steam_interfaces",
                        side_effect=error,
                    ) as writer,
                    patch("goldberg_manager.cli.console", test_console),
                    patch("goldberg_manager.cli.pause") as pause,
                    patch("goldberg_manager.cli.clear_screen"),
                    patch("goldberg_manager.cli.render_header"),
                ):
                    confirm.return_value.ask.return_value = True
                    generate_steam_interfaces_menu(
                        make_config(),
                        translations=translations,
                    )

                writer.assert_called_once()
                pause.assert_called_once_with("Pressione Enter para continuar...")
                rendered = output.getvalue()
                self.assertIn("[blue]error literal[/blue]", rendered)
                self.assertIn(str(error), rendered)
                self.assertNotIn("gerado com sucesso", rendered)

    def test_unexpected_writer_exception_propagates_without_success_or_pause(
        self,
    ) -> None:
        game = make_game()
        output = StringIO()
        test_console = Console(file=output, width=200, color_system=None)

        with (
            patch("goldberg_manager.cli.get_menu_game", return_value=game),
            patch("goldberg_manager.cli.has_backup", return_value=True),
            patch("goldberg_manager.cli.verify_backup", return_value=True),
            patch("goldberg_manager.cli.questionary.confirm") as confirm,
            patch(
                "goldberg_manager.cli.generate_game_steam_interfaces",
                side_effect=LookupError("unexpected [red]failure[/red]"),
            ) as writer,
            patch("goldberg_manager.cli.console", test_console),
            patch("goldberg_manager.cli.pause") as pause,
            patch("goldberg_manager.cli.clear_screen"),
            patch("goldberg_manager.cli.render_header"),
        ):
            confirm.return_value.ask.return_value = True

            with self.assertRaisesRegex(LookupError, "unexpected"):
                generate_steam_interfaces_menu(
                    make_config(),
                    translations=MappingTranslations(),
                )

        writer.assert_called_once()
        pause.assert_not_called()
        self.assertNotIn("gerado com sucesso", output.getvalue())
        self.assertNotIn("Erro ao gerar", output.getvalue())

    def test_explicit_english_translates_complete_leaf(self) -> None:
        game = make_game()
        translations = load_translations("en")

        cases = (
            (
                False,
                False,
                (
                    "This game does not yet have a backup of the original Steam API.",
                    "First create a backup using the Back up game option.",
                ),
            ),
            (
                True,
                False,
                ("The Steam API backup failed the integrity check.",),
            ),
        )

        for backup_exists, backup_valid, expected_messages in cases:
            with self.subTest(expected_messages=expected_messages):
                output = StringIO()
                test_console = Console(file=output, width=200, color_system=None)

                with (
                    patch("goldberg_manager.cli.load_translations") as loader,
                    patch(
                        "goldberg_manager.cli.get_menu_game", return_value=game
                    ) as get_game,
                    patch(
                        "goldberg_manager.cli.has_backup",
                        return_value=backup_exists,
                    ),
                    patch(
                        "goldberg_manager.cli.verify_backup",
                        return_value=backup_valid,
                    ),
                    patch("goldberg_manager.cli.console", test_console),
                    patch("goldberg_manager.cli.pause"),
                    patch("goldberg_manager.cli.clear_screen"),
                    patch("goldberg_manager.cli.render_header"),
                ):
                    generate_steam_interfaces_menu(
                        make_config(),
                        translations=translations,
                    )

                loader.assert_not_called()
                self.assertIs(get_game.call_args.kwargs["translations"], translations)
                for expected in expected_messages:
                    self.assertIn(expected, output.getvalue())

        output = StringIO()
        test_console = Console(file=output, width=200, color_system=None)
        output_path = Path("/output/steam_interfaces.txt")

        with (
            patch("goldberg_manager.cli.load_translations") as loader,
            patch("goldberg_manager.cli.get_menu_game", return_value=game),
            patch("goldberg_manager.cli.has_backup", return_value=True),
            patch("goldberg_manager.cli.verify_backup", return_value=True),
            patch("goldberg_manager.cli.questionary.confirm") as confirm,
            patch(
                "goldberg_manager.cli.generate_game_steam_interfaces",
                return_value=output_path,
            ),
            patch("goldberg_manager.cli.console", test_console),
            patch("goldberg_manager.cli.pause") as pause,
            patch("goldberg_manager.cli.clear_screen"),
            patch("goldberg_manager.cli.render_header"),
        ):
            confirm.return_value.ask.return_value = True
            generate_steam_interfaces_menu(
                make_config(),
                game,
                translations=translations,
            )

        loader.assert_not_called()
        confirm.assert_called_once_with(
            "Generate steam_interfaces.txt for Example Game?",
            default=True,
        )
        self.assertIn("steam_interfaces.txt generated successfully.", output.getvalue())
        pause.assert_called_once_with("Press Enter to continue...")

        output = StringIO()
        test_console = Console(file=output, width=200, color_system=None)

        with (
            patch("goldberg_manager.cli.load_translations") as loader,
            patch("goldberg_manager.cli.get_menu_game", return_value=game),
            patch("goldberg_manager.cli.has_backup", return_value=True),
            patch("goldberg_manager.cli.verify_backup", return_value=True),
            patch("goldberg_manager.cli.questionary.confirm") as confirm,
            patch(
                "goldberg_manager.cli.generate_game_steam_interfaces",
                side_effect=ValueError("literal detail"),
            ),
            patch("goldberg_manager.cli.console", test_console),
            patch("goldberg_manager.cli.pause") as pause,
            patch("goldberg_manager.cli.clear_screen"),
            patch("goldberg_manager.cli.render_header"),
        ):
            confirm.return_value.ask.return_value = True
            generate_steam_interfaces_menu(
                make_config(),
                game,
                translations=translations,
            )

        loader.assert_not_called()
        self.assertIn(
            "Error generating steam_interfaces.txt: literal detail",
            output.getvalue(),
        )
        self.assertNotIn("generated successfully", output.getvalue())
        pause.assert_called_once_with("Press Enter to continue...")

    def test_rich_like_translations_names_paths_and_errors_render_literally(
        self,
    ) -> None:
        game = make_game(name="Game [bold]name[/bold]")
        output_path = Path("/output/[blue]literal[/blue]/steam_interfaces.txt")
        translations = MappingTranslations(
            {
                "Gerar steam_interfaces.txt para {game}?": (
                    "[magenta]Generate[/magenta] for {game}?"
                ),
                "steam_interfaces.txt gerado com sucesso.": (
                    "[red]success literal[/red]"
                ),
                "Pressione Enter para continuar...": "[yellow]pause literal[/yellow]",
            }
        )
        output = StringIO()
        test_console = Console(file=output, width=300, color_system=None)

        with (
            patch("goldberg_manager.cli.get_menu_game", return_value=game),
            patch("goldberg_manager.cli.has_backup", return_value=True),
            patch("goldberg_manager.cli.verify_backup", return_value=True),
            patch("goldberg_manager.cli.questionary.confirm") as confirm,
            patch(
                "goldberg_manager.cli.generate_game_steam_interfaces",
                return_value=output_path,
            ),
            patch("goldberg_manager.cli.console", test_console),
            patch("goldberg_manager.cli.pause") as pause,
            patch("goldberg_manager.cli.clear_screen"),
            patch("goldberg_manager.cli.render_header"),
        ):
            confirm.return_value.ask.return_value = True
            generate_steam_interfaces_menu(
                make_config(),
                translations=translations,
            )

        self.assertEqual(
            confirm.call_args.args[0],
            "[magenta]Generate[/magenta] for Game [bold]name[/bold]?",
        )
        rendered = output.getvalue()
        self.assertIn("[red]success literal[/red]", rendered)
        self.assertIn(str(output_path), rendered)
        pause.assert_called_once_with("[yellow]pause literal[/yellow]")

    def test_unrelated_mutations_remain_isolated_on_success(self) -> None:
        game = make_game()

        with ExitStack() as stack:
            stack.enter_context(
                patch("goldberg_manager.cli.get_menu_game", return_value=game)
            )
            stack.enter_context(
                patch("goldberg_manager.cli.has_backup", return_value=True)
            )
            stack.enter_context(
                patch("goldberg_manager.cli.verify_backup", return_value=True)
            )
            confirm = stack.enter_context(
                patch("goldberg_manager.cli.questionary.confirm")
            )
            writer = stack.enter_context(
                patch(
                    "goldberg_manager.cli.generate_game_steam_interfaces",
                    return_value=Path("/output/steam_interfaces.txt"),
                )
            )
            unrelated = [
                stack.enter_context(patch(f"goldberg_manager.cli.{name}"))
                for name in UNRELATED_MUTATIONS
            ]
            stack.enter_context(patch("goldberg_manager.cli.console.print"))
            stack.enter_context(patch("goldberg_manager.cli.pause"))
            stack.enter_context(patch("goldberg_manager.cli.clear_screen"))
            stack.enter_context(patch("goldberg_manager.cli.render_header"))
            confirm.return_value.ask.return_value = True

            generate_steam_interfaces_menu(
                make_config(),
                translations=MappingTranslations(),
            )

        writer.assert_called_once()
        for mutation in unrelated:
            mutation.assert_not_called()


if __name__ == "__main__":
    unittest.main()
