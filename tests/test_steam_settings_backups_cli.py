from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from contextlib import ExitStack
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path
from unittest.mock import Mock, patch

from rich.console import Console
from rich.text import Text

from goldberg_manager.cli import (
    create_steam_settings_backup_menu,
    get_menu_game,
    list_steam_settings_backups_menu,
    manage_steam_settings_backups_menu,
    manage_steam_settings_menu,
    restore_steam_settings_backup_menu,
)
from goldberg_manager.config import AppConfig
from goldberg_manager.core.game import Game
from goldberg_manager.presentation.i18n import load_translations
from goldberg_manager.settings_backup import (
    SteamSettingsBackup,
    create_steam_settings_backup,
    list_steam_settings_backups,
)


class MappingTranslations:
    def __init__(self, messages: dict[str, str] | None = None) -> None:
        self.messages = messages or {}

    def gettext(self, message: str) -> str:
        return self.messages.get(message, message)


def make_game(
    root: Path = Path("/games/Example"),
    *,
    name: str = "Example Game",
) -> Game:
    return Game(
        name=name,
        root_directory=root,
        executable=root / "Game.exe",
        steam_api=root / "steam_api64.dll",
        steam_api_relative_path=Path("steam_api64.dll"),
        architecture="64-bit",
        source_directory=root.parent,
    )


def make_settings_backup(
    path: Path = Path("/backups/Example/steam_settings/snapshot"),
    *,
    created_at: datetime = datetime(2026, 8, 30, 21, 22, 23, tzinfo=UTC),
    file_count: int = 3,
    valid: bool = True,
) -> SteamSettingsBackup:
    return SteamSettingsBackup(
        path=path,
        created_at=created_at,
        file_count=file_count,
        valid=valid,
    )


SUBMENU_VALUES = ["create", "list", "restore", "back"]
SUBMENU_ACTIONS = (
    "create_steam_settings_backup_menu",
    "list_steam_settings_backups_menu",
    "restore_steam_settings_backup_menu",
)
UNRELATED_MUTATIONS = (
    "apply_game_sentinel_repair",
    "backup_game",
    "generate_game_steam_interfaces",
    "import_generated_achievements",
    "restore_game_backup",
    "restore_steam_settings_backup",
    "run_generate_emu_config",
    "save_appid_search_cache",
    "save_config",
    "update_game_steam_appid",
    "update_user_setting",
)
RESTORE_UNRELATED_MUTATIONS = tuple(
    name for name in UNRELATED_MUTATIONS if name != "restore_steam_settings_backup"
) + (
    "create_settings_safety_backup",
    "generate_game_steam_settings",
)


class SteamSettingsBackupsRoutingTests(unittest.TestCase):
    def test_portuguese_default_loads_once_and_uses_stable_values(self) -> None:
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
            manage_steam_settings_backups_menu(AppConfig())

        load_catalog.assert_called_once_with()
        self.assertEqual(select.call_args.args[0], "Backups de steam_settings:")
        choices = select.call_args.kwargs["choices"]
        self.assertEqual(
            [choice.title for choice in choices],
            [
                "Criar backup agora",
                "Ver backups",
                "Restaurar backup",
                "Voltar",
            ],
        )
        self.assertEqual([choice.value for choice in choices], SUBMENU_VALUES)

    def test_explicit_english_bypasses_loader_and_translates_shell(self) -> None:
        with (
            patch("goldberg_manager.cli.load_translations") as load_catalog,
            patch("goldberg_manager.cli.questionary.select") as select,
            patch("goldberg_manager.cli.clear_screen"),
            patch("goldberg_manager.cli.render_header"),
        ):
            select.return_value.ask.return_value = "back"
            manage_steam_settings_backups_menu(
                AppConfig(),
                translations=load_translations("en"),
            )

        load_catalog.assert_not_called()
        self.assertEqual(select.call_args.args[0], "steam_settings backups:")
        choices = select.call_args.kwargs["choices"]
        self.assertEqual(
            [choice.title for choice in choices],
            ["Create backup now", "View backups", "Restore backup", "Back"],
        )
        self.assertEqual([choice.value for choice in choices], SUBMENU_VALUES)

    def test_create_dispatch_forwards_exact_translation_identity(self) -> None:
        config = AppConfig()
        game = make_game()
        translations = MappingTranslations()

        with (
            patch("goldberg_manager.cli.questionary.select") as select,
            patch("goldberg_manager.cli.create_steam_settings_backup_menu") as create,
            patch("goldberg_manager.cli.list_steam_settings_backups_menu") as list_menu,
            patch("goldberg_manager.cli.restore_steam_settings_backup_menu") as restore,
            patch("goldberg_manager.cli.clear_screen"),
            patch("goldberg_manager.cli.render_header"),
        ):
            select.return_value.ask.side_effect = ["create", "back"]
            manage_steam_settings_backups_menu(
                config,
                game,
                translations=translations,
            )

        create.assert_called_once_with(
            config,
            game=game,
            translations=translations,
        )
        self.assertIs(create.call_args.args[0], config)
        self.assertIs(create.call_args.kwargs["game"], game)
        self.assertIs(create.call_args.kwargs["translations"], translations)
        list_menu.assert_not_called()
        restore.assert_not_called()

    def test_restore_dispatch_forwards_exact_translation_identity(self) -> None:
        config = AppConfig()
        game = make_game()
        translations = MappingTranslations()

        with (
            patch("goldberg_manager.cli.questionary.select") as select,
            patch("goldberg_manager.cli.create_steam_settings_backup_menu") as create,
            patch("goldberg_manager.cli.list_steam_settings_backups_menu") as list_menu,
            patch("goldberg_manager.cli.restore_steam_settings_backup_menu") as restore,
            patch("goldberg_manager.cli.clear_screen"),
            patch("goldberg_manager.cli.render_header"),
        ):
            select.return_value.ask.side_effect = ["restore", "back"]
            manage_steam_settings_backups_menu(
                config,
                game,
                translations=translations,
            )

        restore.assert_called_once_with(
            config,
            game=game,
            translations=translations,
        )
        self.assertIs(restore.call_args.args[0], config)
        self.assertIs(restore.call_args.kwargs["game"], game)
        self.assertIs(restore.call_args.kwargs["translations"], translations)
        create.assert_not_called()
        list_menu.assert_not_called()

    def test_list_dispatch_forwards_exact_translation_identity(self) -> None:
        config = AppConfig()
        game = make_game()
        translations = MappingTranslations()

        with (
            patch("goldberg_manager.cli.questionary.select") as select,
            patch("goldberg_manager.cli.create_steam_settings_backup_menu") as create,
            patch("goldberg_manager.cli.list_steam_settings_backups_menu") as list_menu,
            patch("goldberg_manager.cli.restore_steam_settings_backup_menu") as restore,
            patch("goldberg_manager.cli.clear_screen"),
            patch("goldberg_manager.cli.render_header"),
        ):
            select.return_value.ask.side_effect = ["list", "back"]
            manage_steam_settings_backups_menu(
                config,
                game,
                translations=translations,
            )

        list_menu.assert_called_once_with(
            config,
            game=game,
            translations=translations,
        )
        self.assertIs(list_menu.call_args.args[0], config)
        self.assertIs(list_menu.call_args.kwargs["game"], game)
        self.assertIs(list_menu.call_args.kwargs["translations"], translations)
        create.assert_not_called()
        restore.assert_not_called()

    def test_none_and_back_return_without_dispatch(self) -> None:
        for answer in (None, "back"):
            with self.subTest(answer=answer), ExitStack() as stack:
                select = stack.enter_context(
                    patch("goldberg_manager.cli.questionary.select")
                )
                actions = [
                    stack.enter_context(patch(f"goldberg_manager.cli.{action}"))
                    for action in SUBMENU_ACTIONS
                ]
                stack.enter_context(patch("goldberg_manager.cli.clear_screen"))
                stack.enter_context(patch("goldberg_manager.cli.render_header"))
                select.return_value.ask.return_value = answer

                manage_steam_settings_backups_menu(
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
                for action in SUBMENU_ACTIONS
            ]
            clear_screen = stack.enter_context(
                patch("goldberg_manager.cli.clear_screen")
            )
            stack.enter_context(patch("goldberg_manager.cli.render_header"))
            select.return_value.ask.side_effect = ["unknown", "back"]

            manage_steam_settings_backups_menu(
                AppConfig(),
                translations=MappingTranslations(),
            )

        self.assertEqual(select.call_count, 2)
        self.assertEqual(clear_screen.call_count, 2)
        for action in actions:
            action.assert_not_called()

    def test_duplicate_routing_like_titles_cannot_affect_dispatch(self) -> None:
        translated = "create list restore back"
        translations = MappingTranslations(
            {
                "Backups de steam_settings": translated,
                "Criar backup agora": translated,
                "Ver backups": translated,
                "Restaurar backup": translated,
                "Voltar": translated,
            }
        )

        with (
            patch("goldberg_manager.cli.questionary.select") as select,
            patch("goldberg_manager.cli.create_steam_settings_backup_menu") as create,
            patch("goldberg_manager.cli.list_steam_settings_backups_menu") as list_menu,
            patch("goldberg_manager.cli.restore_steam_settings_backup_menu") as restore,
            patch("goldberg_manager.cli.clear_screen"),
            patch("goldberg_manager.cli.render_header"),
        ):
            select.return_value.ask.side_effect = ["create", "back"]
            config = AppConfig()
            game = make_game()
            manage_steam_settings_backups_menu(
                config,
                game,
                translations=translations,
            )

        first_call = select.call_args_list[0]
        self.assertEqual(first_call.args[0], f"{translated}:")
        self.assertTrue(
            all(choice.title == translated for choice in first_call.kwargs["choices"])
        )
        self.assertEqual(
            [choice.value for choice in first_call.kwargs["choices"]],
            SUBMENU_VALUES,
        )
        create.assert_called_once_with(
            config,
            game=game,
            translations=translations,
        )
        list_menu.assert_not_called()
        restore.assert_not_called()

    def test_default_submenu_to_real_list_loads_once_and_preserves_identity(
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
            patch("goldberg_manager.cli.list_steam_settings_backups") as list_backups,
            patch("goldberg_manager.cli.pause") as pause,
            patch("goldberg_manager.cli.clear_screen"),
            patch("goldberg_manager.cli.render_header"),
        ):
            select.return_value.ask.side_effect = ["list", "back"]
            manage_steam_settings_backups_menu(config, game)

        load_catalog.assert_called_once_with()
        get_game.assert_called_once_with(
            config,
            game,
            "Selecione o jogo para listar os backups:",
            translations=translations,
        )
        self.assertIs(get_game.call_args.kwargs["translations"], translations)
        list_backups.assert_not_called()
        pause.assert_not_called()

    def test_default_parent_to_real_list_loads_once_and_preserves_identity(
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
            patch("goldberg_manager.cli.list_steam_settings_backups") as list_backups,
            patch("goldberg_manager.cli.pause") as pause,
            patch("goldberg_manager.cli.clear_screen"),
            patch("goldberg_manager.cli.render_header"),
        ):
            select.return_value.ask.side_effect = ["backups", "list", "back", "back"]
            manage_steam_settings_menu(config, game)

        load_catalog.assert_called_once_with()
        get_game.assert_called_once_with(
            config,
            game,
            "Selecione o jogo para listar os backups:",
            translations=translations,
        )
        self.assertIs(get_game.call_args.kwargs["translations"], translations)
        list_backups.assert_not_called()
        pause.assert_not_called()


