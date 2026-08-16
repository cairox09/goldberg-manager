from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class Game:
    name: str
    root_directory: Path
    executable: Path
    steam_api: Path
    steam_api_relative_path: Path
    architecture: str
    source_directory: Path


@dataclass(slots=True)
class GameCandidate:
    name: str
    root_directory: Path
    executable: Path
    source_directory: Path
    game: Game | None

    @property
    def configurable(self) -> bool:
        return self.game is not None


def detect_generate_interfaces(
    root: Path,
) -> tuple[Path | None, Path | None]:
    candidates_x64 = [
        root / "tools" / "generate_interfaces" / "generate_interfacesx64.exe",
        root / "tools" / "generate_interfaces" / "generate_interfaces64.exe",
        root / "tools" / "generate_interfaces" / "generate_interfaces_x64.exe",
    ]

    candidates_x86 = [
        root / "tools" / "generate_interfaces" / "generate_interfacesx86.exe",
        root / "tools" / "generate_interfaces" / "generate_interfaces32.exe",
        root / "tools" / "generate_interfaces" / "generate_interfaces_x86.exe",
    ]

    x64 = next((path for path in candidates_x64 if path.is_file()), None)
    x86 = next((path for path in candidates_x86 if path.is_file()), None)

    if x64 is None:
        for pattern in (
            "generate_interfacesx64.exe",
            "generate_interfaces_x64.exe",
        ):
            for path in root.rglob(pattern):
                if path.is_file():
                    x64 = path
                    break

            if x64 is not None:
                break

    if x86 is None:
        for pattern in (
            "generate_interfacesx86.exe",
            "generate_interfaces_x86.exe",
        ):
            for path in root.rglob(pattern):
                if path.is_file():
                    x86 = path
                    break

            if x86 is not None:
                break

    return x64, x86


def detect_emu_config_generator(
    root: Path,
) -> Path | None:
    root = root.expanduser().resolve()

    search_roots = [root]

    current = root

    for _ in range(2):
        if current.parent == current:
            break

        current = current.parent

        if current not in search_roots:
            search_roots.append(current)

    relative_candidates = (
        (
            "gse_fork_tools",
            "generate_emu_config",
            "generate_emu_config",
        ),
        (
            "gse_fork_tools",
            "generate_emu_config",
            "generate_emu_config.exe",
        ),
        (
            "tools",
            "generate_emu_config",
            "generate_emu_config",
        ),
        (
            "tools",
            "generate_emu_config",
            "generate_emu_config.exe",
        ),
        (
            "generate_emu_config",
            "generate_emu_config",
        ),
        (
            "generate_emu_config",
            "generate_emu_config.exe",
        ),
        ("generate_emu_config",),
        ("generate_emu_config.exe",),
    )

    for search_root in search_roots:
        for relative_parts in relative_candidates:
            candidate = search_root.joinpath(*relative_parts)

            if candidate.is_file():
                return candidate

    for search_root in search_roots:
        for name in (
            "generate_emu_config",
            "generate_emu_config.exe",
        ):
            for path in search_root.rglob(name):
                if path.is_file():
                    return path

    return None


def _is_ignored_executable(
    executable: Path,
) -> bool:
    name = executable.name.lower()

    ignored_exact_names = {
        "install.exe",
        "setup.exe",
        "uninstall.exe",
        "unins000.exe",
        "unins001.exe",
        "oalinst.exe",
    }

    if name in ignored_exact_names:
        return True

    if name.startswith("unins"):
        return True

    if name.endswith("setup.exe"):
        return True

    if name.endswith("installer.exe"):
        return True

    ignored_fragments = (
        "crashpad",
        "crashreporter",
        "crash_reporter",
        "tradução",
        "traducao",
        "translation",
    )

    return any(fragment in name for fragment in ignored_fragments)


def _is_ignored_candidate_directory(
    directory: Path,
) -> bool:
    ignored_names = {
        "_commonredist",
        "commonredist",
        "redist",
        "redistributables",
        "tools",
        "steamclient_experimental",
    }

    return any(part.lower() in ignored_names for part in directory.parts)


def _is_standalone_launcher_candidate(
    directory: Path,
    executable: Path,
) -> bool:
    return (
        "launcher" in directory.name.lower() and "launcher" in executable.name.lower()
    )


def _find_game_executable(
    game_directory: Path,
) -> Path | None:
    executables = [path for path in game_directory.glob("*.exe") if path.is_file()]

    candidates = [path for path in executables if not _is_ignored_executable(path)]

    if not candidates:
        return None

    candidates.sort(
        key=lambda path: (
            "launcher" in path.name.lower(),
            "browser" in path.name.lower(),
            "crash" in path.name.lower(),
            path.name.lower(),
        )
    )

    return candidates[0]


