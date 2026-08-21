from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from .core.game import Game

BACKUP_ROOT = Path.home() / ".local" / "share" / "goldberg-manager" / "backups"


def get_backup_path(game: Game) -> Path:
    return BACKUP_ROOT / game.name / game.steam_api_relative_path


def get_metadata_path(game: Game) -> Path:
    return BACKUP_ROOT / game.name / "metadata.json"


def has_backup_metadata(game: Game) -> bool:
    return get_metadata_path(game).is_file()


def _write_backup_metadata(game: Game) -> Path:
    backup_path = get_backup_path(game)
    metadata_path = get_metadata_path(game)

    payload = {
        "version": 1,
        "game_name": game.name,
        "architecture": game.architecture,
        "steam_api_relative_path": str(game.steam_api_relative_path),
        "sha256": calculate_sha256(backup_path),
    }

    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    return metadata_path


def has_backup(game: Game) -> bool:
    return get_backup_path(game).is_file()


def backup_game(game: Game) -> Path:
    backup_path = get_backup_path(game)

    if has_backup(game):
        raise FileExistsError(f"Já existe um backup para este jogo: {backup_path}")

    backup_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(game.steam_api, backup_path)
    _write_backup_metadata(game)

    return backup_path


def restore_game_backup(game: Game) -> None:
    backup_path = get_backup_path(game)

    if not backup_path.is_file():
        raise FileNotFoundError(
            f"Nenhum backup encontrado para este jogo: {backup_path}"
        )
    if not verify_backup(game):
        raise ValueError("O backup falhou na verificação de integridade.")

    shutil.copy2(backup_path, game.steam_api)


def calculate_sha256(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as file:
        while chunk := file.read(1024 * 1024):
            digest.update(chunk)

    return digest.hexdigest()


def verify_backup(game: Game) -> bool:
    backup_path = get_backup_path(game)
    metadata_path = get_metadata_path(game)

    if not backup_path.is_file() or not metadata_path.is_file():
        return False

    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False

    expected_sha256 = metadata.get("sha256")

    if not isinstance(expected_sha256, str):
        return False

    return calculate_sha256(backup_path) == expected_sha256


def current_file_matches_backup(game: Game) -> bool:
    backup_path = get_backup_path(game)

    if not backup_path.is_file():
        return False

    if not game.steam_api.is_file():
        return False

    return calculate_sha256(game.steam_api) == calculate_sha256(backup_path)


def ensure_backup_metadata(game: Game) -> Path:
    backup_path = get_backup_path(game)

    if not backup_path.is_file():
        raise FileNotFoundError(f"Nenhum backup encontrado: {backup_path}")

    metadata_path = get_metadata_path(game)

    if metadata_path.is_file():
        return metadata_path

    return _write_backup_metadata(game)