class SteamSettingsBackupRestorationTests(unittest.TestCase):
    def test_default_parent_to_real_restore_loads_once_and_preserves_identity(
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
            patch("goldberg_manager.cli.list_steam_settings_backups") as list_backups,
            patch("goldberg_manager.cli.questionary.confirm") as confirm,
            patch("goldberg_manager.cli.pause") as pause,
            patch("goldberg_manager.cli.clear_screen"),
            patch("goldberg_manager.cli.render_header"),
        ):
            select.return_value.ask.side_effect = [
                "backups",
                "restore",
                "back",
                "back",
            ]
            manage_steam_settings_menu(config, game)

        load_catalog.assert_called_once_with()
        get_game.assert_called_once_with(
            config,
            game,
            "Selecione o jogo cujo backup deseja restaurar:",
            translations=translations,
        )
        self.assertIs(get_game.call_args.kwargs["translations"], translations)
        list_backups.assert_not_called()
        confirm.assert_not_called()
        pause.assert_not_called()

    def test_direct_default_loads_once_and_passes_identity_to_game_selection(
        self,
    ) -> None:
        config = AppConfig()
        translations = MappingTranslations()

        with (
            patch(
                "goldberg_manager.cli.load_translations",
                return_value=translations,
            ) as load_catalog,
            patch("goldberg_manager.cli.get_menu_game", return_value=None) as get_game,
            patch("goldberg_manager.cli.list_steam_settings_backups") as list_backups,
            patch("goldberg_manager.cli.questionary.confirm") as confirm,
            patch("goldberg_manager.cli.console.print") as console_print,
            patch("goldberg_manager.cli.pause") as pause,
            patch("goldberg_manager.cli.clear_screen"),
            patch("goldberg_manager.cli.render_header"),
        ):
            restore_steam_settings_backup_menu(config)

        load_catalog.assert_called_once_with()
        get_game.assert_called_once_with(
            config,
            None,
            "Selecione o jogo cujo backup deseja restaurar:",
            translations=translations,
        )
        self.assertIs(get_game.call_args.kwargs["translations"], translations)
        list_backups.assert_not_called()
        confirm.assert_not_called()
        console_print.assert_not_called()
        pause.assert_not_called()

    def test_explicit_translations_bypass_loader(self) -> None:
        translations = MappingTranslations()

        with (
            patch("goldberg_manager.cli.load_translations") as load_catalog,
            patch("goldberg_manager.cli.get_menu_game", return_value=None) as get_game,
            patch("goldberg_manager.cli.list_steam_settings_backups") as list_backups,
            patch("goldberg_manager.cli.pause") as pause,
            patch("goldberg_manager.cli.clear_screen"),
            patch("goldberg_manager.cli.render_header"),
        ):
            restore_steam_settings_backup_menu(
                AppConfig(),
                translations=translations,
            )

        load_catalog.assert_not_called()
        self.assertIs(get_game.call_args.kwargs["translations"], translations)
        list_backups.assert_not_called()
        pause.assert_not_called()

    def test_supplied_game_bypasses_detection_and_preserves_empty_state(self) -> None:
        config = AppConfig()
        game = make_game()
        translations = MappingTranslations()

        with (
            patch("goldberg_manager.cli.get_detected_games") as get_games,
            patch("goldberg_manager.cli.select_game") as select_game,
            patch(
                "goldberg_manager.cli.get_menu_game",
                wraps=get_menu_game,
            ) as get_game,
            patch(
                "goldberg_manager.cli.list_steam_settings_backups",
                return_value=[],
            ) as list_backups,
            patch("goldberg_manager.cli.questionary.confirm") as confirm,
            patch("goldberg_manager.cli.console.print"),
            patch("goldberg_manager.cli.pause") as pause,
            patch("goldberg_manager.cli.clear_screen"),
            patch("goldberg_manager.cli.render_header"),
        ):
            restore_steam_settings_backup_menu(
                config,
                game,
                translations=translations,
            )

        get_game.assert_called_once_with(
            config,
            game,
            "Selecione o jogo cujo backup deseja restaurar:",
            translations=translations,
        )
        self.assertIs(get_game.call_args.args[0], config)
        self.assertIs(get_game.call_args.args[1], game)
        get_games.assert_not_called()
        select_game.assert_not_called()
        list_backups.assert_called_once_with(game)
        confirm.assert_not_called()
        pause.assert_called_once_with("Pressione Enter para continuar...")

    def test_game_selection_cancellation_stops_before_read_or_mutation(self) -> None:
        with ExitStack() as stack:
            stack.enter_context(
                patch("goldberg_manager.cli.get_menu_game", return_value=None)
            )
            list_backups = stack.enter_context(
                patch("goldberg_manager.cli.list_steam_settings_backups")
            )
            confirm = stack.enter_context(
                patch("goldberg_manager.cli.questionary.confirm")
            )
            create = stack.enter_context(
                patch("goldberg_manager.cli.create_steam_settings_backup")
            )
            restore = stack.enter_context(
                patch("goldberg_manager.cli.restore_steam_settings_backup")
            )
            console_print = stack.enter_context(
                patch("goldberg_manager.cli.console.print")
            )
            pause = stack.enter_context(patch("goldberg_manager.cli.pause"))
            stack.enter_context(patch("goldberg_manager.cli.clear_screen"))
            stack.enter_context(patch("goldberg_manager.cli.render_header"))
            unrelated = [
                stack.enter_context(patch(f"goldberg_manager.cli.{name}"))
                for name in RESTORE_UNRELATED_MUTATIONS
            ]

            restore_steam_settings_backup_menu(
                AppConfig(),
                translations=MappingTranslations(),
            )

        list_backups.assert_not_called()
        confirm.assert_not_called()
        create.assert_not_called()
        restore.assert_not_called()
        console_print.assert_not_called()
        pause.assert_not_called()
        for mutation in unrelated:
            mutation.assert_not_called()

    def test_listing_oserror_is_translated_literal_and_pauses_once(self) -> None:
        error = OSError("[green]literal listing failure[/green]")
        translations = MappingTranslations(
            {
                "Não foi possível listar os backups": (
                    "[red]literal listing framing[/red]"
                ),
                "Pressione Enter para continuar...": "Translated pause",
            }
        )
        output = StringIO()
        test_console = Console(file=output, width=240, color_system=None)

        with (
            patch("goldberg_manager.cli.get_menu_game", return_value=make_game()),
            patch(
                "goldberg_manager.cli.list_steam_settings_backups",
                side_effect=error,
            ) as list_backups,
            patch("goldberg_manager.cli.questionary.select") as select,
            patch("goldberg_manager.cli.questionary.confirm") as confirm,
            patch("goldberg_manager.cli.create_steam_settings_backup") as create,
            patch("goldberg_manager.cli.restore_steam_settings_backup") as restore,
            patch("goldberg_manager.cli.console", test_console),
            patch("goldberg_manager.cli.pause") as pause,
            patch("goldberg_manager.cli.clear_screen"),
            patch("goldberg_manager.cli.render_header"),
        ):
            restore_steam_settings_backup_menu(
                AppConfig(),
                translations=translations,
            )

        list_backups.assert_called_once()
        self.assertIn(
            "[red]literal listing framing[/red]: "
            "[green]literal listing failure[/green]",
            output.getvalue(),
        )
        pause.assert_called_once_with("Translated pause")
        select.assert_not_called()
        confirm.assert_not_called()
        create.assert_not_called()
        restore.assert_not_called()

    def test_explicit_english_empty_listing_stops_before_selection(self) -> None:
        output = StringIO()
        test_console = Console(file=output, width=240, color_system=None)

        with (
            patch("goldberg_manager.cli.get_menu_game", return_value=make_game()),
            patch(
                "goldberg_manager.cli.list_steam_settings_backups",
                return_value=[],
            ),
            patch("goldberg_manager.cli.questionary.select") as select,
            patch("goldberg_manager.cli.questionary.confirm") as confirm,
            patch("goldberg_manager.cli.create_steam_settings_backup") as create,
            patch("goldberg_manager.cli.restore_steam_settings_backup") as restore,
            patch("goldberg_manager.cli.console", test_console),
            patch("goldberg_manager.cli.pause") as pause,
            patch("goldberg_manager.cli.clear_screen"),
            patch("goldberg_manager.cli.render_header"),
        ):
            restore_steam_settings_backup_menu(
                AppConfig(),
                translations=load_translations("en"),
            )

        self.assertIn(
            "No steam_settings backups were found for this game.",
            output.getvalue(),
        )
        pause.assert_called_once_with("Press Enter to continue...")
        select.assert_not_called()
        confirm.assert_not_called()
        create.assert_not_called()
        restore.assert_not_called()

    def test_snapshot_choices_use_stable_values_and_exact_selected_path(self) -> None:
        game = make_game()
        created_at = datetime(2026, 8, 30, 21, 22, 23, tzinfo=UTC)
        backups = [
            make_settings_backup(
                Path("/backups/newer"),
                created_at=created_at,
            ),
            make_settings_backup(
                Path("/backups/older"),
                created_at=created_at,
            ),
        ]
        translated = "restore back 0 1 [red]literal[/red]"
        timestamp = created_at.astimezone().strftime("%d/%m/%Y %H:%M:%S")
        duplicate_title = f"2 - {timestamp} • {translated} • {translated}"
        translations = MappingTranslations(
            {
                "Selecione o backup:": translated,
                "{count} arquivos": translated,
                "Íntegro": translated,
                "Voltar": duplicate_title,
            }
        )

        with (
            patch("goldberg_manager.cli.get_menu_game", return_value=game),
            patch(
                "goldberg_manager.cli.list_steam_settings_backups",
                return_value=backups,
            ),
            patch("goldberg_manager.cli.questionary.select") as select,
            patch("goldberg_manager.cli.questionary.confirm") as confirm,
            patch(
                "goldberg_manager.cli.get_steam_settings_directory",
                return_value=Path("/missing/current/steam_settings"),
            ),
            patch("goldberg_manager.cli.create_steam_settings_backup") as create,
            patch(
                "goldberg_manager.cli.restore_steam_settings_backup",
                return_value=Path("/restored/steam_settings"),
            ) as restore,
            patch("goldberg_manager.cli.console.print"),
            patch("goldberg_manager.cli.pause"),
            patch("goldberg_manager.cli.clear_screen"),
            patch("goldberg_manager.cli.render_header"),
        ):
            select.return_value.ask.return_value = 1
            confirm.return_value.ask.return_value = True
            restore_steam_settings_backup_menu(
                AppConfig(),
                translations=translations,
            )

        self.assertEqual(select.call_args.args[0], translated)
        choices = select.call_args.kwargs["choices"]
        self.assertEqual([choice.value for choice in choices], [0, 1, "back"])
        self.assertTrue(choices[0].title.startswith("1 - "))
        self.assertTrue(choices[1].title.startswith("2 - "))
        self.assertEqual(choices[1].title, choices[-1].title)
        create.assert_not_called()
        restore.assert_called_once_with(game, backups[1].path)
        self.assertIs(restore.call_args.args[0], game)
        self.assertIs(restore.call_args.args[1], backups[1].path)
        self.assertEqual(restore.call_args.kwargs, {})

    def test_none_and_back_snapshot_selection_are_silent(self) -> None:
        for answer in (None, "back"):
            with self.subTest(answer=answer), ExitStack() as stack:
                game = make_game()
                backup = make_settings_backup()
                stack.enter_context(
                    patch("goldberg_manager.cli.get_menu_game", return_value=game)
                )
                stack.enter_context(
                    patch(
                        "goldberg_manager.cli.list_steam_settings_backups",
                        return_value=[backup],
                    )
                )
                select = stack.enter_context(
                    patch("goldberg_manager.cli.questionary.select")
                )
                select.return_value.ask.return_value = answer
                confirm = stack.enter_context(
                    patch("goldberg_manager.cli.questionary.confirm")
                )
                create = stack.enter_context(
                    patch("goldberg_manager.cli.create_steam_settings_backup")
                )
                restore = stack.enter_context(
                    patch("goldberg_manager.cli.restore_steam_settings_backup")
                )
                console_print = stack.enter_context(
                    patch("goldberg_manager.cli.console.print")
                )
                pause = stack.enter_context(patch("goldberg_manager.cli.pause"))
                stack.enter_context(patch("goldberg_manager.cli.clear_screen"))
                stack.enter_context(patch("goldberg_manager.cli.render_header"))

                restore_steam_settings_backup_menu(
                    AppConfig(),
                    translations=MappingTranslations(),
                )

            confirm.assert_not_called()
            create.assert_not_called()
            restore.assert_not_called()
            console_print.assert_not_called()
            pause.assert_not_called()

    def test_corrupted_snapshot_warns_and_stops_before_confirmation(self) -> None:
        translations = MappingTranslations(
            {
                "Este backup está corrompido e não pode ser restaurado.": (
                    "[red]literal corrupted warning[/red]"
                ),
                "Pressione Enter para continuar...": "Translated pause",
            }
        )
        output = StringIO()
        test_console = Console(file=output, width=240, color_system=None)

        with (
            patch("goldberg_manager.cli.get_menu_game", return_value=make_game()),
            patch(
                "goldberg_manager.cli.list_steam_settings_backups",
                return_value=[make_settings_backup(valid=False)],
            ),
            patch("goldberg_manager.cli.questionary.select") as select,
            patch("goldberg_manager.cli.questionary.confirm") as confirm,
            patch("goldberg_manager.cli.create_steam_settings_backup") as create,
            patch("goldberg_manager.cli.restore_steam_settings_backup") as restore,
            patch("goldberg_manager.cli.console", test_console),
            patch("goldberg_manager.cli.pause") as pause,
            patch("goldberg_manager.cli.clear_screen"),
            patch("goldberg_manager.cli.render_header"),
        ):
            select.return_value.ask.return_value = 0
            restore_steam_settings_backup_menu(
                AppConfig(),
                translations=translations,
            )

        self.assertIn("[red]literal corrupted warning[/red]", output.getvalue())
        pause.assert_called_once_with("Translated pause")
        confirm.assert_not_called()
        create.assert_not_called()
        restore.assert_not_called()

    def test_english_summary_translates_labels_and_preserves_dynamic_values(
        self,
    ) -> None:
        game = make_game(name="[bold]Literal Game[/bold]")
        backup = make_settings_backup(file_count=17)
        timestamp = backup.created_at.astimezone().strftime("%d/%m/%Y %H:%M:%S")
        output = StringIO()
        test_console = Console(file=output, width=240, color_system=None)

        with (
            patch("goldberg_manager.cli.get_menu_game", return_value=game),
            patch(
                "goldberg_manager.cli.list_steam_settings_backups",
                return_value=[backup],
            ),
            patch("goldberg_manager.cli.questionary.select") as select,
            patch("goldberg_manager.cli.questionary.confirm") as confirm,
            patch("goldberg_manager.cli.create_steam_settings_backup") as create,
            patch("goldberg_manager.cli.restore_steam_settings_backup") as restore,
            patch("goldberg_manager.cli.console", test_console),
            patch("goldberg_manager.cli.pause") as pause,
            patch("goldberg_manager.cli.clear_screen"),
            patch("goldberg_manager.cli.render_header"),
        ):
            select.return_value.ask.return_value = 0
            confirm.return_value.ask.return_value = False
            restore_steam_settings_backup_menu(
                AppConfig(),
                translations=load_translations("en"),
            )

        self.assertEqual(select.call_args.args[0], "Select the backup:")
        self.assertIn("17 files", select.call_args.kwargs["choices"][0].title)
        confirm.assert_called_once_with(
            "Restore this snapshot? The current configuration will be replaced.",
            default=False,
        )
        rendered = output.getvalue()
        for expected in (
            "Game",
            "Backup",
            "Files",
            "Integrity",
            "Valid",
            "Restore backup",
            "[bold]Literal Game[/bold]",
            timestamp,
            "17",
        ):
            self.assertIn(expected, rendered)
        create.assert_not_called()
        restore.assert_not_called()
        pause.assert_not_called()

    def test_false_and_none_confirmation_cancel_without_mutation_or_pause(
        self,
    ) -> None:
        for answer in (False, None):
            with self.subTest(answer=answer), ExitStack() as stack:
                game = make_game()
                stack.enter_context(
                    patch("goldberg_manager.cli.get_menu_game", return_value=game)
                )
                stack.enter_context(
                    patch(
                        "goldberg_manager.cli.list_steam_settings_backups",
                        return_value=[make_settings_backup()],
                    )
                )
                select = stack.enter_context(
                    patch("goldberg_manager.cli.questionary.select")
                )
                select.return_value.ask.return_value = 0
                confirm = stack.enter_context(
                    patch("goldberg_manager.cli.questionary.confirm")
                )
                confirm.return_value.ask.return_value = answer
                get_settings = stack.enter_context(
                    patch("goldberg_manager.cli.get_steam_settings_directory")
                )
                create = stack.enter_context(
                    patch("goldberg_manager.cli.create_steam_settings_backup")
                )
                restore = stack.enter_context(
                    patch("goldberg_manager.cli.restore_steam_settings_backup")
                )
                console_print = stack.enter_context(
                    patch("goldberg_manager.cli.console.print")
                )
                pause = stack.enter_context(patch("goldberg_manager.cli.pause"))
                stack.enter_context(patch("goldberg_manager.cli.clear_screen"))
                stack.enter_context(patch("goldberg_manager.cli.render_header"))
                unrelated = [
                    stack.enter_context(patch(f"goldberg_manager.cli.{name}"))
                    for name in RESTORE_UNRELATED_MUTATIONS
                ]

                restore_steam_settings_backup_menu(
                    AppConfig(),
                    translations=MappingTranslations(),
                )

            confirm.assert_called_once_with(
                "Restaurar este snapshot? A configuração atual será substituída.",
                default=False,
            )
            get_settings.assert_not_called()
            create.assert_not_called()
            restore.assert_not_called()
            pause.assert_not_called()
            rendered_values = " ".join(
                str(call) for call in console_print.call_args_list
            )
            self.assertNotIn("restaurado com sucesso", rendered_values)
            self.assertNotIn("A restauração foi cancelada", rendered_values)
            for mutation in unrelated:
                mutation.assert_not_called()

    def test_success_preserves_consent_writer_order_and_exact_call_shapes(
        self,
    ) -> None:
        game = make_game()
        backup = make_settings_backup()
        safety_path = Path("/backups/safety-snapshot")
        restored_path = Path("/game/steam_settings")
        translations = MappingTranslations()
        events: list[tuple[str, object]] = []
        answer = Mock()
        answer.ask.side_effect = lambda: events.append(("ask", None)) or True

        def record_confirm(prompt, *, default):
            events.append(("confirm", (prompt, default)))
            return answer

        def record_create(supplied_game):
            events.append(("create", supplied_game))
            return safety_path

        def record_restore(supplied_game, supplied_path):
            events.append(("restore", (supplied_game, supplied_path)))
            return restored_path

        def record_print(*values):
            if (
                values
                and isinstance(values[0], Text)
                and values[0].plain == "steam_settings restaurado com sucesso!"
            ):
                events.append(("success", values[0].plain))

        with tempfile.TemporaryDirectory() as temp_directory, ExitStack() as stack:
            current_settings = Path(temp_directory) / "steam_settings"
            current_settings.mkdir()
            stack.enter_context(
                patch("goldberg_manager.cli.get_menu_game", return_value=game)
            )
            stack.enter_context(
                patch(
                    "goldberg_manager.cli.list_steam_settings_backups",
                    return_value=[backup],
                )
            )
            select = stack.enter_context(
                patch("goldberg_manager.cli.questionary.select")
            )
            select.return_value.ask.return_value = 0
            confirm = stack.enter_context(
                patch(
                    "goldberg_manager.cli.questionary.confirm",
                    side_effect=record_confirm,
                )
            )
            stack.enter_context(
                patch(
                    "goldberg_manager.cli.get_steam_settings_directory",
                    return_value=current_settings,
                )
            )
            create = stack.enter_context(
                patch(
                    "goldberg_manager.cli.create_steam_settings_backup",
                    side_effect=record_create,
                )
            )
            restore = stack.enter_context(
                patch(
                    "goldberg_manager.cli.restore_steam_settings_backup",
                    side_effect=record_restore,
                )
            )
            stack.enter_context(
                patch("goldberg_manager.cli.console.print", side_effect=record_print)
            )
            pause = stack.enter_context(
                patch(
                    "goldberg_manager.cli.pause",
                    side_effect=lambda prompt: events.append(("pause", prompt)),
                )
            )
            stack.enter_context(patch("goldberg_manager.cli.clear_screen"))
            stack.enter_context(patch("goldberg_manager.cli.render_header"))
            unrelated = [
                stack.enter_context(patch(f"goldberg_manager.cli.{name}"))
                for name in RESTORE_UNRELATED_MUTATIONS
            ]

            restore_steam_settings_backup_menu(
                AppConfig(),
                translations=translations,
            )

        confirm.assert_called_once_with(
            "Restaurar este snapshot? A configuração atual será substituída.",
            default=False,
        )
        create.assert_called_once_with(game)
        self.assertEqual(create.call_args.kwargs, {})
        restore.assert_called_once_with(game, backup.path)
        self.assertIs(restore.call_args.args[0], game)
        self.assertIs(restore.call_args.args[1], backup.path)
        self.assertEqual(restore.call_args.kwargs, {})
        pause.assert_called_once_with("Pressione Enter para continuar...")
        self.assertEqual(
            events,
            [
                (
                    "confirm",
                    (
                        "Restaurar este snapshot? A configuração atual será substituída.",
                        False,
                    ),
                ),
                ("ask", None),
                ("create", game),
                ("restore", (game, backup.path)),
                ("success", "steam_settings restaurado com sucesso!"),
                ("pause", "Pressione Enter para continuar..."),
            ],
        )
        for mutation in unrelated:
            mutation.assert_not_called()

    def test_missing_current_settings_skips_only_safety_backup(self) -> None:
        game = make_game()
        backup = make_settings_backup()

        with tempfile.TemporaryDirectory() as temp_directory:
            missing_settings = Path(temp_directory) / "missing-steam_settings"
            with (
                patch("goldberg_manager.cli.get_menu_game", return_value=game),
                patch(
                    "goldberg_manager.cli.list_steam_settings_backups",
                    return_value=[backup],
                ),
                patch("goldberg_manager.cli.questionary.select") as select,
                patch("goldberg_manager.cli.questionary.confirm") as confirm,
                patch(
                    "goldberg_manager.cli.get_steam_settings_directory",
                    return_value=missing_settings,
                ),
                patch("goldberg_manager.cli.create_steam_settings_backup") as create,
                patch(
                    "goldberg_manager.cli.restore_steam_settings_backup",
                    return_value=missing_settings,
                ) as restore,
                patch("goldberg_manager.cli.console.print"),
                patch("goldberg_manager.cli.pause"),
                patch("goldberg_manager.cli.clear_screen"),
                patch("goldberg_manager.cli.render_header"),
            ):
                select.return_value.ask.return_value = 0
                confirm.return_value.ask.return_value = True
                restore_steam_settings_backup_menu(
                    AppConfig(),
                    translations=MappingTranslations(),
                )

        create.assert_not_called()
        restore.assert_called_once_with(game, backup.path)
        self.assertEqual(restore.call_args.kwargs, {})

    def test_handled_safety_backup_failures_cancel_before_restore(self) -> None:
        errors = (
            FileNotFoundError("[red]missing settings[/red]"),
            OSError("[red]filesystem failure[/red]"),
            ValueError("[red]invalid settings[/red]"),
        )

        for error in errors:
            with self.subTest(error=type(error).__name__):
                output = StringIO()
                test_console = Console(file=output, width=240, color_system=None)
                game = make_game()
                translations = MappingTranslations(
                    {
                        "Não foi possível criar o backup de segurança antes da restauração": (
                            "[green]literal safety framing[/green]"
                        ),
                        "A restauração foi cancelada.": (
                            "[yellow]literal cancellation[/yellow]"
                        ),
                        "Pressione Enter para continuar...": "Translated pause",
                    }
                )

                with tempfile.TemporaryDirectory() as temp_directory:
                    current_settings = Path(temp_directory) / "steam_settings"
                    current_settings.mkdir()
                    with (
                        patch(
                            "goldberg_manager.cli.get_menu_game",
                            return_value=game,
                        ),
                        patch(
                            "goldberg_manager.cli.list_steam_settings_backups",
                            return_value=[make_settings_backup()],
                        ),
                        patch("goldberg_manager.cli.questionary.select") as select,
                        patch("goldberg_manager.cli.questionary.confirm") as confirm,
                        patch(
                            "goldberg_manager.cli.get_steam_settings_directory",
                            return_value=current_settings,
                        ),
                        patch(
                            "goldberg_manager.cli.create_steam_settings_backup",
                            side_effect=error,
                        ) as create,
                        patch(
                            "goldberg_manager.cli.restore_steam_settings_backup"
                        ) as restore,
                        patch("goldberg_manager.cli.console", test_console),
                        patch("goldberg_manager.cli.pause") as pause,
                        patch("goldberg_manager.cli.clear_screen"),
                        patch("goldberg_manager.cli.render_header"),
                    ):
                        select.return_value.ask.return_value = 0
                        confirm.return_value.ask.return_value = True
                        restore_steam_settings_backup_menu(
                            AppConfig(),
                            translations=translations,
                        )

                create.assert_called_once_with(game)
                self.assertEqual(create.call_args.kwargs, {})
                restore.assert_not_called()
                pause.assert_called_once_with("Translated pause")
                rendered = output.getvalue()
                self.assertIn(
                    f"[green]literal safety framing[/green]: {error}",
                    rendered,
                )
                self.assertIn("[yellow]literal cancellation[/yellow]", rendered)
                self.assertNotIn("restaurado com sucesso", rendered)

    def test_unexpected_safety_backup_exception_propagates(self) -> None:
        error = RuntimeError("unexpected safety failure")
        game = make_game()

        with tempfile.TemporaryDirectory() as temp_directory:
            current_settings = Path(temp_directory) / "steam_settings"
            current_settings.mkdir()
            with (
                patch("goldberg_manager.cli.get_menu_game", return_value=game),
                patch(
                    "goldberg_manager.cli.list_steam_settings_backups",
                    return_value=[make_settings_backup()],
                ),
                patch("goldberg_manager.cli.questionary.select") as select,
                patch("goldberg_manager.cli.questionary.confirm") as confirm,
                patch(
                    "goldberg_manager.cli.get_steam_settings_directory",
                    return_value=current_settings,
                ),
                patch(
                    "goldberg_manager.cli.create_steam_settings_backup",
                    side_effect=error,
                ) as create,
                patch("goldberg_manager.cli.restore_steam_settings_backup") as restore,
                patch("goldberg_manager.cli.console.print"),
                patch("goldberg_manager.cli.pause") as pause,
                patch("goldberg_manager.cli.clear_screen"),
                patch("goldberg_manager.cli.render_header"),
                self.assertRaises(RuntimeError) as raised,
            ):
                select.return_value.ask.return_value = 0
                confirm.return_value.ask.return_value = True
                restore_steam_settings_backup_menu(
                    AppConfig(),
                    translations=MappingTranslations(),
                )

        self.assertIs(raised.exception, error)
        create.assert_called_once_with(game)
        restore.assert_not_called()
        pause.assert_not_called()

    def test_handled_restore_failures_translate_only_framing(self) -> None:
        errors = (
            OSError("[green]filesystem failure[/green]"),
            ValueError("[green]ownership failure[/green]"),
        )

        for error in errors:
            with self.subTest(error=type(error).__name__):
                output = StringIO()
                test_console = Console(file=output, width=240, color_system=None)
                game = make_game()
                backup = make_settings_backup()
                translations = MappingTranslations(
                    {
                        "Falha ao restaurar o backup": (
                            "[red]literal restore framing[/red]"
                        ),
                        "Pressione Enter para continuar...": "Translated pause",
                    }
                )

                with (
                    patch("goldberg_manager.cli.get_menu_game", return_value=game),
                    patch(
                        "goldberg_manager.cli.list_steam_settings_backups",
                        return_value=[backup],
                    ),
                    patch("goldberg_manager.cli.questionary.select") as select,
                    patch("goldberg_manager.cli.questionary.confirm") as confirm,
                    patch(
                        "goldberg_manager.cli.get_steam_settings_directory",
                        return_value=Path("/missing/current/steam_settings"),
                    ),
                    patch(
                        "goldberg_manager.cli.create_steam_settings_backup"
                    ) as create,
                    patch(
                        "goldberg_manager.cli.restore_steam_settings_backup",
                        side_effect=error,
                    ) as restore,
                    patch("goldberg_manager.cli.console", test_console),
                    patch("goldberg_manager.cli.pause") as pause,
                    patch("goldberg_manager.cli.clear_screen"),
                    patch("goldberg_manager.cli.render_header"),
                ):
                    select.return_value.ask.return_value = 0
                    confirm.return_value.ask.return_value = True
                    restore_steam_settings_backup_menu(
                        AppConfig(),
                        translations=translations,
                    )

                create.assert_not_called()
                restore.assert_called_once_with(game, backup.path)
                self.assertEqual(restore.call_args.kwargs, {})
                pause.assert_called_once_with("Translated pause")
                self.assertIn(
                    f"[red]literal restore framing[/red]: {error}",
                    output.getvalue(),
                )
                self.assertNotIn("restaurado com sucesso", output.getvalue())

    def test_unexpected_restore_exception_propagates_without_success_or_pause(
        self,
    ) -> None:
        error = RuntimeError("unexpected restore failure")
        game = make_game()
        backup = make_settings_backup()

        with (
            patch("goldberg_manager.cli.get_menu_game", return_value=game),
            patch(
                "goldberg_manager.cli.list_steam_settings_backups",
                return_value=[backup],
            ),
            patch("goldberg_manager.cli.questionary.select") as select,
            patch("goldberg_manager.cli.questionary.confirm") as confirm,
            patch(
                "goldberg_manager.cli.get_steam_settings_directory",
                return_value=Path("/missing/current/steam_settings"),
            ),
            patch("goldberg_manager.cli.create_steam_settings_backup") as create,
            patch(
                "goldberg_manager.cli.restore_steam_settings_backup",
                side_effect=error,
            ) as restore,
            patch("goldberg_manager.cli.console.print") as console_print,
            patch("goldberg_manager.cli.pause") as pause,
            patch("goldberg_manager.cli.clear_screen"),
            patch("goldberg_manager.cli.render_header"),
            self.assertRaises(RuntimeError) as raised,
        ):
            select.return_value.ask.return_value = 0
            confirm.return_value.ask.return_value = True
            restore_steam_settings_backup_menu(
                AppConfig(),
                translations=MappingTranslations(),
            )

        self.assertIs(raised.exception, error)
        create.assert_not_called()
        restore.assert_called_once_with(game, backup.path)
        pause.assert_not_called()
        rendered_values = " ".join(str(call) for call in console_print.call_args_list)
        self.assertNotIn("restaurado com sucesso", rendered_values)

    def test_unexpected_listing_errors_still_propagate_without_pause(self) -> None:
        errors = (
            TypeError("metadata failure"),
            RuntimeError("unexpected listing failure"),
        )

        for error in errors:
            with self.subTest(error=type(error).__name__), ExitStack() as stack:
                stack.enter_context(
                    patch(
                        "goldberg_manager.cli.get_menu_game", return_value=make_game()
                    )
                )
                stack.enter_context(
                    patch(
                        "goldberg_manager.cli.list_steam_settings_backups",
                        side_effect=error,
                    )
                )
                select = stack.enter_context(
                    patch("goldberg_manager.cli.questionary.select")
                )
                confirm = stack.enter_context(
                    patch("goldberg_manager.cli.questionary.confirm")
                )
                create = stack.enter_context(
                    patch("goldberg_manager.cli.create_steam_settings_backup")
                )
                restore = stack.enter_context(
                    patch("goldberg_manager.cli.restore_steam_settings_backup")
                )
                console_print = stack.enter_context(
                    patch("goldberg_manager.cli.console.print")
                )
                pause = stack.enter_context(patch("goldberg_manager.cli.pause"))
                stack.enter_context(patch("goldberg_manager.cli.clear_screen"))
                stack.enter_context(patch("goldberg_manager.cli.render_header"))

                with self.assertRaises(type(error)) as raised:
                    restore_steam_settings_backup_menu(
                        AppConfig(),
                        translations=MappingTranslations(),
                    )

            self.assertIs(raised.exception, error)
            select.assert_not_called()
            confirm.assert_not_called()
            create.assert_not_called()
            restore.assert_not_called()
            console_print.assert_not_called()
            pause.assert_not_called()

    def test_rich_like_translations_and_dynamic_success_values_are_literal(
        self,
    ) -> None:
        game = make_game(name="[bold]Literal Game[/bold]")
        backup = make_settings_backup(Path("/backups/[cyan]chosen[/cyan]"))
        restored_path = Path("/game/[red]restored[/red]/steam_settings")
        translations = MappingTranslations(
            {
                "Jogo": "[red]literal game label[/red]",
                "Restaurar backup": "[blue]literal panel title[/blue]",
                "steam_settings restaurado com sucesso!": (
                    "[green]literal success[/green]"
                ),
                "Pressione Enter para continuar...": "[cyan]literal pause[/cyan]",
            }
        )
        output = StringIO()
        test_console = Console(file=output, width=260, color_system=None)

        with (
            patch("goldberg_manager.cli.get_menu_game", return_value=game),
            patch(
                "goldberg_manager.cli.list_steam_settings_backups",
                return_value=[backup],
            ),
            patch("goldberg_manager.cli.questionary.select") as select,
            patch("goldberg_manager.cli.questionary.confirm") as confirm,
            patch(
                "goldberg_manager.cli.get_steam_settings_directory",
                return_value=Path("/missing/current/steam_settings"),
            ),
            patch("goldberg_manager.cli.create_steam_settings_backup") as create,
            patch(
                "goldberg_manager.cli.restore_steam_settings_backup",
                return_value=restored_path,
            ) as restore,
            patch("goldberg_manager.cli.console", test_console),
            patch("goldberg_manager.cli.pause") as pause,
            patch("goldberg_manager.cli.clear_screen"),
            patch("goldberg_manager.cli.render_header"),
        ):
            select.return_value.ask.return_value = 0
            confirm.return_value.ask.return_value = True
            restore_steam_settings_backup_menu(
                AppConfig(),
                translations=translations,
            )

        create.assert_not_called()
        restore.assert_called_once_with(game, backup.path)
        rendered = output.getvalue()
        for expected in (
            "[red]literal game label[/red]",
            "[blue]literal panel title[/blue]",
            "[bold]Literal Game[/bold]",
            "[green]literal success[/green]",
            str(restored_path),
        ):
            self.assertIn(expected, rendered)
        pause.assert_called_once_with("[cyan]literal pause[/cyan]")


