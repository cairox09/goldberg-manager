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


def _find_game_executable(game_directory: Path) -> Path | None:
    executables = [path for path in game_directory.glob("*.exe") if path.is_file()]

    if not executables:
        return None

    ignored_names = {
        "uninstall.exe",
        "unins000.exe",
        "unins001.exe",
        "setup.exe",
        "install.exe",
    }

    preferred = [path for path in executables if path.name.lower() not in ignored_names]

    candidates = preferred or executables

    candidates.sort(
        key=lambda path: (
            "launcher" in path.name.lower(),
            "crash" in path.name.lower(),
            path.name.lower(),
        )
    )

    return candidates[0]


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


def _find_game_root(steam_api: Path) -> Path:
    current = steam_api.parent

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


def detect_games(directories: list[Path]) -> list[Game]:
    games: list[Game] = []
    seen_directories: set[Path] = set()

    for source_directory in directories:
        if not source_directory.is_dir():
            continue

        for steam_api in source_directory.rglob("steam_api*.dll"):
            if not steam_api.is_file():
                continue

            game_directory = steam_api.parent
            resolved_directory = game_directory.resolve()

            if resolved_directory in seen_directories:
                continue

            executable = _find_game_executable(game_directory)

            if executable is None:
                continue

            seen_directories.add(resolved_directory)

            game_root = _find_game_root(steam_api)
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
