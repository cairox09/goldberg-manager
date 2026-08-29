from __future__ import annotations

import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from rich.console import Console

from goldberg_manager.appid import AppIdCandidate
from goldberg_manager.cli import (
    GameSentinelResolution as CliGameSentinelResolution,
)
from goldberg_manager.cli import (
    resolve_game_sentinel_runtime,
    show_game_sentinel_status,
)
from goldberg_manager.game_resolution import (
    GameSentinelResolution,
)
from goldberg_manager.game_resolution import (
    resolve_game_sentinel_runtime as resolve_game_sentinel_runtime_domain,
)
from goldberg_manager.presentation.i18n import load_translations
from goldberg_manager.scanner import Game
from goldberg_manager.sentinel import (
    SentinelConfigStatus,
    SentinelInstallation,
    SentinelRuntimeSave,
)


def make_game() -> Game:
    root = Path("/games/Sonic")

    return Game(
        name="Sonic All-Stars Racing Transformed",
        root_directory=root,
        executable=root / "ASN_App_PcDx9_Final.exe",
        steam_api=root / "steam_api.dll",
        steam_api_relative_path=Path("steam_api.dll"),
        architecture="x86",
        source_directory=root.parent,
    )


def make_status() -> SentinelConfigStatus:
    return SentinelConfigStatus(
        path=Path("/config/sentinel/config.json"),
        exists=True,
        valid_json=True,
        schema_valid=True,
        prefix_paths=(),
        emulators=(),
    )


def make_runtime(
    app_id: int,
    *,
    emulator_id: str = "gse",
    prefix_path: Path = Path("/prefix"),
) -> SentinelRuntimeSave:
    drive_c = prefix_path / "pfx" / "drive_c"

    saves_directory = (
        drive_c / "users" / "steamuser" / "AppData" / "Roaming" / "GSE Saves"
    )

    app_directory = saves_directory / str(app_id)

    return SentinelRuntimeSave(
        emulator_id=emulator_id,
        prefix_path=prefix_path,
        drive_c=drive_c,
        saves_directory=saves_directory,
        app_id=app_id,
        app_directory=app_directory,
        achievements_path=(app_directory / "achievements.json"),
    )


def make_installation(
    executable: Path | None = Path("/usr/bin/sentinel"),
) -> SentinelInstallation:
    return SentinelInstallation(
        executable=executable,
        config_path=Path("/config/sentinel/config.json"),
        data_directory=Path("/data/sentinel"),
        state_directory=Path("/state/sentinel"),
        log_path=Path("/state/sentinel/logs/sentinel.log"),
    )


class RichLikeTranslations:
    def gettext(self, message: str) -> str:
        return f"[red]{message}[/red]"


def render_status(
    game: Game,
    installation: SentinelInstallation,
    status: SentinelConfigStatus,
    resolution: GameSentinelResolution,
    *,
    translations=None,
):
    output = StringIO()
    test_console = Console(file=output, width=300, color_system=None)
    events: list[str] = []

    def detect():
        events.append("detect")
        return installation

    def read_config(path):
        events.append("read_config")
        return status

    def resolve(selected_game, *, status):
        events.append("resolve")
        return resolution

    with (
        patch("goldberg_manager.cli.console", test_console),
        patch("goldberg_manager.cli.clear_screen"),
        patch("goldberg_manager.cli.render_header"),
        patch("goldberg_manager.cli.detect_sentinel", side_effect=detect) as detector,
        patch(
            "goldberg_manager.cli.read_sentinel_config",
            side_effect=read_config,
        ) as config_reader,
        patch(
            "goldberg_manager.cli.resolve_game_sentinel_runtime",
            side_effect=resolve,
        ) as resolver,
        patch("goldberg_manager.cli.pause") as pause,
        patch("goldberg_manager.cli.apply_game_sentinel_repair") as repair,
        patch("goldberg_manager.cli.backup_game") as backup,
        patch("goldberg_manager.cli.restore_game_backup") as restore,
        patch("goldberg_manager.cli.subprocess.run") as subprocess_run,
    ):
        if translations is None:
            show_game_sentinel_status(game)
        else:
            show_game_sentinel_status(game, translations=translations)

    return output.getvalue(), {
        "detector": detector,
        "config_reader": config_reader,
        "resolver": resolver,
        "pause": pause,
        "repair": repair,
        "backup": backup,
        "restore": restore,
        "subprocess_run": subprocess_run,
        "events": events,
    }


