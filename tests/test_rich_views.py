from __future__ import annotations

import unittest
from io import StringIO
from pathlib import Path
from types import SimpleNamespace

from rich.console import Console

from goldberg_manager.presentation.i18n import load_translations
from goldberg_manager.presentation.rich_views import render_game_profile


def namespace(**values: object) -> SimpleNamespace:
    return SimpleNamespace(**values)


class MappingTranslations:
    def __init__(self, messages: dict[str, str]) -> None:
        self.messages = messages

    def gettext(self, message: str) -> str:
        return self.messages.get(message, message)


def make_minimal_profile() -> SimpleNamespace:
    game = namespace(
        name="Example [red]Game[/red]",
        executable=Path("/games/Example/Binaries/Game.exe"),
        steam_api=Path("/games/Example/Binaries/steam_api64.dll"),
    )

    return namespace(
        game=game,
        architecture="64-bit",
        app_id=None,
        app_id_confidence=None,
        app_id_source=None,
        settings=namespace(
            account_name=None,
            account_steamid=None,
            language=None,
            ip_country=None,
            local_save_path=None,
            saves_folder_name=None,
        ),
        gse=namespace(save_resolution=None),
        achievements=namespace(
            metadata_path=Path("/games/Example/steam_settings/achievements.json"),
            metadata_exists=False,
            reports=(),
            errors=(),
        ),
        sentinel=namespace(
            installation=namespace(
                installed=False,
                executable=None,
            ),
            status=namespace(
                exists=False,
                valid_json=False,
                schema_valid=False,
                configured=False,
                path=Path("/config/sentinel/config.json"),
                error=None,
            ),
            coverage=namespace(
                fully_watched=False,
                partially_watched=False,
                unwatched=False,
                effective_save_resolved=False,
                recognized_by_sentinel=False,
            ),
        ),
        heroic=namespace(
            resolved=False,
            ambiguous=False,
            candidates=(),
            effective=None,
            strongest_evidence=None,
        ),
        steam=namespace(
            resolved=False,
            ambiguous=False,
            candidates=(),
            effective=None,
            prefix=None,
            strongest_evidence=None,
        ),
        prefix_consensus=namespace(
            resolved=False,
            conflict=False,
            evidences=(),
            effective_wine_prefix=None,
            effective_drive_c=None,
        ),
    )


def render(profile: SimpleNamespace, *, translations=None) -> str:
    output = StringIO()
    console = Console(file=output, width=220, color_system=None)
    render_game_profile(
        profile,
        console=console,
        translations=translations,
    )
    return output.getvalue()


class RichGameProfileViewTests(unittest.TestCase):
    def test_default_portuguese_uses_explicit_console_and_escapes_markup(
        self,
    ) -> None:
        output = StringIO()
        console = Console(file=output, width=220, color_system=None)

        render_game_profile(
            make_minimal_profile(),
            console=console,
        )

        rendered = output.getvalue()
        self.assertIn("Example [red]Game[/red]", rendered)
        self.assertIn("Perfil do jogo", rendered)
        self.assertIn("Identidade", rendered)
        self.assertIn("Configurações", rendered)
        self.assertIn("Conquistas", rendered)
        self.assertIn("DESCONHECIDO", rendered)
        self.assertIn("Consenso de prefixo (GSE / Heroic)", rendered)

    def test_explicit_english_catalog_translates_complete_minimal_profile(
        self,
    ) -> None:
        rendered = render(
            make_minimal_profile(),
            translations=load_translations("en"),
        )

        for expected in (
            "Game profile",
            "Identity",
            "Architecture",
            "Executable",
            "Settings",
            "No configuration identified",
            "Resolution",
            "GSE save not identified",
            "Achievements",
            "Metadata",
            "Not found",
            "Runtime unavailable",
            "Installation",
            "Not detected",
            "Configuration",
            "Configuration path",
            "GSE integration",
            "No effective save to evaluate",
            "Heroic ownership not identified.",
            "Steam ownership not identified.",
            "UNKNOWN",
            "Prefix consensus (GSE / Heroic)",
            "No structural prefix evidence from GSE or Heroic is available.",
        ):
            self.assertIn(expected, rendered)

    def test_explicit_english_catalog_translates_indexed_rows(self) -> None:
        profile = make_minimal_profile()
        profile.gse.save_resolution = namespace(
            source="default",
            raw_value=None,
            effective_locations=(),
            ambiguous=True,
            locations=(
                namespace(root=Path("/saves/one")),
                namespace(root=Path("/saves/two")),
            ),
        )
        profile.achievements.metadata_exists = True
        profile.achievements.reports = tuple(
            namespace(
                runtime_path=Path(f"/saves/{index}/achievements.json"),
                total=10,
                unlocked=index,
                locked=10 - index,
                completion_percentage=index * 10.0,
            )
            for index in (1, 2)
        )

        rendered = render(profile, translations=load_translations("en"))

        for expected in (
            "Ambiguous",
            "Effective save",
            "Not determined",
            "Possible save #1",
            "Possible save #2",
            "Runtime #1",
            "Total #1",
            "Unlocked #1",
            "Locked #1",
            "Completion #1",
            "Runtime #2",
            "Total #2",
            "Unlocked #2",
            "Locked #2",
            "Completion #2",
        ):
            self.assertIn(expected, rendered)

    def test_translated_rich_markup_is_literal_and_missing_keys_fall_back(
        self,
    ) -> None:
        translations = MappingTranslations({"Perfil do jogo": "[red]literal[/red]"})

        rendered = render(make_minimal_profile(), translations=translations)

        self.assertIn("[red]literal[/red]", rendered)
        self.assertIn("Identidade", rendered)


if __name__ == "__main__":
    unittest.main()
