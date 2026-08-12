from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

APP_CONFIG_DIR = Path.home() / ".config" / "goldberg-manager"
APP_CONFIG_FILE = APP_CONFIG_DIR / "config.json"


@dataclass(slots=True)
class GoldbergConfig:
    root: Path | None = None
    interfaces_generator_x64: Path | None = None
    interfaces_generator_x86: Path | None = None
    emu_config_generator: Path | None = None


@dataclass(slots=True)
class GamesConfig:
    directories: list[Path] = field(default_factory=list)


@dataclass(slots=True)
class UIConfig:
    theme: str = "dark"


@dataclass(slots=True)
class AppConfig:
    goldberg: GoldbergConfig = field(default_factory=GoldbergConfig)
    games: GamesConfig = field(default_factory=GamesConfig)
    ui: UIConfig = field(default_factory=UIConfig)


def _path_to_str(value: Path | None) -> str | None:
    return None if value is None else str(value)


def _str_to_path(value: Any) -> Path | None:
    if value is None or value == "":
        return None
    return Path(str(value))


def _list_to_paths(value: Any) -> list[Path]:
    if not isinstance(value, list):
        return []
    return [Path(str(item)) for item in value if item not in (None, "")]


def _config_to_dict(config: AppConfig) -> dict[str, Any]:
    return {
        "goldberg": {
            "root": _path_to_str(config.goldberg.root),
            "interfaces_generator_x64": _path_to_str(
                config.goldberg.interfaces_generator_x64
            ),
            "interfaces_generator_x86": _path_to_str(
                config.goldberg.interfaces_generator_x86
            ),
            "emu_config_generator": _path_to_str(config.goldberg.emu_config_generator),
        },
        "games": {
            "directories": [str(path) for path in config.games.directories],
        },
        "ui": {
            "theme": config.ui.theme,
        },
    }


def _dict_to_config(data: dict[str, Any]) -> AppConfig:
    goldberg_data = data.get("goldberg", {}) if isinstance(data, dict) else {}
    games_data = data.get("games", {}) if isinstance(data, dict) else {}
    ui_data = data.get("ui", {}) if isinstance(data, dict) else {}

    return AppConfig(
        goldberg=GoldbergConfig(
            root=_str_to_path(goldberg_data.get("root")),
            interfaces_generator_x64=_str_to_path(
                goldberg_data.get("interfaces_generator_x64")
            ),
            interfaces_generator_x86=_str_to_path(
                goldberg_data.get("interfaces_generator_x86")
            ),
            emu_config_generator=_str_to_path(
                goldberg_data.get("emu_config_generator")
            ),
        ),
        games=GamesConfig(
            directories=_list_to_paths(games_data.get("directories")),
        ),
        ui=UIConfig(
            theme=str(ui_data.get("theme", "dark")),
        ),
    )


def save_config(config: AppConfig) -> None:
    APP_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    payload = _config_to_dict(config)
    APP_CONFIG_FILE.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def load_config() -> AppConfig:
    if not APP_CONFIG_FILE.exists():
        config = AppConfig()
        save_config(config)
        return config

    try:
        raw = json.loads(APP_CONFIG_FILE.read_text(encoding="utf-8"))

        if not isinstance(raw, dict):
            raise TypeError("Config file root is not an object")

        return _dict_to_config(raw)

    except (json.JSONDecodeError, OSError, TypeError, KeyError, ValueError):
        backup_file = APP_CONFIG_FILE.with_suffix(".broken.json")

        try:
            APP_CONFIG_FILE.replace(backup_file)
        except OSError:
            backup_file = None

        config = AppConfig()
        save_config(config)
        return config
