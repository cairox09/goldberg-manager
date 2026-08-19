from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from goldberg_manager.gse_saves import GseSaveLocation, GseSaveResolution
from goldberg_manager.sentinel import (
    SENTINEL_GOLDBERG_EMULATOR_ID,
    SENTINEL_GSE_EMULATOR_ID,
    SentinelConfigStatus,
    SentinelEmulator,
    read_sentinel_config,
)
from goldberg_manager.sentinel_integration import resolve_sentinel_gse_coverage

APP_ID = 212480


def make_status(
    prefix_paths: tuple[Path, ...],
    emulator_ids: tuple[str, ...] = (SENTINEL_GSE_EMULATOR_ID,),
) -> SentinelConfigStatus:
    return SentinelConfigStatus(
        path=Path("/config/sentinel/config.json"),
        exists=True,
        valid_json=True,
        schema_valid=True,
        prefix_paths=prefix_paths,
        emulators=tuple(
            SentinelEmulator(id=emulator_id, should_notify=True)
            for emulator_id in emulator_ids
        ),
    )


def make_sentinel_layout(
    root: Path,
    emulator_ids: tuple[str, ...] = (SENTINEL_GSE_EMULATOR_ID,),
) -> tuple[SentinelConfigStatus, Path, Path]:
    prefix_root = root / "prefixes"
    drive_c = prefix_root / "Game" / "pfx" / "drive_c"
    drive_c.mkdir(parents=True)
    roaming = drive_c / "users" / "steamuser" / "AppData" / "Roaming"
    return (
        make_status((prefix_root,), emulator_ids),
        roaming / "GSE Saves",
        roaming / "Goldberg SteamEmu Saves",
    )


def make_save_resolution(
    roots: tuple[Path, ...],
    app_id: int = APP_ID,
) -> GseSaveResolution:
    return GseSaveResolution(
        source="test",
        raw_value=None,
        locations=tuple(
            GseSaveLocation(source="test", root=root, app_id=app_id) for root in roots
        ),
    )


