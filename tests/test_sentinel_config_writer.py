from __future__ import annotations

import json
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from goldberg_manager.gse_saves import GseSaveLocation, GseSaveResolution
from goldberg_manager.sentinel import (
    SENTINEL_GOLDBERG_EMULATOR_ID,
    SENTINEL_GSE_EMULATOR_ID,
    SENTINEL_GSE_RELATIVE_PATH,
    read_sentinel_config,
)
from goldberg_manager.sentinel_config_writer import (
    SentinelConfigWriteReason,
    SentinelConfigWriteStatus,
    apply_sentinel_config_repair,
)
from goldberg_manager.sentinel_integration import resolve_sentinel_gse_coverage
from goldberg_manager.sentinel_repair import plan_sentinel_gse_repair

APP_ID = 212480


def make_payload(
    *,
    prefixes: list[dict[str, object]] | None = None,
    gse_enabled: bool = True,
) -> dict[str, object]:
    emulators: list[dict[str, object]] = []

    if gse_enabled:
        emulators.append(
            {
                "id": SENTINEL_GSE_EMULATOR_ID,
                "shouldNotify": False,
            }
        )

    emulators.append(
        {
            "id": SENTINEL_GOLDBERG_EMULATOR_ID,
            "shouldNotify": True,
        }
    )

    return {
        "language": "brazilian",
        "prefixes": [] if prefixes is None else prefixes,
        "emulators": emulators,
        "SteamAPIKey": "secret-key",
        "steamDataSource": "steam",
        "notificationSound": "default",
        "achievementProgressUpdateMode": "all",
        "logLevel": "debug",
        "startOnLogin": True,
        "decky": {"enabled": False},
        "futureUnknownField": {"nested": [1, 2, 3]},
    }


def write_config(
    path: Path,
    payload: dict[str, object],
) -> bytes:
    original_bytes = (json.dumps(payload, ensure_ascii=False, indent=4) + "\n").encode(
        "utf-8"
    )
    path.write_bytes(original_bytes)
    return original_bytes


def make_standard_location(
    root: Path,
    name: str = "Game",
    *,
    create_candidate: bool = True,
    create_drive_c: bool = True,
) -> tuple[Path, Path, Path]:
    candidate = root / name / "pfx"
    drive_c = candidate / "drive_c"

    if create_drive_c:
        drive_c.mkdir(parents=True)
    elif create_candidate:
        candidate.mkdir(parents=True)

    return drive_c / SENTINEL_GSE_RELATIVE_PATH, candidate, drive_c


def make_plan(
    config_path: Path,
    roots: tuple[Path, ...],
):
    status = read_sentinel_config(config_path)
    save_resolution = GseSaveResolution(
        source="test",
        raw_value=None,
        locations=tuple(
            GseSaveLocation(source="test", root=root, app_id=APP_ID) for root in roots
        ),
    )
    coverage = resolve_sentinel_gse_coverage(
        status,
        APP_ID,
        save_resolution,
    )
    return plan_sentinel_gse_repair(coverage)


def backup_paths(config_path: Path) -> tuple[Path, ...]:
    return tuple(
        config_path.parent.glob(f"{config_path.name}.goldberg-manager-backup-*")
    )


def temporary_paths(config_path: Path) -> tuple[Path, ...]:
    return tuple(config_path.parent.glob(f".{config_path.name}.goldberg-manager-*.tmp"))


