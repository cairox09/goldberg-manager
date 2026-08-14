import tempfile
import unittest
from pathlib import Path

from goldberg_manager.appid import (
    get_game_search_query,
    normalize_game_name,
    resolve_local_appid,
    search_game_on_steam,
    search_steam_store,
)
from goldberg_manager.scanner import Game


class AppIdResolverTests(unittest.TestCase):
    def _create_game(
        self,
        root: Path,
        name: str,
    ) -> Game:
        root.mkdir(
            parents=True,
            exist_ok=True,
        )

        executable = root / "re2.exe"

        steam_api = root / "steam_api64.dll"

        executable.write_bytes(b"game")
        steam_api.write_bytes(b"api")

        return Game(
            name=name,
            root_directory=root,
            executable=executable,
            steam_api=steam_api,
            steam_api_relative_path=Path("steam_api64.dll"),
            architecture="64-bit",
            source_directory=root,
        )

    def test_normalizes_detected_game_name(
        self,
    ) -> None:
        self.assertEqual(
            normalize_game_name("RESIDENT EVIL 2 Opti V4 FIX"),
            "resident evil 2",
        )

    def test_prefers_existing_steam_appid(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)

            game = self._create_game(
                root / "Resident Evil 2",
                "Resident Evil 2",
            )

            steam_settings = game.steam_api.parent / "steam_settings"

            steam_settings.mkdir()

            (steam_settings / "steam_appid.txt").write_text(
                "883710\n",
                encoding="utf-8",
            )

            candidates = resolve_local_appid(
                game,
                steam_roots=[],
            )

            self.assertEqual(
                len(candidates),
                1,
            )

            self.assertEqual(
                candidates[0].app_id,
                883710,
            )

            self.assertEqual(
                candidates[0].score,
                100,
            )

            self.assertEqual(
                candidates[0].source,
                "steam_appid.txt",
            )

    def test_detects_exact_steam_manifest(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)

            steam_root = root / "Steam"

            common = steam_root / "steamapps" / "common"

            game_root = common / "RESIDENT EVIL 2 BIOHAZARD RE2"

            game = self._create_game(
                game_root,
                "RESIDENT EVIL 2 BIOHAZARD RE2",
            )

            steamapps = steam_root / "steamapps"

            steamapps.mkdir(
                parents=True,
                exist_ok=True,
            )

            (steamapps / "appmanifest_883710.acf").write_text(
                '"AppState"\n'
                "{\n"
                '    "appid" "883710"\n'
                '    "name" '
                '"RESIDENT EVIL 2 / BIOHAZARD RE:2"\n'
                '    "installdir" '
                '"RESIDENT EVIL 2 BIOHAZARD RE2"\n'
                "}\n",
                encoding="utf-8",
            )

            candidates = resolve_local_appid(
                game,
                steam_roots=[steam_root],
            )

            self.assertTrue(candidates)

            self.assertEqual(
                candidates[0].app_id,
                883710,
            )

            self.assertEqual(
                candidates[0].score,
                100,
            )

    def test_matches_manifest_by_game_name(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)

            game = self._create_game(
                root / "Games" / "RE2",
                "RESIDENT EVIL 2 Opti V4 FIX",
            )

            steam_root = root / "Steam"

            steamapps = steam_root / "steamapps"

            steamapps.mkdir(
                parents=True,
                exist_ok=True,
            )

            (steamapps / "appmanifest_883710.acf").write_text(
                '"AppState"\n'
                "{\n"
                '    "appid" "883710"\n'
                '    "name" "Resident Evil 2"\n'
                '    "installdir" "Resident Evil 2"\n'
                "}\n",
                encoding="utf-8",
            )

            candidates = resolve_local_appid(
                game,
                steam_roots=[steam_root],
            )

            self.assertTrue(candidates)

            self.assertEqual(
                candidates[0].app_id,
                883710,
            )

            self.assertGreaterEqual(
                candidates[0].score,
                90,
            )

    def test_builds_clean_search_query(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)

            game = self._create_game(
                root / "RESIDENT EVIL 2 Opti V4 FIX",
                "RESIDENT EVIL 2 Opti V4 FIX",
            )

            self.assertEqual(
                get_game_search_query(game),
                "resident evil 2",
            )

    def test_searches_steam_store_results(
        self,
    ) -> None:
        html = """
        <html>
            <body>
                <a
                    class="search_result_row"
                    href="https://store.steampowered.com/app/883710/Resident_Evil_2/"
                >
                    <span class="title">
                        Resident Evil 2
                    </span>
                </a>

                <a
                    class="search_result_row"
                    href="https://store.steampowered.com/app/952060/Resident_Evil_3/"
                >
                    <span class="title">
                        Resident Evil 3
                    </span>
                </a>
            </body>
        </html>
        """

        requested_urls: list[str] = []

        def fake_fetcher(
            url: str,
        ) -> str:
            requested_urls.append(url)
            return html

        candidates = search_steam_store(
            "resident evil 2",
            fetcher=fake_fetcher,
        )

        self.assertTrue(requested_urls)

        self.assertEqual(
            candidates[0].app_id,
            883710,
        )

        self.assertEqual(
            candidates[0].name,
            "Resident Evil 2",
        )

        self.assertEqual(
            candidates[0].score,
            100,
        )

        self.assertEqual(
            candidates[0].source,
            "steam_store",
        )

    def test_searches_game_using_clean_name(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)

            game = self._create_game(
                root / "RESIDENT EVIL 2 Opti V4 FIX",
                "RESIDENT EVIL 2 Opti V4 FIX",
            )

            html = """
            <a
                href="https://store.steampowered.com/app/883710/Resident_Evil_2/"
            >
                <span class="title">
                    Resident Evil 2
                </span>
            </a>
            """

            requested_urls: list[str] = []

            def fake_fetcher(
                url: str,
            ) -> str:
                requested_urls.append(url)
                return html

            candidates = search_game_on_steam(
                game,
                fetcher=fake_fetcher,
            )

            self.assertEqual(
                candidates[0].app_id,
                883710,
            )

            self.assertIn(
                "resident+evil+2",
                requested_urls[0],
            )

    def test_deduplicates_store_results(
        self,
    ) -> None:
        html = """
        <a href="https://store.steampowered.com/app/883710/a/">
            <span class="title">
                Resident Evil 2
            </span>
        </a>

        <a href="https://store.steampowered.com/app/883710/b/">
            <span class="title">
                Resident Evil 2
            </span>
        </a>
        """

        candidates = search_steam_store(
            "Resident Evil 2",
            fetcher=lambda _: html,
        )

        self.assertEqual(
            len(candidates),
            1,
        )

        self.assertEqual(
            candidates[0].app_id,
            883710,
        )


if __name__ == "__main__":
    unittest.main()
