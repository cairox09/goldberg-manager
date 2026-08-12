from __future__ import annotations

import os
import subprocess
from pathlib import Path

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .backup import (
    backup_game,
    current_file_matches_backup,
    has_backup,
    has_backup_metadata,
    restore_game_backup,
    verify_backup,
)
from .config import AppConfig, load_config, save_config
from .scanner import Game, detect_games, detect_generate_interfaces

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


def create_game_backup(game) -> None:
    if has_backup(game):
        console.print(
            "[yellow]Já existe um backup da Steam API para este jogo.[/yellow]"
        )
        pause()
        return

    confirm = questionary.confirm(
        "Deseja criar um backup da Steam API original?",
        default=True,
    ).ask()

    if not confirm:
        return

    try:
        backup_path = backup_game(game)
    except (OSError, FileExistsError) as exc:
        console.print(f"[red]Erro ao criar backup:[/red] {exc}")
        pause()
        return

    console.print("[green]Backup criado com sucesso.[/green]")
    console.print(f"[dim]{backup_path}[/dim]")
    pause()


def restore_game_api(game) -> None:
    if not has_backup(game):
        console.print("[yellow]Nenhum backup foi encontrado para este jogo.[/yellow]")
        pause()
        return

    confirm = questionary.confirm(
        "Restaurar a Steam API original?",
        default=False,
    ).ask()

    if not confirm:
        return

    try:
        restore_game_backup(game)
    except (OSError, ValueError) as exc:
        console.print(f"[red]Erro ao restaurar backup:[/red] {exc}")
        pause()
        return

    console.print("[green]Steam API original restaurada com sucesso.[/green]")
    pause()


def show_game_details(game) -> None:
    while True:
        clear_screen()
        render_header()

        table = Table.grid(padding=(0, 2))
        table.add_column(style="bold cyan", no_wrap=True)
        table.add_column(style="white")

        table.add_row("Nome", game.name)
        table.add_row("Arquitetura", game.architecture)
        table.add_row("Raiz do jogo", str(game.root_directory))
        table.add_row("Executável", str(game.executable))
        table.add_row("Steam API", str(game.steam_api))
        table.add_row(
            "Steam API relativa",
            str(game.steam_api_relative_path),
        )
        if not has_backup(game):
            backup_status = "Não"
        elif not has_backup_metadata(game):
            backup_status = "Sim • sem metadados"
        elif verify_backup(game):
            backup_status = "Sim • íntegro"
        else:
            backup_status = "Sim • CORROMPIDO"

        table.add_row("Backup", backup_status)
        if not has_backup(game):
            current_status = "Desconhecido"
        elif current_file_matches_backup(game):
            current_status = "Original"
        else:
            current_status = "Modificado"

        table.add_row("Steam API atual", current_status)
        table.add_row(
            "Origem da detecção",
            str(game.source_directory),
        )

        console.print(
            Panel(
                table,
                title="Detalhes do jogo",
                border_style="green",
                box=box.ROUNDED,
            )
        )

        choice = questionary.select(
            "O que deseja fazer?",
            choices=[
                "Fazer backup da Steam API",
                "Restaurar Steam API original",
                "Voltar",
            ],
        ).ask()

        if choice == "Fazer backup da Steam API":
            create_game_backup(game)

        elif choice == "Restaurar Steam API original":
            restore_game_api(game)

        else:
            return


def get_detected_games(config: AppConfig) -> list[Game] | None:
    if not config.games.directories:
        console.print("[yellow]Nenhum diretório de jogos foi configurado.[/yellow]")
        console.print("Adicione um diretório em Configurações.")
        pause()
        return None

    games = detect_games(config.games.directories)

    if not games:
        console.print("[yellow]Nenhum jogo compatível foi encontrado.[/yellow]")
        pause()
        return None

    return games


def select_game(
    games: list[Game],
    message: str = "Selecione um jogo:",
) -> Game | None:
    choices = [
        f"{index} - {game.name} [{game.architecture}]"
        for index, game in enumerate(games, start=1)
    ]

    choices.append("Voltar")

    selected = questionary.select(
        message,
        choices=choices,
    ).ask()

    if selected is None or selected == "Voltar":
        return None

    index = int(selected.split(" - ", 1)[0]) - 1

    return games[index]


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
        table.add_row(
            str(index),
            game.name,
            game.architecture,
            game.steam_api.name,
            game.executable.name,
        )

    console.print(table)

    choices = [game.name for game in games]
    choices.append("Voltar")

    selected = questionary.select(
        "Selecione um jogo:",
        choices=choices,
    ).ask()

    if selected is None or selected == "Voltar":
        return

    selected_game = next(game for game in games if game.name == selected)

    show_game_details(selected_game)


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


def backup_game_menu(config: AppConfig) -> None:
    clear_screen()
    render_header()

    games = get_detected_games(config)

    if games is None:
        return

    game = select_game(
        games,
        "Selecione o jogo para criar o backup:",
    )

    if game is None:
        return

    create_game_backup(game)


def restore_game_menu(config: AppConfig) -> None:
    clear_screen()
    render_header()

    games = get_detected_games(config)

    if games is None:
        return

    game = select_game(
        games,
        "Selecione o jogo que deseja restaurar:",
    )

    if game is None:
        return

    restore_game_api(game)


def open_game_directory_menu(config: AppConfig) -> None:
    clear_screen()
    render_header()

    games = get_detected_games(config)

    if games is None:
        return

    game = select_game(
        games,
        "Selecione o jogo cuja pasta deseja abrir:",
    )

    if game is None:
        return

    try:
        subprocess.run(
            ["xdg-open", str(game.root_directory)],
            check=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        console.print(f"[red]Não foi possível abrir a pasta do jogo:[/red] {exc}")
        pause()


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
            backup_game_menu(config)

        elif choice == "6":
            restore_game_menu(config)

        elif choice == "7":
            open_game_directory_menu(config)

        elif choice == "8":
            show_settings(config)
        elif choice == "9":
            console.print("Saindo...")
            return 0
        else:
            console.print(f"Opção inválida: {choice}")
            pause()

    return 0
