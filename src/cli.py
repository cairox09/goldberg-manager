#!/usr/bin/env python3
"""Goldberg Manager - Step 1

Base inicial da interface de terminal usando Rich + Questionary.

Executar no Fish sem usar `pip` diretamente:

    python3 -m pip install --user rich questionary

Se o `pip` estiver quebrando no Fish, o mais seguro é sempre chamar o módulo:

    python3 -m pip ...

ou criar um ambiente virtual:

    python3 -m venv .venv
    source .venv/bin/activate.fish
    python -m pip install rich questionary

"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


APP_NAME = "Goldberg Manager"
APP_VERSION = "0.1.0"


@dataclass(slots=True)
class AppConfig:
    goldberg_root: Optional[Path] = None
    theme: str = "dark"


class MissingDependencyError(RuntimeError):
    pass


def _require_dependency(name: str):
    try:
        return __import__(name)
    except Exception as exc:  # pragma: no cover - user-facing bootstrap
        raise MissingDependencyError(
            f"Dependência ausente: {name}. Instale com: python3 -m pip install --user {name}"
        ) from exc


rich = _require_dependency("rich")
questionary = _require_dependency("questionary")

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box

console = Console()


MENU_ITEMS = [
    ("1", "Detectar jogos"),
    ("2", "Instalar Goldberg em um jogo"),
    ("3", "Gerar steam_interfaces"),
    ("4", "Gerar steam_settings"),
    ("5", "Backup do jogo"),
    ("6", "Restaurar backup"),
    ("7", "Abrir pasta do jogo"),
    ("8", "Configurações"),
    ("9", "Sair"),
]


def clear_screen() -> None:
    os.system("clear" if os.name != "nt" else "cls")


def render_header() -> None:
    title = Text(f"{APP_NAME}", style="bold")
    subtitle = Text(f"v{APP_VERSION}  •  Linux / Proton / Wine / Heroic / Lutris", style="dim")

    panel = Panel.fit(
        Text.assemble(title, "\n", subtitle),
        box=box.ROUNDED,
        border_style="cyan",
        padding=(1, 2),
    )
    console.print(panel)


def render_menu() -> None:
    table = Table.grid(padding=(0, 2))
    table.add_column(justify="right", style="bold cyan", no_wrap=True)
    table.add_column(style="white")

    for key, label in MENU_ITEMS:
        table.add_row(key, label)

    console.print(Panel(table, title="Menu principal", border_style="blue", box=box.ROUNDED))


def ask_menu_choice() -> str:
    choices = [f"{key} - {label}" for key, label in MENU_ITEMS]
    answer = questionary.select(
        "Escolha uma ação:",
        choices=choices,
        use_shortcuts=True,
        use_arrow_keys=True,
    ).ask()
    if not answer:
        return "9"
    return answer.split(" - ", 1)[0].strip()


def pause(message: str = "Pressione Enter para continuar...") -> None:
    try:
        input(message)
    except EOFError:
        pass


def show_placeholder(name: str) -> None:
    console.print(Panel.fit(f"[bold yellow]{name}[/bold yellow]\n\nAinda não implementado.", border_style="yellow", box=box.ROUNDED))
    pause()


def load_config() -> AppConfig:
    # Fase 1: configuração em memória. Depois vamos ler config.yaml aqui.
    return AppConfig()


def start() -> int:
        config = load_config()
        _ = config
    
        while True:
            clear_screen()
            render_header()
            render_menu()
    
            choice = ask_menu_choice()
    
            if choice == "1":
                clear_screen()
                render_header()
                show_placeholder("Detectar jogos")
            elif choice == "2":
                clear_screen()
                render_header()
                show_placeholder("Instalar Goldberg em um jogo")
            elif choice == "3":
                clear_screen()
                render_header()
                show_placeholder("Gerar steam_interfaces")
            elif choice == "4":
                clear_screen()
                render_header()
                show_placeholder("Gerar steam_settings")
            elif choice == "5":
                clear_screen()
                render_header()
                show_placeholder("Backup do jogo")
            elif choice == "6":
                clear_screen()
                render_header()
                show_placeholder("Restaurar backup")
            elif choice == "7":
                clear_screen()
                render_header()
                show_placeholder("Abrir pasta do jogo")
            elif choice == "8":
                clear_screen()
                render_header()
                show_placeholder("Configurações")
            elif choice == "9":
                console.print("Saindo...")
                return 0
            else:
                console.print(f"Opção inválida: {choice}")
                pause()
    
        return 0