class SentinelGameResolutionTests(
    unittest.TestCase,
):
    def test_resolution_type_remains_available_from_cli(self) -> None:
        self.assertIs(
            CliGameSentinelResolution,
            GameSentinelResolution,
        )

    def test_domain_resolver_supports_explicit_dependencies(self) -> None:
        candidate = AppIdCandidate(
            app_id=212480,
            name="Sonic All-Stars Racing Transformed",
            score=95,
            source="steam_manifest",
        )
        runtime_save = make_runtime(212480)

        resolution = resolve_game_sentinel_runtime_domain(
            make_game(),
            status=make_status(),
            app_id_resolver=lambda game: [candidate],
            runtime_saves_resolver=lambda status: (runtime_save,),
        )

        self.assertEqual(
            resolution.app_id,
            212480,
        )
        self.assertIs(
            resolution.runtime_saves[0],
            runtime_save,
        )

    def test_prefers_candidate_with_runtime_save(
        self,
    ) -> None:
        candidates = [
            AppIdCandidate(
                app_id=111111,
                name="Wrong candidate",
                score=100,
                source="steam_manifest",
            ),
            AppIdCandidate(
                app_id=212480,
                name="Sonic All-Stars Racing Transformed",
                score=95,
                source="steam_manifest",
            ),
        ]

        runtime_save = make_runtime(212480)

        with (
            patch(
                "goldberg_manager.cli.resolve_local_appid",
                return_value=candidates,
            ),
            patch(
                "goldberg_manager.cli.resolve_sentinel_runtime_saves",
                return_value=(runtime_save,),
            ),
        ):
            resolution = resolve_game_sentinel_runtime(
                make_game(),
                status=make_status(),
            )

        self.assertEqual(
            resolution.app_id,
            212480,
        )

        self.assertEqual(
            resolution.app_id_confidence,
            95,
        )

        self.assertTrue(
            resolution.runtime_found,
        )

        self.assertEqual(
            resolution.runtime_saves,
            (runtime_save,),
        )

    def test_falls_back_to_best_local_appid_without_runtime(
        self,
    ) -> None:
        candidates = [
            AppIdCandidate(
                app_id=212480,
                name="Sonic All-Stars Racing Transformed",
                score=100,
                source="steam_appid.txt",
            )
        ]

        with (
            patch(
                "goldberg_manager.cli.resolve_local_appid",
                return_value=candidates,
            ),
            patch(
                "goldberg_manager.cli.resolve_sentinel_runtime_saves",
                return_value=(),
            ),
        ):
            resolution = resolve_game_sentinel_runtime(
                make_game(),
                status=make_status(),
            )

        self.assertEqual(
            resolution.app_id,
            212480,
        )

        self.assertEqual(
            resolution.app_id_source,
            "steam_appid.txt",
        )

        self.assertFalse(
            resolution.runtime_found,
        )

    def test_reports_missing_appid(
        self,
    ) -> None:
        with (
            patch(
                "goldberg_manager.cli.resolve_local_appid",
                return_value=[],
            ),
            patch(
                "goldberg_manager.cli.resolve_sentinel_runtime_saves",
                return_value=(),
            ),
        ):
            resolution = resolve_game_sentinel_runtime(
                make_game(),
                status=make_status(),
            )

        self.assertIsNone(
            resolution.app_id,
        )

        self.assertIsNone(
            resolution.app_id_confidence,
        )

        self.assertIsNone(
            resolution.app_id_source,
        )

        self.assertFalse(
            resolution.runtime_found,
        )


