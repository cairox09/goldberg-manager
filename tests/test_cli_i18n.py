from __future__ import annotations

import unittest
from io import StringIO
from unittest.mock import patch

from rich.console import Console

from goldberg_manager.cli import MENU_ITEMS, ask_menu_choice, render_menu
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


if __name__ == "__main__":
    unittest.main()
