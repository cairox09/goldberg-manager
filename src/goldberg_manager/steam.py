from __future__ import annotations

import os
import re
from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from .scanner import Game

STEAM_STATE_FULLY_INSTALLED = 4

_LIBRARYFOLDERS = Path("steamapps/libraryfolders.vdf")
_MANIFEST_NAME = re.compile(r"^appmanifest_([1-9][0-9]*)\.acf$")
_WINDOWS_ABSOLUTE_PATH = re.compile(r"^[A-Za-z]:[\\/]")


class SteamProvenanceStatus(str, Enum):
    RESOLVED = "resolved"
    AMBIGUOUS = "ambiguous"
    UNKNOWN = "unknown"


class SteamMatchEvidence(str, Enum):
    GAME_ROOT_EQUALS_INSTALL_PATH = "game-root-equals-install-path"
    EXECUTABLE_AND_STEAM_API_WITHIN_INSTALL_PATH = (
        "executable-and-steam-api-within-install-path"
    )
    EXECUTABLE_WITHIN_INSTALL_PATH = "executable-within-install-path"
    STEAM_API_WITHIN_INSTALL_PATH = "steam-api-within-install-path"


_STRONG_MATCH_TIERS = (
    SteamMatchEvidence.GAME_ROOT_EQUALS_INSTALL_PATH,
    SteamMatchEvidence.EXECUTABLE_AND_STEAM_API_WITHIN_INSTALL_PATH,
)


class SteamPrefixLayout(str, Enum):
    PFX_SUBDIRECTORY = "pfx-subdirectory"
    MISSING = "missing"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True, slots=True)
class SteamReadError:
    path: Path
    message: str


@dataclass(frozen=True, slots=True)
class SteamLibrary:
    library_root: Path
    libraryfolders_path: Path
    declared_app_ids: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class SteamInstalledGame:
    app_id: int
    library_root: Path
    manifest_path: Path
    install_dir: str
    install_path: Path
    state_flags: int
    name: str | None = None

    def __post_init__(self) -> None:
        if self.app_id <= 0:
            raise ValueError("Steam AppID must be positive.")
        if self.state_flags & STEAM_STATE_FULLY_INSTALLED == 0:
            raise ValueError("Steam installed game requires the fully-installed flag.")


@dataclass(frozen=True, slots=True)
class SteamInstalledGames:
    steam_roots: tuple[Path, ...]
    libraries: tuple[SteamLibrary, ...]
    games: tuple[SteamInstalledGame, ...]
    errors: tuple[SteamReadError, ...]


@dataclass(frozen=True, slots=True)
class SteamPrefixState:
    compatdata_root: Path
    structural_wine_prefix: Path | None
    drive_c: Path | None
    layout: SteamPrefixLayout

    def __post_init__(self) -> None:
        resolved = self.layout is SteamPrefixLayout.PFX_SUBDIRECTORY
        if resolved != (
            self.structural_wine_prefix is not None and self.drive_c is not None
        ):
            raise ValueError(
                "Resolved Steam prefix requires complete structural paths."
            )
        if not resolved and (
            self.structural_wine_prefix is not None or self.drive_c is not None
        ):
            raise ValueError("Unresolved Steam prefix cannot have structural paths.")
        if resolved:
            expected_prefix = self.compatdata_root / "pfx"
            if self.structural_wine_prefix != expected_prefix:
                raise ValueError("Steam Wine prefix must be compatdata/pfx.")
            if self.drive_c != expected_prefix / "drive_c":
                raise ValueError("Steam drive_c must belong to compatdata/pfx.")


@dataclass(frozen=True, slots=True)
class SteamGameMatch:
    installed_game: SteamInstalledGame
    evidences: tuple[SteamMatchEvidence, ...]


