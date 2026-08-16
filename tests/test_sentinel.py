import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from goldberg_manager.sentinel import (
    SENTINEL_GOLDBERG_EMULATOR_ID,
    SENTINEL_GSE_EMULATOR_ID,
    detect_sentinel,
    read_sentinel_config,
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


if __name__ == "__main__":
    unittest.main()
