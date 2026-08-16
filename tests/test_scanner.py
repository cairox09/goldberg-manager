import tempfile
import unittest
from pathlib import Path

from goldberg_manager.scanner import (
    detect_emu_config_generator,
    detect_games,
    detect_generate_interfaces,
    discover_game_candidates,
)


class ScannerTests(unittest.TestCase):
    def test_detects_64_bit_game_in_generic_subdirectory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            library = Path(temp_directory)
            game_root = library / "Resident Evil 2"
            game_data = game_root / "gamedata"
            game_data.mkdir(parents=True)

            executable = game_data / "re2.exe"
            steam_api = game_data / "steam_api64.dll"

            executable.write_bytes(b"exe")
            steam_api.write_bytes(b"dll")

            games = detect_games([library])

            self.assertEqual(len(games), 1)

            game = games[0]

            self.assertEqual(game.name, "Resident Evil 2")
            self.assertEqual(game.root_directory, game_root)
            self.assertEqual(game.executable, executable)
            self.assertEqual(game.steam_api, steam_api)
            self.assertEqual(
                game.steam_api_relative_path,
                Path("gamedata/steam_api64.dll"),
            )
            self.assertEqual(game.architecture, "64-bit")
            self.assertEqual(game.source_directory, library)

    def test_detects_32_bit_game(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            library = Path(temp_directory)
            game_root = library / "Sonic Racing"
            game_root.mkdir()

            executable = game_root / "Sonic.exe"
            steam_api = game_root / "steam_api.dll"

            executable.write_bytes(b"exe")
            steam_api.write_bytes(b"dll")

            games = detect_games([library])

            self.assertEqual(len(games), 1)

            game = games[0]

            self.assertEqual(game.name, "Sonic Racing")
            self.assertEqual(game.architecture, "32-bit")
            self.assertEqual(
                game.steam_api_relative_path,
                Path("steam_api.dll"),
            )

    def test_prefers_game_executable_over_launcher(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            library = Path(temp_directory)
            game_root = library / "Example Game"
            game_root.mkdir()

            (game_root / "Launcher.exe").write_bytes(b"launcher")
            executable = game_root / "Game.exe"
            executable.write_bytes(b"game")
            (game_root / "steam_api64.dll").write_bytes(b"dll")

            games = detect_games([library])

            self.assertEqual(len(games), 1)
            self.assertEqual(games[0].executable, executable)

    def test_ignores_directory_without_executable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            library = Path(temp_directory)
            game_root = library / "Broken Game"
            game_root.mkdir()

            (game_root / "steam_api64.dll").write_bytes(b"dll")

            games = detect_games([library])

            self.assertEqual(games, [])

    def test_detects_game_with_deep_separate_steam_api(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            library = Path(temp_directory)

            game_root = library / "Invincible VS"

            steam_directory = (
                game_root
                / "Engine"
                / "Binaries"
                / "ThirdParty"
                / "Steamworks"
                / "Steamv161"
                / "Win64"
            )

            shipping_directory = game_root / "TagFighter" / "Binaries" / "Win64"

            steam_directory.mkdir(parents=True)

            shipping_directory.mkdir(parents=True)

            executable = game_root / "InvincibleVS.exe"

            shipping_executable = shipping_directory / "InvincibleVS-Win64-Shipping.exe"

            steam_api = steam_directory / "steam_api64.dll"

            executable.write_bytes(b"exe")

            shipping_executable.write_bytes(b"exe")

            steam_api.write_bytes(b"dll")

            games = detect_games([library])

            self.assertEqual(
                len(games),
                1,
            )

            game = games[0]

            self.assertEqual(
                game.name,
                "Invincible VS",
            )

            self.assertEqual(
                game.root_directory,
                game_root,
            )

            self.assertEqual(
                game.executable,
                executable,
            )

            self.assertEqual(
                game.steam_api,
                steam_api,
            )

            self.assertEqual(
                game.steam_api_relative_path,
                Path(
                    "Engine/"
                    "Binaries/"
                    "ThirdParty/"
                    "Steamworks/"
                    "Steamv161/"
                    "Win64/"
                    "steam_api64.dll"
                ),
            )

            self.assertEqual(
                game.architecture,
                "64-bit",
            )

            self.assertEqual(
                game.source_directory,
                library,
            )

    def test_detects_generate_interfaces_tools(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            tools = root / "tools" / "generate_interfaces"
            tools.mkdir(parents=True)

            x64 = tools / "generate_interfaces_x64.exe"
            x86 = tools / "generate_interfaces_x86.exe"

            x64.write_bytes(b"x64")
            x86.write_bytes(b"x86")

            detected_x64, detected_x86 = detect_generate_interfaces(root)

            self.assertEqual(detected_x64, x64)
            self.assertEqual(detected_x86, x86)

    def test_detects_emu_config_generator(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)

            generator_directory = root / "gse_fork_tools" / "generate_emu_config"

            generator_directory.mkdir(parents=True)

            generator = generator_directory / "generate_emu_config"

            generator.write_bytes(b"generator")

            detected = detect_emu_config_generator(root)

            self.assertEqual(
                detected,
                generator,
            )

    def test_detects_emu_config_generator_from_sibling_tools(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            base = Path(temp_directory)

            goldberg_root = base / "gbe_fork" / "release"

            goldberg_root.mkdir(parents=True)

            generator_directory = base / "gse_fork_tools" / "generate_emu_config"

            generator_directory.mkdir(parents=True)

            generator = generator_directory / "generate_emu_config"

            generator.write_bytes(b"generator")

            detected = detect_emu_config_generator(goldberg_root)

            self.assertEqual(
                detected,
                generator,
            )

    def test_detects_game_root_through_nested_generic_directories(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            library = Path(temp_directory)
            game_root = library / "Example Game"
            binaries = game_root / "Binaries" / "Win64"
            binaries.mkdir(parents=True)

            executable = binaries / "ExampleGame.exe"
            steam_api = binaries / "steam_api64.dll"

            executable.write_bytes(b"exe")
            steam_api.write_bytes(b"dll")

            games = detect_games([library])

            self.assertEqual(len(games), 1)

            game = games[0]

            self.assertEqual(game.name, "Example Game")
            self.assertEqual(game.root_directory, game_root)
            self.assertEqual(game.executable, executable)
            self.assertEqual(game.steam_api, steam_api)
            self.assertEqual(
                game.steam_api_relative_path,
                Path("Binaries/Win64/steam_api64.dll"),
            )

    def test_discovers_game_without_steam_api(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            library = Path(temp_directory)

            game_root = library / "Assassin's Creed"

            game_root.mkdir()

            executable = game_root / "AssassinsCreed_Game.exe"

            executable.write_bytes(b"exe")

            detection_directory = game_root / "Detection"

            detection_directory.mkdir()

            (detection_directory / "Detection.exe").write_bytes(b"exe")

            candidates = discover_game_candidates([library])

            self.assertEqual(
                len(candidates),
                1,
            )

            candidate = candidates[0]

            self.assertEqual(
                candidate.name,
                "Assassin's Creed",
            )

            self.assertEqual(
                candidate.root_directory,
                game_root,
            )

            self.assertEqual(
                candidate.executable,
                executable,
            )

            self.assertFalse(candidate.configurable)

            self.assertIsNone(candidate.game)

    def test_discovers_configurable_game(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            library = Path(temp_directory)

            game_root = library / "Example Game"

            game_root.mkdir()

            executable = game_root / "Game.exe"

            steam_api = game_root / "steam_api64.dll"

            executable.write_bytes(b"exe")

            steam_api.write_bytes(b"dll")

            candidates = discover_game_candidates([library])

            self.assertEqual(
                len(candidates),
                1,
            )

            candidate = candidates[0]

            self.assertTrue(candidate.configurable)

            self.assertIsNotNone(candidate.game)

            assert candidate.game is not None

            self.assertEqual(
                candidate.game.steam_api,
                steam_api,
            )

    def test_does_not_promote_library_root_from_setup_executable(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            library = Path(temp_directory)

            setup = library / "BakkesModSetup.exe"

            steam_directory = library / "release" / "regular" / "x64"

            steam_directory.mkdir(parents=True)

            steam_api = steam_directory / "steam_api64.dll"

            setup.write_bytes(b"setup")

            steam_api.write_bytes(b"dll")

            games = detect_games([library])

            self.assertEqual(
                games,
                [],
            )

    def test_loose_steam_api_does_not_hide_discovered_games(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            library = Path(temp_directory)

            (library / "BakkesModSetup.exe").write_bytes(b"setup")

            loose_api_directory = library / "release" / "regular" / "x64"

            loose_api_directory.mkdir(parents=True)

            (loose_api_directory / "steam_api64.dll").write_bytes(b"dll")

            ac1 = library / "Assassins Creed"

            ac1.mkdir()

            (ac1 / "AssassinsCreed_Game.exe").write_bytes(b"exe")

            detection = ac1 / "Detection"

            detection.mkdir()

            (detection / "Detection.exe").write_bytes(b"exe")

            ac2 = library / "Assassins Creed II"

            ac2.mkdir()

            (ac2 / "AssassinsCreedII.exe").write_bytes(b"exe")

            (ac2 / "UPlayBrowser.exe").write_bytes(b"browser")

            candidates = discover_game_candidates([library])

            self.assertEqual(
                len(candidates),
                2,
            )

            candidates_by_name = {candidate.name: candidate for candidate in candidates}

            self.assertIn(
                "Assassins Creed",
                candidates_by_name,
            )

            self.assertIn(
                "Assassins Creed II",
                candidates_by_name,
            )

            self.assertFalse(candidates_by_name["Assassins Creed"].configurable)

            self.assertFalse(candidates_by_name["Assassins Creed II"].configurable)

    def test_prefers_nested_game_over_translation_wrapper(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            library = Path(temp_directory)

            wrapper = library / "Assassins-Creed-II-Steamrip"

            game_root = wrapper / "Assassins Creed II"

            game_root.mkdir(parents=True)

            (wrapper / "Assassins Creed 2 - TRADUÇÃO.exe").write_bytes(b"translation")

            executable = game_root / "AssassinsCreedII.exe"

            executable.write_bytes(b"exe")

            (game_root / "UPlayBrowser.exe").write_bytes(b"browser")

            candidates = discover_game_candidates([library])

            self.assertEqual(
                len(candidates),
                1,
            )

            candidate = candidates[0]

            self.assertEqual(
                candidate.name,
                "Assassins Creed II",
            )

            self.assertEqual(
                candidate.root_directory,
                game_root,
            )

            self.assertEqual(
                candidate.executable,
                executable,
            )

            self.assertFalse(candidate.configurable)

    def test_ignores_technical_directories_during_discovery(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            library = Path(temp_directory)

            common_redist = library / "_CommonRedist"

            common_redist.mkdir()

            (common_redist / "oalinst.exe").write_bytes(b"installer")

            generate_interfaces = library / "release" / "tools" / "generate_interfaces"

            generate_interfaces.mkdir(parents=True)

            (generate_interfaces / "generate_interfaces_x64.exe").write_bytes(b"tool")

            lobby_connect = library / "release" / "tools" / "lobby_connect"

            lobby_connect.mkdir(parents=True)

            (lobby_connect / "lobby_connect_x64.exe").write_bytes(b"tool")

            steamclient = library / "release" / "steamclient_experimental"

            steamclient.mkdir(parents=True)

            (steamclient / "steamclient_loader_x64.exe").write_bytes(b"tool")

            candidates = discover_game_candidates([library])

            self.assertEqual(
                candidates,
                [],
            )

    def test_ignores_standalone_launcher_candidate(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            library = Path(temp_directory)

            launcher_root = library / "Tag Team Studio Sparking Launcher"

            launcher_root.mkdir()

            (launcher_root / "TagTeamStudioLauncher.exe").write_bytes(b"launcher")

            candidates = discover_game_candidates([library])

            self.assertEqual(
                candidates,
                [],
            )


if __name__ == "__main__":
    unittest.main()