@dataclass(frozen=True, slots=True)
class SteamGameProvenance:
    discovery: SteamInstalledGames
    status: SteamProvenanceStatus
    candidates: tuple[SteamGameMatch, ...]
    effective: SteamGameMatch | None
    prefix: SteamPrefixState | None
    strongest_evidence: SteamMatchEvidence | None

    def __post_init__(self) -> None:
        resolved = self.status is SteamProvenanceStatus.RESOLVED
        ambiguous = self.status is SteamProvenanceStatus.AMBIGUOUS
        highest_strong_tier = next(
            (
                tier
                for tier in _STRONG_MATCH_TIERS
                if any(tier in candidate.evidences for candidate in self.candidates)
            ),
            None,
        )
        candidates_in_highest_tier = (
            tuple(
                candidate
                for candidate in self.candidates
                if highest_strong_tier in candidate.evidences
            )
            if highest_strong_tier is not None
            else ()
        )

        if resolved != (self.effective is not None and self.prefix is not None):
            raise ValueError(
                "Resolved Steam provenance requires ownership and prefix state."
            )
        if self.effective is not None and not any(
            candidate is self.effective for candidate in self.candidates
        ):
            raise ValueError("The effective Steam match must be a candidate.")
        if not resolved and (self.effective is not None or self.prefix is not None):
            raise ValueError("Unresolved Steam provenance cannot have effective state.")
        if resolved:
            assert self.effective is not None
            assert self.prefix is not None
            if highest_strong_tier is None:
                raise ValueError("Resolved Steam provenance requires a strong tier.")
            if self.strongest_evidence is not highest_strong_tier:
                raise ValueError(
                    "Resolved strongest evidence must be the highest strong tier."
                )
            if len(candidates_in_highest_tier) != 1:
                raise ValueError(
                    "Resolved Steam provenance requires exactly one highest-tier "
                    "candidate."
                )
            if candidates_in_highest_tier[0] is not self.effective:
                raise ValueError(
                    "Resolved Steam provenance requires the effective match to be the "
                    "highest-tier candidate."
                )
            expected_compatdata_root = _normalize_lexical_path(
                self.effective.installed_game.library_root
                / "steamapps"
                / "compatdata"
                / str(self.effective.installed_game.app_id)
            )
            if (
                _normalize_lexical_path(self.prefix.compatdata_root)
                != expected_compatdata_root
            ):
                raise ValueError("Steam prefix must belong to effective ownership.")
        if ambiguous:
            if highest_strong_tier is None:
                raise ValueError("Ambiguous Steam provenance requires a strong tier.")
            if self.strongest_evidence is not highest_strong_tier:
                raise ValueError(
                    "Ambiguous strongest evidence must be the highest strong tier."
                )
            if len(candidates_in_highest_tier) < 2:
                raise ValueError(
                    "Ambiguous Steam provenance requires at least two strongest-tier "
                    "candidates."
                )
        if self.status is SteamProvenanceStatus.UNKNOWN:
            if self.strongest_evidence is not None:
                raise ValueError("Unknown Steam provenance has no strongest evidence.")
            if highest_strong_tier is not None:
                raise ValueError(
                    "Unknown Steam provenance cannot contain strong evidence."
                )

    @property
    def resolved(self) -> bool:
        return self.status is SteamProvenanceStatus.RESOLVED

    @property
    def ambiguous(self) -> bool:
        return self.status is SteamProvenanceStatus.AMBIGUOUS

    @property
    def unknown(self) -> bool:
        return self.status is SteamProvenanceStatus.UNKNOWN

    @property
    def errors(self) -> tuple[SteamReadError, ...]:
        return self.discovery.errors


class _KeyValuesError(ValueError):
    pass


_OPEN_BRACE = object()
_CLOSE_BRACE = object()


def _normalize_lexical_path(path: Path) -> Path:
    return Path(os.path.normpath(os.path.abspath(path.expanduser())))


def _path_has_nul(path: Path) -> bool:
    return "\x00" in os.fspath(path)


def _parse_positive_int(value: object) -> int | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    if not stripped or "\x00" in stripped or not stripped.isascii():
        return None
    if not stripped.isdigit():
        return None
    parsed = int(stripped)
    return parsed if parsed > 0 else None


def _parse_nonnegative_int(value: object) -> int | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    if not stripped or "\x00" in stripped or not stripped.isascii():
        return None
    if not stripped.isdigit():
        return None
    return int(stripped)


def _get_key(values: dict[str, object], key: str) -> object | None:
    expected = key.casefold()
    return next(
        (value for name, value in values.items() if name.casefold() == expected),
        None,
    )


