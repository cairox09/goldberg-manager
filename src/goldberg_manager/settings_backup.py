from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from .backup import BACKUP_ROOT, calculate_sha256
from .core.game import Game


@dataclass(slots=True)
class SteamSettingsBackup:
    path: Path
    created_at: datetime
    file_count: int
    valid: bool


def get_steam_settings_directory(
    game: Game,
) -> Path:
    return game.steam_api.parent / "steam_settings"


def get_steam_settings_backup_root(
    game: Game,
) -> Path:
    return BACKUP_ROOT / game.name / "steam_settings"


def _iter_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*") if path.is_file())


def _calculate_file_hashes(
    root: Path,
) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): calculate_sha256(path)
        for path in _iter_files(root)
    }


def _load_metadata(
    snapshot_path: Path,
) -> dict[str, object]:
    metadata_path = snapshot_path / "metadata.json"

    if not metadata_path.is_file():
        raise FileNotFoundError(
            f"Metadados do snapshot não encontrados: {metadata_path}"
        )

    try:
        metadata = json.loads(
            metadata_path.read_text(
                encoding="utf-8",
            )
        )
    except json.JSONDecodeError as exc:
        raise ValueError(f"Metadados inválidos: {metadata_path}") from exc

    if not isinstance(metadata, dict):
        raise TypeError(f"Metadados inválidos: {metadata_path}")

    return metadata


def _unique_snapshot_path(
    backup_root: Path,
    created_at: datetime,
) -> Path:
    base_name = created_at.strftime("%Y-%m-%d_%H-%M-%S_%f")

    snapshot_path = backup_root / base_name

    counter = 1

    while snapshot_path.exists():
        snapshot_path = backup_root / f"{base_name}_{counter:02d}"
        counter += 1

    return snapshot_path


def create_steam_settings_backup(
    game: Game,
    *,
    created_at: datetime | None = None,
) -> Path:
    source_directory = get_steam_settings_directory(game)

    if not source_directory.is_dir():
        raise FileNotFoundError(
            f"A pasta steam_settings não existe: {source_directory}"
        )

    source_files = _iter_files(source_directory)

    if not source_files:
        raise ValueError("A pasta steam_settings está vazia.")

    if created_at is None:
        created_at = datetime.now().astimezone()

    backup_root = get_steam_settings_backup_root(game)

    backup_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    snapshot_path = _unique_snapshot_path(
        backup_root,
        created_at,
    )

    files_path = snapshot_path / "files"

    try:
        shutil.copytree(
            source_directory,
            files_path,
        )

        file_hashes = _calculate_file_hashes(files_path)

        metadata = {
            "version": 1,
            "created_at": created_at.isoformat(),
            "game_name": game.name,
            "architecture": game.architecture,
            "steam_api_relative_path": str(game.steam_api_relative_path),
            "file_count": len(file_hashes),
            "files": file_hashes,
        }

        (snapshot_path / "metadata.json").write_text(
            json.dumps(
                metadata,
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    except Exception:
        shutil.rmtree(
            snapshot_path,
            ignore_errors=True,
        )
        raise

    return snapshot_path


def verify_steam_settings_backup(
    snapshot_path: Path,
) -> bool:
    files_path = snapshot_path / "files"

    if not files_path.is_dir():
        return False

    try:
        metadata = _load_metadata(snapshot_path)

        expected_files = metadata.get("files")

        if not isinstance(
            expected_files,
            dict,
        ):
            return False

        actual_files = _calculate_file_hashes(files_path)

        if set(actual_files) != set(expected_files):
            return False

        for relative_path, actual_hash in actual_files.items():
            expected_hash = expected_files.get(relative_path)

            if (
                not isinstance(
                    expected_hash,
                    str,
                )
                or actual_hash != expected_hash
            ):
                return False

    except (
        OSError,
        ValueError,
        TypeError,
    ):
        return False

    return True


def list_steam_settings_backups(
    game: Game,
) -> list[SteamSettingsBackup]:
    backup_root = get_steam_settings_backup_root(game)

    if not backup_root.is_dir():
        return []

    backups: list[SteamSettingsBackup] = []

    for snapshot_path in backup_root.iterdir():
        if not snapshot_path.is_dir():
            continue

        valid = verify_steam_settings_backup(snapshot_path)

        try:
            metadata = _load_metadata(snapshot_path)
        except (
            OSError,
            ValueError,
        ):
            metadata = {}

        created_at_value = metadata.get("created_at")

        if isinstance(
            created_at_value,
            str,
        ):
            try:
                created_at = datetime.fromisoformat(created_at_value)
            except ValueError:
                created_at = datetime.fromtimestamp(
                    snapshot_path.stat().st_mtime
                ).astimezone()
        else:
            created_at = datetime.fromtimestamp(
                snapshot_path.stat().st_mtime
            ).astimezone()

        file_count_value = metadata.get("file_count")

        if isinstance(
            file_count_value,
            int,
        ):
            file_count = file_count_value
        else:
            files_path = snapshot_path / "files"

            file_count = len(_iter_files(files_path)) if files_path.is_dir() else 0

        backups.append(
            SteamSettingsBackup(
                path=snapshot_path,
                created_at=created_at,
                file_count=file_count,
                valid=valid,
            )
        )

    backups.sort(
        key=lambda backup: backup.created_at,
        reverse=True,
    )

    return backups


def _remove_path(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)

    elif path.exists() or path.is_symlink():
        path.unlink()


def restore_steam_settings_backup(
    game: Game,
    snapshot_path: Path,
) -> Path:
    if not verify_steam_settings_backup(snapshot_path):
        raise ValueError(
            "O backup de steam_settings falhou na verificação de integridade."
        )

    metadata = _load_metadata(snapshot_path)

    if metadata.get("game_name") != game.name:
        raise ValueError("Este backup pertence a outro jogo.")

    expected_api_path = str(game.steam_api_relative_path)

    if metadata.get("steam_api_relative_path") != expected_api_path:
        raise ValueError(
            "Este backup pertence a outra instalação/configuração do jogo."
        )

    source_directory = snapshot_path / "files"

    target_directory = get_steam_settings_directory(game)

    target_directory.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    restore_id = uuid4().hex

    temporary_directory = (
        target_directory.parent / f".steam_settings.restore-{restore_id}"
    )

    previous_directory = (
        target_directory.parent / f".steam_settings.previous-{restore_id}"
    )

    shutil.copytree(
        source_directory,
        temporary_directory,
    )

    had_previous = target_directory.exists()

    try:
        if had_previous:
            target_directory.rename(previous_directory)

        temporary_directory.rename(target_directory)

    except Exception:
        _remove_path(temporary_directory)

        if (
            had_previous
            and previous_directory.exists()
            and not target_directory.exists()
        ):
            previous_directory.rename(target_directory)

        raise

    if previous_directory.exists():
        try:
            _remove_path(previous_directory)
        except OSError:
            pass

    return target_directory
