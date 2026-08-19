from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from goldberg_manager.achievements import (
    AchievementDataError,
    read_achievement_report,
)


class AchievementReportTests(unittest.TestCase):
    def write_json(
        self,
        path: Path,
        payload: object,
    ) -> None:
        path.write_text(
            json.dumps(payload),
            encoding="utf-8",
        )

    def make_metadata(
        self,
        root: Path,
        achievements: list[dict[str, object]] | None = None,
    ) -> Path:
        metadata_path = root / "metadata.json"

        self.write_json(
            metadata_path,
            achievements
            if achievements is not None
            else [
                {
                    "name": "ACH_ONE",
                    "displayName": "First achievement",
                    "description": "Complete the first objective",
                    "hidden": 0,
                },
                {
                    "name": "ACH_TWO",
                    "displayName": "Second achievement",
                    "description": "Complete the second objective",
                    "hidden": 1,
                },
            ],
        )

        return metadata_path

    def test_without_runtime_all_achievements_are_locked(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            metadata_path = self.make_metadata(Path(temp_directory))

            report = read_achievement_report(metadata_path)

            self.assertEqual(report.total, 2)
            self.assertEqual(report.unlocked, 0)
            self.assertEqual(report.locked, 2)
            self.assertEqual(report.partial, 0)
            self.assertEqual(report.completion_percentage, 0.0)
            self.assertTrue(all(status.locked for status in report.achievements))
            self.assertTrue(report.achievements[1].definition.hidden)

            status = report.achievements[0]

            self.assertIsNone(status.runtime)
            self.assertFalse(status.earned)
            self.assertTrue(status.locked)
            self.assertIsNone(status.earned_time)
            self.assertIsNone(status.progress)
            self.assertIsNone(status.max_progress)
            self.assertFalse(status.partial)
            self.assertEqual(status.progress_percentage, 0.0)

    def test_reads_string_hidden_flags(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            metadata_path = self.make_metadata(
                root,
                [
                    {
                        "name": "ACH_HIDDEN",
                        "hidden": "1",
                    },
                    {
                        "name": "ACH_VISIBLE",
                        "hidden": "0",
                    },
                ],
            )

            report = read_achievement_report(metadata_path)

            self.assertTrue(report.achievements[0].definition.hidden)
            self.assertFalse(report.achievements[1].definition.hidden)

    def test_reads_unlocked_achievement_and_earned_time(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            metadata_path = self.make_metadata(root)
            runtime_path = root / "runtime.json"

            self.write_json(
                runtime_path,
                {
                    "ACH_ONE": {
                        "earned": True,
                        "earned_time": 1_725_000_000,
                    }
                },
            )

            report = read_achievement_report(metadata_path, runtime_path)
            status = report.achievements[0]

            self.assertTrue(status.earned)
            self.assertFalse(status.locked)
            self.assertEqual(status.earned_time, 1_725_000_000)
            self.assertEqual(status.progress_percentage, 100.0)
            self.assertEqual(report.unlocked, 1)
            self.assertEqual(report.locked, 1)
            self.assertEqual(report.completion_percentage, 50.0)

    def test_reads_partial_progress(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            metadata_path = self.make_metadata(root)
            runtime_path = root / "runtime.json"

            self.write_json(
                runtime_path,
                {
                    "ACH_ONE": {
                        "earned": False,
                        "progress": 3,
                        "max_progress": 10,
                    }
                },
            )

            report = read_achievement_report(metadata_path, runtime_path)
            status = report.achievements[0]

            self.assertTrue(status.partial)
            self.assertEqual(status.progress, 3)
            self.assertEqual(status.max_progress, 10)
            self.assertEqual(status.progress_percentage, 30.0)
            self.assertEqual(report.partial, 1)

    def test_unlocked_achievement_is_not_partial(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            metadata_path = self.make_metadata(root)
            runtime_path = root / "runtime.json"

            self.write_json(
                runtime_path,
                {
                    "ACH_ONE": {
                        "earned": True,
                        "progress": 10,
                        "max_progress": 10,
                    }
                },
            )

            report = read_achievement_report(metadata_path, runtime_path)

            self.assertFalse(report.achievements[0].partial)
            self.assertEqual(report.partial, 0)

    def test_partial_requires_progress_strictly_below_positive_maximum(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            names = (
                "ACH_NO_MAX",
                "ACH_ZERO_MAX",
                "ACH_AT_MAX",
                "ACH_OVER_MAX",
            )
            metadata_path = self.make_metadata(
                root,
                [{"name": name} for name in names],
            )
            runtime_path = root / "runtime.json"

            self.write_json(
                runtime_path,
                {
                    "ACH_NO_MAX": {
                        "progress": 1,
                    },
                    "ACH_ZERO_MAX": {
                        "progress": 1,
                        "max_progress": 0,
                    },
                    "ACH_AT_MAX": {
                        "progress": 10,
                        "max_progress": 10,
                    },
                    "ACH_OVER_MAX": {
                        "progress": 11,
                        "max_progress": 10,
                    },
                },
            )

            report = read_achievement_report(metadata_path, runtime_path)

            self.assertEqual(report.partial, 0)

            for status in report.achievements:
                with self.subTest(name=status.definition.name):
                    self.assertFalse(status.partial)

    def test_uses_requested_language(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            metadata_path = self.make_metadata(
                root,
                [
                    {
                        "name": "ACH_ONE",
                        "displayName": {
                            "english": "First achievement",
                            "brazilian": "Primeira conquista",
                        },
                        "description": {
                            "english": "Complete the objective",
                            "brazilian": "Complete o objetivo",
                        },
                    }
                ],
            )

            report = read_achievement_report(
                metadata_path,
                language="brazilian",
            )
            definition = report.achievements[0].definition

            self.assertEqual(definition.display_name, "Primeira conquista")
            self.assertEqual(definition.description, "Complete o objetivo")

    def test_falls_back_to_english(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            metadata_path = self.make_metadata(
                root,
                [
                    {
                        "name": "ACH_ONE",
                        "displayName": {
                            "token": "#ACH_ONE_NAME",
                            "french": "Première réussite",
                            "english": "First achievement",
                        },
                        "description": {
                            "english": "Complete the objective",
                        },
                    }
                ],
            )

            report = read_achievement_report(
                metadata_path,
                language="brazilian",
            )
            definition = report.achievements[0].definition

            self.assertEqual(definition.display_name, "First achievement")
            self.assertEqual(definition.description, "Complete the objective")

    def test_existing_empty_requested_language_precedes_english(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            metadata_path = self.make_metadata(
                root,
                [
                    {
                        "name": "ACH_ONE",
                        "displayName": {
                            "brazilian": "",
                            "english": "First achievement",
                        },
                        "description": {
                            "brazilian": "",
                            "english": "Complete the objective",
                        },
                    }
                ],
            )

            report = read_achievement_report(
                metadata_path,
                language="brazilian",
            )
            definition = report.achievements[0].definition

            self.assertEqual(definition.display_name, "ACH_ONE")
            self.assertEqual(definition.description, "")

    def test_falls_back_to_first_language_before_token(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            metadata_path = self.make_metadata(
                root,
                [
                    {
                        "name": "ACH_ONE",
                        "displayName": {
                            "token": "#ACH_ONE_NAME",
                            "french": "Première réussite",
                        },
                        "description": {
                            "token": "#ACH_ONE_DESC",
                        },
                    }
                ],
            )

            report = read_achievement_report(
                metadata_path,
                language="brazilian",
            )
            definition = report.achievements[0].definition

            self.assertEqual(definition.display_name, "Première réussite")
            self.assertEqual(definition.description, "#ACH_ONE_DESC")

    def test_rejects_invalid_earned_times(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            names = (
                "ACH_FLOAT",
                "ACH_NEGATIVE",
                "ACH_BOOL",
                "ACH_ZERO",
            )
            metadata_path = self.make_metadata(
                root,
                [{"name": name} for name in names],
            )
            runtime_path = root / "runtime.json"

            self.write_json(
                runtime_path,
                {
                    "ACH_FLOAT": {
                        "earned_time": 123.9,
                    },
                    "ACH_NEGATIVE": {
                        "earned_time": -1,
                    },
                    "ACH_BOOL": {
                        "earned_time": True,
                    },
                    "ACH_ZERO": {
                        "earned_time": 0,
                    },
                },
            )

            report = read_achievement_report(metadata_path, runtime_path)

            self.assertIsNone(report.achievements[0].earned_time)
            self.assertIsNone(report.achievements[1].earned_time)
            self.assertIsNone(report.achievements[2].earned_time)
            self.assertEqual(report.achievements[3].earned_time, 0)

    def test_matches_runtime_case_insensitively(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            metadata_path = self.make_metadata(root)
            runtime_path = root / "runtime.json"

            self.write_json(
                runtime_path,
                {
                    "ach_one": {
                        "earned": True,
                    }
                },
            )

            report = read_achievement_report(metadata_path, runtime_path)

            self.assertTrue(report.achievements[0].earned)
            runtime = report.achievements[0].runtime

            self.assertIsNotNone(runtime)
            self.assertEqual(runtime.name, "ach_one")
            self.assertEqual(report.unknown_runtime_names, ())

    def test_preserves_unknown_runtime_names(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            metadata_path = self.make_metadata(root)
            runtime_path = root / "runtime.json"

            self.write_json(
                runtime_path,
                {
                    "ACH_UNKNOWN": {
                        "earned": True,
                    },
                    "another_unknown": {
                        "earned": False,
                    },
                },
            )

            report = read_achievement_report(metadata_path, runtime_path)

            self.assertEqual(
                report.unknown_runtime_names,
                ("ACH_UNKNOWN", "another_unknown"),
            )

    def test_rejects_invalid_metadata_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            metadata_path = Path(temp_directory) / "metadata.json"
            self.write_json(metadata_path, {})

            with self.assertRaisesRegex(
                AchievementDataError,
                "metadata de achievements não é uma lista",
            ):
                read_achievement_report(metadata_path)

    def test_rejects_invalid_runtime_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            metadata_path = self.make_metadata(root)
            runtime_path = root / "runtime.json"
            self.write_json(runtime_path, [])

            with self.assertRaisesRegex(
                AchievementDataError,
                "runtime de achievements não é um objeto",
            ):
                read_achievement_report(metadata_path, runtime_path)


if __name__ == "__main__":
    unittest.main()