def _tokenize_keyvalues(content: str) -> tuple[object, ...]:
    if "\x00" in content:
        raise _KeyValuesError("NUL is not valid in Steam KeyValues.")

    tokens: list[object] = []
    index = 0
    length = len(content)

    while index < length:
        character = content[index]
        if character.isspace():
            index += 1
            continue
        if content.startswith("//", index):
            newline = content.find("\n", index + 2)
            index = length if newline == -1 else newline + 1
            continue
        if character in "{}":
            tokens.append(_OPEN_BRACE if character == "{" else _CLOSE_BRACE)
            index += 1
            continue
        if character != '"':
            raise _KeyValuesError("Steam KeyValues tokens must be quoted.")

        index += 1
        value: list[str] = []
        while index < length:
            character = content[index]
            if character == '"':
                index += 1
                tokens.append("".join(value))
                break
            if character == "\\":
                index += 1
                if index >= length:
                    raise _KeyValuesError("Invalid Steam KeyValues escape.")
                escaped = content[index]
                replacements = {
                    "\\": "\\",
                    '"': '"',
                    "n": "\n",
                    "r": "\r",
                    "t": "\t",
                }
                if escaped in replacements:
                    value.append(replacements[escaped])
                else:
                    value.extend(("\\", escaped))
                index += 1
                continue
            value.append(character)
            index += 1
        else:
            raise _KeyValuesError("Unterminated Steam KeyValues string.")

    return tuple(tokens)


def _parse_keyvalues_object(
    tokens: tuple[object, ...],
    index: int,
    *,
    nested: bool,
) -> tuple[dict[str, object], int]:
    values: dict[str, object] = {}
    normalized_keys: set[str] = set()

    while index < len(tokens):
        if tokens[index] is _CLOSE_BRACE:
            if not nested:
                raise _KeyValuesError("Unexpected Steam KeyValues closing brace.")
            return values, index + 1

        key = tokens[index]
        if not isinstance(key, str):
            raise _KeyValuesError("Unexpected Steam KeyValues opening brace.")
        normalized_key = key.casefold()
        if normalized_key in normalized_keys:
            raise _KeyValuesError("Duplicate Steam KeyValues key.")
        normalized_keys.add(normalized_key)
        index += 1
        if index >= len(tokens):
            raise _KeyValuesError("Missing Steam KeyValues value.")

        if tokens[index] is _OPEN_BRACE:
            value, index = _parse_keyvalues_object(tokens, index + 1, nested=True)
        elif tokens[index] is _CLOSE_BRACE:
            raise _KeyValuesError("Missing Steam KeyValues value.")
        else:
            value = tokens[index]
            if not isinstance(value, str):
                raise _KeyValuesError("Invalid Steam KeyValues value.")
            index += 1
        values[key] = value

    if nested:
        raise _KeyValuesError("Unclosed Steam KeyValues object.")
    return values, index


def _parse_keyvalues(content: str) -> dict[str, object]:
    tokens = _tokenize_keyvalues(content)
    values, index = _parse_keyvalues_object(tokens, 0, nested=False)
    if index != len(tokens):
        raise _KeyValuesError("Unexpected Steam KeyValues data.")
    return values


def _read_keyvalues(
    path: Path,
) -> tuple[dict[str, object] | None, SteamReadError | None]:
    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return None, SteamReadError(
            path=path, message="Invalid Steam metadata encoding."
        )
    except OSError:
        return None, SteamReadError(path=path, message="Could not read Steam metadata.")

    try:
        return _parse_keyvalues(content), None
    except _KeyValuesError:
        return None, SteamReadError(path=path, message="Invalid Steam KeyValues.")


def _is_same_existing_path(first: Path, second: Path) -> bool:
    try:
        return os.path.samefile(first, second)
    except OSError:
        return first == second


def discover_steam_roots(
    steam_roots: Iterable[Path] | None = None,
    *,
    home: Path | None = None,
) -> tuple[Path, ...]:
    if steam_roots is None:
        user_home = Path.home() if home is None else home
        steam_roots = (
            user_home / ".local" / "share" / "Steam",
            user_home / ".steam" / "steam",
            user_home / ".steam" / "root",
        )

    normalized_roots = sorted(
        {
            _normalize_lexical_path(root)
            for root in steam_roots
            if not _path_has_nul(root)
        },
        key=os.fspath,
    )
    roots: list[Path] = []
    for root in normalized_roots:
        if not root.is_dir():
            continue
        if any(_is_same_existing_path(root, existing) for existing in roots):
            continue
        roots.append(root)
    return tuple(roots)


