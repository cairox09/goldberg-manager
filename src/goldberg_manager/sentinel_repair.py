from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from .gse_saves import GseSaveLocation
from .sentinel import SENTINEL_GSE_RELATIVE_PATH, SentinelConfigStatus
from .sentinel_integration import (
    SentinelGseCoverage,
    SentinelGseLocationCoverage,
)


class SentinelRepairKind(str, Enum):
    ALREADY_COVERED = "already-covered"
    ADD_PREFIX = "add-prefix"
    PREFIX_ALREADY_CONFIGURED = "prefix-already-configured"
    UNSUPPORTED_CUSTOM_SAVE_ROOT = "unsupported-custom-save-root"
    UNSUPPORTED_WINE_USER = "unsupported-wine-user"
    UNRESOLVED = "unresolved"


class SentinelRepairConfigState(str, Enum):
    VALID = "valid"
    MISSING = "missing"
    INVALID_JSON = "invalid-json"
    INVALID_SCHEMA = "invalid-schema"


@dataclass(frozen=True, slots=True)
class SentinelLocationRepairPlan:
    kind: SentinelRepairKind
    location_coverage: SentinelGseLocationCoverage | None
    drive_c: Path | None = None
    candidate_prefix: Path | None = None
    configured_prefix: Path | None = None

    @property
    def location(self) -> GseSaveLocation | None:
        if self.location_coverage is None:
            return None

        return self.location_coverage.location

    @property
    def covered(self) -> bool:
        return self.location_coverage is not None and self.location_coverage.covered


@dataclass(frozen=True, slots=True)
class SentinelRepairPlan:
    coverage: SentinelGseCoverage
    config_state: SentinelRepairConfigState
    location_plans: tuple[SentinelLocationRepairPlan, ...]

    @property
    def config_valid(self) -> bool:
        return self.config_state is SentinelRepairConfigState.VALID

    @property
    def gse_enabled(self) -> bool:
        return self.coverage.gse_enabled

    @property
    def has_prefixes(self) -> bool:
        return bool(self.coverage.sentinel_status.prefix_paths)

    @property
    def uncovered_location_plans(self) -> tuple[SentinelLocationRepairPlan, ...]:
        return tuple(
            plan
            for plan in self.location_plans
            if plan.location_coverage is not None and not plan.covered
        )

    @property
    def needs_repair(self) -> bool:
        return self.coverage.effective_save_resolved and bool(
            self.uncovered_location_plans
        )

    @property
    def candidate_prefixes(self) -> tuple[Path, ...]:
        if not self.config_valid:
            return ()

        candidates: list[Path] = []
        seen: set[Path] = set()

        for plan in self.uncovered_location_plans:
            if (
                plan.kind is not SentinelRepairKind.ADD_PREFIX
                or plan.candidate_prefix is None
            ):
                continue

            normalized = _normalize_path(plan.candidate_prefix)

            if normalized in seen:
                continue

            seen.add(normalized)
            candidates.append(normalized)

        return tuple(candidates)

    @property
    def has_safe_prefix_additions(self) -> bool:
        return bool(self.candidate_prefixes)

    @property
    def fully_repairable_via_sentinel_config(self) -> bool:
        uncovered = self.uncovered_location_plans
        return (
            self.needs_repair
            and self.config_valid
            and self.gse_enabled
            and all(
                plan.kind is SentinelRepairKind.ADD_PREFIX
                and plan.candidate_prefix is not None
                for plan in uncovered
            )
        )

    @property
    def partially_repairable_via_sentinel_config(self) -> bool:
        return (
            self.needs_repair
            and self.config_valid
            and self.gse_enabled
            and not self.fully_repairable_via_sentinel_config
            and any(
                plan.kind is SentinelRepairKind.ADD_PREFIX
                and plan.candidate_prefix is not None
                for plan in self.uncovered_location_plans
            )
        )

    @property
    def repairable_via_sentinel_config(self) -> bool:
        return (
            self.fully_repairable_via_sentinel_config
            or self.partially_repairable_via_sentinel_config
        )

    @property
    def requires_gse_change(self) -> bool:
        unsupported_kinds = {
            SentinelRepairKind.UNSUPPORTED_CUSTOM_SAVE_ROOT,
            SentinelRepairKind.UNSUPPORTED_WINE_USER,
        }
        return self.needs_repair and any(
            plan.kind in unsupported_kinds for plan in self.uncovered_location_plans
        )


