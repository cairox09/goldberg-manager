from __future__ import annotations

import os
import tempfile
import unittest
from dataclasses import FrozenInstanceError, fields, replace
from pathlib import Path
from unittest.mock import patch

from goldberg_manager.appid import AppIdCandidate
from goldberg_manager.cli import GameGseResolution as CliGameGseResolution
from goldberg_manager.game_profile import (
    GamePrefixProvenance,
    GameProfile,
    GameProfileSentinelState,
    PrefixEvidence,
    PrefixProvenanceStatus,
    resolve_game_prefix_provenance,
    resolve_game_profile,
)
from goldberg_manager.game_resolution import (
    GameAchievementResolution,
    GameGseResolution,
    GameSentinelIntegrationResolution,
)
from goldberg_manager.gse_saves import GseSaveLocation, GseSaveResolution
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
    resolve_game_prefix_consensus,
)
from goldberg_manager.scanner import Game
from goldberg_manager.sentinel import (
    SentinelConfigStatus,
    SentinelDriveC,
    SentinelInstallation,
    read_sentinel_config,
)
from goldberg_manager.sentinel_integration import resolve_sentinel_gse_coverage
from goldberg_manager.settings import SteamSettingsSnapshot
from goldberg_manager.steam import (
    SteamGameProvenance,
    SteamInstalledGames,
    SteamProvenanceStatus,
)

APP_ID = 212480


def make_game(root: Path, name: str = "Example Game") -> Game:
    binaries = root / "Binaries" / "Win64"
    return Game(
        name=name,
        root_directory=root,
        executable=binaries / "Game.exe",
        steam_api=binaries / "steam_api64.dll",
        steam_api_relative_path=Path("Binaries/Win64/steam_api64.dll"),
        architecture="64-bit",
        source_directory=root,
    )


def make_installation(config_path: Path) -> SentinelInstallation:
    return SentinelInstallation(
        executable=Path("/usr/bin/sentinel"),
        config_path=config_path,
        data_directory=Path("/data/sentinel"),
        state_directory=Path("/state/sentinel"),
        log_path=Path("/state/sentinel/logs/sentinel.log"),
    )


def make_status(
    config_path: Path = Path("/config/sentinel/config.json"),
    prefixes: tuple[Path, ...] = (),
) -> SentinelConfigStatus:
    return SentinelConfigStatus(
        path=config_path,
        exists=True,
        valid_json=True,
        schema_valid=True,
        prefix_paths=prefixes,
        emulators=(),
    )


def make_save_resolution(
    roots: tuple[Path, ...],
    *,
    app_id: int = APP_ID,
    source: str = "default",
) -> GseSaveResolution:
    return GseSaveResolution(
        source=source,
        raw_value=None,
        locations=tuple(
            GseSaveLocation(source=source, root=root, app_id=app_id) for root in roots
        ),
    )


def make_resolutions(
    game: Game,
    status: SentinelConfigStatus,
    *,
    app_id: int | None = APP_ID,
    save_resolution: GseSaveResolution | None = None,
) -> tuple[
    GameGseResolution,
    GameAchievementResolution,
    GameSentinelIntegrationResolution,
]:
    gse = GameGseResolution(
        app_id=app_id,
        app_id_confidence=100 if app_id is not None else None,
        app_id_source="steam_appid.txt" if app_id is not None else None,
        save_resolution=save_resolution,
    )
    achievements = GameAchievementResolution(
        gse_resolution=gse,
        metadata_path=game.steam_api.parent / "steam_settings" / "achievements.json",
        language="english",
        runtime_paths=(),
        reports=(),
        errors=(),
    )
    coverage = resolve_sentinel_gse_coverage(
        status,
        app_id,
        save_resolution,
    )
    integration = GameSentinelIntegrationResolution(
        gse_resolution=gse,
        coverage=coverage,
    )
    return gse, achievements, integration


def make_candidate(root: Path, name: str) -> SentinelDriveC:
    prefix = root / name
    return SentinelDriveC(
        prefix_path=prefix,
        drive_c=prefix / "pfx" / "drive_c",
    )


def make_heroic_provenance(
    config_root: Path = Path("/config/heroic"),
) -> HeroicGameProvenance:
    return HeroicGameProvenance(
        config_root=config_root,
        status=HeroicProvenanceStatus.UNKNOWN,
        candidates=(),
        effective=None,
        strongest_evidence=None,
        errors=(),
    )


def make_prefix_consensus() -> GamePrefixConsensus:
    return GamePrefixConsensus(
        status=GamePrefixConsensusStatus.UNKNOWN,
        evidences=(),
    )


