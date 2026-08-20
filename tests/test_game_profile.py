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
from goldberg_manager.scanner import Game
from goldberg_manager.sentinel import (
    SentinelConfigStatus,
    SentinelDriveC,
    SentinelInstallation,
    read_sentinel_config,
)
from goldberg_manager.sentinel_integration import resolve_sentinel_gse_coverage
from goldberg_manager.settings import SteamSettingsSnapshot

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


def make_profile_with_selection(
    app_id: int | None,
    app_id_confidence: int | None,
    app_id_source: str | None,
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
        prefix_provenance=GamePrefixProvenance(
            status=PrefixProvenanceStatus.UNKNOWN,
            candidates=(),
        ),
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
                )

            after = {
                path.relative_to(root): path.read_bytes()
                for path in root.rglob("*")
                if path.is_file()
            }
            self.assertEqual(profile.app_id, APP_ID)
            self.assertEqual(after, before)


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
