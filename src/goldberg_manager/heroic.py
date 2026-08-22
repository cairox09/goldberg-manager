from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from .core.game import Game

_SIDELOAD_LIBRARY = Path("sideload_apps/library.json")
_LEGENDARY_INSTALLED = Path("legendaryConfig/legendary/installed.json")
_GOG_INSTALLED = Path("gog_store/installed.json")
_NILE_INSTALLED = Path("nile_config/nile/installed.json")
_WINDOWS_ABSOLUTE_PATH = re.compile(r"^[A-Za-z]:[\\/]")


class HeroicPrefixLayout(str, Enum):
    DIRECT = "direct"
    PFX_SUBDIRECTORY = "pfx-subdirectory"
    MISSING = "missing"
    UNRESOLVED = "unresolved"
    AMBIGUOUS = "ambiguous"


class HeroicMatchEvidence(str, Enum):
    EXACT_EXECUTABLE_PATH = "exact-executable-path"
    GAME_ROOT_EQUALS_INSTALL_PATH = "game-root-equals-install-path"
    EXECUTABLE_AND_STEAM_API_WITHIN_INSTALL_PATH = (
        "executable-and-steam-api-within-install-path"
    )
    EXECUTABLE_WITHIN_INSTALL_PATH = "executable-within-install-path"
    STEAM_API_WITHIN_INSTALL_PATH = "steam-api-within-install-path"


class HeroicProvenanceStatus(str, Enum):
    RESOLVED = "resolved"
    AMBIGUOUS = "ambiguous"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class HeroicGameId:
    runner: str
    app_name: str


@dataclass(frozen=True, slots=True)
class HeroicInstalledGame:
    id: HeroicGameId
    install_path: Path
    executable: Path | None
    platform: str | None
    source_path: Path


@dataclass(frozen=True, slots=True)
class HeroicGameConfig:
    configured_prefix: Path | None
    wine_version_name: str | None
    wine_version_type: str | None
    wine_binary: Path | None
    target_exe: Path | None
    explicit: bool | None
    source_path: Path


@dataclass(frozen=True, slots=True)
class HeroicPrefixState:
    configured_prefix: Path | None
    structural_wine_prefix: Path | None
    drive_c: Path | None
    layout: HeroicPrefixLayout


@dataclass(frozen=True, slots=True)
class HeroicReadError:
    path: Path
    message: str


@dataclass(frozen=True, slots=True)
class HeroicInstalledGames:
    config_root: Path
    config_exists: bool
    games: tuple[HeroicInstalledGame, ...]
    errors: tuple[HeroicReadError, ...]


@dataclass(frozen=True, slots=True)
class HeroicGameMatch:
    installed_game: HeroicInstalledGame
    config: HeroicGameConfig | None
    prefix: HeroicPrefixState
    evidences: tuple[HeroicMatchEvidence, ...]


@dataclass(frozen=True, slots=True)
class HeroicGameProvenance:
    config_root: Path
    status: HeroicProvenanceStatus
    candidates: tuple[HeroicGameMatch, ...]
    effective: HeroicGameMatch | None
    strongest_evidence: HeroicMatchEvidence | None
    errors: tuple[HeroicReadError, ...]

    def __post_init__(self) -> None:
        resolved = self.status is HeroicProvenanceStatus.RESOLVED

        if resolved != (self.effective is not None):
            raise ValueError("Resolved Heroic provenance requires one effective match.")
        if self.effective is not None and self.effective not in self.candidates:
            raise ValueError("The effective Heroic match must be a candidate.")

    @property
    def resolved(self) -> bool:
        return self.status is HeroicProvenanceStatus.RESOLVED

    @property
    def ambiguous(self) -> bool:
        return self.status is HeroicProvenanceStatus.AMBIGUOUS

    @property
    def unknown(self) -> bool:
        return self.status is HeroicProvenanceStatus.UNKNOWN


def _normalize_lexical_path(path: Path) -> Path:
    return Path(os.path.normpath(os.path.abspath(path.expanduser())))


def _is_windows_absolute_path(value: str) -> bool:
    return _WINDOWS_ABSOLUTE_PATH.match(value) is not None


