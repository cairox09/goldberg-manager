from __future__ import annotations

import unittest
from contextlib import ExitStack
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from rich.console import Console

from goldberg_manager.cli import (
    MENU_ITEMS,
    ask_menu_choice,
    get_menu_game,
    render_menu,
    select_game,
    show_game_details,
)
from goldberg_manager.core.game import Game
from goldberg_manager.presentation.i18n import load_translations


class FakeTranslations:
    def __init__(self, translated: str) -> None:
        self.translated = translated

    def gettext(self, message: str) -> str:
        return self.translated


def render_main_menu(*, translations=None) -> str:
    output = StringIO()
    test_console = Console(file=output, width=120, color_system=None)

    with patch("goldberg_manager.cli.console", test_console):
        render_menu(translations=translations)

    return output.getvalue()


def make_game(
    name: str,
    *,
    architecture: str = "64-bit",
    suffix: str = "game",
) -> Game:
    root = Path("/games") / suffix
    return Game(
        name=name,
        root_directory=root,
        executable=root / "game.exe",
        steam_api=root / "steam_api64.dll",
        steam_api_relative_path=Path("steam_api64.dll"),
        architecture=architecture,
        source_directory=Path("/games"),
    )


GAME_DETAILS_VALUES = [
    "profile",
    "achievement_progress",
    "gse_saves",
    "sentinel_status",
    "sentinel_integration",
    "sentinel_repair",
    "steam_api_backup",
    "steam_api_restore",
    "back",
]

GAME_DETAILS_ACTIONS = (
    "show_game_profile",
    "show_game_achievement_status",
    "show_game_gse_status",
    "show_game_sentinel_status",
    "show_game_sentinel_integration_status",
    "repair_game_sentinel_integration",
    "create_game_backup",
    "restore_game_api",
)


def render_game_details(
    game: Game,
    *,
    translations=None,
    backup_exists: bool = False,
    metadata_exists: bool = False,
    backup_verified: bool = False,
    current_matches: bool = False,
):
    output = StringIO()
    test_console = Console(file=output, width=300, color_system=None)

    with (
        patch("goldberg_manager.cli.console", test_console),
        patch("goldberg_manager.cli.clear_screen"),
        patch("goldberg_manager.cli.render_header"),
        patch("goldberg_manager.cli.questionary.select") as select,
        patch(
            "goldberg_manager.cli.has_backup",
            return_value=backup_exists,
        ) as has_backup,
        patch(
            "goldberg_manager.cli.has_backup_metadata",
            return_value=metadata_exists,
        ),
        patch(
            "goldberg_manager.cli.verify_backup",
            return_value=backup_verified,
        ),
        patch(
            "goldberg_manager.cli.current_file_matches_backup",
            return_value=current_matches,
        ),
    ):
        select.return_value.ask.return_value = "back"
        if translations is None:
            show_game_details(game)
        else:
            show_game_details(game, translations=translations)

    return output.getvalue(), select, has_backup


class MainMenuI18nTests(unittest.TestCase):
    def test_portuguese_main_menu_remains_default(self) -> None:
        rendered = render_main_menu()

        self.assertIn("Menu principal", rendered)
        self.assertIn("Detectar jogos", rendered)
        self.assertIn("Configurações", rendered)

    def test_renders_english_main_menu_when_explicitly_requested(self) -> None:
        rendered = render_main_menu(translations=load_translations("en"))

        self.assertIn("Main menu", rendered)
        self.assertIn("Detect games", rendered)
        self.assertIn("Settings", rendered)

    def test_questionary_choices_have_translated_titles_and_stable_values(self) -> None:
        translations = load_translations("en")

        with patch("goldberg_manager.cli.questionary.select") as select:
            select.return_value.ask.return_value = "4"

            choice = ask_menu_choice(translations=translations)

        choices = select.call_args.kwargs["choices"]
        self.assertEqual(
            [questionary_choice.value for questionary_choice in choices],
            [key for key, _ in MENU_ITEMS],
        )
        self.assertEqual(choices[0].title, "1 - Detect games")
        self.assertEqual(choices[8].title, "9 - Exit")
        self.assertEqual(choice, "4")
        self.assertTrue(select.call_args.kwargs["use_shortcuts"])
        self.assertTrue(select.call_args.kwargs["use_arrow_keys"])

    def test_keyboard_cancellation_still_returns_exit_key(self) -> None:
        with patch("goldberg_manager.cli.questionary.select") as select:
            select.return_value.ask.return_value = None

            choice = ask_menu_choice(translations=load_translations("en"))

        self.assertEqual(choice, "9")

    def test_routing_is_independent_of_translated_display_text(self) -> None:
        translations = FakeTranslations("unrelated display text")

        with patch("goldberg_manager.cli.questionary.select") as select:
            select.return_value.ask.return_value = "2"

            choice = ask_menu_choice(translations=translations)

        self.assertEqual(choice, "2")
        self.assertTrue(
            all(
                questionary_choice.title.endswith("unrelated display text")
                for questionary_choice in select.call_args.kwargs["choices"]
            )
        )

    def test_rich_like_translated_text_renders_literally(self) -> None:
        rendered = render_main_menu(translations=FakeTranslations("[red]literal[/red]"))

        self.assertIn("[red]literal[/red]", rendered)


