import tempfile
import unittest
from datetime import (
    UTC,
    datetime,
    timedelta,
)
from pathlib import Path

from goldberg_manager.appid import (
    AppIdCandidate,
)
from goldberg_manager.appid_cache import (
    get_cached_appid_search,
    save_appid_search_cache,
)


class AppIdCacheTests(unittest.TestCase):
    def test_saves_and_reads_cache(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            cache_path = Path(temp_directory) / "cache.json"

            now = datetime(
                2026,
                8,
                14,
                16,
                0,
                tzinfo=UTC,
            )

            candidates = [
                AppIdCandidate(
                    app_id=883710,
                    name="Resident Evil 2",
                    score=100,
                    source="steam_store",
                )
            ]

            save_appid_search_cache(
                "resident evil 2",
                candidates,
                cache_path=cache_path,
                now=now,
            )

            result = get_cached_appid_search(
                "Resident   Evil 2",
                cache_path=cache_path,
                now=now,
            )

            self.assertIsNotNone(result)

            assert result is not None

            self.assertEqual(
                len(result),
                1,
            )

            self.assertEqual(
                result[0].app_id,
                883710,
            )

    def test_expired_cache_is_ignored(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            cache_path = Path(temp_directory) / "cache.json"

            created_at = datetime(
                2026,
                8,
                1,
                tzinfo=UTC,
            )

            candidates = [
                AppIdCandidate(
                    app_id=883710,
                    name="Resident Evil 2",
                    score=100,
                    source="steam_store",
                )
            ]

            save_appid_search_cache(
                "resident evil 2",
                candidates,
                cache_path=cache_path,
                now=created_at,
            )

            result = get_cached_appid_search(
                "resident evil 2",
                cache_path=cache_path,
                now=(created_at + timedelta(days=8)),
            )

            self.assertIsNone(result)

    def test_corrupted_cache_is_ignored(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            cache_path = Path(temp_directory) / "cache.json"

            cache_path.write_text(
                "{invalid json",
                encoding="utf-8",
            )

            result = get_cached_appid_search(
                "resident evil 2",
                cache_path=cache_path,
            )

            self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