def _unix_path(
    value: object,
    *,
    relative_base: Path | None = None,
) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        return None

    stripped = value.strip()
    if "\x00" in stripped or _is_windows_absolute_path(stripped):
        return None

    path = Path(stripped).expanduser()
    if relative_base is not None and not path.is_absolute():
        path = relative_base / path

    return _normalize_lexical_path(path)


def _safe_app_name(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None

    app_name = value.strip()
    if (
        app_name in {".", ".."}
        or "\x00" in app_name
        or "/" in app_name
        or "\\" in app_name
    ):
        return None

    return app_name


def _optional_string(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    return value.strip() or None


def _read_json(path: Path) -> tuple[object | None, HeroicReadError | None]:
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None, HeroicReadError(path=path, message="Invalid Heroic JSON.")
    except OSError:
        return None, HeroicReadError(
            path=path, message="Could not read Heroic metadata."
        )


def _required_install_path(
    value: object,
    path: Path,
    errors: list[HeroicReadError],
) -> Path | None:
    install_path = _unix_path(value)
    if install_path is None:
        errors.append(
            HeroicReadError(path=path, message="Invalid Heroic install path.")
        )
    return install_path


def _optional_executable(
    value: object,
    *,
    install_path: Path,
    path: Path,
    allow_relative: bool,
    errors: list[HeroicReadError],
) -> Path | None:
    if value is None or value == "":
        return None
    if (
        not isinstance(value, str)
        or "\x00" in value
        or _is_windows_absolute_path(value.strip())
    ):
        errors.append(
            HeroicReadError(path=path, message="Unsupported Heroic executable path.")
        )
        return None

    raw_path = Path(value.strip()).expanduser()
    if not raw_path.is_absolute() and not allow_relative:
        errors.append(
            HeroicReadError(path=path, message="Unsupported relative executable path.")
        )
        return None

    executable = _unix_path(
        value,
        relative_base=install_path if allow_relative else None,
    )
    if executable is None:
        return None

    if not raw_path.is_absolute() and not _is_lexically_within(
        executable,
        install_path,
    ):
        errors.append(
            HeroicReadError(
                path=path, message="Heroic executable escapes install path."
            )
        )
        return None

    return executable


def _read_sideload_games(
    path: Path,
) -> tuple[list[HeroicInstalledGame], list[HeroicReadError]]:
    payload, read_error = _read_json(path)
    if read_error is not None:
        return [], [read_error]
    if not isinstance(payload, dict) or not isinstance(payload.get("games"), list):
        return [], [HeroicReadError(path=path, message="Invalid sideload registry.")]

    games: list[HeroicInstalledGame] = []
    errors: list[HeroicReadError] = []

    for entry in payload["games"]:
        if not isinstance(entry, dict) or entry.get("is_installed") is not True:
            continue
        if entry.get("runner") != "sideload":
            errors.append(
                HeroicReadError(path=path, message="Invalid sideload runner.")
            )
            continue

        app_name = _safe_app_name(entry.get("app_name"))
        install_path = _required_install_path(entry.get("folder_name"), path, errors)
        install = entry.get("install")

        if app_name is None or install_path is None or not isinstance(install, dict):
            if app_name is None or not isinstance(install, dict):
                errors.append(
                    HeroicReadError(path=path, message="Invalid sideload game entry.")
                )
            continue
        if install.get("is_dlc") is True:
            continue

        executable = _optional_executable(
            install.get("executable"),
            install_path=install_path,
            path=path,
            allow_relative=False,
            errors=errors,
        )
        games.append(
            HeroicInstalledGame(
                id=HeroicGameId(runner="sideload", app_name=app_name),
                install_path=install_path,
                executable=executable,
                platform=_optional_string(install.get("platform")),
                source_path=path,
            )
        )

    return games, errors


def _read_legendary_games(
    path: Path,
) -> tuple[list[HeroicInstalledGame], list[HeroicReadError]]:
    payload, read_error = _read_json(path)
    if read_error is not None:
        return [], [read_error]
    if not isinstance(payload, dict):
        return [], [HeroicReadError(path=path, message="Invalid Legendary registry.")]

    games: list[HeroicInstalledGame] = []
    errors: list[HeroicReadError] = []

    for key, entry in payload.items():
        if not isinstance(entry, dict):
            errors.append(
                HeroicReadError(path=path, message="Invalid Legendary game entry.")
            )
            continue
        if entry.get("is_dlc") is True:
            continue

        app_name = _safe_app_name(entry.get("app_name", key))
        if app_name is None or ("app_name" in entry and entry["app_name"] != key):
            errors.append(
                HeroicReadError(path=path, message="Invalid Legendary game identity.")
            )
            continue

        install_path = _required_install_path(entry.get("install_path"), path, errors)
        if install_path is None:
            continue

        games.append(
            HeroicInstalledGame(
                id=HeroicGameId(runner="legendary", app_name=app_name),
                install_path=install_path,
                executable=_optional_executable(
                    entry.get("executable"),
                    install_path=install_path,
                    path=path,
                    allow_relative=True,
                    errors=errors,
                ),
                platform=_optional_string(entry.get("platform")),
                source_path=path,
            )
        )

    return games, errors


def _read_gog_games(
    path: Path,
) -> tuple[list[HeroicInstalledGame], list[HeroicReadError]]:
    payload, read_error = _read_json(path)
    if read_error is not None:
        return [], [read_error]
    if not isinstance(payload, dict) or not isinstance(payload.get("installed"), list):
        return [], [HeroicReadError(path=path, message="Invalid GOG registry.")]

    games: list[HeroicInstalledGame] = []
    errors: list[HeroicReadError] = []

    for entry in payload["installed"]:
        if not isinstance(entry, dict):
            errors.append(HeroicReadError(path=path, message="Invalid GOG game entry."))
            continue
        if entry.get("is_dlc") is True:
            continue

        app_name = _safe_app_name(entry.get("appName"))
        install_path = _required_install_path(entry.get("install_path"), path, errors)
        platform = _optional_string(entry.get("platform"))

        if (
            app_name is None
            or install_path is None
            or platform not in {"windows", "linux", "osx"}
        ):
            if app_name is None or platform not in {"windows", "linux", "osx"}:
                errors.append(
                    HeroicReadError(path=path, message="Invalid GOG game entry.")
                )
            continue

        games.append(
            HeroicInstalledGame(
                id=HeroicGameId(runner="gog", app_name=app_name),
                install_path=install_path,
                executable=None,
                platform=platform,
                source_path=path,
            )
        )

    return games, errors


def _read_nile_games(
    path: Path,
) -> tuple[list[HeroicInstalledGame], list[HeroicReadError]]:
    payload, read_error = _read_json(path)
    if read_error is not None:
        return [], [read_error]
    if not isinstance(payload, list):
        return [], [HeroicReadError(path=path, message="Invalid Nile registry.")]

    games: list[HeroicInstalledGame] = []
    errors: list[HeroicReadError] = []

    for entry in payload:
        if not isinstance(entry, dict):
            errors.append(
                HeroicReadError(path=path, message="Invalid Nile game entry.")
            )
            continue

        app_name = _safe_app_name(entry.get("id"))
        install_path = _required_install_path(entry.get("path"), path, errors)
        version = _optional_string(entry.get("version"))

        if app_name is None or install_path is None or version is None:
            if app_name is None or version is None:
                errors.append(
                    HeroicReadError(path=path, message="Invalid Nile game entry.")
                )
            continue

        games.append(
            HeroicInstalledGame(
                id=HeroicGameId(runner="nile", app_name=app_name),
                install_path=install_path,
                executable=None,
                platform="Windows",
                source_path=path,
            )
        )

    return games, errors


def get_heroic_config_root(
    *,
    config_root: Path | None = None,
    environment: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> Path:
    if config_root is not None:
        return _normalize_lexical_path(config_root)

    env = os.environ if environment is None else environment
    xdg_config_home = env.get("XDG_CONFIG_HOME")
    if xdg_config_home is not None and xdg_config_home.strip():
        base = Path(xdg_config_home.strip())
    else:
        user_home = Path.home() if home is None else home
        base = user_home / ".config"

    return _normalize_lexical_path(base / "heroic")


def discover_heroic_installed_games(
    *,
    config_root: Path | None = None,
    environment: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> HeroicInstalledGames:
    root = get_heroic_config_root(
        config_root=config_root,
        environment=environment,
        home=home,
    )
    if not root.is_dir():
        return HeroicInstalledGames(
            config_root=root,
            config_exists=False,
            games=(),
            errors=(),
        )

    readers = (
        (_SIDELOAD_LIBRARY, _read_sideload_games),
        (_LEGENDARY_INSTALLED, _read_legendary_games),
        (_GOG_INSTALLED, _read_gog_games),
        (_NILE_INSTALLED, _read_nile_games),
    )
    games: list[HeroicInstalledGame] = []
    errors: list[HeroicReadError] = []

    for relative_path, reader in readers:
        path = root / relative_path
        if not path.is_file():
            continue

        parsed_games, read_errors = reader(path)
        games.extend(parsed_games)
        errors.extend(read_errors)

    return HeroicInstalledGames(
        config_root=root,
        config_exists=True,
        games=tuple(games),
        errors=tuple(errors),
    )


def read_heroic_game_config(
    config_root: Path,
    installed_game: HeroicInstalledGame,
) -> tuple[HeroicGameConfig | None, tuple[HeroicReadError, ...]]:
    app_name = _safe_app_name(installed_game.id.app_name)
    if app_name is None:
        return None, (
            HeroicReadError(
                path=config_root / "GamesConfig",
                message="Unsafe Heroic game identity.",
            ),
        )

    path = config_root / "GamesConfig" / f"{app_name}.json"
    if not path.is_file():
        return None, ()

    payload, read_error = _read_json(path)
    if read_error is not None:
        return None, (read_error,)
    if not isinstance(payload, dict) or not isinstance(payload.get(app_name), dict):
        return None, (
            HeroicReadError(path=path, message="Heroic game config identity mismatch."),
        )

    values = payload[app_name]
    errors: list[HeroicReadError] = []
    configured_prefix = _unix_path(values.get("winePrefix"))
    if values.get("winePrefix") not in (None, "") and configured_prefix is None:
        errors.append(
            HeroicReadError(path=path, message="Unsupported Heroic prefix path.")
        )

    wine_version = values.get("wineVersion")
    if not isinstance(wine_version, dict):
        wine_version = {}

    wine_binary = _unix_path(wine_version.get("bin"))
    if wine_version.get("bin") not in (None, "") and wine_binary is None:
        errors.append(
            HeroicReadError(path=path, message="Unsupported Heroic Wine binary path.")
        )

    target_exe = _optional_executable(
        values.get("targetExe"),
        install_path=installed_game.install_path,
        path=path,
        allow_relative=True,
        errors=errors,
    )
    explicit = payload.get("explicit")

    return (
        HeroicGameConfig(
            configured_prefix=configured_prefix,
            wine_version_name=_optional_string(wine_version.get("name")),
            wine_version_type=_optional_string(wine_version.get("type")),
            wine_binary=wine_binary,
            target_exe=target_exe,
            explicit=explicit if isinstance(explicit, bool) else None,
            source_path=path,
        ),
        tuple(errors),
    )


def _ambiguous_config_app_names(
    games: tuple[HeroicInstalledGame, ...],
) -> frozenset[str]:
    runners_by_app_name: dict[str, set[str]] = {}

    for game in games:
        app_name = _safe_app_name(game.id.app_name)
        if app_name is None:
            continue
        runners_by_app_name.setdefault(app_name, set()).add(game.id.runner)

    return frozenset(
        app_name
        for app_name, runners in runners_by_app_name.items()
        if len(runners) > 1
    )


def _installed_game_metadata_signature(
    game: HeroicInstalledGame,
) -> tuple[Path, Path | None, str | None]:
    return (
        _normalize_lexical_path(game.install_path),
        (
            _normalize_lexical_path(game.executable)
            if game.executable is not None
            else None
        ),
        game.platform,
    )


def _installed_game_representative_key(
    game: HeroicInstalledGame,
) -> tuple[str, str, str, str, str]:
    return (
        os.fspath(_normalize_lexical_path(game.source_path)),
        os.fspath(game.source_path),
        os.fspath(game.install_path),
        os.fspath(game.executable) if game.executable is not None else "",
        game.platform or "",
    )


def _canonicalize_installed_games(
    games: tuple[HeroicInstalledGame, ...],
) -> tuple[tuple[HeroicInstalledGame, ...], tuple[HeroicReadError, ...]]:
    records_by_id: dict[HeroicGameId, list[HeroicInstalledGame]] = {}
    for game in games:
        records_by_id.setdefault(game.id, []).append(game)

    canonical_games: list[HeroicInstalledGame] = []
    errors: list[HeroicReadError] = []

    for game_id in sorted(
        records_by_id,
        key=lambda identity: (identity.runner, identity.app_name),
    ):
        records = records_by_id[game_id]
        representative = min(records, key=_installed_game_representative_key)
        signatures = {_installed_game_metadata_signature(record) for record in records}
        if len(signatures) > 1:
            errors.append(
                HeroicReadError(
                    path=representative.source_path,
                    message=(
                        "Conflicting Heroic installed metadata for the same game "
                        "identity."
                    ),
                )
            )
            continue

        canonical_games.append(representative)

    return tuple(canonical_games), tuple(errors)


def resolve_heroic_prefix_state(
    config: HeroicGameConfig | None,
) -> HeroicPrefixState:
    configured_prefix = config.configured_prefix if config is not None else None
    if configured_prefix is None:
        return HeroicPrefixState(
            configured_prefix=None,
            structural_wine_prefix=None,
            drive_c=None,
            layout=HeroicPrefixLayout.UNRESOLVED,
        )
    if not configured_prefix.exists():
        return HeroicPrefixState(
            configured_prefix=configured_prefix,
            structural_wine_prefix=None,
            drive_c=None,
            layout=HeroicPrefixLayout.MISSING,
        )

    direct_drive_c = configured_prefix / "drive_c"
    pfx_prefix = configured_prefix / "pfx"
    pfx_drive_c = pfx_prefix / "drive_c"
    direct_exists = direct_drive_c.is_dir()
    pfx_exists = pfx_drive_c.is_dir()

    if direct_exists and pfx_exists:
        try:
            same_drive_c = os.path.samefile(direct_drive_c, pfx_drive_c)
        except OSError:
            same_drive_c = False

        if not same_drive_c:
            return HeroicPrefixState(
                configured_prefix=configured_prefix,
                structural_wine_prefix=None,
                drive_c=None,
                layout=HeroicPrefixLayout.AMBIGUOUS,
            )

    if direct_exists:
        return HeroicPrefixState(
            configured_prefix=configured_prefix,
            structural_wine_prefix=configured_prefix,
            drive_c=direct_drive_c,
            layout=HeroicPrefixLayout.DIRECT,
        )
    if pfx_exists:
        return HeroicPrefixState(
            configured_prefix=configured_prefix,
            structural_wine_prefix=pfx_prefix,
            drive_c=pfx_drive_c,
            layout=HeroicPrefixLayout.PFX_SUBDIRECTORY,
        )

    return HeroicPrefixState(
        configured_prefix=configured_prefix,
        structural_wine_prefix=None,
        drive_c=None,
        layout=HeroicPrefixLayout.UNRESOLVED,
    )


def _is_lexically_within(path: Path, parent: Path) -> bool:
    normalized_path = _normalize_lexical_path(path)
    normalized_parent = _normalize_lexical_path(parent)

    try:
        normalized_path.relative_to(normalized_parent)
    except ValueError:
        return False
    return True


def _match_evidences(
    game: Game,
    installed_game: HeroicInstalledGame,
    config: HeroicGameConfig | None,
) -> tuple[HeroicMatchEvidence, ...]:
    executable = _normalize_lexical_path(game.executable)
    steam_api = _normalize_lexical_path(game.steam_api)
    game_root = _normalize_lexical_path(game.root_directory)
    install_path = _normalize_lexical_path(installed_game.install_path)
    heroic_executables = tuple(
        _normalize_lexical_path(candidate)
        for candidate in (
            installed_game.executable,
            config.target_exe if config is not None else None,
        )
        if candidate is not None
    )
    executable_within = _is_lexically_within(executable, install_path)
    steam_api_within = _is_lexically_within(steam_api, install_path)
    evidences: list[HeroicMatchEvidence] = []

    if executable in heroic_executables:
        evidences.append(HeroicMatchEvidence.EXACT_EXECUTABLE_PATH)
    if game_root == install_path:
        evidences.append(HeroicMatchEvidence.GAME_ROOT_EQUALS_INSTALL_PATH)
    if executable_within and steam_api_within:
        evidences.append(
            HeroicMatchEvidence.EXECUTABLE_AND_STEAM_API_WITHIN_INSTALL_PATH
        )
    if executable_within:
        evidences.append(HeroicMatchEvidence.EXECUTABLE_WITHIN_INSTALL_PATH)
    if steam_api_within:
        evidences.append(HeroicMatchEvidence.STEAM_API_WITHIN_INSTALL_PATH)

    return tuple(evidences)


def resolve_game_heroic_provenance(
    game: Game,
    *,
    config_root: Path | None = None,
    environment: Mapping[str, str] | None = None,
    home: Path | None = None,
    installed_games: HeroicInstalledGames | None = None,
) -> HeroicGameProvenance:
    discovery = installed_games or discover_heroic_installed_games(
        config_root=config_root,
        environment=environment,
        home=home,
    )
    errors = list(discovery.errors)
    candidates: list[HeroicGameMatch] = []
    ambiguous_config_app_names = _ambiguous_config_app_names(discovery.games)
    canonical_games, canonicalization_errors = _canonicalize_installed_games(
        discovery.games
    )
    errors.extend(canonicalization_errors)

    for app_name in sorted(ambiguous_config_app_names):
        path = discovery.config_root / "GamesConfig" / f"{app_name}.json"
        if path.is_file():
            errors.append(
                HeroicReadError(
                    path=path,
                    message=(
                        "Heroic game config ownership is ambiguous across runners."
                    ),
                )
            )

    for installed_game in canonical_games:
        app_name = _safe_app_name(installed_game.id.app_name)
        if app_name in ambiguous_config_app_names:
            config, config_errors = None, ()
        else:
            config, config_errors = read_heroic_game_config(
                discovery.config_root,
                installed_game,
            )
        errors.extend(config_errors)
        evidences = _match_evidences(game, installed_game, config)
        if not evidences:
            continue

        candidates.append(
            HeroicGameMatch(
                installed_game=installed_game,
                config=config,
                prefix=resolve_heroic_prefix_state(config),
                evidences=evidences,
            )
        )

    strong_tiers = (
        HeroicMatchEvidence.EXACT_EXECUTABLE_PATH,
        HeroicMatchEvidence.GAME_ROOT_EQUALS_INSTALL_PATH,
        HeroicMatchEvidence.EXECUTABLE_AND_STEAM_API_WITHIN_INSTALL_PATH,
    )

    for tier in strong_tiers:
        tier_matches = tuple(
            candidate for candidate in candidates if tier in candidate.evidences
        )
        if not tier_matches:
            continue

        return HeroicGameProvenance(
            config_root=discovery.config_root,
            status=(
                HeroicProvenanceStatus.RESOLVED
                if len(tier_matches) == 1
                else HeroicProvenanceStatus.AMBIGUOUS
            ),
            candidates=tuple(candidates),
            effective=tier_matches[0] if len(tier_matches) == 1 else None,
            strongest_evidence=tier,
            errors=tuple(errors),
        )

    return HeroicGameProvenance(
        config_root=discovery.config_root,
        status=(
            HeroicProvenanceStatus.AMBIGUOUS
            if len(candidates) > 1
            else HeroicProvenanceStatus.UNKNOWN
        ),
        candidates=tuple(candidates),
        effective=None,
        strongest_evidence=None,
        errors=tuple(errors),
    )
