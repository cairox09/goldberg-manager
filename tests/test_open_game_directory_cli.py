from __future__ import annotations

import subprocess
import unittest
from contextlib import ExitStack
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from rich.console import Console

from goldberg_manager.cli import get_detected_games, open_game_directory_menu
from goldberg_manager.config import AppConfig, GamesConfig
from goldberg_manager.core.game import Game
from goldberg_manager.presentation.i18n import load_translations


class MappingTranslations:
    def __init__(self, messages: dict[str, str] | None = None) -> None:
        self.messages = messages or {}

    def gettext(self, message: str) -> str:
        return self.messages.get(message, message)


def make_game(root: Path = Path("/games/Example")) -> Game:
    return Game(
        name="Example Game",
        root_directory=root,
        executable=root / "Game.exe",
        steam_api=root / "steam_api64.dll",
        steam_api_relative_path=Path("steam_api64.dll"),
        architecture="64-bit",
        source_directory=root.parent,
    )


def make_config(*directories: Path) -> AppConfig:
    return AppConfig(games=GamesConfig(directories=list(directories)))


MUTATION_FUNCTIONS = (
    "apply_game_sentinel_repair",
    "backup_game",
    "create_steam_settings_backup",
    "generate_game_steam_interfaces",
    "import_generated_achievements",
    "restore_game_backup",
    "restore_steam_settings_backup",
    "run_generate_emu_config",
    "save_appid_search_cache",
    "save_config",
    "search_game_on_steam",
    "update_game_steam_appid",
    "update_user_setting",
)