class GameDetailsI18nTests(unittest.TestCase):
    def test_portuguese_defaults_and_stable_choice_values(self) -> None:
        rendered, select, has_backup = render_game_details(make_game("Jogo"))

        for expected in (
            "Nome",
            "Arquitetura",
            "Raiz do jogo",
            "Executável",
            "Steam API relativa",
            "Backup",
            "Steam API atual",
            "Origem da detecção",
            "Detalhes do jogo",
            "Não",
            "Desconhecido",
        ):
            self.assertIn(expected, rendered)

        choices = select.call_args.kwargs["choices"]
        self.assertEqual(select.call_args.args[0], "O que deseja fazer?")
        self.assertEqual(
            [choice.title for choice in choices],
            [
                "Ver perfil do jogo",
                "Verificar conquistas / progresso",
                "Verificar saves do GSE",
                "Verificar Sentinel",
                "Verificar integração Sentinel",
                "Corrigir integração Sentinel",
                "Fazer backup da Steam API",
                "Restaurar Steam API original",
                "Voltar",
            ],
        )
        self.assertEqual([choice.value for choice in choices], GAME_DETAILS_VALUES)
        self.assertIsNotNone(choices[-1].value)
        self.assertNotIn("default", select.call_args.kwargs)
        self.assertNotIn("use_shortcuts", select.call_args.kwargs)
        self.assertNotIn("use_arrow_keys", select.call_args.kwargs)
        self.assertEqual(has_backup.call_count, 2)

    def test_explicit_english_translates_panel_menu_and_statuses(self) -> None:
        translations = load_translations("en")
        game = make_game("Literal Game")
        rendered, select, has_backup = render_game_details(
            game,
            translations=translations,
        )

        for expected in (
            "Name",
            "Architecture",
            "Game root",
            "Executable",
            "Steam API relative path",
            "Backup",
            "Current Steam API",
            "Detection source",
            "Game details",
            "No",
            "Unknown",
            "Steam API",
            "64-bit",
        ):
            self.assertIn(expected, rendered)

        choices = select.call_args.kwargs["choices"]
        self.assertEqual(select.call_args.args[0], "What would you like to do?")
        self.assertEqual(
            [choice.title for choice in choices],
            [
                "View game profile",
                "Check achievements / progress",
                "Check GSE saves",
                "Check Sentinel",
                "Check Sentinel integration",
                "Repair Sentinel integration",
                "Back up the Steam API",
                "Restore the original Steam API",
                "Back",
            ],
        )
        self.assertEqual([choice.value for choice in choices], GAME_DETAILS_VALUES)
        self.assertEqual(has_backup.call_count, 2)

        status_cases = (
            (
                {
                    "backup_exists": True,
                    "metadata_exists": False,
                    "current_matches": True,
                },
                ("Yes • no metadata", "Original"),
            ),
            (
                {
                    "backup_exists": True,
                    "metadata_exists": True,
                    "backup_verified": True,
                    "current_matches": False,
                },
                ("Yes • intact", "Modified"),
            ),
            (
                {
                    "backup_exists": True,
                    "metadata_exists": True,
                    "backup_verified": False,
                    "current_matches": False,
                },
                ("Yes • CORRUPTED", "Modified"),
            ),
        )
        for options, expected_statuses in status_cases:
            with self.subTest(expected_statuses=expected_statuses):
                status_rendered, _, status_has_backup = render_game_details(
                    game,
                    translations=translations,
                    **options,
                )
                for expected in expected_statuses:
                    self.assertIn(expected, status_rendered)
                self.assertEqual(status_has_backup.call_count, 2)

    def test_duplicate_translated_titles_cannot_affect_routing(self) -> None:
        game = make_game("Jogo")
        translations = FakeTranslations("duplicate title")

        with (
            patch("goldberg_manager.cli.questionary.select") as select,
            patch("goldberg_manager.cli.repair_game_sentinel_integration") as repair,
            patch("goldberg_manager.cli.has_backup", return_value=False),
            patch("goldberg_manager.cli.clear_screen"),
            patch("goldberg_manager.cli.render_header"),
            patch("goldberg_manager.cli.console.print"),
        ):
            select.return_value.ask.side_effect = ["sentinel_repair", "back"]

            show_game_details(game, translations=translations)

        first_choices = select.call_args_list[0].kwargs["choices"]
        self.assertTrue(
            all(choice.title == "duplicate title" for choice in first_choices)
        )
        self.assertEqual(
            [choice.value for choice in first_choices],
            GAME_DETAILS_VALUES,
        )
        repair.assert_called_once_with(game)

    def test_profile_route_propagates_exact_translation_object(self) -> None:
        game = make_game("Jogo")
        translations = FakeTranslations("duplicate title")

        with (
            patch("goldberg_manager.cli.questionary.select") as select,
            patch("goldberg_manager.cli.show_game_profile") as profile,
            patch("goldberg_manager.cli.has_backup", return_value=False),
            patch("goldberg_manager.cli.clear_screen"),
            patch("goldberg_manager.cli.render_header"),
            patch("goldberg_manager.cli.console.print"),
        ):
            select.return_value.ask.side_effect = ["profile", "back"]

            show_game_details(game, translations=translations)

        first_choices = select.call_args_list[0].kwargs["choices"]
        self.assertTrue(
            all(choice.title == "duplicate title" for choice in first_choices)
        )
        self.assertEqual(
            [choice.value for choice in first_choices],
            GAME_DETAILS_VALUES,
        )
        profile.assert_called_once_with(
            game,
            translations=translations,
        )

    def test_sentinel_status_route_propagates_exact_translation_object(self) -> None:
        game = make_game("Jogo")
        translations = FakeTranslations("duplicate title")

        with (
            patch("goldberg_manager.cli.questionary.select") as select,
            patch("goldberg_manager.cli.show_game_sentinel_status") as sentinel_status,
            patch("goldberg_manager.cli.has_backup", return_value=False),
            patch("goldberg_manager.cli.clear_screen"),
            patch("goldberg_manager.cli.render_header"),
            patch("goldberg_manager.cli.console.print"),
        ):
            select.return_value.ask.side_effect = ["sentinel_status", "back"]

            show_game_details(game, translations=translations)

        first_choices = select.call_args_list[0].kwargs["choices"]
        self.assertTrue(
            all(choice.title == "duplicate title" for choice in first_choices)
        )
        self.assertEqual(
            [choice.value for choice in first_choices],
            GAME_DETAILS_VALUES,
        )
        sentinel_status.assert_called_once_with(
            game,
            translations=translations,
        )

    def test_sentinel_integration_route_propagates_exact_translation_object(
        self,
    ) -> None:
        game = make_game("Jogo")
        translations = FakeTranslations("duplicate title")

        with (
            patch("goldberg_manager.cli.questionary.select") as select,
            patch(
                "goldberg_manager.cli.show_game_sentinel_integration_status"
            ) as integration_status,
            patch("goldberg_manager.cli.has_backup", return_value=False),
            patch("goldberg_manager.cli.clear_screen"),
            patch("goldberg_manager.cli.render_header"),
            patch("goldberg_manager.cli.console.print"),
        ):
            select.return_value.ask.side_effect = ["sentinel_integration", "back"]

            show_game_details(game, translations=translations)

        first_choices = select.call_args_list[0].kwargs["choices"]
        self.assertTrue(
            all(choice.title == "duplicate title" for choice in first_choices)
        )
        self.assertEqual(
            [choice.value for choice in first_choices],
            GAME_DETAILS_VALUES,
        )
        integration_status.assert_called_once_with(
            game,
            translations=translations,
        )

    def test_gse_status_route_propagates_exact_translation_object(self) -> None:
        game = make_game("Jogo")
        translations = FakeTranslations("duplicate title")

        with (
            patch("goldberg_manager.cli.questionary.select") as select,
            patch("goldberg_manager.cli.show_game_gse_status") as gse_status,
            patch("goldberg_manager.cli.has_backup", return_value=False),
            patch("goldberg_manager.cli.clear_screen"),
            patch("goldberg_manager.cli.render_header"),
            patch("goldberg_manager.cli.console.print"),
        ):
            select.return_value.ask.side_effect = ["gse_saves", "back"]

            show_game_details(game, translations=translations)

        first_choices = select.call_args_list[0].kwargs["choices"]
        self.assertTrue(
            all(choice.title == "duplicate title" for choice in first_choices)
        )
        self.assertEqual(
            [choice.value for choice in first_choices],
            GAME_DETAILS_VALUES,
        )
        gse_status.assert_called_once_with(
            game,
            translations=translations,
        )

    def test_achievement_status_route_propagates_exact_translation_object(
        self,
    ) -> None:
        game = make_game("Jogo")
        translations = FakeTranslations("duplicate title")

        with (
            patch("goldberg_manager.cli.questionary.select") as select,
            patch(
                "goldberg_manager.cli.show_game_achievement_status"
            ) as achievement_status,
            patch("goldberg_manager.cli.has_backup", return_value=False),
            patch("goldberg_manager.cli.clear_screen"),
            patch("goldberg_manager.cli.render_header"),
            patch("goldberg_manager.cli.console.print"),
        ):
            select.return_value.ask.side_effect = ["achievement_progress", "back"]

            show_game_details(game, translations=translations)

        first_choices = select.call_args_list[0].kwargs["choices"]
        self.assertTrue(
            all(choice.title == "duplicate title" for choice in first_choices)
        )
        self.assertEqual(
            [choice.value for choice in first_choices],
            GAME_DETAILS_VALUES,
        )
        achievement_status.assert_called_once_with(
            game,
            translations=translations,
        )

    def test_steam_api_backup_route_propagates_exact_translation_object(self) -> None:
        game = make_game("Jogo")
        translations = FakeTranslations("duplicate title")

        with (
            patch("goldberg_manager.cli.questionary.select") as select,
            patch("goldberg_manager.cli.create_game_backup") as backup,
            patch("goldberg_manager.cli.has_backup", return_value=False),
            patch("goldberg_manager.cli.clear_screen"),
            patch("goldberg_manager.cli.render_header"),
            patch("goldberg_manager.cli.console.print"),
        ):
            select.return_value.ask.side_effect = ["steam_api_backup", "back"]

            show_game_details(game, translations=translations)

        first_choices = select.call_args_list[0].kwargs["choices"]
        self.assertTrue(
            all(choice.title == "duplicate title" for choice in first_choices)
        )
        self.assertEqual(
            [choice.value for choice in first_choices],
            GAME_DETAILS_VALUES,
        )
        backup.assert_called_once_with(
            game,
            translations=translations,
        )
        self.assertIs(backup.call_args.kwargs["translations"], translations)

    def test_none_back_and_unknown_values_return_without_action(self) -> None:
        game = make_game("Jogo")

        for answer in (None, "back", "unknown"):
            with self.subTest(answer=answer), ExitStack() as stack:
                select = stack.enter_context(
                    patch("goldberg_manager.cli.questionary.select")
                )
                actions = [
                    stack.enter_context(patch(f"goldberg_manager.cli.{action}"))
                    for action in GAME_DETAILS_ACTIONS
                ]
                stack.enter_context(
                    patch("goldberg_manager.cli.has_backup", return_value=False)
                )
                stack.enter_context(patch("goldberg_manager.cli.clear_screen"))
                stack.enter_context(patch("goldberg_manager.cli.render_header"))
                stack.enter_context(patch("goldberg_manager.cli.console.print"))
                select.return_value.ask.return_value = answer

                show_game_details(game)

                for action in actions:
                    action.assert_not_called()

    def test_dynamic_rich_markup_and_technical_values_render_literally(self) -> None:
        root = Path("/games/[red]literal[/red]")
        game = Game(
            name="[bold]Literal Game[/bold]",
            root_directory=root,
            executable=root / "[cyan]game.exe[/cyan]",
            steam_api=root / "[green]steam_api64.dll[/green]",
            steam_api_relative_path=Path("[yellow]steam_api64.dll[/yellow]"),
            architecture="[magenta]64-bit[/magenta]",
            source_directory=Path("/source/[blue]library[/blue]"),
        )

        rendered, _, _ = render_game_details(
            game,
            translations=load_translations("en"),
        )

        for expected in (
            "[bold]Literal Game[/bold]",
            "/games/[red]literal[/red]",
            "[cyan]game.exe[/cyan]",
            "[green]steam_api64.dll[/green]",
            "[yellow]steam_api64.dll[/yellow]",
            "[magenta]64-bit[/magenta]",
            "/source/[blue]library[/blue]",
            "Steam API",
        ):
            self.assertIn(expected, rendered)

    def test_translated_rich_markup_renders_literally(self) -> None:
        rendered, _, _ = render_game_details(
            make_game("Jogo"),
            translations=FakeTranslations("[red]literal[/red]"),
        )

        self.assertIn("[red]literal[/red]", rendered)


