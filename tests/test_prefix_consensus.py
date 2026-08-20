from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from goldberg_manager.game_profile import (
    GamePrefixProvenance,
    PrefixEvidence,
    PrefixProvenanceStatus,
)
from goldberg_manager.heroic import (
    HeroicGameConfig,
    HeroicGameId,
    HeroicGameMatch,
    HeroicGameProvenance,
    HeroicInstalledGame,
    HeroicMatchEvidence,
    HeroicPrefixLayout,
    HeroicPrefixState,
    HeroicProvenanceStatus,
)
from goldberg_manager.prefix_consensus import (
    GamePrefixConsensus,
    GamePrefixConsensusStatus,
    PrefixConsensusEvidence,
    PrefixEvidenceSource,
    resolve_game_prefix_consensus,
)
from goldberg_manager.sentinel import SentinelDriveC


def make_gse_provenance(wine_prefix: Path) -> GamePrefixProvenance:
    candidate = SentinelDriveC(
        prefix_path=wine_prefix.parent,
        drive_c=wine_prefix / "drive_c",
    )
    return GamePrefixProvenance(
        status=PrefixProvenanceStatus.RESOLVED,
        candidates=(candidate,),
        effective=candidate,
        evidence=PrefixEvidence.GSE_EFFECTIVE_LOCATION,
        evidence_path=candidate.drive_c / "users" / "steamuser" / "GSE Saves",
    )


def make_unresolved_gse_provenance(
    status: PrefixProvenanceStatus = PrefixProvenanceStatus.UNKNOWN,
) -> GamePrefixProvenance:
    candidates = (
        (
            SentinelDriveC(
                prefix_path=Path("/sentinel/first"),
                drive_c=Path("/prefix/first/drive_c"),
            ),
            SentinelDriveC(
                prefix_path=Path("/sentinel/second"),
                drive_c=Path("/prefix/second/drive_c"),
            ),
        )
        if status is PrefixProvenanceStatus.AMBIGUOUS
        else ()
    )
    return GamePrefixProvenance(status=status, candidates=candidates)


def make_heroic_provenance(
    layout: HeroicPrefixLayout,
    structural_wine_prefix: Path | None,
    *,
    drive_c: Path | None = None,
    configured_prefix: Path | None = None,
) -> HeroicGameProvenance:
    if configured_prefix is None:
        configured_prefix = (
            structural_wine_prefix.parent
            if layout is HeroicPrefixLayout.PFX_SUBDIRECTORY
            and structural_wine_prefix is not None
            else structural_wine_prefix
        )
    config = HeroicGameConfig(
        configured_prefix=configured_prefix,
        wine_version_name="proton-test",
        wine_version_type="proton",
        wine_binary=Path("/tools/proton"),
        target_exe=Path("/games/example/Game.exe"),
        explicit=True,
        source_path=Path("/heroic/GamesConfig/game-id.json"),
    )
    installed = HeroicInstalledGame(
        id=HeroicGameId(runner="sideload", app_name="game-id"),
        install_path=Path("/games/example"),
        executable=Path("/games/example/Game.exe"),
        platform="Windows",
        source_path=Path("/heroic/sideload_apps/library.json"),
    )
    prefix = HeroicPrefixState(
        configured_prefix=configured_prefix,
        structural_wine_prefix=structural_wine_prefix,
        drive_c=(
            drive_c
            if drive_c is not None
            else (
                structural_wine_prefix / "drive_c"
                if structural_wine_prefix is not None
                else None
            )
        ),
        layout=layout,
    )
    match = HeroicGameMatch(
        installed_game=installed,
        config=config,
        prefix=prefix,
        evidences=(HeroicMatchEvidence.EXACT_EXECUTABLE_PATH,),
    )
    return HeroicGameProvenance(
        config_root=Path("/heroic"),
        status=HeroicProvenanceStatus.RESOLVED,
        candidates=(match,),
        effective=match,
        strongest_evidence=HeroicMatchEvidence.EXACT_EXECUTABLE_PATH,
        errors=(),
    )


