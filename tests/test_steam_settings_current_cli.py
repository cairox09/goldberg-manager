from __future__ import annotations

import shutil
import tempfile
import unittest
from contextlib import ExitStack
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from rich.console import Console

from goldberg_manager.cli import (
    manage_steam_settings_menu,
    show_current_steam_settings_menu,
)
from goldberg_manager.config import AppConfig
from goldberg_manager.core.game import Game
from goldberg_manager.presentation.i18n import load_translations
from goldberg_manager.settings import SteamSettingsSnapshot


class MappingTranslations:
    def __init__(self, messages: dict[str, str] | None = None) -> None:
        self.messages = messages or {}

    def gettext(self, message: str) -> str:
        return self.messages.get(message, message)


def make_game(root: Path = Path("/games/Example")) -> Game:
    return Game(
        name="Example Game",
        root_directory=root,
        executable=root / "Game.exe",
        steam_api=root / "steam_api64.dll",
        steam_api_relative_path=Path("steam_api64.dll"),
        architecture="64-bit",
        source_directory=root.parent,
    )


PARENT_VALUES = ["current", "edit", "generate", "backups", "back"]
PARENT_ACTIONS = (
    "show_current_steam_settings_menu",
    "edit_steam_settings_menu",
    "generate_steam_settings_menu",
    "manage_steam_settings_backups_menu",
)