def make_steam_provenance() -> SteamGameProvenance:
    return SteamGameProvenance(
        discovery=SteamInstalledGames(
            steam_roots=(),
            libraries=(),
            games=(),
            errors=(),
        ),
        status=SteamProvenanceStatus.UNKNOWN,
        candidates=(),
        effective=None,
        prefix=None,
        strongest_evidence=None,
    )


def make_resolved_prefix_provenance(wine_prefix: Path) -> GamePrefixProvenance:
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


def make_structural_heroic_provenance(
    layout: HeroicPrefixLayout,
    wine_prefix: Path | None,
) -> HeroicGameProvenance:
    configured_prefix = (
        wine_prefix.parent
        if layout is HeroicPrefixLayout.PFX_SUBDIRECTORY and wine_prefix is not None
        else wine_prefix
    )
    if layout is HeroicPrefixLayout.MISSING:
        configured_prefix = Path("/prefix/missing")
    config = HeroicGameConfig(
        configured_prefix=configured_prefix,
        wine_version_name="proton-test",
        wine_version_type="proton",
        wine_binary=Path("/tools/proton"),
        target_exe=Path("/games/Profile/Game.exe"),
        explicit=True,
        source_path=Path("/heroic/GamesConfig/game-id.json"),
    )
    installed = HeroicInstalledGame(
        id=HeroicGameId(runner="sideload", app_name="game-id"),
        install_path=Path("/games/Profile"),
        executable=Path("/games/Profile/Game.exe"),
        platform="Windows",
        source_path=Path("/heroic/sideload_apps/library.json"),
    )
    match = HeroicGameMatch(
        installed_game=installed,
        config=config,
        prefix=HeroicPrefixState(
            configured_prefix=configured_prefix,
            structural_wine_prefix=wine_prefix,
            drive_c=wine_prefix / "drive_c" if wine_prefix is not None else None,
            layout=layout,
        ),
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


def make_profile_with_selection(
    app_id: int | None,
    app_id_confidence: int | None,
    app_id_source: str | None,
    *,
    prefix_provenance: GamePrefixProvenance | None = None,
    heroic: HeroicGameProvenance | None = None,
    steam: SteamGameProvenance | None = None,
    prefix_consensus: GamePrefixConsensus | None = None,
) -> GameProfile:
    game = make_game(Path("/games/AppID Invariant"))
    status = make_status()
    gse = GameGseResolution(
        app_id=app_id,
        app_id_confidence=app_id_confidence,
        app_id_source=app_id_source,
        save_resolution=None,
    )
    achievements = GameAchievementResolution(
        gse_resolution=gse,
        metadata_path=game.steam_api.parent / "steam_settings" / "achievements.json",
        language="english",
        runtime_paths=(),
        reports=(),
        errors=(),
    )
    integration = GameSentinelIntegrationResolution(
        gse_resolution=gse,
        coverage=resolve_sentinel_gse_coverage(status, app_id, None),
    )
    if prefix_provenance is None:
        prefix_provenance = GamePrefixProvenance(
            status=PrefixProvenanceStatus.UNKNOWN,
            candidates=(),
        )
    if heroic is None:
        heroic = make_heroic_provenance()
    if steam is None:
        steam = make_steam_provenance()
    if prefix_consensus is None:
        prefix_consensus = resolve_game_prefix_consensus(prefix_provenance, heroic)

    return GameProfile(
        game=game,
        app_id=app_id,
        app_id_confidence=app_id_confidence,
        app_id_source=app_id_source,
        settings=SteamSettingsSnapshot(app_id=app_id),
        gse=gse,
        achievements=achievements,
        sentinel=GameProfileSentinelState(
            installation=make_installation(status.path),
            integration=integration,
        ),
        prefix_provenance=prefix_provenance,
        heroic=heroic,
        steam=steam,
        prefix_consensus=prefix_consensus,
    )


def make_sentinel_state(
    installation_path: Path,
    status_path: Path,
) -> GameProfileSentinelState:
    game = make_game(Path("/games/Sentinel Invariant"))
    status = make_status(status_path)
    _, _, integration = make_resolutions(game, status)
    return GameProfileSentinelState(
        installation=make_installation(installation_path),
        integration=integration,
    )


class GameProfileTests(unittest.TestCase):
    def test_profile_composes_existing_state_and_reuses_resolutions(self) -> None:
        game = make_game(Path("/games/Example"))
        installation = make_installation(Path("/config/sentinel/config.json"))
        status = make_status(installation.config_path)
        settings = SteamSettingsSnapshot(
            app_id=APP_ID,
            account_name="Player",
            account_steamid=76561198000000000,
            language="brazilian",
            ip_country="BR",
            local_save_path="./saves",
            has_steam_interfaces=True,
        )
        candidate = make_candidate(Path("/prefixes"), "Example")
        save_resolution = make_save_resolution((Path("/games/Example/saves"),))
        gse, achievements, integration = make_resolutions(
            game,
            status,
            save_resolution=save_resolution,
        )
        prefix_provenance = GamePrefixProvenance(
            status=PrefixProvenanceStatus.UNKNOWN,
            candidates=(candidate,),
        )
        heroic = make_heroic_provenance()
        steam = make_steam_provenance()
        prefix_consensus = make_prefix_consensus()

        with (
            patch(
                "goldberg_manager.game_profile.detect_sentinel",
                return_value=installation,
            ) as detector,
            patch(
                "goldberg_manager.game_profile.read_sentinel_config",
                return_value=status,
            ) as config_reader,
            patch(
                "goldberg_manager.game_profile.read_game_steam_settings",
                return_value=settings,
            ) as settings_reader,
            patch(
                "goldberg_manager.game_profile.discover_sentinel_drive_c_paths",
                return_value=(candidate,),
            ) as drive_discoverer,
            patch(
                "goldberg_manager.game_profile.resolve_game_gse_runtime",
                return_value=gse,
            ) as gse_resolver,
            patch(
                "goldberg_manager.game_profile.resolve_game_achievement_progress",
                return_value=achievements,
            ) as achievement_resolver,
            patch(
                "goldberg_manager.game_profile.resolve_game_sentinel_integration",
                return_value=integration,
            ) as sentinel_resolver,
            patch(
                "goldberg_manager.game_profile.resolve_game_prefix_provenance",
                return_value=prefix_provenance,
            ) as prefix_resolver,
            patch(
                "goldberg_manager.game_profile.resolve_game_heroic_provenance",
                return_value=heroic,
            ) as heroic_resolver,
            patch(
                "goldberg_manager.game_profile.resolve_game_steam_provenance",
                return_value=steam,
            ) as steam_resolver,
            patch(
                "goldberg_manager.game_profile.resolve_game_prefix_consensus",
                return_value=prefix_consensus,
            ) as consensus_resolver,
        ):
            profile = resolve_game_profile(game)

        self.assertIs(profile.game, game)
        self.assertEqual(profile.architecture, "64-bit")
        self.assertIs(profile.settings, settings)
        self.assertEqual(profile.settings.account_name, "Player")
        self.assertEqual(profile.settings.account_steamid, 76561198000000000)
        self.assertIs(profile.gse, gse)
        self.assertIs(profile.achievements, achievements)
        self.assertIs(profile.achievements.gse_resolution, profile.gse)
        self.assertIs(profile.sentinel.integration, integration)
        self.assertIs(profile.sentinel.integration.gse_resolution, profile.gse)
        self.assertIs(profile.sentinel.status, status)
        self.assertIs(profile.sentinel.coverage.save_resolution, save_resolution)
        self.assertIs(profile.prefix_provenance, prefix_provenance)
        self.assertIs(profile.heroic, heroic)
        self.assertIs(profile.steam, steam)
        self.assertIs(profile.prefix_consensus, prefix_consensus)
        self.assertEqual(profile.app_id, APP_ID)
        self.assertEqual(profile.app_id_confidence, 100)
        self.assertEqual(profile.app_id_source, "steam_appid.txt")

        detector.assert_called_once_with()
        config_reader.assert_called_once_with(installation.config_path)
        settings_reader.assert_called_once_with(game)
        drive_discoverer.assert_called_once_with(status.prefix_paths)
        gse_resolver.assert_called_once_with(
            game,
            sentinel_status=status,
            settings=settings,
            sentinel_drive_cs=(candidate,),
        )
        achievement_resolver.assert_called_once_with(
            game,
            sentinel_status=status,
            gse_resolution=gse,
            settings=settings,
        )
        sentinel_resolver.assert_called_once_with(
            game,
            sentinel_status=status,
            gse_resolution=gse,
        )
        prefix_resolver.assert_called_once_with(
            (candidate,),
            save_resolution,
        )
        heroic_resolver.assert_called_once_with(
            game,
            config_root=None,
        )
        steam_resolver.assert_called_once_with(game, steam_roots=None)
        consensus_resolver.assert_called_once_with(prefix_provenance, heroic)

    def test_profile_represents_missing_appid_honestly(self) -> None:
        game = make_game(Path("/games/Unknown"))
        installation = make_installation(Path("/config/sentinel/config.json"))
        status = make_status(installation.config_path)
        settings = SteamSettingsSnapshot()
        gse, achievements, integration = make_resolutions(
            game,
            status,
            app_id=None,
        )
        heroic = make_heroic_provenance()

        with (
            patch(
                "goldberg_manager.game_profile.read_game_steam_settings",
                return_value=settings,
            ),
            patch(
                "goldberg_manager.game_profile.discover_sentinel_drive_c_paths",
                return_value=(),
            ),
            patch(
                "goldberg_manager.game_profile.resolve_game_gse_runtime",
                return_value=gse,
            ),
            patch(
                "goldberg_manager.game_profile.resolve_game_achievement_progress",
                return_value=achievements,
            ),
            patch(
                "goldberg_manager.game_profile.resolve_game_sentinel_integration",
                return_value=integration,
            ),
            patch(
                "goldberg_manager.game_profile.resolve_game_heroic_provenance",
                return_value=heroic,
            ),
            patch(
                "goldberg_manager.game_profile.resolve_game_steam_provenance",
                return_value=make_steam_provenance(),
            ),
        ):
            profile = resolve_game_profile(
                game,
                sentinel_installation=installation,
                sentinel_status=status,
            )

        self.assertIsNone(profile.app_id)
        self.assertIsNone(profile.app_id_confidence)
        self.assertIsNone(profile.app_id_source)
        self.assertIsNone(profile.gse.save_resolution)
        self.assertIsNone(profile.sentinel.coverage.app_id)
        self.assertTrue(profile.prefix_provenance.unknown)
        self.assertTrue(profile.prefix_consensus.unknown)

    def test_profile_enforces_single_appid_across_components(self) -> None:
        game = make_game(Path("/games/Inconsistent"))
        status = make_status()
        save_resolution = make_save_resolution((Path("/saves"),))
        gse, achievements, integration = make_resolutions(
            game,
            status,
            save_resolution=save_resolution,
        )
        inconsistent_coverage = replace(integration.coverage, app_id=999999)
        inconsistent_integration = replace(
            integration,
            coverage=inconsistent_coverage,
        )

        with self.assertRaisesRegex(ValueError, "Sentinel coverage"):
            GameProfile(
                game=game,
                app_id=APP_ID,
                app_id_confidence=100,
                app_id_source="steam_appid.txt",
                settings=SteamSettingsSnapshot(app_id=APP_ID),
                gse=gse,
                achievements=achievements,
                sentinel=GameProfileSentinelState(
                    installation=make_installation(status.path),
                    integration=inconsistent_integration,
                ),
                prefix_provenance=GamePrefixProvenance(
                    status=PrefixProvenanceStatus.UNKNOWN,
                    candidates=(),
                ),
                heroic=make_heroic_provenance(),
                steam=make_steam_provenance(),
                prefix_consensus=make_prefix_consensus(),
            )

    def test_missing_appid_rejects_confidence(self) -> None:
        with self.assertRaisesRegex(ValueError, "cannot have confidence"):
            make_profile_with_selection(None, 100, None)

    def test_missing_appid_rejects_source(self) -> None:
        with self.assertRaisesRegex(ValueError, "cannot have a source"):
            make_profile_with_selection(None, None, "steam_appid.txt")

    def test_selected_appid_requires_confidence(self) -> None:
        with self.assertRaisesRegex(ValueError, "requires confidence"):
            make_profile_with_selection(APP_ID, None, "steam_appid.txt")

    def test_selected_appid_requires_non_empty_source(self) -> None:
        for source in (None, "", "   "):
            with (
                self.subTest(source=source),
                self.assertRaisesRegex(ValueError, "non-empty source"),
            ):
                make_profile_with_selection(APP_ID, 100, source)

    def test_appid_must_be_positive(self) -> None:
        for app_id in (0, -1):
            with (
                self.subTest(app_id=app_id),
                self.assertRaisesRegex(ValueError, "positive integer"),
            ):
                make_profile_with_selection(app_id, 100, "steam_appid.txt")

    def test_valid_appid_selection_is_accepted(self) -> None:
        profile = make_profile_with_selection(APP_ID, 100, "steam_appid.txt")

        self.assertEqual(profile.app_id, APP_ID)

    def test_complete_appid_absence_is_accepted(self) -> None:
        profile = make_profile_with_selection(None, None, None)

        self.assertIsNone(profile.app_id)

    def test_profile_is_frozen_and_has_no_repair_action_state(self) -> None:
        game = make_game(Path("/games/Example"))
        status = make_status()
        gse, achievements, integration = make_resolutions(game, status)
        profile = GameProfile(
            game=game,
            app_id=APP_ID,
            app_id_confidence=100,
            app_id_source="steam_appid.txt",
            settings=SteamSettingsSnapshot(app_id=APP_ID),
            gse=gse,
            achievements=achievements,
            sentinel=GameProfileSentinelState(
                installation=make_installation(status.path),
                integration=integration,
            ),
            prefix_provenance=GamePrefixProvenance(
                status=PrefixProvenanceStatus.UNKNOWN,
                candidates=(),
            ),
            heroic=make_heroic_provenance(),
            steam=make_steam_provenance(),
            prefix_consensus=make_prefix_consensus(),
        )

        with self.assertRaises(FrozenInstanceError):
            profile.app_id = 999999

        profile_fields = {field.name for field in fields(GameProfile)}
        self.assertNotIn("repair", profile_fields)
        self.assertNotIn("repair_plan", profile_fields)

    def test_resolution_types_remain_available_from_cli(self) -> None:
        self.assertIs(CliGameGseResolution, GameGseResolution)

    def test_profile_resolution_does_not_write_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            game = make_game(root / "game")
            game.steam_api.parent.mkdir(parents=True)
            game.executable.write_bytes(b"game")
            game.steam_api.write_bytes(b"steam api")
            steam_settings = game.steam_api.parent / "steam_settings"
            steam_settings.mkdir()
            (steam_settings / "steam_appid.txt").write_text(
                f"{APP_ID}\n",
                encoding="utf-8",
            )
            (steam_settings / "configs.user.ini").write_text(
                "[user::general]\n"
                "account_name=Player\n"
                "language=english\n"
                "\n"
                "[user::saves]\n"
                "local_save_path=./saves\n",
                encoding="utf-8",
            )
            config_path = root / "sentinel" / "config.json"
            config_path.parent.mkdir()
            config_path.write_text(
                '{"prefixes": [], "emulators": []}\n',
                encoding="utf-8",
            )
            status = read_sentinel_config(config_path)
            installation = make_installation(config_path)
            candidate = AppIdCandidate(
                app_id=APP_ID,
                name=game.name,
                score=100,
                source="steam_appid.txt",
            )
            before = {
                path.relative_to(root): path.read_bytes()
                for path in root.rglob("*")
                if path.is_file()
            }

            with patch(
                "goldberg_manager.game_resolution.resolve_local_appid",
                return_value=[candidate],
            ):
                profile = resolve_game_profile(
                    game,
                    sentinel_installation=installation,
                    sentinel_status=status,
                    heroic_config_root=root / "missing-heroic",
                    steam_roots=(root / "missing-steam",),
                )

            after = {
                path.relative_to(root): path.read_bytes()
                for path in root.rglob("*")
                if path.is_file()
            }
            self.assertEqual(profile.app_id, APP_ID)
            self.assertTrue(profile.heroic.unknown)
            self.assertEqual(after, before)


class GameProfilePrefixConsensusTests(unittest.TestCase):
    def test_accepts_consensus_from_exact_profile_snapshots(self) -> None:
        prefix_provenance = make_resolved_prefix_provenance(Path("/prefix/Profile/pfx"))
        heroic = make_structural_heroic_provenance(
            HeroicPrefixLayout.PFX_SUBDIRECTORY,
            Path("/prefix/Profile/pfx"),
        )
        consensus = resolve_game_prefix_consensus(prefix_provenance, heroic)

        profile = make_profile_with_selection(
            APP_ID,
            100,
            "steam_appid.txt",
            prefix_provenance=prefix_provenance,
            heroic=heroic,
            prefix_consensus=consensus,
        )

        self.assertIs(profile.prefix_provenance, prefix_provenance)
        self.assertIs(profile.heroic, heroic)
        self.assertIs(profile.prefix_consensus, consensus)

    def test_rejects_equivalent_gse_evidence_from_another_snapshot(self) -> None:
        prefix_provenance = make_resolved_prefix_provenance(Path("/prefix/Profile/pfx"))
        external_provenance = make_resolved_prefix_provenance(
            Path("/prefix/Profile/pfx")
        )
        heroic = make_heroic_provenance()
        consensus = resolve_game_prefix_consensus(external_provenance, heroic)
        self.assertEqual(prefix_provenance, external_provenance)
        self.assertIsNot(prefix_provenance, external_provenance)

        with self.assertRaisesRegex(ValueError, "reuse its prefix provenance"):
            make_profile_with_selection(
                APP_ID,
                100,
                "steam_appid.txt",
                prefix_provenance=prefix_provenance,
                heroic=heroic,
                prefix_consensus=consensus,
            )

    def test_rejects_equivalent_heroic_match_from_another_snapshot(self) -> None:
        prefix_provenance = GamePrefixProvenance(
            status=PrefixProvenanceStatus.UNKNOWN,
            candidates=(),
        )
        heroic = make_structural_heroic_provenance(
            HeroicPrefixLayout.DIRECT,
            Path("/prefix/Profile"),
        )
        external_heroic = make_structural_heroic_provenance(
            HeroicPrefixLayout.DIRECT,
            Path("/prefix/Profile"),
        )
        consensus = resolve_game_prefix_consensus(
            prefix_provenance,
            external_heroic,
        )
        self.assertEqual(heroic.effective, external_heroic.effective)
        self.assertIsNot(heroic.effective, external_heroic.effective)

        with self.assertRaisesRegex(ValueError, "reuse its effective match"):
            make_profile_with_selection(
                APP_ID,
                100,
                "steam_appid.txt",
                prefix_provenance=prefix_provenance,
                heroic=heroic,
                prefix_consensus=consensus,
            )

    def test_rejects_unknown_consensus_that_omits_resolved_gse(self) -> None:
        prefix_provenance = make_resolved_prefix_provenance(Path("/prefix/Profile/pfx"))

        with self.assertRaisesRegex(ValueError, "omit GSE_RUNTIME"):
            make_profile_with_selection(
                APP_ID,
                100,
                "steam_appid.txt",
                prefix_provenance=prefix_provenance,
                heroic=make_heroic_provenance(),
                prefix_consensus=make_prefix_consensus(),
            )

    def test_rejects_consensus_that_omits_structural_heroic(self) -> None:
        prefix_provenance = GamePrefixProvenance(
            status=PrefixProvenanceStatus.UNKNOWN,
            candidates=(),
        )

        for layout, wine_prefix in (
            (HeroicPrefixLayout.DIRECT, Path("/prefix/Direct")),
            (HeroicPrefixLayout.PFX_SUBDIRECTORY, Path("/prefix/Pfx/pfx")),
        ):
            with (
                self.subTest(layout=layout),
                self.assertRaisesRegex(ValueError, "omit Heroic"),
            ):
                make_profile_with_selection(
                    APP_ID,
                    100,
                    "steam_appid.txt",
                    prefix_provenance=prefix_provenance,
                    heroic=make_structural_heroic_provenance(
                        layout,
                        wine_prefix,
                    ),
                    prefix_consensus=make_prefix_consensus(),
                )

    def test_rejects_evidence_invented_from_external_snapshots(self) -> None:
        prefix_provenance = GamePrefixProvenance(
            status=PrefixProvenanceStatus.UNKNOWN,
            candidates=(),
        )
        heroic = make_heroic_provenance()
        invented_consensuses = (
            (
                "GSE_RUNTIME",
                resolve_game_prefix_consensus(
                    make_resolved_prefix_provenance(Path("/prefix/External/pfx")),
                    heroic,
                ),
            ),
            (
                "Heroic",
                resolve_game_prefix_consensus(
                    prefix_provenance,
                    make_structural_heroic_provenance(
                        HeroicPrefixLayout.DIRECT,
                        Path("/prefix/External"),
                    ),
                ),
            ),
        )

        for source, consensus in invented_consensuses:
            with (
                self.subTest(source=source),
                self.assertRaisesRegex(ValueError, f"invent {source}"),
            ):
                make_profile_with_selection(
                    APP_ID,
                    100,
                    "steam_appid.txt",
                    prefix_provenance=prefix_provenance,
                    heroic=heroic,
                    prefix_consensus=consensus,
                )

    def test_missing_heroic_prefix_accepts_consensus_without_heroic_evidence(
        self,
    ) -> None:
        prefix_provenance = GamePrefixProvenance(
            status=PrefixProvenanceStatus.UNKNOWN,
            candidates=(),
        )
        heroic = make_structural_heroic_provenance(
            HeroicPrefixLayout.MISSING,
            None,
        )
        consensus = resolve_game_prefix_consensus(prefix_provenance, heroic)

        profile = make_profile_with_selection(
            APP_ID,
            100,
            "steam_appid.txt",
            prefix_provenance=prefix_provenance,
            heroic=heroic,
            prefix_consensus=consensus,
        )

        self.assertTrue(profile.prefix_consensus.unknown)
        self.assertEqual(profile.prefix_consensus.evidences, ())


class GameProfileSentinelStateTests(unittest.TestCase):
    def test_equal_config_paths_are_accepted(self) -> None:
        path = Path("/config/sentinel/config.json")

        state = make_sentinel_state(path, path)

        self.assertEqual(state.installation.config_path, state.status.path)

    def test_lexically_equivalent_config_paths_are_accepted(self) -> None:
        installation_path = Path("/config/sentinel/./nested/../config.json")
        status_path = Path("/config/sentinel/config.json")

        state = make_sentinel_state(installation_path, status_path)

        self.assertIsNotNone(state)

    def test_different_config_paths_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "same path"):
            make_sentinel_state(
                Path("/config/sentinel-a/config.json"),
                Path("/config/sentinel-b/config.json"),
            )


