from __future__ import annotations

from dataclasses import dataclass

from ..core.game import Game
from ..game_resolution import resolve_game_sentinel_integration
from ..sentinel import SentinelConfigStatus
from ..sentinel_config_writer import (
    SentinelConfigWriteResult,
    SentinelConfigWriteStatus,
    apply_sentinel_config_repair,
)
from ..sentinel_repair import SentinelRepairPlan, plan_sentinel_gse_repair


@dataclass(frozen=True, slots=True)
class GameSentinelRepairOutcome:
    write_result: SentinelConfigWriteResult
    post_plan: SentinelRepairPlan | None = None
    post_resolution_error: Exception | None = None


def resolve_game_sentinel_repair(
    game: Game,
    *,
    sentinel_status: SentinelConfigStatus | None = None,
) -> SentinelRepairPlan:
    integration = resolve_game_sentinel_integration(
        game,
        sentinel_status=sentinel_status,
    )
    return plan_sentinel_gse_repair(integration.coverage)


def apply_game_sentinel_repair(
    game: Game,
    approved_plan: SentinelRepairPlan,
    *,
    allow_partial: bool,
) -> GameSentinelRepairOutcome:
    write_result = apply_sentinel_config_repair(
        approved_plan,
        allow_partial=allow_partial,
    )

    if write_result.status is not SentinelConfigWriteStatus.APPLIED:
        return GameSentinelRepairOutcome(write_result=write_result)

    try:
        post_plan = resolve_game_sentinel_repair(game)
    except Exception as error:  # noqa: BLE001 - post-write feedback remains nonfatal
        return GameSentinelRepairOutcome(
            write_result=write_result,
            post_resolution_error=error,
        )

    return GameSentinelRepairOutcome(
        write_result=write_result,
        post_plan=post_plan,
    )
