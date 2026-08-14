from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

from .scanner import Game


@dataclass(
    slots=True,
    frozen=True,
)
class AppIdCandidate:
    app_id: int
    name: str
    score: int
    source: str
    manifest_path: Path | None = None


_NOISE_WORDS = {
    "fix",
    "opti",
    "optimized",
    "patch",
    "release",
    "update",
    "win32",
    "win64",
    "x86",
    "x64",
}


def normalize_game_name(
    value: str,
) -> str:
    normalized = unicodedata.normalize(
        "NFKD",
        value,
    )

    normalized = (
        normalized.encode(
            "ascii",
            "ignore",
        )
        .decode("ascii")
        .casefold()
    )

    normalized = re.sub(
        r"\bv\d+\b",
        " ",
        normalized,
    )

    normalized = re.sub(
        r"[^a-z0-9]+",
        " ",
        normalized,
    )

    words = [word for word in normalized.split() if word not in _NOISE_WORDS]

    return " ".join(words)


def _similarity(
    first: str,
    second: str,
) -> int:
    first_normalized = normalize_game_name(first)

    second_normalized = normalize_game_name(second)

    if not first_normalized or not second_normalized:
        return 0

    if first_normalized == second_normalized:
        return 100

    ratio = SequenceMatcher(
        None,
        first_normalized,
        second_normalized,
    ).ratio()

    return round(ratio * 100)


def _read_existing_appid(
    game: Game,
) -> int | None:
    app_id_path = game.steam_api.parent / "steam_settings" / "steam_appid.txt"

    if not app_id_path.is_file():
        return None

    try:
        app_id = int(
            app_id_path.read_text(
                encoding="utf-8",
            ).strip()
        )
    except (
        OSError,
        ValueError,
    ):
        return None

    if app_id <= 0:
        return None

    return app_id


def _parse_manifest_value(
    content: str,
    key: str,
) -> str | None:
    match = re.search(
        rf'"{re.escape(key)}"\s+"([^"]*)"',
        content,
        flags=re.IGNORECASE,
    )

    if match is None:
        return None

    return match.group(1).strip()


def _read_app_manifest(
    path: Path,
) -> tuple[int, str, str] | None:
    try:
        content = path.read_text(
            encoding="utf-8",
            errors="replace",
        )
    except OSError:
        return None

    app_id_value = _parse_manifest_value(
        content,
        "appid",
    )

    name = _parse_manifest_value(
        content,
        "name",
    )

    install_dir = _parse_manifest_value(
        content,
        "installdir",
    )

    if app_id_value is None or name is None or install_dir is None:
        return None

    try:
        app_id = int(app_id_value)
    except ValueError:
        return None

    if app_id <= 0:
        return None

    return (
        app_id,
        name,
        install_dir,
    )


def get_default_steam_roots(
    home: Path | None = None,
) -> list[Path]:
    if home is None:
        home = Path.home()

    candidates = [
        home / ".steam" / "steam",
        home / ".local" / "share" / "Steam",
        (
            home
            / ".var"
            / "app"
            / "com.valvesoftware.Steam"
            / ".local"
            / "share"
            / "Steam"
        ),
    ]

    roots: list[Path] = []

    for path in candidates:
        if path.is_dir() and path not in roots:
            roots.append(path)

    return roots


def _read_library_paths(
    steam_root: Path,
) -> list[Path]:
    library_file = steam_root / "steamapps" / "libraryfolders.vdf"

    libraries = [steam_root]

    if not library_file.is_file():
        return libraries

    try:
        content = library_file.read_text(
            encoding="utf-8",
            errors="replace",
        )
    except OSError:
        return libraries

    for value in re.findall(
        r'"path"\s+"([^"]+)"',
        content,
        flags=re.IGNORECASE,
    ):
        value = value.replace(
            "\\\\",
            "\\",
        )

        path = Path(value).expanduser()

        if path.is_dir() and path not in libraries:
            libraries.append(path)

    return libraries


def discover_steam_libraries(
    steam_roots: list[Path] | None = None,
) -> list[Path]:
    if steam_roots is None:
        steam_roots = get_default_steam_roots()

    libraries: list[Path] = []

    for steam_root in steam_roots:
        for library in _read_library_paths(steam_root):
            if library not in libraries:
                libraries.append(library)

    return libraries


def _game_name_signals(
    game: Game,
) -> list[str]:
    signals = [
        game.name,
        game.root_directory.name,
        game.executable.stem,
    ]

    return list(dict.fromkeys(signal for signal in signals if signal.strip()))


def _manifest_score(
    game: Game,
    library: Path,
    name: str,
    install_dir: str,
) -> int:
    expected_directory = library / "steamapps" / "common" / install_dir

    try:
        if game.root_directory.resolve() == expected_directory.resolve():
            return 100
    except OSError:
        pass

    signals = _game_name_signals(game)

    scores = [
        _similarity(
            signal,
            candidate_name,
        )
        for signal in signals
        for candidate_name in (
            name,
            install_dir,
        )
    ]

    return max(
        scores,
        default=0,
    )


def find_manifest_candidates(
    game: Game,
    *,
    steam_roots: list[Path] | None = None,
    minimum_score: int = 55,
) -> list[AppIdCandidate]:
    candidates: list[AppIdCandidate] = []

    libraries = discover_steam_libraries(steam_roots)

    for library in libraries:
        steamapps = library / "steamapps"

        if not steamapps.is_dir():
            continue

        for manifest_path in steamapps.glob("appmanifest_*.acf"):
            manifest = _read_app_manifest(manifest_path)

            if manifest is None:
                continue

            app_id, name, install_dir = manifest

            score = _manifest_score(
                game,
                library,
                name,
                install_dir,
            )

            if score < minimum_score:
                continue

            candidates.append(
                AppIdCandidate(
                    app_id=app_id,
                    name=name,
                    score=score,
                    source="steam_manifest",
                    manifest_path=(manifest_path),
                )
            )

    return candidates


def resolve_local_appid(
    game: Game,
    *,
    steam_roots: list[Path] | None = None,
) -> list[AppIdCandidate]:
    candidates: list[AppIdCandidate] = []

    existing_app_id = _read_existing_appid(game)

    if existing_app_id is not None:
        candidates.append(
            AppIdCandidate(
                app_id=existing_app_id,
                name=game.name,
                score=100,
                source="steam_appid.txt",
            )
        )

    candidates.extend(
        find_manifest_candidates(
            game,
            steam_roots=steam_roots,
        )
    )

    best_by_app_id: dict[
        int,
        AppIdCandidate,
    ] = {}

    for candidate in candidates:
        previous = best_by_app_id.get(candidate.app_id)

        if previous is None or candidate.score > previous.score:
            best_by_app_id[candidate.app_id] = candidate

    return sorted(
        best_by_app_id.values(),
        key=lambda candidate: (
            candidate.score,
            candidate.name.casefold(),
        ),
        reverse=True,
    )
