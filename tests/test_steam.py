from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from goldberg_manager.scanner import Game
from goldberg_manager.steam import (
    STEAM_STATE_FULLY_INSTALLED,
    SteamGameMatch,
    SteamGameProvenance,
    SteamInstalledGame,
    SteamInstalledGames,
    SteamMatchEvidence,
    SteamPrefixLayout,
    SteamPrefixState,
    SteamProvenanceStatus,
    _KeyValuesError,
    _parse_keyvalues,
    discover_steam_installed_games,
    discover_steam_roots,
    resolve_game_steam_provenance,
)


def quote_vdf(value: object) -> str:
    return str(value).replace("\\", "\\\\").replace('"', '\\"')


def write_libraryfolders(
    steam_root: Path,
    libraries: list[tuple[Path, tuple[int, ...]]],
) -> Path:
    path = steam_root / "steamapps" / "libraryfolders.vdf"
    path.parent.mkdir(parents=True, exist_ok=True)
    entries: list[str] = []
    for index, (library_root, app_ids) in enumerate(libraries):
        apps = "\n".join(f'            "{app_id}" "1"' for app_id in app_ids)
        entries.append(
            f'''    "{index}"
    {{
        "path" "{quote_vdf(library_root)}"
        "apps"
        {{
{apps}
        }}
    }}'''
        )
    path.write_text(
        '"libraryfolders"\n{\n' + "\n".join(entries) + "\n}\n",
        encoding="utf-8",
    )
    return path


def write_manifest(
    library_root: Path,
    app_id: int,
    *,
    internal_app_id: object | None = None,
    install_dir: str = "Example",
    state_flags: object = STEAM_STATE_FULLY_INSTALLED,
    name: str = "Example Game",
    create_install: bool = True,
    extra_app_state: str = "",
) -> Path:
    manifest_path = library_root / "steamapps" / f"appmanifest_{app_id}.acf"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        f'''"AppState"
{{
    "appid" "{quote_vdf(app_id if internal_app_id is None else internal_app_id)}"
    "name" "{quote_vdf(name)}"
    "StateFlags" "{quote_vdf(state_flags)}"
    "installdir" "{quote_vdf(install_dir)}"
    {extra_app_state}
    "InstalledDepots"
    {{
        "1"
        {{
            "manifest" "123"
        }}
    }}
}}
''',
        encoding="utf-8",
    )
    if create_install:
        install_path = library_root / "steamapps" / "common" / install_dir
        install_path.mkdir(parents=True, exist_ok=True)
    return manifest_path


def make_game(
    root: Path,
    *,
    executable: Path | None = None,
    steam_api: Path | None = None,
    name: str = "Scanned Game",
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
    app_id: int = 100,
    library_root: Path | None = None,
    name: str | None = "Example Game",
) -> SteamInstalledGame:
    if library_root is None:
        library_root = install_path.parent.parent.parent
    return SteamInstalledGame(
        app_id=app_id,
        library_root=library_root,
        manifest_path=library_root / "steamapps" / f"appmanifest_{app_id}.acf",
        install_dir=install_path.name,
        install_path=install_path,
        state_flags=STEAM_STATE_FULLY_INSTALLED,
        name=name,
    )


def make_discovery(
    games: tuple[SteamInstalledGame, ...],
) -> SteamInstalledGames:
    return SteamInstalledGames(
        steam_roots=(),
        libraries=(),
        games=games,
        errors=(),
    )


class SteamKeyValuesTests(unittest.TestCase):
    def test_parses_nested_quoted_keyvalues_and_escapes(self) -> None:
        payload = _parse_keyvalues(
            '"AppState" { "appid" "100" "nested" { "path" "A\\\\B" } }'
        )

        app_state = payload["AppState"]
        assert isinstance(app_state, dict)
        nested = app_state["nested"]
        assert isinstance(nested, dict)
        self.assertEqual(nested["path"], "A\\B")

    def test_rejects_malformed_keyvalues(self) -> None:
        for content in ('"AppState" {', "AppState { }", '"key"'):
            with self.subTest(content=content), self.assertRaises(_KeyValuesError):
                _parse_keyvalues(content)

    def test_rejects_duplicate_keys_case_insensitively(self) -> None:
        with self.assertRaises(_KeyValuesError):
            _parse_keyvalues('"AppState" { "appid" "100" "AppID" "100" }')

    def test_rejects_nul(self) -> None:
        with self.assertRaises(_KeyValuesError):
            _parse_keyvalues('"path" "/steam\x00/escape"')


