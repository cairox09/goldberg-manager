from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from difflib import SequenceMatcher
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .core.game import Game


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


class SteamStoreSearchError(RuntimeError):
    pass


class _SteamStoreSearchParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)

        self.results: list[tuple[int, str]] = []

        self._current_app_id: int | None = None
        self._inside_title = False
        self._title_parts: list[str] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        attributes = dict(attrs)

        if tag == "a" and self._current_app_id is None:
            href = attributes.get("href")

            if href:
                match = re.search(
                    r"/app/(\d+)(?:/|$)",
                    href,
                )

                if match is not None:
                    self._current_app_id = int(match.group(1))

                    self._title_parts = []

        elif tag == "span" and self._current_app_id is not None:
            class_value = attributes.get("class") or ""

            classes = class_value.split()

            if "title" in classes:
                self._inside_title = True

    def handle_data(
        self,
        data: str,
    ) -> None:
        if self._inside_title:
            self._title_parts.append(data)

    def handle_endtag(
        self,
        tag: str,
    ) -> None:
        if tag == "span" and self._inside_title:
            self._inside_title = False

        elif tag == "a" and self._current_app_id is not None:
            title = " ".join(
                part.strip() for part in self._title_parts if part.strip()
            ).strip()

            if title:
                self.results.append(
                    (
                        self._current_app_id,
                        title,
                    )
                )

            self._current_app_id = None
            self._inside_title = False
            self._title_parts = []


def _download_steam_store_search(
    url: str,
) -> str:
    request = Request(
        url,
        headers={
            "User-Agent": ("GoldbergManager/0.1 (Steam AppID search)"),
            "Accept-Language": "en-US,en;q=0.8",
        },
    )

    try:
        with urlopen(
            request,
            timeout=10,
        ) as response:
            return response.read().decode(
                "utf-8",
                errors="replace",
            )

    except (
        HTTPError,
        URLError,
        TimeoutError,
        OSError,
    ) as exc:
        raise SteamStoreSearchError(
            "Não foi possível consultar a Steam Store."
        ) from exc


def search_steam_store(
    query: str,
    *,
    limit: int = 10,
    fetcher: Callable[[str], str] | None = None,
) -> list[AppIdCandidate]:
    query = query.strip()

    if not query:
        return []

    if limit <= 0:
        return []

    parameters = urlencode(
        {
            "term": query,
            "l": "english",
        }
    )

    url = f"https://store.steampowered.com/search/?{parameters}"

    if fetcher is None:
        fetcher = _download_steam_store_search

    content = fetcher(url)

    parser = _SteamStoreSearchParser()
    parser.feed(content)

    candidates: list[AppIdCandidate] = []

    seen_app_ids: set[int] = set()

    for app_id, name in parser.results:
        if app_id in seen_app_ids:
            continue

        seen_app_ids.add(app_id)

        score = _similarity(
            query,
            name,
        )

        candidates.append(
            AppIdCandidate(
                app_id=app_id,
                name=name,
                score=score,
                source="steam_store",
            )
        )

    candidates.sort(
        key=lambda candidate: (
            candidate.score,
            candidate.name.casefold(),
        ),
        reverse=True,
    )

    return candidates[:limit]


def get_game_search_query(
    game: Game,
) -> str:
    candidates = [
        normalize_game_name(game.name),
        normalize_game_name(game.root_directory.name),
        normalize_game_name(game.executable.stem),
    ]

    return max(
        (candidate for candidate in candidates if candidate),
        key=len,
        default="",
    )


def search_game_on_steam(
    game: Game,
    *,
    query: str | None = None,
    limit: int = 10,
    fetcher: Callable[[str], str] | None = None,
) -> list[AppIdCandidate]:
    if query is None:
        query = get_game_search_query(game)

    return search_steam_store(
        query,
        limit=limit,
        fetcher=fetcher,
    )
