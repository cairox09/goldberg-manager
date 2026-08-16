from __future__ import annotations

import unicodedata
from dataclasses import dataclass

import pycountry


@dataclass(frozen=True, slots=True)
class SettingChoice:
    value: str
    label: str

    @property
    def display(self) -> str:
        return f"{self.label} ({self.value})"


STEAM_LANGUAGE_CHOICES = (
    SettingChoice("arabic", "Árabe"),
    SettingChoice("bulgarian", "Búlgaro"),
    SettingChoice(
        "schinese",
        "Chinês simplificado",
    ),
    SettingChoice(
        "tchinese",
        "Chinês tradicional",
    ),
    SettingChoice("czech", "Tcheco"),
    SettingChoice("danish", "Dinamarquês"),
    SettingChoice("dutch", "Holandês"),
    SettingChoice("english", "Inglês"),
    SettingChoice("finnish", "Finlandês"),
    SettingChoice("french", "Francês"),
    SettingChoice("german", "Alemão"),
    SettingChoice("greek", "Grego"),
    SettingChoice("hungarian", "Húngaro"),
    SettingChoice("italian", "Italiano"),
    SettingChoice("japanese", "Japonês"),
    SettingChoice("koreana", "Coreano"),
    SettingChoice("norwegian", "Norueguês"),
    SettingChoice("polish", "Polonês"),
    SettingChoice(
        "portuguese",
        "Português (Portugal)",
    ),
    SettingChoice(
        "brazilian",
        "Português (Brasil)",
    ),
    SettingChoice("romanian", "Romeno"),
    SettingChoice("russian", "Russo"),
    SettingChoice(
        "spanish",
        "Espanhol (Espanha)",
    ),
    SettingChoice(
        "latam",
        "Espanhol (América Latina)",
    ),
    SettingChoice("swedish", "Sueco"),
    SettingChoice("thai", "Tailandês"),
    SettingChoice("turkish", "Turco"),
    SettingChoice("ukrainian", "Ucraniano"),
    SettingChoice("vietnamese", "Vietnamita"),
)


def _normalize_search(
    value: str,
) -> str:
    normalized = unicodedata.normalize(
        "NFKD",
        value.casefold(),
    )

    return "".join(
        character for character in normalized if not unicodedata.combining(character)
    )


def search_setting_choices(
    choices: tuple[SettingChoice, ...],
    query: str,
) -> list[SettingChoice]:
    normalized_query = _normalize_search(query).strip()

    if not normalized_query:
        return list(choices)

    terms = normalized_query.split()

    matches: list[SettingChoice] = []

    for choice in choices:
        searchable = _normalize_search(f"{choice.label} {choice.value}")

        if all(term in searchable for term in terms):
            matches.append(choice)

    return matches


def get_country_choices() -> tuple[SettingChoice, ...]:
    choices = [
        SettingChoice(
            country.alpha_2,
            country.name,
        )
        for country in pycountry.countries
    ]

    choices.sort(key=lambda choice: choice.label.casefold())

    return tuple(choices)


def search_country_choices(
    query: str,
) -> list[SettingChoice]:
    return search_setting_choices(
        get_country_choices(),
        query,
    )


def is_valid_country_code(
    value: str,
) -> bool:
    code = value.strip().upper()

    if len(code) != 2:
        return False

    return pycountry.countries.get(alpha_2=code) is not None


def is_valid_steam_language(
    value: str,
) -> bool:
    normalized = value.strip().casefold()

    return any(choice.value == normalized for choice in STEAM_LANGUAGE_CHOICES)