def _parse_library_path(value: object) -> Path | None:
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        return None
    stripped = value.strip()
    if _WINDOWS_ABSOLUTE_PATH.match(stripped) is not None:
        return None
    path = Path(stripped).expanduser()
    if not path.is_absolute():
        return None
    return _normalize_lexical_path(path)


def _read_libraries(
    steam_root: Path,
) -> tuple[list[SteamLibrary], list[SteamReadError]]:
    path = steam_root / _LIBRARYFOLDERS
    if not path.is_file():
        return [], [
            SteamReadError(path=path, message="Steam library registry is missing.")
        ]

    payload, read_error = _read_keyvalues(path)
    if read_error is not None:
        return [], [read_error]
    assert payload is not None
    libraryfolders = _get_key(payload, "libraryfolders")
    if not isinstance(libraryfolders, dict):
        return [], [
            SteamReadError(path=path, message="Invalid Steam library registry.")
        ]

    libraries: list[SteamLibrary] = []
    errors: list[SteamReadError] = []
    for value in libraryfolders.values():
        if not isinstance(value, dict):
            errors.append(
                SteamReadError(path=path, message="Invalid Steam library entry.")
            )
            continue
        library_root = _parse_library_path(_get_key(value, "path"))
        apps = _get_key(value, "apps")
        if library_root is None or not isinstance(apps, dict):
            errors.append(
                SteamReadError(path=path, message="Invalid Steam library entry.")
            )
            continue

        declared_app_ids: list[int] = []
        invalid_apps = False
        for app_id_value, installed_size in apps.items():
            app_id = _parse_positive_int(app_id_value)
            if app_id is None or not isinstance(installed_size, str):
                invalid_apps = True
                break
            declared_app_ids.append(app_id)
        if invalid_apps:
            errors.append(
                SteamReadError(path=path, message="Invalid Steam library apps map.")
            )
            continue
        if not library_root.is_dir():
            errors.append(
                SteamReadError(path=path, message="Steam library root is missing.")
            )
            continue

        libraries.append(
            SteamLibrary(
                library_root=library_root,
                libraryfolders_path=path,
                declared_app_ids=tuple(sorted(declared_app_ids)),
            )
        )

    return libraries, errors


def _canonicalize_libraries(
    libraries: list[SteamLibrary],
) -> tuple[list[SteamLibrary], list[SteamReadError]]:
    physical_groups: list[list[SteamLibrary]] = []
    errors: list[SteamReadError] = []

    for library in sorted(
        libraries,
        key=lambda item: (
            os.fspath(item.library_root),
            os.fspath(item.libraryfolders_path),
        ),
    ):
        physical_group = next(
            (
                group
                for group in physical_groups
                if _is_same_existing_path(library.library_root, group[0].library_root)
            ),
            None,
        )
        if physical_group is None:
            physical_groups.append([library])
        else:
            physical_group.append(library)

    canonical: list[SteamLibrary] = []
    for physical_group in physical_groups:
        declared_app_ids = {library.declared_app_ids for library in physical_group}
        if len(declared_app_ids) != 1:
            errors.append(
                SteamReadError(
                    path=physical_group[0].libraryfolders_path,
                    message="Conflicting Steam metadata for the same physical library.",
                )
            )
            continue
        canonical.append(physical_group[0])

    return canonical, errors


def _safe_install_path(library_root: Path, install_dir: object) -> Path | None:
    if not isinstance(install_dir, str) or not install_dir.strip():
        return None
    stripped = install_dir.strip()
    if "\x00" in stripped or _WINDOWS_ABSOLUTE_PATH.match(stripped) is not None:
        return None
    relative = Path(stripped)
    if relative.is_absolute():
        return None

    common_root = _normalize_lexical_path(library_root / "steamapps" / "common")
    install_path = _normalize_lexical_path(common_root / relative)
    if install_path == common_root:
        return None
    try:
        install_path.relative_to(common_root)
    except ValueError:
        return None
    return install_path


