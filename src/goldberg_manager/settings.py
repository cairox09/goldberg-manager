from __future__ import annotations

import configparser
from dataclasses import dataclass
from pathlib import Path

from .generators import generate_steam_appid
from .scanner import Game


@dataclass(slots=True)
class SteamUserSettings:
    account_name: str
    account_steamid: int | None = None
    language: str | None = None
    ip_country: str | None = None
    local_save_path: str | None = None
    saves_folder_name: str | None = None


@dataclass(slots=True)
class SteamSettingsSnapshot:
    app_id: int | None = None
    account_name: str | None = None
    account_steamid: int | None = None
    language: str | None = None
    ip_country: str | None = None
    local_save_path: str | None = None
    saves_folder_name: str | None = None
    has_steam_interfaces: bool = False


def generate_user_config(
    steam_settings_directory: Path,
    settings: SteamUserSettings,
) -> Path:
    account_name = settings.account_name.strip()

    if not account_name:
        raise ValueError("O nome da conta não pode ficar vazio.")

    if settings.account_steamid is not None and settings.account_steamid <= 0:
        raise ValueError("O SteamID deve ser um número inteiro positivo.")

    language = settings.language.strip() if settings.language is not None else None

    ip_country = (
        settings.ip_country.strip().upper() if settings.ip_country is not None else None
    )

    if ip_country is not None and (len(ip_country) != 2 or not ip_country.isalpha()):
        raise ValueError("O código do país deve possuir duas letras, como BR.")

    local_save_path = (
        settings.local_save_path.strip()
        if settings.local_save_path is not None
        else None
    )

    saves_folder_name = (
        settings.saves_folder_name.strip()
        if settings.saves_folder_name is not None
        else None
    )

    lines = [
        "[user::general]",
        f"account_name={account_name}",
    ]

    if settings.account_steamid is not None:
        lines.append(f"account_steamid={settings.account_steamid}")

    if language:
        lines.append(f"language={language}")

    if ip_country:
        lines.append(f"ip_country={ip_country}")

    if local_save_path:
        lines.extend(
            [
                "",
                "[user::saves]",
                f"local_save_path={local_save_path}",
            ]
        )

    elif saves_folder_name:
        lines.extend(
            [
                "",
                "[user::saves]",
                f"saves_folder_name={saves_folder_name}",
            ]
        )

    steam_settings_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_path = steam_settings_directory / "configs.user.ini"

    output_path.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )

    return output_path


def generate_game_steam_settings(
    game: Game,
    app_id: int,
    user_settings: SteamUserSettings,
) -> tuple[Path, Path]:
    if app_id <= 0:
        raise ValueError("O Steam AppID deve ser um número inteiro positivo.")

    steam_settings_directory = game.steam_api.parent / "steam_settings"

    user_config_path = generate_user_config(
        steam_settings_directory,
        user_settings,
    )

    app_id_path = generate_steam_appid(
        steam_settings_directory,
        app_id,
    )

    return app_id_path, user_config_path


def _read_optional_value(
    parser: configparser.ConfigParser,
    section: str,
    option: str,
) -> str | None:
    if not parser.has_option(section, option):
        return None

    value = parser.get(section, option).strip()

    return value or None


def read_steam_appid(
    steam_settings_directory: Path,
) -> int | None:
    app_id_path = steam_settings_directory / "steam_appid.txt"

    if not app_id_path.is_file():
        return None

    value = app_id_path.read_text(
        encoding="utf-8",
    ).strip()

    if not value:
        raise ValueError("steam_appid.txt está vazio.")

    try:
        app_id = int(value)
    except ValueError as exc:
        raise ValueError(f"Steam AppID inválido em {app_id_path}: {value!r}") from exc

    if app_id <= 0:
        raise ValueError(f"Steam AppID inválido em {app_id_path}: {app_id}")

    return app_id


def read_user_config(
    steam_settings_directory: Path,
) -> SteamSettingsSnapshot:
    config_path = steam_settings_directory / "configs.user.ini"

    snapshot = SteamSettingsSnapshot()

    if not config_path.is_file():
        return snapshot

    parser = configparser.ConfigParser(
        interpolation=None,
    )

    try:
        with config_path.open(
            "r",
            encoding="utf-8",
        ) as file:
            parser.read_file(file)
    except configparser.Error as exc:
        raise ValueError(f"configs.user.ini inválido: {exc}") from exc

    snapshot.account_name = _read_optional_value(
        parser,
        "user::general",
        "account_name",
    )

    steam_id = _read_optional_value(
        parser,
        "user::general",
        "account_steamid",
    )

    if steam_id is not None:
        try:
            snapshot.account_steamid = int(steam_id)
        except ValueError as exc:
            raise ValueError(
                f"SteamID64 inválido em configs.user.ini: {steam_id!r}"
            ) from exc

        if snapshot.account_steamid <= 0:
            raise ValueError(
                f"SteamID64 inválido em configs.user.ini: {snapshot.account_steamid}"
            )

    snapshot.language = _read_optional_value(
        parser,
        "user::general",
        "language",
    )

    snapshot.ip_country = _read_optional_value(
        parser,
        "user::general",
        "ip_country",
    )

    snapshot.local_save_path = _read_optional_value(
        parser,
        "user::saves",
        "local_save_path",
    )

    snapshot.saves_folder_name = _read_optional_value(
        parser,
        "user::saves",
        "saves_folder_name",
    )

    return snapshot


