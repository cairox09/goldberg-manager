from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from goldberg_manager.gse_saves import GseSaveLocation, GseSaveResolution
from goldberg_manager.sentinel import (
    SENTINEL_GOLDBERG_EMULATOR_ID,
    SENTINEL_GSE_EMULATOR_ID,
    SentinelConfigStatus,
    SentinelEmulator,
    SentinelRuntimeSave,
    SentinelSaveRoot,
)
from goldberg_manager.sentinel_integration import (
    SentinelGseCoverage,
    SentinelGseLocationCoverage,
    resolve_sentinel_gse_coverage,
)
from goldberg_manager.sentinel_repair import (
    SentinelRepairConfigState,
    SentinelRepairKind,
    plan_sentinel_gse_repair,
)

APP_ID = 212480


def make_status(
    *,
    exists: bool = True,
    valid_json: bool = True,
    schema_valid: bool = True,
    prefixes: tuple[Path, ...] = (),
    emulator_ids: tuple[str, ...] = (SENTINEL_GSE_EMULATOR_ID,),
) -> SentinelConfigStatus:
    return SentinelConfigStatus(
        path=Path("/config/sentinel/config.json"),
        exists=exists,
        valid_json=valid_json,
        schema_valid=schema_valid,
        prefix_paths=prefixes,
        emulators=tuple(
            SentinelEmulator(id=emulator_id, should_notify=True)
            for emulator_id in emulator_ids
        ),
    )


def make_coverage(
    roots: tuple[Path, ...],
    *,
    status: SentinelConfigStatus | None = None,
    covered_indexes: tuple[int, ...] = (),
    runtime_emulator_ids: tuple[str, ...] = (),
) -> SentinelGseCoverage:
    sentinel_status = make_status() if status is None else status
    locations = tuple(
        GseSaveLocation(source="test", root=root, app_id=APP_ID) for root in roots
    )
    save_resolution = GseSaveResolution(
        source="test",
        raw_value=None,
        locations=locations,
    )
    matching_roots = tuple(
        SentinelSaveRoot(
            emulator_id=SENTINEL_GSE_EMULATOR_ID,
            prefix_path=Path("/prefixes"),
            drive_c=location.root.parents[4],
            path=location.root,
        )
        for index, location in enumerate(locations)
        if index in covered_indexes
    )
    location_coverages = tuple(
        SentinelGseLocationCoverage(
            location=location,
            matching_roots=tuple(
                save_root
                for save_root in matching_roots
                if save_root.path == location.root
            ),
        )
        for location in locations
    )
    runtime_matches = tuple(
        SentinelRuntimeSave(
            emulator_id=emulator_id,
            prefix_path=Path("/prefixes"),
            drive_c=Path("/prefixes/Game/pfx/drive_c"),
            saves_directory=Path("/runtime") / emulator_id,
            app_id=APP_ID,
            app_directory=Path("/runtime") / emulator_id / str(APP_ID),
            achievements_path=(
                Path("/runtime") / emulator_id / str(APP_ID) / "achievements.json"
            ),
        )
        for emulator_id in runtime_emulator_ids
    )
    return SentinelGseCoverage(
        app_id=APP_ID,
        sentinel_status=sentinel_status,
        save_resolution=save_resolution,
        gse_save_roots=matching_roots,
        location_coverages=location_coverages,
        runtime_matches=runtime_matches,
        gse_runtime_matches=tuple(
            match
            for match in runtime_matches
            if match.emulator_id == SENTINEL_GSE_EMULATOR_ID
        ),
        legacy_runtime_matches=tuple(
            match
            for match in runtime_matches
            if match.emulator_id == SENTINEL_GOLDBERG_EMULATOR_ID
        ),
    )


def standard_gse_root(base: Path, drive_c_name: str = "drive_c") -> Path:
    return (
        base
        / "Game"
        / "pfx"
        / drive_c_name
        / "users"
        / "steamuser"
        / "AppData"
        / "Roaming"
        / "GSE Saves"
    )