def make_unknown_heroic_provenance() -> HeroicGameProvenance:
    return HeroicGameProvenance(
        config_root=Path("/heroic"),
        status=HeroicProvenanceStatus.UNKNOWN,
        candidates=(),
        effective=None,
        strongest_evidence=None,
        errors=(),
    )


class PrefixConsensusResolutionTests(unittest.TestCase):
    def test_zero_evidence_is_unknown(self) -> None:
        consensus = resolve_game_prefix_consensus(
            make_unresolved_gse_provenance(),
            make_unknown_heroic_provenance(),
        )

        self.assertTrue(consensus.unknown)
        self.assertFalse(consensus.resolved)
        self.assertFalse(consensus.conflict)
        self.assertEqual(consensus.evidences, ())
        self.assertIsNone(consensus.effective_wine_prefix)
        self.assertIsNone(consensus.effective_drive_c)

    def test_gse_only_resolves_with_runtime_backed_evidence(self) -> None:
        gse = make_gse_provenance(Path("/prefix/Game/pfx"))

        consensus = resolve_game_prefix_consensus(
            gse,
            make_unknown_heroic_provenance(),
        )

        self.assertTrue(consensus.resolved)
        self.assertEqual(consensus.effective_wine_prefix, Path("/prefix/Game/pfx"))
        self.assertEqual(
            consensus.effective_drive_c,
            Path("/prefix/Game/pfx/drive_c"),
        )
        self.assertEqual(len(consensus.evidences), 1)
        evidence = consensus.evidences[0]
        self.assertIs(evidence.source, PrefixEvidenceSource.GSE_RUNTIME)
        self.assertIs(evidence.gse_provenance, gse)
        self.assertIsNone(evidence.heroic_match)
        self.assertIsNotNone(gse.evidence_path)

    def test_heroic_direct_only_resolves_with_auditable_evidence(self) -> None:
        heroic = make_heroic_provenance(
            HeroicPrefixLayout.DIRECT,
            Path("/prefix/Game"),
        )

        consensus = resolve_game_prefix_consensus(
            make_unresolved_gse_provenance(),
            heroic,
        )

        self.assertTrue(consensus.resolved)
        self.assertEqual(consensus.effective_wine_prefix, Path("/prefix/Game"))
        evidence = consensus.evidences[0]
        self.assertIs(evidence.source, PrefixEvidenceSource.HEROIC)
        self.assertIs(evidence.heroic_match, heroic.effective)
        assert evidence.heroic_match is not None
        self.assertEqual(
            evidence.heroic_match.installed_game.id,
            HeroicGameId(runner="sideload", app_name="game-id"),
        )
        self.assertEqual(
            evidence.heroic_match.prefix.layout,
            HeroicPrefixLayout.DIRECT,
        )
        assert evidence.heroic_match.config is not None
        self.assertEqual(
            evidence.heroic_match.config.source_path,
            Path("/heroic/GamesConfig/game-id.json"),
        )

    def test_heroic_pfx_subdirectory_only_resolves(self) -> None:
        heroic = make_heroic_provenance(
            HeroicPrefixLayout.PFX_SUBDIRECTORY,
            Path("/prefix/Game/pfx"),
            configured_prefix=Path("/prefix/Game"),
        )

        consensus = resolve_game_prefix_consensus(
            make_unresolved_gse_provenance(),
            heroic,
        )

        self.assertTrue(consensus.resolved)
        self.assertEqual(consensus.effective_wine_prefix, Path("/prefix/Game/pfx"))
        self.assertEqual(
            consensus.effective_drive_c,
            Path("/prefix/Game/pfx/drive_c"),
        )

    def test_non_structural_heroic_layouts_do_not_produce_evidence(self) -> None:
        for layout in (
            HeroicPrefixLayout.MISSING,
            HeroicPrefixLayout.UNRESOLVED,
            HeroicPrefixLayout.AMBIGUOUS,
        ):
            with self.subTest(layout=layout):
                heroic = make_heroic_provenance(
                    layout,
                    None,
                    configured_prefix=Path("/prefix/configured"),
                )

                consensus = resolve_game_prefix_consensus(
                    make_unresolved_gse_provenance(),
                    heroic,
                )

                self.assertTrue(consensus.unknown)
                self.assertEqual(consensus.evidences, ())

    def test_gse_resolves_when_heroic_prefix_is_missing(self) -> None:
        gse = make_gse_provenance(Path("/prefix/GSE/pfx"))
        heroic = make_heroic_provenance(
            HeroicPrefixLayout.MISSING,
            None,
            configured_prefix=Path("/prefix/Heroic-missing"),
        )

        consensus = resolve_game_prefix_consensus(gse, heroic)

        self.assertTrue(consensus.resolved)
        self.assertEqual(
            tuple(evidence.source for evidence in consensus.evidences),
            (PrefixEvidenceSource.GSE_RUNTIME,),
        )
        self.assertEqual(consensus.effective_wine_prefix, Path("/prefix/GSE/pfx"))

    def test_unknown_heroic_provenance_does_not_produce_evidence(self) -> None:
        consensus = resolve_game_prefix_consensus(
            make_unresolved_gse_provenance(),
            make_unknown_heroic_provenance(),
        )

        self.assertTrue(consensus.unknown)

    def test_ambiguous_gse_does_not_conflict_with_structural_heroic(self) -> None:
        heroic = make_heroic_provenance(
            HeroicPrefixLayout.PFX_SUBDIRECTORY,
            Path("/prefix/Game/pfx"),
        )

        consensus = resolve_game_prefix_consensus(
            make_unresolved_gse_provenance(PrefixProvenanceStatus.AMBIGUOUS),
            heroic,
        )

        self.assertTrue(consensus.resolved)
        self.assertEqual(
            tuple(evidence.source for evidence in consensus.evidences),
            (PrefixEvidenceSource.HEROIC,),
        )

    def test_lexically_equivalent_gse_and_heroic_evidence_agree(self) -> None:
        gse = make_gse_provenance(Path("/prefix/Game/pfx"))
        heroic = make_heroic_provenance(
            HeroicPrefixLayout.PFX_SUBDIRECTORY,
            Path("/prefix/Game/temporary/../pfx"),
            drive_c=Path("/prefix/Game/pfx/./drive_c"),
            configured_prefix=Path("/prefix/Game"),
        )

        consensus = resolve_game_prefix_consensus(gse, heroic)

        self.assertTrue(consensus.resolved)
        self.assertEqual(len(consensus.evidences), 2)
        self.assertEqual(consensus.effective_wine_prefix, Path("/prefix/Game/pfx"))
        self.assertEqual(
            consensus.effective_drive_c,
            Path("/prefix/Game/pfx/drive_c"),
        )
        self.assertEqual(
            tuple(evidence.source for evidence in consensus.evidences),
            (PrefixEvidenceSource.GSE_RUNTIME, PrefixEvidenceSource.HEROIC),
        )

    def test_different_structural_prefixes_conflict(self) -> None:
        gse = make_gse_provenance(Path("/prefix/GSE/pfx"))
        heroic = make_heroic_provenance(
            HeroicPrefixLayout.DIRECT,
            Path("/prefix/Heroic"),
        )

        consensus = resolve_game_prefix_consensus(gse, heroic)

        self.assertTrue(consensus.conflict)
        self.assertFalse(consensus.resolved)
        self.assertIsNone(consensus.effective_wine_prefix)
        self.assertIsNone(consensus.effective_drive_c)
        self.assertEqual(len(consensus.evidences), 2)

    def test_different_prefix_with_same_drive_c_is_rejected(self) -> None:
        gse = make_gse_provenance(Path("/prefix/GSE"))
        heroic = make_heroic_provenance(
            HeroicPrefixLayout.DIRECT,
            Path("/prefix/Heroic"),
            drive_c=Path("/prefix/GSE/drive_c"),
        )

        with self.assertRaisesRegex(ValueError, "must belong"):
            resolve_game_prefix_consensus(gse, heroic)

    def test_same_prefix_with_different_drive_c_is_rejected(self) -> None:
        wine_prefix = Path("/prefix/Game")
        gse = make_gse_provenance(wine_prefix)
        heroic = make_heroic_provenance(
            HeroicPrefixLayout.DIRECT,
            wine_prefix,
            drive_c=wine_prefix / "other" / "drive_c",
        )

        with self.assertRaisesRegex(ValueError, "must belong"):
            resolve_game_prefix_consensus(gse, heroic)

    def test_internally_invalid_gse_relationship_is_rejected(self) -> None:
        candidate = SentinelDriveC(
            prefix_path=Path("/sentinel/Game"),
            drive_c=Path("/prefix/Game/not-drive-c"),
        )
        gse = GamePrefixProvenance(
            status=PrefixProvenanceStatus.RESOLVED,
            candidates=(candidate,),
            effective=candidate,
            evidence=PrefixEvidence.GSE_EFFECTIVE_LOCATION,
            evidence_path=candidate.drive_c / "users" / "steamuser" / "GSE Saves",
        )

        with self.assertRaisesRegex(ValueError, "must belong"):
            resolve_game_prefix_consensus(gse, make_unknown_heroic_provenance())


