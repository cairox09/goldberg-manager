from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class Game:
    name: str
    root_directory: Path
    executable: Path
    steam_api: Path
    steam_api_relative_path: Path
    architecture: str
    source_directory: Path
