from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .appid import (
    SteamStoreSearchError,
    get_game_search_query,
    resolve_local_appid,
    search_game_on_steam,
)
from .appid_cache import (
    get_cached_appid_search,
    save_appid_search_cache,
)
from .backup import (
    backup_game,
    current_file_matches_backup,
    has_backup,
    has_backup_metadata,
    restore_game_backup,
    verify_backup,
)
from .config import AppConfig, load_config, save_config
from .generators import generate_game_steam_interfaces
from .scanner import Game, detect_games, detect_generate_interfaces
from .settings import (
    SteamUserSettings,
    generate_game_steam_settings,
    read_game_steam_settings,
    update_game_steam_appid,
    update_user_setting,
)
from .settings_backup import (
    create_steam_settings_backup,
    get_steam_settings_directory,
    list_steam_settings_backups,
    restore_steam_settings_backup,
)

APP_NAME = "Goldberg Manager"
APP_VERSION = "0.1.0"


@dataclass(slots=True)
class GameAssistantStatus:
    app_id: int | None
    app_id_confidence: int | None
    app_id_configured: bool
    backup_exists: bool
    backup_valid: bool
    steam_settings_exists: bool
    steam_interfaces_exists: bool
    gbe_configured: bool

    @property
    def ready(self) -> bool:
        return (
            self.app_id is not None
            and self.app_id_configured
            and self.backup_exists
            and self.backup_valid
            and self.steam_settings_exists
            and self.steam_interfaces_exists
            and self.gbe_configured
        )


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
    ("2", "Configurar Goldberg/GBE para um jogo"),
    ("3", "Gerar steam_interfaces"),
    ("4", "Gerenciar steam_settings"),
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
            f"[bold yellow]{name}[/bold yellow]\n\n"
            "Esta funcionalidade ainda está em desenvolvimento.",
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


def get_menu_game(
    config: AppConfig,
    game: Game | None,
    message: str,
) -> Game | None:
    if game is not None:
        return game

    games = get_detected_games(config)

    if games is None:
        return None

    return select_game(
        games,
        message,
    )


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

        table.add_column(
            style="bold cyan",
            no_wrap=True,
        )

        table.add_column(style="white")

        table.add_row(
            "Tema",
            config.ui.theme,
        )
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


def generate_steam_interfaces_menu(
    config: AppConfig,
    game: Game | None = None,
) -> None:
    clear_screen()
    render_header()

    game = get_menu_game(
        config,
        game,
        "Selecione o jogo para gerar steam_interfaces:",
    )

    if game is None:
        return

    if not has_backup(game):
        console.print(
            "[yellow]Este jogo ainda não possui backup da Steam API original.[/yellow]"
        )
        console.print(
            "Crie primeiro um backup usando a opção [bold]Backup do jogo[/bold]."
        )
        pause()
        return

    if not verify_backup(game):
        console.print(
            "[red]O backup da Steam API não passou pela "
            "verificação de integridade.[/red]"
        )
        pause()
        return

    confirm = questionary.confirm(
        f"Gerar steam_interfaces.txt para {game.name}?",
        default=True,
    ).ask()

    if not confirm:
        return

    try:
        output_path = generate_game_steam_interfaces(
            game,
            config.goldberg.interfaces_generator_x64,
            config.goldberg.interfaces_generator_x86,
            command_prefix=("wine",),
        )
    except (FileNotFoundError, RuntimeError, ValueError, OSError) as exc:
        console.print(f"[red]Erro ao gerar steam_interfaces.txt:[/red] {exc}")
        pause()
        return

    console.print("[green]steam_interfaces.txt gerado com sucesso.[/green]")
    console.print(f"[dim]{output_path}[/dim]")
    pause()