class PrefixConsensusInvariantTests(unittest.TestCase):
    def setUp(self) -> None:
        self.gse = make_gse_provenance(Path("/prefix/Game/pfx"))
        self.heroic = make_heroic_provenance(
            HeroicPrefixLayout.PFX_SUBDIRECTORY,
            Path("/prefix/Game/pfx"),
        )
        resolved = resolve_game_prefix_consensus(self.gse, self.heroic)
        self.gse_evidence = resolved.evidences[0]
        self.heroic_evidence = resolved.evidences[1]

    def test_evidence_order_is_canonical(self) -> None:
        consensus = GamePrefixConsensus(
            status=GamePrefixConsensusStatus.RESOLVED,
            evidences=(self.heroic_evidence, self.gse_evidence),
            effective_wine_prefix=Path("/prefix/Game/pfx"),
            effective_drive_c=Path("/prefix/Game/pfx/drive_c"),
        )

        self.assertEqual(
            tuple(evidence.source for evidence in consensus.evidences),
            (PrefixEvidenceSource.GSE_RUNTIME, PrefixEvidenceSource.HEROIC),
        )

    def test_unknown_rejects_evidence(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unknown"):
            GamePrefixConsensus(
                status=GamePrefixConsensusStatus.UNKNOWN,
                evidences=(self.gse_evidence,),
            )

    def test_resolved_requires_complete_agreeing_evidence(self) -> None:
        with self.assertRaisesRegex(ValueError, "requires evidence"):
            GamePrefixConsensus(
                status=GamePrefixConsensusStatus.RESOLVED,
                evidences=(),
            )

        conflicting_heroic = resolve_game_prefix_consensus(
            make_unresolved_gse_provenance(),
            make_heroic_provenance(
                HeroicPrefixLayout.DIRECT,
                Path("/prefix/Other"),
            ),
        ).evidences[0]
        with self.assertRaisesRegex(ValueError, "agreeing"):
            GamePrefixConsensus(
                status=GamePrefixConsensusStatus.RESOLVED,
                evidences=(self.gse_evidence, conflicting_heroic),
                effective_wine_prefix=self.gse_evidence.wine_prefix,
                effective_drive_c=self.gse_evidence.drive_c,
            )

    def test_conflict_requires_divergent_evidence_without_effective_paths(
        self,
    ) -> None:
        with self.assertRaisesRegex(ValueError, "divergent"):
            GamePrefixConsensus(
                status=GamePrefixConsensusStatus.CONFLICT,
                evidences=(self.gse_evidence, self.heroic_evidence),
            )

        conflicting_heroic = resolve_game_prefix_consensus(
            make_unresolved_gse_provenance(),
            make_heroic_provenance(
                HeroicPrefixLayout.DIRECT,
                Path("/prefix/Other"),
            ),
        ).evidences[0]
        with self.assertRaisesRegex(ValueError, "cannot have effective"):
            GamePrefixConsensus(
                status=GamePrefixConsensusStatus.CONFLICT,
                evidences=(self.gse_evidence, conflicting_heroic),
                effective_wine_prefix=self.gse_evidence.wine_prefix,
                effective_drive_c=self.gse_evidence.drive_c,
            )

    def test_duplicate_evidence_source_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "repeat"):
            GamePrefixConsensus(
                status=GamePrefixConsensusStatus.RESOLVED,
                evidences=(self.gse_evidence, self.gse_evidence),
                effective_wine_prefix=self.gse_evidence.wine_prefix,
                effective_drive_c=self.gse_evidence.drive_c,
            )

    def test_evidence_must_match_upstream_snapshot(self) -> None:
        with self.assertRaisesRegex(ValueError, "upstream"):
            PrefixConsensusEvidence(
                source=PrefixEvidenceSource.GSE_RUNTIME,
                wine_prefix=Path("/prefix/Other"),
                drive_c=Path("/prefix/Other/drive_c"),
                gse_provenance=self.gse,
            )


