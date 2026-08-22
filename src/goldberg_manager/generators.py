from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from .backup import get_backup_path, verify_backup
from .core.game import Game


def generate_steam_appid(
    steam_settings_directory: Path,
    app_id: int,
) -> Path:
    if app_id <= 0:
        raise ValueError("O Steam AppID deve ser um número inteiro positivo.")

    steam_settings_directory.mkdir(parents=True, exist_ok=True)

    output_path = steam_settings_directory / "steam_appid.txt"
    output_path.write_text(f"{app_id}\n", encoding="utf-8")

    return output_path


def generate_steam_interfaces(
    generator: Path,
    steam_api: Path,
    steam_settings_directory: Path,
    *,
    command_prefix: tuple[str, ...] = (),
) -> Path:
    if not generator.is_file():
        raise FileNotFoundError(f"Gerador de interfaces não encontrado: {generator}")

    if not steam_api.is_file():
        raise FileNotFoundError(f"Steam API original não encontrada: {steam_api}")

    generator = generator.resolve()
    steam_api = steam_api.resolve()

    with tempfile.TemporaryDirectory() as temp_directory:
        working_directory = Path(temp_directory)

        command = [
            *command_prefix,
            str(generator),
            str(steam_api),
        ]

        try:
            subprocess.run(
                command,
                cwd=working_directory,
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as error:
            details = error.stderr.strip() if error.stderr else "erro desconhecido"

            raise RuntimeError(
                f"Falha ao gerar steam_interfaces.txt: {details}"
            ) from error

        generated_file = working_directory / "steam_interfaces.txt"

        if not generated_file.is_file():
            raise RuntimeError("O gerador terminou sem criar steam_interfaces.txt.")

        steam_settings_directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        output_path = steam_settings_directory / "steam_interfaces.txt"

        shutil.copy2(
            generated_file,
            output_path,
        )

        return output_path


def select_interfaces_generator(
    game: Game,
    generator_x64: Path | None,
    generator_x86: Path | None,
) -> Path:
    if game.architecture == "64-bit":
        generator = generator_x64
    elif game.architecture == "32-bit":
        generator = generator_x86
    else:
        raise ValueError(f"Arquitetura não suportada: {game.architecture}")

    if generator is None:
        raise FileNotFoundError(
            f"Nenhum generate_interfaces configurado para jogos {game.architecture}."
        )

    if not generator.is_file():
        raise FileNotFoundError(f"Gerador de interfaces não encontrado: {generator}")

    return generator


def generate_game_steam_interfaces(
    game: Game,
    generator_x64: Path | None,
    generator_x86: Path | None,
    *,
    command_prefix: tuple[str, ...] = (),
) -> Path:
    if not verify_backup(game):
        raise ValueError(
            "É necessário um backup íntegro da Steam API original "
            "antes de gerar steam_interfaces.txt."
        )

    generator = select_interfaces_generator(
        game,
        generator_x64,
        generator_x86,
    )

    original_steam_api = get_backup_path(game)

    steam_settings_directory = game.steam_api.parent / "steam_settings"

    return generate_steam_interfaces(
        generator,
        original_steam_api,
        steam_settings_directory,
        command_prefix=command_prefix,
    )