class SteamSettingsBackupCreationRoutingTests(unittest.TestCase):
    def test_default_submenu_to_real_creation_loads_once_and_preserves_identity(
        self,
    ) -> None:
        config = AppConfig()
        game = make_game()
        snapshot_path = Path("/backups/Example/steam_settings/snapshot")
        translations = MappingTranslations()

        with (
            patch(
                "goldberg_manager.cli.load_translations",
                return_value=translations,
            ) as load_catalog,
            patch("goldberg_manager.cli.questionary.select") as select,
            patch(
                "goldberg_manager.cli.get_menu_game",
                wraps=get_menu_game,
            ) as get_game,
            patch(
                "goldberg_manager.cli.create_steam_settings_backup",
                return_value=snapshot_path,
            ) as writer,
            patch("goldberg_manager.cli.questionary.confirm") as confirm,
            patch("goldberg_manager.cli.console.print"),
            patch("goldberg_manager.cli.pause") as pause,
            patch("goldberg_manager.cli.clear_screen"),
            patch("goldberg_manager.cli.render_header"),
        ):
            select.return_value.ask.side_effect = ["create", "back"]
            manage_steam_settings_backups_menu(config, game)

        load_catalog.assert_called_once_with()
        get_game.assert_called_once_with(
            config,
            game,
            "Selecione o jogo para criar o backup de steam_settings:",
            translations=translations,
        )
        self.assertIs(get_game.call_args.kwargs["translations"], translations)
        writer.assert_called_once_with(game)
        self.assertIs(writer.call_args.args[0], game)
        self.assertEqual(writer.call_args.kwargs, {})
        confirm.assert_not_called()
        pause.assert_called_once_with("Pressione Enter para continuar...")

    def test_explicit_submenu_translations_reach_real_creation_without_reload(
        self,
    ) -> None:
        config = AppConfig()
        game = make_game()
        translations = MappingTranslations()

        with (
            patch("goldberg_manager.cli.load_translations") as load_catalog,
            patch("goldberg_manager.cli.questionary.select") as select,
            patch(
                "goldberg_manager.cli.get_menu_game",
                return_value=None,
            ) as get_game,
            patch("goldberg_manager.cli.create_steam_settings_backup") as writer,
            patch("goldberg_manager.cli.questionary.confirm") as confirm,
            patch("goldberg_manager.cli.console.print") as console_print,
            patch("goldberg_manager.cli.pause") as pause,
            patch("goldberg_manager.cli.clear_screen"),
            patch("goldberg_manager.cli.render_header"),
        ):
            select.return_value.ask.side_effect = ["create", "back"]
            manage_steam_settings_backups_menu(
                config,
                game,
                translations=translations,
            )

        load_catalog.assert_not_called()
        get_game.assert_called_once_with(
            config,
            game,
            "Selecione o jogo para criar o backup de steam_settings:",
            translations=translations,
        )
        self.assertIs(get_game.call_args.kwargs["translations"], translations)
        writer.assert_not_called()
        confirm.assert_not_called()
        console_print.assert_not_called()
        pause.assert_not_called()

    def test_default_steam_settings_parent_to_real_creation_loads_once(self) -> None:
        config = AppConfig()
        game = make_game()
        translations = MappingTranslations()

        with (
            patch(
                "goldberg_manager.cli.load_translations",
                return_value=translations,
            ) as load_catalog,
            patch("goldberg_manager.cli.questionary.select") as select,
            patch(
                "goldberg_manager.cli.get_menu_game",
                return_value=None,
            ) as get_game,
            patch("goldberg_manager.cli.create_steam_settings_backup") as writer,
            patch("goldberg_manager.cli.pause") as pause,
            patch("goldberg_manager.cli.clear_screen"),
            patch("goldberg_manager.cli.render_header"),
        ):
            select.return_value.ask.side_effect = ["backups", "create", "back", "back"]
            manage_steam_settings_menu(config, game)

        load_catalog.assert_called_once_with()
        get_game.assert_called_once_with(
            config,
            game,
            "Selecione o jogo para criar o backup de steam_settings:",
            translations=translations,
        )
        self.assertIs(get_game.call_args.kwargs["translations"], translations)
        writer.assert_not_called()
        pause.assert_not_called()