def _read_manifest(
    library: SteamLibrary,
    manifest_path: Path,
    expected_app_id: int,
) -> tuple[SteamInstalledGame | None, SteamReadError | None]:
    filename_match = _MANIFEST_NAME.fullmatch(manifest_path.name)
    filename_app_id = (
        int(filename_match.group(1)) if filename_match is not None else None
    )
    if filename_app_id is None or filename_app_id != expected_app_id:
        return None, SteamReadError(
            path=manifest_path,
            message="Steam manifest filename AppID is invalid.",
        )

    payload, read_error = _read_keyvalues(manifest_path)
    if read_error is not None:
        return None, read_error
    assert payload is not None
    app_state = _get_key(payload, "AppState")
    if not isinstance(app_state, dict):
        return None, SteamReadError(
            path=manifest_path,
            message="Invalid Steam app manifest.",
        )

    app_id = _parse_positive_int(_get_key(app_state, "appid"))
    state_flags = _parse_nonnegative_int(_get_key(app_state, "StateFlags"))
    install_dir = _get_key(app_state, "installdir")
    name = _get_key(app_state, "name")
    install_path = _safe_install_path(library.library_root, install_dir)
    if (
        app_id is None
        or app_id != filename_app_id
        or state_flags is None
        or install_path is None
        or not isinstance(install_dir, str)
        or (name is not None and not isinstance(name, str))
    ):
        return None, SteamReadError(
            path=manifest_path,
            message="Invalid Steam app manifest.",
        )
    if state_flags & STEAM_STATE_FULLY_INSTALLED == 0:
        return None, SteamReadError(
            path=manifest_path,
            message="Steam app manifest is not fully installed.",
        )
    if not install_path.is_dir():
        return None, SteamReadError(
            path=manifest_path,
            message="Steam app install path is missing.",
        )

    return (
        SteamInstalledGame(
            app_id=app_id,
            library_root=library.library_root,
            manifest_path=manifest_path,
            install_dir=install_dir.strip(),
            install_path=install_path,
            state_flags=state_flags,
            name=name.strip() if isinstance(name, str) and name.strip() else None,
        ),
        None,
    )


def _read_installed_games(
    library: SteamLibrary,
) -> tuple[list[SteamInstalledGame], list[SteamReadError]]:
    steamapps = library.library_root / "steamapps"
    declared = set(library.declared_app_ids)
    games: list[SteamInstalledGame] = []
    errors: list[SteamReadError] = []

    for manifest_path in sorted(steamapps.glob("appmanifest_*.acf")):
        match = _MANIFEST_NAME.fullmatch(manifest_path.name)
        app_id = int(match.group(1)) if match is not None else None
        if app_id is None or app_id not in declared:
            errors.append(
                SteamReadError(
                    path=manifest_path,
                    message="Steam manifest is not declared by its library.",
                )
            )

    for app_id in library.declared_app_ids:
        manifest_path = steamapps / f"appmanifest_{app_id}.acf"
        if not manifest_path.is_file():
            errors.append(
                SteamReadError(
                    path=manifest_path,
                    message="Declared Steam app manifest is missing.",
                )
            )
            continue
        game, read_error = _read_manifest(library, manifest_path, app_id)
        if read_error is not None:
            errors.append(read_error)
            continue
        assert game is not None
        games.append(game)

    return games, errors


def discover_steam_installed_games(
    *,
    steam_roots: Iterable[Path] | None = None,
    home: Path | None = None,
) -> SteamInstalledGames:
    roots = discover_steam_roots(steam_roots, home=home)
    libraries: list[SteamLibrary] = []
    errors: list[SteamReadError] = []

    for root in roots:
        parsed_libraries, read_errors = _read_libraries(root)
        libraries.extend(parsed_libraries)
        errors.extend(read_errors)

    libraries, canonicalization_errors = _canonicalize_libraries(libraries)
    errors.extend(canonicalization_errors)
    games: list[SteamInstalledGame] = []
    for library in libraries:
        parsed_games, read_errors = _read_installed_games(library)
        games.extend(parsed_games)
        errors.extend(read_errors)

    games.sort(
        key=lambda game: (
            game.app_id,
            os.fspath(game.library_root),
            os.fspath(game.manifest_path),
        )
    )
    return SteamInstalledGames(
        steam_roots=roots,
        libraries=tuple(libraries),
        games=tuple(games),
        errors=tuple(errors),
    )


