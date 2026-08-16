from __future__ import annotations

import json
import os
import shutil
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

SENTINEL_APP_NAME = "sentinel"

SENTINEL_GSE_EMULATOR_ID = "gse"
SENTINEL_GOLDBERG_EMULATOR_ID = "goldberg-steamemu"

SENTINEL_GSE_RELATIVE_PATH = Path("users/steamuser/AppData/Roaming/GSE Saves")
SENTINEL_GOLDBERG_RELATIVE_PATH = Path(
    "users/steamuser/AppData/Roaming/Goldberg SteamEmu Saves"
)


@dataclass(frozen=True, slots=True)
class SentinelEmulator:
    id: str
    should_notify: bool


@dataclass(frozen=True, slots=True)
class SentinelInstallation:
    executable: Path | None
    config_path: Path
    data_directory: Path
    state_directory: Path
    log_path: Path

    @property
    def installed(self) -> bool:
        return self.executable is not None

    @property
    def config_exists(self) -> bool:
        return self.config_path.is_file()

    @property
    def data_exists(self) -> bool:
        return self.data_directory.is_dir()

    @property
    def state_exists(self) -> bool:
        return self.state_directory.is_dir()


@dataclass(frozen=True, slots=True)
class SentinelConfigStatus:
    path: Path
    exists: bool
    valid_json: bool
    schema_valid: bool
    prefix_paths: tuple[Path, ...]
    emulators: tuple[SentinelEmulator, ...]
    error: str | None = None

    @property
    def configured(self) -> bool:
        return self.exists and self.valid_json and self.schema_valid

    @property
    def gse_enabled(self) -> bool:
        return any(
            emulator.id == SENTINEL_GSE_EMULATOR_ID for emulator in self.emulators
        )

    @property
    def goldberg_enabled(self) -> bool:
        return any(
            emulator.id == SENTINEL_GOLDBERG_EMULATOR_ID for emulator in self.emulators
        )

    @property
    def watcher_configured(self) -> bool:
        return self.configured and bool(self.prefix_paths) and bool(self.emulators)

    @property
    def gse_watcher_configured(self) -> bool:
        return self.configured and bool(self.prefix_paths) and self.gse_enabled


def _xdg_directory(
    environment: Mapping[str, str],
    variable: str,
    fallback: Path,
) -> Path:
    value = environment.get(variable)

    if value:
        return Path(value).expanduser()

    return fallback


def detect_sentinel(
    environment: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> SentinelInstallation:
    env = os.environ if environment is None else environment
    user_home = Path.home() if home is None else home

    config_home = _xdg_directory(
        env,
        "XDG_CONFIG_HOME",
        user_home / ".config",
    )
    data_home = _xdg_directory(
        env,
        "XDG_DATA_HOME",
        user_home / ".local" / "share",
    )
    state_home = _xdg_directory(
        env,
        "XDG_STATE_HOME",
        user_home / ".local" / "state",
    )

    executable_string = shutil.which(SENTINEL_APP_NAME)
    executable = Path(executable_string) if executable_string is not None else None

    config_directory = config_home / SENTINEL_APP_NAME
    data_directory = data_home / SENTINEL_APP_NAME
    state_directory = state_home / SENTINEL_APP_NAME

    return SentinelInstallation(
        executable=executable,
        config_path=config_directory / "config.json",
        data_directory=data_directory,
        state_directory=state_directory,
        log_path=state_directory / "logs" / "sentinel.log",
    )


def _read_prefixes(
    value: object,
) -> tuple[tuple[Path, ...], bool]:
    if not isinstance(value, list):
        return (), False

    paths: list[Path] = []
    valid = True

    for entry in value:
        if not isinstance(entry, dict):
            valid = False
            continue

        path = entry.get("path")

        if not isinstance(path, str) or not path.strip():
            valid = False
            continue

        paths.append(Path(path).expanduser())

    return tuple(paths), valid


def _read_emulators(
    value: object,
) -> tuple[tuple[SentinelEmulator, ...], bool]:
    if not isinstance(value, list):
        return (), False

    emulators: list[SentinelEmulator] = []
    valid = True

    for entry in value:
        if not isinstance(entry, dict):
            valid = False
            continue

        emulator_id = entry.get("id")
        should_notify = entry.get("shouldNotify")

        if not isinstance(emulator_id, str) or not emulator_id:
            valid = False
            continue

        if not isinstance(should_notify, bool):
            valid = False
            continue

        emulators.append(
            SentinelEmulator(
                id=emulator_id,
                should_notify=should_notify,
            )
        )

    return tuple(emulators), valid


def read_sentinel_config(
    path: Path,
) -> SentinelConfigStatus:
    if not path.is_file():
        return SentinelConfigStatus(
            path=path,
            exists=False,
            valid_json=False,
            schema_valid=False,
            prefix_paths=(),
            emulators=(),
        )

    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        return SentinelConfigStatus(
            path=path,
            exists=True,
            valid_json=False,
            schema_valid=False,
            prefix_paths=(),
            emulators=(),
            error=str(exc),
        )

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        return SentinelConfigStatus(
            path=path,
            exists=True,
            valid_json=False,
            schema_valid=False,
            prefix_paths=(),
            emulators=(),
            error=str(exc),
        )

    if not isinstance(data, dict):
        return SentinelConfigStatus(
            path=path,
            exists=True,
            valid_json=True,
            schema_valid=False,
            prefix_paths=(),
            emulators=(),
            error="A raiz da configuração do Sentinel não é um objeto JSON.",
        )

    prefixes, prefixes_valid = _read_prefixes(data.get("prefixes", []))
    emulators, emulators_valid = _read_emulators(data.get("emulators", []))

    return SentinelConfigStatus(
        path=path,
        exists=True,
        valid_json=True,
        schema_valid=prefixes_valid and emulators_valid,
        prefix_paths=prefixes,
        emulators=emulators,
    )