class GamePrefixProvenanceTests(unittest.TestCase):
    def test_zero_candidates_is_unknown(self) -> None:
        provenance = resolve_game_prefix_provenance((), None)

        self.assertTrue(provenance.unknown)
        self.assertTrue(provenance.unresolved)
        self.assertFalse(provenance.ambiguous)
        self.assertEqual(provenance.candidates, ())

    def test_multiple_candidates_without_evidence_is_ambiguous(self) -> None:
        root = Path("/prefixes")
        candidates = (
            make_candidate(root, "First"),
            make_candidate(root, "Second"),
        )

        provenance = resolve_game_prefix_provenance(candidates, None)

        self.assertTrue(provenance.ambiguous)
        self.assertTrue(provenance.unresolved)
        self.assertFalse(provenance.unknown)
        self.assertIsNone(provenance.effective_sentinel_prefix)
        self.assertIsNone(provenance.effective_wine_prefix)
        self.assertIsNone(provenance.evidence)

    def test_single_candidate_without_runtime_evidence_is_not_effective(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            candidate = make_candidate(Path(temp_directory), "Only")
            root = (
                candidate.drive_c
                / "users"
                / "steamuser"
                / "AppData"
                / "Roaming"
                / "GSE Saves"
            )
            resolution = make_save_resolution((root,))

            provenance = resolve_game_prefix_provenance(
                (candidate,),
                resolution,
            )

        self.assertTrue(resolution.resolved)
        self.assertTrue(provenance.unknown)
        self.assertIsNone(provenance.effective)

    def test_resolved_provenance_distinguishes_prefix_concepts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            sentinel_prefix = root / "sentinel" / "search-root"
            wine_prefix = sentinel_prefix / "Game" / "pfx"
            candidate = SentinelDriveC(
                prefix_path=sentinel_prefix,
                drive_c=wine_prefix / "drive_c",
            )
            gse_root = (
                candidate.drive_c
                / "users"
                / "custom-user"
                / "AppData"
                / "Roaming"
                / "GSE Saves"
            )
            resolution = make_save_resolution((gse_root,))
            resolution.locations[0].app_directory.mkdir(parents=True)

            provenance = resolve_game_prefix_provenance(
                (candidate,),
                resolution,
            )

        self.assertTrue(provenance.resolved)
        self.assertIs(provenance.effective, candidate)
        self.assertEqual(provenance.effective_sentinel_prefix, sentinel_prefix)
        self.assertEqual(provenance.effective_wine_prefix, wine_prefix)
        self.assertEqual(provenance.effective_drive_c, candidate.drive_c)
        self.assertNotEqual(
            provenance.effective_sentinel_prefix,
            provenance.effective_wine_prefix,
        )
        self.assertNotEqual(
            provenance.effective_wine_prefix,
            provenance.effective_drive_c,
        )
        self.assertFalse(hasattr(provenance, "effective_prefix"))
        self.assertIs(
            provenance.evidence,
            PrefixEvidence.GSE_EFFECTIVE_LOCATION,
        )
        self.assertEqual(provenance.evidence_path, gse_root)

    def test_parent_segments_escaping_drive_c_cannot_resolve_prefix(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            candidate = make_candidate(root, "Game")
            escaping_root = candidate.drive_c / ".." / "outside" / "GSE Saves"
            resolution = make_save_resolution((escaping_root,))
            resolution.locations[0].app_directory.mkdir(parents=True)

            provenance = resolve_game_prefix_provenance(
                (candidate,),
                resolution,
            )

        self.assertTrue(provenance.unknown)
        self.assertIsNone(provenance.effective)
        self.assertIsNone(provenance.evidence)

    def test_parent_segments_remaining_inside_drive_c_can_resolve(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            candidate = make_candidate(root, "Game")
            equivalent_root = (
                candidate.drive_c
                / "."
                / "users"
                / "steamuser"
                / ".."
                / "steamuser"
                / "AppData"
                / "Roaming"
                / "GSE Saves"
            )
            resolution = make_save_resolution((equivalent_root,))
            resolution.locations[0].app_directory.mkdir(parents=True)

            provenance = resolve_game_prefix_provenance(
                (candidate,),
                resolution,
            )

        self.assertTrue(provenance.resolved)
        self.assertIs(provenance.effective, candidate)

    def test_relative_and_absolute_paths_are_compared_lexically(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            candidate = make_candidate(Path(temp_directory), "Game")
            relative_drive_c = Path(os.path.relpath(candidate.drive_c, Path.cwd()))
            relative_root = (
                relative_drive_c
                / "users"
                / "steamuser"
                / "AppData"
                / "Roaming"
                / "GSE Saves"
            )
            resolution = make_save_resolution((relative_root,))
            resolution.locations[0].app_directory.mkdir(parents=True)

            provenance = resolve_game_prefix_provenance(
                (candidate,),
                resolution,
            )

        self.assertTrue(provenance.resolved)
        self.assertIs(provenance.effective, candidate)

    def test_effective_gse_root_outside_drive_c_remains_unknown(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            candidate = make_candidate(root, "Game")
            resolution = make_save_resolution((root / "portable-saves",))
            resolution.locations[0].app_directory.mkdir(parents=True)

            provenance = resolve_game_prefix_provenance(
                (candidate,),
                resolution,
            )

        self.assertTrue(resolution.resolved)
        self.assertTrue(provenance.unknown)
        self.assertIsNone(provenance.effective_sentinel_prefix)
        self.assertIsNone(provenance.effective_wine_prefix)

    def test_sonic_like_local_save_does_not_invent_prefix(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            candidate = make_candidate(root, "Sonic All Stars")
            local_save = root / "game" / "Binaries" / "Win64" / "saves"
            resolution = make_save_resolution(
                (local_save,),
                source="local_save_path",
            )
            resolution.locations[0].app_directory.mkdir(parents=True)

            provenance = resolve_game_prefix_provenance(
                (candidate,),
                resolution,
            )

        self.assertTrue(provenance.unknown)
        self.assertIsNone(provenance.effective)

    def test_tlou_like_possible_roots_do_not_choose_by_name(self) -> None:
        root = Path("/prefixes")
        candidates = (
            make_candidate(root, "The Last of Us"),
            make_candidate(root, "The Last of Us Part I"),
        )
        resolution = make_save_resolution(
            tuple(
                candidate.drive_c
                / "users"
                / "steamuser"
                / "AppData"
                / "Roaming"
                / "GSE Saves"
                for candidate in candidates
            )
        )

        provenance = resolve_game_prefix_provenance(candidates, resolution)

        self.assertTrue(resolution.ambiguous)
        self.assertTrue(provenance.ambiguous)
        self.assertIsNone(provenance.effective)

    def test_invincible_like_multiple_runtimes_remain_ambiguous(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            candidates = (
                make_candidate(root, "First"),
                make_candidate(root, "Second"),
            )
            resolution = make_save_resolution(
                tuple(
                    candidate.drive_c
                    / "users"
                    / "steamuser"
                    / "AppData"
                    / "Roaming"
                    / "GSE Saves"
                    for candidate in candidates
                )
            )
            for location in resolution.locations:
                location.app_directory.mkdir(parents=True)

            provenance = resolve_game_prefix_provenance(candidates, resolution)

        self.assertTrue(resolution.ambiguous)
        self.assertTrue(provenance.ambiguous)
        self.assertIsNone(provenance.effective_drive_c)

    def test_one_runtime_among_candidates_resolves_structurally(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            candidates = (
                make_candidate(root, "First"),
                make_candidate(root, "Second"),
            )
            resolution = make_save_resolution(
                tuple(
                    candidate.drive_c
                    / "users"
                    / "steamuser"
                    / "AppData"
                    / "Roaming"
                    / "GSE Saves"
                    for candidate in candidates
                )
            )
            selected = resolution.locations[1]
            selected.app_directory.mkdir(parents=True)

            provenance = resolve_game_prefix_provenance(candidates, resolution)
            resolution_resolved = resolution.resolved

        self.assertTrue(resolution_resolved)
        self.assertTrue(provenance.resolved)
        self.assertIs(provenance.effective, candidates[1])
        self.assertEqual(provenance.evidence_path, selected.root)

    def test_overlapping_drive_c_candidates_do_not_choose_arbitrarily(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            outer = SentinelDriveC(
                prefix_path=root / "outer-prefix",
                drive_c=root / "outer-prefix" / "drive_c",
            )
            inner = SentinelDriveC(
                prefix_path=root / "inner-prefix",
                drive_c=outer.drive_c / "nested" / "drive_c",
            )
            gse_root = (
                inner.drive_c
                / "users"
                / "steamuser"
                / "AppData"
                / "Roaming"
                / "GSE Saves"
            )
            resolution = make_save_resolution((gse_root,))
            resolution.locations[0].app_directory.mkdir(parents=True)

            provenance = resolve_game_prefix_provenance(
                (outer, inner),
                resolution,
            )

        self.assertTrue(provenance.ambiguous)
        self.assertIsNone(provenance.effective)
        self.assertIsNone(provenance.evidence)


if __name__ == "__main__":
    unittest.main()
