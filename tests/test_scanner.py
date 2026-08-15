import tempfile
import unittest
from pathlib import Path

from goldberg_manager.scanner import detect_games, detect_generate_interfaces


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


if __name__ == "__main__":
    unittest.main()
