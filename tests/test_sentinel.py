import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from goldberg_manager.sentinel import (
    SENTINEL_GOLDBERG_EMULATOR_ID,
    SENTINEL_GSE_EMULATOR_ID,
    detect_sentinel,
    discover_sentinel_drive_c_paths,
    find_sentinel_runtime_saves,
    read_sentinel_config,
    resolve_sentinel_runtime_saves,
    resolve_sentinel_save_roots,
)


class SentinelTests(unittest.TestCase):
    def test_detects_sentinel_with_default_xdg_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            home = Path(temp_directory)
            executable = Path("/usr/local/bin/sentinel")

            with patch(
                "goldberg_manager.sentinel.shutil.which",
                return_value=str(executable),
            ):
                installation = detect_sentinel(
                    environment={},
                    home=home,
                )

            self.assertTrue(installation.installed)
            self.assertEqual(
                installation.executable,
                executable,
            )
            self.assertEqual(
                installation.config_path,
                home / ".config" / "sentinel" / "config.json",
            )
            self.assertEqual(
                installation.data_directory,
                home / ".local" / "share" / "sentinel",
            )
            self.assertEqual(
                installation.state_directory,
                home / ".local" / "state" / "sentinel",
            )
            self.assertEqual(
                installation.log_path,
                home / ".local" / "state" / "sentinel" / "logs" / "sentinel.log",
            )

    def test_detects_missing_sentinel(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            home = Path(temp_directory)

            with patch(
                "goldberg_manager.sentinel.shutil.which",
                return_value=None,
            ):
                installation = detect_sentinel(
                    environment={},
                    home=home,
                )

            self.assertFalse(installation.installed)
            self.assertIsNone(installation.executable)

    def test_honors_xdg_directories(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)

            environment = {
                "XDG_CONFIG_HOME": str(root / "config"),
                "XDG_DATA_HOME": str(root / "data"),
                "XDG_STATE_HOME": str(root / "state"),
            }

            with patch(
                "goldberg_manager.sentinel.shutil.which",
                return_value="/usr/bin/sentinel",
            ):
                installation = detect_sentinel(
                    environment=environment,
                    home=root / "home",
                )

            self.assertEqual(
                installation.config_path,
                root / "config" / "sentinel" / "config.json",
            )
            self.assertEqual(
                installation.data_directory,
                root / "data" / "sentinel",
            )
            self.assertEqual(
                installation.state_directory,
                root / "state" / "sentinel",
            )

    def test_reads_current_sentinel_config(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            config_path = Path(temp_directory) / "sentinel" / "config.json"
            config_path.parent.mkdir()

            payload = {
                "prefixes": [
                    {
                        "path": "/games/compatdata",
                    }
                ],
                "emulators": [
                    {
                        "id": SENTINEL_GSE_EMULATOR_ID,
                        "shouldNotify": True,
                    },
                    {
                        "id": SENTINEL_GOLDBERG_EMULATOR_ID,
                        "shouldNotify": False,
                    },
                ],
            }

            config_path.write_text(
                json.dumps(payload),
                encoding="utf-8",
            )

            status = read_sentinel_config(config_path)

            self.assertTrue(status.exists)
            self.assertTrue(status.valid_json)
            self.assertTrue(status.schema_valid)
            self.assertTrue(status.configured)
            self.assertTrue(status.watcher_configured)
            self.assertTrue(status.gse_watcher_configured)
            self.assertTrue(status.gse_enabled)
            self.assertTrue(status.goldberg_enabled)

            self.assertEqual(
                status.prefix_paths,
                (Path("/games/compatdata"),),
            )
            self.assertEqual(
                len(status.emulators),
                2,
            )
            self.assertTrue(status.emulators[0].should_notify)
            self.assertFalse(status.emulators[1].should_notify)

    def test_missing_config_is_not_configured(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            config_path = Path(temp_directory) / "config.json"

            status = read_sentinel_config(config_path)

            self.assertFalse(status.exists)
            self.assertFalse(status.valid_json)
            self.assertFalse(status.schema_valid)
            self.assertFalse(status.configured)
            self.assertFalse(status.watcher_configured)

    def test_rejects_invalid_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            config_path = Path(temp_directory) / "config.json"

            config_path.write_text(
                "{broken",
                encoding="utf-8",
            )

            status = read_sentinel_config(config_path)

            self.assertTrue(status.exists)
            self.assertFalse(status.valid_json)
            self.assertFalse(status.schema_valid)
            self.assertIsNotNone(status.error)

    def test_reports_invalid_schema(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            config_path = Path(temp_directory) / "config.json"

            payload = {
                "prefixes": "not-a-list",
                "emulators": [
                    {
                        "id": SENTINEL_GSE_EMULATOR_ID,
                        "shouldNotify": True,
                    }
                ],
            }

            config_path.write_text(
                json.dumps(payload),
                encoding="utf-8",
            )

            status = read_sentinel_config(config_path)

            self.assertTrue(status.valid_json)
            self.assertFalse(status.schema_valid)
            self.assertFalse(status.configured)

    def test_gse_watcher_requires_prefix(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            config_path = Path(temp_directory) / "config.json"

            payload = {
                "prefixes": [],
                "emulators": [
                    {
                        "id": SENTINEL_GSE_EMULATOR_ID,
                        "shouldNotify": True,
                    }
                ],
            }

            config_path.write_text(
                json.dumps(payload),
                encoding="utf-8",
            )

            status = read_sentinel_config(config_path)

            self.assertTrue(status.configured)
            self.assertTrue(status.gse_enabled)
            self.assertFalse(status.watcher_configured)
            self.assertFalse(status.gse_watcher_configured)

    def test_discovers_drive_c_below_configured_prefix(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)

            prefix_root = root / "Prefixes"

            drive_c = prefix_root / "Sonic" / "pfx" / "drive_c"

            drive_c.mkdir(parents=True)

            resolved = discover_sentinel_drive_c_paths(
                (prefix_root,),
            )

            self.assertEqual(
                len(resolved),
                1,
            )

            self.assertEqual(
                resolved[0].prefix_path,
                prefix_root,
            )

            self.assertEqual(
                resolved[0].drive_c,
                drive_c,
            )

    def test_discovers_drive_c_case_insensitively(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)

            prefix_root = root / "Prefixes"

            drive_c = prefix_root / "Game" / "pfx" / "DRIVE_C"

            drive_c.mkdir(parents=True)

            resolved = discover_sentinel_drive_c_paths(
                (prefix_root,),
            )

            self.assertEqual(
                len(resolved),
                1,
            )

            self.assertEqual(
                resolved[0].drive_c,
                drive_c,
            )

    def test_resolves_expected_gse_save_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)

            prefix_root = root / "Prefixes"

            drive_c = prefix_root / "Sonic" / "pfx" / "drive_c"

            drive_c.mkdir(parents=True)

            config_path = root / "config.json"

            payload = {
                "prefixes": [
                    {
                        "path": str(prefix_root),
                    }
                ],
                "emulators": [
                    {
                        "id": SENTINEL_GSE_EMULATOR_ID,
                        "shouldNotify": True,
                    }
                ],
            }

            config_path.write_text(
                json.dumps(payload),
                encoding="utf-8",
            )

            status = read_sentinel_config(config_path)

            roots = resolve_sentinel_save_roots(status)

            self.assertEqual(
                len(roots),
                1,
            )

            self.assertEqual(
                roots[0].emulator_id,
                SENTINEL_GSE_EMULATOR_ID,
            )

            self.assertEqual(
                roots[0].drive_c,
                drive_c,
            )

            self.assertEqual(
                roots[0].path,
                (drive_c / "users" / "steamuser" / "AppData" / "Roaming" / "GSE Saves"),
            )

            self.assertFalse(
                roots[0].exists,
            )

    def test_resolves_legacy_goldberg_save_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)

            prefix_root = root / "Prefixes"

            drive_c = prefix_root / "Game" / "pfx" / "drive_c"

            drive_c.mkdir(parents=True)

            config_path = root / "config.json"

            payload = {
                "prefixes": [
                    {
                        "path": str(prefix_root),
                    }
                ],
                "emulators": [
                    {
                        "id": SENTINEL_GOLDBERG_EMULATOR_ID,
                        "shouldNotify": False,
                    }
                ],
            }

            config_path.write_text(
                json.dumps(payload),
                encoding="utf-8",
            )

            status = read_sentinel_config(config_path)

            roots = resolve_sentinel_save_roots(status)

            self.assertEqual(
                len(roots),
                1,
            )

            self.assertEqual(
                roots[0].path,
                (
                    drive_c
                    / "users"
                    / "steamuser"
                    / "AppData"
                    / "Roaming"
                    / "Goldberg SteamEmu Saves"
                ),
            )

    def test_resolves_runtime_appid_and_achievements_file(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)

            prefix_root = root / "Prefixes"

            drive_c = prefix_root / "Sonic" / "pfx" / "drive_c"

            saves_directory = (
                drive_c / "users" / "steamuser" / "AppData" / "Roaming" / "GSE Saves"
            )

            app_directory = saves_directory / "212480"

            app_directory.mkdir(parents=True)

            achievements_path = app_directory / "achievements.json"

            achievements_path.write_text(
                "{}",
                encoding="utf-8",
            )

            (saves_directory / "settings").mkdir()

            config_path = root / "config.json"

            payload = {
                "prefixes": [
                    {
                        "path": str(prefix_root),
                    }
                ],
                "emulators": [
                    {
                        "id": SENTINEL_GSE_EMULATOR_ID,
                        "shouldNotify": True,
                    }
                ],
            }

            config_path.write_text(
                json.dumps(payload),
                encoding="utf-8",
            )

            status = read_sentinel_config(config_path)

            runtime_saves = resolve_sentinel_runtime_saves(
                status,
            )

            self.assertEqual(
                len(runtime_saves),
                1,
            )

            runtime_save = runtime_saves[0]

            self.assertEqual(
                runtime_save.app_id,
                212480,
            )

            self.assertEqual(
                runtime_save.app_directory,
                app_directory,
            )

            self.assertEqual(
                runtime_save.achievements_path,
                achievements_path,
            )

            self.assertTrue(
                runtime_save.achievements_exists,
            )

    def test_keeps_appid_when_runtime_achievements_are_missing(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)

            prefix_root = root / "Prefixes"

            saves_directory = (
                prefix_root
                / "Game"
                / "pfx"
                / "drive_c"
                / "users"
                / "steamuser"
                / "AppData"
                / "Roaming"
                / "GSE Saves"
            )

            app_directory = saves_directory / "212480"

            app_directory.mkdir(parents=True)

            config_path = root / "config.json"

            payload = {
                "prefixes": [
                    {
                        "path": str(prefix_root),
                    }
                ],
                "emulators": [
                    {
                        "id": SENTINEL_GSE_EMULATOR_ID,
                        "shouldNotify": True,
                    }
                ],
            }

            config_path.write_text(
                json.dumps(payload),
                encoding="utf-8",
            )

            status = read_sentinel_config(config_path)

            runtime_saves = resolve_sentinel_runtime_saves(
                status,
            )

            self.assertEqual(
                len(runtime_saves),
                1,
            )

            self.assertEqual(
                runtime_saves[0].app_id,
                212480,
            )

            self.assertFalse(
                runtime_saves[0].achievements_exists,
            )

    def test_filters_runtime_saves_by_appid(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)

            prefix_root = root / "Prefixes"

            saves_directory = (
                prefix_root
                / "Games"
                / "pfx"
                / "drive_c"
                / "users"
                / "steamuser"
                / "AppData"
                / "Roaming"
                / "GSE Saves"
            )

            (saves_directory / "212480").mkdir(
                parents=True,
            )

            (saves_directory / "123456").mkdir()

            config_path = root / "config.json"

            payload = {
                "prefixes": [
                    {
                        "path": str(prefix_root),
                    }
                ],
                "emulators": [
                    {
                        "id": SENTINEL_GSE_EMULATOR_ID,
                        "shouldNotify": True,
                    }
                ],
            }

            config_path.write_text(
                json.dumps(payload),
                encoding="utf-8",
            )

            status = read_sentinel_config(config_path)

            matches = find_sentinel_runtime_saves(
                status,
                212480,
            )

            self.assertEqual(
                len(matches),
                1,
            )

            self.assertEqual(
                matches[0].app_id,
                212480,
            )


if __name__ == "__main__":
    unittest.main()
