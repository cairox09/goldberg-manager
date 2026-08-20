from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from rich import box
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .achievements import (
    AchievementDataError,
    AchievementReport,
)
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
from .emu_config import (
    EmuConfigError,
    EmuConfigSummary,
    import_generated_achievements,
    read_generated_emu_summary,
    read_generated_supported_languages,
    read_installed_achievements_status,
    run_generate_emu_config,
)
from .game_profile import GameProfile, resolve_game_profile
from .game_resolution import (
    AchievementReadError as _AchievementReadError,
)
from .game_resolution import (
    GameAchievementResolution,
    GameGseResolution,
    GameSentinelIntegrationResolution,
)
from .game_resolution import (
    resolve_game_achievement_progress as resolve_game_achievement_progress_domain,
)
from .game_resolution import (
    resolve_game_gse_runtime as resolve_game_gse_runtime_domain,
)
from .game_resolution import (
    resolve_game_sentinel_integration as resolve_game_sentinel_integration_domain,
)
from .generators import generate_game_steam_interfaces
from .scanner import (
    Game,
    GameCandidate,
    detect_emu_config_generator,
    detect_games,
    detect_generate_interfaces,
    discover_game_candidates,
)
from .sentinel import (
    SENTINEL_GSE_EMULATOR_ID,
    SentinelConfigStatus,
    SentinelRuntimeSave,
    detect_sentinel,
    discover_sentinel_drive_c_paths,
    read_sentinel_config,
    resolve_sentinel_runtime_saves,
    resolve_sentinel_save_roots,
)
from .sentinel_config_writer import (
    SentinelConfigWriteReason,
    SentinelConfigWriteResult,
    SentinelConfigWriteStatus,
    apply_sentinel_config_repair,
)
from .sentinel_integration import (
    resolve_sentinel_gse_coverage,
)
from .sentinel_repair import (
    SentinelRepairConfigState,
    SentinelRepairKind,
    SentinelRepairPlan,
    plan_sentinel_gse_repair,
)
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
from .settings_catalog import (
    STEAM_LANGUAGE_CHOICES,
    SettingChoice,
    get_country_choices,
    prioritize_setting_choices,
)

AchievementReadError = _AchievementReadError

APP_NAME = "Goldberg Manager"
APP_VERSION = "0.2.0"


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


@dataclass(frozen=True, slots=True)
class GameSentinelResolution:
    app_id: int | None
    app_id_confidence: int | None
    app_id_source: str | None
    runtime_saves: tuple[SentinelRuntimeSave, ...]

    @property
    def runtime_found(self) -> bool:
        return bool(self.runtime_saves)


def get_next_guided_step(
    status: GameAssistantStatus,
) -> str | None:
    if status.backup_exists and not status.backup_valid:
        return "blocked"

    if not status.gbe_configured:
        return "gbe"

    if not status.app_id_configured:
        return "appid"

    if not status.backup_exists:
        return "backup"

    if not status.steam_settings_exists:
        return "settings"

    if not status.steam_interfaces_exists:
        return "interfaces"

    return None


def resolve_game_sentinel_runtime(
    game: Game,
    *,
    status: SentinelConfigStatus | None = None,
) -> GameSentinelResolution:
    if status is None:
        installation = detect_sentinel()

        status = read_sentinel_config(
            installation.config_path,
        )

    app_id_candidates = resolve_local_appid(game)

    runtime_saves = resolve_sentinel_runtime_saves(
        status,
    )

    for candidate in app_id_candidates:
        matches = tuple(
            runtime_save
            for runtime_save in runtime_saves
            if runtime_save.app_id == candidate.app_id
        )

        if not matches:
            continue

        return GameSentinelResolution(
            app_id=candidate.app_id,
            app_id_confidence=candidate.score,
            app_id_source=candidate.source,
            runtime_saves=matches,
        )

    if not app_id_candidates:
        return GameSentinelResolution(
            app_id=None,
            app_id_confidence=None,
            app_id_source=None,
            runtime_saves=(),
        )

    best_candidate = app_id_candidates[0]

    return GameSentinelResolution(
        app_id=best_candidate.app_id,
        app_id_confidence=best_candidate.score,
        app_id_source=best_candidate.source,
        runtime_saves=(),
    )


def resolve_game_gse_runtime(
    game: Game,
    *,
    sentinel_status: SentinelConfigStatus | None = None,
) -> GameGseResolution:
    return resolve_game_gse_runtime_domain(
        game,
        sentinel_status=sentinel_status,
        sentinel_detector=detect_sentinel,
        sentinel_config_reader=read_sentinel_config,
        drive_c_discoverer=discover_sentinel_drive_c_paths,
        app_id_resolver=resolve_local_appid,
        settings_reader=read_game_steam_settings,
    )


def resolve_game_sentinel_integration(
    game: Game,
    *,
    sentinel_status: SentinelConfigStatus | None = None,
) -> GameSentinelIntegrationResolution:
    return resolve_game_sentinel_integration_domain(
        game,
        sentinel_status=sentinel_status,
        sentinel_detector=detect_sentinel,
        sentinel_config_reader=read_sentinel_config,
        gse_resolver=resolve_game_gse_runtime,
        coverage_resolver=resolve_sentinel_gse_coverage,
    )


def resolve_game_sentinel_repair(
    game: Game,
    *,
    sentinel_status: SentinelConfigStatus | None = None,
) -> SentinelRepairPlan:
    integration = resolve_game_sentinel_integration(
        game,
        sentinel_status=sentinel_status,
    )
    return plan_sentinel_gse_repair(integration.coverage)


