from __future__ import annotations

import unittest

from goldberg_manager.cli import (
    GameAssistantStatus,
    get_next_guided_step,
)


def make_status(
    *,
    app_id: int | None = 883710,
    app_id_configured: bool = True,
    backup_exists: bool = True,
    backup_valid: bool = True,
    steam_settings_exists: bool = True,
    steam_interfaces_exists: bool = True,
    gbe_configured: bool = True,
) -> GameAssistantStatus:
    return GameAssistantStatus(
        app_id=app_id,
        app_id_confidence=(100 if app_id is not None else None),
        app_id_configured=app_id_configured,
        backup_exists=backup_exists,
        backup_valid=backup_valid,
        steam_settings_exists=steam_settings_exists,
        steam_interfaces_exists=steam_interfaces_exists,
        gbe_configured=gbe_configured,
    )


class GuidedConfigurationTests(unittest.TestCase):
    def test_ready_game_has_no_next_step(
        self,
    ) -> None:
        status = make_status()

        self.assertIsNone(get_next_guided_step(status))

    def test_requires_gbe_first(
        self,
    ) -> None:
        status = make_status(gbe_configured=False)

        self.assertEqual(
            get_next_guided_step(status),
            "gbe",
        )

    def test_requires_configured_appid(
        self,
    ) -> None:
        status = make_status(app_id_configured=False)

        self.assertEqual(
            get_next_guided_step(status),
            "appid",
        )

    def test_requires_backup(
        self,
    ) -> None:
        status = make_status(
            backup_exists=False,
            backup_valid=False,
        )

        self.assertEqual(
            get_next_guided_step(status),
            "backup",
        )

    def test_blocks_corrupted_backup(
        self,
    ) -> None:
        status = make_status(
            backup_exists=True,
            backup_valid=False,
        )

        self.assertEqual(
            get_next_guided_step(status),
            "blocked",
        )

    def test_requires_steam_settings(
        self,
    ) -> None:
        status = make_status(steam_settings_exists=False)

        self.assertEqual(
            get_next_guided_step(status),
            "settings",
        )

    def test_requires_steam_interfaces(
        self,
    ) -> None:
        status = make_status(steam_interfaces_exists=False)

        self.assertEqual(
            get_next_guided_step(status),
            "interfaces",
        )


if __name__ == "__main__":
    unittest.main()
