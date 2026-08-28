from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from goldberg_manager.application.game_sentinel_repair import (
    apply_game_sentinel_repair,
    resolve_game_sentinel_repair,
)
from goldberg_manager.core.game import Game
from goldberg_manager.sentinel import SentinelConfigStatus
from goldberg_manager.sentinel_config_writer import (
    SentinelConfigWriteReason,
    SentinelConfigWriteResult,
    SentinelConfigWriteStatus,
)


def make_game() -> Game:
    root = Path("/games/Example")
    return Game(
        name="Example Game",
        root_directory=root,
        executable=root / "Game.exe",
        steam_api=root / "steam_api64.dll",
        steam_api_relative_path=Path("steam_api64.dll"),
        architecture="64-bit",
        source_directory=root.parent,
    )


def make_status() -> SentinelConfigStatus:
    return SentinelConfigStatus(
        path=Path("/config/sentinel/config.json"),
        exists=True,
        valid_json=True,
        schema_valid=True,
        prefix_paths=(),
        emulators=(),
    )


def make_write_result(
    status: SentinelConfigWriteStatus,
    reason: SentinelConfigWriteReason,
) -> SentinelConfigWriteResult:
    return SentinelConfigWriteResult(
        status=status,
        reason=reason,
        config_path=Path("/config/sentinel/config.json"),
    )