def resolve_game_achievement_progress(
    game: Game,
    *,
    sentinel_status: SentinelConfigStatus | None = None,
) -> GameAchievementResolution:
    return resolve_game_achievement_progress_domain(
        game,
        sentinel_status=sentinel_status,
        gse_resolver=resolve_game_gse_runtime,
        settings_reader=read_game_steam_settings,
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


def _game_profile_table() -> Table:
    table = Table.grid(padding=(0, 2))
    table.add_column(style="bold cyan", no_wrap=True)
    table.add_column(style="white")
    return table


def _profile_display_value(value: object) -> str:
    return escape(str(value))


def _print_game_profile_section(
    title: str,
    table: Table,
    *,
    border_style: str = "cyan",
) -> None:
    console.print(
        Panel(
            table,
            title=title,
            border_style=border_style,
            box=box.ROUNDED,
        )
    )


def render_game_profile(profile: GameProfile) -> None:
    unavailable = "[dim]— Não disponível[/dim]"

    console.print(
        Panel.fit(
            f"[bold]{_profile_display_value(profile.game.name)}[/bold]",
            title="Perfil do jogo",
            border_style="cyan",
            box=box.ROUNDED,
        )
    )

    identity = _game_profile_table()
    if profile.app_id is None:
        app_id = "[dim]— Não identificado[/dim]"
    else:
        app_id_details = [
            detail
            for detail in (
                (
                    _profile_display_value(profile.app_id_source)
                    if profile.app_id_source is not None
                    else None
                ),
                (
                    f"{profile.app_id_confidence}%"
                    if profile.app_id_confidence is not None
                    else None
                ),
            )
            if detail is not None
        ]
        metadata = f" • {' • '.join(app_id_details)}" if app_id_details else ""
        app_id = f"[green]✓ {profile.app_id}[/green]{metadata}"
    identity.add_row("AppID", app_id)
    identity.add_row("Arquitetura", _profile_display_value(profile.architecture))
    identity.add_row("Executável", _profile_display_value(profile.game.executable))
    identity.add_row("Steam API", _profile_display_value(profile.game.steam_api))
    _print_game_profile_section("Identidade", identity)

    settings = _game_profile_table()
    settings_snapshot = profile.settings
    setting_values = (
        settings_snapshot.account_name,
        settings_snapshot.account_steamid,
        settings_snapshot.language,
        settings_snapshot.ip_country,
        settings_snapshot.local_save_path,
        settings_snapshot.saves_folder_name,
    )
    if not any(value is not None for value in setting_values):
        settings.add_row("Status", "[dim]— Nenhuma configuração identificada[/dim]")
    else:
        if settings_snapshot.account_name is not None:
            settings.add_row(
                "Conta", _profile_display_value(settings_snapshot.account_name)
            )
        if settings_snapshot.account_steamid is not None:
            settings.add_row("SteamID", str(settings_snapshot.account_steamid))
        if settings_snapshot.language is not None:
            settings.add_row(
                "Idioma", _profile_display_value(settings_snapshot.language)
            )
        if settings_snapshot.ip_country is not None:
            settings.add_row(
                "País", _profile_display_value(settings_snapshot.ip_country)
            )
        if settings_snapshot.local_save_path is not None:
            settings.add_row(
                "local_save_path",
                _profile_display_value(settings_snapshot.local_save_path),
            )
        if settings_snapshot.saves_folder_name is not None:
            settings.add_row(
                "saves_folder_name",
                _profile_display_value(settings_snapshot.saves_folder_name),
            )
    _print_game_profile_section("Settings", settings)

    saves = _game_profile_table()
    save_resolution = profile.gse.save_resolution
    if save_resolution is None:
        saves.add_row("Resolução", "[dim]— GSE save não identificado[/dim]")
    else:
        saves.add_row("Origem", _profile_display_value(save_resolution.source))
        if save_resolution.raw_value is not None:
            saves.add_row(
                "Valor configurado",
                _profile_display_value(save_resolution.raw_value),
            )

        effective_locations = save_resolution.effective_locations
        if save_resolution.ambiguous:
            saves.add_row("Resolução", "[yellow]⚠ Ambígua[/yellow]")
            saves.add_row("Save efetivo", "[dim]— Não determinado[/dim]")
        elif effective_locations:
            saves.add_row("Resolução", "[green]✓ Determinada[/green]")
            for location in effective_locations:
                saves.add_row("Save efetivo", _profile_display_value(location.root))
        else:
            saves.add_row("Resolução", "[dim]— Caminho não resolvido[/dim]")

        if save_resolution.ambiguous:
            for index, location in enumerate(save_resolution.locations, start=1):
                saves.add_row(
                    f"Save possível #{index}",
                    _profile_display_value(location.root),
                )
    _print_game_profile_section(
        "Saves / GSE",
        saves,
        border_style=(
            "yellow"
            if save_resolution is None
            or save_resolution.ambiguous
            or not save_resolution.effective_locations
            else "green"
        ),
    )

    achievements = _game_profile_table()
    achievement_resolution = profile.achievements
    metadata_error = next(
        (
            error
            for error in achievement_resolution.errors
            if error.path == achievement_resolution.metadata_path
        ),
        None,
    )
    if metadata_error is not None:
        metadata_status = (
            "[red]✗ Inválida[/red] • "
            f"{_profile_display_value(achievement_resolution.metadata_path)}"
        )
    elif achievement_resolution.metadata_exists:
        metadata_status = (
            "[green]✓ Encontrada[/green] • "
            f"{_profile_display_value(achievement_resolution.metadata_path)}"
        )
    else:
        metadata_status = (
            "[yellow]⚠ Não encontrada[/yellow] • "
            f"{_profile_display_value(achievement_resolution.metadata_path)}"
        )
    achievements.add_row("Metadata", metadata_status)
    runtime_reports = tuple(
        report
        for report in achievement_resolution.reports
        if report.runtime_path is not None
    )
    metadata_report = next(
        (
            report
            for report in achievement_resolution.reports
            if report.runtime_path is None
        ),
        None,
    )
    if runtime_reports:
        multiple_reports = len(runtime_reports) > 1
        for index, report in enumerate(runtime_reports, start=1):
            suffix = f" #{index}" if multiple_reports else ""
            achievements.add_row(
                f"Runtime{suffix}", _profile_display_value(report.runtime_path)
            )
            achievements.add_row(f"Total{suffix}", str(report.total))
            achievements.add_row(f"Desbloqueadas{suffix}", str(report.unlocked))
            achievements.add_row(f"Bloqueadas{suffix}", str(report.locked))
            achievements.add_row(
                f"Conclusão{suffix}",
                f"{report.completion_percentage:.1f}%",
            )
    else:
        achievements.add_row(
            "Total",
            str(metadata_report.total) if metadata_report is not None else unavailable,
        )
        achievements.add_row("Progresso", "[dim]— Runtime indisponível[/dim]")
    if achievement_resolution.errors:
        achievements.add_row(
            "Erros de leitura",
            f"[red]✗ {len(achievement_resolution.errors)}[/red]",
        )
    _print_game_profile_section(
        "Achievements",
        achievements,
        border_style="green" if runtime_reports else "yellow",
    )

    sentinel = _game_profile_table()
    installation = profile.sentinel.installation
    status = profile.sentinel.status
    coverage = profile.sentinel.coverage
    sentinel.add_row(
        "Instalação",
        (
            "[green]✓ Detectada[/green] • "
            f"{_profile_display_value(installation.executable)}"
            if installation.installed
            else "[yellow]⚠ Não detectada[/yellow]"
        ),
    )
    if not status.exists:
        config_status = "[yellow]⚠ Ausente[/yellow]"
    elif not status.valid_json or not status.schema_valid:
        config_status = "[red]✗ Inválida[/red]"
    else:
        config_status = "[green]✓ Válida[/green]"
    sentinel.add_row("Configuração", config_status)
    sentinel.add_row("Config path", _profile_display_value(status.path))
    if status.error is not None:
        sentinel.add_row(
            "Diagnóstico",
            f"[red]{_profile_display_value(status.error)}[/red]",
        )

    if coverage.fully_watched:
        coverage_status = "[green]✓ Cobertura completa[/green]"
    elif coverage.partially_watched:
        coverage_status = "[yellow]⚠ Cobertura parcial[/yellow]"
    elif coverage.unwatched:
        coverage_status = "[yellow]⚠ Save efetivo não coberto[/yellow]"
    elif coverage.effective_save_resolved:
        coverage_status = "[yellow]⚠ Cobertura não confirmada[/yellow]"
    else:
        coverage_status = "[dim]— Sem save efetivo para avaliar[/dim]"
    sentinel.add_row("Integração GSE", coverage_status)
    if coverage.recognized_by_sentinel:
        sentinel.add_row("Runtime Sentinel", "[green]✓ Reconhecido[/green]")
    _print_game_profile_section(
        "Sentinel",
        sentinel,
        border_style=(
            "green"
            if installation.installed and status.configured and coverage.fully_watched
            else "yellow"
        ),
    )

    heroic = _game_profile_table()
    heroic_provenance = profile.heroic
    if heroic_provenance.resolved:
        heroic.add_row("Status", "[green]✓ RESOLVED[/green]")
        heroic_match = heroic_provenance.effective
        assert heroic_match is not None
        heroic.add_row(
            "Runner",
            _profile_display_value(heroic_match.installed_game.id.runner),
        )
        heroic.add_row(
            "App name",
            _profile_display_value(heroic_match.installed_game.id.app_name),
        )
        heroic.add_row(
            "Evidência",
            (
                heroic_provenance.strongest_evidence.value
                if heroic_provenance.strongest_evidence is not None
                else unavailable
            ),
        )
        heroic.add_row(
            "Configured prefix",
            (
                _profile_display_value(heroic_match.prefix.configured_prefix)
                if heroic_match.prefix.configured_prefix is not None
                else unavailable
            ),
        )
        heroic.add_row(
            "Structural Wine prefix",
            (
                _profile_display_value(heroic_match.prefix.structural_wine_prefix)
                if heroic_match.prefix.structural_wine_prefix is not None
                else unavailable
            ),
        )
        heroic.add_row("Prefix layout", heroic_match.prefix.layout.name)
        heroic_border = (
            "green"
            if heroic_match.prefix.structural_wine_prefix is not None
            else "yellow"
        )
    elif heroic_provenance.ambiguous:
        heroic.add_row("Status", "[yellow]⚠ AMBIGUOUS[/yellow]")
        heroic.add_row("Ownership", "[yellow]Mais de um match Heroic[/yellow]")
        heroic.add_row("Candidates", str(len(heroic_provenance.candidates)))
        heroic_border = "yellow"
    else:
        heroic.add_row("Status", "[dim]UNKNOWN[/dim]")
        heroic.add_row("Ownership", "[dim]Heroic ownership não identificado.[/dim]")
        heroic_border = "cyan"
    _print_game_profile_section("Heroic", heroic, border_style=heroic_border)

    steam = _game_profile_table()
    steam_provenance = profile.steam
    if steam_provenance.resolved:
        steam.add_row("Status", "[green]✓ RESOLVED[/green]")
        steam_match = steam_provenance.effective
        steam_prefix = steam_provenance.prefix
        assert steam_match is not None
        assert steam_prefix is not None
        steam.add_row("AppID efetivo", str(steam_match.installed_game.app_id))
        steam.add_row(
            "Library",
            _profile_display_value(steam_match.installed_game.library_root),
        )
        steam.add_row(
            "Install path",
            _profile_display_value(steam_match.installed_game.install_path),
        )
        steam.add_row(
            "Evidência",
            (
                steam_provenance.strongest_evidence.value
                if steam_provenance.strongest_evidence is not None
                else unavailable
            ),
        )
        steam.add_row("Prefix layout", steam_prefix.layout.name)
        if steam_prefix.structural_wine_prefix is not None:
            steam.add_row(
                "Structural Wine prefix",
                _profile_display_value(steam_prefix.structural_wine_prefix),
            )
        steam_border = (
            "green" if steam_prefix.structural_wine_prefix is not None else "yellow"
        )
    elif steam_provenance.ambiguous:
        steam.add_row("Status", "[yellow]⚠ AMBIGUOUS[/yellow]")
        steam.add_row("Ownership", "[yellow]Mais de um match Steam[/yellow]")
        steam.add_row("Candidates", str(len(steam_provenance.candidates)))
        steam_border = "yellow"
    else:
        steam.add_row("Status", "[dim]UNKNOWN[/dim]")
        steam.add_row("Ownership", "[dim]Steam ownership não identificado.[/dim]")
        steam_border = "cyan"
    _print_game_profile_section("Steam", steam, border_style=steam_border)

    prefix = _game_profile_table()
    consensus = profile.prefix_consensus
    if consensus.resolved:
        prefix.add_row("Status", "[green]✓ RESOLVED[/green]")
        prefix.add_row(
            "Wine prefix efetivo",
            _profile_display_value(consensus.effective_wine_prefix),
        )
        prefix.add_row(
            "drive_c efetivo",
            _profile_display_value(consensus.effective_drive_c),
        )
        sources = ", ".join(evidence.source.name for evidence in consensus.evidences)
        prefix.add_row("Fontes" if len(consensus.evidences) > 1 else "Fonte", sources)
        prefix_border = "green"
    elif consensus.conflict:
        prefix.add_row("Status", "[red]✗ CONFLICT[/red]")
        prefix.add_row("Resultado", "[red]Nenhuma fonte foi selecionada.[/red]")
        for evidence in consensus.evidences:
            prefix.add_row(
                evidence.source.name,
                _profile_display_value(evidence.wine_prefix),
            )
        prefix_border = "red"
    else:
        prefix.add_row("Status", "[dim]UNKNOWN[/dim]")
        prefix.add_row(
            "Resultado",
            "[dim]Nenhuma evidência estrutural de prefix disponível.[/dim]",
        )
        prefix_border = "cyan"
    _print_game_profile_section(
        "Prefix Consensus",
        prefix,
        border_style=prefix_border,
    )


def show_game_profile(game: Game) -> None:
    clear_screen()
    render_header()

    try:
        profile = resolve_game_profile(game)
    except (OSError, ValueError) as error:
        console.print(
            Panel.fit(
                "[red]Não foi possível resolver o perfil do jogo.[/red]\n\n"
                f"{_profile_display_value(error)}",
                border_style="red",
                box=box.ROUNDED,
            )
        )
        pause()
        return

    render_game_profile(profile)
    console.print()
    console.print(
        "[dim]Somente leitura • nenhum arquivo ou configuração foi alterado.[/dim]"
    )
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
                "Ver perfil do jogo",
                "Verificar achievements / progresso",
                "Verificar GSE saves",
                "Verificar Sentinel",
                "Verificar integração Sentinel",
                "Corrigir integração Sentinel",
                "Fazer backup da Steam API",
                "Restaurar Steam API original",
                "Voltar",
            ],
        ).ask()

        if choice == "Ver perfil do jogo":
            show_game_profile(game)

        elif choice == "Verificar achievements / progresso":
            show_game_achievement_status(game)

        elif choice == "Verificar GSE saves":
            show_game_gse_status(game)

        elif choice == "Verificar Sentinel":
            show_game_sentinel_status(game)

        elif choice == "Verificar integração Sentinel":
            show_game_sentinel_integration_status(game)

        elif choice == "Corrigir integração Sentinel":
            repair_game_sentinel_integration(game)

        elif choice == "Fazer backup da Steam API":
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


