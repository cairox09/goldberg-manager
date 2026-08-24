from __future__ import annotations

from rich import box
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table

from ..game_profile import GameProfile


def _game_profile_table() -> Table:
    table = Table.grid(padding=(0, 2))
    table.add_column(style="bold cyan", no_wrap=True)
    table.add_column(style="white")
    return table


def _profile_display_value(value: object) -> str:
    return escape(str(value))


def _print_game_profile_section(
    console: Console,
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


def render_game_profile(
    profile: GameProfile,
    *,
    console: Console,
) -> None:
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
    _print_game_profile_section(console, "Identidade", identity)

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
    _print_game_profile_section(console, "Settings", settings)

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
        console,
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
        console,
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
        console,
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
    _print_game_profile_section(console, "Heroic", heroic, border_style=heroic_border)

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
    _print_game_profile_section(console, "Steam", steam, border_style=steam_border)

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
            "[dim]Nenhuma evidência estrutural de prefixo via GSE ou Heroic "
            "disponível.[/dim]",
        )
        prefix_border = "cyan"
    _print_game_profile_section(
        console,
        "Prefix Consensus (GSE / Heroic)",
        prefix,
        border_style=prefix_border,
    )