class SentinelGameStatusPresentationTests(unittest.TestCase):
    def test_portuguese_default_is_read_only_and_preserves_orchestration(self) -> None:
        game = make_game()
        installation = make_installation()
        status = make_status()

        with tempfile.TemporaryDirectory() as temporary_directory:
            runtime = make_runtime(
                212480,
                prefix_path=Path(temporary_directory) / "prefix",
            )
            runtime.achievements_path.parent.mkdir(parents=True)
            runtime.achievements_path.write_text("{}", encoding="utf-8")
            resolution = GameSentinelResolution(
                app_id=212480,
                app_id_confidence=95,
                app_id_source="steam_manifest",
                runtime_saves=(runtime,),
            )

            rendered, mocks = render_status(
                game,
                installation,
                status,
                resolution,
            )

        for expected in (
            "Jogo",
            "Detectado",
            "Configuração",
            "Válida",
            "1 correspondência",
            "Emulador",
            "Prefixo",
            "Raiz do save",
            "AppID do runtime",
            "Encontrado",
            "Sentinel • Runtime do jogo",
            "Somente leitura • nenhum arquivo do Sentinel ou do GSE foi alterado.",
            "steam_manifest",
            "212480",
            "95%",
        ):
            self.assertIn(expected, rendered)

        self.assertNotIn("Save root", rendered)
        self.assertNotIn("AppID runtime", rendered)
        self.assertEqual(mocks["events"], ["detect", "read_config", "resolve"])
        mocks["detector"].assert_called_once_with()
        mocks["config_reader"].assert_called_once_with(installation.config_path)
        mocks["resolver"].assert_called_once_with(game, status=status)
        mocks["pause"].assert_called_once_with("Pressione Enter para continuar...")
        for mutation in ("repair", "backup", "restore", "subprocess_run"):
            mocks[mutation].assert_not_called()

    def test_explicit_english_translates_missing_states_and_pause(self) -> None:
        installation = make_installation(executable=None)
        status = SentinelConfigStatus(
            path=installation.config_path,
            exists=False,
            valid_json=False,
            schema_valid=False,
            prefix_paths=(),
            emulators=(),
        )
        resolution = GameSentinelResolution(
            app_id=None,
            app_id_confidence=None,
            app_id_source=None,
            runtime_saves=(),
        )

        rendered, mocks = render_status(
            make_game(),
            installation,
            status,
            resolution,
            translations=load_translations("en"),
        )

        for expected in (
            "Game",
            "Not detected",
            "Configuration",
            "Not configured",
            "Unresolved",
            "No matching save found",
            "Sentinel • Game runtime",
            "Read-only • no Sentinel or GSE file was changed.",
            "AppID",
            "Runtime",
        ):
            self.assertIn(expected, rendered)

        mocks["pause"].assert_called_once_with("Press Enter to continue...")

    def test_multiple_runtimes_use_translated_indexed_labels_and_states(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_path = Path(temporary_directory)
            found_runtime = make_runtime(
                212480,
                emulator_id="gse",
                prefix_path=temporary_path / "first-prefix",
            )
            found_runtime.achievements_path.parent.mkdir(parents=True)
            found_runtime.achievements_path.write_text("{}", encoding="utf-8")
            missing_runtime = make_runtime(
                212480,
                emulator_id="goldberg-steamemu",
                prefix_path=temporary_path / "second-prefix",
            )
            resolution = GameSentinelResolution(
                app_id=212480,
                app_id_confidence=100,
                app_id_source="steam_appid.txt",
                runtime_saves=(found_runtime, missing_runtime),
            )

            rendered, _ = render_status(
                make_game(),
                make_installation(),
                make_status(),
                resolution,
                translations=load_translations("en"),
            )

        for expected in (
            "2 matches",
            "Emulator #1",
            "Emulator #2",
            "Prefix #1",
            "Prefix #2",
            "Save root #1",
            "Save root #2",
            "Runtime AppID #1",
            "Runtime AppID #2",
            "Found",
            "Not created yet",
            "gse",
            "goldberg-steamemu",
            "steam_appid.txt",
            "drive_c #1",
            "achievements.json #2",
        ):
            self.assertIn(expected, rendered)

    def test_rich_like_translations_and_dynamic_values_render_literally(self) -> None:
        root = Path("/games/[bold]literal[/bold]")
        game = Game(
            name="[bold]Literal Game[/bold]",
            root_directory=root,
            executable=root / "game.exe",
            steam_api=root / "steam_api.dll",
            steam_api_relative_path=Path("steam_api.dll"),
            architecture="x86",
            source_directory=root.parent,
        )
        installation = make_installation(Path("/usr/bin/[cyan]sentinel[/cyan]"))
        runtime = make_runtime(
            212480,
            emulator_id="[blue]gse[/blue]",
            prefix_path=Path("/prefix/[yellow]literal[/yellow]"),
        )
        resolution = GameSentinelResolution(
            app_id=212480,
            app_id_confidence=95,
            app_id_source="[magenta]steam_manifest[/magenta]",
            runtime_saves=(runtime,),
        )

        rendered, _ = render_status(
            game,
            installation,
            make_status(),
            resolution,
            translations=RichLikeTranslations(),
        )

        for expected in (
            "[red]Jogo[/red]",
            "[red]Detectado[/red]",
            "[red]Runtime do jogo[/red]",
            "[bold]Literal Game[/bold]",
            "/usr/bin/[cyan]sentinel[/cyan]",
            "[magenta]steam_manifest[/magenta]",
            "[blue]gse[/blue]",
            "/prefix/[yellow]literal[/yellow]",
        ):
            self.assertIn(expected, rendered)

    def test_resolver_exception_still_propagates_without_pausing(self) -> None:
        game = make_game()
        installation = make_installation()
        status = make_status()

        with (
            patch("goldberg_manager.cli.clear_screen"),
            patch("goldberg_manager.cli.render_header"),
            patch(
                "goldberg_manager.cli.detect_sentinel",
                return_value=installation,
            ) as detector,
            patch(
                "goldberg_manager.cli.read_sentinel_config",
                return_value=status,
            ) as config_reader,
            patch(
                "goldberg_manager.cli.resolve_game_sentinel_runtime",
                side_effect=OSError("resolver failure"),
            ) as resolver,
            patch("goldberg_manager.cli.pause") as pause,
            self.assertRaisesRegex(OSError, "resolver failure"),
        ):
            show_game_sentinel_status(game)

        detector.assert_called_once_with()
        config_reader.assert_called_once_with(installation.config_path)
        resolver.assert_called_once_with(game, status=status)
        pause.assert_not_called()


if __name__ == "__main__":
    unittest.main()
