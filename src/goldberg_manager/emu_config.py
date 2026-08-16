from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


class EmuConfigError(RuntimeError):
    """Erro base da integração com generate_emu_config."""


class EmuConfigGenerationError(EmuConfigError):
    """Falha durante a execução de generate_emu_config."""


class EmuConfigOutputError(EmuConfigError):
    """Output ausente, inválido ou corrompido."""


@dataclass(frozen=True, slots=True)
class EmuConfigSummary:
    app_id: int
    output_directory: Path
    steam_settings_directory: Path
    achievements_file: Path | None
    achievements_count: int
    achievement_images_directory: Path
    achievement_images_count: int
    supported_languages_count: int
    dlc_count: int
    depots_count: int
    branches_count: int
    has_product_info: bool
    has_app_details: bool

    @property
    def has_achievements(self) -> bool:
        return self.achievements_file is not None and self.achievements_count > 0

    @property
    def has_achievement_images(self) -> bool:
        return self.achievement_images_count > 0


@dataclass(frozen=True, slots=True)
class AchievementsImportResult:
    destination_directory: Path
    achievements_file: Path
    images_directory: Path | None
    achievements_count: int
    images_count: int


@dataclass(frozen=True, slots=True)
class InstalledAchievementsStatus:
    achievements_file: Path | None
    achievements_count: int
    images_directory: Path
    images_count: int

    @property
    def installed(self) -> bool:
        return self.achievements_file is not None and self.achievements_count > 0


def _validate_app_id(
    app_id: int,
) -> None:
    if app_id <= 0:
        raise ValueError("O Steam AppID deve ser um número inteiro positivo.")


def build_generate_emu_config_command(
    generator: Path,
    app_id: int,
    *,
    anonymous: bool = False,
    relative_output: bool = True,
    clear_output: bool = True,
) -> list[str]:
    _validate_app_id(app_id)

    command = [str(generator.expanduser().resolve())]

    if anonymous:
        command.append("-anon")

    if relative_output:
        command.append("-rel_out")

    if clear_output:
        command.append("-clr")

    command.append(str(app_id))

    return command


def get_emu_output_directory(
    generator: Path,
    app_id: int,
) -> Path:
    _validate_app_id(app_id)

    generator = generator.expanduser().resolve()

    return generator.parent / "_OUTPUT" / str(app_id)


def run_generate_emu_config(
    generator: Path,
    app_id: int,
    *,
    anonymous: bool = False,
) -> Path:
    _validate_app_id(app_id)

    generator = generator.expanduser().resolve()

    if not generator.is_file():
        raise FileNotFoundError(f"generate_emu_config não encontrado: {generator}")

    command = build_generate_emu_config_command(
        generator,
        app_id,
        anonymous=anonymous,
    )

    try:
        subprocess.run(
            command,
            cwd=generator.parent,
            check=True,
        )
    except subprocess.CalledProcessError as error:
        raise EmuConfigGenerationError(
            f"generate_emu_config terminou com código {error.returncode}."
        ) from error

    output_directory = get_emu_output_directory(
        generator,
        app_id,
    )

    if not output_directory.is_dir():
        raise EmuConfigOutputError(
            "generate_emu_config terminou, "
            "mas o diretório de saída "
            "não foi encontrado: "
            f"{output_directory}"
        )

    return output_directory


def _read_json(
    path: Path,
) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise EmuConfigOutputError(f"JSON inválido: {path}") from error
    except OSError as error:
        raise EmuConfigOutputError(f"Não foi possível ler: {path}") from error


def _count_json_entries(
    path: Path,
) -> int:
    payload = _read_json(path)

    if isinstance(
        payload,
        (list, dict),
    ):
        return len(payload)

    raise EmuConfigOutputError(f"Estrutura JSON não suportada: {path}")


def _count_nonempty_lines(
    path: Path,
) -> int:
    if not path.is_file():
        return 0

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise EmuConfigOutputError(f"Não foi possível ler: {path}") from error

    return sum(
        1 for line in lines if line.strip() and not line.lstrip().startswith("#")
    )


def _count_dlc_entries(
    path: Path,
) -> int:
    if not path.is_file():
        return 0

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise EmuConfigOutputError(f"Não foi possível ler: {path}") from error

    in_dlc_section = False
    count = 0

    for raw_line in lines:
        line = raw_line.strip()

        if line.startswith("[") and line.endswith("]"):
            in_dlc_section = line.casefold() == "[app::dlcs]"

            continue

        if not in_dlc_section:
            continue

        if not line or line.startswith(("#", ";")):
            continue

        key, separator, _ = line.partition("=")

        if separator and key.strip().isdigit():
            count += 1

    return count


def _count_image_files(
    directory: Path,
) -> int:
    if not directory.is_dir():
        return 0

    supported_extensions = {
        ".jpg",
        ".jpeg",
        ".png",
        ".webp",
    }

    return sum(
        1
        for path in directory.iterdir()
        if path.is_file() and path.suffix.lower() in supported_extensions
    )


def _contains_generated_file(
    directory: Path,
    filename: str,
) -> bool:
    if not directory.is_dir():
        return False

    for path in directory.rglob("*"):
        if not path.is_file():
            continue

        if path.name == filename:
            return True

        if path.name.endswith(f"\\{filename}"):
            return True

    return False


