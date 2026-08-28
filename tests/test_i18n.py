from __future__ import annotations

import gettext
import locale
import unittest
from importlib.resources import files
from unittest.mock import patch

from goldberg_manager.presentation.i18n import (
    DOMAIN,
    SOURCE_LOCALE,
    load_translations,
    normalize_locale,
)

MAIN_MENU_TRANSLATIONS = {
    "Detectar jogos": "Detect games",
    "Configurar Goldberg/GBE para um jogo": "Configure Goldberg/GBE for a game",
    "Gerar steam_interfaces": "Generate steam_interfaces",
    "Gerenciar steam_settings": "Manage steam_settings",
    "Backup do jogo": "Back up game",
    "Restaurar backup": "Restore backup",
    "Abrir pasta do jogo": "Open game folder",
    "Configurações": "Settings",
    "Sair": "Exit",
    "Menu principal": "Main menu",
    "Escolha uma ação:": "Choose an action:",
}


class I18nTests(unittest.TestCase):
    def test_default_uses_portuguese_source_messages(self) -> None:
        translations = load_translations()

        self.assertEqual(translations.gettext("Detectar jogos"), "Detectar jogos")

    def test_loads_exact_english_main_menu_translations(self) -> None:
        translations = load_translations("en")

        self.assertEqual(
            {
                message: translations.gettext(message)
                for message in MAIN_MENU_TRANSLATIONS
            },
            MAIN_MENU_TRANSLATIONS,
        )

    def test_missing_english_message_falls_back_to_portuguese_msgid(self) -> None:
        translations = load_translations("en")

        self.assertEqual(translations.gettext("Saindo..."), "Saindo...")

    def test_unsupported_locale_falls_back_to_portuguese(self) -> None:
        translations = load_translations("de_DE")

        self.assertEqual(translations.gettext("Detectar jogos"), "Detectar jogos")

    def test_normalizes_portuguese_locale_names(self) -> None:
        self.assertEqual(normalize_locale("pt-BR"), SOURCE_LOCALE)
        self.assertEqual(normalize_locale("pt_BR.UTF-8"), SOURCE_LOCALE)

    def test_resolves_regional_english_locales_to_english(self) -> None:
        for locale_name in ("en_US", "en_GB"):
            with self.subTest(locale_name=locale_name):
                translations = load_translations(locale_name)
                self.assertEqual(
                    translations.gettext("Detectar jogos"),
                    "Detect games",
                )

    def test_missing_catalog_falls_back_to_portuguese(self) -> None:
        with patch("goldberg_manager.presentation.i18n.files") as package_files:
            package_files.return_value.joinpath.return_value.open.side_effect = (
                FileNotFoundError
            )

            translations = load_translations("en")

        self.assertEqual(translations.gettext("Detectar jogos"), "Detectar jogos")

    def test_loading_translations_does_not_mutate_process_locale(self) -> None:
        with (
            patch.object(locale, "setlocale") as setlocale,
            patch.object(gettext, "install") as install,
        ):
            load_translations("en")

        setlocale.assert_not_called()
        install.assert_not_called()

    def test_catalog_loads_from_package_resources(self) -> None:
        catalog = files("goldberg_manager.presentation").joinpath(
            "locales",
            "en",
            "LC_MESSAGES",
            f"{DOMAIN}.mo",
        )

        with catalog.open("rb") as catalog_file:
            translations = gettext.GNUTranslations(catalog_file)

        self.assertEqual(translations.gettext("Menu principal"), "Main menu")


if __name__ == "__main__":
    unittest.main()
