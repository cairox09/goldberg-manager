from __future__ import annotations

from pathlib import Path


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