def show_current_steam_settings_menu(
    config: AppConfig,
    game: Game | None = None,
) -> None:
    clear_screen()
    render_header()

    game = get_menu_game(
        config,
        game,
        "Selecione o jogo para visualizar steam_settings:",
    )

    if game is None:
        return

    try:
        snapshot = read_game_steam_settings(game)
    except (OSError, ValueError) as exc:
        console.print(f"[red]Erro ao ler steam_settings:[/red] {exc}")
        pause()
        return

    steam_settings_directory = game.steam_api.parent / "steam_settings"

    app_id_file = steam_settings_directory / "steam_appid.txt"

    user_config_file = steam_settings_directory / "configs.user.ini"

    interfaces_file = steam_settings_directory / "steam_interfaces.txt"

    if (
        not app_id_file.is_file()
        and not user_config_file.is_file()
        and not interfaces_file.is_file()
    ):
        console.print(
            Panel.fit(
                "[yellow]Nenhuma configuração "
                "steam_settings foi encontrada "
                "para este jogo.[/yellow]",
                border_style="yellow",
                box=box.ROUNDED,
            )
        )
        pause()
        return

    table = Table.grid(padding=(0, 2))
    table.add_column(
        style="bold cyan",
        no_wrap=True,
    )
    table.add_column(style="white")

    table.add_row(
        "Jogo",
        game.name,
    )

    table.add_row(
        "AppID",
        str(snapshot.app_id) if snapshot.app_id is not None else "(não definido)",
    )

    table.add_row(
        "Nick",
        snapshot.account_name or "(não definido)",
    )

    table.add_row(
        "SteamID64",
        str(snapshot.account_steamid)
        if snapshot.account_steamid is not None
        else "(não definido / automático)",
    )

    table.add_row(
        "Idioma",
        snapshot.language or "(não definido)",
    )

    table.add_row(
        "País",
        snapshot.ip_country or "(não definido)",
    )

    if snapshot.local_save_path:
        save_status = f"Local/portátil: {snapshot.local_save_path}"

    elif snapshot.saves_folder_name:
        save_status = f"Pasta global: {snapshot.saves_folder_name}"

    else:
        save_status = "Padrão / não definido"

    table.add_row(
        "Saves",
        save_status,
    )

    table.add_row(
        "steam_appid.txt",
        "Presente" if app_id_file.is_file() else "Ausente",
    )

    table.add_row(
        "configs.user.ini",
        "Presente" if user_config_file.is_file() else "Ausente",
    )

    table.add_row(
        "steam_interfaces.txt",
        "Presente" if snapshot.has_steam_interfaces else "Ausente",
    )

    console.print(
        Panel(
            table,
            title="Configuração atual",
            border_style="green",
            box=box.ROUNDED,
        )
    )

    console.print()
    console.print(f"[dim]{steam_settings_directory}[/dim]")

    pause()


def create_settings_safety_backup(
    game: Game,
) -> bool:
    steam_settings_directory = get_steam_settings_directory(game)

    if not steam_settings_directory.is_dir():
        return True

    if not any(path.is_file() for path in steam_settings_directory.rglob("*")):
        return True

    try:
        snapshot_path = create_steam_settings_backup(game)

    except (
        FileNotFoundError,
        OSError,
        ValueError,
    ) as exc:
        console.print(f"[red]Não foi possível criar o backup de segurança:[/red] {exc}")

        console.print(
            "[yellow]A alteração foi cancelada "
            "para proteger a configuração atual.[/yellow]"
        )

        pause()
        return False

    console.print("[dim]Backup de segurança criado:[/dim]")
    console.print(f"[dim]{snapshot_path}[/dim]")

    return True


