from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .achievements import (
    AchievementDataError,
    AchievementReport,
    read_achievement_report,
)
from .appid import AppIdCandidate, resolve_local_appid
from .core.game import Game
from .gse_saves import GseSaveResolution, resolve_game_gse_saves
from .sentinel import (
    SentinelConfigStatus,
    SentinelDriveC,
    SentinelInstallation,
    detect_sentinel,
    discover_sentinel_drive_c_paths,
    read_sentinel_config,
)
from .sentinel_integration import (
    SentinelGseCoverage,
    resolve_sentinel_gse_coverage,
)
from .settings import (
    SteamSettingsSnapshot,
    read_game_steam_settings,
)


@dataclass(frozen=True, slots=True)
class GameGseResolution:
    app_id: int | None
    app_id_confidence: int | None
    app_id_source: str | None
    save_resolution: GseSaveResolution | None

    @property
    def resolved(self) -> bool:
        return self.save_resolution is not None and self.save_resolution.resolved

    @property
    def runtime_found(self) -> bool:
        return self.save_resolution is not None and self.save_resolution.runtime_found

    @property
    def achievements_found(self) -> bool:
        return (
            self.save_resolution is not None and self.save_resolution.achievements_found
        )


@dataclass(frozen=True, slots=True)
class GameSentinelIntegrationResolution:
    gse_resolution: GameGseResolution
    coverage: SentinelGseCoverage


@dataclass(frozen=True, slots=True)
class AchievementReadError:
    path: Path
    message: str


@dataclass(frozen=True, slots=True)
class GameAchievementResolution:
    gse_resolution: GameGseResolution
    metadata_path: Path
    language: str
    runtime_paths: tuple[Path, ...]
    reports: tuple[AchievementReport, ...]
    errors: tuple[AchievementReadError, ...]

    @property
    def metadata_exists(self) -> bool:
        return self.metadata_path.is_file()

    @property
    def runtime_resolved(self) -> bool:
        return self.gse_resolution.resolved


def resolve_game_gse_runtime(
    game: Game,
    *,
    sentinel_status: SentinelConfigStatus | None = None,
    settings: SteamSettingsSnapshot | None = None,
    sentinel_drive_cs: tuple[SentinelDriveC, ...] | None = None,
    sentinel_detector: Callable[[], SentinelInstallation] | None = None,
    sentinel_config_reader: Callable[[Path], SentinelConfigStatus] | None = None,
    drive_c_discoverer: Callable[[tuple[Path, ...]], tuple[SentinelDriveC, ...]]
    | None = None,
    app_id_resolver: Callable[[Game], list[AppIdCandidate]] | None = None,
    settings_reader: Callable[[Game], SteamSettingsSnapshot] | None = None,
    save_resolver: Callable[..., GseSaveResolution] | None = None,
) -> GameGseResolution:
    if sentinel_detector is None:
        sentinel_detector = detect_sentinel
    if sentinel_config_reader is None:
        sentinel_config_reader = read_sentinel_config
    if drive_c_discoverer is None:
        drive_c_discoverer = discover_sentinel_drive_c_paths
    if app_id_resolver is None:
        app_id_resolver = resolve_local_appid
    if settings_reader is None:
        settings_reader = read_game_steam_settings
    if save_resolver is None:
        save_resolver = resolve_game_gse_saves

    if sentinel_status is None:
        installation = sentinel_detector()
        sentinel_status = sentinel_config_reader(installation.config_path)

    if sentinel_drive_cs is None:
        sentinel_drive_cs = drive_c_discoverer(sentinel_status.prefix_paths)

    wine_drive_c_paths = tuple(discovered.drive_c for discovered in sentinel_drive_cs)
    app_id_candidates = app_id_resolver(game)

    if not app_id_candidates:
        return GameGseResolution(
            app_id=None,
            app_id_confidence=None,
            app_id_source=None,
            save_resolution=None,
        )

    snapshot = settings_reader(game) if settings is None else settings
    fallback: GameGseResolution | None = None
    runtime_match: GameGseResolution | None = None

    for candidate in app_id_candidates:
        save_resolution = save_resolver(
            game,
            candidate.app_id,
            settings=snapshot,
            wine_drive_c_paths=wine_drive_c_paths,
        )
        current = GameGseResolution(
            app_id=candidate.app_id,
            app_id_confidence=candidate.score,
            app_id_source=candidate.source,
            save_resolution=save_resolution,
        )

        if fallback is None:
            fallback = current

        if save_resolution.achievements_found:
            return current

        if save_resolution.runtime_found and runtime_match is None:
            runtime_match = current

    if runtime_match is not None:
        return runtime_match

    assert fallback is not None
    return fallback