class ManageSteamSettingsRoutingTests(unittest.TestCase):
    def test_portuguese_default_uses_stable_values_and_preserves_order(self) -> None:
        config = AppConfig()
        translations = MappingTranslations()

        with (
            patch(
                "goldberg_manager.cli.load_translations",
                return_value=translations,
            ) as load_catalog,
            patch("goldberg_manager.cli.questionary.select") as select,
            patch("goldberg_manager.cli.clear_screen"),
            patch("goldberg_manager.cli.render_header"),
        ):
            select.return_value.ask.return_value = None
            manage_steam_settings_menu(config)

        load_catalog.assert_called_once_with()
        self.assertEqual(select.call_args.args[0], "Gerenciar steam_settings:")
        choices = select.call_args.kwargs["choices"]
        self.assertEqual(
            [choice.title for choice in choices],
            [
                "Ver configuração atual",
                "Editar configuração",
                "Criar / substituir configuração",
                "Backups de configuração",
                "Voltar",
            ],
        )
        self.assertEqual([choice.value for choice in choices], PARENT_VALUES)

    def test_explicit_english_translates_prompt_and_titles(self) -> None:
        with (
            patch("goldberg_manager.cli.load_translations") as load_catalog,
            patch("goldberg_manager.cli.questionary.select") as select,
            patch("goldberg_manager.cli.clear_screen"),
            patch("goldberg_manager.cli.render_header"),
        ):
            select.return_value.ask.return_value = "back"
            manage_steam_settings_menu(
                AppConfig(),
                translations=load_translations("en"),
            )

        load_catalog.assert_not_called()
        self.assertEqual(select.call_args.args[0], "Manage steam_settings:")
        choices = select.call_args.kwargs["choices"]
        self.assertEqual(
            [choice.title for choice in choices],
            [
                "View current configuration",
                "Edit configuration",
                "Create / replace configuration",
                "Configuration backups",
                "Back",
            ],
        )
        self.assertEqual([choice.value for choice in choices], PARENT_VALUES)

    def test_mutation_sibling_dispatch_preserves_exact_calls(self) -> None:
        config = AppConfig()
        game = make_game()
        cases = (
            ("edit", "edit_steam_settings_menu"),
            ("generate", "generate_steam_settings_menu"),
            ("backups", "manage_steam_settings_backups_menu"),
        )

        for value, expected_action in cases:
            with self.subTest(value=value), ExitStack() as stack:
                select = stack.enter_context(
                    patch("goldberg_manager.cli.questionary.select")
                )
                actions = {
                    action: stack.enter_context(patch(f"goldberg_manager.cli.{action}"))
                    for action in PARENT_ACTIONS
                }
                stack.enter_context(patch("goldberg_manager.cli.clear_screen"))
                stack.enter_context(patch("goldberg_manager.cli.render_header"))
                select.return_value.ask.side_effect = [value, "back"]

                manage_steam_settings_menu(
                    config,
                    game,
                    translations=MappingTranslations(),
                )

            actions[expected_action].assert_called_once_with(config, game=game)
            self.assertIs(actions[expected_action].call_args.args[0], config)
            self.assertIs(actions[expected_action].call_args.kwargs["game"], game)
            self.assertEqual(actions[expected_action].call_args.kwargs, {"game": game})
            for action_name, action in actions.items():
                if action_name != expected_action:
                    action.assert_not_called()

    def test_current_dispatch_forwards_only_exact_translations(self) -> None:
        config = AppConfig()
        game = make_game()
        translations = MappingTranslations()

        with (
            patch("goldberg_manager.cli.questionary.select") as select,
            patch("goldberg_manager.cli.show_current_steam_settings_menu") as current,
            patch("goldberg_manager.cli.edit_steam_settings_menu") as edit,
            patch("goldberg_manager.cli.generate_steam_settings_menu") as generate,
            patch("goldberg_manager.cli.manage_steam_settings_backups_menu") as backups,
            patch("goldberg_manager.cli.clear_screen"),
            patch("goldberg_manager.cli.render_header"),
        ):
            select.return_value.ask.side_effect = ["current", "back"]
            manage_steam_settings_menu(
                config,
                game,
                translations=translations,
            )

        current.assert_called_once_with(
            config,
            game=game,
            translations=translations,
        )
        self.assertIs(current.call_args.args[0], config)
        self.assertIs(current.call_args.kwargs["game"], game)
        self.assertIs(current.call_args.kwargs["translations"], translations)
        edit.assert_not_called()
        generate.assert_not_called()
        backups.assert_not_called()

    def test_none_and_back_return_without_dispatch(self) -> None:
        for answer in (None, "back"):
            with self.subTest(answer=answer), ExitStack() as stack:
                select = stack.enter_context(
                    patch("goldberg_manager.cli.questionary.select")
                )
                actions = [
                    stack.enter_context(patch(f"goldberg_manager.cli.{action}"))
                    for action in PARENT_ACTIONS
                ]
                stack.enter_context(patch("goldberg_manager.cli.clear_screen"))
                stack.enter_context(patch("goldberg_manager.cli.render_header"))
                select.return_value.ask.return_value = answer

                manage_steam_settings_menu(
                    AppConfig(),
                    translations=MappingTranslations(),
                )

            for action in actions:
                action.assert_not_called()

    def test_unknown_value_invokes_no_child_and_preserves_loop(self) -> None:
        with ExitStack() as stack:
            select = stack.enter_context(
                patch("goldberg_manager.cli.questionary.select")
            )
            actions = [
                stack.enter_context(patch(f"goldberg_manager.cli.{action}"))
                for action in PARENT_ACTIONS
            ]
            clear_screen = stack.enter_context(
                patch("goldberg_manager.cli.clear_screen")
            )
            stack.enter_context(patch("goldberg_manager.cli.render_header"))
            select.return_value.ask.side_effect = ["unknown", "back"]

            manage_steam_settings_menu(
                AppConfig(),
                translations=MappingTranslations(),
            )

        self.assertEqual(select.call_count, 2)
        self.assertEqual(clear_screen.call_count, 2)
        for action in actions:
            action.assert_not_called()

    def test_duplicate_routing_like_titles_cannot_affect_dispatch(self) -> None:
        translated = "back current edit generate backups:"
        translations = MappingTranslations(
            {
                "Gerenciar steam_settings": translated.removesuffix(":"),
                "Ver configuração atual": translated,
                "Editar configuração": translated,
                "Criar / substituir configuração": translated,
                "Backups de configuração": translated,
                "Voltar": translated,
            }
        )

        with (
            patch("goldberg_manager.cli.questionary.select") as select,
            patch("goldberg_manager.cli.edit_steam_settings_menu") as edit,
            patch("goldberg_manager.cli.show_current_steam_settings_menu") as current,
            patch("goldberg_manager.cli.generate_steam_settings_menu") as generate,
            patch("goldberg_manager.cli.manage_steam_settings_backups_menu") as backups,
            patch("goldberg_manager.cli.clear_screen"),
            patch("goldberg_manager.cli.render_header"),
        ):
            select.return_value.ask.side_effect = ["edit", "back"]
            config = AppConfig()
            game = make_game()
            manage_steam_settings_menu(
                config,
                game,
                translations=translations,
            )

        first_call = select.call_args_list[0]
        self.assertEqual(first_call.args[0], translated)
        self.assertTrue(
            all(choice.title == translated for choice in first_call.kwargs["choices"])
        )
        self.assertEqual(
            [choice.value for choice in first_call.kwargs["choices"]],
            PARENT_VALUES,
        )
        edit.assert_called_once_with(config, game=game)
        current.assert_not_called()
        generate.assert_not_called()
        backups.assert_not_called()

    def test_default_parent_to_real_leaf_loads_once_and_propagates_identity(
        self,
    ) -> None:
        config = AppConfig()
        game = make_game()
        translations = MappingTranslations()

        with (
            patch(
                "goldberg_manager.cli.load_translations",
                return_value=translations,
            ) as load_catalog,
            patch("goldberg_manager.cli.questionary.select") as select,
            patch("goldberg_manager.cli.get_menu_game", return_value=None) as get_game,
            patch("goldberg_manager.cli.read_game_steam_settings") as read_settings,
            patch("goldberg_manager.cli.pause") as pause,
            patch("goldberg_manager.cli.clear_screen"),
            patch("goldberg_manager.cli.render_header"),
        ):
            select.return_value.ask.side_effect = ["current", "back"]
            manage_steam_settings_menu(config, game)

        load_catalog.assert_called_once_with()
        get_game.assert_called_once_with(
            config,
            game,
            "Selecione o jogo para visualizar steam_settings",
            translations=translations,
        )
        self.assertIs(get_game.call_args.args[0], config)
        self.assertIs(get_game.call_args.args[1], game)
        self.assertIs(get_game.call_args.kwargs["translations"], translations)
        read_settings.assert_not_called()
        pause.assert_not_called()