def edit_steam_settings_menu(
    config: AppConfig,
    game: Game | None = None,
) -> None:
    clear_screen()
    render_header()

    game = get_menu_game(
        config,
        game,
        "Selecione o jogo cuja configuração deseja editar:",
    )

    if game is None:
        return

    steam_settings_directory = game.steam_api.parent / "steam_settings"

    while True:
        clear_screen()
        render_header()

        try:
            snapshot = read_game_steam_settings(game)
        except (OSError, ValueError) as exc:
            console.print(f"[red]Erro ao ler steam_settings:[/red] {exc}")
            pause()
            return

        app_id_display = (
            str(snapshot.app_id) if snapshot.app_id is not None else "(não definido)"
        )

        nick_display = snapshot.account_name or "(não definido)"

        steam_id_display = (
            str(snapshot.account_steamid)
            if snapshot.account_steamid is not None
            else "(automático)"
        )

        language_display = snapshot.language or "(não definido)"

        country_display = snapshot.ip_country or "(não definido)"

        if snapshot.local_save_path:
            saves_display = f"Local/portátil: {snapshot.local_save_path}"

        elif snapshot.saves_folder_name:
            saves_display = f"Pasta global: {snapshot.saves_folder_name}"

        else:
            saves_display = "Padrão do GBE"

        choices = [
            f"AppID — {app_id_display}",
            f"Nick — {nick_display}",
            f"SteamID64 — {steam_id_display}",
            f"Idioma — {language_display}",
            f"País — {country_display}",
            f"Saves — {saves_display}",
            "Voltar",
        ]

        choice = questionary.select(
            f"Editar steam_settings de {game.name}:",
            choices=choices,
        ).ask()

        if choice is None or choice == "Voltar":
            return

        try:
            if choice.startswith("AppID —"):
                answer = questionary.text(
                    "Novo Steam AppID:",
                    default=(
                        str(snapshot.app_id) if snapshot.app_id is not None else ""
                    ),
                ).ask()

                if answer is None:
                    continue

                try:
                    app_id = int(answer.strip())

                    if app_id <= 0:
                        raise ValueError

                except ValueError:
                    console.print(
                        "[red]Steam AppID inválido. "
                        "Digite um número inteiro positivo.[/red]"
                    )
                    pause()
                    continue

                if not create_settings_safety_backup(game):
                    continue

                update_game_steam_appid(
                    game,
                    app_id,
                )

                console.print("[green]AppID atualizado com sucesso.[/green]")
                pause()

            elif choice.startswith("Nick —"):
                answer = questionary.text(
                    "Novo Nome/Nick:",
                    default=snapshot.account_name or "Player",
                ).ask()

                if answer is None:
                    continue

                if not create_settings_safety_backup(game):
                    continue

                update_user_setting(
                    steam_settings_directory,
                    "account_name",
                    answer,
                )

                console.print("[green]Nick atualizado com sucesso.[/green]")
                pause()

            elif choice.startswith("SteamID64 —"):
                answer = questionary.text(
                    "Novo SteamID64 (deixe vazio para voltar ao automático):",
                    default=(
                        str(snapshot.account_steamid)
                        if snapshot.account_steamid is not None
                        else ""
                    ),
                ).ask()

                if answer is None:
                    continue

                value = answer.strip() or None

                if not create_settings_safety_backup(game):
                    continue

                update_user_setting(
                    steam_settings_directory,
                    "account_steamid",
                    value,
                )

                if value is None:
                    console.print(
                        "[green]SteamID64 removido. "
                        "O GBE poderá usar o modo automático.[/green]"
                    )
                else:
                    console.print("[green]SteamID64 atualizado com sucesso.[/green]")

                pause()

            elif choice.startswith("Idioma —"):
                answer = questionary.text(
                    "Novo idioma (vazio remove a configuração):",
                    default=snapshot.language or "",
                ).ask()

                if answer is None:
                    continue

                if not create_settings_safety_backup(game):
                    continue

                update_user_setting(
                    steam_settings_directory,
                    "language",
                    answer.strip() or None,
                )

                console.print("[green]Idioma atualizado com sucesso.[/green]")
                pause()

            elif choice.startswith("País —"):
                answer = questionary.text(
                    "Novo país (duas letras; vazio remove):",
                    default=snapshot.ip_country or "",
                ).ask()

                if answer is None:
                    continue

                if not create_settings_safety_backup(game):
                    continue

                update_user_setting(
                    steam_settings_directory,
                    "ip_country",
                    answer.strip() or None,
                )

                console.print("[green]País atualizado com sucesso.[/green]")
                pause()

            elif choice.startswith("Saves —"):
                save_choice = questionary.select(
                    "Modo de saves:",
                    choices=[
                        "Usar save local/portátil",
                        "Usar pasta global personalizada",
                        "Usar padrão do GBE",
                        "Cancelar",
                    ],
                ).ask()

                if save_choice is None or save_choice == "Cancelar":
                    continue

                if save_choice == "Usar save local/portátil":
                    answer = questionary.text(
                        "Caminho dos saves locais:",
                        default=(snapshot.local_save_path or "./saves"),
                    ).ask()

                    if answer is None:
                        continue

                    path = answer.strip()

                    if not path:
                        console.print(
                            "[red]O caminho dos saves não pode ficar vazio.[/red]"
                        )
                        pause()
                        continue

                    if not create_settings_safety_backup(game):
                        continue

                    update_user_setting(
                        steam_settings_directory,
                        "local_save_path",
                        path,
                    )

                    console.print("[green]Save local/portátil ativado.[/green]")
                    pause()

                elif save_choice == "Usar pasta global personalizada":
                    answer = questionary.text(
                        "Nome da pasta global de saves:",
                        default=(snapshot.saves_folder_name or "GSE Saves"),
                    ).ask()

                    if answer is None:
                        continue

                    folder_name = answer.strip()

                    if not folder_name:
                        console.print(
                            "[red]O nome da pasta não pode ficar vazio.[/red]"
                        )
                        pause()
                        continue

                    if not create_settings_safety_backup(game):
                        continue

                    update_user_setting(
                        steam_settings_directory,
                        "saves_folder_name",
                        folder_name,
                    )

                    console.print("[green]Pasta global de saves atualizada.[/green]")
                    pause()

                elif save_choice == "Usar padrão do GBE":
                    if not create_settings_safety_backup(game):
                        continue

                    update_user_setting(
                        steam_settings_directory,
                        "local_save_path",
                        None,
                    )

                    update_user_setting(
                        steam_settings_directory,
                        "saves_folder_name",
                        None,
                    )

                    console.print(
                        "[green]Configuração personalizada de saves removida.[/green]"
                    )
                    pause()

        except (OSError, ValueError) as exc:
            console.print(
                f"[red]Não foi possível atualizar a configuração:[/red] {exc}"
            )
            pause()