def _normalize_path(path: Path) -> Path:
    return Path(os.path.normpath(os.path.abspath(path.expanduser())))


def _config_state(status: SentinelConfigStatus) -> SentinelRepairConfigState:
    if not status.exists:
        return SentinelRepairConfigState.MISSING

    if not status.valid_json:
        return SentinelRepairConfigState.INVALID_JSON

    if not status.schema_valid:
        return SentinelRepairConfigState.INVALID_SCHEMA

    return SentinelRepairConfigState.VALID


def _supported_drive_c(root: Path) -> Path | None:
    expected_parts = SENTINEL_GSE_RELATIVE_PATH.parts
    normalized = _normalize_path(root)

    if normalized.parts[-len(expected_parts) :] != expected_parts:
        return None

    drive_c = normalized.parents[len(expected_parts) - 1]

    if drive_c.name.casefold() != "drive_c":
        return None

    return drive_c


def _uses_unsupported_wine_user(root: Path) -> bool:
    expected_parts = SENTINEL_GSE_RELATIVE_PATH.parts
    expected_tail = expected_parts[2:]
    normalized = _normalize_path(root)
    parts = normalized.parts

    if len(parts) < len(expected_parts) + 1:
        return False

    if parts[-len(expected_tail) :] != expected_tail:
        return False

    user_index = len(parts) - len(expected_tail) - 1
    users_index = user_index - 1
    drive_c_index = users_index - 1

    return (
        drive_c_index >= 0
        and parts[users_index] == expected_parts[0]
        and parts[drive_c_index].casefold() == "drive_c"
        and parts[user_index] != expected_parts[1]
    )


def _configured_prefix_for_drive_c(
    status: SentinelConfigStatus,
    drive_c: Path,
) -> Path | None:
    normalized_drive_c = _normalize_path(drive_c)
    candidate_prefix = normalized_drive_c.parent

    for prefix in status.prefix_paths:
        normalized_prefix = _normalize_path(prefix)

        if normalized_prefix == candidate_prefix:
            return normalized_prefix

        if normalized_prefix == normalized_drive_c:
            continue

        if (
            normalized_prefix in normalized_drive_c.parents
            and normalized_prefix.is_dir()
            and normalized_drive_c.is_dir()
        ):
            return normalized_prefix

    return None


def _plan_location(
    status: SentinelConfigStatus,
    location_coverage: SentinelGseLocationCoverage,
) -> SentinelLocationRepairPlan:
    if location_coverage.covered:
        return SentinelLocationRepairPlan(
            kind=SentinelRepairKind.ALREADY_COVERED,
            location_coverage=location_coverage,
        )

    root = location_coverage.location.root
    drive_c = _supported_drive_c(root)

    if drive_c is None:
        kind = (
            SentinelRepairKind.UNSUPPORTED_WINE_USER
            if _uses_unsupported_wine_user(root)
            else SentinelRepairKind.UNSUPPORTED_CUSTOM_SAVE_ROOT
        )
        return SentinelLocationRepairPlan(
            kind=kind,
            location_coverage=location_coverage,
        )

    configured_prefix = _configured_prefix_for_drive_c(status, drive_c)

    if configured_prefix is not None:
        return SentinelLocationRepairPlan(
            kind=SentinelRepairKind.PREFIX_ALREADY_CONFIGURED,
            location_coverage=location_coverage,
            drive_c=drive_c,
            configured_prefix=configured_prefix,
        )

    return SentinelLocationRepairPlan(
        kind=SentinelRepairKind.ADD_PREFIX,
        location_coverage=location_coverage,
        drive_c=drive_c,
        candidate_prefix=drive_c.parent if status.configured else None,
    )


def plan_sentinel_gse_repair(
    coverage: SentinelGseCoverage,
) -> SentinelRepairPlan:
    if not coverage.effective_save_resolved:
        location_plans = (
            SentinelLocationRepairPlan(
                kind=SentinelRepairKind.UNRESOLVED,
                location_coverage=None,
            ),
        )
    else:
        location_plans = tuple(
            _plan_location(coverage.sentinel_status, location_coverage)
            for location_coverage in coverage.location_coverages
        )

    return SentinelRepairPlan(
        coverage=coverage,
        config_state=_config_state(coverage.sentinel_status),
        location_plans=location_plans,
    )