class SentinelIntegrationTests(unittest.TestCase):
    def test_exact_gse_root_is_covered(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            status, gse_root, _ = make_sentinel_layout(Path(temp_directory))
            save_resolution = make_save_resolution((gse_root,))

            coverage = resolve_sentinel_gse_coverage(
                status,
                APP_ID,
                save_resolution,
            )

            self.assertTrue(coverage.watcher_configured)
            self.assertTrue(coverage.gse_enabled)
            self.assertTrue(coverage.effective_save_resolved)
            self.assertTrue(coverage.effective_save_watched)
            self.assertTrue(coverage.fully_watched)
            self.assertFalse(coverage.partially_watched)
            self.assertFalse(coverage.unwatched)
            self.assertEqual(coverage.covered_locations, save_resolution.locations)
            self.assertEqual(coverage.uncovered_locations, ())
            self.assertEqual(len(coverage.gse_save_roots), 1)

    def test_custom_gse_root_outside_sentinel_is_unwatched(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            status, _, _ = make_sentinel_layout(root)
            save_resolution = make_save_resolution((root / "game" / "saves",))

            coverage = resolve_sentinel_gse_coverage(
                status,
                APP_ID,
                save_resolution,
            )

            self.assertFalse(coverage.effective_save_watched)
            self.assertTrue(coverage.unwatched)
            self.assertEqual(coverage.covered_locations, ())
            self.assertEqual(coverage.uncovered_locations, save_resolution.locations)

    def test_runtime_recognition_does_not_imply_effective_save_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            status, gse_root, _ = make_sentinel_layout(root)
            (gse_root / str(APP_ID)).mkdir(parents=True)

            coverage = resolve_sentinel_gse_coverage(
                status,
                APP_ID,
                make_save_resolution((root / "game" / "saves",)),
            )

            self.assertTrue(coverage.recognized_by_sentinel)
            self.assertTrue(coverage.recognized_by_gse_runtime)
            self.assertFalse(coverage.effective_save_watched)
            self.assertTrue(coverage.unwatched)

    def test_preserves_gse_runtime_matches(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            status, gse_root, _ = make_sentinel_layout(root)
            app_directory = gse_root / str(APP_ID)
            app_directory.mkdir(parents=True)

            coverage = resolve_sentinel_gse_coverage(
                status,
                APP_ID,
                make_save_resolution((gse_root,)),
            )

            self.assertEqual(len(coverage.runtime_matches), 1)
            self.assertEqual(len(coverage.gse_runtime_matches), 1)
            self.assertEqual(coverage.legacy_runtime_matches, ())
            self.assertEqual(
                coverage.gse_runtime_matches[0].app_directory,
                app_directory,
            )

    def test_preserves_legacy_only_runtime_recognition(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            status, _, legacy_root = make_sentinel_layout(
                root,
                (SENTINEL_GOLDBERG_EMULATOR_ID,),
            )
            (legacy_root / str(APP_ID)).mkdir(parents=True)

            coverage = resolve_sentinel_gse_coverage(
                status,
                APP_ID,
                make_save_resolution((root / "game" / "saves",)),
            )

            self.assertTrue(coverage.recognized_by_sentinel)
            self.assertFalse(coverage.recognized_by_gse_runtime)
            self.assertEqual(coverage.gse_runtime_matches, ())
            self.assertEqual(len(coverage.legacy_runtime_matches), 1)

    def test_gse_disabled_is_distinct_from_watcher_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            status, _, _ = make_sentinel_layout(
                root,
                (SENTINEL_GOLDBERG_EMULATOR_ID,),
            )

            coverage = resolve_sentinel_gse_coverage(
                status,
                APP_ID,
                make_save_resolution((root / "saves",)),
            )

            self.assertTrue(coverage.watcher_configured)
            self.assertFalse(coverage.gse_enabled)
            self.assertEqual(coverage.gse_save_roots, ())
            self.assertFalse(coverage.effective_save_watched)

    def test_gse_watcher_without_prefixes_has_no_derived_roots(self) -> None:
        status = make_status(())

        coverage = resolve_sentinel_gse_coverage(
            status,
            APP_ID,
            make_save_resolution((Path("/saves"),)),
        )

        self.assertTrue(coverage.gse_enabled)
        self.assertFalse(coverage.watcher_configured)
        self.assertEqual(coverage.gse_save_roots, ())
        self.assertTrue(coverage.unwatched)

    def test_invalid_config_status_is_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            config_path = Path(temp_directory) / "config.json"
            config_path.write_text("{invalid", encoding="utf-8")
            status = read_sentinel_config(config_path)

            coverage = resolve_sentinel_gse_coverage(
                status,
                APP_ID,
                make_save_resolution((Path(temp_directory) / "saves",)),
            )

            self.assertIs(coverage.sentinel_status, status)
            self.assertTrue(coverage.sentinel_status.exists)
            self.assertFalse(coverage.sentinel_status.valid_json)
            self.assertFalse(coverage.sentinel_status.schema_valid)
            self.assertFalse(coverage.watcher_configured)
            self.assertEqual(coverage.gse_save_roots, ())

    def test_missing_and_schema_invalid_configs_remain_distinct(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            missing_status = read_sentinel_config(root / "missing.json")
            schema_path = root / "schema.json"
            schema_path.write_text(
                json.dumps({"prefixes": "invalid", "emulators": []}),
                encoding="utf-8",
            )
            schema_status = read_sentinel_config(schema_path)

            missing = resolve_sentinel_gse_coverage(missing_status, APP_ID, None)
            invalid_schema = resolve_sentinel_gse_coverage(
                schema_status,
                APP_ID,
                None,
            )

            self.assertFalse(missing.sentinel_status.exists)
            self.assertFalse(missing.sentinel_status.valid_json)
            self.assertTrue(invalid_schema.sentinel_status.exists)
            self.assertTrue(invalid_schema.sentinel_status.valid_json)
            self.assertFalse(invalid_schema.sentinel_status.schema_valid)

    def test_save_resolution_without_locations_is_not_watched(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            status, _, _ = make_sentinel_layout(Path(temp_directory))

            coverage = resolve_sentinel_gse_coverage(
                status,
                APP_ID,
                make_save_resolution(()),
            )

            self.assertFalse(coverage.effective_save_resolved)
            self.assertFalse(coverage.effective_save_watched)
            self.assertFalse(coverage.fully_watched)
            self.assertFalse(coverage.partially_watched)
            self.assertFalse(coverage.unwatched)

    def test_none_appid_has_no_runtime_recognition(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            status, gse_root, _ = make_sentinel_layout(root)
            (gse_root / str(APP_ID)).mkdir(parents=True)

            coverage = resolve_sentinel_gse_coverage(
                status,
                None,
                make_save_resolution((gse_root,)),
            )

            self.assertIsNone(coverage.app_id)
            self.assertEqual(coverage.runtime_matches, ())
            self.assertEqual(coverage.gse_runtime_matches, ())
            self.assertEqual(coverage.legacy_runtime_matches, ())
            self.assertFalse(coverage.recognized_by_sentinel)
            self.assertFalse(coverage.recognized_by_gse_runtime)

    def test_multiple_locations_all_covered(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            first_status, first_gse_root, _ = make_sentinel_layout(root / "first")
            second_status, second_gse_root, _ = make_sentinel_layout(root / "second")
            status = make_status(
                first_status.prefix_paths + second_status.prefix_paths,
            )
            save_resolution = make_save_resolution(
                (first_gse_root, second_gse_root),
            )

            coverage = resolve_sentinel_gse_coverage(
                status,
                APP_ID,
                save_resolution,
            )

            self.assertTrue(coverage.fully_watched)
            self.assertFalse(coverage.partially_watched)
            self.assertFalse(coverage.unwatched)
            self.assertEqual(coverage.covered_locations, save_resolution.locations)

    def test_multiple_locations_partially_covered(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            status, gse_root, _ = make_sentinel_layout(root)
            custom_root = root / "game" / "saves"
            save_resolution = make_save_resolution((gse_root, custom_root))

            coverage = resolve_sentinel_gse_coverage(
                status,
                APP_ID,
                save_resolution,
            )

            self.assertFalse(coverage.fully_watched)
            self.assertTrue(coverage.partially_watched)
            self.assertFalse(coverage.unwatched)
            self.assertEqual(
                coverage.covered_locations,
                (save_resolution.locations[0],),
            )
            self.assertEqual(
                coverage.uncovered_locations,
                (save_resolution.locations[1],),
            )

    def test_multiple_locations_none_covered(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            status, _, _ = make_sentinel_layout(root)
            save_resolution = make_save_resolution(
                (root / "game-a" / "saves", root / "game-b" / "saves"),
            )

            coverage = resolve_sentinel_gse_coverage(
                status,
                APP_ID,
                save_resolution,
            )

            self.assertFalse(coverage.effective_save_watched)
            self.assertFalse(coverage.fully_watched)
            self.assertFalse(coverage.partially_watched)
            self.assertTrue(coverage.unwatched)
            self.assertEqual(coverage.uncovered_locations, save_resolution.locations)

    def test_lexically_equivalent_paths_are_covered(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            status, gse_root, _ = make_sentinel_layout(Path(temp_directory))
            relative_root = Path(
                os.path.relpath(
                    gse_root / "temporary" / "..",
                    Path.cwd(),
                )
            )

            coverage = resolve_sentinel_gse_coverage(
                status,
                APP_ID,
                make_save_resolution((relative_root,)),
            )

            self.assertTrue(coverage.effective_save_watched)
            self.assertTrue(coverage.fully_watched)

    def test_legacy_root_does_not_cover_current_gse_save(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            status, _, legacy_root = make_sentinel_layout(
                root,
                (
                    SENTINEL_GSE_EMULATOR_ID,
                    SENTINEL_GOLDBERG_EMULATOR_ID,
                ),
            )
            (legacy_root / str(APP_ID)).mkdir(parents=True)

            coverage = resolve_sentinel_gse_coverage(
                status,
                APP_ID,
                make_save_resolution((legacy_root,)),
            )

            self.assertTrue(coverage.recognized_by_sentinel)
            self.assertEqual(len(coverage.legacy_runtime_matches), 1)
            self.assertFalse(coverage.effective_save_watched)
            self.assertTrue(coverage.unwatched)


if __name__ == "__main__":
    unittest.main()