class SentinelRepairTests(unittest.TestCase):
    def test_already_covered_location_needs_no_repair(self) -> None:
        root = standard_gse_root(Path("/prefixes"))

        plan = plan_sentinel_gse_repair(make_coverage((root,), covered_indexes=(0,)))

        self.assertEqual(
            plan.location_plans[0].kind,
            SentinelRepairKind.ALREADY_COVERED,
        )
        self.assertFalse(plan.needs_repair)
        self.assertEqual(plan.candidate_prefixes, ())

    def test_standard_steamuser_layout_can_add_prefix(self) -> None:
        root = standard_gse_root(Path("/games"))

        plan = plan_sentinel_gse_repair(make_coverage((root,)))

        location_plan = plan.location_plans[0]
        self.assertEqual(location_plan.kind, SentinelRepairKind.ADD_PREFIX)
        self.assertEqual(location_plan.drive_c, root.parents[4])
        self.assertTrue(plan.has_safe_prefix_additions)
        self.assertTrue(plan.fully_repairable_via_sentinel_config)

    def test_candidate_prefix_is_drive_c_parent(self) -> None:
        root = standard_gse_root(Path("/games"), "DRIVE_C")

        plan = plan_sentinel_gse_repair(make_coverage((root,)))

        self.assertEqual(
            plan.location_plans[0].candidate_prefix,
            root.parents[4].parent,
        )
        self.assertEqual(plan.candidate_prefixes, (root.parents[4].parent,))

    def test_custom_local_save_path_is_unsupported(self) -> None:
        root = Path("/games/Sonic/saves")

        plan = plan_sentinel_gse_repair(make_coverage((root,)))

        assert plan.coverage.save_resolution is not None
        self.assertTrue(plan.coverage.save_resolution.resolved)
        self.assertFalse(plan.coverage.save_resolution.ambiguous)
        self.assertEqual(
            plan.location_plans[0].kind,
            SentinelRepairKind.UNSUPPORTED_CUSTOM_SAVE_ROOT,
        )
        self.assertIsNone(plan.location_plans[0].candidate_prefix)
        self.assertTrue(plan.requires_gse_change)
        self.assertFalse(plan.has_safe_prefix_additions)

    def test_non_steamuser_wine_path_is_unsupported(self) -> None:
        root = (
            Path("/games/Game/pfx/drive_c")
            / "users"
            / "davi"
            / "AppData"
            / "Roaming"
            / "GSE Saves"
        )

        plan = plan_sentinel_gse_repair(make_coverage((root,)))

        self.assertEqual(
            plan.location_plans[0].kind,
            SentinelRepairKind.UNSUPPORTED_WINE_USER,
        )
        self.assertIsNone(plan.location_plans[0].candidate_prefix)
        self.assertTrue(plan.requires_gse_change)

    def test_unresolved_save_does_not_assert_repair(self) -> None:
        plan = plan_sentinel_gse_repair(make_coverage(()))

        self.assertEqual(
            plan.location_plans[0].kind,
            SentinelRepairKind.UNRESOLVED,
        )
        self.assertFalse(plan.needs_repair)
        self.assertFalse(plan.repairable_via_sentinel_config)
        self.assertFalse(plan.requires_gse_change)

    def test_ambiguous_cross_prefix_roots_do_not_produce_repair(self) -> None:
        roots = (
            Path("/prefixes/Resident Evil 2/drive_c")
            / "users"
            / "davica"
            / "AppData"
            / "Roaming"
            / "GSE Saves",
            Path("/prefixes/Assassins Creed II/drive_c")
            / "users"
            / "steamuser"
            / "AppData"
            / "Roaming"
            / "GSE Saves",
        )
        save_resolution = GseSaveResolution(
            source="default",
            raw_value=None,
            locations=tuple(
                GseSaveLocation(source="default", root=root, app_id=APP_ID)
                for root in roots
            ),
        )
        coverage = resolve_sentinel_gse_coverage(
            make_status(),
            APP_ID,
            save_resolution,
        )

        plan = plan_sentinel_gse_repair(coverage)

        self.assertTrue(save_resolution.ambiguous)
        self.assertFalse(coverage.effective_save_resolved)
        self.assertFalse(coverage.unwatched)
        self.assertFalse(plan.needs_repair)
        self.assertFalse(plan.requires_gse_change)
        self.assertEqual(plan.candidate_prefixes, ())
        self.assertEqual(
            plan.location_plans[0].kind,
            SentinelRepairKind.UNRESOLVED,
        )

    def test_invalid_json_blocks_candidate_prefixes(self) -> None:
        status = make_status(valid_json=False, schema_valid=False)
        root = standard_gse_root(Path("/games"))

        plan = plan_sentinel_gse_repair(make_coverage((root,), status=status))

        self.assertEqual(
            plan.config_state,
            SentinelRepairConfigState.INVALID_JSON,
        )
        self.assertFalse(plan.config_valid)
        self.assertEqual(plan.location_plans[0].kind, SentinelRepairKind.ADD_PREFIX)
        self.assertIsNone(plan.location_plans[0].candidate_prefix)
        self.assertEqual(plan.candidate_prefixes, ())
        self.assertFalse(plan.repairable_via_sentinel_config)

    def test_missing_config_blocks_candidate_prefixes(self) -> None:
        status = make_status(
            exists=False,
            valid_json=False,
            schema_valid=False,
        )
        root = standard_gse_root(Path("/games"))

        plan = plan_sentinel_gse_repair(make_coverage((root,), status=status))

        self.assertEqual(plan.config_state, SentinelRepairConfigState.MISSING)
        self.assertIsNone(plan.location_plans[0].candidate_prefix)
        self.assertEqual(plan.candidate_prefixes, ())
        self.assertFalse(plan.has_safe_prefix_additions)

    def test_invalid_schema_is_preserved_separately(self) -> None:
        status = make_status(schema_valid=False)

        plan = plan_sentinel_gse_repair(
            make_coverage((standard_gse_root(Path("/games")),), status=status)
        )

        self.assertEqual(
            plan.config_state,
            SentinelRepairConfigState.INVALID_SCHEMA,
        )
        self.assertEqual(plan.candidate_prefixes, ())

    def test_fully_watched_coverage_needs_no_repair(self) -> None:
        roots = (
            standard_gse_root(Path("/prefix-a")),
            standard_gse_root(Path("/prefix-b")),
        )

        plan = plan_sentinel_gse_repair(make_coverage(roots, covered_indexes=(0, 1)))

        self.assertFalse(plan.needs_repair)
        self.assertFalse(plan.repairable_via_sentinel_config)
        self.assertEqual(plan.candidate_prefixes, ())

    def test_partially_watched_plans_only_safe_uncovered_location(self) -> None:
        covered = standard_gse_root(Path("/prefix-a"))
        uncovered = standard_gse_root(Path("/prefix-b"))

        plan = plan_sentinel_gse_repair(
            make_coverage((covered, uncovered), covered_indexes=(0,))
        )

        self.assertTrue(plan.needs_repair)
        self.assertEqual(
            tuple(location.kind for location in plan.location_plans),
            (
                SentinelRepairKind.ALREADY_COVERED,
                SentinelRepairKind.ADD_PREFIX,
            ),
        )
        self.assertEqual(plan.candidate_prefixes, (uncovered.parents[4].parent,))
        self.assertTrue(plan.fully_repairable_via_sentinel_config)

    def test_partially_watched_with_unsupported_location_requires_gse_change(
        self,
    ) -> None:
        covered = standard_gse_root(Path("/prefix-a"))
        unsupported = Path("/games/Sonic/saves")

        plan = plan_sentinel_gse_repair(
            make_coverage((covered, unsupported), covered_indexes=(0,))
        )

        self.assertTrue(plan.needs_repair)
        self.assertTrue(plan.requires_gse_change)
        self.assertFalse(plan.repairable_via_sentinel_config)

    def test_mixed_uncovered_locations_are_only_partially_repairable(self) -> None:
        safe = standard_gse_root(Path("/prefix-a"))
        unsupported = Path("/games/Sonic/saves")

        plan = plan_sentinel_gse_repair(make_coverage((safe, unsupported)))

        self.assertFalse(plan.fully_repairable_via_sentinel_config)
        self.assertTrue(plan.partially_repairable_via_sentinel_config)
        self.assertTrue(plan.repairable_via_sentinel_config)
        self.assertTrue(plan.requires_gse_change)
        self.assertEqual(plan.candidate_prefixes, (safe.parents[4].parent,))

    def test_multiple_safe_candidates_are_preserved(self) -> None:
        first = standard_gse_root(Path("/prefix-a"))
        second = standard_gse_root(Path("/prefix-b"))

        plan = plan_sentinel_gse_repair(make_coverage((first, second)))

        self.assertEqual(
            plan.candidate_prefixes,
            (first.parents[4].parent, second.parents[4].parent),
        )
        self.assertTrue(plan.fully_repairable_via_sentinel_config)

    def test_duplicate_candidate_prefixes_are_deduplicated(self) -> None:
        first = standard_gse_root(Path("/prefix"))
        equivalent = first.parent / "temporary" / ".." / "GSE Saves"

        plan = plan_sentinel_gse_repair(make_coverage((first, equivalent)))

        self.assertEqual(plan.candidate_prefixes, (first.parents[4].parent,))

    def test_existing_prefix_ancestor_prevents_duplicate_addition(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            prefix = Path(temp_directory) / "prefixes"
            root = standard_gse_root(prefix)
            drive_c = root.parents[4]
            drive_c.mkdir(parents=True)
            status = make_status(prefixes=(prefix,))

            plan = plan_sentinel_gse_repair(make_coverage((root,), status=status))

            location_plan = plan.location_plans[0]
            self.assertEqual(
                location_plan.kind,
                SentinelRepairKind.PREFIX_ALREADY_CONFIGURED,
            )
            self.assertEqual(location_plan.configured_prefix, prefix)
            self.assertEqual(plan.candidate_prefixes, ())

    def test_configured_prefix_is_not_a_representable_repair_action(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            prefix = Path(temp_directory) / "prefixes"
            root = standard_gse_root(prefix)
            root.parents[4].mkdir(parents=True)
            status = make_status(prefixes=(prefix,))

            plan = plan_sentinel_gse_repair(make_coverage((root,), status=status))

            self.assertEqual(
                plan.location_plans[0].kind,
                SentinelRepairKind.PREFIX_ALREADY_CONFIGURED,
            )
            self.assertTrue(plan.gse_enabled)
            self.assertTrue(plan.needs_repair)
            self.assertFalse(plan.has_safe_prefix_additions)
            self.assertFalse(plan.fully_repairable_via_sentinel_config)
            self.assertFalse(plan.partially_repairable_via_sentinel_config)
            self.assertFalse(plan.repairable_via_sentinel_config)

    def test_legacy_goldberg_path_is_not_a_gse_repair_target(self) -> None:
        root = (
            Path("/games/Game/pfx/drive_c")
            / "users"
            / "steamuser"
            / "AppData"
            / "Roaming"
            / "Goldberg SteamEmu Saves"
        )

        plan = plan_sentinel_gse_repair(make_coverage((root,)))

        self.assertEqual(
            plan.location_plans[0].kind,
            SentinelRepairKind.UNSUPPORTED_CUSTOM_SAVE_ROOT,
        )
        self.assertEqual(plan.candidate_prefixes, ())

    def test_gse_and_prefix_facts_remain_separate_from_path_classification(
        self,
    ) -> None:
        status = make_status(
            prefixes=(),
            emulator_ids=(SENTINEL_GOLDBERG_EMULATOR_ID,),
        )
        root = standard_gse_root(Path("/games"))

        plan = plan_sentinel_gse_repair(make_coverage((root,), status=status))

        self.assertFalse(plan.gse_enabled)
        self.assertFalse(plan.has_prefixes)
        self.assertEqual(plan.location_plans[0].kind, SentinelRepairKind.ADD_PREFIX)

    def test_gse_disabled_blocks_repairability_with_safe_prefix(self) -> None:
        status = make_status(
            emulator_ids=(SENTINEL_GOLDBERG_EMULATOR_ID,),
        )
        root = standard_gse_root(Path("/games"))

        plan = plan_sentinel_gse_repair(make_coverage((root,), status=status))

        self.assertEqual(plan.location_plans[0].kind, SentinelRepairKind.ADD_PREFIX)
        self.assertTrue(plan.has_safe_prefix_additions)
        self.assertFalse(plan.gse_enabled)
        self.assertFalse(plan.fully_repairable_via_sentinel_config)
        self.assertFalse(plan.partially_repairable_via_sentinel_config)
        self.assertFalse(plan.repairable_via_sentinel_config)
        self.assertFalse(plan.requires_gse_change)

    def test_sonic_recognition_does_not_change_custom_root_repair(self) -> None:
        sonic_root = Path(
            "/games/Sonic & All-Stars Racing Transformed Collection/saves"
        )
        coverage = make_coverage(
            (sonic_root,),
            runtime_emulator_ids=(
                SENTINEL_GSE_EMULATOR_ID,
                SENTINEL_GOLDBERG_EMULATOR_ID,
            ),
        )

        self.assertTrue(coverage.recognized_by_sentinel)

        plan = plan_sentinel_gse_repair(coverage)

        assert coverage.save_resolution is not None
        self.assertTrue(coverage.save_resolution.resolved)
        self.assertFalse(coverage.save_resolution.ambiguous)
        self.assertTrue(plan.needs_repair)
        self.assertFalse(plan.has_safe_prefix_additions)
        self.assertFalse(plan.fully_repairable_via_sentinel_config)
        self.assertTrue(plan.requires_gse_change)
        self.assertEqual(
            plan.location_plans[0].kind,
            SentinelRepairKind.UNSUPPORTED_CUSTOM_SAVE_ROOT,
        )
        self.assertIsNone(plan.location_plans[0].candidate_prefix)


if __name__ == "__main__":
    unittest.main()
