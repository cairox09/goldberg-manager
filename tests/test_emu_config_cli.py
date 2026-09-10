from __future__ import annotations

import shutil
import subprocess
import unittest
from contextlib import ExitStack
from dataclasses import asdict
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from rich.console import Console

from goldberg_manager.cli import show_emu_config_summary
from goldberg_manager.emu_config import EmuConfigSummary
from goldberg_manager.presentation.i18n import load_translations


class RecordingTranslations:
    def __init__(self, messages: dict[str, str] | None = None) -> None:
        self.translations = messages or {}
        self.messages: list[str] = []

    def gettext(self, message: str) -> str:
        self.messages.append(message)
        return self.translations.get(message, message)


def make_summary(
    *,
    output_directory: Path = Path("/gse/_OUTPUT/2353060"),
    achievements_count: int = 12,
    achievement_images_count: int = 9,
    supported_languages_count: int = 4,
    dlc_count: int = 3,
    depots_count: int = 2,
    branches_count: int = 1,
    has_product_info: bool = True,
    has_app_details: bool = True,
) -> EmuConfigSummary:
    steam_settings = output_directory / "steam_settings"
    return EmuConfigSummary(
        app_id=2353060,
        output_directory=output_directory,
        steam_settings_directory=steam_settings,
        achievements_file=(
            steam_settings / "achievements.json" if achievements_count else None
        ),
        achievements_count=achievements_count,
        achievement_images_directory=steam_settings / "img",
        achievement_images_count=achievement_images_count,
        supported_languages_count=supported_languages_count,
        dlc_count=dlc_count,
        depots_count=depots_count,
        branches_count=branches_count,
        has_product_info=has_product_info,
        has_app_details=has_app_details,
    )


def render_summary(
    summary: EmuConfigSummary,
    *,
    translations=None,
) -> tuple[str, dict[str, object]]:
    output = StringIO()
    test_console = Console(file=output, width=240, color_system=None)
    boundary_names = (
        "questionary.select",
        "questionary.text",
        "questionary.confirm",
        "questionary.autocomplete",
        "pause",
        "run_generate_emu_config",
        "read_generated_emu_summary",
        "import_generated_achievements",
        "create_settings_safety_backup",
        "create_steam_settings_backup",
        "backup_game",
        "restore_game_backup",
        "restore_steam_settings_backup",
        "generate_game_steam_interfaces",
        "generate_game_steam_settings",
        "apply_game_sentinel_repair",
        "save_config",
        "save_appid_search_cache",
        "search_game_on_steam",
        "update_game_steam_appid",
        "update_user_setting",
    )
    path_mutation_names = (
        "mkdir",
        "rename",
        "replace",
        "rmdir",
        "touch",
        "unlink",
        "write_bytes",
        "write_text",
    )

    with ExitStack() as stack:
        stack.enter_context(patch("goldberg_manager.cli.console", test_console))
        boundaries = {
            name: stack.enter_context(patch(f"goldberg_manager.cli.{name}"))
            for name in boundary_names
        }
        boundaries.update(
            {
                f"Path.{name}": stack.enter_context(patch.object(Path, name))
                for name in path_mutation_names
            }
        )
        boundaries.update(
            {
                "shutil.copy": stack.enter_context(patch.object(shutil, "copy")),
                "shutil.copy2": stack.enter_context(patch.object(shutil, "copy2")),
                "shutil.move": stack.enter_context(patch.object(shutil, "move")),
                "shutil.rmtree": stack.enter_context(patch.object(shutil, "rmtree")),
            }
        )
        subprocess_run = stack.enter_context(patch.object(subprocess, "run"))

        if translations is None:
            show_emu_config_summary(summary)
        else:
            show_emu_config_summary(summary, translations=translations)

    boundaries["subprocess.run"] = subprocess_run
    return output.getvalue(), boundaries