class SteamSettingsBackupCreationTests(unittest.TestCase):
    def test_direct_default_loads_once_and_preserves_portuguese_success_sequence(
        self,
    ) -> None:
        config = AppConfig()
        game = make_game()
        snapshot_path = Path("/backups/Example/steam_settings/snapshot")
        translations = MappingTranslations()
        events: list[tuple[str, object]] = []

        def record_writer(supplied_game):
            events.append(("create_steam_settings_backup", supplied_game))
            return snapshot_path

        def record_print(value):
            self.assertIsInstance(value, Text)
            events.append(("print", value.plain))

        with ExitStack() as stack:
            load_catalog = stack.enter_context(
                patch(
                    "goldberg_manager.cli.load_translations",
                    return_value=translations,
                )
            )
            get_games = stack.enter_context(
                patch(
                    "goldberg_manager.cli.get_detected_games",
                    return_value=[game],
                )
            )
            select = stack.enter_context(
                patch("goldberg_manager.cli.questionary.select")
            )
            select.return_value.ask.return_value = 0
            get_game = stack.enter_context(
                patch(
                    "goldberg_manager.cli.get_menu_game",
                    wraps=get_menu_game,
                )
            )
            writer = stack.enter_context(
                patch(
                    "goldberg_manager.cli.create_steam_settings_backup",
                    side_effect=record_writer,
                )
            )
            console_print = stack.enter_context(
                patch(
                    "goldberg_manager.cli.console.print",
                    side_effect=record_print,
                )
            )
            pause = stack.enter_context(
                patch(
                    "goldberg_manager.cli.pause",
                    side_effect=lambda message: events.append(("pause", message)),
                )
            )
            confirm = stack.enter_context(
                patch("goldberg_manager.cli.questionary.confirm")
            )
            stack.enter_context(patch("goldberg_manager.cli.clear_screen"))
            stack.enter_context(patch("goldberg_manager.cli.render_header"))
            unrelated = [
                stack.enter_context(patch(f"goldberg_manager.cli.{name}"))
                for name in UNRELATED_MUTATIONS
            ]

            create_steam_settings_backup_menu(config)

        load_catalog.assert_called_once_with()
        get_game.assert_called_once_with(
            config,
            None,
            "Selecione o jogo para criar o backup de steam_settings:",
            translations=translations,
        )
        self.assertIs(get_game.call_args.kwargs["translations"], translations)
        get_games.assert_called_once_with(
            config,
            translations=translations,
        )
        self.assertEqual(
            select.call_args.args[0],
            "Selecione o jogo para criar o backup de steam_settings:",
        )
        self.assertEqual(
            [choice.value for choice in select.call_args.kwargs["choices"]],
            [0, "back"],
        )
        writer.assert_called_once_with(game)
        self.assertIs(writer.call_args.args[0], game)
        self.assertEqual(writer.call_args.kwargs, {})
        self.assertEqual(console_print.call_count, 2)
        confirm.assert_not_called()
        pause.assert_called_once_with("Pressione Enter para continuar...")
        for mutation in unrelated:
            mutation.assert_not_called()
        self.assertEqual(
            events,
            [
                ("create_steam_settings_backup", game),
                ("print", "Backup de steam_settings criado com sucesso!"),
                ("print", str(snapshot_path)),
                ("pause", "Pressione Enter para continuar..."),
            ],
        )

    def test_explicit_english_translates_selection_success_and_pause(self) -> None:
        config = AppConfig()
        game = make_game(name="Technical Game")
        snapshot_path = Path("/backups/Technical Game/steam_settings/snapshot")
        translations = load_translations("en")
        output = StringIO()
        test_console = Console(file=output, width=240, color_system=None)

        with (
            patch("goldberg_manager.cli.load_translations") as load_catalog,
            patch(
                "goldberg_manager.cli.get_detected_games",
                return_value=[game],
            ),
            patch("goldberg_manager.cli.questionary.select") as select,
            patch(
                "goldberg_manager.cli.create_steam_settings_backup",
                return_value=snapshot_path,
            ) as writer,
            patch("goldberg_manager.cli.questionary.confirm") as confirm,
            patch("goldberg_manager.cli.console", test_console),
            patch("goldberg_manager.cli.pause") as pause,
            patch("goldberg_manager.cli.clear_screen"),
            patch("goldberg_manager.cli.render_header"),
        ):
            select.return_value.ask.return_value = 0
            create_steam_settings_backup_menu(
                config,
                translations=translations,
            )

        load_catalog.assert_not_called()
        self.assertEqual(
            select.call_args.args[0],
            "Select the game to create the steam_settings backup:",
        )
        choices = select.call_args.kwargs["choices"]
        self.assertEqual([choice.value for choice in choices], [0, "back"])
        self.assertIn("Technical Game", choices[0].title)
        self.assertEqual(choices[-1].title, "Back")
        writer.assert_called_once_with(game)
        self.assertIs(writer.call_args.args[0], game)
        self.assertEqual(writer.call_args.kwargs, {})
        confirm.assert_not_called()
        rendered = output.getvalue()
        self.assertIn("steam_settings backup created successfully!", rendered)
        self.assertIn(str(snapshot_path), rendered)
        pause.assert_called_once_with("Press Enter to continue...")

    def test_explicit_translations_bypass_loader_and_reach_game_resolution(
        self,
    ) -> None:
        config = AppConfig()
        translations = MappingTranslations()

        with (
            patch("goldberg_manager.cli.load_translations") as load_catalog,
            patch(
                "goldberg_manager.cli.get_menu_game",
                return_value=None,
            ) as get_game,
            patch("goldberg_manager.cli.create_steam_settings_backup") as writer,
            patch("goldberg_manager.cli.questionary.confirm") as confirm,
            patch("goldberg_manager.cli.console.print") as console_print,
            patch("goldberg_manager.cli.pause") as pause,
            patch("goldberg_manager.cli.clear_screen"),
            patch("goldberg_manager.cli.render_header"),
        ):
            create_steam_settings_backup_menu(
                config,
                translations=translations,
            )

        load_catalog.assert_not_called()
        get_game.assert_called_once_with(
            config,
            None,
            "Selecione o jogo para criar o backup de steam_settings:",
            translations=translations,
        )
        self.assertIs(get_game.call_args.kwargs["translations"], translations)
        writer.assert_not_called()
        confirm.assert_not_called()
        console_print.assert_not_called()
        pause.assert_not_called()

    def test_supplied_game_bypasses_detection_and_preserves_writer_identity(
        self,
    ) -> None:
        config = AppConfig()
        game = make_game()
        translations = MappingTranslations()

        with (
            patch("goldberg_manager.cli.get_detected_games") as get_games,
            patch("goldberg_manager.cli.select_game") as select_game,
            patch(
                "goldberg_manager.cli.create_steam_settings_backup",
                return_value=Path("/backups/snapshot"),
            ) as writer,
            patch("goldberg_manager.cli.questionary.confirm") as confirm,
            patch("goldberg_manager.cli.console.print"),
            patch("goldberg_manager.cli.pause"),
            patch("goldberg_manager.cli.clear_screen"),
            patch("goldberg_manager.cli.render_header"),
        ):
            create_steam_settings_backup_menu(
                config,
                game,
                translations=translations,
            )

        get_games.assert_not_called()
        select_game.assert_not_called()
        writer.assert_called_once_with(game)
        self.assertIs(writer.call_args.args[0], game)
        self.assertEqual(writer.call_args.kwargs, {})
        confirm.assert_not_called()

    def test_selection_cancellation_returns_without_mutation_output_or_pause(
        self,
    ) -> None:
        with ExitStack() as stack:
            stack.enter_context(
                patch("goldberg_manager.cli.get_menu_game", return_value=None)
            )
            writer = stack.enter_context(
                patch("goldberg_manager.cli.create_steam_settings_backup")
            )
            confirm = stack.enter_context(
                patch("goldberg_manager.cli.questionary.confirm")
            )
            console_print = stack.enter_context(
                patch("goldberg_manager.cli.console.print")
            )
            pause = stack.enter_context(patch("goldberg_manager.cli.pause"))
            stack.enter_context(patch("goldberg_manager.cli.clear_screen"))
            stack.enter_context(patch("goldberg_manager.cli.render_header"))
            unrelated = [
                stack.enter_context(patch(f"goldberg_manager.cli.{name}"))
                for name in UNRELATED_MUTATIONS
            ]

            create_steam_settings_backup_menu(
                AppConfig(),
                translations=MappingTranslations(),
            )

        writer.assert_not_called()
        confirm.assert_not_called()
        console_print.assert_not_called()
        pause.assert_not_called()
        for mutation in unrelated:
            mutation.assert_not_called()

    def test_each_handled_writer_error_preserves_portuguese_and_pauses_once(
        self,
    ) -> None:
        errors = (
            FileNotFoundError("missing settings"),
            OSError("filesystem failure"),
            ValueError("invalid settings"),
        )

        for error in errors:
            with self.subTest(error=type(error).__name__):
                output = StringIO()
                test_console = Console(file=output, width=200, color_system=None)

                with (
                    patch(
                        "goldberg_manager.cli.get_menu_game", return_value=make_game()
                    ),
                    patch(
                        "goldberg_manager.cli.create_steam_settings_backup",
                        side_effect=error,
                    ) as writer,
                    patch("goldberg_manager.cli.questionary.confirm") as confirm,
                    patch("goldberg_manager.cli.console", test_console),
                    patch("goldberg_manager.cli.pause") as pause,
                    patch("goldberg_manager.cli.clear_screen"),
                    patch("goldberg_manager.cli.render_header"),
                ):
                    create_steam_settings_backup_menu(
                        AppConfig(),
                        translations=MappingTranslations(),
                    )

                writer.assert_called_once()
                confirm.assert_not_called()
                self.assertEqual(
                    output.getvalue().strip(),
                    f"Não foi possível criar o backup: {error}",
                )
                self.assertNotIn(
                    "Backup de steam_settings criado com sucesso!",
                    output.getvalue(),
                )
                pause.assert_called_once_with("Pressione Enter para continuar...")

    def test_explicit_english_translates_handled_error_and_pause(self) -> None:
        error = OSError("technical failure")
        output = StringIO()
        test_console = Console(file=output, width=200, color_system=None)

        with (
            patch("goldberg_manager.cli.get_menu_game", return_value=make_game()),
            patch(
                "goldberg_manager.cli.create_steam_settings_backup",
                side_effect=error,
            ),
            patch("goldberg_manager.cli.console", test_console),
            patch("goldberg_manager.cli.pause") as pause,
            patch("goldberg_manager.cli.clear_screen"),
            patch("goldberg_manager.cli.render_header"),
        ):
            create_steam_settings_backup_menu(
                AppConfig(),
                translations=load_translations("en"),
            )

        self.assertEqual(
            output.getvalue().strip(),
            "Could not create the backup: technical failure",
        )
        pause.assert_called_once_with("Press Enter to continue...")

    def test_unexpected_writer_error_propagates_without_success_or_pause(self) -> None:
        game = make_game()
        error = RuntimeError("unexpected writer failure")

        with (
            patch("goldberg_manager.cli.get_menu_game", return_value=game),
            patch(
                "goldberg_manager.cli.create_steam_settings_backup",
                side_effect=error,
            ) as writer,
            patch("goldberg_manager.cli.console.print") as console_print,
            patch("goldberg_manager.cli.pause") as pause,
            patch("goldberg_manager.cli.clear_screen"),
            patch("goldberg_manager.cli.render_header"),
            self.assertRaises(RuntimeError) as raised,
        ):
            create_steam_settings_backup_menu(
                AppConfig(),
                translations=MappingTranslations(),
            )

        self.assertIs(raised.exception, error)
        writer.assert_called_once_with(game)
        self.assertEqual(writer.call_args.kwargs, {})
        console_print.assert_not_called()
        pause.assert_not_called()

    def test_translated_and_dynamic_rich_content_renders_literally(self) -> None:
        output = StringIO()
        test_console = Console(file=output, width=240, color_system=None)
        snapshot_path = Path("/backups/[red]literal path[/red]/snapshot")
        translations = MappingTranslations(
            {
                "Backup de steam_settings criado com sucesso!": (
                    "[green]literal success[/green]"
                ),
                "Pressione Enter para continuar...": "[cyan]literal pause[/cyan]",
            }
        )

        with (
            patch("goldberg_manager.cli.get_menu_game", return_value=make_game()),
            patch(
                "goldberg_manager.cli.create_steam_settings_backup",
                return_value=snapshot_path,
            ),
            patch("goldberg_manager.cli.console", test_console),
            patch("goldberg_manager.cli.pause") as pause,
            patch("goldberg_manager.cli.clear_screen"),
            patch("goldberg_manager.cli.render_header"),
        ):
            create_steam_settings_backup_menu(
                AppConfig(),
                translations=translations,
            )

        rendered = output.getvalue()
        self.assertIn("[green]literal success[/green]", rendered)
        self.assertIn(str(snapshot_path), rendered)
        pause.assert_called_once_with("[cyan]literal pause[/cyan]")

    def test_translated_error_and_dynamic_detail_render_literally(self) -> None:
        output = StringIO()
        test_console = Console(file=output, width=240, color_system=None)
        error = OSError("[green]literal detail[/green]")
        translations = MappingTranslations(
            {
                "Não foi possível criar o backup": "[red]literal framing[/red]",
                "Pressione Enter para continuar...": "Translated pause",
            }
        )

        with (
            patch("goldberg_manager.cli.get_menu_game", return_value=make_game()),
            patch(
                "goldberg_manager.cli.create_steam_settings_backup",
                side_effect=error,
            ),
            patch("goldberg_manager.cli.console", test_console),
            patch("goldberg_manager.cli.pause") as pause,
            patch("goldberg_manager.cli.clear_screen"),
            patch("goldberg_manager.cli.render_header"),
        ):
            create_steam_settings_backup_menu(
                AppConfig(),
                translations=translations,
            )

        self.assertIn(
            "[red]literal framing[/red]: [green]literal detail[/green]",
            output.getvalue(),
        )
        pause.assert_called_once_with("Translated pause")