def show_game_candidate_details(
    candidate: GameCandidate,
) -> None:
    clear_screen()
    render_header()

    table = Table.grid(padding=(0, 2))

    table.add_column(
        style="bold cyan",
        no_wrap=True,
    )

    table.add_column(
        style="white",
    )

    table.add_row(
        "Nome",
        candidate.name,
    )

    table.add_row(
        "Raiz do jogo",
        str(candidate.root_directory),
    )

    table.add_row(
        "Executável",
        str(candidate.executable),
    )

    table.add_row(
        "Steam API",
        "[yellow]Não localizada[/yellow]",
    )

    table.add_row(
        "Status",
        "[yellow]Não configurável[/yellow]",
    )

    table.add_row(
        "Origem da detecção",
        str(candidate.source_directory),
    )

    console.print(
        Panel(
            table,
            title="Detalhes do jogo",
            border_style="yellow",
            box=box.ROUNDED,
        )
    )

    console.print(
        Panel.fit(
            "[yellow]O executável foi detectado, "
            "mas nenhuma Steam API foi localizada.[/yellow]\n\n"
            "As funções que dependem da Steam API "
            "não estão disponíveis para este jogo.",
            border_style="yellow",
            box=box.ROUNDED,
        )
    )

    pause()


def show_games(
    config: AppConfig,
) -> None:
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

    candidates = discover_game_candidates(config.games.directories)

    if not candidates:
        console.print(
            Panel.fit(
                "[yellow]Nenhum jogo foi encontrado.[/yellow]",
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

    table.add_column(
        "#",
        style="bold cyan",
        justify="right",
        no_wrap=True,
    )

    table.add_column(
        "Jogo",
        style="bold",
    )

    table.add_column(
        "Arquitetura",
    )

    table.add_column(
        "Steam API",
    )

    table.add_column(
        "Status",
    )

    table.add_column(
        "Executável",
    )

    for index, candidate in enumerate(
        candidates,
        start=1,
    ):
        if candidate.game is not None:
            architecture = candidate.game.architecture

            steam_api = candidate.game.steam_api.name

            status = "[green]✓ Configurável[/green]"

        else:
            architecture = "—"
            steam_api = "—"

            status = "[yellow]⚠ Steam API ausente[/yellow]"

        table.add_row(
            str(index),
            candidate.name,
            architecture,
            steam_api,
            status,
            candidate.executable.name,
        )

    console.print(table)

    choices = [
        (f"{index} - {candidate.name}")
        for index, candidate in enumerate(
            candidates,
            start=1,
        )
    ]

    choices.append("Voltar")

    selected = questionary.select(
        "Selecione um jogo:",
        choices=choices,
    ).ask()

    if selected is None or selected == "Voltar":
        return

    index = (
        int(
            selected.split(
                " - ",
                1,
            )[0]
        )
        - 1
    )

    candidate = candidates[index]

    if candidate.game is not None:
        show_game_details(candidate.game)
        return

    show_game_candidate_details(candidate)


def show_sentinel_status() -> None:
    installation = detect_sentinel()

    status = read_sentinel_config(
        installation.config_path,
    )

    table = Table.grid(padding=(0, 2))

    table.add_column(
        style="bold cyan",
        no_wrap=True,
    )
    table.add_column(style="white")

    table.add_row(
        "Instalação",
        (
            f"[green]✓ Detectado[/green] • {installation.executable}"
            if installation.installed
            else "[yellow]⚠ Não detectado[/yellow]"
        ),
    )

    if not status.exists:
        config_status = "[yellow]⚠ Não encontrada[/yellow]"
    elif not status.valid_json:
        config_status = "[red]✗ JSON inválido[/red]"
    elif not status.schema_valid:
        config_status = "[red]✗ Schema não reconhecido[/red]"
    else:
        config_status = "[green]✓ Válida[/green]"

    table.add_row(
        "Configuração",
        config_status,
    )

    table.add_row(
        "Arquivo",
        str(installation.config_path),
    )

    table.add_row(
        "Dados",
        (
            "[green]✓ Encontrados[/green]"
            if installation.data_exists
            else "[yellow]⚠ Não encontrados[/yellow]"
        ),
    )

    table.add_row(
        "Estado",
        (
            "[green]✓ Encontrado[/green]"
            if installation.state_exists
            else "[yellow]⚠ Não encontrado[/yellow]"
        ),
    )

    table.add_row(
        "Prefixos",
        (
            f"[green]✓ {len(status.prefix_paths)} configurados[/green]"
            if status.prefix_paths
            else "[yellow]⚠ Nenhum configurado[/yellow]"
        ),
    )

    table.add_row(
        "GSE",
        (
            "[green]✓ Habilitado[/green]"
            if status.gse_enabled
            else "[yellow]⚠ Não habilitado[/yellow]"
        ),
    )

    table.add_row(
        "Goldberg legado",
        (
            "[green]✓ Habilitado[/green]"
            if status.goldberg_enabled
            else "[dim]— Não habilitado[/dim]"
        ),
    )

    gse_notifications = next(
        (
            emulator.should_notify
            for emulator in status.emulators
            if emulator.id == SENTINEL_GSE_EMULATOR_ID
        ),
        None,
    )

    if gse_notifications is True:
        notification_status = "[green]✓ Habilitadas[/green]"
    elif gse_notifications is False:
        notification_status = "[yellow]⚠ Desabilitadas[/yellow]"
    else:
        notification_status = "[dim]— GSE não configurado[/dim]"

    table.add_row(
        "Notificações GSE",
        notification_status,
    )

    if status.gse_watcher_configured:
        watcher_status = "[green]✓ Pronto para GSE[/green]"
    elif status.watcher_configured:
        watcher_status = "[yellow]⚠ Configurado sem GSE[/yellow]"
    else:
        watcher_status = "[yellow]⚠ Não configurado[/yellow]"

    table.add_row(
        "Watcher (config)",
        watcher_status,
    )

    gse_save_roots = tuple(
        save_root
        for save_root in resolve_sentinel_save_roots(status)
        if (save_root.emulator_id == SENTINEL_GSE_EMULATOR_ID and save_root.exists)
    )

    if len(gse_save_roots) == 1:
        gse_saves_status = f"[green]✓ Encontrado[/green] • {gse_save_roots[0].path}"

    elif len(gse_save_roots) > 1:
        gse_saves_status = f"[green]✓ {len(gse_save_roots)} encontrados[/green]"

    elif status.gse_enabled:
        gse_saves_status = "[yellow]⚠ Não encontrado[/yellow]"

    else:
        gse_saves_status = "[dim]— GSE não configurado[/dim]"

    table.add_row(
        "GSE Saves",
        gse_saves_status,
    )

    console.print(
        Panel(
            table,
            title="Sentinel",
            border_style=(
                "green"
                if installation.installed and status.gse_watcher_configured
                else "yellow"
            ),
            box=box.ROUNDED,
        )
    )

    console.print(
        "[dim]Somente leitura • "
        "nenhuma configuração do Sentinel foi alterada • "
        "o estado acima não confirma se o processo está em execução.[/dim]"
    )


def show_game_sentinel_status(
    game: Game,
) -> None:
    clear_screen()
    render_header()

    installation = detect_sentinel()

    status = read_sentinel_config(
        installation.config_path,
    )

    resolution = resolve_game_sentinel_runtime(
        game,
        status=status,
    )

    table = Table.grid(
        padding=(0, 2),
    )

    table.add_column(
        style="bold cyan",
        no_wrap=True,
    )

    table.add_column(
        style="white",
    )

    table.add_row(
        "Jogo",
        game.name,
    )

    table.add_row(
        "Sentinel",
        (
            f"[green]✓ Detectado[/green] • {installation.executable}"
            if installation.installed
            else "[yellow]⚠ Não detectado[/yellow]"
        ),
    )

    table.add_row(
        "Configuração",
        (
            "[green]✓ Válida[/green]"
            if status.configured
            else "[yellow]⚠ Não configurada[/yellow]"
        ),
    )

    if resolution.app_id is None:
        app_id_status = "[yellow]⚠ Não resolvido[/yellow]"
    else:
        details: list[str] = []

        if resolution.app_id_source is not None:
            details.append(
                resolution.app_id_source,
            )

        if resolution.app_id_confidence is not None:
            details.append(f"{resolution.app_id_confidence}%")

        metadata = " • " + " • ".join(details) if details else ""

        app_id_status = f"[green]✓ {resolution.app_id}[/green]{metadata}"

    table.add_row(
        "AppID",
        app_id_status,
    )

    if resolution.runtime_saves:
        runtime_count = len(
            resolution.runtime_saves,
        )

        runtime_label = "correspondência" if runtime_count == 1 else "correspondências"

        table.add_row(
            "Runtime",
            (f"[green]✓ {runtime_count} {runtime_label}[/green]"),
        )

        multiple_matches = runtime_count > 1

        for index, runtime_save in enumerate(
            resolution.runtime_saves,
            start=1,
        ):
            suffix = f" #{index}" if multiple_matches else ""

            table.add_row(
                f"Emulador{suffix}",
                runtime_save.emulator_id,
            )

            table.add_row(
                f"Prefixo{suffix}",
                str(runtime_save.prefix_path),
            )

            table.add_row(
                f"drive_c{suffix}",
                str(runtime_save.drive_c),
            )

            table.add_row(
                f"Save root{suffix}",
                str(runtime_save.saves_directory),
            )

            table.add_row(
                f"AppID runtime{suffix}",
                str(runtime_save.app_id),
            )

            table.add_row(
                f"achievements.json{suffix}",
                (
                    f"[green]✓ Encontrado[/green] • {runtime_save.achievements_path}"
                    if runtime_save.achievements_exists
                    else (
                        "[yellow]⚠ Ainda não criado[/yellow] • "
                        f"{runtime_save.achievements_path}"
                    )
                ),
            )

    else:
        table.add_row(
            "Runtime",
            "[yellow]⚠ Nenhum save correspondente encontrado[/yellow]",
        )

    console.print(
        Panel(
            table,
            title="Sentinel • Runtime do jogo",
            border_style=("green" if resolution.runtime_found else "yellow"),
            box=box.ROUNDED,
        )
    )

    console.print(
        "[dim]"
        "Somente leitura • "
        "nenhum arquivo do Sentinel ou do GSE foi alterado."
        "[/dim]"
    )

    pause()


def _achievement_report_table(
    report: AchievementReport,
    *,
    confirmed_runtime: bool,
) -> Table:
    table = Table.grid(
        padding=(0, 2),
    )
    table.add_column(
        style="bold cyan",
        no_wrap=True,
    )
    table.add_column(
        style="white",
        justify="right",
    )

    if report.runtime_path is not None:
        table.add_row(
            "Runtime",
            str(report.runtime_path),
        )

    table.add_row(
        "Disponíveis",
        str(report.total),
    )

    if confirmed_runtime:
        table.add_row(
            "Desbloqueadas",
            str(report.unlocked),
        )
        table.add_row(
            "Bloqueadas",
            str(report.locked),
        )
        table.add_row(
            "Parciais",
            str(report.partial),
        )
        table.add_row(
            "Conclusão",
            f"{report.completion_percentage:.1f}%",
        )

    if report.unknown_runtime_names:
        table.add_row(
            "Runtime sem metadata",
            str(len(report.unknown_runtime_names)),
        )

    return table


def show_game_achievement_status(
    game: Game,
) -> None:
    clear_screen()
    render_header()

    try:
        resolution = resolve_game_achievement_progress(game)
    except (
        AchievementDataError,
        OSError,
        ValueError,
    ) as error:
        console.print(
            Panel.fit(
                "[red]Não foi possível resolver o progresso "
                f"de achievements.[/red]\n\n{error}",
                border_style="red",
                box=box.ROUNDED,
            )
        )
        pause()
        return

    gse_resolution = resolution.gse_resolution
    metadata_error = next(
        (
            error
            for error in resolution.errors
            if error.path == resolution.metadata_path
        ),
        None,
    )

    overview = Table.grid(
        padding=(0, 2),
    )
    overview.add_column(
        style="bold cyan",
        no_wrap=True,
    )
    overview.add_column(
        style="white",
    )
    overview.add_row(
        "Jogo",
        game.name,
    )
    overview.add_row(
        "AppID",
        (
            str(gse_resolution.app_id)
            if gse_resolution.app_id is not None
            else "[yellow]⚠ Não resolvido[/yellow]"
        ),
    )

    if not resolution.metadata_exists:
        metadata_status = (
            f"[yellow]⚠ Não encontrado[/yellow] • {resolution.metadata_path}"
        )
    elif metadata_error is not None:
        metadata_status = f"[red]✗ Metadata inválida[/red] • {resolution.metadata_path}"
    else:
        metadata_status = f"[green]✓ Encontrado[/green] • {resolution.metadata_path}"

    overview.add_row(
        "Metadata",
        metadata_status,
    )
    overview.add_row(
        "Idioma",
        resolution.language,
    )

    if resolution.runtime_paths:
        runtime_count = len(resolution.runtime_paths)
        runtime_status = (
            f"[green]✓ {runtime_count} "
            + ("arquivo encontrado" if runtime_count == 1 else "arquivos encontrados")
            + "[/green]"
        )
    elif not resolution.runtime_resolved:
        runtime_status = "[yellow]⚠ Não resolvido[/yellow]"
    else:
        runtime_status = "[yellow]⚠ achievements.json ainda não criado[/yellow]"

    overview.add_row(
        "Runtime",
        runtime_status,
    )

    if resolution.runtime_resolved and not resolution.runtime_paths:
        save_resolution = gse_resolution.save_resolution

        assert save_resolution is not None

        multiple_locations = len(save_resolution.locations) > 1

        for index, location in enumerate(
            save_resolution.locations,
            start=1,
        ):
            suffix = f" #{index}" if multiple_locations else ""
            overview.add_row(
                f"Runtime esperado{suffix}",
                str(location.achievements_path),
            )

    console.print(
        Panel(
            overview,
            title="Achievements • Progresso",
            border_style=(
                "green"
                if resolution.metadata_exists
                and metadata_error is None
                and resolution.runtime_resolved
                else "yellow"
            ),
            box=box.ROUNDED,
        )
    )

    if metadata_error is not None:
        console.print()
        console.print(
            Panel.fit(
                f"[red]Não foi possível ler a metadata.[/red]\n\n{metadata_error.message}",
                border_style="red",
                box=box.ROUNDED,
            )
        )

    elif resolution.metadata_exists:
        if not resolution.runtime_resolved and not resolution.runtime_paths:
            metadata_report = next(
                (
                    report
                    for report in resolution.reports
                    if report.runtime_path is None
                ),
                None,
            )

            if metadata_report is not None:
                console.print()
                console.print(
                    Panel(
                        _achievement_report_table(
                            metadata_report,
                            confirmed_runtime=False,
                        ),
                        title="Achievements • Metadata",
                        border_style="yellow",
                        box=box.ROUNDED,
                    )
                )

        elif not resolution.runtime_paths:
            metadata_report = next(
                (
                    report
                    for report in resolution.reports
                    if report.runtime_path is None
                ),
                None,
            )

            if metadata_report is not None:
                console.print()
                console.print(
                    Panel(
                        _achievement_report_table(
                            metadata_report,
                            confirmed_runtime=True,
                        ),
                        title="Achievements",
                        border_style="yellow",
                        box=box.ROUNDED,
                    )
                )

        else:
            multiple_runtimes = len(resolution.runtime_paths) > 1

            for index, runtime_path in enumerate(
                resolution.runtime_paths,
                start=1,
            ):
                report = next(
                    (
                        candidate
                        for candidate in resolution.reports
                        if candidate.runtime_path == runtime_path
                    ),
                    None,
                )
                error = next(
                    (
                        candidate
                        for candidate in resolution.errors
                        if candidate.path == runtime_path
                    ),
                    None,
                )
                suffix = f" • Runtime #{index}" if multiple_runtimes else ""

                console.print()

                if report is not None:
                    console.print(
                        Panel(
                            _achievement_report_table(
                                report,
                                confirmed_runtime=True,
                            ),
                            title=f"Achievements{suffix}",
                            border_style="green",
                            box=box.ROUNDED,
                        )
                    )
                elif error is not None:
                    console.print(
                        Panel.fit(
                            f"[red]Runtime inválido:[/red] {runtime_path}\n\n"
                            f"{error.message}",
                            title=f"Achievements{suffix}",
                            border_style="red",
                            box=box.ROUNDED,
                        )
                    )

    console.print()
    console.print(
        "[dim]Somente leitura • nenhum arquivo de achievements foi alterado.[/dim]"
    )
    pause()


def show_game_gse_status(
    game: Game,
) -> None:
    clear_screen()
    render_header()

    installation = detect_sentinel()

    sentinel_status = read_sentinel_config(
        installation.config_path,
    )

    resolution = resolve_game_gse_runtime(
        game,
        sentinel_status=sentinel_status,
    )

    table = Table.grid(
        padding=(0, 2),
    )

    table.add_column(
        style="bold cyan",
        no_wrap=True,
    )

    table.add_column(
        style="white",
    )

    table.add_row(
        "Jogo",
        game.name,
    )

    if resolution.app_id is None:
        table.add_row(
            "AppID",
            "[yellow]⚠ Não resolvido[/yellow]",
        )

        table.add_row(
            "GSE save",
            "[yellow]⚠ Não foi possível resolver[/yellow]",
        )

    else:
        app_id_details: list[str] = []

        if resolution.app_id_source is not None:
            app_id_details.append(
                resolution.app_id_source,
            )

        if resolution.app_id_confidence is not None:
            app_id_details.append(f"{resolution.app_id_confidence}%")

        app_id_metadata = " • " + " • ".join(app_id_details) if app_id_details else ""

        table.add_row(
            "AppID",
            (f"[green]✓ {resolution.app_id}[/green]{app_id_metadata}"),
        )

        save_resolution = resolution.save_resolution

        assert save_resolution is not None

        source_labels = {
            "GseSavePath": "GseSavePath",
            "local_save_path": "local_save_path",
            "saves_folder_name": "saves_folder_name",
            "default": "GSE padrão",
        }

        source_label = source_labels.get(
            save_resolution.source,
            save_resolution.source,
        )

        table.add_row(
            "Origem do save",
            source_label,
        )

        if save_resolution.raw_value is not None:
            table.add_row(
                "Valor configurado",
                save_resolution.raw_value,
            )

        if not save_resolution.locations:
            table.add_row(
                "Resolução",
                "[yellow]⚠ Caminho não resolvido[/yellow]",
            )

            if (
                game.steam_api.suffix.casefold() == ".dll"
                and not sentinel_status.prefix_paths
            ):
                table.add_row(
                    "Motivo provável",
                    (
                        "[yellow]Nenhum prefixo Wine/Proton "
                        "foi encontrado no Sentinel.[/yellow]"
                    ),
                )

        elif save_resolution.ambiguous:
            table.add_row(
                "Resolução",
                "[yellow]⚠ Ambígua[/yellow]",
            )
            table.add_row("Effective root", "[dim]— Não determinado[/dim]")
        else:
            table.add_row("Resolução", "[green]✓ Determinada[/green]")

            for location in save_resolution.effective_locations:
                table.add_row("Effective root", str(location.root))

        if save_resolution.locations:
            multiple_locations = len(save_resolution.locations) > 1

            for index, location in enumerate(save_resolution.locations, start=1):
                suffix = f" #{index}" if multiple_locations else ""

                if multiple_locations:
                    table.add_row(f"Possible root{suffix}", str(location.root))

                table.add_row(
                    f"Possible AppID dir{suffix}"
                    if multiple_locations
                    else "AppID dir",
                    (
                        f"[green]✓ Existe[/green] • {location.app_directory}"
                        if location.app_directory_exists
                        else (
                            "[yellow]⚠ Ainda não criado[/yellow] • "
                            f"{location.app_directory}"
                        )
                    ),
                )

                table.add_row(
                    (
                        f"Possible achievements.json{suffix}"
                        if multiple_locations
                        else "achievements.json"
                    ),
                    (
                        f"[green]✓ Encontrado[/green] • {location.achievements_path}"
                        if location.achievements_exists
                        else (
                            "[yellow]⚠ Ainda não criado[/yellow] • "
                            f"{location.achievements_path}"
                        )
                    ),
                )

    console.print(
        Panel(
            table,
            title="GSE • Resolução de saves",
            border_style=("green" if resolution.runtime_found else "yellow"),
            box=box.ROUNDED,
        )
    )

    console.print(
        "[dim]"
        "Somente leitura • "
        "nenhum save ou arquivo de configuração foi alterado."
        "[/dim]"
    )

    pause()


_SENTINEL_REPAIR_KIND_LABELS = {
    SentinelRepairKind.ALREADY_COVERED: "já coberta",
    SentinelRepairKind.ADD_PREFIX: "prefix pode ser adicionado com segurança",
    SentinelRepairKind.PREFIX_ALREADY_CONFIGURED: (
        "prefix já configurado; inconsistência exige diagnóstico"
    ),
    SentinelRepairKind.UNSUPPORTED_CUSTOM_SAVE_ROOT: (
        "save customizado fora do layout observado pelo Sentinel; "
        "não é suportado pelo modelo atual"
    ),
    SentinelRepairKind.UNSUPPORTED_WINE_USER: (
        "usuário Wine diferente de steamuser não é suportado pelo Sentinel atual"
    ),
    SentinelRepairKind.UNRESOLVED: "save não resolvido",
}


def _add_sentinel_repair_rows(
    table: Table,
    plan: SentinelRepairPlan,
) -> None:
    if not plan.coverage.effective_save_resolved:
        save_resolution = plan.coverage.save_resolution
        unknown = (
            "[yellow]⚠ Não determinado / ambíguo[/yellow]"
            if save_resolution is not None and save_resolution.ambiguous
            else "[dim]— Não determinado[/dim]"
        )
        repair_needed = unknown
        repairability = unknown
        fully_watched = unknown
        requires_gse_change = unknown
    else:
        repair_needed = (
            "[yellow]⚠ Sim[/yellow]" if plan.needs_repair else "[green]✓ Não[/green]"
        )

        if plan.fully_repairable_via_sentinel_config:
            repairability = "[green]✓ Sim[/green]"
        elif plan.partially_repairable_via_sentinel_config:
            repairability = "[yellow]⚠ Parcialmente[/yellow]"
        else:
            repairability = "[red]✗ Não[/red]"

        fully_watched = (
            "[green]✓ Sim[/green]"
            if plan.coverage.fully_watched
            else "[dim]— Não[/dim]"
        )
        requires_gse_change = (
            "[yellow]⚠ Sim[/yellow]"
            if plan.requires_gse_change
            else "[green]✓ Não[/green]"
        )

    table.add_row("", "")
    table.add_row("[bold]Reparo[/bold]", "")
    table.add_row("Reparo necessário", repair_needed)
    table.add_row(
        "Corrigível apenas no Sentinel",
        repairability,
    )
    table.add_row("Fully watched", fully_watched)
    table.add_row("Requer mudança no GSE", requires_gse_change)
    table.add_row(
        "Candidate prefixes",
        (
            "\n".join(str(prefix) for prefix in plan.candidate_prefixes)
            if plan.candidate_prefixes
            else "[dim]— Nenhum seguro[/dim]"
        ),
    )

    multiple_locations = len(plan.location_plans) > 1

    for index, location_plan in enumerate(plan.location_plans, start=1):
        suffix = f" #{index}" if multiple_locations else ""
        location = location_plan.location
        table.add_row(
            f"Location de reparo{suffix}",
            str(location.root)
            if location is not None
            else "[dim]— Não resolvida[/dim]",
        )
        table.add_row(
            f"Classificação{suffix}",
            _SENTINEL_REPAIR_KIND_LABELS[location_plan.kind],
        )


def _show_sentinel_repair_plan(
    game: Game,
    plan: SentinelRepairPlan,
    *,
    title: str,
) -> None:
    table = Table.grid(padding=(0, 2))
    table.add_column(style="bold cyan", no_wrap=True)
    table.add_column(style="white")
    table.add_row("Jogo", game.name)
    table.add_row("Config", str(plan.coverage.sentinel_status.path))
    _add_sentinel_repair_rows(table, plan)
    console.print(
        Panel(
            table,
            title=title,
            border_style=(
                "green"
                if not plan.needs_repair
                else "cyan"
                if plan.repairable_via_sentinel_config
                else "yellow"
            ),
            box=box.ROUNDED,
        )
    )


def show_sentinel_config_write_result(
    result: SentinelConfigWriteResult,
) -> None:
    status_styles = {
        SentinelConfigWriteStatus.APPLIED: "green",
        SentinelConfigWriteStatus.NO_CHANGE: "cyan",
        SentinelConfigWriteStatus.REJECTED: "yellow",
        SentinelConfigWriteStatus.CONFLICT: "red",
        SentinelConfigWriteStatus.FAILED: "red",
        SentinelConfigWriteStatus.ROLLED_BACK: "yellow",
    }
    style = status_styles[result.status]
    table = Table.grid(padding=(0, 2))
    table.add_column(style="bold cyan", no_wrap=True)
    table.add_column(style="white")
    table.add_row("Status", f"[{style}]{result.status.name}[/{style}]")
    table.add_row("Reason", result.reason.name)
    table.add_row("Config", str(result.config_path))

    if result.message:
        table.add_row("Mensagem", result.message)

    for index, prefix in enumerate(result.added_prefixes, start=1):
        suffix = f" #{index}" if len(result.added_prefixes) > 1 else ""
        table.add_row(f"Prefix adicionado{suffix}", str(prefix))

    if result.backup_path is not None:
        table.add_row("Backup", str(result.backup_path))

    if result.partial:
        table.add_row("Parcial", "[yellow]Sim[/yellow]")

    table.add_row(
        "Rollback executado",
        "[yellow]Sim[/yellow]" if result.rolled_back else "Não",
    )
    console.print(
        Panel(
            table,
            title="Resultado do reparo Sentinel",
            border_style=style,
            box=box.ROUNDED,
        )
    )

    if result.status is SentinelConfigWriteStatus.ROLLED_BACK:
        console.print(
            "[yellow]A operação falhou, mas a configuração original "
            "foi restaurada pelo rollback.[/yellow]"
        )
    elif (
        result.status is SentinelConfigWriteStatus.FAILED
        and result.reason is SentinelConfigWriteReason.ROLLBACK_FAILED
    ):
        console.print(
            "[red]Falha crítica: o rollback FALHOU e a restauração do "
            "original não pôde ser confirmada.[/red]"
        )
    elif result.status is SentinelConfigWriteStatus.CONFLICT:
        console.print(
            "[red]CONFLICT: a configuração mudou durante a operação; "
            "nenhuma alteração concorrente foi sobrescrita.[/red]"
        )


def show_game_sentinel_integration_status(
    game: Game,
) -> None:
    clear_screen()
    render_header()

    installation = detect_sentinel()
    sentinel_status = read_sentinel_config(installation.config_path)
    repair_plan = resolve_game_sentinel_repair(
        game,
        sentinel_status=sentinel_status,
    )
    coverage = repair_plan.coverage

    table = Table.grid(padding=(0, 2))
    table.add_column(style="bold cyan", no_wrap=True)
    table.add_column(style="white")
    table.add_row("Jogo", game.name)
    table.add_row(
        "AppID",
        (
            f"[green]✓ {coverage.app_id}[/green]"
            if coverage.app_id is not None
            else "[yellow]⚠ Não resolvido[/yellow]"
        ),
    )
    table.add_row("", "")
    table.add_row("[bold]Sentinel[/bold]", "")
    table.add_row(
        "Instalação",
        (
            f"[green]✓ Detectada[/green] • {installation.executable}"
            if installation.installed
            else "[yellow]⚠ Não detectada[/yellow]"
        ),
    )
    table.add_row(
        "Config existente",
        (
            "[green]✓ Sim[/green]"
            if sentinel_status.exists
            else "[yellow]⚠ Não[/yellow]"
        ),
    )

    if not sentinel_status.exists:
        json_status = "[dim]— Não avaliado[/dim]"
        schema_status = "[dim]— Não avaliado[/dim]"
    elif not sentinel_status.valid_json:
        json_status = "[red]✗ Inválido[/red]"
        schema_status = "[dim]— Não avaliado[/dim]"
    else:
        json_status = "[green]✓ Válido[/green]"
        schema_status = (
            "[green]✓ Válido[/green]"
            if sentinel_status.schema_valid
            else "[red]✗ Inválido[/red]"
        )

    table.add_row("JSON", json_status)
    table.add_row("Schema", schema_status)
    table.add_row(
        "Watcher configurado",
        (
            "[green]✓ Sim[/green]"
            if coverage.watcher_configured
            else "[yellow]⚠ Não[/yellow]"
        ),
    )
    table.add_row(
        "GSE habilitado",
        ("[green]✓ Sim[/green]" if coverage.gse_enabled else "[yellow]⚠ Não[/yellow]"),
    )

    gse_notifications = next(
        (
            emulator.should_notify
            for emulator in sentinel_status.emulators
            if emulator.id == SENTINEL_GSE_EMULATOR_ID
        ),
        None,
    )

    if gse_notifications is True:
        notification_status = "[green]✓ Habilitadas[/green]"
    elif gse_notifications is False:
        notification_status = "[yellow]⚠ Desabilitadas[/yellow]"
    else:
        notification_status = "[dim]— Não disponível[/dim]"

    table.add_row("Notificações GSE", notification_status)
    table.add_row("", "")
    table.add_row("[bold]Reconhecimento[/bold]", "")

    if not coverage.recognized_by_sentinel:
        sentinel_recognition = "[yellow]⚠ Não[/yellow]"
    elif coverage.recognized_by_gse_runtime:
        sentinel_recognition = "[green]✓ Sim[/green] • runtime GSE"
    elif coverage.legacy_runtime_matches:
        sentinel_recognition = "[yellow]⚠ Sim[/yellow] • somente Goldberg legacy"
    else:
        sentinel_recognition = "[green]✓ Sim[/green]"

    table.add_row("Sentinel", sentinel_recognition)
    table.add_row(
        "Runtime GSE",
        (
            "[green]✓ Reconhecido[/green]"
            if coverage.recognized_by_gse_runtime
            else "[yellow]⚠ Não reconhecido[/yellow]"
        ),
    )
    table.add_row(
        "Runtime Goldberg legacy",
        (
            "[yellow]⚠ Reconhecido[/yellow]"
            if coverage.legacy_runtime_matches
            else "[dim]— Não reconhecido[/dim]"
        ),
    )
    table.add_row("", "")
    table.add_row("[bold]Coverage[/bold]", "")
    save_resolution = coverage.save_resolution
    save_ambiguous = save_resolution is not None and save_resolution.ambiguous
    table.add_row(
        "Save GSE resolvido",
        (
            "[yellow]⚠ Ambíguo[/yellow]"
            if save_ambiguous
            else "[green]✓ Sim[/green]"
            if coverage.effective_save_resolved
            else "[yellow]⚠ Não[/yellow]"
        ),
    )

    if coverage.effective_save_resolved:
        table.add_row(
            "Fully watched",
            "[green]✓ Sim[/green]" if coverage.fully_watched else "[dim]— Não[/dim]",
        )
        table.add_row(
            "Partially watched",
            (
                "[yellow]⚠ Sim[/yellow]"
                if coverage.partially_watched
                else "[dim]— Não[/dim]"
            ),
        )
        table.add_row(
            "Unwatched",
            "[red]✗ Sim[/red]" if coverage.unwatched else "[dim]— Não[/dim]",
        )
    else:
        table.add_row("Fully watched", "[dim]— Não determinado[/dim]")
        table.add_row("Partially watched", "[dim]— Não determinado[/dim]")
        table.add_row("Unwatched", "[dim]— Não determinado[/dim]")

        if save_ambiguous:
            table.add_row("Effective root", "[dim]— Não determinado[/dim]")

    if coverage.location_coverages:
        multiple_locations = len(coverage.location_coverages) > 1

        for index, location_coverage in enumerate(
            coverage.location_coverages,
            start=1,
        ):
            suffix = f" #{index}" if multiple_locations else ""
            table.add_row(
                f"Effective root{suffix}",
                str(location_coverage.location.root),
            )
            table.add_row(
                f"Cobertura{suffix}",
                (
                    "[green]✓ Coberta[/green]"
                    if location_coverage.covered
                    else "[red]✗ Não coberta[/red]"
                ),
            )

            for root_index, matching_root in enumerate(
                location_coverage.matching_roots,
                start=1,
            ):
                match_suffix = (
                    f" #{root_index}"
                    if len(location_coverage.matching_roots) > 1
                    else ""
                )
                table.add_row(
                    f"Sentinel match{suffix}{match_suffix}",
                    str(matching_root.path),
                )

    if save_resolution is not None and len(save_resolution.locations) > 1:
        for index, location in enumerate(save_resolution.locations, start=1):
            table.add_row(f"Possible root #{index}", str(location.root))

    if coverage.gse_save_roots:
        multiple_roots = len(coverage.gse_save_roots) > 1

        for index, save_root in enumerate(coverage.gse_save_roots, start=1):
            suffix = f" #{index}" if multiple_roots else ""
            table.add_row(
                f"Sentinel GSE root{suffix}",
                str(save_root.path),
            )
    else:
        table.add_row("Sentinel GSE roots", "[dim]— Nenhuma derivada[/dim]")

    _add_sentinel_repair_rows(table, repair_plan)

    console.print(
        Panel(
            table,
            title="Sentinel • Integração GSE",
            border_style="green" if coverage.fully_watched else "yellow",
            box=box.ROUNDED,
        )
    )

    diagnostics: list[str] = []

    if not installation.installed:
        diagnostics.append("O Sentinel não foi detectado neste sistema.")

    if not sentinel_status.exists:
        diagnostics.append("A configuração do Sentinel não foi encontrada.")
    elif not sentinel_status.valid_json:
        diagnostics.append("A configuração do Sentinel contém JSON inválido.")
    elif not sentinel_status.schema_valid:
        diagnostics.append("O schema da configuração do Sentinel é inválido.")

    if sentinel_status.configured and not coverage.gse_enabled:
        diagnostics.append("O Sentinel não possui o emulator GSE habilitado.")

    if sentinel_status.configured and not sentinel_status.prefix_paths:
        diagnostics.append("O watcher do Sentinel não possui prefixes configurados.")

    if save_ambiguous:
        if save_resolution is not None and len(save_resolution.runtime_locations) > 1:
            diagnostics.append(
                "Múltiplos runtimes para este AppID foram encontrados; "
                "o root efetivo permanece ambíguo."
            )
        else:
            diagnostics.append(
                "Há múltiplos roots Wine possíveis e não foi possível determinar "
                "com segurança qual é usado por este jogo."
            )
    elif not coverage.effective_save_resolved:
        diagnostics.append("O save efetivo usado pelo GSE não pôde ser resolvido.")
    elif coverage.fully_watched:
        diagnostics.append("Todas as locations efetivas do GSE estão cobertas.")
    elif coverage.partially_watched:
        diagnostics.append("A cobertura do Sentinel é parcial.")
        diagnostics.append("Será necessária uma correção de cobertura do Sentinel.")
    elif coverage.unwatched:
        diagnostics.append("O save efetivamente usado pelo GSE não é observado.")
        diagnostics.append("Será necessária uma correção de cobertura do Sentinel.")

    if (
        coverage.recognized_by_sentinel
        and coverage.effective_save_resolved
        and not coverage.effective_save_watched
    ):
        diagnostics.append(
            "O Sentinel reconhece este AppID em outro runtime, "
            "mas não está observando o save atualmente usado pelo GSE."
        )

    if (
        coverage.recognized_by_sentinel
        and not coverage.recognized_by_gse_runtime
        and coverage.legacy_runtime_matches
    ):
        diagnostics.append(
            "O AppID foi reconhecido somente no runtime Goldberg legacy, "
            "não no runtime GSE atual."
        )

    for location_plan in repair_plan.uncovered_location_plans:
        diagnostics.append(
            f"Motivo: {_SENTINEL_REPAIR_KIND_LABELS[location_plan.kind]}."
        )

    console.print()
    console.print(
        Panel.fit(
            "\n".join(diagnostics) if diagnostics else "Nenhum problema detectado.",
            title="Diagnóstico",
            border_style="green" if coverage.fully_watched else "yellow",
            box=box.ROUNDED,
        )
    )
    console.print()
    console.print(
        "[dim]Somente leitura • nenhum arquivo do Sentinel ou save foi alterado.[/dim]"
    )
    pause()


def repair_game_sentinel_integration(
    game: Game,
) -> None:
    clear_screen()
    render_header()

    try:
        plan = resolve_game_sentinel_repair(game)
    except Exception as error:  # noqa: BLE001 - user-facing boundary
        console.print(
            Panel.fit(
                f"[red]Não foi possível resolver o reparo do Sentinel.[/red]\n\n{error}",
                border_style="red",
                box=box.ROUNDED,
            )
        )
        pause()
        return

    _show_sentinel_repair_plan(
        game,
        plan,
        title="Sentinel • Plano de reparo",
    )

    if not plan.config_valid:
        config_messages = {
            SentinelRepairConfigState.MISSING: (
                "A configuração do Sentinel não foi encontrada."
            ),
            SentinelRepairConfigState.INVALID_JSON: (
                "A configuração do Sentinel contém JSON inválido."
            ),
            SentinelRepairConfigState.INVALID_SCHEMA: (
                "O schema da configuração do Sentinel é inválido."
            ),
        }
        console.print(f"[yellow]{config_messages[plan.config_state]}[/yellow]")
        console.print("[yellow]Nenhuma alteração foi realizada.[/yellow]")
        pause()
        return

    if not plan.gse_enabled:
        console.print(
            "[yellow]O emulator GSE está desabilitado. Esta versão não o "
            "habilita automaticamente.[/yellow]"
        )
        console.print("[yellow]Nenhuma alteração foi realizada.[/yellow]")
        pause()
        return

    save_resolution = plan.coverage.save_resolution

    if not plan.coverage.effective_save_resolved:
        unresolved_message = (
            "O save GSE efetivo não pôde ser determinado com segurança."
            if save_resolution is not None and save_resolution.ambiguous
            else "O save GSE efetivo não pôde ser resolvido com segurança."
        )
        console.print(f"[yellow]{unresolved_message}[/yellow]")
        console.print("[yellow]Nenhuma correção automática será proposta.[/yellow]")
        pause()
        return

    if not plan.needs_repair:
        console.print("[green]Nenhuma correção é necessária.[/green]")
        pause()
        return

    if not plan.has_safe_prefix_additions:
        console.print(
            "[yellow]Não existe candidate prefix seguro que esta versão "
            "possa adicionar.[/yellow]"
        )
        if plan.requires_gse_change:
            console.print(
                "[yellow]É necessária uma mudança na configuração de saves "
                "do GSE; ela não será feita automaticamente.[/yellow]"
            )
        pause()
        return

    partial = plan.partially_repairable_via_sentinel_config

    if not plan.fully_repairable_via_sentinel_config and not partial:
        console.print(
            "[yellow]O planner não produziu um reparo representável com "
            "segurança. Nenhuma alteração foi realizada.[/yellow]"
        )
        pause()
        return

    console.print()

    if partial:
        console.print("[bold yellow]Esta correção é PARCIAL.[/bold yellow]")
        console.print(
            "[yellow]As locations classificadas como não suportadas "
            "continuarão sem cobertura.[/yellow]"
        )
        if plan.requires_gse_change:
            console.print(
                "[yellow]Uma correção completa também requer mudança no GSE.[/yellow]"
            )
    else:
        console.print(
            "[bold green]Esta correção pode ser feita no Sentinel.[/bold green]"
        )

    confirmation = Table.grid(padding=(0, 2))
    confirmation.add_column(style="bold cyan", no_wrap=True)
    confirmation.add_column(style="white")
    confirmation.add_row("Config", str(plan.coverage.sentinel_status.path))
    confirmation.add_row(
        "Será adicionado",
        "\n".join(str(prefix) for prefix in plan.candidate_prefixes),
    )
    console.print(
        Panel(
            confirmation,
            title="Alteração proposta",
            border_style="yellow" if partial else "cyan",
            box=box.ROUNDED,
        )
    )
    console.print("[dim]Nenhum prefix existente será removido.[/dim]")
    console.print("[dim]Nenhuma configuração GSE será modificada.[/dim]")
    console.print("[dim]Um backup será criado automaticamente.[/dim]")
    console.print("[dim]Somente a lista prefixes do Sentinel será alterada.[/dim]")

    confirmation_message = (
        "Aplicar esta correção parcial do Sentinel?"
        if partial
        else "Aplicar esta correção do Sentinel?"
    )
    confirmed = questionary.confirm(
        confirmation_message,
        default=False,
    ).ask()

    if not confirmed:
        console.print(
            "[yellow]Correção cancelada. Nenhuma alteração foi realizada.[/yellow]"
        )
        pause()
        return

    result = apply_sentinel_config_repair(
        plan,
        allow_partial=partial,
    )
    console.print()
    show_sentinel_config_write_result(result)

    if result.status is SentinelConfigWriteStatus.APPLIED:
        console.print()

        try:
            post_plan = resolve_game_sentinel_repair(game)
        except Exception as error:  # noqa: BLE001 - post-write feedback must not crash
            console.print(
                "[yellow]A alteração foi aplicada, mas não foi possível "
                f"reconsultar a integração: {error}[/yellow]"
            )
        else:
            _show_sentinel_repair_plan(
                game,
                post_plan,
                title="Sentinel • Estado pós-operação",
            )

    pause()


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

        console.print()
        show_sentinel_status()
        console.print()

        choice = questionary.select(
            "O que deseja fazer?",
            choices=[
                "Alterar tema",
                "Definir pasta do Goldberg",
                "Adicionar diretório de jogos",
                "Remover diretório de jogos",
                "Detectar generate_interfaces",
                "Detectar generate_emu_config",
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

        elif choice == "Detectar generate_emu_config":
            if config.goldberg.root is None:
                console.print("[red]Defina primeiro a pasta do Goldberg.[/red]")
                pause()
                continue

            generator = detect_emu_config_generator(config.goldberg.root)

            if generator is None:
                console.print("[red]generate_emu_config não foi encontrado.[/red]")
                pause()
                continue

            config.goldberg.emu_config_generator = generator

            save_config(config)

            console.print("[green]generate_emu_config detectado e salvo.[/green]")

            console.print(f"[dim]{generator}[/dim]")

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


def select_catalog_value(
    message: str,
    choices: tuple[
        SettingChoice,
        ...,
    ],
    current_value: str | None = None,
) -> str | None:
    display_to_value = {choice.display.casefold(): (choice.value) for choice in choices}

    current_display = ""

    if current_value is not None:
        normalized_current = current_value.casefold()

        for choice in choices:
            if choice.value.casefold() == normalized_current:
                current_display = choice.display
                break

    answer = questionary.autocomplete(
        message,
        choices=[choice.display for choice in choices],
        default=current_display,
        ignore_case=True,
        match_middle=True,
        validate=lambda value: value.casefold() in display_to_value,
    ).ask()

    if answer is None:
        return None

    return display_to_value[answer.casefold()]


def get_game_language_choices(
    config: AppConfig,
    app_id: int | None,
) -> tuple[
    tuple[SettingChoice, ...],
    tuple[str, ...],
]:
    if app_id is None:
        return (
            STEAM_LANGUAGE_CHOICES,
            (),
        )

    generator = config.goldberg.emu_config_generator

    if generator is None or not generator.is_file():
        return (
            STEAM_LANGUAGE_CHOICES,
            (),
        )

    try:
        supported_languages = read_generated_supported_languages(
            generator,
            app_id,
        )

    except (
        EmuConfigError,
        OSError,
        ValueError,
    ):
        return (
            STEAM_LANGUAGE_CHOICES,
            (),
        )

    choices = prioritize_setting_choices(
        STEAM_LANGUAGE_CHOICES,
        supported_languages,
    )

    return (
        choices,
        supported_languages,
    )


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
                action = questionary.select(
                    "Idioma:",
                    choices=[
                        "Selecionar / pesquisar idioma",
                        "Remover configuração",
                        "Cancelar",
                    ],
                ).ask()

                if action is None or action == "Cancelar":
                    continue

                if action == "Remover configuração":
                    language = None

                else:
                    language_choices, supported_languages = get_game_language_choices(
                        config,
                        snapshot.app_id,
                    )

                    if supported_languages:
                        supported_choices = [
                            choice
                            for choice in language_choices
                            if choice.value in supported_languages
                        ]

                        console.print()

                        supported_table = Table.grid(padding=(0, 2))

                        supported_table.add_column(style="green")

                        for supported_choice in supported_choices:
                            supported_table.add_row(
                                "✓",
                                supported_choice.display,
                            )

                        console.print(
                            Panel(
                                supported_table,
                                title=("Idiomas suportados pelo jogo"),
                                border_style="green",
                                box=box.ROUNDED,
                            )
                        )

                        console.print()

                    language = select_catalog_value(
                        "Digite ou selecione o idioma:",
                        language_choices,
                        snapshot.language,
                    )

                    if language is None:
                        continue

                if not create_settings_safety_backup(game):
                    continue

                update_user_setting(
                    steam_settings_directory,
                    "language",
                    language,
                )

                if language is None:
                    console.print("[green]Configuração de idioma removida.[/green]")
                else:
                    console.print(f"[green]Idioma atualizado:[/green] {language}")

                pause()

            elif choice.startswith("País —"):
                action = questionary.select(
                    "País:",
                    choices=[
                        "Selecionar / pesquisar país",
                        "Remover configuração",
                        "Cancelar",
                    ],
                ).ask()

                if action is None or action == "Cancelar":
                    continue

                if action == "Remover configuração":
                    country = None

                else:
                    country_choices = get_country_choices()

                    country = select_catalog_value(
                        "Digite ou selecione o país:",
                        country_choices,
                        snapshot.ip_country,
                    )

                    if country is None:
                        continue

                if not create_settings_safety_backup(game):
                    continue

                update_user_setting(
                    steam_settings_directory,
                    "ip_country",
                    country,
                )

                if country is None:
                    console.print("[green]Configuração de país removida.[/green]")
                else:
                    console.print(f"[green]País atualizado:[/green] {country}")

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


def guided_configuration_menu(
    config: AppConfig,
    game: Game,
) -> None:
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

        table.add_row(
            "Jogo",
            game.name,
        )

        table.add_row(
            "",
            "",
        )

        table.add_row(
            "GBE",
            (
                "[green]✓ Pronto[/green]"
                if status.gbe_configured
                else "[yellow]⚠ Pendente[/yellow]"
            ),
        )

        if status.app_id_configured:
            app_id_status = f"[green]✓ {status.app_id}[/green]"

        elif status.app_id is not None:
            confidence = (
                status.app_id_confidence if status.app_id_confidence is not None else 0
            )

            app_id_status = (
                f"[yellow]⚠ Detectado: {status.app_id} ({confidence}%)[/yellow]"
            )

        else:
            app_id_status = "[yellow]⚠ Pendente[/yellow]"

        table.add_row(
            "Steam AppID",
            app_id_status,
        )

        if status.backup_exists and status.backup_valid:
            backup_status = "[green]✓ Íntegro[/green]"

        elif status.backup_exists:
            backup_status = "[red]✗ CORROMPIDO[/red]"

        else:
            backup_status = "[yellow]⚠ Pendente[/yellow]"

        table.add_row(
            "Backup Steam API",
            backup_status,
        )

        table.add_row(
            "steam_settings",
            (
                "[green]✓ Pronto[/green]"
                if status.steam_settings_exists
                else "[yellow]⚠ Pendente[/yellow]"
            ),
        )

        table.add_row(
            "steam_interfaces",
            (
                "[green]✓ Pronto[/green]"
                if status.steam_interfaces_exists
                else "[yellow]⚠ Pendente[/yellow]"
            ),
        )

        console.print(
            Panel(
                table,
                title="Configuração guiada",
                border_style=("green" if status.ready else "cyan"),
                box=box.ROUNDED,
            )
        )

        if status.ready:
            console.print()
            console.print(
                Panel.fit(
                    "[bold green]✓ JOGO PRONTO[/bold green]\n\n"
                    "Todas as etapas necessárias "
                    "foram concluídas.",
                    title="Configuração concluída",
                    border_style="green",
                    box=box.ROUNDED,
                )
            )

            pause()
            return

        next_step = get_next_guided_step(status)

        if next_step == "blocked":
            console.print()
            console.print(
                Panel.fit(
                    "[bold red]✗ Backup corrompido[/bold red]\n\n"
                    "A configuração guiada foi interrompida "
                    "para evitar alterações sem um backup "
                    "válido da Steam API.",
                    border_style="red",
                    box=box.ROUNDED,
                )
            )

            pause()
            return

        if next_step == "gbe":
            next_step_name = "Configurar Goldberg / GBE"

        elif next_step == "appid":
            next_step_name = "Confirmar / configurar Steam AppID"

        elif next_step == "backup":
            next_step_name = "Criar backup da Steam API"

        elif next_step == "settings":
            next_step_name = "Configurar steam_settings"

        elif next_step == "interfaces":
            next_step_name = "Gerar steam_interfaces"

        else:
            console.print()
            console.print(
                "[yellow]Não foi possível determinar a próxima etapa.[/yellow]"
            )
            pause()
            return

        console.print()
        console.print("[bold]Próxima etapa recomendada:[/bold]")
        console.print(f"[cyan]→ {next_step_name}[/cyan]")

        choice = questionary.select(
            "Como deseja continuar?",
            choices=[
                "Executar etapa recomendada",
                "Voltar",
            ],
        ).ask()

        if choice is None or choice == "Voltar":
            return

        if next_step == "gbe":
            show_settings(config)

        elif next_step == "appid":
            resolve_game_appid_menu(game)

        elif next_step == "backup":
            create_game_backup(game)

        elif next_step == "settings":
            generate_steam_settings_menu(
                config,
                game=game,
            )

        elif next_step == "interfaces":
            generate_steam_interfaces_menu(
                config,
                game=game,
            )


def show_emu_config_summary(
    summary: EmuConfigSummary,
) -> None:
    table = Table.grid(padding=(0, 2))

    table.add_column(
        style="bold cyan",
        no_wrap=True,
    )

    table.add_column(
        style="white",
    )

    table.add_row(
        "Steam AppID",
        str(summary.app_id),
    )

    table.add_row(
        "Achievements",
        (
            f"[green]✓ {summary.achievements_count}[/green]"
            if summary.has_achievements
            else "[yellow]⚠ Não encontrados[/yellow]"
        ),
    )

    table.add_row(
        "Imagens",
        (
            f"[green]✓ {summary.achievement_images_count}[/green]"
            if summary.has_achievement_images
            else "[yellow]⚠ Nenhuma[/yellow]"
        ),
    )

    table.add_row(
        "Idiomas",
        str(summary.supported_languages_count),
    )

    table.add_row(
        "DLCs",
        str(summary.dlc_count),
    )

    table.add_row(
        "Depots",
        str(summary.depots_count),
    )

    table.add_row(
        "Branches",
        str(summary.branches_count),
    )

    table.add_row(
        "Product info",
        (
            "[green]✓ Sim[/green]"
            if summary.has_product_info
            else "[yellow]⚠ Não[/yellow]"
        ),
    )

    table.add_row(
        "App details",
        (
            "[green]✓ Sim[/green]"
            if summary.has_app_details
            else "[yellow]⚠ Não[/yellow]"
        ),
    )

    console.print(
        Panel(
            table,
            title="Dados gerados pelo GSE",
            border_style="green",
            box=box.ROUNDED,
        )
    )

    console.print()
    console.print("[dim]Output:[/dim]")
    console.print(f"[dim]{summary.output_directory}[/dim]")


def generate_emu_config_menu(
    config: AppConfig,
    game: Game | None = None,
) -> None:
    clear_screen()
    render_header()

    game = get_menu_game(
        config,
        game,
        ("Selecione o jogo para gerar dados Steam / achievements:"),
    )

    if game is None:
        return

    generator = config.goldberg.emu_config_generator

    if generator is None or not generator.is_file():
        console.print(
            Panel.fit(
                "[yellow]generate_emu_config "
                "não está configurado ou "
                "não foi encontrado.[/yellow]\n\n"
                "Entre em Configurações e use "
                "'Detectar generate_emu_config'.",
                border_style="yellow",
                box=box.ROUNDED,
            )
        )

        pause()
        return

    try:
        snapshot = read_game_steam_settings(game)
    except (OSError, ValueError) as exc:
        console.print(f"[red]Não foi possível ler steam_settings:[/red] {exc}")
        pause()
        return

    if snapshot.app_id is None:
        console.print(
            Panel.fit(
                "[yellow]Este jogo ainda não "
                "possui um Steam AppID "
                "configurado.[/yellow]\n\n"
                "Configure primeiro o AppID "
                "pelo Assistente.",
                border_style="yellow",
                box=box.ROUNDED,
            )
        )

        pause()
        return

    app_id = snapshot.app_id

    mode = questionary.select(
        "Como deseja acessar os dados Steam?",
        choices=[
            ("Autenticado (recomendado para achievements)"),
            "Anônimo",
            "Cancelar",
        ],
    ).ask()

    if mode is None or mode == "Cancelar":
        return

    anonymous = mode == "Anônimo"

    console.print()

    table = Table.grid(padding=(0, 2))

    table.add_column(
        style="bold cyan",
        no_wrap=True,
    )

    table.add_column(
        style="white",
    )

    table.add_row(
        "Jogo",
        game.name,
    )

    table.add_row(
        "Steam AppID",
        str(app_id),
    )

    table.add_row(
        "Generator",
        str(generator),
    )

    table.add_row(
        "Modo",
        ("Anônimo" if anonymous else "Autenticado"),
    )

    console.print(
        Panel(
            table,
            title="Geração de dados Steam",
            border_style="cyan",
            box=box.ROUNDED,
        )
    )

    console.print()

    console.print("[yellow]O diretório _OUTPUT deste AppID será recriado.[/yellow]")

    console.print("[dim]Nenhum arquivo do jogo será alterado nesta etapa.[/dim]")

    if not anonymous:
        console.print()
        console.print(
            "[cyan]O generate_emu_config "
            "poderá solicitar login, senha "
            "e Steam Guard diretamente "
            "no terminal.[/cyan]"
        )

        console.print("[dim]O Goldberg Manager não salvará essas credenciais.[/dim]")

    console.print()

    confirm = questionary.confirm(
        "Executar generate_emu_config agora?",
        default=True,
    ).ask()

    if not confirm:
        return

    console.print()
    console.print("[bold cyan]Iniciando generate_emu_config...[/bold cyan]")
    console.print()

    try:
        run_generate_emu_config(
            generator,
            app_id,
            anonymous=anonymous,
        )

        summary = read_generated_emu_summary(
            generator,
            app_id,
        )

    except (
        FileNotFoundError,
        EmuConfigError,
        OSError,
        ValueError,
    ) as exc:
        clear_screen()
        render_header()

        console.print(
            Panel.fit(
                f"[red]Falha ao gerar os dados Steam.[/red]\n\n{exc}",
                border_style="red",
                box=box.ROUNDED,
            )
        )

        pause()
        return

    clear_screen()
    render_header()

    console.print(
        Panel.fit(
            "[bold green]✓ Dados Steam gerados com sucesso![/bold green]",
            border_style="green",
            box=box.ROUNDED,
        )
    )

    console.print()

    show_emu_config_summary(summary)

    console.print()

    console.print("[dim]Os dados ainda não foram importados para o jogo.[/dim]")

    pause()


def import_generated_achievements_menu(
    config: AppConfig,
    game: Game | None = None,
) -> None:
    clear_screen()
    render_header()

    game = get_menu_game(
        config,
        game,
        ("Selecione o jogo para importar achievements gerados:"),
    )

    if game is None:
        return

    generator = config.goldberg.emu_config_generator

    if generator is None or not generator.is_file():
        console.print(
            Panel.fit(
                "[yellow]generate_emu_config "
                "não está configurado ou "
                "não foi encontrado.[/yellow]\n\n"
                "Entre em Configurações e use "
                "'Detectar generate_emu_config'.",
                border_style="yellow",
                box=box.ROUNDED,
            )
        )

        pause()
        return

    try:
        snapshot = read_game_steam_settings(game)
    except (OSError, ValueError) as exc:
        console.print(f"[red]Não foi possível ler steam_settings:[/red] {exc}")
        pause()
        return

    if snapshot.app_id is None:
        console.print(
            Panel.fit(
                "[yellow]Este jogo ainda não "
                "possui Steam AppID "
                "configurado.[/yellow]\n\n"
                "Configure primeiro o AppID "
                "pelo Assistente.",
                border_style="yellow",
                box=box.ROUNDED,
            )
        )

        pause()
        return

    app_id = snapshot.app_id

    try:
        summary = read_generated_emu_summary(
            generator,
            app_id,
        )
    except (
        EmuConfigError,
        OSError,
        ValueError,
    ) as exc:
        console.print(
            Panel.fit(
                f"[red]Não foi possível ler os dados gerados pelo GSE.[/red]\n\n{exc}",
                border_style="red",
                box=box.ROUNDED,
            )
        )

        pause()
        return

    if not summary.has_achievements:
        console.print(
            Panel.fit(
                "[yellow]Nenhum achievement "
                "foi encontrado no output "
                "deste AppID.[/yellow]\n\n"
                "Use primeiro a opção "
                "'Gerar dados Steam / achievements'.",
                border_style="yellow",
                box=box.ROUNDED,
            )
        )

        pause()
        return

    destination = get_steam_settings_directory(game)

    achievements_destination = destination / "achievements.json"

    images_destination = destination / "img"

    show_emu_config_summary(summary)

    console.print()

    destination_table = Table.grid(padding=(0, 2))

    destination_table.add_column(
        style="bold cyan",
        no_wrap=True,
    )

    destination_table.add_column(
        style="white",
    )

    destination_table.add_row(
        "Destino",
        str(destination),
    )

    destination_table.add_row(
        "Achievements",
        str(summary.achievements_count),
    )

    destination_table.add_row(
        "Imagens",
        str(summary.achievement_images_count),
    )

    console.print(
        Panel(
            destination_table,
            title="Importação",
            border_style="cyan",
            box=box.ROUNDED,
        )
    )

    existing_targets: list[Path] = []

    if achievements_destination.exists():
        existing_targets.append(achievements_destination)

    if images_destination.exists():
        existing_targets.append(images_destination)

    if existing_targets:
        console.print()
        console.print(
            "[yellow]Atenção: já existem "
            "dados de achievements no "
            "steam_settings.[/yellow]"
        )

        for path in existing_targets:
            console.print(f"[yellow]• {path}[/yellow]")

        console.print()
        console.print(
            "[dim]Um snapshot completo do "
            "steam_settings será criado "
            "antes da importação.[/dim]"
        )

    else:
        console.print()
        console.print("[dim]Nenhum achievement instalado foi encontrado.[/dim]")

    console.print()

    confirm = questionary.confirm(
        (f"Importar {summary.achievements_count} achievements para {game.name}?"),
        default=not existing_targets,
    ).ask()

    if not confirm:
        return

    if not create_settings_safety_backup(game):
        return

    try:
        result = import_generated_achievements(
            summary,
            destination,
        )
    except (
        EmuConfigError,
        OSError,
        ValueError,
    ) as exc:
        console.print(
            Panel.fit(
                f"[red]Falha ao importar achievements.[/red]\n\n{exc}",
                border_style="red",
                box=box.ROUNDED,
            )
        )

        pause()
        return

    if not result.achievements_file.is_file():
        console.print(
            Panel.fit(
                "[red]A importação terminou, "
                "mas achievements.json "
                "não foi encontrado no "
                "destino.[/red]",
                border_style="red",
                box=box.ROUNDED,
            )
        )

        pause()
        return

    clear_screen()
    render_header()

    result_table = Table.grid(padding=(0, 2))

    result_table.add_column(
        style="bold cyan",
        no_wrap=True,
    )

    result_table.add_column(
        style="white",
    )

    result_table.add_row(
        "Jogo",
        game.name,
    )

    result_table.add_row(
        "Achievements",
        (f"[green]✓ {result.achievements_count}[/green]"),
    )

    result_table.add_row(
        "Imagens",
        (
            f"[green]✓ {result.images_count}[/green]"
            if result.images_count
            else "[yellow]— Nenhuma[/yellow]"
        ),
    )

    result_table.add_row(
        "achievements.json",
        str(result.achievements_file),
    )

    if result.images_directory is not None:
        result_table.add_row(
            "Imagens",
            str(result.images_directory),
        )

    console.print(
        Panel(
            result_table,
            title="Achievements importados",
            border_style="green",
            box=box.ROUNDED,
        )
    )

    console.print()

    console.print("[bold green]✓ Importação concluída com sucesso![/bold green]")

    pause()


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

        generator = config.goldberg.emu_config_generator

        generator_ready = generator is not None and generator.is_file()

        table.add_row(
            "GSE generator",
            (
                "[green]✓ Configurado[/green]"
                if generator_ready
                else "[yellow]⚠ Não configurado[/yellow]"
            ),
        )

        steam_settings_directory = get_steam_settings_directory(game)

        try:
            installed_achievements = read_installed_achievements_status(
                steam_settings_directory
            )

        except EmuConfigError:
            achievements_status = "[red]✗ achievements.json inválido[/red]"

        else:
            if installed_achievements.installed:
                achievements_status = (
                    "[green]✓ "
                    f"{installed_achievements.achievements_count} "
                    "instalados[/green]"
                )

            else:
                generated_achievements = 0

                if (
                    generator_ready
                    and status.app_id_configured
                    and status.app_id is not None
                ):
                    try:
                        generated_summary = read_generated_emu_summary(
                            generator,
                            status.app_id,
                        )

                    except (
                        EmuConfigError,
                        OSError,
                        ValueError,
                    ):
                        pass

                    else:
                        if generated_summary.has_achievements:
                            generated_achievements = (
                                generated_summary.achievements_count
                            )

                if generated_achievements:
                    achievements_status = (
                        "[yellow]⚠ "
                        f"{generated_achievements} "
                        "gerados, não importados"
                        "[/yellow]"
                    )

                else:
                    achievements_status = "[dim]— Não gerados[/dim]"

        table.add_row(
            "Achievements",
            achievements_status,
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
                "Configuração guiada",
                "Detectar / configurar Steam AppID",
                "Gerenciar steam_settings",
                "Gerar steam_interfaces",
                "Gerar dados Steam / achievements",
                "Importar achievements gerados",
                "Fazer backup da Steam API",
                "Restaurar Steam API original",
                "Ver detalhes do jogo",
                "Voltar",
            ],
        ).ask()

        if choice is None or choice == "Voltar":
            return

        if choice == "Configuração guiada":
            guided_configuration_menu(
                config,
                game,
            )

        elif choice == "Detectar / configurar Steam AppID":
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

        elif choice == "Gerar dados Steam / achievements":
            generate_emu_config_menu(
                config,
                game=game,
            )

        elif choice == "Importar achievements gerados":
            import_generated_achievements_menu(
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
