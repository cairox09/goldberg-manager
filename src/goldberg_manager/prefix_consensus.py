from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

from .heroic import (
    HeroicGameMatch,
    HeroicGameProvenance,
    HeroicPrefixLayout,
)

if TYPE_CHECKING:
    from .game_profile import GamePrefixProvenance


class PrefixEvidenceSource(str, Enum):
    GSE_RUNTIME = "gse_runtime"
    HEROIC = "heroic"


_PREFIX_EVIDENCE_SOURCE_ORDER = {
    PrefixEvidenceSource.GSE_RUNTIME: 0,
    PrefixEvidenceSource.HEROIC: 1,
}


class GamePrefixConsensusStatus(str, Enum):
    RESOLVED = "resolved"
    CONFLICT = "conflict"
    UNKNOWN = "unknown"


def _normalize_lexical_path(path: Path) -> Path:
    return Path(os.path.normpath(os.path.abspath(path.expanduser())))


def _validate_structural_paths(wine_prefix: Path, drive_c: Path) -> None:
    if drive_c != wine_prefix / "drive_c":
        raise ValueError("Prefix evidence drive_c must belong to its Wine prefix.")


@dataclass(frozen=True, slots=True)
class PrefixConsensusEvidence:
    source: PrefixEvidenceSource
    wine_prefix: Path
    drive_c: Path
    gse_provenance: GamePrefixProvenance | None = None
    heroic_match: HeroicGameMatch | None = None

    def __post_init__(self) -> None:
        wine_prefix = _normalize_lexical_path(self.wine_prefix)
        drive_c = _normalize_lexical_path(self.drive_c)
        _validate_structural_paths(wine_prefix, drive_c)
        object.__setattr__(self, "wine_prefix", wine_prefix)
        object.__setattr__(self, "drive_c", drive_c)

        if self.source is PrefixEvidenceSource.GSE_RUNTIME:
            if self.gse_provenance is None or self.heroic_match is not None:
                raise ValueError("GSE prefix evidence requires GSE provenance only.")
            if not self.gse_provenance.resolved:
                raise ValueError("GSE prefix evidence requires resolved provenance.")
            expected_wine_prefix = self.gse_provenance.effective_wine_prefix
            expected_drive_c = self.gse_provenance.effective_drive_c
        elif self.source is PrefixEvidenceSource.HEROIC:
            if self.heroic_match is None or self.gse_provenance is not None:
                raise ValueError("Heroic prefix evidence requires a Heroic match only.")
            if self.heroic_match.prefix.layout not in {
                HeroicPrefixLayout.DIRECT,
                HeroicPrefixLayout.PFX_SUBDIRECTORY,
            }:
                raise ValueError("Heroic prefix evidence requires a structural layout.")
            expected_wine_prefix = self.heroic_match.prefix.structural_wine_prefix
            expected_drive_c = self.heroic_match.prefix.drive_c
        else:
            raise ValueError("Unsupported prefix evidence source.")

        if expected_wine_prefix is None or expected_drive_c is None:
            raise ValueError("Prefix evidence requires complete upstream paths.")
        if wine_prefix != _normalize_lexical_path(
            expected_wine_prefix
        ) or drive_c != _normalize_lexical_path(expected_drive_c):
            raise ValueError("Prefix evidence must match its upstream provenance.")


@dataclass(frozen=True, slots=True)
class GamePrefixConsensus:
    status: GamePrefixConsensusStatus
    evidences: tuple[PrefixConsensusEvidence, ...]
    effective_wine_prefix: Path | None = None
    effective_drive_c: Path | None = None

    def __post_init__(self) -> None:
        evidences = tuple(
            sorted(
                self.evidences,
                key=lambda item: _PREFIX_EVIDENCE_SOURCE_ORDER[item.source],
            )
        )
        if len({evidence.source for evidence in evidences}) != len(evidences):
            raise ValueError("Prefix consensus cannot repeat an evidence source.")
        object.__setattr__(self, "evidences", evidences)

        wine_prefix = self.effective_wine_prefix
        drive_c = self.effective_drive_c
        if (wine_prefix is None) != (drive_c is None):
            raise ValueError("Effective prefix consensus paths must be complete.")
        if wine_prefix is not None and drive_c is not None:
            wine_prefix = _normalize_lexical_path(wine_prefix)
            drive_c = _normalize_lexical_path(drive_c)
            _validate_structural_paths(wine_prefix, drive_c)
            object.__setattr__(self, "effective_wine_prefix", wine_prefix)
            object.__setattr__(self, "effective_drive_c", drive_c)

        evidence_paths = {
            (evidence.wine_prefix, evidence.drive_c) for evidence in evidences
        }

        if self.status is GamePrefixConsensusStatus.RESOLVED:
            if wine_prefix is None or drive_c is None or not evidences:
                raise ValueError(
                    "Resolved prefix consensus requires evidence and paths."
                )
            if evidence_paths != {(wine_prefix, drive_c)}:
                raise ValueError(
                    "Resolved prefix consensus requires agreeing evidence."
                )
        elif self.status is GamePrefixConsensusStatus.CONFLICT:
            if wine_prefix is not None or drive_c is not None:
                raise ValueError(
                    "Conflicting prefix consensus cannot have effective paths."
                )
            if len(evidences) < 2 or len(evidence_paths) < 2:
                raise ValueError(
                    "Conflicting prefix consensus requires divergent evidence."
                )
        elif self.status is GamePrefixConsensusStatus.UNKNOWN:
            if wine_prefix is not None or drive_c is not None or evidences:
                raise ValueError(
                    "Unknown prefix consensus cannot have evidence or paths."
                )
        else:
            raise ValueError("Unsupported prefix consensus status.")

    @property
    def resolved(self) -> bool:
        return self.status is GamePrefixConsensusStatus.RESOLVED

    @property
    def conflict(self) -> bool:
        return self.status is GamePrefixConsensusStatus.CONFLICT

    @property
    def unknown(self) -> bool:
        return self.status is GamePrefixConsensusStatus.UNKNOWN


