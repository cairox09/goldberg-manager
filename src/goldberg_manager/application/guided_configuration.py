from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class GameAssistantStatus:
    app_id: int | None
    app_id_confidence: int | None
    app_id_configured: bool
    backup_exists: bool
    backup_valid: bool
    steam_settings_exists: bool
    steam_interfaces_exists: bool
    gbe_configured: bool

    @property
    def ready(self) -> bool:
        return (
            self.app_id is not None
            and self.app_id_configured
            and self.backup_exists
            and self.backup_valid
            and self.steam_settings_exists
            and self.steam_interfaces_exists
            and self.gbe_configured
        )


def get_next_guided_step(
    status: GameAssistantStatus,
) -> str | None:
    if status.backup_exists and not status.backup_valid:
        return "blocked"

    if not status.gbe_configured:
        return "gbe"

    if not status.app_id_configured:
        return "appid"

    if not status.backup_exists:
        return "backup"

    if not status.steam_settings_exists:
        return "settings"

    if not status.steam_interfaces_exists:
        return "interfaces"

    return None
