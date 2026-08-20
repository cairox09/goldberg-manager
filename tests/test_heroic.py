from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from goldberg_manager.heroic import (
    HeroicGameConfig,
    HeroicGameId,
    HeroicInstalledGame,
    HeroicInstalledGames,
    HeroicMatchEvidence,
    HeroicPrefixLayout,
    discover_heroic_installed_games,
    get_heroic_config_root,
    read_heroic_game_config,
    resolve_game_heroic_provenance,
    resolve_heroic_prefix_state,
)
from goldberg_manager.scanner import Game


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def make_game(
    root: Path,
    *,
    name: str = "Example Game",
    executable: Path | None = None,
    steam_api: Path | None = None,
) -> Game:
    return Game(
        name=name,
        root_directory=root,
        executable=executable or root / "Game.exe",
        steam_api=steam_api or root / "steam_api64.dll",
        steam_api_relative_path=Path("steam_api64.dll"),
        architecture="64-bit",
        source_directory=root.parent,
    )


def make_installed_game(
    install_path: Path,
    *,
    runner: str = "sideload",
    app_name: str = "game-id",
    executable: Path | None = None,
    source_path: Path | None = None,
) -> HeroicInstalledGame:
    return HeroicInstalledGame(
        id=HeroicGameId(runner=runner, app_name=app_name),
        install_path=install_path,
        executable=executable,
        platform="Windows",
        source_path=(
            source_path
            if source_path is not None
            else Path("/heroic") / runner / "installed.json"
        ),
    )


def make_discovery(
    config_root: Path,
    games: tuple[HeroicInstalledGame, ...],
) -> HeroicInstalledGames:
    return HeroicInstalledGames(
        config_root=config_root,
        config_exists=True,
        games=games,
        errors=(),
    )


def make_config(configured_prefix: Path | None) -> HeroicGameConfig:
    return HeroicGameConfig(
        configured_prefix=configured_prefix,
        wine_version_name="proton-test",
        wine_version_type="proton",
        wine_binary=Path("/tools/proton"),
        target_exe=None,
        explicit=True,
        source_path=Path("/heroic/GamesConfig/game-id.json"),
    )


def write_sideload_registry(
    config_root: Path,
    entries: list[object],
) -> Path:
    path = config_root / "sideload_apps" / "library.json"
    write_json(path, {"games": entries})
    return path


def sideload_entry(
    install_path: Path,
    executable: Path,
    *,
    app_name: str = "game-id",
    installed: bool = True,
    title: str = "Display title",
) -> dict[str, object]:
    return {
        "runner": "sideload",
        "app_name": app_name,
        "title": title,
        "folder_name": str(install_path),
        "is_installed": installed,
        "install": {
            "executable": str(executable),
            "platform": "Windows",
            "is_dlc": False,
        },
    }


def write_game_config(
    config_root: Path,
    app_name: str,
    prefix: Path | str | None,
    *,
    internal_app_name: str | None = None,
    extra_values: dict[str, object] | None = None,
) -> Path:
    path = config_root / "GamesConfig" / f"{app_name}.json"
    values: dict[str, object] = {
        "winePrefix": str(prefix) if prefix is not None else "",
        "wineVersion": {
            "name": "proton-test",
            "type": "proton",
            "bin": "/tools/proton",
        },
        "targetExe": "bin/Target.exe",
    }
    if extra_values is not None:
        values.update(extra_values)
    write_json(
        path,
        {
            internal_app_name or app_name: values,
            "version": "v0",
            "explicit": True,
        },
    )
    return path


