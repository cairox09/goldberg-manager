from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from .core.game import Game
from .settings import (
    SteamSettingsSnapshot,
    read_game_steam_settings,
)

GSE_DEFAULT_SAVES_FOLDER_NAME = "GSE Saves"
GSE_SAVE_PATH_ENVIRONMENT_VARIABLE = "GseSavePath"


@dataclass(frozen=True, slots=True)
class GseSaveLocation:
    source: str
    root: Path
    app_id: int

    @property
    def app_directory(self) -> Path:
        return self.root / str(self.app_id)

    @property
    def achievements_path(self) -> Path:
        return self.app_directory / "achievements.json"

    @property
    def root_exists(self) -> bool:
        return self.root.is_dir()

    @property
    def app_directory_exists(self) -> bool:
        return self.app_directory.is_dir()

    @property
    def achievements_exists(self) -> bool:
        return self.achievements_path.is_file()


@dataclass(frozen=True, slots=True)
class GseSaveResolution:
    source: str
    raw_value: str | None
    locations: tuple[GseSaveLocation, ...]

    @property
    def runtime_locations(self) -> tuple[GseSaveLocation, ...]:
        return tuple(
            location for location in self.locations if location.app_directory_exists
        )

    @property
    def effective_locations(self) -> tuple[GseSaveLocation, ...]:
        if len(self.locations) == 1:
            return self.locations

        runtime_locations = self.runtime_locations
        return runtime_locations if len(runtime_locations) == 1 else ()

    @property
    def ambiguous(self) -> bool:
        return len(self.locations) > 1 and len(self.runtime_locations) != 1

    @property
    def resolved(self) -> bool:
        return bool(self.effective_locations)

    @property
    def runtime_found(self) -> bool:
        return bool(self.runtime_locations)

    @property
    def achievements_found(self) -> bool:
        return any(location.achievements_exists for location in self.locations)


def resolve_gse_linux_data_home(
    environment: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> Path:
    env = os.environ if environment is None else environment

    xdg_data_home = env.get("XDG_DATA_HOME")

    if xdg_data_home:
        return Path(xdg_data_home)

    user_home = Path.home() if home is None else home

    return user_home / ".local" / "share"


def discover_wine_appdata_roots(
    wine_drive_c_paths: tuple[Path, ...],
) -> tuple[Path, ...]:
    roots: list[Path] = []
    seen: set[Path] = set()

    for drive_c in wine_drive_c_paths:
        users_directory = drive_c / "users"

        discovered_for_drive: list[Path] = []

        try:
            user_directories = sorted(
                users_directory.iterdir(),
                key=lambda path: path.name.casefold(),
            )
        except OSError:
            user_directories = []

        for user_directory in user_directories:
            if not user_directory.is_dir():
                continue

            appdata = user_directory / "AppData" / "Roaming"

            if not appdata.is_dir():
                continue

            discovered_for_drive.append(
                appdata,
            )

        if not discovered_for_drive:
            discovered_for_drive.append(
                drive_c / "users" / "steamuser" / "AppData" / "Roaming"
            )

        for appdata in discovered_for_drive:
            normalized = Path(os.path.normpath(appdata))

            if normalized in seen:
                continue

            seen.add(normalized)
            roots.append(normalized)

    return tuple(roots)


def _windows_absolute_path(
    value: str,
) -> tuple[str, str] | None:
    if len(value) < 3:
        return None

    if not value[0].isalpha():
        return None

    if value[1] != ":":
        return None

    if value[2] not in ("\\", "/"):
        return None

    return (
        value[0].casefold(),
        value[3:],
    )


def _normalized_relative_path(
    value: str,
) -> Path:
    return Path(value.replace("\\", "/"))


def _resolve_configured_roots(
    value: str,
    *,
    windows_game: bool,
    relative_base: Path | None,
    wine_drive_c_paths: tuple[Path, ...],
) -> tuple[Path, ...]:
    stripped = value.strip()

    if not stripped:
        return ()

    if windows_game:
        windows_absolute = _windows_absolute_path(
            stripped,
        )

        if windows_absolute is not None:
            drive_letter, remainder = windows_absolute

            if drive_letter != "c":
                return ()

            relative = _normalized_relative_path(
                remainder,
            )

            return tuple(drive_c / relative for drive_c in wine_drive_c_paths)

        if stripped.startswith(("\\", "/")):
            relative = _normalized_relative_path(
                stripped.lstrip("\\/"),
            )

            return tuple(drive_c / relative for drive_c in wine_drive_c_paths)

        if relative_base is None:
            return ()

        return (relative_base / _normalized_relative_path(stripped),)

    path = Path(stripped)

    if path.is_absolute():
        return (path,)

    if relative_base is None:
        return ()

    return (relative_base / path,)


def _build_locations(
    source: str,
    roots: tuple[Path, ...],
    app_id: int,
) -> tuple[GseSaveLocation, ...]:
    locations: list[GseSaveLocation] = []
    seen: set[Path] = set()

    for root in roots:
        normalized_root = Path(os.path.normpath(root))

        if normalized_root in seen:
            continue

        seen.add(normalized_root)

        locations.append(
            GseSaveLocation(
                source=source,
                root=normalized_root,
                app_id=app_id,
            )
        )

    return tuple(locations)


def resolve_game_gse_saves(
    game: Game,
    app_id: int,
    *,
    settings: SteamSettingsSnapshot | None = None,
    environment: Mapping[str, str] | None = None,
    home: Path | None = None,
    cwd: Path | None = None,
    wine_drive_c_paths: tuple[Path, ...] = (),
) -> GseSaveResolution:
    if app_id <= 0:
        raise ValueError("O Steam AppID deve ser um número inteiro positivo.")

    env = os.environ if environment is None else environment

    snapshot = read_game_steam_settings(game) if settings is None else settings

    windows_game = game.steam_api.suffix.casefold() == ".dll"

    environment_save_path = env.get(GSE_SAVE_PATH_ENVIRONMENT_VARIABLE)

    if environment_save_path is not None and environment_save_path.strip():
        roots = _resolve_configured_roots(
            environment_save_path,
            windows_game=windows_game,
            relative_base=cwd,
            wine_drive_c_paths=wine_drive_c_paths,
        )

        return GseSaveResolution(
            source="GseSavePath",
            raw_value=environment_save_path,
            locations=_build_locations(
                "GseSavePath",
                roots,
                app_id,
            ),
        )

    if snapshot.local_save_path:
        roots = _resolve_configured_roots(
            snapshot.local_save_path,
            windows_game=windows_game,
            relative_base=game.steam_api.parent,
            wine_drive_c_paths=wine_drive_c_paths,
        )

        return GseSaveResolution(
            source="local_save_path",
            raw_value=snapshot.local_save_path,
            locations=_build_locations(
                "local_save_path",
                roots,
                app_id,
            ),
        )

    saves_folder_name = snapshot.saves_folder_name or GSE_DEFAULT_SAVES_FOLDER_NAME

    source = "saves_folder_name" if snapshot.saves_folder_name else "default"

    if windows_game:
        appdata_roots = discover_wine_appdata_roots(
            wine_drive_c_paths,
        )

        roots = tuple(appdata / saves_folder_name for appdata in appdata_roots)

    else:
        data_home = resolve_gse_linux_data_home(
            environment=env,
            home=home,
        )

        roots = (data_home / saves_folder_name,)

    return GseSaveResolution(
        source=source,
        raw_value=(snapshot.saves_folder_name if snapshot.saves_folder_name else None),
        locations=_build_locations(
            source,
            roots,
            app_id,
        ),
    )
