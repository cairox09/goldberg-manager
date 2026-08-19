from __future__ import annotations

import json
import os
import stat
import tempfile
import time
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from pathlib import Path

from .sentinel import read_sentinel_config
from .sentinel_integration import resolve_sentinel_gse_coverage
from .sentinel_repair import (
    SentinelRepairKind,
    SentinelRepairPlan,
    plan_sentinel_gse_repair,
)


class SentinelConfigWriteStatus(str, Enum):
    APPLIED = "applied"
    NO_CHANGE = "no-change"
    REJECTED = "rejected"
    CONFLICT = "conflict"
    FAILED = "failed"
    ROLLED_BACK = "rolled-back"


class SentinelConfigWriteReason(str, Enum):
    APPLIED = "applied"
    ALREADY_CURRENT = "already-current"
    CONFIG_UNAVAILABLE = "config-unavailable"
    CONFIG_INVALID = "config-invalid"
    GSE_DISABLED = "gse-disabled"
    PARTIAL_NOT_ALLOWED = "partial-not-allowed"
    NO_SAFE_PREFIXES = "no-safe-prefixes"
    CANDIDATE_PREFIX_INVALID = "candidate-prefix-invalid"
    DRIVE_C_INVALID = "drive-c-invalid"
    CONCURRENT_MODIFICATION = "concurrent-modification"
    TEMP_VALIDATION_FAILED = "temp-validation-failed"
    WRITE_FAILED = "write-failed"
    POST_VALIDATION_FAILED = "post-validation-failed"
    ROLLBACK_FAILED = "rollback-failed"


class _RollbackOutcome(Enum):
    ROLLED_BACK = "rolled-back"
    CONFLICT = "conflict"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class SentinelConfigWriteResult:
    status: SentinelConfigWriteStatus
    reason: SentinelConfigWriteReason
    config_path: Path
    backup_path: Path | None = None
    added_prefixes: tuple[Path, ...] = ()
    partial: bool = False
    rolled_back: bool = False
    message: str = ""


def _result(
    status: SentinelConfigWriteStatus,
    reason: SentinelConfigWriteReason,
    config_path: Path,
    *,
    backup_path: Path | None = None,
    added_prefixes: tuple[Path, ...] = (),
    partial: bool = False,
    rolled_back: bool = False,
    message: str = "",
) -> SentinelConfigWriteResult:
    return SentinelConfigWriteResult(
        status=status,
        reason=reason,
        config_path=config_path,
        backup_path=backup_path,
        added_prefixes=added_prefixes,
        partial=partial,
        rolled_back=rolled_back,
        message=message,
    )


def _normalize_path(path: Path) -> Path:
    return Path(os.path.normpath(os.path.abspath(path.expanduser())))


def _read_bytes(path: Path) -> bytes:
    return path.read_bytes()


def _config_matches(path: Path, expected: bytes) -> bool:
    try:
        return _read_bytes(path) == expected
    except OSError:
        return False


def _reject_json_constant(value: str) -> object:
    raise ValueError(f"Constante JSON não suportada: {value}")


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}

    for key, value in pairs:
        if key in result:
            raise ValueError(f"Chave JSON duplicada: {key}")

        result[key] = value

    return result


def _decode_json(content: bytes) -> object:
    return json.loads(
        content.decode("utf-8"),
        object_pairs_hook=_reject_duplicate_keys,
        parse_constant=_reject_json_constant,
        parse_float=Decimal,
    )


def _skip_json_whitespace(text: str, index: int) -> int:
    while index < len(text) and text[index] in " \t\r\n":
        index += 1

    return index


def _json_string_end(text: str, start: int) -> int:
    index = start + 1

    while index < len(text):
        if text[index] == "\\":
            index += 2
            continue

        if text[index] == '"':
            return index + 1

        index += 1

    raise ValueError("String JSON sem fechamento.")