class HeroicDiscoveryTests(unittest.TestCase):
    def test_uses_xdg_config_home(self) -> None:
        root = get_heroic_config_root(
            environment={"XDG_CONFIG_HOME": "/custom/config"},
            home=Path("/ignored"),
        )

        self.assertEqual(root, Path("/custom/config/heroic"))

    def test_empty_xdg_config_home_uses_home_fallback(self) -> None:
        root = get_heroic_config_root(
            environment={"XDG_CONFIG_HOME": "   "},
            home=Path("/users/player"),
        )

        self.assertEqual(root, Path("/users/player/.config/heroic"))

    def test_explicit_config_root_is_normalized(self) -> None:
        root = get_heroic_config_root(config_root=Path("/config/./heroic/../heroic"))

        self.assertEqual(root, Path("/config/heroic"))

    def test_missing_heroic_root_returns_empty_discovery(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            missing = Path(temp_directory) / "missing"

            discovery = discover_heroic_installed_games(config_root=missing)

        self.assertFalse(discovery.config_exists)
        self.assertEqual(discovery.games, ())
        self.assertEqual(discovery.errors, ())

    def test_reads_installed_sideload_and_ignores_not_installed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            install_path = root / "games" / "installed"
            executable = install_path / "Game.exe"
            write_sideload_registry(
                root,
                [
                    {
                        **sideload_entry(install_path, executable),
                        "access_token": "must-not-survive",
                    },
                    sideload_entry(
                        root / "games" / "removed",
                        root / "games" / "removed" / "Removed.exe",
                        app_name="removed",
                        installed=False,
                    ),
                ],
            )

            discovery = discover_heroic_installed_games(config_root=root)

        self.assertEqual(len(discovery.games), 1)
        installed = discovery.games[0]
        self.assertEqual(
            installed.id,
            HeroicGameId(runner="sideload", app_name="game-id"),
        )
        self.assertEqual(installed.install_path, install_path)
        self.assertEqual(installed.executable, executable)
        self.assertNotIn("must-not-survive", repr(installed))

    def test_legendary_combines_relative_executable_with_install_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            install_path = root / "games" / "epic"
            source = root / "legendaryConfig" / "legendary" / "installed.json"
            write_json(
                source,
                {
                    "EpicId": {
                        "app_name": "EpicId",
                        "install_path": str(install_path),
                        "executable": "Binaries/Win64/Game.exe",
                        "platform": "Windows",
                        "refresh_token": "ignored",
                    }
                },
            )

            discovery = discover_heroic_installed_games(config_root=root)

        self.assertEqual(len(discovery.games), 1)
        installed = discovery.games[0]
        self.assertEqual(installed.id.runner, "legendary")
        self.assertEqual(
            installed.executable,
            install_path / "Binaries" / "Win64" / "Game.exe",
        )
        self.assertNotIn("refresh_token", repr(installed))

    def test_dlc_entries_are_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            install_path = root / "games" / "base"
            sideload_dlc = sideload_entry(
                install_path,
                install_path / "Dlc.exe",
                app_name="sideload-dlc",
            )
            assert isinstance(sideload_dlc["install"], dict)
            sideload_dlc["install"]["is_dlc"] = True
            write_sideload_registry(root, [sideload_dlc])
            write_json(
                root / "legendaryConfig" / "legendary" / "installed.json",
                {
                    "legendary-dlc": {
                        "app_name": "legendary-dlc",
                        "install_path": str(install_path),
                        "executable": "Dlc.exe",
                        "is_dlc": True,
                    }
                },
            )
            write_json(
                root / "gog_store" / "installed.json",
                {
                    "installed": [
                        {
                            "appName": "gog-dlc",
                            "install_path": str(install_path),
                            "platform": "windows",
                            "is_dlc": True,
                        }
                    ]
                },
            )

            discovery = discover_heroic_installed_games(config_root=root)

        self.assertEqual(discovery.games, ())

    def test_reads_valid_gog_entry_without_trusting_executable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            install_path = root / "games" / "gog"
            write_json(
                root / "gog_store" / "installed.json",
                {
                    "installed": [
                        {
                            "appName": "123456",
                            "install_path": str(install_path),
                            "platform": "windows",
                            "executable": str(install_path),
                        }
                    ]
                },
            )

            discovery = discover_heroic_installed_games(config_root=root)

        self.assertEqual(len(discovery.games), 1)
        installed = discovery.games[0]
        self.assertEqual(installed.id, HeroicGameId(runner="gog", app_name="123456"))
        self.assertEqual(installed.install_path, install_path)
        self.assertIsNone(installed.executable)

    def test_reads_valid_nile_entry(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            install_path = root / "games" / "amazon"
            write_json(
                root / "nile_config" / "nile" / "installed.json",
                [
                    {
                        "id": "amazon-id",
                        "version": "version-id",
                        "path": str(install_path),
                        "size": 123,
                    }
                ],
            )

            discovery = discover_heroic_installed_games(config_root=root)

        self.assertEqual(len(discovery.games), 1)
        installed = discovery.games[0]
        self.assertEqual(
            installed.id,
            HeroicGameId(runner="nile", app_name="amazon-id"),
        )
        self.assertEqual(installed.install_path, install_path)
        self.assertIsNone(installed.executable)
        self.assertEqual(installed.platform, "Windows")

    def test_malformed_file_records_error_and_preserves_valid_entries(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            install_path = root / "games" / "valid"
            write_sideload_registry(
                root,
                [sideload_entry(install_path, install_path / "Game.exe")],
            )
            malformed = root / "legendaryConfig" / "legendary" / "installed.json"
            malformed.parent.mkdir(parents=True)
            malformed.write_text('{"token":"not-in-error"', encoding="utf-8")

            discovery = discover_heroic_installed_games(config_root=root)

        self.assertEqual(len(discovery.games), 1)
        self.assertEqual(len(discovery.errors), 1)
        self.assertEqual(discovery.errors[0].path, malformed)
        self.assertNotIn("not-in-error", discovery.errors[0].message)

    def test_invalid_utf8_records_controlled_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            path = root / "sideload_apps" / "library.json"
            path.parent.mkdir(parents=True)
            path.write_bytes(b"\xff\xfe")

            discovery = discover_heroic_installed_games(config_root=root)

        self.assertEqual(discovery.games, ())
        self.assertEqual(len(discovery.errors), 1)
        self.assertEqual(discovery.errors[0].path, path)

    def test_same_app_name_in_different_runners_remains_distinct(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            sideload_path = root / "games" / "sideload"
            legendary_path = root / "games" / "legendary"
            write_sideload_registry(
                root,
                [
                    sideload_entry(
                        sideload_path,
                        sideload_path / "Game.exe",
                        app_name="shared-id",
                    )
                ],
            )
            write_json(
                root / "legendaryConfig" / "legendary" / "installed.json",
                {
                    "shared-id": {
                        "app_name": "shared-id",
                        "install_path": str(legendary_path),
                        "executable": "Game.exe",
                    }
                },
            )

            discovery = discover_heroic_installed_games(config_root=root)

        self.assertEqual(
            {game.id for game in discovery.games},
            {
                HeroicGameId(runner="sideload", app_name="shared-id"),
                HeroicGameId(runner="legendary", app_name="shared-id"),
            },
        )

    def test_windows_style_install_path_is_unsupported(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            write_sideload_registry(
                root,
                [
                    sideload_entry(
                        Path(r"C:\Games\Example"),
                        Path(r"C:\Games\Example\Game.exe"),
                    )
                ],
            )

            discovery = discover_heroic_installed_games(config_root=root)

        self.assertEqual(discovery.games, ())
        self.assertTrue(discovery.errors)

    def test_auth_and_browser_storage_are_not_discovered(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            (root / "gog_store").mkdir()
            (root / "gog_store" / "auth.json").write_text("{invalid", encoding="utf-8")
            (root / "Cookies").write_text("sensitive", encoding="utf-8")
            write_json(
                root / "GamesConfig" / "orphan.json",
                {"orphan": {"access_token": "sensitive"}},
            )

            discovery = discover_heroic_installed_games(config_root=root)

        self.assertEqual(discovery.games, ())
        self.assertEqual(discovery.errors, ())

    def test_unsafe_app_name_cannot_escape_whitelisted_config_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            install_path = root / "game"
            write_sideload_registry(
                root,
                [
                    sideload_entry(
                        install_path,
                        install_path / "Game.exe",
                        app_name="../auth",
                    )
                ],
            )
            (root / "auth.json").write_text(
                '{"token":"sensitive"}',
                encoding="utf-8",
            )

            discovery = discover_heroic_installed_games(config_root=root)

        self.assertEqual(discovery.games, ())
        self.assertTrue(discovery.errors)
        self.assertNotIn("sensitive", repr(discovery.errors))

    def test_nul_app_name_is_rejected_without_filesystem_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            install_path = root / "game"
            write_sideload_registry(
                root,
                [
                    sideload_entry(
                        install_path,
                        install_path / "Game.exe",
                        app_name="unsafe\x00id",
                    )
                ],
            )

            discovery = discover_heroic_installed_games(config_root=root)

        self.assertEqual(discovery.games, ())
        self.assertTrue(discovery.errors)
        self.assertNotIn("\x00", repr(discovery.errors))
        self.assertNotIn("embedded null byte", repr(discovery.errors))

    def test_nul_install_path_is_rejected_without_filesystem_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            entry = sideload_entry(root / "game", root / "game" / "Game.exe")
            entry["folder_name"] = f"{root}/unsafe\x00path"
            write_sideload_registry(root, [entry])

            discovery = discover_heroic_installed_games(config_root=root)

        self.assertEqual(discovery.games, ())
        self.assertTrue(discovery.errors)
        self.assertNotIn("\x00", repr(discovery.errors))
        self.assertNotIn("embedded null byte", repr(discovery.errors))

    def test_nul_executable_path_is_rejected_without_dropping_install(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            install_path = root / "game"
            entry = sideload_entry(install_path, install_path / "Game.exe")
            install = entry["install"]
            assert isinstance(install, dict)
            install["executable"] = f"{install_path}/unsafe\x00.exe"
            write_sideload_registry(root, [entry])

            discovery = discover_heroic_installed_games(config_root=root)

        self.assertEqual(len(discovery.games), 1)
        self.assertIsNone(discovery.games[0].executable)
        self.assertTrue(discovery.errors)
        self.assertNotIn("\x00", repr(discovery.errors))
        self.assertNotIn("embedded null byte", repr(discovery.errors))


class HeroicConfigTests(unittest.TestCase):
    def test_reads_game_config_by_installed_app_name(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            install_path = root / "game"
            installed = make_installed_game(install_path)
            prefix = root / "prefix"
            config_path = write_game_config(root, "game-id", prefix)

            config, errors = read_heroic_game_config(root, installed)

        self.assertEqual(errors, ())
        assert config is not None
        self.assertEqual(config.configured_prefix, prefix)
        self.assertEqual(config.wine_version_name, "proton-test")
        self.assertEqual(config.wine_version_type, "proton")
        self.assertEqual(config.wine_binary, Path("/tools/proton"))
        self.assertEqual(config.target_exe, install_path / "bin" / "Target.exe")
        self.assertTrue(config.explicit)
        self.assertEqual(config.source_path, config_path)

    def test_orphan_game_config_does_not_create_installed_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            write_game_config(root, "orphan", root / "prefix")
            game = make_game(root / "game")

            provenance = resolve_game_heroic_provenance(game, config_root=root)

        self.assertTrue(provenance.unknown)
        self.assertEqual(provenance.candidates, ())

    def test_mismatched_internal_config_key_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            game = make_game(root / "game")
            installed = make_installed_game(
                game.root_directory,
                executable=game.executable,
            )
            write_game_config(
                root,
                "game-id",
                root / "prefix",
                internal_app_name="different-id",
            )

            provenance = resolve_game_heroic_provenance(
                game,
                installed_games=make_discovery(root, (installed,)),
            )

        self.assertTrue(provenance.resolved)
        assert provenance.effective is not None
        self.assertIsNone(provenance.effective.config)
        self.assertEqual(
            provenance.effective.prefix.layout, HeroicPrefixLayout.UNRESOLVED
        )
        self.assertEqual(len(provenance.errors), 1)

    def test_token_like_extra_config_fields_are_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            installed = make_installed_game(root / "game")
            write_game_config(
                root,
                "game-id",
                root / "prefix",
                extra_values={
                    "access_token": "must-not-survive",
                    "credentials": {"password": "must-not-survive"},
                },
            )

            config, errors = read_heroic_game_config(root, installed)

        self.assertEqual(errors, ())
        self.assertNotIn("must-not-survive", repr(config))

    def test_nul_config_paths_are_unsupported_without_creating_exact_match(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            install_path = root / "heroic-install"
            game = make_game(root / "outside-game")
            installed = make_installed_game(
                install_path,
                executable=install_path / "Launcher.exe",
            )
            write_game_config(
                root,
                "game-id",
                f"{root}/unsafe\x00prefix",
                extra_values={
                    "wineVersion": {
                        "name": "proton-test",
                        "type": "proton",
                        "bin": "/tools/unsafe\x00proton",
                    },
                    "targetExe": f"{game.executable}\x00",
                },
            )

            config, errors = read_heroic_game_config(root, installed)
            provenance = resolve_game_heroic_provenance(
                game,
                installed_games=make_discovery(root, (installed,)),
            )

        assert config is not None
        self.assertIsNone(config.configured_prefix)
        self.assertIsNone(config.wine_binary)
        self.assertIsNone(config.target_exe)
        self.assertEqual(
            resolve_heroic_prefix_state(config).layout,
            HeroicPrefixLayout.UNRESOLVED,
        )
        self.assertEqual(len(errors), 3)
        self.assertTrue(provenance.unknown)
        self.assertEqual(provenance.candidates, ())
        self.assertNotIn("\x00", repr(errors))
        self.assertNotIn("embedded null byte", repr(errors))


class HeroicConfigOwnershipTests(unittest.TestCase):
    def test_cross_runner_collision_keeps_metadata_ownership_order_independent(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            sideload_path = root / "games" / "sideload"
            legendary_path = root / "games" / "legendary"
            sideload_executable = sideload_path / "Game.exe"
            game = make_game(
                root / "scanned-game",
                executable=sideload_executable,
                steam_api=root / "scanned-game" / "steam_api64.dll",
            )
            write_sideload_registry(
                root,
                [
                    sideload_entry(
                        sideload_path,
                        sideload_executable,
                        app_name="shared-id",
                    )
                ],
            )
            write_json(
                root / "legendaryConfig" / "legendary" / "installed.json",
                {
                    "shared-id": {
                        "app_name": "shared-id",
                        "install_path": str(legendary_path),
                        "executable": "Launcher.exe",
                    }
                },
            )
            prefix = root / "prefix"
            (prefix / "drive_c").mkdir(parents=True)
            config_path = write_game_config(
                root,
                "shared-id",
                prefix,
                extra_values={"targetExe": str(game.executable)},
            )
            discovery = discover_heroic_installed_games(config_root=root)

            first = resolve_game_heroic_provenance(
                game,
                installed_games=discovery,
            )
            second = resolve_game_heroic_provenance(
                game,
                installed_games=make_discovery(
                    root,
                    tuple(reversed(discovery.games)),
                ),
            )

        self.assertEqual(
            {installed.id for installed in discovery.games},
            {
                HeroicGameId(runner="sideload", app_name="shared-id"),
                HeroicGameId(runner="legendary", app_name="shared-id"),
            },
        )
        for provenance in (first, second):
            self.assertTrue(provenance.resolved)
            self.assertEqual(
                len(provenance.candidates),
                len(
                    {candidate.installed_game.id for candidate in provenance.candidates}
                ),
            )
            self.assertIs(
                provenance.strongest_evidence,
                HeroicMatchEvidence.EXACT_EXECUTABLE_PATH,
            )
            assert provenance.effective is not None
            self.assertEqual(
                provenance.effective.installed_game.id,
                HeroicGameId(runner="sideload", app_name="shared-id"),
            )
            self.assertIsNone(provenance.effective.config)
            self.assertEqual(
                provenance.effective.prefix.layout,
                HeroicPrefixLayout.UNRESOLVED,
            )
            self.assertIsNone(provenance.effective.prefix.configured_prefix)
            self.assertEqual(len(provenance.errors), 1)
            self.assertEqual(provenance.errors[0].path, config_path)
            self.assertEqual(
                provenance.errors[0].message,
                "Heroic game config ownership is ambiguous across runners.",
            )

    def test_ambiguous_config_target_exe_cannot_create_exact_match(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            game = make_game(root / "outside-game")
            entries = (
                make_installed_game(
                    root / "sideload",
                    runner="sideload",
                    app_name="shared-id",
                    executable=root / "sideload" / "Launcher.exe",
                ),
                make_installed_game(
                    root / "legendary",
                    runner="legendary",
                    app_name="shared-id",
                    executable=root / "legendary" / "Launcher.exe",
                ),
            )
            write_game_config(
                root,
                "shared-id",
                root / "prefix",
                extra_values={"targetExe": str(game.executable)},
            )

            provenance = resolve_game_heroic_provenance(
                game,
                installed_games=make_discovery(root, entries),
            )

        self.assertTrue(provenance.unknown)
        self.assertEqual(provenance.candidates, ())
        self.assertEqual(len(provenance.errors), 1)

    def test_cross_runner_strong_tier_tie_remains_ambiguous(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            game = make_game(root / "game")
            entries = (
                make_installed_game(
                    root / "sideload",
                    runner="sideload",
                    app_name="shared-id",
                    executable=game.executable,
                ),
                make_installed_game(
                    root / "legendary",
                    runner="legendary",
                    app_name="shared-id",
                    executable=game.executable,
                ),
            )
            prefix = root / "prefix"
            (prefix / "drive_c").mkdir(parents=True)
            write_game_config(root, "shared-id", prefix)

            provenance = resolve_game_heroic_provenance(
                game,
                installed_games=make_discovery(root, entries),
            )

        self.assertTrue(provenance.ambiguous)
        self.assertIsNone(provenance.effective)
        self.assertIs(
            provenance.strongest_evidence,
            HeroicMatchEvidence.EXACT_EXECUTABLE_PATH,
        )
        self.assertEqual(
            {candidate.installed_game.id for candidate in provenance.candidates},
            {entry.id for entry in entries},
        )
        self.assertEqual(
            len(provenance.candidates),
            len({candidate.installed_game.id for candidate in provenance.candidates}),
        )
        self.assertTrue(
            all(candidate.config is None for candidate in provenance.candidates)
        )
        self.assertTrue(
            all(
                candidate.prefix.layout is HeroicPrefixLayout.UNRESOLVED
                for candidate in provenance.candidates
            )
        )

    def test_unique_app_name_keeps_game_config_behavior(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            game = make_game(root / "outside-game")
            installed = make_installed_game(
                root / "heroic-install",
                executable=root / "heroic-install" / "Launcher.exe",
            )
            prefix = root / "prefix"
            (prefix / "drive_c").mkdir(parents=True)
            write_game_config(
                root,
                "game-id",
                prefix,
                extra_values={"targetExe": str(game.executable)},
            )

            provenance = resolve_game_heroic_provenance(
                game,
                installed_games=make_discovery(root, (installed,)),
            )

        self.assertTrue(provenance.resolved)
        self.assertEqual(provenance.errors, ())
        assert provenance.effective is not None
        self.assertIsNotNone(provenance.effective.config)
        self.assertEqual(provenance.effective.prefix.layout, HeroicPrefixLayout.DIRECT)
        self.assertEqual(provenance.effective.prefix.configured_prefix, prefix)

    def test_equivalent_duplicate_identity_is_canonicalized_order_independently(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            game = make_game(root / "outside-game")
            install_path = root / "game"
            entries = (
                make_installed_game(
                    install_path / "nested" / "..",
                    app_name="shared-id",
                    executable=install_path / "nested" / ".." / "Launcher.exe",
                    source_path=Path("/heroic/z-installed.json"),
                ),
                make_installed_game(
                    install_path,
                    app_name="shared-id",
                    executable=install_path / "Launcher.exe",
                    source_path=Path("/heroic/a-installed.json"),
                ),
            )
            write_game_config(
                root,
                "shared-id",
                None,
                extra_values={"targetExe": str(game.executable)},
            )

            first = resolve_game_heroic_provenance(
                game,
                installed_games=make_discovery(root, entries),
            )
            second = resolve_game_heroic_provenance(
                game,
                installed_games=make_discovery(root, tuple(reversed(entries))),
            )

        self.assertEqual(first, second)
        self.assertTrue(first.resolved)
        self.assertEqual(first.errors, ())
        self.assertEqual(len(first.candidates), 1)
        self.assertEqual(
            len(first.candidates),
            len({candidate.installed_game.id for candidate in first.candidates}),
        )
        assert first.effective is not None
        self.assertEqual(
            first.effective.installed_game.id,
            HeroicGameId(runner="sideload", app_name="shared-id"),
        )
        self.assertEqual(
            first.effective.installed_game.source_path,
            Path("/heroic/a-installed.json"),
        )
        self.assertIsNotNone(first.effective.config)

    def test_conflicting_duplicate_identity_is_excluded_order_independently(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            game = make_game(root / "outside-game")
            entries = (
                make_installed_game(
                    root / "first",
                    app_name="shared-id",
                    executable=root / "first" / "Launcher.exe",
                    source_path=Path("/heroic/z-installed.json"),
                ),
                make_installed_game(
                    root / "second",
                    app_name="shared-id",
                    executable=root / "second" / "Launcher.exe",
                    source_path=Path("/heroic/a-installed.json"),
                ),
            )
            write_game_config(
                root,
                "shared-id",
                None,
                extra_values={"targetExe": str(game.executable)},
            )

            first = resolve_game_heroic_provenance(
                game,
                installed_games=make_discovery(root, entries),
            )
            second = resolve_game_heroic_provenance(
                game,
                installed_games=make_discovery(root, tuple(reversed(entries))),
            )

        self.assertEqual(first, second)
        self.assertTrue(first.unknown)
        self.assertIsNone(first.effective)
        self.assertEqual(first.candidates, ())
        self.assertEqual(len(first.errors), 1)
        self.assertEqual(first.errors[0].path, Path("/heroic/a-installed.json"))
        self.assertEqual(
            first.errors[0].message,
            "Conflicting Heroic installed metadata for the same game identity.",
        )

    def test_conflicting_identity_does_not_block_another_valid_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            game = make_game(root / "outside-game")
            entries = (
                make_installed_game(
                    root / "sideload-first",
                    runner="sideload",
                    app_name="shared-id",
                    executable=game.executable,
                    source_path=Path("/heroic/sideload/z-installed.json"),
                ),
                make_installed_game(
                    root / "sideload-second",
                    runner="sideload",
                    app_name="shared-id",
                    executable=game.executable,
                    source_path=Path("/heroic/sideload/a-installed.json"),
                ),
                make_installed_game(
                    root / "legendary",
                    runner="legendary",
                    app_name="shared-id",
                    executable=game.executable,
                ),
            )
            write_game_config(
                root,
                "shared-id",
                root / "prefix",
                extra_values={"targetExe": str(game.executable)},
            )

            provenance = resolve_game_heroic_provenance(
                game,
                installed_games=make_discovery(root, entries),
            )

        self.assertTrue(provenance.resolved)
        self.assertEqual(len(provenance.candidates), 1)
        self.assertEqual(
            len(provenance.candidates),
            len({candidate.installed_game.id for candidate in provenance.candidates}),
        )
        assert provenance.effective is not None
        self.assertEqual(
            provenance.effective.installed_game.id,
            HeroicGameId(runner="legendary", app_name="shared-id"),
        )
        self.assertIsNone(provenance.effective.config)
        self.assertEqual(
            provenance.effective.prefix.layout,
            HeroicPrefixLayout.UNRESOLVED,
        )
        self.assertEqual(
            {error.message for error in provenance.errors},
            {
                "Conflicting Heroic installed metadata for the same game identity.",
                "Heroic game config ownership is ambiguous across runners.",
            },
        )


class HeroicPrefixTests(unittest.TestCase):
    def test_direct_prefix_layout(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            prefix = Path(temp_directory) / "prefix"
            drive_c = prefix / "drive_c"
            drive_c.mkdir(parents=True)

            state = resolve_heroic_prefix_state(make_config(prefix))

        self.assertEqual(state.layout, HeroicPrefixLayout.DIRECT)
        self.assertEqual(state.configured_prefix, prefix)
        self.assertEqual(state.structural_wine_prefix, prefix)
        self.assertEqual(state.drive_c, drive_c)

    def test_pfx_subdirectory_layout(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            prefix = Path(temp_directory) / "prefix"
            drive_c = prefix / "pfx" / "drive_c"
            drive_c.mkdir(parents=True)

            state = resolve_heroic_prefix_state(make_config(prefix))

        self.assertEqual(state.layout, HeroicPrefixLayout.PFX_SUBDIRECTORY)
        self.assertEqual(state.structural_wine_prefix, prefix / "pfx")
        self.assertEqual(state.drive_c, drive_c)

    def test_missing_configured_prefix(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            prefix = Path(temp_directory) / "missing"

            state = resolve_heroic_prefix_state(make_config(prefix))

        self.assertEqual(state.layout, HeroicPrefixLayout.MISSING)
        self.assertEqual(state.configured_prefix, prefix)
        self.assertIsNone(state.structural_wine_prefix)
        self.assertIsNone(state.drive_c)

    def test_no_configured_prefix_is_unresolved(self) -> None:
        state = resolve_heroic_prefix_state(make_config(None))

        self.assertEqual(state.layout, HeroicPrefixLayout.UNRESOLVED)
        self.assertIsNone(state.configured_prefix)

    def test_existing_directory_without_drive_c_is_unresolved(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            prefix = Path(temp_directory) / "prefix"
            prefix.mkdir()

            state = resolve_heroic_prefix_state(make_config(prefix))

        self.assertEqual(state.layout, HeroicPrefixLayout.UNRESOLVED)

    def test_distinct_direct_and_pfx_layouts_are_ambiguous(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            prefix = Path(temp_directory) / "prefix"
            (prefix / "drive_c").mkdir(parents=True)
            (prefix / "pfx" / "drive_c").mkdir(parents=True)

            state = resolve_heroic_prefix_state(make_config(prefix))

        self.assertEqual(state.layout, HeroicPrefixLayout.AMBIGUOUS)
        self.assertIsNone(state.structural_wine_prefix)
        self.assertIsNone(state.drive_c)

    def test_direct_and_pfx_alias_is_not_ambiguous(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            prefix = Path(temp_directory) / "prefix"
            (prefix / "drive_c").mkdir(parents=True)
            (prefix / "pfx").symlink_to(".", target_is_directory=True)

            state = resolve_heroic_prefix_state(make_config(prefix))

        self.assertEqual(state.layout, HeroicPrefixLayout.DIRECT)
        self.assertEqual(state.structural_wine_prefix, prefix)
        self.assertEqual(state.drive_c, prefix / "drive_c")


class HeroicMatchingTests(unittest.TestCase):
    def resolve(
        self,
        game: Game,
        entries: tuple[HeroicInstalledGame, ...],
    ):
        return resolve_game_heroic_provenance(
            game,
            installed_games=make_discovery(Path("/heroic"), entries),
        )

    def test_exact_executable_path_resolves(self) -> None:
        game = make_game(Path("/games/example"))
        installed = make_installed_game(
            Path("/other/install"),
            executable=game.executable,
        )

        provenance = self.resolve(game, (installed,))

        self.assertTrue(provenance.resolved)
        self.assertIs(
            provenance.strongest_evidence, HeroicMatchEvidence.EXACT_EXECUTABLE_PATH
        )

    def test_target_exe_override_can_provide_exact_match(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            game = make_game(root / "outside-game")
            installed = make_installed_game(
                root / "heroic-install",
                executable=root / "heroic-install" / "Launcher.exe",
            )
            write_game_config(
                root,
                "game-id",
                None,
                extra_values={"targetExe": str(game.executable)},
            )

            provenance = resolve_game_heroic_provenance(
                game,
                installed_games=make_discovery(root, (installed,)),
            )

        self.assertTrue(provenance.resolved)
        self.assertIs(
            provenance.strongest_evidence,
            HeroicMatchEvidence.EXACT_EXECUTABLE_PATH,
        )

    def test_game_root_equals_install_path_resolves(self) -> None:
        game = make_game(Path("/games/example"))
        installed = make_installed_game(game.root_directory)

        provenance = self.resolve(game, (installed,))

        self.assertTrue(provenance.resolved)
        self.assertIs(
            provenance.strongest_evidence,
            HeroicMatchEvidence.GAME_ROOT_EQUALS_INSTALL_PATH,
        )

    def test_executable_and_steam_api_containment_resolves(self) -> None:
        game_root = Path("/games/tlou")
        install_path = game_root / "gamedata"
        game = make_game(
            game_root,
            executable=install_path / "crs-handler.exe",
            steam_api=install_path / "steam_api64.dll",
        )
        installed = make_installed_game(
            install_path,
            executable=install_path / "tlou-i-l.exe",
        )

        provenance = self.resolve(game, (installed,))

        self.assertTrue(provenance.resolved)
        self.assertIs(
            provenance.strongest_evidence,
            HeroicMatchEvidence.EXECUTABLE_AND_STEAM_API_WITHIN_INSTALL_PATH,
        )
        assert provenance.effective is not None
        self.assertNotIn(
            HeroicMatchEvidence.EXACT_EXECUTABLE_PATH,
            provenance.effective.evidences,
        )

    def test_executable_only_containment_does_not_resolve(self) -> None:
        install_path = Path("/heroic/install")
        game = make_game(
            Path("/games/example"),
            executable=install_path / "Game.exe",
            steam_api=Path("/other/steam_api64.dll"),
        )

        provenance = self.resolve(game, (make_installed_game(install_path),))

        self.assertTrue(provenance.unknown)
        self.assertEqual(len(provenance.candidates), 1)
        self.assertIsNone(provenance.effective)

    def test_steam_api_only_containment_does_not_resolve(self) -> None:
        install_path = Path("/heroic/install")
        game = make_game(
            Path("/games/example"),
            executable=Path("/other/Game.exe"),
            steam_api=install_path / "steam_api64.dll",
        )

        provenance = self.resolve(game, (make_installed_game(install_path),))

        self.assertTrue(provenance.unknown)
        self.assertEqual(len(provenance.candidates), 1)

    def test_two_exact_matches_are_ambiguous(self) -> None:
        game = make_game(Path("/games/example"))
        entries = (
            make_installed_game(
                Path("/first"),
                app_name="first",
                executable=game.executable,
            ),
            make_installed_game(
                Path("/second"),
                app_name="second",
                executable=game.executable,
            ),
        )

        provenance = self.resolve(game, entries)

        self.assertTrue(provenance.ambiguous)
        self.assertIsNone(provenance.effective)
        self.assertIs(
            provenance.strongest_evidence, HeroicMatchEvidence.EXACT_EXECUTABLE_PATH
        )

    def test_strong_tier_tie_is_not_broken_by_lower_tier(self) -> None:
        game = make_game(Path("/games/example"))
        entries = (
            make_installed_game(
                Path("/first"),
                app_name="first",
                executable=game.executable,
            ),
            make_installed_game(
                Path("/second"),
                app_name="second",
                executable=game.executable,
            ),
            make_installed_game(game.root_directory, app_name="root-match"),
        )

        provenance = self.resolve(game, entries)

        self.assertTrue(provenance.ambiguous)
        self.assertIs(
            provenance.strongest_evidence, HeroicMatchEvidence.EXACT_EXECUTABLE_PATH
        )
        self.assertEqual(len(provenance.candidates), 3)

    def test_entry_order_and_similar_names_do_not_change_resolution(self) -> None:
        game = make_game(Path("/games/The Last of Us"), name="The Last of Us")
        exact = make_installed_game(
            Path("/unrelated"),
            app_name="the-last-of-us-part-one",
            executable=game.executable,
        )
        unrelated = make_installed_game(
            Path("/different"),
            app_name="the-last-of-us",
            executable=Path("/different/Game.exe"),
        )

        first = self.resolve(game, (exact, unrelated))
        second = self.resolve(game, (unrelated, exact))

        assert first.effective is not None
        assert second.effective is not None
        self.assertEqual(first.effective.installed_game.id, exact.id)
        self.assertEqual(second.effective.installed_game.id, exact.id)

    def test_lexically_equivalent_dot_segments_match(self) -> None:
        game = make_game(Path("/games/example"))
        installed = make_installed_game(
            Path("/other"),
            executable=Path("/games/temporary/../example/./Game.exe"),
        )

        provenance = self.resolve(game, (installed,))

        self.assertTrue(provenance.resolved)
        self.assertIs(
            provenance.strongest_evidence, HeroicMatchEvidence.EXACT_EXECUTABLE_PATH
        )

    def test_parent_segments_escaping_install_path_do_not_match(self) -> None:
        install_path = Path("/heroic/install")
        game = make_game(
            Path("/games/example"),
            executable=install_path / ".." / "outside" / "Game.exe",
            steam_api=install_path / ".." / "outside" / "steam_api64.dll",
        )

        provenance = self.resolve(game, (make_installed_game(install_path),))

        self.assertTrue(provenance.unknown)
        self.assertEqual(provenance.candidates, ())

    def test_multiple_weak_candidates_are_ambiguous_without_effective(self) -> None:
        game = make_game(
            Path("/games/example"),
            executable=Path("/first/Game.exe"),
            steam_api=Path("/second/steam_api64.dll"),
        )
        entries = (
            make_installed_game(Path("/first"), app_name="first"),
            make_installed_game(Path("/second"), app_name="second"),
        )

        provenance = self.resolve(game, entries)

        self.assertTrue(provenance.ambiguous)
        self.assertIsNone(provenance.effective)
        self.assertIsNone(provenance.strongest_evidence)


class HeroicRealWorldShapeTests(unittest.TestCase):
    def test_sonic_like_exact_match_and_direct_alias_prefix(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            install_path = root / "Sonic Collection"
            executable = install_path / "ASN_App_PcDx9_Final.exe"
            game = make_game(
                install_path,
                name="Sonic & All-Stars Racing Transformed Collection",
                executable=executable,
                steam_api=install_path / "steam_api.dll",
            )
            prefix = root / "Prefixes" / "Sonic All Stars Racing Transformed"
            (prefix / "drive_c").mkdir(parents=True)
            (prefix / "pfx").symlink_to(".", target_is_directory=True)
            write_sideload_registry(
                root,
                [
                    sideload_entry(
                        install_path,
                        executable,
                        app_name="sonic-id",
                    )
                ],
            )
            write_game_config(root, "sonic-id", prefix)

            provenance = resolve_game_heroic_provenance(game, config_root=root)

        self.assertTrue(provenance.resolved)
        assert provenance.effective is not None
        self.assertIn(
            HeroicMatchEvidence.EXACT_EXECUTABLE_PATH,
            provenance.effective.evidences,
        )
        self.assertEqual(provenance.effective.prefix.layout, HeroicPrefixLayout.DIRECT)
        self.assertEqual(provenance.effective.prefix.structural_wine_prefix, prefix)
        self.assertEqual(provenance.effective.prefix.drive_c, prefix / "drive_c")

    def test_tlou_like_containment_match_and_pfx_prefix(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            game_root = root / "The Last of Us Part I Opti"
            install_path = game_root / "gamedata"
            game = make_game(
                game_root,
                name="The Last of Us Part I Opti",
                executable=install_path / "crs-handler.exe",
                steam_api=install_path / "steam_api64.dll",
            )
            prefix = root / "Prefixes" / "The Last of Us"
            (prefix / "pfx" / "drive_c").mkdir(parents=True)
            write_sideload_registry(
                root,
                [
                    sideload_entry(
                        install_path,
                        install_path / "tlou-i-l.exe",
                        app_name="tlou-id",
                    )
                ],
            )
            write_game_config(root, "tlou-id", prefix)

            provenance = resolve_game_heroic_provenance(game, config_root=root)

        self.assertTrue(provenance.resolved)
        self.assertIs(
            provenance.strongest_evidence,
            HeroicMatchEvidence.EXECUTABLE_AND_STEAM_API_WITHIN_INSTALL_PATH,
        )
        assert provenance.effective is not None
        self.assertNotIn(
            HeroicMatchEvidence.EXACT_EXECUTABLE_PATH,
            provenance.effective.evidences,
        )
        self.assertEqual(
            provenance.effective.prefix.layout,
            HeroicPrefixLayout.PFX_SUBDIRECTORY,
        )
        self.assertEqual(
            provenance.effective.prefix.structural_wine_prefix,
            prefix / "pfx",
        )

    def test_invincible_like_ownership_resolved_with_missing_prefix(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            install_path = root / "Invincible.VS.Season.1"
            executable = install_path / "InvincibleVS.exe"
            game = make_game(
                install_path,
                name="Invincible.VS.Season.1",
                executable=executable,
                steam_api=install_path / "Engine" / "steam_api64.dll",
            )
            configured_prefix = root / "Prefixes" / "Invincible VS"
            write_sideload_registry(
                root,
                [
                    sideload_entry(
                        install_path,
                        executable,
                        app_name="invincible-id",
                    )
                ],
            )
            write_game_config(root, "invincible-id", configured_prefix)

            provenance = resolve_game_heroic_provenance(game, config_root=root)

        self.assertTrue(provenance.resolved)
        assert provenance.effective is not None
        prefix = provenance.effective.prefix
        self.assertEqual(prefix.layout, HeroicPrefixLayout.MISSING)
        self.assertEqual(prefix.configured_prefix, configured_prefix)
        self.assertIsNone(prefix.structural_wine_prefix)
        self.assertIsNone(prefix.drive_c)


class HeroicReadOnlyTests(unittest.TestCase):
    def test_resolver_does_not_write_or_launch_subprocesses(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            install_path = root / "game"
            executable = install_path / "Game.exe"
            game = make_game(install_path, executable=executable)
            write_sideload_registry(
                root,
                [sideload_entry(install_path, executable)],
            )
            write_game_config(root, "game-id", root / "missing-prefix")
            before = {
                path.relative_to(root): path.read_bytes()
                for path in root.rglob("*")
                if path.is_file()
            }
            before_entries = {path.relative_to(root) for path in root.rglob("*")}

            with (
                patch.object(subprocess, "run") as run,
                patch.object(subprocess, "Popen") as popen,
            ):
                resolve_game_heroic_provenance(game, config_root=root)

            after = {
                path.relative_to(root): path.read_bytes()
                for path in root.rglob("*")
                if path.is_file()
            }
            after_entries = {path.relative_to(root) for path in root.rglob("*")}

        self.assertEqual(after, before)
        self.assertEqual(after_entries, before_entries)
        run.assert_not_called()
        popen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
