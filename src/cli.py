from __future__ import annotations

import os
from pathlib import Path

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from config import AppConfig, load_config, save_config
from scanner import detect_games, detect_generate_interfaces

APP_NAME = "Goldberg Manager"
APP_VERSION = "0.1.0"


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
    subtitle = Text(
        f"v{APP_VERSION}  •  Linux / Proton / Wine / Heroic / Lutris", style="dim"
    )

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

    console.print(
        Panel(table, title="Menu principal", border_style="blue", box=box.ROUNDED)
    )


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
    console.print(
        Panel.fit(
            f"[bold yellow]{name}[/bold yellow]\n\nAinda não implementado.",
            border_style="yellow",
            box=box.ROUNDED,
        )
    )
    pause()


def add_game_directory(config: AppConfig) -> None:
    new_directory = questionary.text(
        "Digite o caminho do diretório de jogos:",
        default="",
    ).ask()

    if new_directory is None:
        return

    new_directory = new_directory.strip()

    if not new_directory:
        console.print("[yellow]Nenhum caminho informado.[/yellow]")
        pause()
        return

    directory = Path(new_directory).expanduser()

    if not directory.is_dir():
        console.print(f"[red]O diretório não existe:[/red] {directory}")
        pause()
        return

    directory = directory.resolve()

    if directory in config.games.directories:
        console.print("[yellow]Esse diretório já está cadastrado.[/yellow]")
        pause()
        return

    config.games.directories.append(directory)
    save_config(config)

    console.print(f"[green]Diretório adicionado:[/green] {directory}")
    pause()


def remove_game_directory(config: AppConfig) -> None:
    if not config.games.directories:
        console.print("[yellow]Nenhum diretório cadastrado.[/yellow]")
        pause()
        return

    choices = [str(path) for path in config.games.directories]
    choices.append("Cancelar")

    selected = questionary.select(
        "Escolha o diretório que deseja remover:",
        choices=choices,
    ).ask()

    if selected is None or selected == "Cancelar":
        return

    directory = Path(selected)

    if directory in config.games.directories:
        config.games.directories.remove(directory)
        save_config(config)
        console.print(f"[green]Diretório removido:[/green] {directory}")
        pause()


def show_games(config: AppConfig) -> None:
    clear_screen()
    render_header()

    if not config.games.directories:
        console.print(
            Panel.fit(
                "[yellow]Nenhum diretório de jogos foi configurado.[/yellow]\n\n"
                "Entre em Configurações e adicione um diretório.",
                border_style="yellow",
                box=box.ROUNDED,
            )
        )
        pause()
        return


    games = detect_games(config.games.directories)

    if not games:
        console.print(
            Panel.fit(
                "[yellow]Nenhum jogo compatível foi encontrado.[/yellow]",
                border_style="yellow",
                box=box.ROUNDED,
            )
        )
        pause()
        return

    table = Table(
        title="Jogos encontrados",
        box=box.ROUNDED,
        border_style="green",
    )

    table.add_column("#", style="bold cyan", justify="right", no_wrap=True)
    table.add_column("Jogo", style="bold")
    table.add_column("Arquitetura")
    table.add_column("Steam API")
    table.add_column("Executável")

    for index, game in enumerate(games, start=1):
        architecture = (
            "64-bit" if game.steam_api.name.lower() == "steam_api64.dll" else "32-bit"
        )

        table.add_row(
            str(index),
            game.name,
            architecture,
            game.steam_api.name,
            game.executable.name if game.executable else "N/A",
        )

    console.print(table)

    pause()


def show_settings(config: AppConfig) -> None:
    while True:
        clear_screen()
        render_header()
        table = Table.grid(padding=(0, 2))
        table.add_column(style="bold cyan", no_wrap=True)
        table.add_column(style="white")

        table.add_row("Tema", config.ui.theme)
        table.add_row("Goldberg root", str(config.goldberg.root))
        table.add_row(
            "Interfaces generator x64", str(config.goldberg.interfaces_generator_x64)
        )
        table.add_row(
            "Interfaces generator x86", str(config.goldberg.interfaces_generator_x86)
        )
        table.add_row("Emu config generator", str(config.goldberg.emu_config_generator))
        table.add_row(
            "Diretórios de jogos",
            "\n".join(str(path) for path in config.games.directories) or "(nenhum)",
        )

        console.print(
            Panel(
                table,
                title="Configurações atuais",
                border_style="green",
                box=box.ROUNDED,
            )
        )

        choice = questionary.select(
            "O que deseja fazer?",
            choices=[
                "Alterar tema",
                "Definir pasta do Goldberg",
                "Adicionar diretório de jogos",
                "Remover diretório de jogos",
                "Detectar generate_interfaces",
                "Salvar e voltar",
                "Voltar sem salvar",
            ],
        ).ask()

        if choice == "Alterar tema":
            new_theme = questionary.select(
                "Escolha o tema:",
                choices=["dark", "light", "system"],
            ).ask()

            if new_theme:
                config.ui.theme = new_theme
                save_config(config)
                console.print(f"[green]Tema salvo:[/green] {new_theme}")
                pause()

        elif choice == "Definir pasta do Goldberg":
            new_root = questionary.text(
                "Digite o caminho da pasta do Goldberg/GBE Fork:",
                default=str(config.goldberg.root or ""),
            ).ask()

            if new_root is not None:
                new_root = new_root.strip()
                if new_root:
                    config.goldberg.root = Path(new_root)
                else:
                    config.goldberg.root = None
                save_config(config)
                console.print("[green]Caminho salvo.[/green]")
                pause()

        elif choice == "Adicionar diretório de jogos":
            add_game_directory(config)

        elif choice == "Remover diretório de jogos":
            remove_game_directory(config)

        elif choice == "Detectar generate_interfaces":
            if config.goldberg.root is None:
                console.print("[red]Defina primeiro a pasta do Goldberg.[/red]")
                pause()
                continue

            x64, x86 = detect_generate_interfaces(config.goldberg.root)

            if x64 is None and x86 is None:
                console.print("[red]Nenhum generate_interfaces foi encontrado.[/red]")
                pause()
                continue

            config.goldberg.interfaces_generator_x64 = x64
            config.goldberg.interfaces_generator_x86 = x86
            save_config(config)

            console.print("[green]generate_interfaces detectado e salvo.[/green]")
            if x64:
                console.print(f"64-bit: {x64}")
            if x86:
                console.print(f"32-bit: {x86}")
            pause()

        elif choice == "Salvar e voltar":
            save_config(config)
            return

        else:
            return


def start() -> int:
    config = load_config()
    _ = config

    while True:
        clear_screen()
        render_header()
        render_menu()

        choice = ask_menu_choice()

        if choice == "1":
            show_games(config)
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
            show_settings(config)
        elif choice == "9":
            console.print("Saindo...")
            return 0
        else:
            console.print(f"Opção inválida: {choice}")
            pause()

    return 0
