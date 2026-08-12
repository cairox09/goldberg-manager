from __future__ import annotations

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
