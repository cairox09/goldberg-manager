from __future__ import annotations

import gettext
from importlib.resources import files
from typing import Protocol

DOMAIN = "goldberg_manager"
SOURCE_LOCALE = "pt_BR"
SUPPORTED_LOCALES = frozenset({SOURCE_LOCALE, "en"})

_CATALOG_RESOURCES = {
    "en": ("locales", "en", "LC_MESSAGES", f"{DOMAIN}.mo"),
}


class Translations(Protocol):
    def gettext(self, message: str) -> str: ...


def normalize_locale(requested_locale: str | None) -> str:
    if not requested_locale:
        return SOURCE_LOCALE

    normalized = requested_locale.strip().split("@", 1)[0].split(".", 1)[0]
    normalized = normalized.replace("-", "_")
    language, _, territory = normalized.partition("_")
    language = language.casefold()

    if language == "en":
        normalized = "en"
    elif territory:
        normalized = f"{language}_{territory.upper()}"
    else:
        normalized = language

    return normalized if normalized in SUPPORTED_LOCALES else SOURCE_LOCALE


def load_translations(
    requested_locale: str | None = None,
) -> gettext.NullTranslations:
    locale_name = normalize_locale(requested_locale)

    if locale_name == SOURCE_LOCALE:
        return gettext.NullTranslations()

    resource_path = _CATALOG_RESOURCES.get(locale_name)
    if resource_path is None:
        return gettext.NullTranslations()

    catalog = files(__package__).joinpath(*resource_path)

    try:
        with catalog.open("rb") as catalog_file:
            translations = gettext.GNUTranslations(catalog_file)
    except FileNotFoundError:
        return gettext.NullTranslations()

    translations.add_fallback(gettext.NullTranslations())
    return translations