def create_steam_settings_backup_menu(
    config: AppConfig,
    game: Game | None = None,
) -> None:
    clear_screen()
    render_header()

    game = get_menu_game(
        config,
        game,
        "Selecione o jogo para criar o backup de steam_settings:",
    )

    if game is None:
        return

    try:
        snapshot_path = create_steam_settings_backup(game)
    except (
        FileNotFoundError,
        OSError,
        ValueError,
    ) as exc:
        console.print(f"[red]Não foi possível criar o backup:[/red] {exc}")
        pause()
        return

    console.print("[green]Backup de steam_settings criado com sucesso![/green]")
    console.print(f"[dim]{snapshot_path}[/dim]")

    pause()


def list_steam_settings_backups_menu(
    config: AppConfig,
    game: Game | None = None,
) -> None:
    clear_screen()
    render_header()

    game = get_menu_game(
        config,
        game,
        "Selecione o jogo para listar os backups:",
    )

    if game is None:
        return

    try:
        backups = list_steam_settings_backups(game)
    except OSError as exc:
        console.print(f"[red]Não foi possível listar os backups:[/red] {exc}")
        pause()
        return

    if not backups:
        console.print(
            "[yellow]Nenhum backup de steam_settings "
            "foi encontrado para este jogo.[/yellow]"
        )
        pause()
        return

    table = Table(
        title=f"Backups de {game.name}",
        box=box.ROUNDED,
        border_style="green",
    )

    table.add_column(
        "#",
        justify="right",
        style="bold cyan",
    )
    table.add_column("Data")
    table.add_column(
        "Arquivos",
        justify="right",
    )
    table.add_column("Integridade")

    for index, backup in enumerate(
        backups,
        start=1,
    ):
        created_at = backup.created_at.astimezone()

        table.add_row(
            str(index),
            created_at.strftime("%d/%m/%Y %H:%M:%S"),
            str(backup.file_count),
            ("[green]Íntegro[/green]" if backup.valid else "[red]CORROMPIDO[/red]"),
        )

    console.print(table)

    console.print()
    console.print(f"[dim]Diretório: {backups[0].path.parent}[/dim]")

    pause()


def restore_steam_settings_backup_menu(
    config: AppConfig,
    game: Game | None = None,
) -> None:
    clear_screen()
    render_header()

    game = get_menu_game(
        config,
        game,
        "Selecione o jogo cujo backup deseja restaurar:",
    )

    if game is None:
        return

    try:
        backups = list_steam_settings_backups(game)
    except OSError as exc:
        console.print(f"[red]Não foi possível listar os backups:[/red] {exc}")
        pause()
        return

    if not backups:
        console.print(
            "[yellow]Nenhum backup de steam_settings "
            "foi encontrado para este jogo.[/yellow]"
        )
        pause()
        return

    choices: list[str] = []

    for index, backup in enumerate(
        backups,
        start=1,
    ):
        created_at = backup.created_at.astimezone()

        integrity = "íntegro" if backup.valid else "CORROMPIDO"

        choices.append(
            f"{index} - "
            f"{created_at.strftime('%d/%m/%Y %H:%M:%S')} "
            f"• {backup.file_count} arquivos "
            f"• {integrity}"
        )

    choices.append("Voltar")

    selected = questionary.select(
        "Selecione o backup:",
        choices=choices,
    ).ask()

    if selected is None or selected == "Voltar":
        return

    index = int(selected.split(" - ", 1)[0]) - 1

    backup = backups[index]

    if not backup.valid:
        console.print(
            "[red]Este backup está corrompido e não pode ser restaurado.[/red]"
        )
        pause()
        return

    console.print()

    table = Table.grid(padding=(0, 2))
    table.add_column(style="bold cyan")
    table.add_column()

    table.add_row(
        "Jogo",
        game.name,
    )
    table.add_row(
        "Backup",
        backup.created_at.astimezone().strftime("%d/%m/%Y %H:%M:%S"),
    )
    table.add_row(
        "Arquivos",
        str(backup.file_count),
    )
    table.add_row(
        "Integridade",
        "Íntegro",
    )

    console.print(
        Panel(
            table,
            title="Restaurar backup",
            border_style="yellow",
            box=box.ROUNDED,
        )
    )

    confirm = questionary.confirm(
        "Restaurar este snapshot? A configuração atual será substituída.",
        default=False,
    ).ask()

    if not confirm:
        return

    current_settings = get_steam_settings_directory(game)

    if current_settings.is_dir():
        try:
            safety_backup = create_steam_settings_backup(game)
        except (
            FileNotFoundError,
            OSError,
            ValueError,
        ) as exc:
            console.print(
                "[red]Não foi possível criar o "
                "backup de segurança antes da restauração:[/red] "
                f"{exc}"
            )
            console.print("[yellow]A restauração foi cancelada.[/yellow]")
            pause()
            return

        console.print(
            "[green]✓ Backup de segurança da configuração atual criado.[/green]"
        )
        console.print(f"[dim]{safety_backup}[/dim]")

    try:
        restored_path = restore_steam_settings_backup(
            game,
            backup.path,
        )
    except (
        OSError,
        ValueError,
    ) as exc:
        console.print(f"[red]Falha ao restaurar o backup:[/red] {exc}")
        pause()
        return

    console.print()
    console.print("[green]steam_settings restaurado com sucesso![/green]")
    console.print(f"[dim]{restored_path}[/dim]")

    pause()