class CurrentSteamSettingsViewTests(unittest.TestCase):
    def test_direct_default_loads_once_and_passes_exact_object_to_game_selection(
        self,
    ) -> None:
        config = AppConfig()
        game = make_game()
        translations = MappingTranslations()

        with (
            patch(
                "goldberg_manager.cli.load_translations",
                return_value=translations,
            ) as load_catalog,
            patch("goldberg_manager.cli.get_menu_game", return_value=None) as get_game,
            patch("goldberg_manager.cli.read_game_steam_settings") as read_settings,
            patch("goldberg_manager.cli.pause") as pause,
            patch("goldberg_manager.cli.clear_screen"),
            patch("goldberg_manager.cli.render_header"),
        ):
            show_current_steam_settings_menu(config, game)

        load_catalog.assert_called_once_with()
        get_game.assert_called_once_with(
            config,
            game,
            "Selecione o jogo para visualizar steam_settings",
            translations=translations,
        )
        self.assertIs(get_game.call_args.kwargs["translations"], translations)
        read_settings.assert_not_called()
        pause.assert_not_called()

    def test_direct_explicit_translations_bypass_loader(self) -> None:
        translations = MappingTranslations()

        with (
            patch("goldberg_manager.cli.load_translations") as load_catalog,
            patch("goldberg_manager.cli.get_menu_game", return_value=None) as get_game,
            patch("goldberg_manager.cli.read_game_steam_settings") as read_settings,
            patch("goldberg_manager.cli.pause") as pause,
            patch("goldberg_manager.cli.clear_screen"),
            patch("goldberg_manager.cli.render_header"),
        ):
            show_current_steam_settings_menu(
                AppConfig(),
                translations=translations,
            )

        load_catalog.assert_not_called()
        self.assertIs(get_game.call_args.kwargs["translations"], translations)
        read_settings.assert_not_called()
        pause.assert_not_called()

    def test_selection_cancellation_returns_before_reader_and_pause(self) -> None:
        with (
            patch("goldberg_manager.cli.get_menu_game", return_value=None),
            patch("goldberg_manager.cli.read_game_steam_settings") as read_settings,
            patch("goldberg_manager.cli.pause") as pause,
            patch("goldberg_manager.cli.clear_screen"),
            patch("goldberg_manager.cli.render_header"),
        ):
            show_current_steam_settings_menu(
                AppConfig(),
                translations=MappingTranslations(),
            )

        read_settings.assert_not_called()
        pause.assert_not_called()

    def test_supplied_game_bypasses_detection_and_selector(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            game = make_game(Path(temp_directory))

            with (
                patch("goldberg_manager.cli.get_detected_games") as get_games,
                patch("goldberg_manager.cli.select_game") as select_game,
                patch(
                    "goldberg_manager.cli.read_game_steam_settings",
                    return_value=SteamSettingsSnapshot(),
                ) as read_settings,
                patch("goldberg_manager.cli.pause") as pause,
                patch("goldberg_manager.cli.console.print"),
                patch("goldberg_manager.cli.clear_screen"),
                patch("goldberg_manager.cli.render_header"),
            ):
                show_current_steam_settings_menu(
                    AppConfig(),
                    game,
                    translations=MappingTranslations(),
                )

        get_games.assert_not_called()
        select_game.assert_not_called()
        read_settings.assert_called_once_with(game)
        pause.assert_called_once_with("Pressione Enter para continuar...")

    def test_complete_real_snapshot_is_literal_and_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory) / "[red]literal-root"
            steam_settings = root / "steam_settings"
            steam_settings.mkdir(parents=True)
            (steam_settings / "steam_appid.txt").write_text(
                "883710\n",
                encoding="utf-8",
            )
            (steam_settings / "configs.user.ini").write_text(
                "[user::general]\n"
                "account_name=[bold]Literal Player[/bold]\n"
                "account_steamid=76561198000000000\n"
                "language=[cyan]brazilian[/cyan]\n"
                "ip_country=[yellow]BR[/yellow]\n"
                "\n"
                "[user::saves]\n"
                "local_save_path=./[magenta]saves[/magenta]\n"
                "saves_folder_name=[blue]Ignored Folder[/blue]\n",
                encoding="utf-8",
            )
            (steam_settings / "steam_interfaces.txt").write_text(
                "SteamClient021\n",
                encoding="utf-8",
            )
            game = make_game(root)
            game.name = "[green]Literal Game[/green]"
            output = StringIO()
            test_console = Console(file=output, width=300, color_system=None)
            translations = MappingTranslations(
                {
                    "Jogo": "[red]literal game label[/red]",
                    "Nick": "[blue]literal nick label[/blue]",
                    "Idioma": "[cyan]literal language label[/cyan]",
                    "País": "[yellow]literal country label[/yellow]",
                    "Saves": "[magenta]literal saves label[/magenta]",
                    "Local/portátil": "[green]literal local label[/green]",
                    "Presente": "[bold]literal present[/bold]",
                    "Configuração atual": "[red]literal panel title[/red]",
                    "Pressione Enter para continuar...": "Translated pause",
                }
            )
            mutation_names = (
                "apply_game_sentinel_repair",
                "backup_game",
                "create_settings_safety_backup",
                "create_steam_settings_backup",
                "generate_game_steam_interfaces",
                "generate_game_steam_settings",
                "import_generated_achievements",
                "restore_game_backup",
                "restore_steam_settings_backup",
                "run_generate_emu_config",
                "save_appid_search_cache",
                "save_config",
                "search_game_on_steam",
                "update_game_steam_appid",
                "update_user_setting",
            )

            with ExitStack() as stack:
                stack.enter_context(
                    patch("goldberg_manager.cli.get_menu_game", return_value=game)
                )
                pause = stack.enter_context(patch("goldberg_manager.cli.pause"))
                stack.enter_context(patch("goldberg_manager.cli.console", test_console))
                stack.enter_context(patch("goldberg_manager.cli.clear_screen"))
                stack.enter_context(patch("goldberg_manager.cli.render_header"))
                mutations = [
                    stack.enter_context(patch(f"goldberg_manager.cli.{name}"))
                    for name in mutation_names
                ]
                path_mkdir = stack.enter_context(patch.object(Path, "mkdir"))
                path_write_text = stack.enter_context(patch.object(Path, "write_text"))
                path_write_bytes = stack.enter_context(
                    patch.object(Path, "write_bytes")
                )
                path_rename = stack.enter_context(patch.object(Path, "rename"))
                path_replace = stack.enter_context(patch.object(Path, "replace"))
                path_unlink = stack.enter_context(patch.object(Path, "unlink"))
                copy = stack.enter_context(patch.object(shutil, "copy"))
                copy2 = stack.enter_context(patch.object(shutil, "copy2"))
                rmtree = stack.enter_context(patch.object(shutil, "rmtree"))
                os_replace = stack.enter_context(
                    patch("goldberg_manager.cli.os.replace")
                )
                run = stack.enter_context(patch("goldberg_manager.cli.subprocess.run"))

                show_current_steam_settings_menu(
                    AppConfig(),
                    game,
                    translations=translations,
                )

            pause.assert_called_once_with("Translated pause")
            for guarded_call in (
                path_mkdir,
                path_write_text,
                path_write_bytes,
                path_rename,
                path_replace,
                path_unlink,
                copy,
                copy2,
                rmtree,
                os_replace,
                run,
                *mutations,
            ):
                guarded_call.assert_not_called()

            rendered = output.getvalue()
            expected_in_order = (
                "[red]literal game label[/red]",
                "AppID",
                "[blue]literal nick label[/blue]",
                "SteamID64",
                "[cyan]literal language label[/cyan]",
                "[yellow]literal country label[/yellow]",
                "[magenta]literal saves label[/magenta]",
                "steam_appid.txt",
                "configs.user.ini",
                "steam_interfaces.txt",
            )
            positions = [rendered.index(value) for value in expected_in_order]
            self.assertEqual(positions, sorted(positions))
            for expected in (
                "[red]literal panel title[/red]",
                "[green]Literal Game[/green]",
                "[bold]Literal Player[/bold]",
                "[cyan]brazilian[/cyan]",
                "[yellow]BR[/yellow]",
                "[green]literal local label[/green]: ./[magenta]saves[/magenta]",
                "[bold]literal present[/bold]",
                str(steam_settings),
            ):
                self.assertIn(expected, rendered)
            self.assertNotIn("Ignored Folder", rendered)

    def test_partial_snapshot_preserves_save_fallbacks_and_placeholders(self) -> None:
        cases = (
            (
                SteamSettingsSnapshot(
                    language="english",
                    saves_folder_name="[red]Custom Saves[/red]",
                    has_steam_interfaces=True,
                ),
                "Global folder: [red]Custom Saves[/red]",
                "english",
            ),
            (
                SteamSettingsSnapshot(has_steam_interfaces=True),
                "Default / not set",
                "(not set)",
            ),
        )

        for snapshot, expected_save, expected_language in cases:
            with self.subTest(expected_save=expected_save):
                with tempfile.TemporaryDirectory() as temp_directory:
                    root = Path(temp_directory)
                    steam_settings = root / "steam_settings"
                    steam_settings.mkdir()
                    (steam_settings / "steam_interfaces.txt").write_text(
                        "SteamClient021\n",
                        encoding="utf-8",
                    )
                    game = make_game(root)
                    output = StringIO()
                    test_console = Console(
                        file=output,
                        width=300,
                        color_system=None,
                    )

                    with (
                        patch(
                            "goldberg_manager.cli.get_menu_game",
                            return_value=game,
                        ),
                        patch(
                            "goldberg_manager.cli.read_game_steam_settings",
                            return_value=snapshot,
                        ),
                        patch("goldberg_manager.cli.pause") as pause,
                        patch("goldberg_manager.cli.console", test_console),
                        patch("goldberg_manager.cli.clear_screen"),
                        patch("goldberg_manager.cli.render_header"),
                    ):
                        show_current_steam_settings_menu(
                            AppConfig(),
                            game,
                            translations=load_translations("en"),
                        )

                pause.assert_called_once_with("Press Enter to continue...")
                rendered = output.getvalue()
                self.assertIn(expected_save, rendered)
                self.assertIn("(not set)", rendered)
                self.assertIn("(not set / automatic)", rendered)
                self.assertIn(expected_language, rendered)

    def test_rich_like_translated_save_labels_are_literal(self) -> None:
        translations = MappingTranslations(
            {
                "Saves": "[magenta]literal saves[/magenta]",
                "Local/portátil": "[red]literal local[/red]",
                "Pasta global": "[blue]literal global[/blue]",
                "Padrão": "[green]literal default[/green]",
                "não definido": "[yellow]literal missing[/yellow]",
            }
        )
        cases = (
            (
                SteamSettingsSnapshot(
                    local_save_path="literal-local-value",
                    has_steam_interfaces=True,
                ),
                "[red]literal local[/red]: literal-local-value",
            ),
            (
                SteamSettingsSnapshot(
                    saves_folder_name="literal-folder-value",
                    has_steam_interfaces=True,
                ),
                "[blue]literal global[/blue]: literal-folder-value",
            ),
            (
                SteamSettingsSnapshot(has_steam_interfaces=True),
                "[green]literal default[/green] / [yellow]literal missing[/yellow]",
            ),
        )

        for snapshot, expected in cases:
            with self.subTest(expected=expected):
                with tempfile.TemporaryDirectory() as temp_directory:
                    root = Path(temp_directory)
                    steam_settings = root / "steam_settings"
                    steam_settings.mkdir()
                    (steam_settings / "steam_interfaces.txt").write_text(
                        "SteamClient021\n",
                        encoding="utf-8",
                    )
                    game = make_game(root)
                    output = StringIO()
                    test_console = Console(
                        file=output,
                        width=300,
                        color_system=None,
                    )

                    with (
                        patch(
                            "goldberg_manager.cli.get_menu_game",
                            return_value=game,
                        ),
                        patch(
                            "goldberg_manager.cli.read_game_steam_settings",
                            return_value=snapshot,
                        ),
                        patch("goldberg_manager.cli.pause"),
                        patch("goldberg_manager.cli.console", test_console),
                        patch("goldberg_manager.cli.clear_screen"),
                        patch("goldberg_manager.cli.render_header"),
                    ):
                        show_current_steam_settings_menu(
                            AppConfig(),
                            game,
                            translations=translations,
                        )

                self.assertIn("[magenta]literal saves[/magenta]", output.getvalue())
                self.assertIn(expected, output.getvalue())

    def test_missing_settings_translates_literal_state_and_pauses_once(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            game = make_game(Path(temp_directory))
            output = StringIO()
            test_console = Console(file=output, width=200, color_system=None)
            translations = MappingTranslations(
                {
                    "Nenhuma configuração steam_settings foi encontrada para este jogo.": (
                        "[red]literal missing state[/red]"
                    ),
                    "Pressione Enter para continuar...": "Translated pause",
                }
            )

            with (
                patch("goldberg_manager.cli.get_menu_game", return_value=game),
                patch(
                    "goldberg_manager.cli.read_game_steam_settings",
                    return_value=SteamSettingsSnapshot(),
                ) as read_settings,
                patch("goldberg_manager.cli.pause") as pause,
                patch("goldberg_manager.cli.console", test_console),
                patch("goldberg_manager.cli.clear_screen"),
                patch("goldberg_manager.cli.render_header"),
            ):
                show_current_steam_settings_menu(
                    AppConfig(),
                    game,
                    translations=translations,
                )

        read_settings.assert_called_once_with(game)
        pause.assert_called_once_with("Translated pause")
        self.assertIn("[red]literal missing state[/red]", output.getvalue())

    def test_handled_reader_errors_are_literal_translated_and_pause_once(self) -> None:
        errors = (
            OSError("[green]literal os error[/green]"),
            FileNotFoundError("[blue]literal missing file[/blue]"),
            ValueError("[magenta]literal invalid value[/magenta]"),
        )

        for error in errors:
            with self.subTest(error=type(error).__name__):
                output = StringIO()
                test_console = Console(file=output, width=200, color_system=None)
                translations = MappingTranslations(
                    {
                        "Erro ao ler steam_settings": (
                            "[red]literal translated framing[/red]"
                        ),
                        "Pressione Enter para continuar...": "Translated pause",
                    }
                )
                game = make_game()

                with (
                    patch("goldberg_manager.cli.get_menu_game", return_value=game),
                    patch(
                        "goldberg_manager.cli.read_game_steam_settings",
                        side_effect=error,
                    ) as read_settings,
                    patch("goldberg_manager.cli.pause") as pause,
                    patch("goldberg_manager.cli.console", test_console),
                    patch("goldberg_manager.cli.clear_screen"),
                    patch("goldberg_manager.cli.render_header"),
                ):
                    show_current_steam_settings_menu(
                        AppConfig(),
                        game,
                        translations=translations,
                    )

                read_settings.assert_called_once_with(game)
                pause.assert_called_once_with("Translated pause")
                self.assertIn(
                    "[red]literal translated framing[/red]:",
                    output.getvalue(),
                )
                self.assertIn(str(error), output.getvalue())

    def test_unexpected_reader_error_propagates_without_pause(self) -> None:
        game = make_game()
        error = RuntimeError("unexpected reader failure")

        with (
            patch("goldberg_manager.cli.get_menu_game", return_value=game),
            patch(
                "goldberg_manager.cli.read_game_steam_settings",
                side_effect=error,
            ),
            patch("goldberg_manager.cli.pause") as pause,
            patch("goldberg_manager.cli.clear_screen"),
            patch("goldberg_manager.cli.render_header"),
            self.assertRaises(RuntimeError) as raised,
        ):
            show_current_steam_settings_menu(
                AppConfig(),
                game,
                translations=MappingTranslations(),
            )

        self.assertIs(raised.exception, error)
        pause.assert_not_called()


if __name__ == "__main__":
    unittest.main()
