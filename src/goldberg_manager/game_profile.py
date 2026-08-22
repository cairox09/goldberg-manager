from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from .core.game import Game
from .game_resolution import (
    GameAchievementResolution,
    GameGseResolution,
    GameSentinelIntegrationResolution,
    resolve_game_achievement_progress,
    resolve_game_gse_runtime,
    resolve_game_sentinel_integration,
)
from .gse_saves import GseSaveResolution
from .heroic import HeroicGameProvenance, resolve_game_heroic_provenance
from .prefix_consensus import (
    GamePrefixConsensus,
    resolve_game_prefix_consensus,
    validate_game_prefix_consensus_snapshots,
)
from .sentinel import (
    SentinelConfigStatus,
    SentinelDriveC,
    SentinelInstallation,
    detect_sentinel,
    discover_sentinel_drive_c_paths,
    read_sentinel_config,
)
from .sentinel_integration import SentinelGseCoverage
from .settings import SteamSettingsSnapshot, read_game_steam_settings
from .steam import SteamGameProvenance, resolve_game_steam_provenance


class PrefixProvenanceStatus(str, Enum):
    RESOLVED = "resolved"
    AMBIGUOUS = "ambiguous"
    UNKNOWN = "unknown"


class PrefixEvidence(str, Enum):
    GSE_EFFECTIVE_LOCATION = "gse_effective_location"


def _normalize_lexical_path(path: Path) -> Path:
    return Path(os.path.normpath(os.path.abspath(path.expanduser())))


def _validate_app_id_selection(
    app_id: int | None,
    app_id_confidence: int | None,
    app_id_source: str | None,
) -> None:
    if app_id is None:
        if app_id_confidence is not None:
            raise ValueError("Missing AppID cannot have confidence.")
        if app_id_source is not None:
            raise ValueError("Missing AppID cannot have a source.")
        return

    if isinstance(app_id, bool) or not isinstance(app_id, int) or app_id <= 0:
        raise ValueError("GameProfile AppID must be a positive integer.")
    if app_id_confidence is None:
        raise ValueError("Selected AppID requires confidence.")
    if not isinstance(app_id_source, str) or not app_id_source.strip():
        raise ValueError("Selected AppID requires a non-empty source.")


@dataclass(frozen=True, slots=True)
class GamePrefixProvenance:
    status: PrefixProvenanceStatus
    candidates: tuple[SentinelDriveC, ...]
    effective: SentinelDriveC | None = None
    evidence: PrefixEvidence | None = None
    evidence_path: Path | None = None

    def __post_init__(self) -> None:
        resolved = self.status is PrefixProvenanceStatus.RESOLVED
        effective_fields = (
            self.effective,
            self.evidence,
            self.evidence_path,
        )

        if resolved and any(value is None for value in effective_fields):
            raise ValueError("Resolved prefix provenance requires complete evidence.")
        if not resolved and any(value is not None for value in effective_fields):
            raise ValueError(
                "Unresolved prefix provenance cannot have an effective drive_c."
            )
        if self.effective is not None and self.effective not in self.candidates:
            raise ValueError("The effective drive_c must be one of the candidates.")

    @property
    def resolved(self) -> bool:
        return self.status is PrefixProvenanceStatus.RESOLVED

    @property
    def ambiguous(self) -> bool:
        return self.status is PrefixProvenanceStatus.AMBIGUOUS

    @property
    def unknown(self) -> bool:
        return self.status is PrefixProvenanceStatus.UNKNOWN

    @property
    def unresolved(self) -> bool:
        return not self.resolved

    @property
    def effective_sentinel_prefix(self) -> Path | None:
        return self.effective.prefix_path if self.effective is not None else None

    @property
    def effective_wine_prefix(self) -> Path | None:
        return self.effective.drive_c.parent if self.effective is not None else None

    @property
    def effective_drive_c(self) -> Path | None:
        return self.effective.drive_c if self.effective is not None else None


@dataclass(frozen=True, slots=True)
class GameProfileSentinelState:
    installation: SentinelInstallation
    integration: GameSentinelIntegrationResolution

    def __post_init__(self) -> None:
        installation_path = _normalize_lexical_path(self.installation.config_path)
        status_path = _normalize_lexical_path(
            self.integration.coverage.sentinel_status.path
        )

        if installation_path != status_path:
            raise ValueError(
                "Sentinel installation and config status must reference the same path."
            )

    @property
    def status(self) -> SentinelConfigStatus:
        return self.integration.coverage.sentinel_status

    @property
    def coverage(self) -> SentinelGseCoverage:
        return self.integration.coverage