def manage_steam_settings_backups_menu(
    config: AppConfig,
    game: Game | None = None,
) -> None:
    while True:
        clear_screen()
        render_header()

        choice = questionary.select(
            "Backups de steam_settings:",
            choices=[
                "Criar backup agora",
                "Ver backups",
                "Restaurar backup",
                "Voltar",
            ],
        ).ask()

        if choice is None or choice == "Voltar":
            return

        if choice == "Criar backup agora":
            create_steam_settings_backup_menu(
                config,
                game=game,
            )

        elif choice == "Ver backups":
            list_steam_settings_backups_menu(
                config,
                game=game,
            )

        elif choice == "Restaurar backup":
            restore_steam_settings_backup_menu(
                config,
                game=game,
            )


def manage_steam_settings_menu(
    config: AppConfig,
    game: Game | None = None,
) -> None:
    while True:
        clear_screen()
        render_header()

        choice = questionary.select(
            "Gerenciar steam_settings:",
            choices=[
                "Ver configuração atual",
                "Editar configuração",
                "Criar / substituir configuração",
                "Backups de configuração",
                "Voltar",
            ],
        ).ask()

        if choice is None or choice == "Voltar":
            return

        if choice == "Ver configuração atual":
            show_current_steam_settings_menu(
                config,
                game=game,
            )

        elif choice == "Editar configuração":
            edit_steam_settings_menu(
                config,
                game=game,
            )

        elif choice == "Criar / substituir configuração":
            generate_steam_settings_menu(
                config,
                game=game,
            )

        elif choice == "Backups de configuração":
            manage_steam_settings_backups_menu(
                config,
                game=game,
            )


def search_appid_on_steam_menu(
    game: Game,
) -> int | None:
    default_query = get_game_search_query(game)

    answer = questionary.text(
        "Pesquisar jogo na Steam:",
        default=default_query,
    ).ask()

    if answer is None:
        return None

    query = answer.strip()

    if not query:
        console.print("[yellow]Nenhum nome informado.[/yellow]")
        pause()
        return None

    console.print()

    try:
        candidates = get_cached_appid_search(query)
    except OSError:
        candidates = None

    if candidates is not None:
        console.print("[green]✓ Resultados carregados do cache local.[/green]")

    else:
        console.print(f"[dim]Pesquisando na Steam por: {query}[/dim]")

        try:
            candidates = search_game_on_steam(
                game,
                query=query,
            )

        except SteamStoreSearchError as exc:
            console.print(f"[red]Falha na pesquisa:[/red] {exc}")
            pause()
            return None

        try:
            save_appid_search_cache(
                query,
                candidates,
            )

        except OSError as exc:
            console.print(
                f"[yellow]Não foi possível salvar o cache da pesquisa:[/yellow] {exc}"
            )

    if not candidates:
        console.print("[yellow]Nenhum resultado encontrado na Steam Store.[/yellow]")
        pause()
        return None

    table = Table(
        title="Resultados da Steam Store",
        box=box.ROUNDED,
        border_style="cyan",
    )

    table.add_column(
        "#",
        justify="right",
        style="bold cyan",
    )
    table.add_column("Jogo")
    table.add_column("AppID")
    table.add_column("Similaridade")

    for index, candidate in enumerate(
        candidates,
        start=1,
    ):
        table.add_row(
            str(index),
            candidate.name,
            str(candidate.app_id),
            f"{candidate.score}%",
        )

    console.print(table)

    choices = [
        (f"{index} - {candidate.name} • {candidate.app_id} • {candidate.score}%")
        for index, candidate in enumerate(
            candidates,
            start=1,
        )
    ]

    choices.extend(
        [
            "Pesquisar novamente",
            "Digitar AppID manualmente",
            "Cancelar",
        ]
    )

    selected = questionary.select(
        "Selecione o jogo correto:",
        choices=choices,
    ).ask()

    if selected is None or selected == "Cancelar":
        return None

    if selected == "Pesquisar novamente":
        return search_appid_on_steam_menu(game)

    if selected == "Digitar AppID manualmente":
        answer = questionary.text(
            "Steam AppID:",
        ).ask()

        if answer is None:
            return None

        try:
            app_id = int(answer.strip())
        except ValueError:
            console.print("[red]Steam AppID inválido.[/red]")
            pause()
            return None

        if app_id <= 0:
            console.print("[red]Steam AppID inválido.[/red]")
            pause()
            return None

        return app_id

    index = (
        int(
            selected.split(
                " - ",
                1,
            )[0]
        )
        - 1
    )

    return candidates[index].app_id