def _json_value_end(text: str, start: int) -> int:
    if text[start] == '"':
        return _json_string_end(text, start)

    if text[start] in "[{":
        closing = {"[": "]", "{": "}"}
        stack = [closing[text[start]]]
        index = start + 1

        while index < len(text) and stack:
            character = text[index]

            if character == '"':
                index = _json_string_end(text, index)
                continue

            if character in closing:
                stack.append(closing[character])
            elif character == stack[-1]:
                stack.pop()

            index += 1

        if stack:
            raise ValueError("Valor JSON sem fechamento.")

        return index

    index = start

    while index < len(text) and text[index] not in ",}]":
        index += 1

    return index


def _top_level_member_span(text: str, member_name: str) -> tuple[int, int] | None:
    index = _skip_json_whitespace(text, 0)

    if index >= len(text) or text[index] != "{":
        return None

    index += 1

    while True:
        index = _skip_json_whitespace(text, index)

        if index >= len(text) or text[index] == "}":
            return None

        if text[index] != '"':
            return None

        key_end = _json_string_end(text, index)
        key = json.loads(text[index:key_end])
        index = _skip_json_whitespace(text, key_end)

        if index >= len(text) or text[index] != ":":
            return None

        value_start = _skip_json_whitespace(text, index + 1)
        value_end = _json_value_end(text, value_start)

        if key == member_name:
            return value_start, value_end

        index = _skip_json_whitespace(text, value_end)

        if index < len(text) and text[index] == ",":
            index += 1
            continue

        if index < len(text) and text[index] == "}":
            return None

        return None


def _append_prefixes(
    original_bytes: bytes,
    prefixes: list[object],
    added_prefixes: tuple[Path, ...],
) -> bytes | None:
    text = original_bytes.decode("utf-8")
    span = _top_level_member_span(text, "prefixes")

    if span is None:
        return None

    value_start, value_end = span

    if text[value_start] != "[" or text[value_end - 1] != "]":
        return None

    entries = ", ".join(
        json.dumps({"path": str(prefix)}, ensure_ascii=False)
        for prefix in added_prefixes
    )
    insertion = f", {entries}" if prefixes else entries
    closing_bracket = value_end - 1
    return (text[:closing_bracket] + insertion + text[closing_bracket:]).encode("utf-8")