def _gse_structural_paths(
    provenance: GamePrefixProvenance,
) -> tuple[Path, Path] | None:
    wine_prefix = provenance.effective_wine_prefix
    drive_c = provenance.effective_drive_c
    if provenance.resolved and wine_prefix is not None and drive_c is not None:
        return wine_prefix, drive_c
    return None


def _heroic_structural_match(
    provenance: HeroicGameProvenance,
) -> HeroicGameMatch | None:
    if not provenance.resolved or provenance.effective is None:
        return None

    match = provenance.effective
    if (
        match.prefix.layout
        in {HeroicPrefixLayout.DIRECT, HeroicPrefixLayout.PFX_SUBDIRECTORY}
        and match.prefix.structural_wine_prefix is not None
        and match.prefix.drive_c is not None
    ):
        return match
    return None


def validate_game_prefix_consensus_snapshots(
    consensus: GamePrefixConsensus,
    gse_provenance: GamePrefixProvenance,
    heroic_provenance: HeroicGameProvenance,
) -> None:
    evidences = {evidence.source: evidence for evidence in consensus.evidences}
    gse_evidence = evidences.get(PrefixEvidenceSource.GSE_RUNTIME)
    gse_paths = _gse_structural_paths(gse_provenance)

    if gse_paths is None:
        if gse_evidence is not None:
            raise ValueError(
                "GameProfile consensus cannot invent GSE_RUNTIME evidence."
            )
    elif gse_evidence is None:
        raise ValueError("GameProfile consensus cannot omit GSE_RUNTIME evidence.")
    elif gse_evidence.gse_provenance is not gse_provenance:
        raise ValueError(
            "GameProfile consensus GSE evidence must reuse its prefix provenance."
        )

    heroic_evidence = evidences.get(PrefixEvidenceSource.HEROIC)
    heroic_match = _heroic_structural_match(heroic_provenance)
    if heroic_match is None:
        if heroic_evidence is not None:
            raise ValueError("GameProfile consensus cannot invent Heroic evidence.")
    elif heroic_evidence is None:
        raise ValueError("GameProfile consensus cannot omit Heroic evidence.")
    elif heroic_evidence.heroic_match is not heroic_match:
        raise ValueError(
            "GameProfile consensus Heroic evidence must reuse its effective match."
        )


def resolve_game_prefix_consensus(
    gse_provenance: GamePrefixProvenance,
    heroic_provenance: HeroicGameProvenance,
) -> GamePrefixConsensus:
    evidences: list[PrefixConsensusEvidence] = []

    gse_paths = _gse_structural_paths(gse_provenance)
    if gse_paths is not None:
        wine_prefix, drive_c = gse_paths
        evidences.append(
            PrefixConsensusEvidence(
                source=PrefixEvidenceSource.GSE_RUNTIME,
                wine_prefix=wine_prefix,
                drive_c=drive_c,
                gse_provenance=gse_provenance,
            )
        )

    heroic_match = _heroic_structural_match(heroic_provenance)
    if heroic_match is not None:
        wine_prefix = heroic_match.prefix.structural_wine_prefix
        drive_c = heroic_match.prefix.drive_c
        assert wine_prefix is not None
        assert drive_c is not None
        evidences.append(
            PrefixConsensusEvidence(
                source=PrefixEvidenceSource.HEROIC,
                wine_prefix=wine_prefix,
                drive_c=drive_c,
                heroic_match=heroic_match,
            )
        )

    if not evidences:
        return GamePrefixConsensus(
            status=GamePrefixConsensusStatus.UNKNOWN,
            evidences=(),
        )

    evidence_paths = {
        (evidence.wine_prefix, evidence.drive_c) for evidence in evidences
    }
    if len(evidence_paths) > 1:
        return GamePrefixConsensus(
            status=GamePrefixConsensusStatus.CONFLICT,
            evidences=tuple(evidences),
        )

    wine_prefix, drive_c = next(iter(evidence_paths))
    return GamePrefixConsensus(
        status=GamePrefixConsensusStatus.RESOLVED,
        evidences=tuple(evidences),
        effective_wine_prefix=wine_prefix,
        effective_drive_c=drive_c,
    )