def select_appid_for_game(
    game: Game,
) -> int | None:
    try:
        candidates = resolve_local_appid(game)
    except OSError as exc:
        console.print(f"[red]Erro ao procurar AppID localmente:[/red] {exc}")
        candidates = []

    if candidates:
        console.print()

        table = Table(
            title="Steam AppID encontrados",
            box=box.ROUNDED,
            border_style="cyan",
        )

        table.add_column(
            "#",
            justify="right",
            style="bold cyan",
        )
        table.add_column("Jogo")
        table.add_column("AppID")
        table.add_column("Confiança")
        table.add_column("Fonte")

        source_names = {
            "steam_appid.txt": "steam_appid.txt",
            "steam_manifest": "Biblioteca Steam",
        }

        for index, candidate in enumerate(
            candidates,
            start=1,
        ):
            table.add_row(
                str(index),
                candidate.name,
                str(candidate.app_id),
                f"{candidate.score}%",
                source_names.get(
                    candidate.source,
                    candidate.source,
                ),
            )

        console.print(table)

        choices = []

        for index, candidate in enumerate(
            candidates,
            start=1,
        ):
            choices.append(
                f"{index} - {candidate.name} • {candidate.app_id} • {candidate.score}%"
            )

        choices.extend(
            [
                "Pesquisar outro jogo na Steam",
                "Digitar AppID manualmente",
                "Cancelar",
            ]
        )

        selected = questionary.select(
            "Selecione o Steam AppID correto:",
            choices=choices,
        ).ask()

        if selected is None or selected == "Cancelar":
            return None

        if selected == "Pesquisar outro jogo na Steam":
            return search_appid_on_steam_menu(game)

        if selected != "Digitar AppID manualmente":
            index = (
                int(
                    selected.split(
                        " - ",
                        1,
                    )[0]
                )
                - 1
            )

            return candidates[index].app_id

    else:
        console.print(
            "[yellow]Nenhum Steam AppID pôde ser identificado automaticamente.[/yellow]"
        )

        selected = questionary.select(
            "Como deseja continuar?",
            choices=[
                "Pesquisar pelo nome do jogo na Steam",
                "Digitar AppID manualmente",
                "Cancelar",
            ],
        ).ask()

        if selected == "Pesquisar pelo nome do jogo na Steam":
            return search_appid_on_steam_menu(game)

        if selected is None or selected == "Cancelar":
            return None

    answer = questionary.text(
        "Steam AppID:",
    ).ask()

    if answer is None:
        return None

    try:
        app_id = int(answer.strip())
    except ValueError:
        console.print("[red]Steam AppID inválido.[/red]")
        pause()
        return None

    if app_id <= 0:
        console.print("[red]Steam AppID deve ser um número inteiro positivo.[/red]")
        pause()
        return None

    return app_id


def resolve_game_appid_menu(
    game: Game,
) -> None:
    app_id = select_appid_for_game(game)

    if app_id is None:
        return

    try:
        snapshot = read_game_steam_settings(game)
    except (OSError, ValueError) as exc:
        console.print(f"[red]Não foi possível ler steam_settings:[/red] {exc}")
        pause()
        return

    if snapshot.app_id == app_id:
        console.print()
        console.print("[green]Este AppID já está configurado para o jogo.[/green]")
        console.print(f"[bold cyan]{app_id}[/bold cyan]")
        pause()
        return

    console.print()

    confirm = questionary.confirm(
        f"Definir Steam AppID {app_id} para {game.name}?",
        default=True,
    ).ask()

    if not confirm:
        return

    if not create_settings_safety_backup(game):
        return

    try:
        output_path = update_game_steam_appid(
            game,
            app_id,
        )
    except (OSError, ValueError) as exc:
        console.print(f"[red]Não foi possível salvar o AppID:[/red] {exc}")
        pause()
        return

    console.print()
    console.print("[green]Steam AppID configurado com sucesso![/green]")
    console.print(f"[bold cyan]{app_id}[/bold cyan]")
    console.print(f"[dim]{output_path}[/dim]")

    pause()