class SteamSettingsBackupsListingTests(unittest.TestCase):
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
            patch("goldberg_manager.cli.list_steam_settings_backups") as list_backups,
            patch("goldberg_manager.cli.pause") as pause,
            patch("goldberg_manager.cli.clear_screen"),
            patch("goldberg_manager.cli.render_header"),
        ):
            list_steam_settings_backups_menu(config, game)

        load_catalog.assert_called_once_with()
        get_game.assert_called_once_with(
            config,
            game,
            "Selecione o jogo para listar os backups:",
            translations=translations,
        )
        self.assertIs(get_game.call_args.args[0], config)
        self.assertIs(get_game.call_args.args[1], game)
        self.assertIs(get_game.call_args.kwargs["translations"], translations)
        list_backups.assert_not_called()
        pause.assert_not_called()

    def test_explicit_translations_bypass_loader(self) -> None:
        translations = MappingTranslations()

        with (
            patch("goldberg_manager.cli.load_translations") as load_catalog,
            patch("goldberg_manager.cli.get_menu_game", return_value=None) as get_game,
            patch("goldberg_manager.cli.list_steam_settings_backups") as list_backups,
            patch("goldberg_manager.cli.pause") as pause,
            patch("goldberg_manager.cli.clear_screen"),
            patch("goldberg_manager.cli.render_header"),
        ):
            list_steam_settings_backups_menu(
                AppConfig(),
                translations=translations,
            )

        load_catalog.assert_not_called()
        self.assertIs(get_game.call_args.kwargs["translations"], translations)
        list_backups.assert_not_called()
        pause.assert_not_called()

    def test_supplied_game_bypasses_detection_and_renders_empty_state(self) -> None:
        game = make_game()

        with (
            patch("goldberg_manager.cli.get_detected_games") as get_games,
            patch("goldberg_manager.cli.select_game") as select_game,
            patch(
                "goldberg_manager.cli.list_steam_settings_backups",
                return_value=[],
            ) as list_backups,
            patch("goldberg_manager.cli.pause") as pause,
            patch("goldberg_manager.cli.console.print"),
            patch("goldberg_manager.cli.clear_screen"),
            patch("goldberg_manager.cli.render_header"),
        ):
            list_steam_settings_backups_menu(
                AppConfig(),
                game,
                translations=MappingTranslations(),
            )

        get_games.assert_not_called()
        select_game.assert_not_called()
        list_backups.assert_called_once_with(game)
        pause.assert_called_once_with("Pressione Enter para continuar...")

    def test_selection_cancellation_returns_before_read_and_pause(self) -> None:
        with (
            patch("goldberg_manager.cli.get_menu_game", return_value=None),
            patch("goldberg_manager.cli.list_steam_settings_backups") as list_backups,
            patch("goldberg_manager.cli.pause") as pause,
            patch("goldberg_manager.cli.clear_screen"),
            patch("goldberg_manager.cli.render_header"),
        ):
            list_steam_settings_backups_menu(
                AppConfig(),
                translations=MappingTranslations(),
            )

        list_backups.assert_not_called()
        pause.assert_not_called()

    def test_empty_backup_list_translates_literal_state_and_pauses_once(self) -> None:
        output = StringIO()
        test_console = Console(file=output, width=200, color_system=None)
        translations = MappingTranslations(
            {
                "Nenhum backup de steam_settings foi encontrado para este jogo.": (
                    "[red]literal empty state[/red]"
                ),
                "Pressione Enter para continuar...": "Translated pause",
            }
        )
        game = make_game()

        with (
            patch("goldberg_manager.cli.get_menu_game", return_value=game),
            patch(
                "goldberg_manager.cli.list_steam_settings_backups",
                return_value=[],
            ),
            patch("goldberg_manager.cli.pause") as pause,
            patch("goldberg_manager.cli.console", test_console),
            patch("goldberg_manager.cli.clear_screen"),
            patch("goldberg_manager.cli.render_header"),
        ):
            list_steam_settings_backups_menu(
                AppConfig(),
                game,
                translations=translations,
            )

        pause.assert_called_once_with("Translated pause")
        self.assertIn("[red]literal empty state[/red]", output.getvalue())

    def test_valid_and_corrupted_rows_are_translated_literal_and_ordered(self) -> None:
        root = Path("/[blue]backup-root[/blue]")
        game = make_game(name="[green]Literal Game[/green]")
        backups = [
            SteamSettingsBackup(
                path=root / "newer",
                created_at=datetime(2026, 8, 30, 21, 22, 23, tzinfo=UTC),
                file_count=7,
                valid=True,
            ),
            SteamSettingsBackup(
                path=root / "older",
                created_at=datetime(2026, 8, 29, 10, 11, 12, tzinfo=UTC),
                file_count=3,
                valid=False,
            ),
        ]
        translations = MappingTranslations(
            {
                "Backups de": "[red]literal backups title[/red]",
                "Data": "[blue]literal date[/blue]",
                "Arquivos": "[green]literal files[/green]",
                "Integridade": "[yellow]literal integrity[/yellow]",
                "Íntegro": "[magenta]literal valid[/magenta]",
                "CORROMPIDO": "[cyan]literal corrupted[/cyan]",
                "Diretório": "[white]literal directory[/white]",
                "Pressione Enter para continuar...": "Translated pause",
            }
        )
        output = StringIO()
        test_console = Console(file=output, width=300, color_system=None)

        with (
            patch("goldberg_manager.cli.get_menu_game", return_value=game),
            patch(
                "goldberg_manager.cli.list_steam_settings_backups",
                return_value=backups,
            ) as list_backups,
            patch("goldberg_manager.cli.pause") as pause,
            patch("goldberg_manager.cli.console", test_console),
            patch("goldberg_manager.cli.clear_screen"),
            patch("goldberg_manager.cli.render_header"),
        ):
            list_steam_settings_backups_menu(
                AppConfig(),
                game,
                translations=translations,
            )

        list_backups.assert_called_once_with(game)
        pause.assert_called_once_with("Translated pause")
        rendered = output.getvalue()
        newer_timestamp = (
            backups[0].created_at.astimezone().strftime("%d/%m/%Y %H:%M:%S")
        )
        older_timestamp = (
            backups[1].created_at.astimezone().strftime("%d/%m/%Y %H:%M:%S")
        )
        expected_in_order = (
            "[red]literal backups title[/red] [green]Literal Game[/green]",
            "[blue]literal date[/blue]",
            "[green]literal files[/green]",
            "[yellow]literal integrity[/yellow]",
            newer_timestamp,
            "[magenta]literal valid[/magenta]",
            older_timestamp,
            "[cyan]literal corrupted[/cyan]",
            "[white]literal directory[/white]: /[blue]backup-root[/blue]",
        )
        positions = [rendered.index(value) for value in expected_in_order]
        self.assertEqual(positions, sorted(positions))
        rendered_lines = rendered.splitlines()
        newer_row = next(line for line in rendered_lines if newer_timestamp in line)
        older_row = next(line for line in rendered_lines if older_timestamp in line)
        self.assertEqual(
            [cell.strip() for cell in newer_row.split("│")[1:-1]],
            ["1", newer_timestamp, "7", "[magenta]literal valid[/magenta]"],
        )
        self.assertEqual(
            [cell.strip() for cell in older_row.split("│")[1:-1]],
            ["2", older_timestamp, "3", "[cyan]literal corrupted[/cyan]"],
        )

    def test_explicit_english_translates_listing(self) -> None:
        game = make_game()
        backup = SteamSettingsBackup(
            path=Path("/backups/Example/steam_settings/snapshot"),
            created_at=datetime(2026, 8, 30, 21, 22, 23, tzinfo=UTC),
            file_count=1,
            valid=True,
        )
        output = StringIO()
        test_console = Console(file=output, width=240, color_system=None)

        with (
            patch("goldberg_manager.cli.load_translations") as load_catalog,
            patch("goldberg_manager.cli.get_menu_game", return_value=game) as get_game,
            patch(
                "goldberg_manager.cli.list_steam_settings_backups",
                return_value=[backup],
            ),
            patch("goldberg_manager.cli.pause") as pause,
            patch("goldberg_manager.cli.console", test_console),
            patch("goldberg_manager.cli.clear_screen"),
            patch("goldberg_manager.cli.render_header"),
        ):
            translations = load_translations("en")
            list_steam_settings_backups_menu(
                AppConfig(),
                game,
                translations=translations,
            )

        load_catalog.assert_not_called()
        self.assertIs(get_game.call_args.kwargs["translations"], translations)
        pause.assert_called_once_with("Press Enter to continue...")
        rendered = output.getvalue()
        for expected in (
            "Backups for Example Game",
            "Date",
            "Files",
            "Integrity",
            "Valid",
            "Directory: /backups/Example/steam_settings",
        ):
            self.assertIn(expected, rendered)

    def test_handled_os_error_is_literal_translated_and_pauses_once(self) -> None:
        error = OSError("[green]literal error[/green]")
        output = StringIO()
        test_console = Console(file=output, width=200, color_system=None)
        translations = MappingTranslations(
            {
                "Não foi possível listar os backups": (
                    "[red]literal error framing[/red]"
                ),
                "Pressione Enter para continuar...": "Translated pause",
            }
        )

        with (
            patch("goldberg_manager.cli.get_menu_game", return_value=make_game()),
            patch(
                "goldberg_manager.cli.list_steam_settings_backups",
                side_effect=error,
            ),
            patch("goldberg_manager.cli.pause") as pause,
            patch("goldberg_manager.cli.console", test_console),
            patch("goldberg_manager.cli.clear_screen"),
            patch("goldberg_manager.cli.render_header"),
        ):
            list_steam_settings_backups_menu(
                AppConfig(),
                translations=translations,
            )

        pause.assert_called_once_with("Translated pause")
        self.assertIn(
            "[red]literal error framing[/red]: [green]literal error[/green]",
            output.getvalue(),
        )

    def test_unexpected_reader_error_propagates_without_pause(self) -> None:
        error = RuntimeError("unexpected reader failure")

        with (
            patch("goldberg_manager.cli.get_menu_game", return_value=make_game()),
            patch(
                "goldberg_manager.cli.list_steam_settings_backups",
                side_effect=error,
            ),
            patch("goldberg_manager.cli.pause") as pause,
            patch("goldberg_manager.cli.clear_screen"),
            patch("goldberg_manager.cli.render_header"),
            self.assertRaises(RuntimeError) as raised,
        ):
            list_steam_settings_backups_menu(
                AppConfig(),
                translations=MappingTranslations(),
            )

        self.assertIs(raised.exception, error)
        pause.assert_not_called()

    def test_real_listing_is_read_only_and_preserves_backup_tree(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            game_root = root / "game"
            game = make_game(game_root, name="Read Only Game")
            steam_settings = game.steam_api.parent / "steam_settings"
            steam_settings.mkdir(parents=True)
            (steam_settings / "configs.user.ini").write_text(
                "[user::general]\naccount_name=Player\n",
                encoding="utf-8",
            )
            backup_root = root / "backups"

            with patch("goldberg_manager.settings_backup.BACKUP_ROOT", backup_root):
                create_steam_settings_backup(
                    game,
                    created_at=datetime(2026, 8, 30, 21, 22, 23, tzinfo=UTC),
                )
                before = {
                    path.relative_to(backup_root).as_posix(): path.read_bytes()
                    for path in sorted(backup_root.rglob("*"))
                    if path.is_file()
                }

                with ExitStack() as stack:
                    stack.enter_context(
                        patch("goldberg_manager.cli.get_menu_game", return_value=game)
                    )
                    pause = stack.enter_context(patch("goldberg_manager.cli.pause"))
                    stack.enter_context(patch("goldberg_manager.cli.console.print"))
                    stack.enter_context(patch("goldberg_manager.cli.clear_screen"))
                    stack.enter_context(patch("goldberg_manager.cli.render_header"))
                    create = stack.enter_context(
                        patch("goldberg_manager.cli.create_steam_settings_backup")
                    )
                    restore = stack.enter_context(
                        patch("goldberg_manager.cli.restore_steam_settings_backup")
                    )
                    backup_game = stack.enter_context(
                        patch("goldberg_manager.cli.backup_game")
                    )
                    restore_game = stack.enter_context(
                        patch("goldberg_manager.cli.restore_game_backup")
                    )
                    save_config = stack.enter_context(
                        patch("goldberg_manager.cli.save_config")
                    )
                    search = stack.enter_context(
                        patch("goldberg_manager.cli.search_game_on_steam")
                    )
                    run = stack.enter_context(
                        patch("goldberg_manager.cli.subprocess.run")
                    )
                    mkdir = stack.enter_context(patch.object(Path, "mkdir"))
                    write_text = stack.enter_context(patch.object(Path, "write_text"))
                    write_bytes = stack.enter_context(patch.object(Path, "write_bytes"))
                    rename = stack.enter_context(patch.object(Path, "rename"))
                    replace = stack.enter_context(patch.object(Path, "replace"))
                    unlink = stack.enter_context(patch.object(Path, "unlink"))
                    copy = stack.enter_context(patch.object(shutil, "copy"))
                    copy2 = stack.enter_context(patch.object(shutil, "copy2"))
                    copytree = stack.enter_context(patch.object(shutil, "copytree"))
                    rmtree = stack.enter_context(patch.object(shutil, "rmtree"))

                    list_steam_settings_backups_menu(
                        AppConfig(),
                        game,
                        translations=MappingTranslations(),
                    )

                pause.assert_called_once_with("Pressione Enter para continuar...")
                for guarded_call in (
                    create,
                    restore,
                    backup_game,
                    restore_game,
                    save_config,
                    search,
                    run,
                    mkdir,
                    write_text,
                    write_bytes,
                    rename,
                    replace,
                    unlink,
                    copy,
                    copy2,
                    copytree,
                    rmtree,
                ):
                    guarded_call.assert_not_called()

                after = {
                    path.relative_to(backup_root).as_posix(): path.read_bytes()
                    for path in sorted(backup_root.rglob("*"))
                    if path.is_file()
                }
                self.assertEqual(after, before)

    def test_non_object_metadata_type_error_still_propagates(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            game = make_game(root / "game", name="Malformed Metadata Game")
            snapshot = root / "backups" / game.name / "steam_settings" / "snapshot"
            (snapshot / "files").mkdir(parents=True)
            (snapshot / "metadata.json").write_text("[]", encoding="utf-8")

            with (
                patch("goldberg_manager.settings_backup.BACKUP_ROOT", root / "backups"),
                self.assertRaises(TypeError),
            ):
                list_steam_settings_backups(game)

    def test_mixed_naive_and_aware_timestamp_type_error_still_propagates(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            game = make_game(root / "game", name="Mixed Timestamp Game")
            backup_root = root / "backups" / game.name / "steam_settings"

            for name, created_at in (
                ("naive", "2026-08-30T20:00:00"),
                ("aware", "2026-08-30T21:00:00+00:00"),
            ):
                snapshot = backup_root / name
                (snapshot / "files").mkdir(parents=True)
                (snapshot / "metadata.json").write_text(
                    json.dumps(
                        {
                            "created_at": created_at,
                            "file_count": 0,
                            "files": {},
                        }
                    ),
                    encoding="utf-8",
                )

            with (
                patch("goldberg_manager.settings_backup.BACKUP_ROOT", root / "backups"),
                self.assertRaises(TypeError),
            ):
                list_steam_settings_backups(game)


if __name__ == "__main__":
    unittest.main()