class ReusableGameSelectionI18nTests(unittest.TestCase):
    def test_portuguese_defaults_use_stable_indices_and_select_first_game(
        self,
    ) -> None:
        games = [
            make_game("Primeiro", suffix="first"),
            make_game("Segundo", architecture="32-bit", suffix="second"),
        ]

        with patch("goldberg_manager.cli.questionary.select") as select:
            select.return_value.ask.return_value = 0

            selected = select_game(games)

        choices = select.call_args.kwargs["choices"]
        self.assertEqual(select.call_args.args[0], "Selecione um jogo:")
        self.assertEqual(
            [choice.title for choice in choices],
            ["1 - Primeiro [64-bit]", "2 - Segundo [32-bit]", "Voltar"],
        )
        self.assertEqual([choice.value for choice in choices], [0, 1, "back"])
        self.assertIs(selected, games[0])
        self.assertNotIn("default", select.call_args.kwargs)
        self.assertNotIn("use_shortcuts", select.call_args.kwargs)
        self.assertNotIn("use_arrow_keys", select.call_args.kwargs)

    def test_explicit_english_translates_only_prompt_and_back(self) -> None:
        games = [
            make_game(
                "Jogo [red]literal[/red]",
                architecture="arquitetura-literal",
            ),
            make_game("Segundo", suffix="second"),
        ]

        with patch("goldberg_manager.cli.questionary.select") as select:
            select.return_value.ask.return_value = 1

            selected = select_game(
                games,
                translations=load_translations("en"),
            )

        choices = select.call_args.kwargs["choices"]
        self.assertEqual(select.call_args.args[0], "Select a game:")
        self.assertEqual(
            choices[0].title,
            "1 - Jogo [red]literal[/red] [arquitetura-literal]",
        )
        self.assertEqual(choices[-1].title, "Back")
        self.assertEqual(choices[-1].value, "back")
        self.assertIsNotNone(choices[-1].value)
        self.assertIs(selected, games[1])

    def test_dynamic_names_cannot_affect_index_routing(self) -> None:
        games = [
            make_game("Jogo - Edição 2", suffix="hyphen"),
            make_game("[red]Jogo[/red]", suffix="markup"),
            make_game("Pokémon ２０７７", suffix="unicode"),
            make_game("Duplicado", suffix="duplicate-one"),
            make_game("Duplicado", suffix="duplicate-two"),
        ]

        with patch("goldberg_manager.cli.questionary.select") as select:
            select.return_value.ask.return_value = 4

            selected = select_game(games)

        choices = select.call_args.kwargs["choices"]
        self.assertEqual(choices[0].title, "1 - Jogo - Edição 2 [64-bit]")
        self.assertEqual(choices[1].title, "2 - [red]Jogo[/red] [64-bit]")
        self.assertEqual(choices[2].title, "3 - Pokémon ２０７７ [64-bit]")
        self.assertEqual(choices[3].title, "4 - Duplicado [64-bit]")
        self.assertEqual(choices[4].title, "5 - Duplicado [64-bit]")
        self.assertIs(selected, games[4])

    def test_fake_translations_cannot_affect_routing(self) -> None:
        games = [make_game("Literal")]
        translations = FakeTranslations("texto traduzido não relacionado")

        with patch("goldberg_manager.cli.questionary.select") as select:
            select.return_value.ask.return_value = 0

            selected = select_game(games, translations=translations)

        choices = select.call_args.kwargs["choices"]
        self.assertEqual(select.call_args.args[0], translations.translated)
        self.assertEqual(choices[0].title, "1 - Literal [64-bit]")
        self.assertEqual(choices[0].value, 0)
        self.assertEqual(choices[-1].title, translations.translated)
        self.assertEqual(choices[-1].value, "back")
        self.assertIs(selected, games[0])

    def test_keyboard_cancellation_returns_none(self) -> None:
        with patch("goldberg_manager.cli.questionary.select") as select:
            select.return_value.ask.return_value = None

            selected = select_game([make_game("Jogo")])

        self.assertIsNone(selected)

    def test_explicit_back_returns_none(self) -> None:
        with patch("goldberg_manager.cli.questionary.select") as select:
            select.return_value.ask.return_value = "back"

            selected = select_game([make_game("Jogo")])

        back = select.call_args.kwargs["choices"][-1]
        self.assertEqual(back.value, "back")
        self.assertIsNotNone(back.value)
        self.assertIsNone(selected)

    def test_custom_message_remains_a_valid_positional_argument(self) -> None:
        game = make_game("Jogo")

        with patch("goldberg_manager.cli.questionary.select") as select:
            select.return_value.ask.return_value = 0

            selected = select_game([game], "Mensagem personalizada:")

        self.assertEqual(select.call_args.args[0], "Mensagem personalizada:")
        self.assertIs(selected, game)

    def test_get_menu_game_returns_supplied_game_without_detection(self) -> None:
        config = object()
        game = make_game("Jogo")

        with (
            patch("goldberg_manager.cli.load_translations") as load_translations,
            patch("goldberg_manager.cli.get_detected_games") as get_detected_games,
            patch("goldberg_manager.cli.select_game") as select_game_mock,
        ):
            selected = get_menu_game(config, game, "Mensagem:")

        self.assertIs(selected, game)
        load_translations.assert_not_called()
        get_detected_games.assert_not_called()
        select_game_mock.assert_not_called()

    def test_get_menu_game_loads_once_and_propagates_exact_translations(self) -> None:
        config = object()
        games = [make_game("Jogo")]
        translations = FakeTranslations("translated")

        with (
            patch(
                "goldberg_manager.cli.load_translations",
                return_value=translations,
            ) as load_translations,
            patch(
                "goldberg_manager.cli.get_detected_games",
                return_value=games,
            ) as get_detected_games,
            patch(
                "goldberg_manager.cli.select_game",
                return_value=games[0],
            ) as select_game_mock,
        ):
            selected = get_menu_game(
                config,
                None,
                "Mensagem:",
            )

        self.assertIs(selected, games[0])
        load_translations.assert_called_once_with()
        get_detected_games.assert_called_once_with(
            config,
            translations=translations,
        )
        select_game_mock.assert_called_once_with(
            games,
            "Mensagem:",
            translations=translations,
        )

    def test_get_menu_game_explicit_translations_bypass_loader(self) -> None:
        config = object()
        games = [make_game("Jogo")]
        translations = FakeTranslations("translated")

        with (
            patch("goldberg_manager.cli.load_translations") as load_translations,
            patch(
                "goldberg_manager.cli.get_detected_games",
                return_value=games,
            ) as get_detected_games,
            patch(
                "goldberg_manager.cli.select_game",
                return_value=games[0],
            ) as select_game_mock,
        ):
            selected = get_menu_game(
                config,
                None,
                "Mensagem:",
                translations=translations,
            )

        self.assertIs(selected, games[0])
        load_translations.assert_not_called()
        self.assertIs(get_detected_games.call_args.kwargs["translations"], translations)
        self.assertIs(select_game_mock.call_args.kwargs["translations"], translations)

    def test_get_menu_game_detection_failure_does_not_select(self) -> None:
        config = object()
        translations = FakeTranslations("translated")

        with (
            patch(
                "goldberg_manager.cli.get_detected_games",
                return_value=None,
            ) as get_detected_games,
            patch("goldberg_manager.cli.select_game") as select_game_mock,
        ):
            selected = get_menu_game(
                config,
                None,
                "Mensagem:",
                translations=translations,
            )

        self.assertIsNone(selected)
        get_detected_games.assert_called_once_with(
            config,
            translations=translations,
        )
        select_game_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