class GameSentinelRepairApplicationTests(unittest.TestCase):
    def test_resolve_game_sentinel_repair_uses_integration_coverage(self) -> None:
        game = make_game()
        coverage = object()
        integration = Mock(coverage=coverage)
        plan = object()

        with (
            patch(
                "goldberg_manager.application.game_sentinel_repair."
                "resolve_game_sentinel_integration",
                return_value=integration,
            ) as integration_resolver,
            patch(
                "goldberg_manager.application.game_sentinel_repair."
                "plan_sentinel_gse_repair",
                return_value=plan,
            ) as planner,
        ):
            resolved = resolve_game_sentinel_repair(game)

        self.assertIs(resolved, plan)
        integration_resolver.assert_called_once_with(
            game,
            sentinel_status=None,
        )
        planner.assert_called_once_with(coverage)

    def test_resolve_game_sentinel_repair_passes_optional_status(self) -> None:
        game = make_game()
        status = make_status()
        integration = Mock(coverage=object())

        with (
            patch(
                "goldberg_manager.application.game_sentinel_repair."
                "resolve_game_sentinel_integration",
                return_value=integration,
            ) as integration_resolver,
            patch(
                "goldberg_manager.application.game_sentinel_repair."
                "plan_sentinel_gse_repair",
                return_value=object(),
            ),
        ):
            resolve_game_sentinel_repair(
                game,
                sentinel_status=status,
            )

        integration_resolver.assert_called_once_with(
            game,
            sentinel_status=status,
        )

    def test_resolve_game_sentinel_repair_propagates_resolution_error(self) -> None:
        game = make_game()
        error = RuntimeError("resolution failed")

        with (
            patch(
                "goldberg_manager.application.game_sentinel_repair."
                "resolve_game_sentinel_integration",
                side_effect=error,
            ),
            patch(
                "goldberg_manager.application.game_sentinel_repair."
                "plan_sentinel_gse_repair",
            ) as planner,
            self.assertRaises(RuntimeError) as raised,
        ):
            resolve_game_sentinel_repair(game)

        self.assertIs(raised.exception, error)
        planner.assert_not_called()

    def test_apply_game_sentinel_repair_passes_exact_approved_plan_without_partial(
        self,
    ) -> None:
        game = make_game()
        approved_plan = object()
        write_result = make_write_result(
            SentinelConfigWriteStatus.NO_CHANGE,
            SentinelConfigWriteReason.ALREADY_CURRENT,
        )

        with patch(
            "goldberg_manager.application.game_sentinel_repair."
            "apply_sentinel_config_repair",
            return_value=write_result,
        ) as writer:
            outcome = apply_game_sentinel_repair(
                game,
                approved_plan,
                allow_partial=False,
            )

        writer.assert_called_once_with(
            approved_plan,
            allow_partial=False,
        )
        self.assertIs(outcome.write_result, write_result)

    def test_apply_game_sentinel_repair_passes_explicit_partial_authorization(
        self,
    ) -> None:
        game = make_game()
        approved_plan = object()
        write_result = make_write_result(
            SentinelConfigWriteStatus.REJECTED,
            SentinelConfigWriteReason.NO_SAFE_PREFIXES,
        )

        with patch(
            "goldberg_manager.application.game_sentinel_repair."
            "apply_sentinel_config_repair",
            return_value=write_result,
        ) as writer:
            apply_game_sentinel_repair(
                game,
                approved_plan,
                allow_partial=True,
            )

        writer.assert_called_once_with(
            approved_plan,
            allow_partial=True,
        )

    def test_apply_game_sentinel_repair_does_not_resolve_post_state_for_non_applied_result(
        self,
    ) -> None:
        game = make_game()
        write_result = make_write_result(
            SentinelConfigWriteStatus.CONFLICT,
            SentinelConfigWriteReason.CONCURRENT_MODIFICATION,
        )

        with (
            patch(
                "goldberg_manager.application.game_sentinel_repair."
                "apply_sentinel_config_repair",
                return_value=write_result,
            ),
            patch(
                "goldberg_manager.application.game_sentinel_repair."
                "resolve_game_sentinel_repair",
            ) as post_resolver,
        ):
            outcome = apply_game_sentinel_repair(
                game,
                object(),
                allow_partial=False,
            )

        post_resolver.assert_not_called()
        self.assertIs(outcome.write_result, write_result)
        self.assertIsNone(outcome.post_plan)
        self.assertIsNone(outcome.post_resolution_error)

    def test_apply_game_sentinel_repair_resolves_post_state_after_applied_result(
        self,
    ) -> None:
        game = make_game()
        write_result = make_write_result(
            SentinelConfigWriteStatus.APPLIED,
            SentinelConfigWriteReason.APPLIED,
        )
        post_plan = object()

        with (
            patch(
                "goldberg_manager.application.game_sentinel_repair."
                "apply_sentinel_config_repair",
                return_value=write_result,
            ),
            patch(
                "goldberg_manager.application.game_sentinel_repair."
                "resolve_game_sentinel_repair",
                return_value=post_plan,
            ) as post_resolver,
        ):
            outcome = apply_game_sentinel_repair(
                game,
                object(),
                allow_partial=False,
            )

        post_resolver.assert_called_once_with(game)
        self.assertIs(outcome.write_result, write_result)
        self.assertIs(outcome.post_plan, post_plan)
        self.assertIsNone(outcome.post_resolution_error)

    def test_apply_game_sentinel_repair_preserves_applied_result_when_post_resolution_fails(
        self,
    ) -> None:
        game = make_game()
        write_result = make_write_result(
            SentinelConfigWriteStatus.APPLIED,
            SentinelConfigWriteReason.APPLIED,
        )
        error = RuntimeError("post-resolution failed")

        with (
            patch(
                "goldberg_manager.application.game_sentinel_repair."
                "apply_sentinel_config_repair",
                return_value=write_result,
            ),
            patch(
                "goldberg_manager.application.game_sentinel_repair."
                "resolve_game_sentinel_repair",
                side_effect=error,
            ),
        ):
            outcome = apply_game_sentinel_repair(
                game,
                object(),
                allow_partial=False,
            )

        self.assertIs(outcome.write_result, write_result)
        self.assertIsNone(outcome.post_plan)
        self.assertIs(outcome.post_resolution_error, error)

    def test_apply_game_sentinel_repair_propagates_writer_exception(self) -> None:
        game = make_game()
        error = RuntimeError("writer failed")

        with (
            patch(
                "goldberg_manager.application.game_sentinel_repair."
                "apply_sentinel_config_repair",
                side_effect=error,
            ),
            patch(
                "goldberg_manager.application.game_sentinel_repair."
                "resolve_game_sentinel_repair",
            ) as post_resolver,
            self.assertRaises(RuntimeError) as raised,
        ):
            apply_game_sentinel_repair(
                game,
                object(),
                allow_partial=False,
            )

        self.assertIs(raised.exception, error)
        post_resolver.assert_not_called()


if __name__ == "__main__":
    unittest.main()