def _find_game_directory_with_executable(
    steam_api: Path,
    source_directory: Path,
) -> tuple[Path, Path] | None:
    current = steam_api.parent
    source_root = source_directory.resolve()

    while True:
        current_root = current.resolve()

        try:
            current_root.relative_to(source_root)
        except ValueError:
            return None

        executable = _find_game_executable(current)

        if executable is not None:
            return (
                current,
                executable,
            )

        if current_root == source_root or current.parent == current:
            return None

        current = current.parent


def _get_game_name(game_directory: Path) -> str:
    generic_names = {
        "gamedata",
        "game",
        "games",
        "bin",
        "binaries",
        "x64",
        "x86",
        "win64",
        "win32",
    }

    if (
        game_directory.name.lower() in generic_names
        and game_directory.parent != game_directory
    ):
        return game_directory.parent.name

    return game_directory.name


def _find_game_root(
    game_directory: Path,
) -> Path:
    current = game_directory

    generic_names = {
        "gamedata",
        "game",
        "games",
        "bin",
        "binaries",
        "x64",
        "x86",
        "win64",
        "win32",
    }

    while current.name.lower() in generic_names and current.parent != current:
        current = current.parent

    return current


def _get_architecture(steam_api: Path) -> str:
    if steam_api.name.lower() == "steam_api64.dll":
        return "64-bit"

    return "32-bit"


def _path_is_within(
    path: Path,
    parent: Path,
) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False

    return True


def detect_games(directories: list[Path]) -> list[Game]:
    games: list[Game] = []
    seen_directories: set[Path] = set()

    for source_directory in directories:
        if not source_directory.is_dir():
            continue

        for steam_api in source_directory.rglob("steam_api*.dll"):
            if not steam_api.is_file():
                continue

            game_match = _find_game_directory_with_executable(
                steam_api,
                source_directory,
            )

            if game_match is None:
                continue

            game_directory, executable = game_match

            game_root = _find_game_root(game_directory)

            resolved_root = game_root.resolve()

            if resolved_root in seen_directories:
                continue

            seen_directories.add(resolved_root)
            architecture = _get_architecture(steam_api)
            steam_api_relative_path = steam_api.relative_to(game_root)

            games.append(
                Game(
                    name=_get_game_name(game_root),
                    root_directory=game_root,
                    executable=executable,
                    steam_api=steam_api,
                    steam_api_relative_path=steam_api_relative_path,
                    architecture=architecture,
                    source_directory=source_directory,
                )
            )

    games.sort(key=lambda game: game.name.lower())

    return games


def discover_game_candidates(
    directories: list[Path],
) -> list[GameCandidate]:
    compatible_games = detect_games(directories)

    candidates_by_root: dict[
        Path,
        GameCandidate,
    ] = {}

    compatible_roots: list[Path] = []

    for game in compatible_games:
        resolved_root = game.root_directory.resolve()

        compatible_roots.append(resolved_root)

        candidates_by_root[resolved_root] = GameCandidate(
            name=game.name,
            root_directory=game.root_directory,
            executable=game.executable,
            source_directory=game.source_directory,
            game=game,
        )

    unsupported_by_root: dict[
        Path,
        tuple[Path, Path, Path],
    ] = {}

    for source_directory in directories:
        if not source_directory.is_dir():
            continue

        executable_directories = sorted(
            {
                executable.parent
                for executable in source_directory.rglob("*.exe")
                if executable.is_file()
            },
            key=lambda path: len(path.parts),
        )

        for executable_directory in executable_directories:
            if _is_ignored_candidate_directory(executable_directory):
                continue

            executable = _find_game_executable(executable_directory)

            if executable is None:
                continue

            candidate_root = _find_game_root(executable_directory)

            if _is_standalone_launcher_candidate(
                candidate_root,
                executable,
            ):
                continue

            resolved_root = candidate_root.resolve()

            if any(
                _path_is_within(
                    resolved_root,
                    compatible_root,
                )
                for compatible_root in compatible_roots
            ):
                continue

            if resolved_root in unsupported_by_root:
                continue

            unsupported_by_root[resolved_root] = (
                candidate_root,
                executable,
                source_directory,
            )

    selected_unsupported_roots: list[Path] = []

    for resolved_root in sorted(
        unsupported_by_root,
        key=lambda path: len(path.parts),
    ):
        if any(
            _path_is_within(
                resolved_root,
                selected_root,
            )
            for selected_root in selected_unsupported_roots
        ):
            continue

        (
            candidate_root,
            executable,
            source_directory,
        ) = unsupported_by_root[resolved_root]

        selected_unsupported_roots.append(resolved_root)

        candidates_by_root[resolved_root] = GameCandidate(
            name=_get_game_name(candidate_root),
            root_directory=candidate_root,
            executable=executable,
            source_directory=source_directory,
            game=None,
        )

    candidates = list(candidates_by_root.values())

    candidates.sort(key=lambda candidate: candidate.name.lower())

    return candidates
