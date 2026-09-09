from __future__ import annotations

import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from rich.console import Console

from goldberg_manager.cli import show_sentinel_status
from goldberg_manager.presentation.i18n import load_translations
from goldberg_manager.sentinel import (
    SENTINEL_GOLDBERG_EMULATOR_ID,
    SENTINEL_GSE_EMULATOR_ID,
    SentinelConfigStatus,
    SentinelEmulator,
    SentinelInstallation,
    SentinelSaveRoot,
)

OMITTED = object()


class RecordingTranslations:
    def __init__(self, translations: dict[str, str] | None = None) -> None:
        self.translations = translations or {}
        self.messages: list[str] = []

    def gettext(self, message: str) -> str:
        self.messages.append(message)
        return self.translations.get(message, message)


class RichLikeTranslations:
    def gettext(self, message: str) -> str:
        return f"[red]{message}[/red]"


def make_installation(
    root: Path,
    *,
    installed: bool = True,
    data_exists: bool = False,
    state_exists: bool = False,
) -> SentinelInstallation:
    data_directory = root / "data" / "[blue]sentinel-data[/blue]"
    state_directory = root / "state" / "[magenta]sentinel-state[/magenta]"

    if data_exists:
        data_directory.mkdir(parents=True)
    if state_exists:
        state_directory.mkdir(parents=True)

    return SentinelInstallation(
        executable=(root / "bin" / "[cyan]sentinel[/cyan]") if installed else None,
        config_path=root / "config" / "[green]config.json[/green]",
        data_directory=data_directory,
        state_directory=state_directory,
        log_path=state_directory / "logs" / "sentinel.log",
    )


def make_status(
    installation: SentinelInstallation,
    *,
    exists: bool = True,
    valid_json: bool = True,
    schema_valid: bool = True,
    prefix_count: int = 0,
    emulators: tuple[SentinelEmulator, ...] = (),
    error: str | None = None,
) -> SentinelConfigStatus:
    return SentinelConfigStatus(
        path=installation.config_path,
        exists=exists,
        valid_json=valid_json,
        schema_valid=schema_valid,
        prefix_paths=tuple(
            installation.config_path.parent / f"[yellow]prefix-{index}[/yellow]"
            for index in range(1, prefix_count + 1)
        ),
        emulators=emulators,
        error=error,
    )


def make_save_root(root: Path, index: int) -> SentinelSaveRoot:
    path = root / f"[bold]save-root-{index}[/bold]"
    path.mkdir(parents=True)
    prefix = root / f"[yellow]save-prefix-{index}[/yellow]"
    return SentinelSaveRoot(
        emulator_id=SENTINEL_GSE_EMULATOR_ID,
        prefix_path=prefix,
        drive_c=prefix / "drive_c",
        path=path,
    )


def render_status(
    installation: SentinelInstallation,
    status: SentinelConfigStatus,
    *,
    save_roots: tuple[SentinelSaveRoot, ...] = (),
    translations=OMITTED,
) -> tuple[str, dict[str, object]]:
    output = StringIO()
    test_console = Console(file=output, width=500, color_system=None)
    events: list[str] = []

    def detect() -> SentinelInstallation:
        events.append("detect")
        return installation

    def read_config(path: Path) -> SentinelConfigStatus:
        events.append("read_config")
        return status

    def resolve_roots(source_status: SentinelConfigStatus):
        events.append("resolve_roots")
        return save_roots

    with (
        patch("goldberg_manager.cli.console", test_console),
        patch("goldberg_manager.cli.detect_sentinel", side_effect=detect) as detector,
        patch(
            "goldberg_manager.cli.read_sentinel_config",
            side_effect=read_config,
        ) as config_reader,
        patch(
            "goldberg_manager.cli.resolve_sentinel_save_roots",
            side_effect=resolve_roots,
        ) as roots_resolver,
        patch("goldberg_manager.cli.pause") as pause,
        patch("goldberg_manager.cli.questionary.select") as select,
        patch("goldberg_manager.cli.questionary.text") as text_prompt,
        patch("goldberg_manager.cli.questionary.confirm") as confirm,
        patch("goldberg_manager.cli.questionary.autocomplete") as autocomplete,
        patch("goldberg_manager.cli.save_config") as config_writer,
        patch("goldberg_manager.cli.apply_game_sentinel_repair") as repair_writer,
        patch("goldberg_manager.cli.backup_game") as game_backup,
        patch("goldberg_manager.cli.create_steam_settings_backup") as settings_backup,
        patch("goldberg_manager.cli.subprocess.run") as subprocess_run,
        patch(
            "goldberg_manager.sentinel_config_writer.apply_sentinel_config_repair"
        ) as sentinel_writer,
    ):
        if translations is OMITTED:
            show_sentinel_status()
        else:
            show_sentinel_status(translations=translations)

    return output.getvalue(), {
        "detector": detector,
        "config_reader": config_reader,
        "roots_resolver": roots_resolver,
        "pause": pause,
        "select": select,
        "text_prompt": text_prompt,
        "confirm": confirm,
        "autocomplete": autocomplete,
        "config_writer": config_writer,
        "repair_writer": repair_writer,
        "sentinel_writer": sentinel_writer,
        "game_backup": game_backup,
        "settings_backup": settings_backup,
        "subprocess_run": subprocess_run,
        "events": events,
    }