class PrefixConsensusRealWorldShapeTests(unittest.TestCase):
    def test_sonic_like_heroic_direct_resolves_without_gse_evidence(self) -> None:
        heroic = make_heroic_provenance(
            HeroicPrefixLayout.DIRECT,
            Path("/prefix/Sonic"),
        )

        consensus = resolve_game_prefix_consensus(
            make_unresolved_gse_provenance(),
            heroic,
        )

        self.assertTrue(consensus.resolved)
        self.assertEqual(
            tuple(evidence.source for evidence in consensus.evidences),
            (PrefixEvidenceSource.HEROIC,),
        )

    def test_tlou_like_heroic_pfx_resolves_while_gse_is_ambiguous(self) -> None:
        heroic = make_heroic_provenance(
            HeroicPrefixLayout.PFX_SUBDIRECTORY,
            Path("/prefix/TLOU/pfx"),
        )

        consensus = resolve_game_prefix_consensus(
            make_unresolved_gse_provenance(PrefixProvenanceStatus.AMBIGUOUS),
            heroic,
        )

        self.assertTrue(consensus.resolved)
        self.assertEqual(consensus.effective_wine_prefix, Path("/prefix/TLOU/pfx"))

    def test_invincible_like_missing_heroic_prefix_remains_unknown(self) -> None:
        heroic = make_heroic_provenance(
            HeroicPrefixLayout.MISSING,
            None,
            configured_prefix=Path("/prefix/Invincible-missing"),
        )

        consensus = resolve_game_prefix_consensus(
            make_unresolved_gse_provenance(PrefixProvenanceStatus.AMBIGUOUS),
            heroic,
        )

        self.assertTrue(consensus.unknown)
        self.assertEqual(consensus.evidences, ())
        assert heroic.effective is not None
        self.assertEqual(
            heroic.effective.prefix.configured_prefix,
            Path("/prefix/Invincible-missing"),
        )

    def test_consensus_resolution_does_not_write_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            marker = root / "marker"
            marker.write_bytes(b"unchanged")
            gse = make_gse_provenance(root / "prefix" / "pfx")
            heroic = make_heroic_provenance(
                HeroicPrefixLayout.PFX_SUBDIRECTORY,
                root / "prefix" / "pfx",
            )
            before = {
                path.relative_to(root): path.read_bytes()
                for path in root.rglob("*")
                if path.is_file()
            }

            resolve_game_prefix_consensus(gse, heroic)

            after = {
                path.relative_to(root): path.read_bytes()
                for path in root.rglob("*")
                if path.is_file()
            }

        self.assertEqual(after, before)


if __name__ == "__main__":
    unittest.main()