def generate_steam_settings_menu(
    config: AppConfig,
    game: Game | None = None,
) -> None:
    clear_screen()
    render_header()

    game = get_menu_game(
        config,
        game,
        "Selecione o jogo para configurar steam_settings:",
    )

    if game is None:
        return

    app_id = select_appid_for_game(game)

    if app_id is None:
        return

    account_name = questionary.text(
        "Nome/Nick:",
        default="Player",
    ).ask()

    if account_name is None:
        return

    account_name = account_name.strip()

    if not account_name:
        console.print("[red]O nome da conta não pode ficar vazio.[/red]")
        pause()
        return

    steam_id_answer = questionary.text(
        "SteamID64 (deixe vazio para não definir):",
        default="",
    ).ask()

    if steam_id_answer is None:
        return

    steam_id_answer = steam_id_answer.strip()

    account_steamid: int | None = None

    if steam_id_answer:
        try:
            account_steamid = int(steam_id_answer)

            if account_steamid <= 0:
                raise ValueError
        except ValueError:
            console.print(
                "[red]SteamID64 inválido. Digite somente números ou deixe vazio.[/red]"
            )
            pause()
            return

    language = questionary.text(
        "Idioma:",
        default="brazilian",
    ).ask()

    if language is None:
        return

    language = language.strip() or None

    ip_country = questionary.text(
        "País (código de duas letras):",
        default="BR",
    ).ask()

    if ip_country is None:
        return

    ip_country = ip_country.strip() or None

    use_local_save = questionary.confirm(
        "Usar saves locais/portáteis?",
        default=True,
    ).ask()

    if use_local_save is None:
        return

    local_save_path: str | None = None
    saves_folder_name: str | None = None

    if use_local_save:
        local_save_answer = questionary.text(
            "Caminho dos saves locais:",
            default="./saves",
        ).ask()

        if local_save_answer is None:
            return

        local_save_path = local_save_answer.strip()

        if not local_save_path:
            console.print("[red]O caminho dos saves não pode ficar vazio.[/red]")
            pause()
            return

    else:
        saves_folder_answer = questionary.text(
            "Nome personalizado da pasta global de saves "
            "(deixe vazio para usar o padrão):",
            default="",
        ).ask()

        if saves_folder_answer is None:
            return

        saves_folder_name = saves_folder_answer.strip() or None

    user_settings = SteamUserSettings(
        account_name=account_name,
        account_steamid=account_steamid,
        language=language,
        ip_country=ip_country,
        local_save_path=local_save_path,
        saves_folder_name=saves_folder_name,
    )

    steam_settings_directory = game.steam_api.parent / "steam_settings"

    app_id_path = steam_settings_directory / "steam_appid.txt"

    user_config_path = steam_settings_directory / "configs.user.ini"

    table = Table.grid(padding=(0, 2))
    table.add_column(style="bold cyan")
    table.add_column()

    table.add_row("Jogo", game.name)
    table.add_row("AppID", str(app_id))
    table.add_row("Nick", account_name)
    table.add_row(
        "SteamID64",
        str(account_steamid) if account_steamid is not None else "(não definido)",
    )
    table.add_row(
        "Idioma",
        language or "(não definido)",
    )
    table.add_row(
        "País",
        ip_country or "(não definido)",
    )

    if local_save_path:
        table.add_row(
            "Save",
            f"Local/portátil: {local_save_path}",
        )
    elif saves_folder_name:
        table.add_row(
            "Save",
            f"Pasta global: {saves_folder_name}",
        )
    else:
        table.add_row(
            "Save",
            "Configuração padrão",
        )

    console.print(
        Panel(
            table,
            title="Configuração a ser gerada",
            border_style="cyan",
            box=box.ROUNDED,
        )
    )

    existing_files = [
        path
        for path in (
            app_id_path,
            user_config_path,
        )
        if path.exists()
    ]

    if existing_files:
        console.print(
            "[yellow]Atenção: os seguintes arquivos "
            "já existem e serão substituídos:[/yellow]"
        )

        for path in existing_files:
            console.print(f"[yellow]• {path}[/yellow]")

    confirm = questionary.confirm(
        "Gerar esta configuração?",
        default=not existing_files,
    ).ask()

    if not confirm:
        return

    if not create_settings_safety_backup(game):
        return

    try:
        generated_app_id, generated_user_config = generate_game_steam_settings(
            game,
            app_id,
            user_settings,
        )
    except (OSError, ValueError) as exc:
        console.print(f"[red]Erro ao gerar steam_settings:[/red] {exc}")
        pause()
        return

    console.print()
    console.print("[green]steam_settings gerado com sucesso![/green]")
    console.print(f"[green]✓[/green] {generated_app_id}")
    console.print(f"[green]✓[/green] {generated_user_config}")

    steam_interfaces = steam_settings_directory / "steam_interfaces.txt"

    if steam_interfaces.is_file():
        console.print(f"[green]✓[/green] {steam_interfaces} [dim](preservado)[/dim]")

    pause()


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


