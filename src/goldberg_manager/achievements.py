from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


class AchievementDataError(RuntimeError):
    """Metadata ou runtime de achievements inválido."""


@dataclass(frozen=True, slots=True)
class AchievementDefinition:
    name: str
    display_name: str
    description: str
    hidden: bool


@dataclass(frozen=True, slots=True)
class AchievementRuntimeState:
    name: str
    earned: bool
    earned_time: int | None
    progress: int | float | None
    max_progress: int | float | None


@dataclass(frozen=True, slots=True)
class AchievementStatus:
    definition: AchievementDefinition
    runtime: AchievementRuntimeState | None

    @property
    def earned(self) -> bool:
        return self.runtime is not None and self.runtime.earned

    @property
    def locked(self) -> bool:
        return not self.earned

    @property
    def earned_time(self) -> int | None:
        if self.runtime is None:
            return None

        return self.runtime.earned_time

    @property
    def progress(self) -> int | float | None:
        if self.runtime is None:
            return None

        return self.runtime.progress

    @property
    def max_progress(self) -> int | float | None:
        if self.runtime is None:
            return None

        return self.runtime.max_progress

    @property
    def partial(self) -> bool:
        return (
            not self.earned
            and self.progress is not None
            and self.max_progress is not None
            and self.max_progress > 0
            and 0 < self.progress < self.max_progress
        )

    @property
    def progress_percentage(self) -> float:
        if self.earned:
            return 100.0

        if self.progress is None or self.max_progress is None or self.max_progress <= 0:
            return 0.0

        return min(max(self.progress / self.max_progress * 100, 0.0), 100.0)


@dataclass(frozen=True, slots=True)
class AchievementReport:
    metadata_path: Path
    runtime_path: Path | None
    achievements: tuple[AchievementStatus, ...]
    unknown_runtime_names: tuple[str, ...]

    @property
    def total(self) -> int:
        return len(self.achievements)

    @property
    def unlocked(self) -> int:
        return sum(achievement.earned for achievement in self.achievements)

    @property
    def locked(self) -> int:
        return self.total - self.unlocked

    @property
    def partial(self) -> int:
        return sum(achievement.partial for achievement in self.achievements)

    @property
    def completion_percentage(self) -> float:
        if not self.total:
            return 0.0

        return self.unlocked / self.total * 100


def _read_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise AchievementDataError(f"JSON inválido: {path}") from error
    except OSError as error:
        raise AchievementDataError(f"Não foi possível ler: {path}") from error


def _localized_text(value: object, language: str) -> str | None:
    if isinstance(value, str):
        return value

    if not isinstance(value, dict):
        return None

    localized = {
        key.casefold(): text
        for key, text in value.items()
        if isinstance(key, str) and isinstance(text, str)
    }

    for candidate in (language.casefold(), "english"):
        if candidate in localized:
            return localized[candidate]

    for key, text in value.items():
        if isinstance(key, str) and key.casefold() != "token" and isinstance(text, str):
            return text

    return localized.get("token")


def _parse_hidden(value: object) -> bool:
    if isinstance(value, bool):
        return value

    if isinstance(value, int):
        return value == 1

    if isinstance(value, str):
        return value == "1"

    return False


def _metadata_definitions(
    path: Path,
    language: str,
) -> tuple[AchievementDefinition, ...]:
    payload = _read_json(path)

    if not isinstance(payload, list):
        raise AchievementDataError(
            f"A raiz da metadata de achievements não é uma lista JSON: {path}"
        )

    definitions: list[AchievementDefinition] = []

    for index, entry in enumerate(payload):
        if not isinstance(entry, dict):
            raise AchievementDataError(
                f"Achievement inválido no índice {index} da metadata: {path}"
            )

        name = entry.get("name")

        if not isinstance(name, str) or not name:
            raise AchievementDataError(
                f"Achievement sem nome válido no índice {index} da metadata: {path}"
            )

        definitions.append(
            AchievementDefinition(
                name=name,
                display_name=_localized_text(entry.get("displayName"), language)
                or name,
                description=_localized_text(entry.get("description"), language) or "",
                hidden=_parse_hidden(entry.get("hidden")),
            )
        )

    return tuple(definitions)


def _number(value: object) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None

    return value


def _parse_earned_time(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None

    return value


def _runtime_states(path: Path | None) -> tuple[AchievementRuntimeState, ...]:
    if path is None or not path.is_file():
        return ()

    payload = _read_json(path)

    if not isinstance(payload, dict):
        raise AchievementDataError(
            f"A raiz do runtime de achievements não é um objeto JSON: {path}"
        )

    states: list[AchievementRuntimeState] = []

    for name, entry in payload.items():
        if not isinstance(entry, dict):
            raise AchievementDataError(
                f"Estado runtime inválido para o achievement {name!r}: {path}"
            )

        states.append(
            AchievementRuntimeState(
                name=name,
                earned=entry.get("earned") is True,
                earned_time=_parse_earned_time(entry.get("earned_time")),
                progress=_number(entry.get("progress")),
                max_progress=_number(entry.get("max_progress")),
            )
        )

    return tuple(states)


def read_achievement_report(
    metadata_path: Path,
    runtime_path: Path | None = None,
    *,
    language: str = "english",
) -> AchievementReport:
    definitions = _metadata_definitions(metadata_path, language)
    runtime_states = _runtime_states(runtime_path)
    runtime_by_name = {state.name.casefold(): state for state in runtime_states}

    achievements = tuple(
        AchievementStatus(
            definition=definition,
            runtime=runtime_by_name.get(definition.name.casefold()),
        )
        for definition in definitions
    )

    definition_names = {definition.name.casefold() for definition in definitions}
    unknown_runtime_names = tuple(
        state.name
        for state in runtime_states
        if state.name.casefold() not in definition_names
    )

    return AchievementReport(
        metadata_path=metadata_path,
        runtime_path=runtime_path,
        achievements=achievements,
        unknown_runtime_names=unknown_runtime_names,
    )