@dataclass(frozen=True, slots=True)
class GameProfile:
    game: Game
    app_id: int | None
    app_id_confidence: int | None
    app_id_source: str | None
    settings: SteamSettingsSnapshot
    gse: GameGseResolution
    achievements: GameAchievementResolution
    sentinel: GameProfileSentinelState
    prefix_provenance: GamePrefixProvenance
    heroic: HeroicGameProvenance
    steam: SteamGameProvenance
    prefix_consensus: GamePrefixConsensus

    def __post_init__(self) -> None:
        _validate_app_id_selection(
            self.app_id,
            self.app_id_confidence,
            self.app_id_source,
        )

        if (
            self.app_id,
            self.app_id_confidence,
            self.app_id_source,
        ) != (
            self.gse.app_id,
            self.gse.app_id_confidence,
            self.gse.app_id_source,
        ):
            raise ValueError(
                "GameProfile AppID selection must match its GSE resolution."
            )
        if self.achievements.gse_resolution is not self.gse:
            raise ValueError("Achievements must reuse the profile GSE resolution.")
        if self.sentinel.integration.gse_resolution is not self.gse:
            raise ValueError("Sentinel must reuse the profile GSE resolution.")

        coverage = self.sentinel.coverage
        if coverage.app_id != self.app_id:
            raise ValueError("Sentinel coverage must use the profile AppID.")
        if coverage.save_resolution is not self.gse.save_resolution:
            raise ValueError("Sentinel coverage must reuse the profile GSE save state.")

        if self.gse.save_resolution is not None:
            location_app_ids = {
                location.app_id for location in self.gse.save_resolution.locations
            }
            if location_app_ids - {self.app_id}:
                raise ValueError("All GSE locations must use the profile AppID.")

        validate_game_prefix_consensus_snapshots(
            self.prefix_consensus,
            self.prefix_provenance,
            self.heroic,
        )

    @property
    def architecture(self) -> str:
        return self.game.architecture


def _is_lexically_within(path: Path, parent: Path) -> bool:
    normalized_path = _normalize_lexical_path(path)
    normalized_parent = _normalize_lexical_path(parent)

    try:
        normalized_path.relative_to(normalized_parent)
    except ValueError:
        return False
    return True


def resolve_game_prefix_provenance(
    candidates: tuple[SentinelDriveC, ...],
    save_resolution: GseSaveResolution | None,
) -> GamePrefixProvenance:
    effective_locations = (
        save_resolution.effective_locations if save_resolution is not None else ()
    )
    runtime_locations = (
        save_resolution.runtime_locations if save_resolution is not None else ()
    )

    if len(effective_locations) == 1 and effective_locations[0] in runtime_locations:
        evidence_path = effective_locations[0].root
        matches = tuple(
            candidate
            for candidate in candidates
            if _is_lexically_within(evidence_path, candidate.drive_c)
        )

        if len(matches) == 1:
            return GamePrefixProvenance(
                status=PrefixProvenanceStatus.RESOLVED,
                candidates=candidates,
                effective=matches[0],
                evidence=PrefixEvidence.GSE_EFFECTIVE_LOCATION,
                evidence_path=evidence_path,
            )

    status = (
        PrefixProvenanceStatus.AMBIGUOUS
        if len(candidates) > 1
        else PrefixProvenanceStatus.UNKNOWN
    )
    return GamePrefixProvenance(
        status=status,
        candidates=candidates,
    )


def resolve_game_profile(
    game: Game,
    *,
    sentinel_installation: SentinelInstallation | None = None,
    sentinel_status: SentinelConfigStatus | None = None,
    heroic_config_root: Path | None = None,
    steam_roots: tuple[Path, ...] | None = None,
) -> GameProfile:
    installation = (
        detect_sentinel() if sentinel_installation is None else sentinel_installation
    )
    status = (
        read_sentinel_config(installation.config_path)
        if sentinel_status is None
        else sentinel_status
    )
    settings = read_game_steam_settings(game)
    sentinel_drive_cs = discover_sentinel_drive_c_paths(status.prefix_paths)
    gse = resolve_game_gse_runtime(
        game,
        sentinel_status=status,
        settings=settings,
        sentinel_drive_cs=sentinel_drive_cs,
    )
    achievements = resolve_game_achievement_progress(
        game,
        sentinel_status=status,
        gse_resolution=gse,
        settings=settings,
    )
    sentinel_integration = resolve_game_sentinel_integration(
        game,
        sentinel_status=status,
        gse_resolution=gse,
    )
    prefix_provenance = resolve_game_prefix_provenance(
        sentinel_drive_cs,
        gse.save_resolution,
    )
    heroic = resolve_game_heroic_provenance(
        game,
        config_root=heroic_config_root,
    )
    steam = resolve_game_steam_provenance(game, steam_roots=steam_roots)
    prefix_consensus = resolve_game_prefix_consensus(prefix_provenance, heroic)

    return GameProfile(
        game=game,
        app_id=gse.app_id,
        app_id_confidence=gse.app_id_confidence,
        app_id_source=gse.app_id_source,
        settings=settings,
        gse=gse,
        achievements=achievements,
        sentinel=GameProfileSentinelState(
            installation=installation,
            integration=sentinel_integration,
        ),
        prefix_provenance=prefix_provenance,
        heroic=heroic,
        steam=steam,
        prefix_consensus=prefix_consensus,
    )