def get_game_assistant_status(
    config: AppConfig,
    game: Game,
) -> GameAssistantStatus:
    steam_settings_directory = game.steam_api.parent / "steam_settings"

    steam_interfaces = steam_settings_directory / "steam_interfaces.txt"

    user_config = steam_settings_directory / "configs.user.ini"

    try:
        snapshot = read_game_steam_settings(game)
    except (OSError, ValueError):
        snapshot = None

    app_id: int | None = None
    app_id_confidence: int | None = None
    app_id_configured = False

    if snapshot is not None and snapshot.app_id is not None:
        app_id = snapshot.app_id
        app_id_confidence = 100
        app_id_configured = True

    else:
        try:
            candidates = resolve_local_appid(game)
        except OSError:
            candidates = []

        if candidates:
            best = candidates[0]

            app_id = best.app_id
            app_id_confidence = best.score

    backup_exists = has_backup(game)

    backup_valid = backup_exists and verify_backup(game)

    return GameAssistantStatus(
        app_id=app_id,
        app_id_confidence=app_id_confidence,
        app_id_configured=app_id_configured,
        backup_exists=backup_exists,
        backup_valid=backup_valid,
        steam_settings_exists=(user_config.is_file()),
        steam_interfaces_exists=(steam_interfaces.is_file()),
        gbe_configured=(config.goldberg.root is not None),
    )


def goldberg_game_assistant_menu(
    config: AppConfig,
) -> None:
    clear_screen()
    render_header()

    games = get_detected_games(config)

    if games is None:
        return

    game = select_game(
        games,
        "Selecione o jogo para configurar Goldberg/GBE:",
    )

    if game is None:
        return

    while True:
        clear_screen()
        render_header()

        status = get_game_assistant_status(
            config,
            game,
        )

        table = Table.grid(padding=(0, 2))

        table.add_column(
            style="bold cyan",
            no_wrap=True,
        )

        table.add_column(style="white")

        if status.ready:
            general_status = "[bold green]✓ PRONTO[/bold green]"
        else:
            general_status = "[bold yellow]⚠ INCOMPLETO[/bold yellow]"

        table.add_row(
            "Status geral",
            general_status,
        )

        table.add_row(
            "",
            "",
        )

        table.add_row(
            "Jogo",
            game.name,
        )

        table.add_row(
            "Arquitetura",
            game.architecture,
        )

        if status.app_id is not None:
            if status.app_id_confidence == 100:
                app_id_status = f"[green]✓ {status.app_id}[/green]"

            else:
                confidence = (
                    status.app_id_confidence
                    if status.app_id_confidence is not None
                    else 0
                )

                app_id_status = (
                    f"[yellow]⚠ {status.app_id} ({confidence}% provável)[/yellow]"
                )

        else:
            app_id_status = "[red]✗ Não identificado[/red]"

        table.add_row(
            "Steam AppID",
            app_id_status,
        )

        if not status.backup_exists:
            backup_status = "[yellow]⚠ Ausente[/yellow]"

        elif status.backup_valid:
            backup_status = "[green]✓ Íntegro[/green]"

        else:
            backup_status = "[red]✗ CORROMPIDO[/red]"

        table.add_row(
            "Backup Steam API",
            backup_status,
        )

        table.add_row(
            "steam_settings",
            (
                "[green]✓ Presente[/green]"
                if status.steam_settings_exists
                else "[yellow]⚠ Ausente[/yellow]"
            ),
        )

        table.add_row(
            "steam_interfaces",
            (
                "[green]✓ Presente[/green]"
                if status.steam_interfaces_exists
                else "[yellow]⚠ Ausente[/yellow]"
            ),
        )

        table.add_row(
            "GBE configurado",
            (
                "[green]✓ Sim[/green]"
                if status.gbe_configured
                else "[yellow]⚠ Não[/yellow]"
            ),
        )

        console.print(
            Panel(
                table,
                title="Assistente Goldberg / GBE",
                border_style=("green" if status.ready else "yellow"),
                box=box.ROUNDED,
            )
        )

        choice = questionary.select(
            "O que deseja fazer?",
            choices=[
                "Detectar / configurar Steam AppID",
                "Gerenciar steam_settings",
                "Gerar steam_interfaces",
                "Fazer backup da Steam API",
                "Restaurar Steam API original",
                "Ver detalhes do jogo",
                "Voltar",
            ],
        ).ask()

        if choice is None or choice == "Voltar":
            return

        if choice == "Detectar / configurar Steam AppID":
            resolve_game_appid_menu(game)

        elif choice == "Gerenciar steam_settings":
            manage_steam_settings_menu(
                config,
                game=game,
            )

        elif choice == "Gerar steam_interfaces":
            generate_steam_interfaces_menu(
                config,
                game=game,
            )

        elif choice == "Fazer backup da Steam API":
            create_game_backup(game)

        elif choice == "Restaurar Steam API original":
            restore_game_api(game)

        elif choice == "Ver detalhes do jogo":
            show_game_details(game)


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
            goldberg_game_assistant_menu(config)

        elif choice == "3":
            generate_steam_interfaces_menu(config)

        elif choice == "4":
            manage_steam_settings_menu(config)

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
