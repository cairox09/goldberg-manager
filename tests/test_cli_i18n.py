from __future__ import annotations

import unittest
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
            patch("goldberg_manager.cli.get_detected_games") as get_detected_games,
            patch("goldberg_manager.cli.select_game") as select_game_mock,
        ):
            selected = get_menu_game(
                config,
                game,
                "Mensagem:",
                translations=FakeTranslations("translated"),
            )

        self.assertIs(selected, game)
        get_detected_games.assert_not_called()
        select_game_mock.assert_not_called()

    def test_get_menu_game_propagates_explicit_translations(self) -> None:
        config = object()
        games = [make_game("Jogo")]
        translations = FakeTranslations("translated")

        with (
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
        get_detected_games.assert_called_once_with(config)
        select_game_mock.assert_called_once_with(
            games,
            "Mensagem:",
            translations=translations,
        )


if __name__ == "__main__":
    unittest.main()