class SentinelGlobalStatusCliTests(unittest.TestCase):
    def assert_read_only(self, mocks: dict[str, object]) -> None:
        for name in (
            "pause",
            "select",
            "text_prompt",
            "confirm",
            "autocomplete",
            "config_writer",
            "repair_writer",
            "sentinel_writer",
            "game_backup",
            "settings_backup",
            "subprocess_run",
        ):
            with self.subTest(boundary=name):
                mocks[name].assert_not_called()

    def test_default_invocation_loads_translations_exactly_once(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            installation = make_installation(Path(temporary_directory))
            status = make_status(installation)
            translations = RecordingTranslations({"Instalação": "Loaded installation"})

            with patch(
                "goldberg_manager.cli.load_translations",
                return_value=translations,
            ) as loader:
                rendered, _ = render_status(installation, status)

        loader.assert_called_once_with()
        self.assertIn("Loaded installation", rendered)
        self.assertIn("Instalação", translations.messages)

    def test_explicit_translations_bypass_loader_and_use_supplied_object(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            installation = make_installation(Path(temporary_directory))
            status = make_status(installation)
            translations = RecordingTranslations(
                {
                    "Instalação": "Exact installation",
                    "Configuração": "Exact configuration",
                }
            )

            with patch("goldberg_manager.cli.load_translations") as loader:
                rendered, _ = render_status(
                    installation,
                    status,
                    translations=translations,
                )

        loader.assert_not_called()
        self.assertIn("Exact installation", rendered)
        self.assertIn("Exact configuration", rendered)
        self.assertIn("Instalação", translations.messages)
        self.assertIn("Configuração", translations.messages)

    def test_portuguese_default_preserves_read_only_orchestration_and_sources(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            installation = make_installation(
                root,
                data_exists=True,
                state_exists=True,
            )
            status = make_status(
                installation,
                prefix_count=2,
                emulators=(
                    SentinelEmulator(SENTINEL_GSE_EMULATOR_ID, True),
                    SentinelEmulator(SENTINEL_GOLDBERG_EMULATOR_ID, False),
                ),
                error="[red]diagnóstico oculto[/red]",
            )
            save_root = make_save_root(root, 1)
            installation_before = installation
            status_before = status

            rendered, mocks = render_status(
                installation,
                status,
                save_roots=(save_root,),
            )

        for expected in (
            "Instalação",
            "✓ Detectado",
            "Configuração",
            "✓ Válida",
            "Dados",
            "✓ Encontrados",
            "Estado",
            "✓ Encontrado",
            "Prefixos",
            "✓ 2 configurados",
            "Goldberg legado",
            "Notificações GSE",
            "✓ Habilitadas",
            "✓ Pronto para GSE",
            "Somente leitura",
            "não confirma se o processo está em execução",
        ):
            self.assertIn(expected, rendered)

        self.assertNotIn("diagnóstico oculto", rendered)
        self.assertEqual(mocks["events"], ["detect", "read_config", "resolve_roots"])
        mocks["detector"].assert_called_once_with()
        mocks["config_reader"].assert_called_once_with(installation.config_path)
        mocks["roots_resolver"].assert_called_once_with(status)
        self.assertIs(installation, installation_before)
        self.assertIs(status, status_before)
        self.assert_read_only(mocks)

    def test_english_installed_valid_state_and_single_prefix(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            installation = make_installation(root, state_exists=True)
            status = make_status(
                installation,
                prefix_count=1,
                emulators=(SentinelEmulator(SENTINEL_GSE_EMULATOR_ID, True),),
            )

            rendered, mocks = render_status(
                installation,
                status,
                save_roots=(make_save_root(root, 1),),
                translations=load_translations("en"),
            )

        for expected in (
            "Installation",
            "Detected",
            "Configuration",
            "Valid",
            "File",
            "Data",
            "Not found",
            "State",
            "Found",
            "Prefixes",
            "1 configured",
            "Enabled",
            "Legacy Goldberg",
            "GSE notifications",
            "Ready for GSE",
            "Read-only",
            "does not confirm whether the process is running",
        ):
            self.assertIn(expected, rendered)

        self.assert_read_only(mocks)

    def test_english_missing_installation_configuration_and_directories(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            installation = make_installation(
                Path(temporary_directory),
                installed=False,
            )
            status = make_status(
                installation,
                exists=False,
                valid_json=False,
                schema_valid=False,
            )

            rendered, mocks = render_status(
                installation,
                status,
                translations=load_translations("en"),
            )

        for expected in (
            "Not detected",
            "Not found",
            "None configured",
            "Not enabled",
            "GSE not configured",
            "Not configured",
        ):
            self.assertIn(expected, rendered)

        self.assertNotIn("Invalid JSON", rendered)
        self.assertNotIn("Unrecognized schema", rendered)
        self.assert_read_only(mocks)

    def test_invalid_configuration_states_preserve_precedence(self) -> None:
        cases = (
            (False, False, "Invalid JSON"),
            (True, False, "Unrecognized schema"),
        )

        for valid_json, schema_valid, expected in cases:
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as temp:
                installation = make_installation(Path(temp))
                status = make_status(
                    installation,
                    valid_json=valid_json,
                    schema_valid=schema_valid,
                )

                rendered, _ = render_status(
                    installation,
                    status,
                    translations=load_translations("en"),
                )

            self.assertIn(expected, rendered)

    def test_notification_and_watcher_tri_states(self) -> None:
        cases = (
            (
                (SentinelEmulator(SENTINEL_GSE_EMULATOR_ID, True),),
                "Enabled",
                "Ready for GSE",
            ),
            (
                (SentinelEmulator(SENTINEL_GSE_EMULATOR_ID, False),),
                "Disabled",
                "Ready for GSE",
            ),
            (
                (SentinelEmulator(SENTINEL_GOLDBERG_EMULATOR_ID, True),),
                "GSE not configured",
                "Configured without GSE",
            ),
            ((), "GSE not configured", "Not configured"),
        )

        for emulators, notification, watcher in cases:
            with (
                self.subTest(notification=notification, watcher=watcher),
                tempfile.TemporaryDirectory() as temporary_directory,
            ):
                installation = make_installation(Path(temporary_directory))
                status = make_status(
                    installation,
                    prefix_count=1,
                    emulators=emulators,
                )
                rendered, _ = render_status(
                    installation,
                    status,
                    translations=load_translations("en"),
                )

            self.assertIn(notification, rendered)
            self.assertIn(watcher, rendered)

    def test_zero_one_and_multiple_save_root_states(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            installation = make_installation(root)
            status = make_status(
                installation,
                prefix_count=1,
                emulators=(SentinelEmulator(SENTINEL_GSE_EMULATOR_ID, True),),
            )
            translations = load_translations("en")
            roots = (make_save_root(root, 1), make_save_root(root, 2))

            missing, _ = render_status(
                installation,
                status,
                translations=translations,
            )
            single, _ = render_status(
                installation,
                status,
                save_roots=roots[:1],
                translations=translations,
            )
            multiple, _ = render_status(
                installation,
                status,
                save_roots=roots,
                translations=translations,
            )

        self.assertIn("⚠ Not found", missing)
        self.assertIn("✓ Found", single)
        self.assertIn(str(roots[0].path), single)
        self.assertIn("✓ 2 found", multiple)
        self.assertNotIn(str(roots[0].path), multiple)

    def test_rich_like_translations_and_displayed_paths_are_literal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            installation = make_installation(root)
            status = make_status(
                installation,
                prefix_count=1,
                emulators=(SentinelEmulator(SENTINEL_GSE_EMULATOR_ID, True),),
            )
            save_root = make_save_root(root, 1)
            prefix_paths_before = status.prefix_paths
            data_directory_before = installation.data_directory
            state_directory_before = installation.state_directory

            rendered, _ = render_status(
                installation,
                status,
                save_roots=(save_root,),
                translations=RichLikeTranslations(),
            )

        for expected in (
            "[red]Instalação[/red]",
            "[red]Detectado[/red]",
            "[red]Somente leitura",
            str(installation.executable),
            str(installation.config_path),
            str(save_root.path),
        ):
            self.assertIn(expected, rendered)

        self.assertIs(status.prefix_paths, prefix_paths_before)
        self.assertIs(installation.data_directory, data_directory_before)
        self.assertIs(installation.state_directory, state_directory_before)

    def test_unexpected_detector_error_propagates_without_other_inspection(
        self,
    ) -> None:
        with (
            patch(
                "goldberg_manager.cli.detect_sentinel",
                side_effect=OSError("detector failure"),
            ) as detector,
            patch("goldberg_manager.cli.read_sentinel_config") as config_reader,
            patch("goldberg_manager.cli.resolve_sentinel_save_roots") as roots,
            self.assertRaisesRegex(OSError, "detector failure"),
        ):
            show_sentinel_status()

        detector.assert_called_once_with()
        config_reader.assert_not_called()
        roots.assert_not_called()

    def test_unexpected_config_reader_error_propagates_before_root_resolution(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            installation = make_installation(Path(temporary_directory))

            with (
                patch(
                    "goldberg_manager.cli.detect_sentinel",
                    return_value=installation,
                ) as detector,
                patch(
                    "goldberg_manager.cli.read_sentinel_config",
                    side_effect=OSError("reader failure"),
                ) as config_reader,
                patch("goldberg_manager.cli.resolve_sentinel_save_roots") as roots,
                self.assertRaisesRegex(OSError, "reader failure"),
            ):
                show_sentinel_status()

        detector.assert_called_once_with()
        config_reader.assert_called_once_with(installation.config_path)
        roots.assert_not_called()


if __name__ == "__main__":
    unittest.main()
