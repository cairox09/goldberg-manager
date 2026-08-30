from __future__ import annotations

import tempfile
import unittest
from contextlib import ExitStack
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from rich.console import Console

from goldberg_manager.cli import show_game_candidate_details, show_games
from goldberg_manager.config import AppConfig, GamesConfig
from goldberg_manager.core.game import Game
from goldberg_manager.presentation.i18n import load_translations
from goldberg_manager.scanner import GameCandidate


class MappingTranslations:
    def __init__(self, messages: dict[str, str] | None = None) -> None:
        self.messages = messages or {}

    def gettext(self, message: str) -> str:
        return self.messages.get(message, message)


def make_config(*directories: Path) -> AppConfig:
    return AppConfig(games=GamesConfig(directories=list(directories)))


def make_game(
    name: str = "Configured Game",
    *,
    root: Path = Path("/games/Configured Game"),
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


def make_candidate(
    name: str = "Unsupported Game",
    *,
    root: Path = Path("/games/Unsupported Game"),
    game: Game | None = None,
) -> GameCandidate:
    return GameCandidate(
        name=name,
        root_directory=root,
        executable=root / "Game.exe",
        source_directory=root.parent,
        game=game,
    )


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


class GameDiscoveryCliTests(unittest.TestCase):
    def test_default_list_loads_once_and_preserves_portuguese(self) -> None:
        output = StringIO()
        test_console = Console(file=output, width=200, color_system=None)
        translations = MappingTranslations()
        game = make_game()
        candidates = [
            make_candidate(game.name, root=game.root_directory, game=game),
            make_candidate(),
        ]
        config = make_config(Path("/games"))

        with (
            patch(
                "goldberg_manager.cli.load_translations",
                return_value=translations,
            ) as load_catalog,
            patch(
                "goldberg_manager.cli.discover_game_candidates",
                return_value=candidates,
            ) as discover,
            patch("goldberg_manager.cli.questionary.select") as select,
            patch("goldberg_manager.cli.show_game_details") as configured_details,
            patch(
                "goldberg_manager.cli.show_game_candidate_details"
            ) as unsupported_details,
            patch("goldberg_manager.cli.pause") as pause,
            patch("goldberg_manager.cli.console", test_console),
            patch("goldberg_manager.cli.clear_screen"),
            patch("goldberg_manager.cli.render_header"),
        ):
            select.return_value.ask.return_value = None

            show_games(config)

        load_catalog.assert_called_once_with()
        discover.assert_called_once_with(config.games.directories)
        self.assertEqual(select.call_args.args[0], "Selecione um jogo:")
        choices = select.call_args.kwargs["choices"]
        self.assertEqual(
            [choice.title for choice in choices],
            ["1 - Configured Game", "2 - Unsupported Game", "Voltar"],
        )
        self.assertEqual([choice.value for choice in choices], [0, 1, "back"])
        for expected in (
            "Jogos encontrados",
            "Jogo",
            "Arquitetura",
            "Status",
            "Executável",
            "✓ Configurável",
            "⚠ Steam API ausente",
        ):
            self.assertIn(expected, output.getvalue())
        configured_details.assert_not_called()
        unsupported_details.assert_not_called()
        pause.assert_not_called()

    def test_standalone_candidate_details_loads_once_and_pauses(self) -> None:
        output = StringIO()
        test_console = Console(file=output, width=200, color_system=None)
        translations = MappingTranslations()
        candidate = make_candidate()

        with (
            patch(
                "goldberg_manager.cli.load_translations",
                return_value=translations,
            ) as load_catalog,
            patch("goldberg_manager.cli.pause") as pause,
            patch("goldberg_manager.cli.console", test_console),
            patch("goldberg_manager.cli.clear_screen"),
            patch("goldberg_manager.cli.render_header"),
        ):
            show_game_candidate_details(candidate)

        load_catalog.assert_called_once_with()
        pause.assert_called_once_with("Pressione Enter para continuar...")
        for expected in (
            "Nome",
            "Raiz do jogo",
            "Executável",
            "Não localizada",
            "Não configurável",
            "Origem da detecção",
            "Detalhes do jogo",
            "O executável foi detectado, mas nenhuma Steam API foi localizada.",
        ):
            self.assertIn(expected, output.getvalue())

    def test_explicit_english_translates_list_prompt_back_and_statuses(self) -> None:
        output = StringIO()
        test_console = Console(file=output, width=200, color_system=None)
        candidate = make_candidate()
        game = make_game()
        configured = make_candidate(game.name, root=game.root_directory, game=game)

        with (
            patch("goldberg_manager.cli.load_translations") as load_catalog,
            patch(
                "goldberg_manager.cli.discover_game_candidates",
                return_value=[configured, candidate],
            ),
            patch("goldberg_manager.cli.questionary.select") as select,
            patch("goldberg_manager.cli.console", test_console),
            patch("goldberg_manager.cli.clear_screen"),
            patch("goldberg_manager.cli.render_header"),
        ):
            select.return_value.ask.return_value = "back"

            show_games(
                make_config(Path("/games")),
                translations=load_translations("en"),
            )

        load_catalog.assert_not_called()
        self.assertEqual(select.call_args.args[0], "Select a game:")
        choices = select.call_args.kwargs["choices"]
        self.assertEqual(choices[-1].title, "Back")
        self.assertEqual(choices[-1].value, "back")
        for expected in (
            "Games found",
            "Game",
            "Architecture",
            "Status",
            "Executable",
            "✓ Configurable",
            "⚠ Steam API missing",
        ):
            self.assertIn(expected, output.getvalue())

    def test_stable_values_route_exact_unsupported_candidate_and_translations(
        self,
    ) -> None:
        translations = MappingTranslations(
            {
                "Selecione um jogo:": "duplicate translated title",
                "Voltar": "duplicate translated title",
            }
        )
        candidates = [
            make_candidate("Duplicado", root=Path("/games/one")),
            make_candidate("Duplicado", root=Path("/games/two")),
            make_candidate("Game - Edition -- Deluxe", root=Path("/games/hyphen")),
            make_candidate(
                "Pokémon ２０７７ [red]literal[/red]",
                root=Path("/games/unicode"),
            ),
        ]

        with (
            patch("goldberg_manager.cli.load_translations") as load_catalog,
            patch(
                "goldberg_manager.cli.discover_game_candidates",
                return_value=candidates,
            ),
            patch("goldberg_manager.cli.questionary.select") as select,
            patch(
                "goldberg_manager.cli.show_game_candidate_details"
            ) as unsupported_details,
            patch("goldberg_manager.cli.show_game_details") as configured_details,
            patch("goldberg_manager.cli.pause") as pause,
            patch("goldberg_manager.cli.console.print"),
            patch("goldberg_manager.cli.clear_screen"),
            patch("goldberg_manager.cli.render_header"),
        ):
            select.return_value.ask.return_value = 3

            show_games(
                make_config(Path("/games")),
                translations=translations,
            )

        load_catalog.assert_not_called()
        choices = select.call_args.kwargs["choices"]
        self.assertEqual([choice.value for choice in choices], [0, 1, 2, 3, "back"])
        self.assertEqual(
            [choice.title for choice in choices],
            [
                "1 - Duplicado",
                "2 - Duplicado",
                "3 - Game - Edition -- Deluxe",
                "4 - Pokémon ２０７７ [red]literal[/red]",
                "duplicate translated title",
            ],
        )
        self.assertEqual(select.call_args.args[0], "duplicate translated title")
        unsupported_details.assert_called_once_with(
            candidates[3],
            translations=translations,
        )
        self.assertIs(unsupported_details.call_args.args[0], candidates[3])
        self.assertIs(
            unsupported_details.call_args.kwargs["translations"],
            translations,
        )
        configured_details.assert_not_called()
        pause.assert_not_called()

    def test_configured_candidate_propagates_exact_game_and_translations(self) -> None:
        translations = MappingTranslations()
        game = make_game()
        candidate = make_candidate(game.name, root=game.root_directory, game=game)
        error = RuntimeError("unexpected configured child")

        with (
            patch(
                "goldberg_manager.cli.discover_game_candidates",
                return_value=[candidate],
            ),
            patch("goldberg_manager.cli.questionary.select") as select,
            patch(
                "goldberg_manager.cli.show_game_details",
                side_effect=error,
            ) as configured_details,
            patch("goldberg_manager.cli.pause") as pause,
            patch("goldberg_manager.cli.console.print"),
            patch("goldberg_manager.cli.clear_screen"),
            patch("goldberg_manager.cli.render_header"),
            self.assertRaises(RuntimeError) as raised,
        ):
            select.return_value.ask.return_value = 0

            show_games(
                make_config(Path("/games")),
                translations=translations,
            )

        self.assertIs(raised.exception, error)
        configured_details.assert_called_once_with(
            game,
            translations=translations,
        )
        self.assertIs(configured_details.call_args.args[0], game)
        self.assertIs(
            configured_details.call_args.kwargs["translations"],
            translations,
        )
        pause.assert_not_called()

    def test_cancellation_and_back_do_not_call_children_or_pause(self) -> None:
        candidate = make_candidate()

        for answer in (None, "back"):
            with self.subTest(answer=answer), ExitStack() as stack:
                stack.enter_context(
                    patch(
                        "goldberg_manager.cli.discover_game_candidates",
                        return_value=[candidate],
                    )
                )
                select = stack.enter_context(
                    patch("goldberg_manager.cli.questionary.select")
                )
                configured_details = stack.enter_context(
                    patch("goldberg_manager.cli.show_game_details")
                )
                unsupported_details = stack.enter_context(
                    patch("goldberg_manager.cli.show_game_candidate_details")
                )
                pause = stack.enter_context(patch("goldberg_manager.cli.pause"))
                stack.enter_context(patch("goldberg_manager.cli.console.print"))
                stack.enter_context(patch("goldberg_manager.cli.clear_screen"))
                stack.enter_context(patch("goldberg_manager.cli.render_header"))
                select.return_value.ask.return_value = answer

                show_games(make_config(Path("/games")))

            configured_details.assert_not_called()
            unsupported_details.assert_not_called()
            pause.assert_not_called()

    def test_empty_config_translates_pauses_and_does_not_discover(self) -> None:
        output = StringIO()
        test_console = Console(file=output, width=200, color_system=None)

        with (
            patch("goldberg_manager.cli.discover_game_candidates") as discover,
            patch("goldberg_manager.cli.questionary.select") as select,
            patch("goldberg_manager.cli.show_game_details") as configured_details,
            patch(
                "goldberg_manager.cli.show_game_candidate_details"
            ) as unsupported_details,
            patch("goldberg_manager.cli.pause") as pause,
            patch("goldberg_manager.cli.console", test_console),
            patch("goldberg_manager.cli.clear_screen"),
            patch("goldberg_manager.cli.render_header"),
        ):
            show_games(make_config(), translations=load_translations("en"))

        discover.assert_not_called()
        select.assert_not_called()
        configured_details.assert_not_called()
        unsupported_details.assert_not_called()
        pause.assert_called_once_with("Press Enter to continue...")
        self.assertIn("No game directories have been configured.", output.getvalue())
        self.assertIn("Go to Settings and add a directory.", output.getvalue())

    def test_empty_discovery_translates_pauses_and_does_not_select(self) -> None:
        output = StringIO()
        test_console = Console(file=output, width=200, color_system=None)
        config = make_config(Path("/games"))

        with (
            patch(
                "goldberg_manager.cli.discover_game_candidates",
                return_value=[],
            ) as discover,
            patch("goldberg_manager.cli.questionary.select") as select,
            patch("goldberg_manager.cli.show_game_details") as configured_details,
            patch(
                "goldberg_manager.cli.show_game_candidate_details"
            ) as unsupported_details,
            patch("goldberg_manager.cli.pause") as pause,
            patch("goldberg_manager.cli.console", test_console),
            patch("goldberg_manager.cli.clear_screen"),
            patch("goldberg_manager.cli.render_header"),
        ):
            show_games(config, translations=load_translations("en"))

        discover.assert_called_once_with(config.games.directories)
        select.assert_not_called()
        configured_details.assert_not_called()
        unsupported_details.assert_not_called()
        pause.assert_called_once_with("Press Enter to continue...")
        self.assertIn("No games were found.", output.getvalue())

    def test_discovery_and_unsupported_child_errors_propagate(self) -> None:
        config = make_config(Path("/games"))
        candidate = make_candidate()

        discovery_error = OSError("discovery failed")
        with (
            patch(
                "goldberg_manager.cli.discover_game_candidates",
                side_effect=discovery_error,
            ),
            patch("goldberg_manager.cli.questionary.select") as select,
            patch("goldberg_manager.cli.pause") as pause,
            patch("goldberg_manager.cli.clear_screen"),
            patch("goldberg_manager.cli.render_header"),
            self.assertRaises(OSError) as raised_discovery,
        ):
            show_games(config)

        self.assertIs(raised_discovery.exception, discovery_error)
        select.assert_not_called()
        pause.assert_not_called()

        child_error = RuntimeError("unsupported child failed")
        with (
            patch(
                "goldberg_manager.cli.discover_game_candidates",
                return_value=[candidate],
            ),
            patch("goldberg_manager.cli.questionary.select") as select,
            patch(
                "goldberg_manager.cli.show_game_candidate_details",
                side_effect=child_error,
            ),
            patch("goldberg_manager.cli.pause") as pause,
            patch("goldberg_manager.cli.console.print"),
            patch("goldberg_manager.cli.clear_screen"),
            patch("goldberg_manager.cli.render_header"),
            self.assertRaises(RuntimeError) as raised_child,
        ):
            select.return_value.ask.return_value = 0
            show_games(config)

        self.assertIs(raised_child.exception, child_error)
        pause.assert_not_called()

    def test_dynamic_and_translated_rich_markup_render_literally(self) -> None:
        output = StringIO()
        test_console = Console(file=output, width=300, color_system=None)
        root = Path("/games/[red]literal root[/red]")
        game = make_game(
            "[bold]literal configured[/bold]",
            root=root,
        )
        game.architecture = "[magenta]64-bit[/magenta]"
        game.steam_api = root / "[green]steam_api64.dll"
        candidate = make_candidate(
            "[bold]literal configured[/bold]",
            root=root,
            game=game,
        )
        candidate.executable = root / "[cyan]Game.exe"
        translations = MappingTranslations(
            {
                "Jogos encontrados": "[red]literal title[/red]",
                "Jogo": "[blue]literal game label[/blue]",
                "Configurável": "[green]literal status[/green]",
            }
        )

        with (
            patch(
                "goldberg_manager.cli.discover_game_candidates",
                return_value=[candidate],
            ),
            patch("goldberg_manager.cli.questionary.select") as select,
            patch("goldberg_manager.cli.console", test_console),
            patch("goldberg_manager.cli.clear_screen"),
            patch("goldberg_manager.cli.render_header"),
        ):
            select.return_value.ask.return_value = "back"
            show_games(
                make_config(Path("/games")),
                translations=translations,
            )

        for expected in (
            "[red]literal title[/red]",
            "[blue]literal game label[/blue]",
            "[green]literal status[/green]",
            "[bold]literal configured[/bold]",
            "[magenta]64-bit[/magenta]",
            "[green]steam_api64.dll",
            "[cyan]Game.exe",
        ):
            self.assertIn(expected, output.getvalue())

        details_output = StringIO()
        details_console = Console(
            file=details_output,
            width=300,
            color_system=None,
        )
        unsupported_root = Path("/games/[red]unsupported root[/red]")
        unsupported = make_candidate(
            "[bold]unsupported name[/bold]",
            root=unsupported_root,
        )
        unsupported.executable = unsupported_root / "[cyan]game.exe[/cyan]"
        unsupported.source_directory = Path("/source/[blue]library[/blue]")
        detail_translations = MappingTranslations(
            {
                "Nome": "[red]literal name label[/red]",
                "Não localizada": "[yellow]literal unavailable[/yellow]",
                "Detalhes do jogo": "[green]literal details title[/green]",
                "O executável foi detectado, mas nenhuma Steam API foi localizada.": (
                    "[magenta]literal first paragraph[/magenta]"
                ),
                "As funções que dependem da Steam API não estão disponíveis para este jogo.": (
                    "[cyan]literal second paragraph[/cyan]"
                ),
            }
        )

        with (
            patch("goldberg_manager.cli.load_translations") as load_catalog,
            patch("goldberg_manager.cli.pause") as pause,
            patch("goldberg_manager.cli.console", details_console),
            patch("goldberg_manager.cli.clear_screen"),
            patch("goldberg_manager.cli.render_header"),
        ):
            show_game_candidate_details(
                unsupported,
                translations=detail_translations,
            )

        load_catalog.assert_not_called()
        pause.assert_called_once_with("Pressione Enter para continuar...")
        for expected in (
            "[red]literal name label[/red]",
            "[yellow]literal unavailable[/yellow]",
            "[green]literal details title[/green]",
            "[magenta]literal first paragraph[/magenta]",
            "[cyan]literal second paragraph[/cyan]",
            "[bold]unsupported name[/bold]",
            "/games/[red]unsupported root[/red]",
            "[cyan]game.exe[/cyan]",
            "/source/[blue]library[/blue]",
        ):
            self.assertIn(expected, details_output.getvalue())

    def test_explicit_english_translates_unsupported_details_and_pause(self) -> None:
        output = StringIO()
        test_console = Console(file=output, width=300, color_system=None)
        candidate = make_candidate()

        with (
            patch("goldberg_manager.cli.load_translations") as load_catalog,
            patch("goldberg_manager.cli.pause") as pause,
            patch("goldberg_manager.cli.console", test_console),
            patch("goldberg_manager.cli.clear_screen"),
            patch("goldberg_manager.cli.render_header"),
        ):
            show_game_candidate_details(
                candidate,
                translations=load_translations("en"),
            )

        load_catalog.assert_not_called()
        pause.assert_called_once_with("Press Enter to continue...")
        for expected in (
            "Name",
            "Game root",
            "Executable",
            "Not found",
            "Not configurable",
            "Detection source",
            "Game details",
            "The executable was detected, but no Steam API was found.",
            "Features that depend on the Steam API are not available for this game.",
        ):
            self.assertIn(expected, output.getvalue())

    def test_real_discovery_back_path_has_no_write_or_external_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            library = Path(temp_directory)
            game_root = library / "Read Only Game"
            game_root.mkdir()
            (game_root / "Game.exe").write_bytes(b"exe")
            config = make_config(library)

            with ExitStack() as stack:
                select = stack.enter_context(
                    patch("goldberg_manager.cli.questionary.select")
                )
                select.return_value.ask.return_value = "back"
                stack.enter_context(patch("goldberg_manager.cli.clear_screen"))
                stack.enter_context(patch("goldberg_manager.cli.render_header"))
                stack.enter_context(patch("goldberg_manager.cli.console.print"))
                pause = stack.enter_context(patch("goldberg_manager.cli.pause"))
                mutations = [
                    stack.enter_context(patch(f"goldberg_manager.cli.{name}"))
                    for name in MUTATION_FUNCTIONS
                ]
                run = stack.enter_context(patch("goldberg_manager.cli.subprocess.run"))
                path_mkdir = stack.enter_context(patch.object(Path, "mkdir"))
                path_write_text = stack.enter_context(patch.object(Path, "write_text"))
                path_write_bytes = stack.enter_context(
                    patch.object(Path, "write_bytes")
                )

                show_games(config)

            choices = select.call_args.kwargs["choices"]
            self.assertEqual([choice.value for choice in choices], [0, "back"])
            self.assertEqual(choices[0].title, "1 - Read Only Game")
            pause.assert_not_called()
            run.assert_not_called()
            path_mkdir.assert_not_called()
            path_write_text.assert_not_called()
            path_write_bytes.assert_not_called()
            for mutation in mutations:
                mutation.assert_not_called()


if __name__ == "__main__":
    unittest.main()
