from __future__ import annotations

import unittest
from io import StringIO
from pathlib import Path
from types import SimpleNamespace

from rich.console import Console

from goldberg_manager.presentation.rich_views import render_game_profile


def namespace(**values: object) -> SimpleNamespace:
    return SimpleNamespace(**values)


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


class RichGameProfileViewTests(unittest.TestCase):
    def test_render_game_profile_uses_explicit_console_and_escapes_markup(
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
        self.assertIn("Prefix Consensus (GSE / Heroic)", rendered)


if __name__ == "__main__":
    unittest.main()