class OpenGameDirectoryCliTests(unittest.TestCase):
    def test_default_call_loads_once_propagates_identity_and_opens_exact_root(
        self,
    ) -> None:
        root = Path("/games/[Exact] Example")
        game = make_game(root)
        games = [game]
        config = make_config(Path("/games"))
        translations = MappingTranslations()

        with ExitStack() as stack:
            load_translations = stack.enter_context(
                patch(
                    "goldberg_manager.cli.load_translations",
                    return_value=translations,
                )
            )
            get_games = stack.enter_context(
                patch(
                    "goldberg_manager.cli.get_detected_games",
                    return_value=games,
                )
            )
            select_game = stack.enter_context(
                patch("goldberg_manager.cli.select_game", return_value=game)
            )
            run = stack.enter_context(patch("goldberg_manager.cli.subprocess.run"))
            pause = stack.enter_context(patch("goldberg_manager.cli.pause"))
            console_print = stack.enter_context(
                patch("goldberg_manager.cli.console.print")
            )
            stack.enter_context(patch("goldberg_manager.cli.clear_screen"))
            stack.enter_context(patch("goldberg_manager.cli.render_header"))
            mutations = [
                stack.enter_context(patch(f"goldberg_manager.cli.{name}"))
                for name in MUTATION_FUNCTIONS
            ]
            path_mkdir = stack.enter_context(patch.object(Path, "mkdir"))
            path_write_text = stack.enter_context(patch.object(Path, "write_text"))
            path_write_bytes = stack.enter_context(patch.object(Path, "write_bytes"))

            open_game_directory_menu(config)

        load_translations.assert_called_once_with()
        get_games.assert_called_once_with(
            config,
            translations=translations,
        )
        select_game.assert_called_once_with(
            games,
            "Selecione o jogo cuja pasta deseja abrir:",
            translations=translations,
        )
        self.assertIs(select_game.return_value, game)
        run.assert_called_once_with(
            ["xdg-open", str(root)],
            check=True,
        )
        self.assertEqual(run.call_args.kwargs, {"check": True})
        pause.assert_not_called()
        console_print.assert_not_called()
        path_mkdir.assert_not_called()
        path_write_text.assert_not_called()
        path_write_bytes.assert_not_called()
        for mutation in mutations:
            mutation.assert_not_called()

    def test_explicit_translations_bypass_loader_and_reach_both_helpers(self) -> None:
        game = make_game()
        games = [game]
        config = make_config(Path("/games"))
        translations = MappingTranslations()

        with (
            patch("goldberg_manager.cli.load_translations") as load_translations,
            patch(
                "goldberg_manager.cli.get_detected_games",
                return_value=games,
            ) as get_games,
            patch(
                "goldberg_manager.cli.select_game",
                return_value=game,
            ) as select_game,
            patch("goldberg_manager.cli.subprocess.run"),
            patch("goldberg_manager.cli.clear_screen"),
            patch("goldberg_manager.cli.render_header"),
        ):
            open_game_directory_menu(
                config,
                translations=translations,
            )

        load_translations.assert_not_called()
        self.assertIs(get_games.call_args.kwargs["translations"], translations)
        self.assertIs(select_game.call_args.kwargs["translations"], translations)

    def test_explicit_english_translates_open_prompt(self) -> None:
        game = make_game()

        with (
            patch(
                "goldberg_manager.cli.get_detected_games",
                return_value=[game],
            ),
            patch("goldberg_manager.cli.questionary.select") as select,
            patch("goldberg_manager.cli.subprocess.run"),
            patch("goldberg_manager.cli.clear_screen"),
            patch("goldberg_manager.cli.render_header"),
        ):
            select.return_value.ask.return_value = 0
            open_game_directory_menu(
                make_config(Path("/games")),
                translations=load_translations("en"),
            )

        self.assertEqual(
            select.call_args.args[0],
            "Select the game whose folder you want to open:",
        )
        self.assertEqual(select.call_args.kwargs["choices"][-1].title, "Back")

    def test_selection_cancellation_does_not_launch_pause_or_print(self) -> None:
        config = make_config(Path("/games"))
        translations = MappingTranslations()

        with (
            patch(
                "goldberg_manager.cli.get_detected_games",
                return_value=[make_game()],
            ),
            patch("goldberg_manager.cli.select_game", return_value=None),
            patch("goldberg_manager.cli.subprocess.run") as run,
            patch("goldberg_manager.cli.pause") as pause,
            patch("goldberg_manager.cli.console.print") as console_print,
            patch("goldberg_manager.cli.clear_screen"),
            patch("goldberg_manager.cli.render_header"),
        ):
            open_game_directory_menu(
                config,
                translations=translations,
            )

        run.assert_not_called()
        pause.assert_not_called()
        console_print.assert_not_called()

    def test_handled_subprocess_errors_are_literal_translated_and_pause_once(
        self,
    ) -> None:
        errors = (
            OSError("[green]literal OSError[/green]"),
            FileNotFoundError("[blue]literal missing executable[/blue]"),
            subprocess.CalledProcessError(7, "xdg-open", stderr="[bad]"),
        )

        for error in errors:
            with self.subTest(error=type(error).__name__):
                output = StringIO()
                test_console = Console(file=output, width=200, color_system=None)
                translations = MappingTranslations(
                    {
                        "Não foi possível abrir a pasta do jogo:": (
                            "[red]Could not open the game folder:[/red]"
                        ),
                        "Pressione Enter para continuar...": "Translated pause",
                    }
                )
                game = make_game()

                with (
                    patch(
                        "goldberg_manager.cli.get_detected_games",
                        return_value=[game],
                    ),
                    patch("goldberg_manager.cli.select_game", return_value=game),
                    patch(
                        "goldberg_manager.cli.subprocess.run",
                        side_effect=error,
                    ) as run,
                    patch("goldberg_manager.cli.pause") as pause,
                    patch("goldberg_manager.cli.console", test_console),
                    patch("goldberg_manager.cli.clear_screen"),
                    patch("goldberg_manager.cli.render_header"),
                ):
                    open_game_directory_menu(
                        make_config(Path("/games")),
                        translations=translations,
                    )

                run.assert_called_once_with(
                    ["xdg-open", str(game.root_directory)],
                    check=True,
                )
                pause.assert_called_once_with("Translated pause")
                self.assertIn(
                    "[red]Could not open the game folder:[/red]",
                    output.getvalue(),
                )
                self.assertIn(str(error), output.getvalue())

    def test_unexpected_subprocess_error_propagates_without_pause(self) -> None:
        game = make_game()
        error = RuntimeError("unexpected")

        with (
            patch(
                "goldberg_manager.cli.get_detected_games",
                return_value=[game],
            ),
            patch("goldberg_manager.cli.select_game", return_value=game),
            patch("goldberg_manager.cli.subprocess.run", side_effect=error),
            patch("goldberg_manager.cli.pause") as pause,
            patch("goldberg_manager.cli.clear_screen"),
            patch("goldberg_manager.cli.render_header"),
            self.assertRaises(RuntimeError) as raised,
        ):
            open_game_directory_menu(
                make_config(Path("/games")),
                translations=MappingTranslations(),
            )

        self.assertIs(raised.exception, error)
        pause.assert_not_called()