def resolve_steam_prefix_state(installed_game: SteamInstalledGame) -> SteamPrefixState:
    compatdata_root = _normalize_lexical_path(
        installed_game.library_root
        / "steamapps"
        / "compatdata"
        / str(installed_game.app_id)
    )
    if not compatdata_root.is_dir():
        return SteamPrefixState(
            compatdata_root=compatdata_root,
            structural_wine_prefix=None,
            drive_c=None,
            layout=SteamPrefixLayout.MISSING,
        )

    wine_prefix = compatdata_root / "pfx"
    drive_c = wine_prefix / "drive_c"
    if not drive_c.is_dir():
        return SteamPrefixState(
            compatdata_root=compatdata_root,
            structural_wine_prefix=None,
            drive_c=None,
            layout=SteamPrefixLayout.UNRESOLVED,
        )

    return SteamPrefixState(
        compatdata_root=compatdata_root,
        structural_wine_prefix=wine_prefix,
        drive_c=drive_c,
        layout=SteamPrefixLayout.PFX_SUBDIRECTORY,
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
    installed_game: SteamInstalledGame,
) -> tuple[SteamMatchEvidence, ...]:
    game_root = _normalize_lexical_path(game.root_directory)
    executable = _normalize_lexical_path(game.executable)
    steam_api = _normalize_lexical_path(game.steam_api)
    install_path = _normalize_lexical_path(installed_game.install_path)
    executable_within = _is_lexically_within(executable, install_path)
    steam_api_within = _is_lexically_within(steam_api, install_path)
    evidences: list[SteamMatchEvidence] = []

    if game_root == install_path:
        evidences.append(SteamMatchEvidence.GAME_ROOT_EQUALS_INSTALL_PATH)
    if executable_within and steam_api_within:
        evidences.append(
            SteamMatchEvidence.EXECUTABLE_AND_STEAM_API_WITHIN_INSTALL_PATH
        )
    if executable_within:
        evidences.append(SteamMatchEvidence.EXECUTABLE_WITHIN_INSTALL_PATH)
    if steam_api_within:
        evidences.append(SteamMatchEvidence.STEAM_API_WITHIN_INSTALL_PATH)
    return tuple(evidences)


def _installed_game_sort_key(
    game: SteamInstalledGame,
) -> tuple[int, str, str, str]:
    return (
        game.app_id,
        os.fspath(game.library_root),
        os.fspath(game.manifest_path),
        os.fspath(game.install_path),
    )


def resolve_game_steam_provenance(
    game: Game,
    *,
    steam_roots: Iterable[Path] | None = None,
    home: Path | None = None,
    installed_games: SteamInstalledGames | None = None,
) -> SteamGameProvenance:
    discovery = installed_games or discover_steam_installed_games(
        steam_roots=steam_roots,
        home=home,
    )
    candidates = tuple(
        sorted(
            (
                SteamGameMatch(installed_game=installed_game, evidences=evidences)
                for installed_game in discovery.games
                if (evidences := _match_evidences(game, installed_game))
            ),
            key=lambda candidate: _installed_game_sort_key(candidate.installed_game),
        )
    )
    for tier in _STRONG_MATCH_TIERS:
        tier_matches = tuple(
            candidate for candidate in candidates if tier in candidate.evidences
        )
        if not tier_matches:
            continue
        if len(tier_matches) > 1:
            return SteamGameProvenance(
                discovery=discovery,
                status=SteamProvenanceStatus.AMBIGUOUS,
                candidates=candidates,
                effective=None,
                prefix=None,
                strongest_evidence=tier,
            )

        effective = tier_matches[0]
        return SteamGameProvenance(
            discovery=discovery,
            status=SteamProvenanceStatus.RESOLVED,
            candidates=candidates,
            effective=effective,
            prefix=resolve_steam_prefix_state(effective.installed_game),
            strongest_evidence=tier,
        )

    return SteamGameProvenance(
        discovery=discovery,
        status=SteamProvenanceStatus.UNKNOWN,
        candidates=candidates,
        effective=None,
        prefix=None,
        strongest_evidence=None,
    )