def resolve_game_sentinel_integration(
    game: Game,
    *,
    sentinel_status: SentinelConfigStatus | None = None,
    gse_resolution: GameGseResolution | None = None,
    sentinel_detector: Callable[[], SentinelInstallation] | None = None,
    sentinel_config_reader: Callable[[Path], SentinelConfigStatus] | None = None,
    gse_resolver: Callable[..., GameGseResolution] | None = None,
    coverage_resolver: Callable[
        [SentinelConfigStatus, int | None, GseSaveResolution | None],
        SentinelGseCoverage,
    ]
    | None = None,
) -> GameSentinelIntegrationResolution:
    if sentinel_detector is None:
        sentinel_detector = detect_sentinel
    if sentinel_config_reader is None:
        sentinel_config_reader = read_sentinel_config
    if gse_resolver is None:
        gse_resolver = resolve_game_gse_runtime
    if coverage_resolver is None:
        coverage_resolver = resolve_sentinel_gse_coverage

    if sentinel_status is None:
        installation = sentinel_detector()
        sentinel_status = sentinel_config_reader(installation.config_path)

    if gse_resolution is None:
        gse_resolution = gse_resolver(
            game,
            sentinel_status=sentinel_status,
        )

    coverage = coverage_resolver(
        sentinel_status,
        gse_resolution.app_id,
        gse_resolution.save_resolution,
    )

    return GameSentinelIntegrationResolution(
        gse_resolution=gse_resolution,
        coverage=coverage,
    )


def resolve_game_achievement_progress(
    game: Game,
    *,
    sentinel_status: SentinelConfigStatus | None = None,
    gse_resolution: GameGseResolution | None = None,
    settings: SteamSettingsSnapshot | None = None,
    gse_resolver: Callable[..., GameGseResolution] | None = None,
    settings_reader: Callable[[Game], SteamSettingsSnapshot] | None = None,
    achievement_reader: Callable[..., AchievementReport] | None = None,
) -> GameAchievementResolution:
    if gse_resolver is None:
        gse_resolver = resolve_game_gse_runtime
    if settings_reader is None:
        settings_reader = read_game_steam_settings
    if achievement_reader is None:
        achievement_reader = read_achievement_report

    if gse_resolution is None:
        gse_resolution = gse_resolver(
            game,
            sentinel_status=sentinel_status,
        )

    snapshot = settings_reader(game) if settings is None else settings
    language = snapshot.language or "english"
    metadata_path = game.steam_api.parent / "steam_settings" / "achievements.json"
    save_resolution = gse_resolution.save_resolution
    runtime_paths = (
        tuple(
            location.achievements_path
            for location in save_resolution.locations
            if location.achievements_exists
        )
        if save_resolution is not None
        else ()
    )

    if not metadata_path.is_file():
        return GameAchievementResolution(
            gse_resolution=gse_resolution,
            metadata_path=metadata_path,
            language=language,
            runtime_paths=runtime_paths,
            reports=(),
            errors=(),
        )

    try:
        metadata_report = achievement_reader(
            metadata_path,
            language=language,
        )
    except AchievementDataError as error:
        return GameAchievementResolution(
            gse_resolution=gse_resolution,
            metadata_path=metadata_path,
            language=language,
            runtime_paths=runtime_paths,
            reports=(),
            errors=(
                AchievementReadError(
                    path=metadata_path,
                    message=str(error),
                ),
            ),
        )

    if not runtime_paths:
        return GameAchievementResolution(
            gse_resolution=gse_resolution,
            metadata_path=metadata_path,
            language=language,
            runtime_paths=(),
            reports=(metadata_report,),
            errors=(),
        )

    reports: list[AchievementReport] = []
    errors: list[AchievementReadError] = []

    for runtime_path in runtime_paths:
        try:
            reports.append(
                achievement_reader(
                    metadata_path,
                    runtime_path,
                    language=language,
                )
            )
        except AchievementDataError as error:
            errors.append(
                AchievementReadError(
                    path=runtime_path,
                    message=str(error),
                )
            )

    return GameAchievementResolution(
        gse_resolution=gse_resolution,
        metadata_path=metadata_path,
        language=language,
        runtime_paths=runtime_paths,
        reports=tuple(reports),
        errors=tuple(errors),
    )