def read_installed_achievements_status(
    destination_directory: Path,
) -> InstalledAchievementsStatus:
    destination_directory = destination_directory.expanduser().resolve()

    achievements_path = destination_directory / "achievements.json"

    images_directory = destination_directory / "img"

    if achievements_path.is_file():
        achievements_file = achievements_path

        achievements_count = _count_json_entries(achievements_path)

    else:
        achievements_file = None
        achievements_count = 0

    return InstalledAchievementsStatus(
        achievements_file=(achievements_file),
        achievements_count=(achievements_count),
        images_directory=(images_directory),
        images_count=(_count_image_files(images_directory)),
    )


def read_generated_emu_summary(
    generator: Path,
    app_id: int,
) -> EmuConfigSummary:
    output_directory = get_emu_output_directory(
        generator,
        app_id,
    )

    if not output_directory.is_dir():
        raise EmuConfigOutputError(
            f"Diretório de saída não encontrado: {output_directory}"
        )

    steam_settings_directory = output_directory / "steam_settings"

    if not steam_settings_directory.is_dir():
        raise EmuConfigOutputError(
            f"steam_settings gerado não foi encontrado: {steam_settings_directory}"
        )

    achievements_path = steam_settings_directory / "achievements.json"

    if achievements_path.is_file():
        achievements_file = achievements_path

        achievements_count = _count_json_entries(achievements_path)
    else:
        achievements_file = None
        achievements_count = 0

    achievement_images_directory = steam_settings_directory / "img"

    supported_languages = steam_settings_directory / "supported_languages.txt"

    configs_app = steam_settings_directory / "configs.app.ini"

    depots = steam_settings_directory / "depots.txt"

    branches = steam_settings_directory / "branches.json"

    if branches.is_file():
        branches_count = _count_json_entries(branches)
    else:
        branches_count = 0

    return EmuConfigSummary(
        app_id=app_id,
        output_directory=output_directory,
        steam_settings_directory=(steam_settings_directory),
        achievements_file=(achievements_file),
        achievements_count=(achievements_count),
        achievement_images_directory=(achievement_images_directory),
        achievement_images_count=(_count_image_files(achievement_images_directory)),
        supported_languages_count=(_count_nonempty_lines(supported_languages)),
        dlc_count=(_count_dlc_entries(configs_app)),
        depots_count=(_count_nonempty_lines(depots)),
        branches_count=(branches_count),
        has_product_info=(
            _contains_generated_file(
                output_directory,
                "app_product_info.json",
            )
        ),
        has_app_details=(
            _contains_generated_file(
                output_directory,
                "app_details.json",
            )
        ),
    )


def _replace_directory(
    source: Path,
    destination: Path,
) -> None:
    if not source.is_dir():
        raise EmuConfigOutputError(f"Diretório de origem não encontrado: {source}")

    if destination.exists() and not destination.is_dir():
        raise EmuConfigOutputError(
            f"O destino existe, mas não é um diretório: {destination}"
        )

    staging_directory = destination.parent / (
        f".{destination.name}.goldberg-manager-new"
    )

    previous_directory = destination.parent / (
        f".{destination.name}.goldberg-manager-old"
    )

    for temporary_directory in (
        staging_directory,
        previous_directory,
    ):
        if temporary_directory.is_dir():
            shutil.rmtree(temporary_directory)

    try:
        shutil.copytree(
            source,
            staging_directory,
        )

        if destination.is_dir():
            destination.rename(previous_directory)

        staging_directory.rename(destination)

        if previous_directory.is_dir():
            shutil.rmtree(previous_directory)

    except OSError as error:
        if not destination.exists() and previous_directory.is_dir():
            previous_directory.rename(destination)

        if staging_directory.is_dir():
            shutil.rmtree(staging_directory)

        raise EmuConfigOutputError(
            "Não foi possível substituir o diretório de imagens."
        ) from error


def import_generated_achievements(
    summary: EmuConfigSummary,
    destination_directory: Path,
) -> AchievementsImportResult:
    achievements_source = summary.achievements_file

    if (
        achievements_source is None
        or not achievements_source.is_file()
        or not summary.has_achievements
    ):
        raise EmuConfigOutputError(
            "Nenhum achievements.json válido foi gerado para importar."
        )

    destination_directory = destination_directory.expanduser().resolve()

    destination_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    achievements_destination = destination_directory / "achievements.json"

    try:
        shutil.copy2(
            achievements_source,
            achievements_destination,
        )
    except OSError as error:
        raise EmuConfigOutputError(
            "Não foi possível importar achievements.json."
        ) from error

    images_destination: Path | None = None

    if (
        summary.achievement_images_directory.is_dir()
        and summary.achievement_images_count > 0
    ):
        images_destination = destination_directory / "img"

        _replace_directory(
            summary.achievement_images_directory,
            images_destination,
        )

    return AchievementsImportResult(
        destination_directory=(destination_directory),
        achievements_file=(achievements_destination),
        images_directory=(images_destination),
        achievements_count=(summary.achievements_count),
        images_count=(summary.achievement_images_count),
    )