class SteamRootDiscoveryTests(unittest.TestCase):
    def test_discovers_explicit_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory) / "Steam"
            root.mkdir()

            roots = discover_steam_roots((root,))

        self.assertEqual(roots, (root,))

    def test_discovers_native_defaults_without_flatpak(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            home = Path(temp_directory)
            root = home / ".local" / "share" / "Steam"
            root.mkdir(parents=True)

            roots = discover_steam_roots(home=home)

        self.assertEqual(roots, (root,))

    def test_missing_roots_are_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            missing = Path(temp_directory) / "missing"

            roots = discover_steam_roots((missing,))

        self.assertEqual(roots, ())

    def test_samefile_aliases_are_deduplicated_order_independently(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            physical = root / "physical"
            physical.mkdir()
            first_alias = root / "a-alias"
            second_alias = root / "z-alias"
            first_alias.symlink_to(physical, target_is_directory=True)
            second_alias.symlink_to(physical, target_is_directory=True)

            first = discover_steam_roots((second_alias, physical, first_alias))
            second = discover_steam_roots((first_alias, second_alias, physical))

        self.assertEqual(first, second)
        self.assertEqual(len(first), 1)
        self.assertEqual(first[0], first_alias)

    def test_samefile_failure_uses_deterministic_lexical_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            first_root = root / "first"
            second_root = root / "second"
            first_root.mkdir()
            second_root.mkdir()

            with patch("goldberg_manager.steam.os.path.samefile", side_effect=OSError):
                first = discover_steam_roots((second_root, first_root))
                second = discover_steam_roots((first_root, second_root))

        self.assertEqual(first, second)
        self.assertEqual(first, (first_root, second_root))


class SteamDiscoveryTests(unittest.TestCase):
    def test_reads_valid_library_and_nested_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory) / "Steam"
            write_libraryfolders(root, [(root, (100,))])
            manifest = write_manifest(root, 100)

            discovery = discover_steam_installed_games(steam_roots=(root,))

        self.assertEqual(discovery.errors, ())
        self.assertEqual(len(discovery.libraries), 1)
        self.assertEqual(discovery.libraries[0].declared_app_ids, (100,))
        self.assertEqual(len(discovery.games), 1)
        self.assertEqual(discovery.games[0].manifest_path, manifest)

    def test_malformed_library_does_not_hide_other_valid_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            invalid_root = root / "invalid"
            invalid_path = invalid_root / "steamapps" / "libraryfolders.vdf"
            invalid_path.parent.mkdir(parents=True)
            invalid_path.write_text('"libraryfolders" {', encoding="utf-8")
            valid_root = root / "valid"
            write_libraryfolders(valid_root, [(valid_root, (200,))])
            write_manifest(valid_root, 200)

            discovery = discover_steam_installed_games(
                steam_roots=(invalid_root, valid_root)
            )

        self.assertEqual([game.app_id for game in discovery.games], [200])
        self.assertEqual(len(discovery.errors), 1)
        self.assertEqual(discovery.errors[0].path, invalid_path)

    def test_duplicate_library_key_is_controlled_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory) / "Steam"
            path = root / "steamapps" / "libraryfolders.vdf"
            path.parent.mkdir(parents=True)
            path.write_text(
                f'''"libraryfolders" {{ "0" {{
                    "path" "{root}" "Path" "{root}" "apps" {{ }}
                }} }}''',
                encoding="utf-8",
            )

            discovery = discover_steam_installed_games(steam_roots=(root,))

        self.assertEqual(discovery.games, ())
        self.assertEqual(len(discovery.errors), 1)
        self.assertNotIn(str(root), discovery.errors[0].message)

    def test_nul_library_value_is_controlled_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory) / "Steam"
            path = root / "steamapps" / "libraryfolders.vdf"
            path.parent.mkdir(parents=True)
            path.write_text(
                '"libraryfolders" { "0" { "path" "/bad\x00path" "apps" { } } }',
                encoding="utf-8",
            )

            discovery = discover_steam_installed_games(steam_roots=(root,))

        self.assertEqual(discovery.games, ())
        self.assertTrue(discovery.errors)
        self.assertNotIn("\x00", repr(discovery.errors))
        self.assertNotIn("embedded null byte", repr(discovery.errors))

    def test_relative_and_windows_library_paths_are_rejected(self) -> None:
        for library_value in ("relative/Steam", r"C:\Steam"):
            with self.subTest(library_value=library_value):
                with tempfile.TemporaryDirectory() as temp_directory:
                    root = Path(temp_directory) / "Steam"
                    path = root / "steamapps" / "libraryfolders.vdf"
                    path.parent.mkdir(parents=True)
                    path.write_text(
                        f'''"libraryfolders" {{ "0" {{
                            "path" "{quote_vdf(library_value)}" "apps" {{ }}
                        }} }}''',
                        encoding="utf-8",
                    )

                    discovery = discover_steam_installed_games(steam_roots=(root,))

                self.assertEqual(discovery.libraries, ())
                self.assertTrue(discovery.errors)

    def test_invalid_apps_map_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory) / "Steam"
            path = root / "steamapps" / "libraryfolders.vdf"
            path.parent.mkdir(parents=True)
            path.write_text(
                f'''"libraryfolders" {{ "0" {{
                    "path" "{root}" "apps" {{ "invalid" "1" }}
                }} }}''',
                encoding="utf-8",
            )

            discovery = discover_steam_installed_games(steam_roots=(root,))

        self.assertEqual(discovery.libraries, ())
        self.assertTrue(discovery.errors)

    def test_reads_multiple_libraries(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory) / "Steam"
            second = Path(temp_directory) / "SecondLibrary"
            second.mkdir()
            write_libraryfolders(root, [(root, (100,)), (second, (200,))])
            write_manifest(root, 100)
            write_manifest(second, 200)

            discovery = discover_steam_installed_games(steam_roots=(root,))

        self.assertEqual(len(discovery.libraries), 2)
        self.assertEqual({game.app_id for game in discovery.games}, {100, 200})

    def test_same_appid_in_distinct_libraries_preserves_both_records(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory) / "Steam"
            second = Path(temp_directory) / "SecondLibrary"
            second.mkdir()
            write_libraryfolders(root, [(root, (100,)), (second, (100,))])
            write_manifest(root, 100)
            write_manifest(second, 100)

            discovery = discover_steam_installed_games(steam_roots=(root,))

        self.assertEqual(len(discovery.games), 2)
        self.assertEqual({game.app_id for game in discovery.games}, {100})
        self.assertEqual(
            {game.library_root for game in discovery.games},
            {root, second},
        )

    def test_alias_roots_do_not_duplicate_libraries_or_games(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            physical = root / "Steam"
            write_libraryfolders(physical, [(physical, (100,))])
            write_manifest(physical, 100)
            alias = root / "steam-alias"
            alias.symlink_to(physical, target_is_directory=True)

            discovery = discover_steam_installed_games(steam_roots=(alias, physical))

        self.assertEqual(len(discovery.steam_roots), 1)
        self.assertEqual(len(discovery.libraries), 1)
        self.assertEqual(len(discovery.games), 1)

    def test_equivalent_metadata_for_physical_library_is_deduplicated(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            first_registry = root / "FirstRegistry"
            second_registry = root / "SecondRegistry"
            shared_library = root / "SharedLibrary"
            shared_library.mkdir()
            write_libraryfolders(first_registry, [(shared_library, (100,))])
            write_libraryfolders(second_registry, [(shared_library, (100,))])
            write_manifest(shared_library, 100)

            discovery = discover_steam_installed_games(
                steam_roots=(second_registry, first_registry)
            )

        self.assertEqual(discovery.errors, ())
        self.assertEqual(len(discovery.libraries), 1)
        self.assertEqual([game.app_id for game in discovery.games], [100])

    def test_conflicting_physical_library_is_excluded_with_its_games(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            first_registry = root / "FirstRegistry"
            second_registry = root / "SecondRegistry"
            shared_library = root / "SharedLibrary"
            shared_library.mkdir()
            write_libraryfolders(first_registry, [(shared_library, (100,))])
            write_libraryfolders(second_registry, [(shared_library, (200,))])
            write_manifest(shared_library, 100)
            write_manifest(shared_library, 200)

            discovery = discover_steam_installed_games(
                steam_roots=(first_registry, second_registry)
            )

        self.assertEqual(discovery.libraries, ())
        self.assertEqual(discovery.games, ())
        self.assertEqual(len(discovery.errors), 1)
        self.assertEqual(
            discovery.errors[0].message,
            "Conflicting Steam metadata for the same physical library.",
        )

    def test_valid_unrelated_library_survives_physical_metadata_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            first_registry = root / "FirstRegistry"
            second_registry = root / "SecondRegistry"
            shared_library = root / "SharedLibrary"
            valid_library = root / "ValidLibrary"
            shared_library.mkdir()
            valid_library.mkdir()
            write_libraryfolders(
                first_registry,
                [(shared_library, (100,)), (valid_library, (300,))],
            )
            write_libraryfolders(second_registry, [(shared_library, (200,))])
            write_manifest(shared_library, 100)
            write_manifest(shared_library, 200)
            write_manifest(valid_library, 300)

            discovery = discover_steam_installed_games(
                steam_roots=(first_registry, second_registry)
            )

        self.assertEqual(
            [library.library_root for library in discovery.libraries],
            [valid_library],
        )
        self.assertEqual([game.app_id for game in discovery.games], [300])
        self.assertEqual(len(discovery.errors), 1)

    def test_physical_metadata_conflict_is_order_independent(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            first_registry = root / "FirstRegistry"
            second_registry = root / "SecondRegistry"
            shared_library = root / "SharedLibrary"
            shared_library.mkdir()
            write_libraryfolders(first_registry, [(shared_library, (100,))])
            write_libraryfolders(second_registry, [(shared_library, (200,))])
            write_manifest(shared_library, 100)
            write_manifest(shared_library, 200)

            first = discover_steam_installed_games(
                steam_roots=(first_registry, second_registry)
            )
            second = discover_steam_installed_games(
                steam_roots=(second_registry, first_registry)
            )

        self.assertEqual(first, second)
        self.assertEqual(first.libraries, ())
        self.assertEqual(first.games, ())

    def test_declared_app_without_manifest_is_controlled_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory) / "Steam"
            write_libraryfolders(root, [(root, (100, 200))])
            write_manifest(root, 200)

            discovery = discover_steam_installed_games(steam_roots=(root,))

        self.assertEqual([game.app_id for game in discovery.games], [200])
        self.assertEqual(len(discovery.errors), 1)

    def test_manifest_outside_apps_map_is_not_installed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory) / "Steam"
            write_libraryfolders(root, [(root, (100,))])
            write_manifest(root, 100)
            write_manifest(root, 200)

            discovery = discover_steam_installed_games(steam_roots=(root,))

        self.assertEqual([game.app_id for game in discovery.games], [100])
        self.assertEqual(len(discovery.errors), 1)

    def test_malformed_manifest_preserves_other_valid_entry(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory) / "Steam"
            write_libraryfolders(root, [(root, (100, 200))])
            malformed = write_manifest(root, 100)
            malformed.write_text('"AppState" {', encoding="utf-8")
            write_manifest(root, 200)

            discovery = discover_steam_installed_games(steam_roots=(root,))

        self.assertEqual([game.app_id for game in discovery.games], [200])
        self.assertEqual(len(discovery.errors), 1)


class SteamManifestValidationTests(unittest.TestCase):
    def discover_one(
        self,
        *,
        internal_app_id: object | None = None,
        install_dir: str = "Example",
        state_flags: object = STEAM_STATE_FULLY_INSTALLED,
        create_install: bool = True,
        extra_app_state: str = "",
    ) -> SteamInstalledGames:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        root = Path(self.temporary_directory.name) / "Steam"
        write_libraryfolders(root, [(root, (100,))])
        write_manifest(
            root,
            100,
            internal_app_id=internal_app_id,
            install_dir=install_dir,
            state_flags=state_flags,
            create_install=create_install,
            extra_app_state=extra_app_state,
        )
        return discover_steam_installed_games(steam_roots=(root,))

    def test_filename_and_internal_appid_must_match(self) -> None:
        discovery = self.discover_one(internal_app_id=200)

        self.assertEqual(discovery.games, ())
        self.assertTrue(discovery.errors)

    def test_zero_internal_appid_is_rejected(self) -> None:
        discovery = self.discover_one(internal_app_id=0)

        self.assertEqual(discovery.games, ())
        self.assertTrue(discovery.errors)

    def test_state_flags_four_and_six_are_fully_installed(self) -> None:
        for state_flags in (4, 6):
            with self.subTest(state_flags=state_flags):
                discovery = self.discover_one(state_flags=state_flags)
                self.assertEqual(len(discovery.games), 1)
                self.assertEqual(discovery.games[0].state_flags, state_flags)

    def test_state_without_fully_installed_bit_is_rejected(self) -> None:
        discovery = self.discover_one(state_flags=2)

        self.assertEqual(discovery.games, ())
        self.assertTrue(discovery.errors)

    def test_install_path_must_exist(self) -> None:
        discovery = self.discover_one(create_install=False)

        self.assertEqual(discovery.games, ())
        self.assertTrue(discovery.errors)

    def test_unsafe_installdir_values_are_rejected(self) -> None:
        for install_dir in ("../escape", "/absolute", r"C:\Games\Escape"):
            with self.subTest(install_dir=install_dir):
                discovery = self.discover_one(
                    install_dir=install_dir,
                    create_install=False,
                )
                self.assertEqual(discovery.games, ())
                self.assertTrue(discovery.errors)

    def test_nul_installdir_is_controlled_error(self) -> None:
        discovery = self.discover_one(
            install_dir="unsafe\x00dir",
            create_install=False,
        )

        self.assertEqual(discovery.games, ())
        self.assertTrue(discovery.errors)
        self.assertNotIn("\x00", repr(discovery.errors))
        self.assertNotIn("embedded null byte", repr(discovery.errors))

    def test_nul_appid_is_controlled_error(self) -> None:
        discovery = self.discover_one(internal_app_id="100\x00")

        self.assertEqual(discovery.games, ())
        self.assertTrue(discovery.errors)
        self.assertNotIn("embedded null byte", repr(discovery.errors))

    def test_duplicate_manifest_key_is_rejected(self) -> None:
        discovery = self.discover_one(extra_app_state='"AppID" "100"')

        self.assertEqual(discovery.games, ())
        self.assertTrue(discovery.errors)


class SteamMatchingTests(unittest.TestCase):
    def test_game_root_equals_install_path_resolves(self) -> None:
        install_path = Path("/library/steamapps/common/Game")
        game = make_game(install_path)

        provenance = resolve_game_steam_provenance(
            game,
            installed_games=make_discovery((make_installed_game(install_path),)),
        )

        self.assertTrue(provenance.resolved)
        self.assertIs(
            provenance.strongest_evidence,
            SteamMatchEvidence.GAME_ROOT_EQUALS_INSTALL_PATH,
        )

    def test_executable_and_steam_api_containment_resolves(self) -> None:
        install_path = Path("/library/steamapps/common/Game")
        game = make_game(
            Path("/scanned/Game"),
            executable=install_path / "bin" / "Game.exe",
            steam_api=install_path / "bin" / "steam_api64.dll",
        )

        provenance = resolve_game_steam_provenance(
            game,
            installed_games=make_discovery((make_installed_game(install_path),)),
        )

        self.assertTrue(provenance.resolved)
        self.assertIs(
            provenance.strongest_evidence,
            SteamMatchEvidence.EXECUTABLE_AND_STEAM_API_WITHIN_INSTALL_PATH,
        )

    def test_executable_only_is_weak(self) -> None:
        install_path = Path("/library/steamapps/common/Game")
        game = make_game(
            Path("/external/Game"),
            executable=install_path / "Game.exe",
            steam_api=Path("/external/steam_api64.dll"),
        )

        provenance = resolve_game_steam_provenance(
            game,
            installed_games=make_discovery((make_installed_game(install_path),)),
        )

        self.assertTrue(provenance.unknown)
        self.assertEqual(len(provenance.candidates), 1)
        self.assertIn(
            SteamMatchEvidence.EXECUTABLE_WITHIN_INSTALL_PATH,
            provenance.candidates[0].evidences,
        )

    def test_steam_api_only_is_weak(self) -> None:
        install_path = Path("/library/steamapps/common/Game")
        game = make_game(
            Path("/external/Game"),
            executable=Path("/external/Game.exe"),
            steam_api=install_path / "steam_api64.dll",
        )

        provenance = resolve_game_steam_provenance(
            game,
            installed_games=make_discovery((make_installed_game(install_path),)),
        )

        self.assertTrue(provenance.unknown)
        self.assertEqual(len(provenance.candidates), 1)

    def test_two_records_in_same_strong_tier_are_ambiguous(self) -> None:
        install_path = Path("/shared/Game")
        game = make_game(install_path)
        entries = (
            make_installed_game(
                install_path,
                app_id=100,
                library_root=Path("/first-library"),
            ),
            make_installed_game(
                install_path,
                app_id=100,
                library_root=Path("/second-library"),
            ),
        )

        provenance = resolve_game_steam_provenance(
            game,
            installed_games=make_discovery(entries),
        )

        self.assertTrue(provenance.ambiguous)
        self.assertIsNone(provenance.effective)
        self.assertIsNone(provenance.prefix)

    def test_strong_tie_is_not_broken_by_lower_tier(self) -> None:
        install_path = Path("/games/Tie")
        game = make_game(install_path)
        entries = (
            make_installed_game(
                install_path,
                app_id=100,
                library_root=Path("/first"),
            ),
            make_installed_game(
                install_path,
                app_id=200,
                library_root=Path("/second"),
            ),
            make_installed_game(
                Path("/games"),
                app_id=300,
                library_root=Path("/third"),
            ),
        )

        provenance = resolve_game_steam_provenance(
            game,
            installed_games=make_discovery(entries),
        )

        self.assertTrue(provenance.ambiguous)
        self.assertIs(
            provenance.strongest_evidence,
            SteamMatchEvidence.GAME_ROOT_EQUALS_INSTALL_PATH,
        )
        self.assertEqual(len(provenance.candidates), 3)

    def test_names_and_entry_order_do_not_change_resolution(self) -> None:
        game = make_game(Path("/games/Actual"), name="Similar Name")
        exact = make_installed_game(
            game.root_directory,
            app_id=100,
            library_root=Path("/z-library"),
            name="Unrelated",
        )
        unrelated = make_installed_game(
            Path("/other"),
            app_id=200,
            library_root=Path("/a-library"),
            name="Similar Name",
        )

        first = resolve_game_steam_provenance(
            game,
            installed_games=make_discovery((exact, unrelated)),
        )
        second = resolve_game_steam_provenance(
            game,
            installed_games=make_discovery((unrelated, exact)),
        )

        assert first.effective is not None
        assert second.effective is not None
        self.assertEqual(first.effective.installed_game.app_id, 100)
        self.assertEqual(second.effective.installed_game.app_id, 100)
        self.assertEqual(first.candidates, second.candidates)

    def test_profile_appid_alone_cannot_create_ownership(self) -> None:
        profile_app_id = 291550
        installed = make_installed_game(
            Path("/steam/steamapps/common/Brawlhalla"),
            app_id=profile_app_id,
            library_root=Path("/steam"),
        )
        external_game = make_game(Path("/external/Brawlhalla"))

        provenance = resolve_game_steam_provenance(
            external_game,
            installed_games=make_discovery((installed,)),
        )

        self.assertEqual(installed.app_id, profile_app_id)
        self.assertTrue(provenance.unknown)
        self.assertEqual(provenance.candidates, ())


class SteamProvenanceInvariantTests(unittest.TestCase):
    def make_resolved_parts(
        self,
    ) -> tuple[SteamInstalledGames, SteamGameMatch, SteamPrefixState]:
        installed = make_installed_game(
            Path("/library-a/steamapps/common/Game"),
            app_id=100,
            library_root=Path("/library-a"),
        )
        effective = SteamGameMatch(
            installed_game=installed,
            evidences=(SteamMatchEvidence.GAME_ROOT_EQUALS_INSTALL_PATH,),
        )
        prefix = SteamPrefixState(
            compatdata_root=Path("/library-a/steamapps/compatdata/100"),
            structural_wine_prefix=None,
            drive_c=None,
            layout=SteamPrefixLayout.MISSING,
        )
        return make_discovery((installed,)), effective, prefix

    def test_resolved_rejects_prefix_from_wrong_library(self) -> None:
        discovery, effective, _ = self.make_resolved_parts()
        wrong_prefix = SteamPrefixState(
            compatdata_root=Path("/library-b/steamapps/compatdata/100"),
            structural_wine_prefix=None,
            drive_c=None,
            layout=SteamPrefixLayout.MISSING,
        )

        with self.assertRaisesRegex(ValueError, "effective ownership"):
            SteamGameProvenance(
                discovery=discovery,
                status=SteamProvenanceStatus.RESOLVED,
                candidates=(effective,),
                effective=effective,
                prefix=wrong_prefix,
                strongest_evidence=SteamMatchEvidence.GAME_ROOT_EQUALS_INSTALL_PATH,
            )

    def test_resolved_rejects_prefix_from_wrong_appid(self) -> None:
        discovery, effective, _ = self.make_resolved_parts()
        wrong_prefix = SteamPrefixState(
            compatdata_root=Path("/library-a/steamapps/compatdata/200"),
            structural_wine_prefix=None,
            drive_c=None,
            layout=SteamPrefixLayout.MISSING,
        )

        with self.assertRaisesRegex(ValueError, "effective ownership"):
            SteamGameProvenance(
                discovery=discovery,
                status=SteamProvenanceStatus.RESOLVED,
                candidates=(effective,),
                effective=effective,
                prefix=wrong_prefix,
                strongest_evidence=SteamMatchEvidence.GAME_ROOT_EQUALS_INSTALL_PATH,
            )

    def test_resolved_rejects_weak_strongest_evidence(self) -> None:
        discovery, effective, prefix = self.make_resolved_parts()

        with self.assertRaisesRegex(ValueError, "strong tier"):
            SteamGameProvenance(
                discovery=discovery,
                status=SteamProvenanceStatus.RESOLVED,
                candidates=(effective,),
                effective=effective,
                prefix=prefix,
                strongest_evidence=SteamMatchEvidence.EXECUTABLE_WITHIN_INSTALL_PATH,
            )

    def test_resolved_rejects_strongest_evidence_absent_from_effective(self) -> None:
        discovery, candidate, prefix = self.make_resolved_parts()
        effective = SteamGameMatch(
            installed_game=candidate.installed_game,
            evidences=(
                SteamMatchEvidence.EXECUTABLE_AND_STEAM_API_WITHIN_INSTALL_PATH,
            ),
        )
        highest_candidate = SteamGameMatch(
            installed_game=make_installed_game(
                Path("/library-b/steamapps/common/Game"),
                app_id=200,
                library_root=Path("/library-b"),
            ),
            evidences=(SteamMatchEvidence.GAME_ROOT_EQUALS_INSTALL_PATH,),
        )
        discovery = make_discovery(
            (effective.installed_game, highest_candidate.installed_game)
        )

        with self.assertRaisesRegex(ValueError, "effective match"):
            SteamGameProvenance(
                discovery=discovery,
                status=SteamProvenanceStatus.RESOLVED,
                candidates=(effective, highest_candidate),
                effective=effective,
                prefix=prefix,
                strongest_evidence=SteamMatchEvidence.GAME_ROOT_EQUALS_INSTALL_PATH,
            )

    def test_resolved_rejects_equivalent_but_distinct_effective(self) -> None:
        discovery, candidate, prefix = self.make_resolved_parts()
        equivalent_effective = SteamGameMatch(
            installed_game=candidate.installed_game,
            evidences=candidate.evidences,
        )
        self.assertEqual(candidate, equivalent_effective)
        self.assertIsNot(candidate, equivalent_effective)

        with self.assertRaisesRegex(ValueError, "must be a candidate"):
            SteamGameProvenance(
                discovery=discovery,
                status=SteamProvenanceStatus.RESOLVED,
                candidates=(candidate,),
                effective=equivalent_effective,
                prefix=prefix,
                strongest_evidence=SteamMatchEvidence.GAME_ROOT_EQUALS_INSTALL_PATH,
            )

    def test_ambiguous_requires_two_candidates_in_strongest_tier(self) -> None:
        discovery, strongest_candidate, _ = self.make_resolved_parts()
        weak_candidate = SteamGameMatch(
            installed_game=make_installed_game(
                Path("/library-b/steamapps/common/Game"),
                app_id=200,
                library_root=Path("/library-b"),
            ),
            evidences=(SteamMatchEvidence.EXECUTABLE_WITHIN_INSTALL_PATH,),
        )

        with self.assertRaisesRegex(ValueError, "two strongest-tier candidates"):
            SteamGameProvenance(
                discovery=discovery,
                status=SteamProvenanceStatus.AMBIGUOUS,
                candidates=(strongest_candidate, weak_candidate),
                effective=None,
                prefix=None,
                strongest_evidence=SteamMatchEvidence.GAME_ROOT_EQUALS_INSTALL_PATH,
            )

    def test_resolved_rejects_two_candidates_in_highest_strong_tier(self) -> None:
        discovery, effective, prefix = self.make_resolved_parts()
        second = SteamGameMatch(
            installed_game=make_installed_game(
                Path("/library-b/steamapps/common/Game"),
                app_id=200,
                library_root=Path("/library-b"),
            ),
            evidences=(SteamMatchEvidence.GAME_ROOT_EQUALS_INSTALL_PATH,),
        )
        discovery = make_discovery((effective.installed_game, second.installed_game))

        with self.assertRaisesRegex(ValueError, "exactly one highest-tier candidate"):
            SteamGameProvenance(
                discovery=discovery,
                status=SteamProvenanceStatus.RESOLVED,
                candidates=(effective, second),
                effective=effective,
                prefix=prefix,
                strongest_evidence=SteamMatchEvidence.GAME_ROOT_EQUALS_INSTALL_PATH,
            )

    def test_resolved_rejects_lower_strongest_evidence(self) -> None:
        discovery, candidate, prefix = self.make_resolved_parts()
        effective = SteamGameMatch(
            installed_game=candidate.installed_game,
            evidences=(
                SteamMatchEvidence.GAME_ROOT_EQUALS_INSTALL_PATH,
                SteamMatchEvidence.EXECUTABLE_AND_STEAM_API_WITHIN_INSTALL_PATH,
            ),
        )

        with self.assertRaisesRegex(ValueError, "highest strong tier"):
            SteamGameProvenance(
                discovery=discovery,
                status=SteamProvenanceStatus.RESOLVED,
                candidates=(effective,),
                effective=effective,
                prefix=prefix,
                strongest_evidence=(
                    SteamMatchEvidence.EXECUTABLE_AND_STEAM_API_WITHIN_INSTALL_PATH
                ),
            )

    def test_resolved_accepts_unique_highest_tier_with_weak_candidates(self) -> None:
        discovery, effective, prefix = self.make_resolved_parts()
        weak = SteamGameMatch(
            installed_game=make_installed_game(
                Path("/library-b/steamapps/common/Game"),
                app_id=200,
                library_root=Path("/library-b"),
            ),
            evidences=(SteamMatchEvidence.EXECUTABLE_WITHIN_INSTALL_PATH,),
        )
        discovery = make_discovery((effective.installed_game, weak.installed_game))

        provenance = SteamGameProvenance(
            discovery=discovery,
            status=SteamProvenanceStatus.RESOLVED,
            candidates=(effective, weak),
            effective=effective,
            prefix=prefix,
            strongest_evidence=SteamMatchEvidence.GAME_ROOT_EQUALS_INSTALL_PATH,
        )

        self.assertIs(provenance.effective, effective)

    def test_ambiguous_rejects_lower_strongest_evidence(self) -> None:
        discovery, candidate, _ = self.make_resolved_parts()
        highest = SteamGameMatch(
            installed_game=candidate.installed_game,
            evidences=(
                SteamMatchEvidence.GAME_ROOT_EQUALS_INSTALL_PATH,
                SteamMatchEvidence.EXECUTABLE_AND_STEAM_API_WITHIN_INSTALL_PATH,
            ),
        )
        lower = SteamGameMatch(
            installed_game=make_installed_game(
                Path("/library-b/steamapps/common/Game"),
                app_id=200,
                library_root=Path("/library-b"),
            ),
            evidences=(
                SteamMatchEvidence.EXECUTABLE_AND_STEAM_API_WITHIN_INSTALL_PATH,
            ),
        )

        with self.assertRaisesRegex(ValueError, "highest strong tier"):
            SteamGameProvenance(
                discovery=discovery,
                status=SteamProvenanceStatus.AMBIGUOUS,
                candidates=(highest, lower),
                effective=None,
                prefix=None,
                strongest_evidence=(
                    SteamMatchEvidence.EXECUTABLE_AND_STEAM_API_WITHIN_INSTALL_PATH
                ),
            )

    def test_unknown_rejects_candidate_with_strong_evidence(self) -> None:
        discovery, strong_candidate, _ = self.make_resolved_parts()

        with self.assertRaisesRegex(ValueError, "cannot contain strong evidence"):
            SteamGameProvenance(
                discovery=discovery,
                status=SteamProvenanceStatus.UNKNOWN,
                candidates=(strong_candidate,),
                effective=None,
                prefix=None,
                strongest_evidence=None,
            )

    def test_unknown_accepts_weak_candidates(self) -> None:
        discovery, candidate, _ = self.make_resolved_parts()
        weak = SteamGameMatch(
            installed_game=candidate.installed_game,
            evidences=(SteamMatchEvidence.EXECUTABLE_WITHIN_INSTALL_PATH,),
        )

        provenance = SteamGameProvenance(
            discovery=discovery,
            status=SteamProvenanceStatus.UNKNOWN,
            candidates=(weak,),
            effective=None,
            prefix=None,
            strongest_evidence=None,
        )

        self.assertTrue(provenance.unknown)
        self.assertEqual(provenance.candidates, (weak,))

    def test_existing_resolver_creates_valid_provenances(self) -> None:
        install_path = Path("/library/steamapps/common/Game")
        installed = make_installed_game(install_path)
        second = make_installed_game(
            install_path,
            app_id=200,
            library_root=Path("/other-library"),
        )
        resolved = resolve_game_steam_provenance(
            make_game(install_path),
            installed_games=make_discovery((installed,)),
        )
        ambiguous = resolve_game_steam_provenance(
            make_game(install_path),
            installed_games=make_discovery((installed, second)),
        )
        weak_game = make_game(
            Path("/external/Game"),
            executable=install_path / "Game.exe",
            steam_api=Path("/external/steam_api64.dll"),
        )
        unknown = resolve_game_steam_provenance(
            weak_game,
            installed_games=make_discovery((installed,)),
        )

        self.assertTrue(resolved.resolved)
        self.assertTrue(ambiguous.ambiguous)
        self.assertTrue(unknown.unknown)


class SteamPrefixTests(unittest.TestCase):
    def test_brawlhalla_like_resolves_ownership_and_pfx(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory) / "Steam"
            write_libraryfolders(root, [(root, (291550,))])
            write_manifest(root, 291550, install_dir="Brawlhalla", name="Brawlhalla")
            install_path = root / "steamapps" / "common" / "Brawlhalla"
            game = make_game(install_path)
            drive_c = root / "steamapps" / "compatdata" / "291550" / "pfx" / "drive_c"
            drive_c.mkdir(parents=True)

            provenance = resolve_game_steam_provenance(
                game,
                steam_roots=(root,),
            )

        self.assertTrue(provenance.resolved)
        self.assertIs(
            provenance.strongest_evidence,
            SteamMatchEvidence.GAME_ROOT_EQUALS_INSTALL_PATH,
        )
        assert provenance.prefix is not None
        self.assertIs(provenance.prefix.layout, SteamPrefixLayout.PFX_SUBDIRECTORY)
        self.assertEqual(provenance.prefix.structural_wine_prefix, drive_c.parent)
        self.assertEqual(provenance.prefix.drive_c, drive_c)

    def test_missing_compatdata_keeps_resolved_ownership(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory) / "Steam"
            install_path = root / "steamapps" / "common" / "Game"
            installed = make_installed_game(
                install_path,
                library_root=root,
            )

            provenance = resolve_game_steam_provenance(
                make_game(install_path),
                installed_games=make_discovery((installed,)),
            )

        self.assertTrue(provenance.resolved)
        assert provenance.prefix is not None
        self.assertIs(provenance.prefix.layout, SteamPrefixLayout.MISSING)
        self.assertIsNone(provenance.prefix.structural_wine_prefix)

    def test_cs2_like_empty_compatdata_is_unresolved(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory) / "Steam"
            install_path = root / "steamapps" / "common" / "CS2"
            installed = make_installed_game(
                install_path,
                app_id=730,
                library_root=root,
            )
            (root / "steamapps" / "compatdata" / "730").mkdir(parents=True)

            provenance = resolve_game_steam_provenance(
                make_game(install_path),
                installed_games=make_discovery((installed,)),
            )

        self.assertTrue(provenance.resolved)
        assert provenance.prefix is not None
        self.assertIs(provenance.prefix.layout, SteamPrefixLayout.UNRESOLVED)
        self.assertIsNone(provenance.prefix.drive_c)

    def test_orphan_compatdata_is_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory) / "Steam"
            install_path = root / "steamapps" / "common" / "Game"
            installed = make_installed_game(
                install_path,
                app_id=100,
                library_root=root,
            )
            orphan_drive_c = (
                root / "steamapps" / "compatdata" / "999" / "pfx" / "drive_c"
            )
            orphan_drive_c.mkdir(parents=True)

            provenance = resolve_game_steam_provenance(
                make_game(install_path),
                installed_games=make_discovery((installed,)),
            )

        assert provenance.prefix is not None
        self.assertIs(provenance.prefix.layout, SteamPrefixLayout.MISSING)
        self.assertNotEqual(provenance.prefix.drive_c, orphan_drive_c)

    def test_prefix_from_other_library_is_not_adopted(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            first_library = root / "LibraryA"
            second_library = root / "LibraryB"
            install_path = first_library / "steamapps" / "common" / "Game"
            installed = make_installed_game(
                install_path,
                app_id=100,
                library_root=first_library,
            )
            other_drive_c = (
                second_library / "steamapps" / "compatdata" / "100" / "pfx" / "drive_c"
            )
            other_drive_c.mkdir(parents=True)

            provenance = resolve_game_steam_provenance(
                make_game(install_path),
                installed_games=make_discovery((installed,)),
            )

        self.assertTrue(provenance.resolved)
        assert provenance.prefix is not None
        self.assertIs(provenance.prefix.layout, SteamPrefixLayout.MISSING)
        self.assertNotEqual(provenance.prefix.drive_c, other_drive_c)


class SteamReadOnlyTests(unittest.TestCase):
    def test_resolution_does_not_write_or_launch_subprocesses(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory) / "Steam"
            write_libraryfolders(root, [(root, (291550,))])
            write_manifest(root, 291550, install_dir="Brawlhalla")
            install_path = root / "steamapps" / "common" / "Brawlhalla"
            (root / "steamapps" / "compatdata" / "291550" / "pfx" / "drive_c").mkdir(
                parents=True
            )
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
                resolve_game_steam_provenance(
                    make_game(install_path),
                    steam_roots=(root,),
                )

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