class EmuConfigSummaryCliTests(unittest.TestCase):
    def assert_read_only(self, boundaries: dict[str, object]) -> None:
        for name, boundary in boundaries.items():
            with self.subTest(boundary=name):
                boundary.assert_not_called()

    def test_default_invocation_loads_translations_exactly_once(self) -> None:
        translations = RecordingTranslations(
            {"Dados gerados pelo GSE": "Loaded summary title"}
        )

        with patch(
            "goldberg_manager.cli.load_translations",
            return_value=translations,
        ) as loader:
            rendered, boundaries = render_summary(make_summary())

        loader.assert_called_once_with()
        self.assertIn("Loaded summary title", rendered)
        self.assertIn("Dados gerados pelo GSE", translations.messages)
        self.assert_read_only(boundaries)

    def test_explicit_translations_bypass_loader_and_reuse_exact_object(self) -> None:
        translations = RecordingTranslations(
            {
                "Achievements": "Exact achievements",
                "Imagens": "Exact images",
            }
        )

        with patch("goldberg_manager.cli.load_translations") as loader:
            rendered, boundaries = render_summary(
                make_summary(),
                translations=translations,
            )

        loader.assert_not_called()
        self.assertIn("Exact achievements", rendered)
        self.assertIn("Exact images", rendered)
        self.assertEqual(
            translations.messages,
            [
                "Achievements",
                "Imagens",
                "Idiomas",
                "DLCs",
                "Depots",
                "Branches",
                "Product info",
                "Sim",
                "App details",
                "Sim",
                "Dados gerados pelo GSE",
                "Output:",
            ],
        )
        self.assert_read_only(boundaries)

    def test_portuguese_complete_summary_preserves_order_and_literal_values(
        self,
    ) -> None:
        summary = make_summary()
        summary_before = asdict(summary)

        rendered, boundaries = render_summary(summary)

        expected_in_order = (
            "Steam AppID",
            "Achievements",
            "Imagens",
            "Idiomas",
            "DLCs",
            "Depots",
            "Branches",
            "Product info",
            "App details",
        )
        positions = [rendered.index(value) for value in expected_in_order]
        self.assertEqual(positions, sorted(positions))
        for expected in (
            "Dados gerados pelo GSE",
            "2353060",
            "✓ 12",
            "✓ 9",
            "4",
            "3",
            "2",
            "1",
            "✓ Sim",
            "Output:",
            str(summary.output_directory),
        ):
            self.assertIn(expected, rendered)
        self.assertEqual(asdict(summary), summary_before)
        self.assert_read_only(boundaries)

    def test_english_complete_and_missing_states_preserve_semantics(self) -> None:
        translations = load_translations("en")
        complete, complete_boundaries = render_summary(
            make_summary(),
            translations=translations,
        )
        missing_summary = make_summary(
            achievements_count=0,
            achievement_images_count=0,
            supported_languages_count=0,
            dlc_count=0,
            depots_count=0,
            branches_count=0,
            has_product_info=False,
            has_app_details=False,
        )
        missing_before = asdict(missing_summary)
        missing, missing_boundaries = render_summary(
            missing_summary,
            translations=translations,
        )

        for expected in (
            "Data generated by GSE",
            "Achievements",
            "Images",
            "Languages",
            "✓ 12",
            "✓ 9",
            "✓ Yes",
            str(make_summary().output_directory),
        ):
            self.assertIn(expected, complete)
        for expected in (
            "⚠ Not found",
            "⚠ None",
            "⚠ No",
        ):
            self.assertIn(expected, missing)
        self.assertEqual(complete.count("✓ Yes"), 2)
        no_status_lines = [
            line
            for line in missing.splitlines()
            if "⚠ No" in line and "Not found" not in line and "None" not in line
        ]
        self.assertEqual(len(no_status_lines), 2)
        self.assertNotIn("Não encontrados", missing)
        self.assertNotIn("Nenhuma", missing)
        self.assertEqual(asdict(missing_summary), missing_before)
        self.assert_read_only(complete_boundaries)
        self.assert_read_only(missing_boundaries)

    def test_rich_like_translations_and_output_path_render_literally(self) -> None:
        output_directory = Path("/gse/[bold]literal-output[/bold]/2353060")
        translations = RecordingTranslations(
            {
                "Achievements": "[red]literal achievements[/red]",
                "Imagens": "[bold]literal images[/bold]",
                "Sim": "[green]literal yes[/green]",
                "Dados gerados pelo GSE": "[cyan]literal title[/cyan]",
                "Output:": "[magenta]literal output[/magenta]",
            }
        )

        rendered, boundaries = render_summary(
            make_summary(output_directory=output_directory),
            translations=translations,
        )

        for expected in (
            "[red]literal achievements[/red]",
            "[bold]literal images[/bold]",
            "[green]literal yes[/green]",
            "[cyan]literal title[/cyan]",
            "[magenta]literal output[/magenta]",
            str(output_directory),
        ):
            self.assertIn(expected, rendered)
        self.assert_read_only(boundaries)


if __name__ == "__main__":
    unittest.main()
