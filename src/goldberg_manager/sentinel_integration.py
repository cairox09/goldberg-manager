from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .gse_saves import GseSaveLocation, GseSaveResolution
from .sentinel import (
    SENTINEL_GOLDBERG_EMULATOR_ID,
    SENTINEL_GSE_EMULATOR_ID,
    SentinelConfigStatus,
    SentinelRuntimeSave,
    SentinelSaveRoot,
    find_sentinel_runtime_saves,
    resolve_sentinel_save_roots,
)


@dataclass(frozen=True, slots=True)
class SentinelGseLocationCoverage:
    location: GseSaveLocation
    matching_roots: tuple[SentinelSaveRoot, ...]

    @property
    def covered(self) -> bool:
        return bool(self.matching_roots)


@dataclass(frozen=True, slots=True)
class SentinelGseCoverage:
    app_id: int | None
    sentinel_status: SentinelConfigStatus
    save_resolution: GseSaveResolution | None
    gse_save_roots: tuple[SentinelSaveRoot, ...]
    location_coverages: tuple[SentinelGseLocationCoverage, ...]
    runtime_matches: tuple[SentinelRuntimeSave, ...]
    gse_runtime_matches: tuple[SentinelRuntimeSave, ...]
    legacy_runtime_matches: tuple[SentinelRuntimeSave, ...]

    @property
    def watcher_configured(self) -> bool:
        return self.sentinel_status.watcher_configured

    @property
    def gse_enabled(self) -> bool:
        return self.sentinel_status.gse_enabled

    @property
    def effective_locations(self) -> tuple[GseSaveLocation, ...]:
        return tuple(coverage.location for coverage in self.location_coverages)

    @property
    def covered_locations(self) -> tuple[GseSaveLocation, ...]:
        return tuple(
            coverage.location
            for coverage in self.location_coverages
            if coverage.covered
        )

    @property
    def uncovered_locations(self) -> tuple[GseSaveLocation, ...]:
        return tuple(
            coverage.location
            for coverage in self.location_coverages
            if not coverage.covered
        )

    @property
    def effective_save_resolved(self) -> bool:
        return bool(self.location_coverages)

    @property
    def effective_save_watched(self) -> bool:
        return any(coverage.covered for coverage in self.location_coverages)

    @property
    def fully_watched(self) -> bool:
        return self.effective_save_resolved and all(
            coverage.covered for coverage in self.location_coverages
        )

    @property
    def partially_watched(self) -> bool:
        return self.effective_save_watched and not self.fully_watched

    @property
    def unwatched(self) -> bool:
        return self.effective_save_resolved and not self.effective_save_watched

    @property
    def recognized_by_sentinel(self) -> bool:
        return bool(self.runtime_matches)

    @property
    def recognized_by_gse_runtime(self) -> bool:
        return bool(self.gse_runtime_matches)


def _normalize_path(path: Path) -> Path:
    return Path(os.path.normpath(os.path.abspath(path.expanduser())))


def resolve_sentinel_gse_coverage(
    status: SentinelConfigStatus,
    app_id: int | None,
    save_resolution: GseSaveResolution | None,
) -> SentinelGseCoverage:
    gse_save_roots = tuple(
        save_root
        for save_root in resolve_sentinel_save_roots(status)
        if save_root.emulator_id == SENTINEL_GSE_EMULATOR_ID
    )
    normalized_roots = tuple(
        (_normalize_path(save_root.path), save_root) for save_root in gse_save_roots
    )
    locations = save_resolution.locations if save_resolution is not None else ()
    location_coverages = tuple(
        SentinelGseLocationCoverage(
            location=location,
            matching_roots=tuple(
                save_root
                for normalized_root, save_root in normalized_roots
                if normalized_root == _normalize_path(location.root)
            ),
        )
        for location in locations
    )

    runtime_matches = (
        find_sentinel_runtime_saves(status, app_id) if app_id is not None else ()
    )
    gse_runtime_matches = tuple(
        match
        for match in runtime_matches
        if match.emulator_id == SENTINEL_GSE_EMULATOR_ID
    )
    legacy_runtime_matches = tuple(
        match
        for match in runtime_matches
        if match.emulator_id == SENTINEL_GOLDBERG_EMULATOR_ID
    )

    return SentinelGseCoverage(
        app_id=app_id,
        sentinel_status=status,
        save_resolution=save_resolution,
        gse_save_roots=gse_save_roots,
        location_coverages=location_coverages,
        runtime_matches=runtime_matches,
        gse_runtime_matches=gse_runtime_matches,
        legacy_runtime_matches=legacy_runtime_matches,
    )