class SentinelConfigWriterTests(unittest.TestCase):
    def test_adds_safe_prefix(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            config_path = root / "config.json"
            write_config(config_path, make_payload())
            location, candidate, _ = make_standard_location(root / "prefixes")
            plan = make_plan(config_path, (location,))

            result = apply_sentinel_config_repair(plan)

            self.assertEqual(result.status, SentinelConfigWriteStatus.APPLIED)
            self.assertEqual(result.reason, SentinelConfigWriteReason.APPLIED)
            self.assertEqual(result.added_prefixes, (candidate,))
            self.assertFalse(result.partial)
            payload = json.loads(config_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["prefixes"], [{"path": str(candidate)}])

    def test_preserves_unknown_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            config_path = root / "config.json"
            before = make_payload()
            write_config(config_path, before)
            location, _, _ = make_standard_location(root / "prefixes")

            apply_sentinel_config_repair(make_plan(config_path, (location,)))

            after = json.loads(config_path.read_text(encoding="utf-8"))
            for key, value in before.items():
                if key != "prefixes":
                    self.assertEqual(after[key], value)

    def test_preserves_emulators_and_should_notify(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            config_path = root / "config.json"
            payload = make_payload()
            original_emulators = payload["emulators"]
            write_config(config_path, payload)
            location, _, _ = make_standard_location(root / "prefixes")

            apply_sentinel_config_repair(make_plan(config_path, (location,)))

            written = json.loads(config_path.read_text(encoding="utf-8"))
            self.assertEqual(written["emulators"], original_emulators)

    def test_preserves_existing_prefix_objects_and_order(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            config_path = root / "config.json"
            existing = [
                {"path": "/first", "label": "keep-me"},
                {"path": "../second", "future": {"value": True}},
            ]
            write_config(config_path, make_payload(prefixes=existing))
            location, candidate, _ = make_standard_location(root / "prefixes")

            apply_sentinel_config_repair(make_plan(config_path, (location,)))

            written = json.loads(config_path.read_text(encoding="utf-8"))
            self.assertEqual(written["prefixes"][:2], existing)
            self.assertEqual(written["prefixes"][2], {"path": str(candidate)})

    def test_backup_is_byte_for_byte_equal_to_original(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            config_path = root / "config.json"
            original_bytes = write_config(config_path, make_payload())
            location, _, _ = make_standard_location(root / "prefixes")

            result = apply_sentinel_config_repair(make_plan(config_path, (location,)))

            self.assertIsNotNone(result.backup_path)
            assert result.backup_path is not None
            self.assertEqual(result.backup_path.read_bytes(), original_bytes)

    def test_backup_does_not_overwrite_existing_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            config_path = root / "config.json"
            write_config(config_path, make_payload())
            existing_backup = config_path.with_name(
                "config.json.goldberg-manager-backup-123"
            )
            existing_backup.write_bytes(b"existing backup")
            location, _, _ = make_standard_location(root / "prefixes")

            with patch(
                "goldberg_manager.sentinel_config_writer.time.time_ns",
                return_value=123,
            ):
                result = apply_sentinel_config_repair(
                    make_plan(config_path, (location,))
                )

            self.assertEqual(existing_backup.read_bytes(), b"existing backup")
            self.assertNotEqual(result.backup_path, existing_backup)

    def test_no_change_does_not_create_backup(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            config_path = root / "config.json"
            location, candidate, _ = make_standard_location(root / "prefixes")
            write_config(
                config_path,
                make_payload(prefixes=[{"path": str(candidate)}]),
            )
            plan = make_plan(config_path, (location,))

            result = apply_sentinel_config_repair(plan)

            self.assertEqual(result.status, SentinelConfigWriteStatus.NO_CHANGE)
            self.assertIsNone(result.backup_path)
            self.assertEqual(backup_paths(config_path), ())

    def test_recalculates_coverage_and_fresh_plan(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            config_path = root / "config.json"
            write_config(config_path, make_payload())
            location, _, _ = make_standard_location(root / "prefixes")
            plan = make_plan(config_path, (location,))

            with (
                patch(
                    "goldberg_manager.sentinel_config_writer."
                    "resolve_sentinel_gse_coverage",
                    wraps=resolve_sentinel_gse_coverage,
                ) as coverage_resolver,
                patch(
                    "goldberg_manager.sentinel_config_writer.plan_sentinel_gse_repair",
                    wraps=plan_sentinel_gse_repair,
                ) as repair_planner,
            ):
                apply_sentinel_config_repair(plan)

            coverage_resolver.assert_called_once()
            self.assertIs(
                coverage_resolver.call_args.args[2],
                plan.coverage.save_resolution,
            )
            repair_planner.assert_called_once()

    def test_config_corrected_between_plan_and_write_is_no_change(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            config_path = root / "config.json"
            write_config(config_path, make_payload())
            location, candidate, _ = make_standard_location(root / "prefixes")
            plan = make_plan(config_path, (location,))
            write_config(
                config_path,
                make_payload(prefixes=[{"path": str(candidate)}]),
            )

            result = apply_sentinel_config_repair(plan)

            self.assertEqual(result.status, SentinelConfigWriteStatus.NO_CHANGE)
            self.assertEqual(backup_paths(config_path), ())

    def test_fresh_plan_cannot_expand_confirmed_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            config_path = root / "config.json"
            original = write_config(config_path, make_payload())
            location_a, candidate_a, _ = make_standard_location(
                root / "prefixes",
                "A",
            )
            location_b, candidate_b, _ = make_standard_location(
                root / "prefixes",
                "B",
            )
            original_plan = make_plan(config_path, (location_a,))
            expanded_plan = make_plan(config_path, (location_a, location_b))

            with (
                patch(
                    "goldberg_manager.sentinel_config_writer.plan_sentinel_gse_repair",
                    return_value=expanded_plan,
                ),
                patch(
                    "goldberg_manager.sentinel_config_writer._write_temporary_file"
                ) as temporary_writer,
                patch(
                    "goldberg_manager.sentinel_config_writer._create_backup"
                ) as backup_writer,
            ):
                result = apply_sentinel_config_repair(original_plan)

            self.assertEqual(result.status, SentinelConfigWriteStatus.CONFLICT)
            self.assertEqual(
                result.reason,
                SentinelConfigWriteReason.CONCURRENT_MODIFICATION,
            )
            self.assertEqual(result.added_prefixes, ())
            self.assertIsNone(result.backup_path)
            self.assertIn("não foram confirmadas", result.message)
            self.assertEqual(config_path.read_bytes(), original)
            self.assertNotIn(str(candidate_a), config_path.read_text(encoding="utf-8"))
            self.assertNotIn(str(candidate_b), config_path.read_text(encoding="utf-8"))
            self.assertEqual(backup_paths(config_path), ())
            temporary_writer.assert_not_called()
            backup_writer.assert_not_called()

    def test_fresh_plan_can_reduce_confirmed_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            config_path = root / "config.json"
            write_config(config_path, make_payload())
            location_a, candidate_a, _ = make_standard_location(
                root / "prefixes",
                "A",
            )
            location_b, candidate_b, _ = make_standard_location(
                root / "prefixes",
                "B",
            )
            original_plan = make_plan(config_path, (location_a, location_b))
            write_config(
                config_path,
                make_payload(prefixes=[{"path": str(candidate_a)}]),
            )

            result = apply_sentinel_config_repair(original_plan)

            self.assertEqual(result.status, SentinelConfigWriteStatus.APPLIED)
            self.assertEqual(result.added_prefixes, (candidate_b,))
            written = json.loads(config_path.read_text(encoding="utf-8"))
            self.assertEqual(
                written["prefixes"],
                [{"path": str(candidate_a)}, {"path": str(candidate_b)}],
            )
            self.assertEqual(len(backup_paths(config_path)), 1)

    def test_invalid_config_before_write_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            config_path = root / "config.json"
            original = write_config(config_path, make_payload())
            location, _, _ = make_standard_location(root / "prefixes")
            plan = make_plan(config_path, (location,))
            invalid = b"{invalid"
            config_path.write_bytes(invalid)

            result = apply_sentinel_config_repair(plan)

            self.assertEqual(result.status, SentinelConfigWriteStatus.REJECTED)
            self.assertEqual(result.reason, SentinelConfigWriteReason.CONFIG_INVALID)
            self.assertEqual(config_path.read_bytes(), invalid)
            self.assertNotEqual(config_path.read_bytes(), original)
            self.assertEqual(backup_paths(config_path), ())

    def test_gse_disabled_before_write_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            config_path = root / "config.json"
            write_config(config_path, make_payload())
            location, _, _ = make_standard_location(root / "prefixes")
            plan = make_plan(config_path, (location,))
            disabled_bytes = write_config(
                config_path,
                make_payload(gse_enabled=False),
            )

            result = apply_sentinel_config_repair(plan)

            self.assertEqual(result.status, SentinelConfigWriteStatus.REJECTED)
            self.assertEqual(result.reason, SentinelConfigWriteReason.GSE_DISABLED)
            self.assertEqual(config_path.read_bytes(), disabled_bytes)

    def test_nonexistent_candidate_prefix_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            config_path = root / "config.json"
            write_config(config_path, make_payload())
            location, _, _ = make_standard_location(
                root / "missing",
                create_candidate=False,
                create_drive_c=False,
            )

            result = apply_sentinel_config_repair(make_plan(config_path, (location,)))

            self.assertEqual(result.status, SentinelConfigWriteStatus.REJECTED)
            self.assertEqual(
                result.reason,
                SentinelConfigWriteReason.CANDIDATE_PREFIX_INVALID,
            )
            self.assertEqual(backup_paths(config_path), ())

    def test_nonexistent_drive_c_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            config_path = root / "config.json"
            write_config(config_path, make_payload())
            location, _, _ = make_standard_location(
                root / "prefixes",
                create_drive_c=False,
            )

            result = apply_sentinel_config_repair(make_plan(config_path, (location,)))

            self.assertEqual(result.status, SentinelConfigWriteStatus.REJECTED)
            self.assertEqual(result.reason, SentinelConfigWriteReason.DRIVE_C_INVALID)
            self.assertEqual(backup_paths(config_path), ())

    def test_partial_repair_is_rejected_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            config_path = root / "config.json"
            original = write_config(config_path, make_payload())
            safe, _, _ = make_standard_location(root / "prefixes")
            custom = root / "Sonic" / "saves"

            result = apply_sentinel_config_repair(
                make_plan(config_path, (safe, custom))
            )

            self.assertEqual(result.status, SentinelConfigWriteStatus.REJECTED)
            self.assertEqual(
                result.reason,
                SentinelConfigWriteReason.PARTIAL_NOT_ALLOWED,
            )
            self.assertEqual(config_path.read_bytes(), original)

    def test_partial_repair_requires_explicit_allow_partial(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            config_path = root / "config.json"
            write_config(config_path, make_payload())
            safe, candidate, _ = make_standard_location(root / "prefixes")
            custom = root / "Sonic" / "saves"

            result = apply_sentinel_config_repair(
                make_plan(config_path, (safe, custom)),
                allow_partial=True,
            )

            self.assertEqual(result.status, SentinelConfigWriteStatus.APPLIED)
            self.assertTrue(result.partial)
            self.assertEqual(result.added_prefixes, (candidate,))

    def test_partial_write_only_adds_safe_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            config_path = root / "config.json"
            write_config(config_path, make_payload())
            safe, candidate, _ = make_standard_location(root / "prefixes")
            custom = root / "Sonic" / "saves"
            wine_user = (
                root
                / "Other"
                / "drive_c"
                / "users"
                / "davi"
                / "AppData"
                / "Roaming"
                / "GSE Saves"
            )

            apply_sentinel_config_repair(
                make_plan(config_path, (safe, custom, wine_user)),
                allow_partial=True,
            )

            written = json.loads(config_path.read_text(encoding="utf-8"))
            self.assertEqual(written["prefixes"], [{"path": str(candidate)}])
            self.assertNotIn(str(custom), config_path.read_text(encoding="utf-8"))
            self.assertNotIn(str(wine_user), config_path.read_text(encoding="utf-8"))

    def test_unsupported_custom_location_is_not_written(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            config_path = root / "config.json"
            original = write_config(config_path, make_payload())
            custom = root / "Sonic" / "saves"

            result = apply_sentinel_config_repair(
                make_plan(config_path, (custom,)),
                allow_partial=True,
            )

            self.assertEqual(result.status, SentinelConfigWriteStatus.REJECTED)
            self.assertEqual(
                result.reason,
                SentinelConfigWriteReason.NO_SAFE_PREFIXES,
            )
            self.assertEqual(config_path.read_bytes(), original)
            self.assertEqual(backup_paths(config_path), ())

    def test_unsupported_wine_user_is_not_written(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            config_path = root / "config.json"
            original = write_config(config_path, make_payload())
            wine_user = (
                root
                / "Game"
                / "drive_c"
                / "users"
                / "davi"
                / "AppData"
                / "Roaming"
                / "GSE Saves"
            )

            result = apply_sentinel_config_repair(
                make_plan(config_path, (wine_user,)),
                allow_partial=True,
            )

            self.assertEqual(result.status, SentinelConfigWriteStatus.REJECTED)
            self.assertEqual(config_path.read_bytes(), original)

    def test_second_write_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            config_path = root / "config.json"
            write_config(config_path, make_payload())
            location, candidate, _ = make_standard_location(root / "prefixes")
            plan = make_plan(config_path, (location,))

            first = apply_sentinel_config_repair(plan)
            second = apply_sentinel_config_repair(plan)

            self.assertEqual(first.status, SentinelConfigWriteStatus.APPLIED)
            self.assertEqual(second.status, SentinelConfigWriteStatus.NO_CHANGE)
            written = json.loads(config_path.read_text(encoding="utf-8"))
            self.assertEqual(written["prefixes"], [{"path": str(candidate)}])
            self.assertEqual(len(backup_paths(config_path)), 1)

    def test_second_partial_write_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            config_path = root / "config.json"
            write_config(config_path, make_payload())
            safe, candidate, _ = make_standard_location(root / "prefixes")
            custom = root / "Sonic" / "saves"
            plan = make_plan(config_path, (safe, custom))

            first = apply_sentinel_config_repair(plan, allow_partial=True)
            second = apply_sentinel_config_repair(plan, allow_partial=True)

            self.assertEqual(first.status, SentinelConfigWriteStatus.APPLIED)
            self.assertTrue(first.partial)
            self.assertEqual(second.status, SentinelConfigWriteStatus.NO_CHANGE)
            self.assertEqual(
                second.reason,
                SentinelConfigWriteReason.ALREADY_CURRENT,
            )
            self.assertTrue(second.partial)
            written = json.loads(config_path.read_text(encoding="utf-8"))
            self.assertEqual(written["prefixes"], [{"path": str(candidate)}])
            self.assertEqual(len(backup_paths(config_path)), 1)

    def test_concurrent_change_before_replace_returns_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            config_path = root / "config.json"
            original = write_config(config_path, make_payload())
            location, _, _ = make_standard_location(root / "prefixes")
            plan = make_plan(config_path, (location,))

            with patch(
                "goldberg_manager.sentinel_config_writer._config_matches",
                side_effect=(True, False),
            ):
                result = apply_sentinel_config_repair(plan)

            self.assertEqual(result.status, SentinelConfigWriteStatus.CONFLICT)
            self.assertEqual(
                result.reason,
                SentinelConfigWriteReason.CONCURRENT_MODIFICATION,
            )
            self.assertEqual(config_path.read_bytes(), original)
            self.assertIsNotNone(result.backup_path)
            self.assertEqual(temporary_paths(config_path), ())

    def test_invalid_temporary_file_leaves_original_intact(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            config_path = root / "config.json"
            original = write_config(config_path, make_payload())
            location, _, _ = make_standard_location(root / "prefixes")

            with patch(
                "goldberg_manager.sentinel_config_writer._append_prefixes",
                return_value=b"{invalid",
            ):
                result = apply_sentinel_config_repair(
                    make_plan(config_path, (location,))
                )

            self.assertEqual(result.status, SentinelConfigWriteStatus.FAILED)
            self.assertEqual(
                result.reason,
                SentinelConfigWriteReason.TEMP_VALIDATION_FAILED,
            )
            self.assertEqual(config_path.read_bytes(), original)
            self.assertEqual(backup_paths(config_path), ())
            self.assertEqual(temporary_paths(config_path), ())

    def test_post_write_failure_rolls_back_original_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            config_path = root / "config.json"
            original = write_config(config_path, make_payload())
            location, _, _ = make_standard_location(root / "prefixes")

            with patch(
                "goldberg_manager.sentinel_config_writer._validate_written_config",
                return_value=False,
            ):
                result = apply_sentinel_config_repair(
                    make_plan(config_path, (location,))
                )

            self.assertEqual(result.status, SentinelConfigWriteStatus.ROLLED_BACK)
            self.assertEqual(
                result.reason,
                SentinelConfigWriteReason.POST_VALIDATION_FAILED,
            )
            self.assertTrue(result.rolled_back)
            self.assertEqual(config_path.read_bytes(), original)
            self.assertIsNotNone(result.backup_path)

    def test_concurrent_change_after_replace_is_not_overwritten_by_rollback(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            config_path = root / "config.json"
            write_config(config_path, make_payload())
            location, _, _ = make_standard_location(root / "prefixes")
            concurrent_bytes = write_config(
                root / "concurrent.json",
                make_payload(prefixes=[{"path": "/concurrent"}]),
            )

            def replace_with_concurrent_config(*_args) -> bool:
                config_path.write_bytes(concurrent_bytes)
                return False

            with patch(
                "goldberg_manager.sentinel_config_writer._validate_written_config",
                side_effect=replace_with_concurrent_config,
            ):
                result = apply_sentinel_config_repair(
                    make_plan(config_path, (location,))
                )

            self.assertEqual(result.status, SentinelConfigWriteStatus.CONFLICT)
            self.assertEqual(
                result.reason,
                SentinelConfigWriteReason.CONCURRENT_MODIFICATION,
            )
            self.assertFalse(result.rolled_back)
            self.assertEqual(config_path.read_bytes(), concurrent_bytes)

    def test_replace_failure_leaves_original_intact(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            config_path = root / "config.json"
            original = write_config(config_path, make_payload())
            location, _, _ = make_standard_location(root / "prefixes")

            with patch(
                "goldberg_manager.sentinel_config_writer.os.replace",
                side_effect=OSError("replace failed"),
            ):
                result = apply_sentinel_config_repair(
                    make_plan(config_path, (location,))
                )

            self.assertEqual(result.status, SentinelConfigWriteStatus.FAILED)
            self.assertEqual(config_path.read_bytes(), original)
            self.assertEqual(temporary_paths(config_path), ())

    def test_backup_failure_leaves_original_intact(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            config_path = root / "config.json"
            original = write_config(config_path, make_payload())
            location, _, _ = make_standard_location(root / "prefixes")

            with patch(
                "goldberg_manager.sentinel_config_writer._create_backup",
                side_effect=OSError("backup failed"),
            ):
                result = apply_sentinel_config_repair(
                    make_plan(config_path, (location,))
                )

            self.assertEqual(result.status, SentinelConfigWriteStatus.FAILED)
            self.assertEqual(config_path.read_bytes(), original)
            self.assertEqual(temporary_paths(config_path), ())

    def test_extreme_json_numbers_are_preserved_byte_for_byte(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            config_path = root / "config.json"
            payload = make_payload()
            original = write_config(config_path, payload).replace(
                b'"futureUnknownField": {',
                (
                    b'"futureLarge": 1e400, "futureSmall": 1e-4000, '
                    b'"futurePrecise": 0.12345678901234567890123456789, '
                    b'"futureUnknownField": {'
                ),
            )
            config_path.write_bytes(original)
            location, _, _ = make_standard_location(root / "prefixes")

            result = apply_sentinel_config_repair(make_plan(config_path, (location,)))

            self.assertEqual(result.status, SentinelConfigWriteStatus.APPLIED)
            written = config_path.read_bytes()
            self.assertIn(b'"futureLarge": 1e400', written)
            self.assertIn(b'"futureSmall": 1e-4000', written)
            self.assertIn(
                b'"futurePrecise": 0.12345678901234567890123456789',
                written,
            )

    def test_invalid_utf8_is_rejected_without_exception(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            config_path = root / "config.json"
            write_config(config_path, make_payload())
            location, _, _ = make_standard_location(root / "prefixes")
            plan = make_plan(config_path, (location,))
            invalid = b'{"prefixes": [], "emulators": []}\xff'
            config_path.write_bytes(invalid)

            result = apply_sentinel_config_repair(plan)

            self.assertEqual(result.status, SentinelConfigWriteStatus.REJECTED)
            self.assertEqual(result.reason, SentinelConfigWriteReason.CONFIG_INVALID)
            self.assertEqual(config_path.read_bytes(), invalid)

    def test_config_permissions_are_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            config_path = root / "config.json"
            write_config(config_path, make_payload())
            config_path.chmod(0o640)
            location, _, _ = make_standard_location(root / "prefixes")

            result = apply_sentinel_config_repair(make_plan(config_path, (location,)))

            self.assertEqual(result.status, SentinelConfigWriteStatus.APPLIED)
            self.assertEqual(stat.S_IMODE(config_path.stat().st_mode), 0o640)

    def test_only_prefixes_change_semantically(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            config_path = root / "config.json"
            before = make_payload(
                prefixes=[{"path": "/existing", "custom": "preserved"}]
            )
            write_config(config_path, before)
            location, candidate, _ = make_standard_location(root / "prefixes")

            apply_sentinel_config_repair(make_plan(config_path, (location,)))

            after = json.loads(config_path.read_text(encoding="utf-8"))
            before_without_prefixes = {
                k: v for k, v in before.items() if k != "prefixes"
            }
            after_without_prefixes = {k: v for k, v in after.items() if k != "prefixes"}
            self.assertEqual(after_without_prefixes, before_without_prefixes)
            self.assertEqual(
                after["prefixes"],
                before["prefixes"] + [{"path": str(candidate)}],
            )


if __name__ == "__main__":
    unittest.main()
