import unittest

from goldberg_manager.settings_catalog import (
    STEAM_LANGUAGE_CHOICES,
    get_country_choices,
    is_valid_country_code,
    is_valid_steam_language,
    search_country_choices,
    search_setting_choices,
)


class SettingsCatalogTests(unittest.TestCase):
    def test_contains_supported_steam_languages(
        self,
    ) -> None:
        values = {choice.value for choice in STEAM_LANGUAGE_CHOICES}

        self.assertIn(
            "english",
            values,
        )

        self.assertIn(
            "brazilian",
            values,
        )

        self.assertIn(
            "latam",
            values,
        )

        self.assertEqual(
            len(values),
            29,
        )

    def test_searches_language_by_name(
        self,
    ) -> None:
        matches = search_setting_choices(
            STEAM_LANGUAGE_CHOICES,
            "portugues",
        )

        values = {choice.value for choice in matches}

        self.assertEqual(
            values,
            {
                "portuguese",
                "brazilian",
            },
        )

    def test_searches_language_by_api_code(
        self,
    ) -> None:
        matches = search_setting_choices(
            STEAM_LANGUAGE_CHOICES,
            "brazilian",
        )

        self.assertEqual(
            [choice.value for choice in matches],
            ["brazilian"],
        )

    def test_validates_steam_language(
        self,
    ) -> None:
        self.assertTrue(is_valid_steam_language("brazilian"))

        self.assertTrue(is_valid_steam_language("ENGLISH"))

        self.assertFalse(is_valid_steam_language("portugues-br"))

    def test_loads_iso_countries(
        self,
    ) -> None:
        countries = get_country_choices()

        self.assertGreaterEqual(
            len(countries),
            240,
        )

        values = {country.value for country in countries}

        self.assertIn(
            "BR",
            values,
        )

        self.assertIn(
            "US",
            values,
        )

    def test_searches_country(
        self,
    ) -> None:
        matches = search_country_choices("Brazil")

        self.assertIn(
            "BR",
            {country.value for country in matches},
        )

    def test_validates_iso_country_code(
        self,
    ) -> None:
        self.assertTrue(is_valid_country_code("BR"))

        self.assertTrue(is_valid_country_code("us"))

        self.assertFalse(is_valid_country_code("ZZ"))

        self.assertFalse(is_valid_country_code("BRA"))


if __name__ == "__main__":
    unittest.main()