def _safe_unlink(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def _write_temporary_file(
    config_path: Path,
    content: bytes,
    mode: int,
    uid: int,
    gid: int,
) -> Path:
    descriptor, temporary_name = tempfile.mkstemp(
        dir=config_path.parent,
        prefix=f".{config_path.name}.goldberg-manager-",
        suffix=".tmp",
    )
    temporary_path = Path(temporary_name)

    try:
        with os.fdopen(descriptor, "wb") as temporary_file:
            os.fchown(temporary_file.fileno(), uid, gid)
            os.fchmod(temporary_file.fileno(), mode)
            temporary_file.write(content)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
    except Exception:
        _safe_unlink(temporary_path)
        raise

    return temporary_path


def _fsync_directory(directory: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    descriptor = os.open(directory, flags)

    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _create_backup(
    config_path: Path,
    original_bytes: bytes,
    mode: int,
    uid: int,
    gid: int,
) -> Path:
    timestamp = time.time_ns()

    for collision_index in range(1000):
        suffix = (
            f"{timestamp}" if collision_index == 0 else f"{timestamp}-{collision_index}"
        )
        backup_path = config_path.with_name(
            f"{config_path.name}.goldberg-manager-backup-{suffix}"
        )

        try:
            descriptor = os.open(
                backup_path,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                mode,
            )
        except FileExistsError:
            continue

        try:
            with os.fdopen(descriptor, "wb") as backup_file:
                os.fchown(backup_file.fileno(), uid, gid)
                os.fchmod(backup_file.fileno(), mode)
                backup_file.write(original_bytes)
                backup_file.flush()
                os.fsync(backup_file.fileno())
        except Exception:
            _safe_unlink(backup_path)
            raise

        return backup_path

    raise FileExistsError("Não foi possível criar um nome exclusivo para o backup.")


def _validate_temporary_config(path: Path) -> bool:
    try:
        payload = _decode_json(_read_bytes(path))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return False

    if not isinstance(payload, dict):
        return False

    try:
        status = read_sentinel_config(path)
    except (OSError, UnicodeDecodeError):
        return False

    return status.configured and status.gse_enabled


def _validate_written_config(
    path: Path,
    added_prefixes: tuple[Path, ...],
) -> bool:
    try:
        status = read_sentinel_config(path)
    except (OSError, UnicodeDecodeError):
        return False

    if not status.configured or not status.gse_enabled:
        return False

    configured_prefixes = {_normalize_path(prefix) for prefix in status.prefix_paths}
    return all(prefix in configured_prefixes for prefix in added_prefixes)


def _restore_original(
    config_path: Path,
    original_bytes: bytes,
    expected_current_bytes: bytes,
    mode: int,
    uid: int,
    gid: int,
) -> _RollbackOutcome:
    rollback_path: Path | None = None

    if not _config_matches(config_path, expected_current_bytes):
        return _RollbackOutcome.CONFLICT

    try:
        rollback_path = _write_temporary_file(
            config_path,
            original_bytes,
            mode,
            uid,
            gid,
        )

        if not _validate_temporary_config(rollback_path):
            return _RollbackOutcome.FAILED

        if not _config_matches(config_path, expected_current_bytes):
            return _RollbackOutcome.CONFLICT

        os.replace(rollback_path, config_path)
        rollback_path = None
        _fsync_directory(config_path.parent)

        restored_status = read_sentinel_config(config_path)
        restored = (
            _read_bytes(config_path) == original_bytes
            and restored_status.configured
            and restored_status.gse_enabled
        )
        return _RollbackOutcome.ROLLED_BACK if restored else _RollbackOutcome.FAILED
    except (OSError, UnicodeDecodeError):
        try:
            restored_status = read_sentinel_config(config_path)
            if (
                _read_bytes(config_path) == original_bytes
                and restored_status.configured
                and restored_status.gse_enabled
            ):
                return _RollbackOutcome.ROLLED_BACK
        except (OSError, UnicodeDecodeError):
            pass

        return _RollbackOutcome.FAILED
    finally:
        if rollback_path is not None:
            _safe_unlink(rollback_path)


def _load_raw_config(original_bytes: bytes) -> dict[str, object] | None:
    try:
        payload = _decode_json(original_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return None

    if not isinstance(payload, dict) or not isinstance(payload.get("prefixes"), list):
        return None

    return payload


def _validate_candidates(plan: SentinelRepairPlan) -> SentinelConfigWriteReason | None:
    candidates = set(plan.candidate_prefixes)

    for location_plan in plan.uncovered_location_plans:
        if (
            location_plan.kind is not SentinelRepairKind.ADD_PREFIX
            or location_plan.candidate_prefix is None
        ):
            continue

        candidate = _normalize_path(location_plan.candidate_prefix)

        if candidate not in candidates:
            continue

        if not candidate.is_dir():
            return SentinelConfigWriteReason.CANDIDATE_PREFIX_INVALID

        if location_plan.drive_c is None or not location_plan.drive_c.is_dir():
            return SentinelConfigWriteReason.DRIVE_C_INVALID

    return None


def _original_partial_actions_are_satisfied(
    original_plan: SentinelRepairPlan,
    fresh_plan: SentinelRepairPlan,
) -> bool:
    if not original_plan.partially_repairable_via_sentinel_config:
        return False

    original_candidates = set(original_plan.candidate_prefixes)
    actionable_roots: set[Path] = set()

    for location_plan in original_plan.uncovered_location_plans:
        location = location_plan.location

        if (
            location_plan.kind is not SentinelRepairKind.ADD_PREFIX
            or location_plan.candidate_prefix is None
            or location is None
            or _normalize_path(location_plan.candidate_prefix)
            not in original_candidates
        ):
            continue

        actionable_roots.add(_normalize_path(location.root))

    if not actionable_roots or fresh_plan.candidate_prefixes:
        return False

    covered_roots = {
        _normalize_path(coverage.location.root)
        for coverage in fresh_plan.coverage.location_coverages
        if coverage.covered
    }

    if not actionable_roots <= covered_roots:
        return False

    unsupported_kinds = {
        SentinelRepairKind.UNSUPPORTED_CUSTOM_SAVE_ROOT,
        SentinelRepairKind.UNSUPPORTED_WINE_USER,
    }
    original_unsupported = {
        (_normalize_path(location_plan.location.root), location_plan.kind)
        for location_plan in original_plan.uncovered_location_plans
        if location_plan.location is not None
        and location_plan.kind in unsupported_kinds
    }

    for location_plan in fresh_plan.uncovered_location_plans:
        location = location_plan.location

        if (
            location is None
            or (
                _normalize_path(location.root),
                location_plan.kind,
            )
            not in original_unsupported
        ):
            return False

    return bool(fresh_plan.uncovered_location_plans)


def apply_sentinel_config_repair(
    plan: SentinelRepairPlan,
    *,
    allow_partial: bool = False,
) -> SentinelConfigWriteResult:
    config_path = plan.coverage.sentinel_status.path

    if config_path.is_symlink():
        return _result(
            SentinelConfigWriteStatus.REJECTED,
            SentinelConfigWriteReason.CONFIG_UNAVAILABLE,
            config_path,
            message="Links simbólicos não são suportados para escrita segura.",
        )

    try:
        original_bytes = _read_bytes(config_path)
        original_stat = config_path.stat()
        original_mode = stat.S_IMODE(original_stat.st_mode)
    except FileNotFoundError:
        return _result(
            SentinelConfigWriteStatus.REJECTED,
            SentinelConfigWriteReason.CONFIG_UNAVAILABLE,
            config_path,
            message="A configuração do Sentinel não foi encontrada.",
        )
    except OSError as error:
        return _result(
            SentinelConfigWriteStatus.FAILED,
            SentinelConfigWriteReason.WRITE_FAILED,
            config_path,
            message=str(error),
        )

    if not stat.S_ISREG(original_stat.st_mode):
        return _result(
            SentinelConfigWriteStatus.REJECTED,
            SentinelConfigWriteReason.CONFIG_UNAVAILABLE,
            config_path,
            message="A configuração do Sentinel não é um arquivo regular.",
        )

    try:
        current_status = read_sentinel_config(config_path)
    except (OSError, UnicodeDecodeError):
        return _result(
            SentinelConfigWriteStatus.REJECTED,
            SentinelConfigWriteReason.CONFIG_INVALID,
            config_path,
            message="A configuração atual do Sentinel não é UTF-8 válido.",
        )

    if not current_status.configured:
        return _result(
            SentinelConfigWriteStatus.REJECTED,
            SentinelConfigWriteReason.CONFIG_INVALID,
            config_path,
            message="A configuração atual do Sentinel é inválida.",
        )

    if not _config_matches(config_path, original_bytes):
        return _result(
            SentinelConfigWriteStatus.CONFLICT,
            SentinelConfigWriteReason.CONCURRENT_MODIFICATION,
            config_path,
            message="A configuração mudou durante a revalidação.",
        )

    fresh_coverage = resolve_sentinel_gse_coverage(
        current_status,
        plan.coverage.app_id,
        plan.coverage.save_resolution,
    )
    fresh_plan = plan_sentinel_gse_repair(fresh_coverage)
    approved_original_candidates = {
        _normalize_path(prefix) for prefix in plan.candidate_prefixes
    }
    fresh_candidates = {
        _normalize_path(prefix) for prefix in fresh_plan.candidate_prefixes
    }

    if not fresh_candidates.issubset(approved_original_candidates):
        return _result(
            SentinelConfigWriteStatus.CONFLICT,
            SentinelConfigWriteReason.CONCURRENT_MODIFICATION,
            config_path,
            message=(
                "O plano de reparo mudou e agora contém alterações que não foram "
                "confirmadas. Revise o plano novamente."
            ),
        )

    if not fresh_plan.gse_enabled:
        return _result(
            SentinelConfigWriteStatus.REJECTED,
            SentinelConfigWriteReason.GSE_DISABLED,
            config_path,
            message="O emulator GSE está desabilitado no Sentinel.",
        )

    if not fresh_plan.needs_repair:
        return _result(
            SentinelConfigWriteStatus.NO_CHANGE,
            SentinelConfigWriteReason.ALREADY_CURRENT,
            config_path,
            message="A cobertura já está atualizada.",
        )

    if _original_partial_actions_are_satisfied(plan, fresh_plan):
        return _result(
            SentinelConfigWriteStatus.NO_CHANGE,
            SentinelConfigWriteReason.ALREADY_CURRENT,
            config_path,
            partial=True,
            message="Todas as ações seguras do plano já foram aplicadas.",
        )

    if fresh_plan.partially_repairable_via_sentinel_config and not allow_partial:
        return _result(
            SentinelConfigWriteStatus.REJECTED,
            SentinelConfigWriteReason.PARTIAL_NOT_ALLOWED,
            config_path,
            message="O reparo parcial exige autorização explícita.",
        )

    partial = fresh_plan.partially_repairable_via_sentinel_config

    if not fresh_plan.fully_repairable_via_sentinel_config and not (
        allow_partial and partial
    ):
        return _result(
            SentinelConfigWriteStatus.REJECTED,
            SentinelConfigWriteReason.NO_SAFE_PREFIXES,
            config_path,
            message="Não há um conjunto de prefixes seguro para aplicar.",
        )

    candidate_error = _validate_candidates(fresh_plan)

    if candidate_error is not None:
        return _result(
            SentinelConfigWriteStatus.REJECTED,
            candidate_error,
            config_path,
            partial=partial,
            message="Um candidate prefix ou drive_c não é um diretório válido.",
        )

    raw_config = _load_raw_config(original_bytes)

    if raw_config is None:
        return _result(
            SentinelConfigWriteStatus.REJECTED,
            SentinelConfigWriteReason.CONFIG_INVALID,
            config_path,
            message="O JSON bruto do Sentinel não possui o schema esperado.",
        )

    prefixes = raw_config["prefixes"]
    assert isinstance(prefixes, list)
    existing_paths = {
        entry.get("path")
        for entry in prefixes
        if isinstance(entry, dict) and isinstance(entry.get("path"), str)
    }
    added_prefixes = tuple(
        prefix
        for prefix in fresh_plan.candidate_prefixes
        if str(prefix) not in existing_paths
    )

    if not added_prefixes:
        return _result(
            SentinelConfigWriteStatus.NO_CHANGE,
            SentinelConfigWriteReason.ALREADY_CURRENT,
            config_path,
            message="Nenhum prefix novo precisa ser adicionado.",
        )

    try:
        new_bytes = _append_prefixes(
            original_bytes,
            prefixes,
            added_prefixes,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        return _result(
            SentinelConfigWriteStatus.REJECTED,
            SentinelConfigWriteReason.CONFIG_INVALID,
            config_path,
            partial=partial,
            message=str(error),
        )

    if new_bytes is None:
        return _result(
            SentinelConfigWriteStatus.REJECTED,
            SentinelConfigWriteReason.CONFIG_INVALID,
            config_path,
            partial=partial,
            message="Não foi possível localizar o array top-level prefixes.",
        )

    temporary_path: Path | None = None
    backup_path: Path | None = None
    replaced = False

    try:
        temporary_path = _write_temporary_file(
            config_path,
            new_bytes,
            original_mode,
            original_stat.st_uid,
            original_stat.st_gid,
        )

        if not _validate_temporary_config(temporary_path):
            return _result(
                SentinelConfigWriteStatus.FAILED,
                SentinelConfigWriteReason.TEMP_VALIDATION_FAILED,
                config_path,
                partial=partial,
                message="O arquivo temporário não passou pela validação.",
            )

        backup_path = _create_backup(
            config_path,
            original_bytes,
            original_mode,
            original_stat.st_uid,
            original_stat.st_gid,
        )
        _fsync_directory(config_path.parent)

        if not _config_matches(config_path, original_bytes):
            return _result(
                SentinelConfigWriteStatus.CONFLICT,
                SentinelConfigWriteReason.CONCURRENT_MODIFICATION,
                config_path,
                backup_path=backup_path,
                partial=partial,
                message="A configuração mudou antes da substituição atômica.",
            )

        os.replace(temporary_path, config_path)
        temporary_path = None
        replaced = True
        _fsync_directory(config_path.parent)

        if not _validate_written_config(config_path, added_prefixes):
            rollback_outcome = _restore_original(
                config_path,
                original_bytes,
                new_bytes,
                original_mode,
                original_stat.st_uid,
                original_stat.st_gid,
            )
            rolled_back = rollback_outcome is _RollbackOutcome.ROLLED_BACK

            if rollback_outcome is _RollbackOutcome.CONFLICT:
                return _result(
                    SentinelConfigWriteStatus.CONFLICT,
                    SentinelConfigWriteReason.CONCURRENT_MODIFICATION,
                    config_path,
                    backup_path=backup_path,
                    partial=partial,
                    message=(
                        "A configuração mudou após a escrita; "
                        "o rollback não foi executado."
                    ),
                )

            return _result(
                (
                    SentinelConfigWriteStatus.ROLLED_BACK
                    if rolled_back
                    else SentinelConfigWriteStatus.FAILED
                ),
                (
                    SentinelConfigWriteReason.POST_VALIDATION_FAILED
                    if rolled_back
                    else SentinelConfigWriteReason.ROLLBACK_FAILED
                ),
                config_path,
                backup_path=backup_path,
                partial=partial,
                rolled_back=rolled_back,
                message=(
                    "A validação pós-write falhou; a configuração foi restaurada."
                    if rolled_back
                    else "A validação pós-write e o rollback falharam."
                ),
            )

        return _result(
            SentinelConfigWriteStatus.APPLIED,
            SentinelConfigWriteReason.APPLIED,
            config_path,
            backup_path=backup_path,
            added_prefixes=added_prefixes,
            partial=partial,
            message="Prefixes do Sentinel atualizados com segurança.",
        )
    except OSError as error:
        rollback_outcome = (
            _restore_original(
                config_path,
                original_bytes,
                new_bytes,
                original_mode,
                original_stat.st_uid,
                original_stat.st_gid,
            )
            if replaced
            else _RollbackOutcome.FAILED
        )
        rolled_back = rollback_outcome is _RollbackOutcome.ROLLED_BACK

        if rollback_outcome is _RollbackOutcome.CONFLICT:
            return _result(
                SentinelConfigWriteStatus.CONFLICT,
                SentinelConfigWriteReason.CONCURRENT_MODIFICATION,
                config_path,
                backup_path=backup_path,
                partial=partial,
                message=(
                    "A configuração mudou após a escrita; o rollback não foi executado."
                ),
            )

        return _result(
            (
                SentinelConfigWriteStatus.ROLLED_BACK
                if rolled_back
                else SentinelConfigWriteStatus.FAILED
            ),
            (
                SentinelConfigWriteReason.WRITE_FAILED
                if rolled_back or not replaced
                else SentinelConfigWriteReason.ROLLBACK_FAILED
            ),
            config_path,
            backup_path=backup_path,
            partial=partial,
            rolled_back=rolled_back,
            message=str(error),
        )
    finally:
        if temporary_path is not None:
            _safe_unlink(temporary_path)