def read_game_steam_settings(
    game: Game,
) -> SteamSettingsSnapshot:
    steam_settings_directory = game.steam_api.parent / "steam_settings"

    snapshot = read_user_config(
        steam_settings_directory,
    )

    snapshot.app_id = read_steam_appid(
        steam_settings_directory,
    )

    snapshot.has_steam_interfaces = (
        steam_settings_directory / "steam_interfaces.txt"
    ).is_file()

    return snapshot


_USER_SETTING_LOCATIONS = {
    "account_name": (
        "user::general",
        "account_name",
    ),
    "account_steamid": (
        "user::general",
        "account_steamid",
    ),
    "language": (
        "user::general",
        "language",
    ),
    "ip_country": (
        "user::general",
        "ip_country",
    ),
    "local_save_path": (
        "user::saves",
        "local_save_path",
    ),
    "saves_folder_name": (
        "user::saves",
        "saves_folder_name",
    ),
}


def _find_ini_section(
    lines: list[str],
    section: str,
) -> tuple[int | None, int | None]:
    section_start: int | None = None

    for index, line in enumerate(lines):
        stripped = line.strip()

        if not (stripped.startswith("[") and stripped.endswith("]")):
            continue

        current_section = stripped[1:-1].strip()

        if section_start is not None:
            return section_start, index

        if current_section.casefold() == section.casefold():
            section_start = index

    if section_start is not None:
        return section_start, len(lines)

    return None, None


def _update_ini_option(
    path: Path,
    section: str,
    option: str,
    value: str | None,
) -> Path:
    if path.is_file():
        lines = path.read_text(
            encoding="utf-8",
        ).splitlines()
    else:
        lines = []

    section_start, section_end = _find_ini_section(
        lines,
        section,
    )

    if section_start is None:
        if value is None:
            return path

        if lines and lines[-1].strip():
            lines.append("")

        lines.extend(
            [
                f"[{section}]",
                f"{option}={value}",
            ]
        )

    else:
        assert section_end is not None

        option_index: int | None = None

        for index in range(
            section_start + 1,
            section_end,
        ):
            stripped = lines[index].lstrip()

            if not stripped:
                continue

            if stripped.startswith(("#", ";")):
                continue

            key, separator, _ = lines[index].partition("=")

            if separator and key.strip().casefold() == option.casefold():
                option_index = index
                break

        if value is None:
            if option_index is not None:
                del lines[option_index]

        elif option_index is not None:
            line = lines[option_index]

            indentation = line[: len(line) - len(line.lstrip())]

            lines[option_index] = f"{indentation}{option}={value}"

        else:
            insertion_index = section_end

            while (
                insertion_index > section_start + 1
                and not lines[insertion_index - 1].strip()
            ):
                insertion_index -= 1

            lines.insert(
                insertion_index,
                f"{option}={value}",
            )

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    if lines:
        content = "\n".join(lines) + "\n"
    else:
        content = ""

    path.write_text(
        content,
        encoding="utf-8",
    )

    return path


def update_user_setting(
    steam_settings_directory: Path,
    field: str,
    value: str | int | None,
) -> Path:
    location = _USER_SETTING_LOCATIONS.get(field)

    if location is None:
        raise ValueError(f"Configuração de usuário desconhecida: {field}")

    normalized_value: str | None

    if field == "account_name":
        if value is None:
            raise ValueError("O nome da conta não pode ficar vazio.")

        normalized_value = str(value).strip()

        if not normalized_value:
            raise ValueError("O nome da conta não pode ficar vazio.")

    elif field == "account_steamid":
        if value is None or not str(value).strip():
            normalized_value = None

        else:
            try:
                steam_id = int(value)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    "O SteamID deve ser um número inteiro positivo."
                ) from exc

            if steam_id <= 0:
                raise ValueError("O SteamID deve ser um número inteiro positivo.")

            normalized_value = str(steam_id)

    elif field == "ip_country":
        if value is None or not str(value).strip():
            normalized_value = None

        else:
            country = str(value).strip().upper()

            if len(country) != 2 or not country.isalpha():
                raise ValueError("O código do país deve possuir duas letras, como BR.")

            normalized_value = country

    else:
        if value is None:
            normalized_value = None
        else:
            normalized_value = str(value).strip() or None

    section, option = location

    config_path = steam_settings_directory / "configs.user.ini"

    _update_ini_option(
        config_path,
        section,
        option,
        normalized_value,
    )

    if field == "local_save_path" and normalized_value is not None:
        _update_ini_option(
            config_path,
            "user::saves",
            "saves_folder_name",
            None,
        )

    elif field == "saves_folder_name" and normalized_value is not None:
        _update_ini_option(
            config_path,
            "user::saves",
            "local_save_path",
            None,
        )

    return config_path


def update_game_steam_appid(
    game: Game,
    app_id: int,
) -> Path:
    if app_id <= 0:
        raise ValueError("O Steam AppID deve ser um número inteiro positivo.")

    steam_settings_directory = game.steam_api.parent / "steam_settings"

    return generate_steam_appid(
        steam_settings_directory,
        app_id,
    )