class DetectedGamesI18nTests(unittest.TestCase):
    def test_no_directories_preserves_portuguese_default_and_loads_once(self) -> None:
        output = StringIO()
        test_console = Console(file=output, width=120, color_system=None)
        translations = MappingTranslations()

        with (
            patch(
                "goldberg_manager.cli.load_translations",
                return_value=translations,
            ) as load_translations,
            patch("goldberg_manager.cli.detect_games") as detect_games,
            patch("goldberg_manager.cli.pause") as pause,
            patch("goldberg_manager.cli.console", test_console),
        ):
            games = get_detected_games(make_config())

        self.assertIsNone(games)
        load_translations.assert_called_once_with()
        detect_games.assert_not_called()
        pause.assert_called_once_with("Pressione Enter para continuar...")
        self.assertIn(
            "Nenhum diretório de jogos foi configurado.",
            output.getvalue(),
        )
        self.assertIn("Adicione um diretório em Configurações.", output.getvalue())

    def test_no_directories_renders_explicit_english_catalog(self) -> None:
        output = StringIO()
        test_console = Console(file=output, width=120, color_system=None)

        with (
            patch("goldberg_manager.cli.pause") as pause,
            patch("goldberg_manager.cli.console", test_console),
        ):
            games = get_detected_games(
                make_config(),
                translations=load_translations("en"),
            )

        self.assertIsNone(games)
        pause.assert_called_once_with("Press Enter to continue...")
        self.assertIn("No game directories have been configured.", output.getvalue())
        self.assertIn("Add a directory in Settings.", output.getvalue())

    def test_no_games_renders_explicit_english_without_loading(self) -> None:
        output = StringIO()
        test_console = Console(file=output, width=120, color_system=None)
        translations = MappingTranslations(
            {
                "Nenhum jogo compatível foi encontrado.": (
                    "No compatible games were found."
                ),
                "Pressione Enter para continuar...": "Press Enter to continue...",
            }
        )
        config = make_config(Path("/games"))

        with (
            patch("goldberg_manager.cli.load_translations") as load_translations,
            patch("goldberg_manager.cli.detect_games", return_value=[]) as detect_games,
            patch("goldberg_manager.cli.pause") as pause,
            patch("goldberg_manager.cli.console", test_console),
        ):
            games = get_detected_games(
                config,
                translations=translations,
            )

        self.assertIsNone(games)
        load_translations.assert_not_called()
        detect_games.assert_called_once_with(config.games.directories)
        pause.assert_called_once_with("Press Enter to continue...")
        self.assertIn("No compatible games were found.", output.getvalue())

    def test_rich_like_empty_state_translation_renders_literally(self) -> None:
        output = StringIO()
        test_console = Console(file=output, width=120, color_system=None)
        translations = MappingTranslations(
            {
                "Nenhum diretório de jogos foi configurado.": (
                    "[red]literal warning[/red]"
                ),
                "Adicione um diretório em Configurações.": (
                    "[blue]literal guidance[/blue]"
                ),
            }
        )

        with (
            patch("goldberg_manager.cli.pause"),
            patch("goldberg_manager.cli.console", test_console),
        ):
            get_detected_games(
                make_config(),
                translations=translations,
            )

        self.assertIn("[red]literal warning[/red]", output.getvalue())
        self.assertIn("[blue]literal guidance[/blue]", output.getvalue())


if __name__ == "__main__":
    unittest.main()
