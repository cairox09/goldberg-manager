from __future__ import annotations

from rich import box
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table

from ..game_profile import GameProfile
from .i18n import Translations, load_translations


def _game_profile_table() -> Table:
    table = Table.grid(padding=(0, 2))
    table.add_column(style="bold cyan", no_wrap=True)
    table.add_column(style="white")
    return table


def _profile_display_value(value: object) -> str:
    return escape(str(value))


def _profile_message(
    translations: Translations,
    message: str,
    **values: object,
) -> str:
    translated = translations.gettext(message)
    if values:
        translated = translated.format(**values)
    return _profile_display_value(translated)


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
    translations: Translations | None = None,
) -> None:
    if translations is None:
        translations = load_translations()

    unavailable = f"[dim]— {_profile_message(translations, 'Não disponível')}[/dim]"

    console.print(
        Panel.fit(
            f"[bold]{_profile_display_value(profile.game.name)}[/bold]",
            title=_profile_message(translations, "Perfil do jogo"),
            border_style="cyan",
            box=box.ROUNDED,
        )
    )

    identity = _game_profile_table()
    if profile.app_id is None:
        app_id = f"[dim]— {_profile_message(translations, 'Não identificado')}[/dim]"
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
                    f"{_profile_display_value(profile.app_id_confidence)}%"
                    if profile.app_id_confidence is not None
                    else None
                ),
            )
            if detail is not None
        ]
        metadata = f" • {' • '.join(app_id_details)}" if app_id_details else ""
        app_id = f"[green]✓ {_profile_display_value(profile.app_id)}[/green]{metadata}"
    identity.add_row("AppID", app_id)
    identity.add_row(
        _profile_message(translations, "Arquitetura"),
        _profile_display_value(profile.architecture),
    )
    identity.add_row(
        _profile_message(translations, "Executável"),
        _profile_display_value(profile.game.executable),
    )
    identity.add_row("Steam API", _profile_display_value(profile.game.steam_api))
    _print_game_profile_section(
        console,
        _profile_message(translations, "Identidade"),
        identity,
    )

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
        settings.add_row(
            _profile_message(translations, "Status"),
            f"[dim]— {_profile_message(translations, 'Nenhuma configuração identificada')}[/dim]",
        )
    else:
        if settings_snapshot.account_name is not None:
            settings.add_row(
                _profile_message(translations, "Conta"),
                _profile_display_value(settings_snapshot.account_name),
            )
        if settings_snapshot.account_steamid is not None:
            settings.add_row(
                "SteamID",
                _profile_display_value(settings_snapshot.account_steamid),
            )
        if settings_snapshot.language is not None:
            settings.add_row(
                _profile_message(translations, "Idioma"),
                _profile_display_value(settings_snapshot.language),
            )
        if settings_snapshot.ip_country is not None:
            settings.add_row(
                _profile_message(translations, "País"),
                _profile_display_value(settings_snapshot.ip_country),
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
    _print_game_profile_section(
        console,
        _profile_message(translations, "Configurações"),
        settings,
    )

    saves = _game_profile_table()
    save_resolution = profile.gse.save_resolution
    if save_resolution is None:
        saves.add_row(
            _profile_message(translations, "Resolução"),
            f"[dim]— {_profile_message(translations, 'GSE save não identificado')}[/dim]",
        )
    else:
        saves.add_row(
            _profile_message(translations, "Origem"),
            _profile_display_value(save_resolution.source),
        )
        if save_resolution.raw_value is not None:
            saves.add_row(
                _profile_message(translations, "Valor configurado"),
                _profile_display_value(save_resolution.raw_value),
            )

        effective_locations = save_resolution.effective_locations
        if save_resolution.ambiguous:
            saves.add_row(
                _profile_message(translations, "Resolução"),
                f"[yellow]⚠ {_profile_message(translations, 'Ambígua')}[/yellow]",
            )
            saves.add_row(
                _profile_message(translations, "Save efetivo"),
                f"[dim]— {_profile_message(translations, 'Não determinado')}[/dim]",
            )
        elif effective_locations:
            saves.add_row(
                _profile_message(translations, "Resolução"),
                f"[green]✓ {_profile_message(translations, 'Determinada')}[/green]",
            )
            for location in effective_locations:
                saves.add_row(
                    _profile_message(translations, "Save efetivo"),
                    _profile_display_value(location.root),
                )
        else:
            saves.add_row(
                _profile_message(translations, "Resolução"),
                f"[dim]— {_profile_message(translations, 'Caminho não resolvido')}[/dim]",
            )

        if save_resolution.ambiguous:
            for index, location in enumerate(save_resolution.locations, start=1):
                saves.add_row(
                    _profile_message(
                        translations,
                        "Save possível #{index}",
                        index=index,
                    ),
                    _profile_display_value(location.root),
                )
    _print_game_profile_section(
        console,
        _profile_message(translations, "Saves / GSE"),
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
            f"[red]✗ {_profile_message(translations, 'Inválida')}[/red] • "
            f"{_profile_display_value(achievement_resolution.metadata_path)}"
        )
    elif achievement_resolution.metadata_exists:
        metadata_status = (
            f"[green]✓ {_profile_message(translations, 'Encontrada')}[/green] • "
            f"{_profile_display_value(achievement_resolution.metadata_path)}"
        )
    else:
        metadata_status = (
            f"[yellow]⚠ {_profile_message(translations, 'Não encontrada')}[/yellow] • "
            f"{_profile_display_value(achievement_resolution.metadata_path)}"
        )
    achievements.add_row(_profile_message(translations, "Metadados"), metadata_status)
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
            runtime_label = (
                _profile_message(translations, "Runtime #{index}", index=index)
                if multiple_reports
                else _profile_message(translations, "Runtime")
            )
            total_label = (
                _profile_message(translations, "Total #{index}", index=index)
                if multiple_reports
                else _profile_message(translations, "Total")
            )
            unlocked_label = (
                _profile_message(
                    translations,
                    "Desbloqueadas #{index}",
                    index=index,
                )
                if multiple_reports
                else _profile_message(translations, "Desbloqueadas")
            )
            locked_label = (
                _profile_message(
                    translations,
                    "Bloqueadas #{index}",
                    index=index,
                )
                if multiple_reports
                else _profile_message(translations, "Bloqueadas")
            )
            completion_label = (
                _profile_message(
                    translations,
                    "Conclusão #{index}",
                    index=index,
                )
                if multiple_reports
                else _profile_message(translations, "Conclusão")
            )
            achievements.add_row(
                runtime_label,
                _profile_display_value(report.runtime_path),
            )
            achievements.add_row(total_label, _profile_display_value(report.total))
            achievements.add_row(
                unlocked_label,
                _profile_display_value(report.unlocked),
            )
            achievements.add_row(locked_label, _profile_display_value(report.locked))
            achievements.add_row(
                completion_label,
                f"{report.completion_percentage:.1f}%",
            )
    else:
        achievements.add_row(
            _profile_message(translations, "Total"),
            (
                _profile_display_value(metadata_report.total)
                if metadata_report is not None
                else unavailable
            ),
        )
        achievements.add_row(
            _profile_message(translations, "Progresso"),
            f"[dim]— {_profile_message(translations, 'Runtime indisponível')}[/dim]",
        )
    if achievement_resolution.errors:
        achievements.add_row(
            _profile_message(translations, "Erros de leitura"),
            f"[red]✗ {_profile_display_value(len(achievement_resolution.errors))}[/red]",
        )
    _print_game_profile_section(
        console,
        _profile_message(translations, "Conquistas"),
        achievements,
        border_style="green" if runtime_reports else "yellow",
    )

    sentinel = _game_profile_table()
    installation = profile.sentinel.installation
    status = profile.sentinel.status
    coverage = profile.sentinel.coverage
    sentinel.add_row(
        _profile_message(translations, "Instalação"),
        (
            f"[green]✓ {_profile_message(translations, 'Detectada')}[/green] • "
            f"{_profile_display_value(installation.executable)}"
            if installation.installed
            else f"[yellow]⚠ {_profile_message(translations, 'Não detectada')}[/yellow]"
        ),
    )
    if not status.exists:
        config_status = (
            f"[yellow]⚠ {_profile_message(translations, 'Ausente')}[/yellow]"
        )
    elif not status.valid_json or not status.schema_valid:
        config_status = f"[red]✗ {_profile_message(translations, 'Inválida')}[/red]"
    else:
        config_status = f"[green]✓ {_profile_message(translations, 'Válida')}[/green]"
    sentinel.add_row(_profile_message(translations, "Configuração"), config_status)
    sentinel.add_row(
        _profile_message(translations, "Caminho da configuração"),
        _profile_display_value(status.path),
    )
    if status.error is not None:
        sentinel.add_row(
            _profile_message(translations, "Diagnóstico"),
            f"[red]{_profile_display_value(status.error)}[/red]",
        )

    if coverage.fully_watched:
        coverage_status = (
            f"[green]✓ {_profile_message(translations, 'Cobertura completa')}[/green]"
        )
    elif coverage.partially_watched:
        coverage_status = (
            f"[yellow]⚠ {_profile_message(translations, 'Cobertura parcial')}[/yellow]"
        )
    elif coverage.unwatched:
        coverage_status = f"[yellow]⚠ {_profile_message(translations, 'Save efetivo não coberto')}[/yellow]"
    elif coverage.effective_save_resolved:
        coverage_status = f"[yellow]⚠ {_profile_message(translations, 'Cobertura não confirmada')}[/yellow]"
    else:
        coverage_status = f"[dim]— {_profile_message(translations, 'Sem save efetivo para avaliar')}[/dim]"
    sentinel.add_row(_profile_message(translations, "Integração GSE"), coverage_status)
    if coverage.recognized_by_sentinel:
        sentinel.add_row(
            _profile_message(translations, "Runtime do Sentinel"),
            f"[green]✓ {_profile_message(translations, 'Reconhecido')}[/green]",
        )
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
        heroic.add_row(
            _profile_message(translations, "Status"),
            f"[green]✓ {_profile_message(translations, 'RESOLVIDO')}[/green]",
        )
        heroic_match = heroic_provenance.effective
        assert heroic_match is not None
        heroic.add_row(
            "Runner",
            _profile_display_value(heroic_match.installed_game.id.runner),
        )
        heroic.add_row(
            _profile_message(translations, "Nome do aplicativo"),
            _profile_display_value(heroic_match.installed_game.id.app_name),
        )
        heroic.add_row(
            _profile_message(translations, "Evidência"),
            (
                _profile_display_value(heroic_provenance.strongest_evidence.value)
                if heroic_provenance.strongest_evidence is not None
                else unavailable
            ),
        )
        heroic.add_row(
            _profile_message(translations, "Prefixo configurado"),
            (
                _profile_display_value(heroic_match.prefix.configured_prefix)
                if heroic_match.prefix.configured_prefix is not None
                else unavailable
            ),
        )
        heroic.add_row(
            _profile_message(translations, "Prefixo Wine estrutural"),
            (
                _profile_display_value(heroic_match.prefix.structural_wine_prefix)
                if heroic_match.prefix.structural_wine_prefix is not None
                else unavailable
            ),
        )
        heroic.add_row(
            _profile_message(translations, "Layout do prefixo"),
            _profile_display_value(heroic_match.prefix.layout.name),
        )
        heroic_border = (
            "green"
            if heroic_match.prefix.structural_wine_prefix is not None
            else "yellow"
        )
    elif heroic_provenance.ambiguous:
        heroic.add_row(
            _profile_message(translations, "Status"),
            f"[yellow]⚠ {_profile_message(translations, 'AMBÍGUO')}[/yellow]",
        )
        heroic.add_row(
            _profile_message(translations, "Propriedade"),
            f"[yellow]{_profile_message(translations, 'Mais de uma correspondência no Heroic')}[/yellow]",
        )
        heroic.add_row(
            _profile_message(translations, "Candidatos"),
            _profile_display_value(len(heroic_provenance.candidates)),
        )
        heroic_border = "yellow"
    else:
        heroic.add_row(
            _profile_message(translations, "Status"),
            f"[dim]{_profile_message(translations, 'DESCONHECIDO')}[/dim]",
        )
        heroic.add_row(
            _profile_message(translations, "Propriedade"),
            f"[dim]{_profile_message(translations, 'Propriedade no Heroic não identificada.')}[/dim]",
        )
        heroic_border = "cyan"
    _print_game_profile_section(console, "Heroic", heroic, border_style=heroic_border)

    steam = _game_profile_table()
    steam_provenance = profile.steam
    if steam_provenance.resolved:
        steam.add_row(
            _profile_message(translations, "Status"),
            f"[green]✓ {_profile_message(translations, 'RESOLVIDO')}[/green]",
        )
        steam_match = steam_provenance.effective
        steam_prefix = steam_provenance.prefix
        assert steam_match is not None
        assert steam_prefix is not None
        steam.add_row(
            _profile_message(translations, "AppID efetivo"),
            _profile_display_value(steam_match.installed_game.app_id),
        )
        steam.add_row(
            _profile_message(translations, "Biblioteca"),
            _profile_display_value(steam_match.installed_game.library_root),
        )
        steam.add_row(
            _profile_message(translations, "Caminho de instalação"),
            _profile_display_value(steam_match.installed_game.install_path),
        )
        steam.add_row(
            _profile_message(translations, "Evidência"),
            (
                _profile_display_value(steam_provenance.strongest_evidence.value)
                if steam_provenance.strongest_evidence is not None
                else unavailable
            ),
        )
        steam.add_row(
            _profile_message(translations, "Layout do prefixo"),
            _profile_display_value(steam_prefix.layout.name),
        )
        if steam_prefix.structural_wine_prefix is not None:
            steam.add_row(
                _profile_message(translations, "Prefixo Wine estrutural"),
                _profile_display_value(steam_prefix.structural_wine_prefix),
            )
        steam_border = (
            "green" if steam_prefix.structural_wine_prefix is not None else "yellow"
        )
    elif steam_provenance.ambiguous:
        steam.add_row(
            _profile_message(translations, "Status"),
            f"[yellow]⚠ {_profile_message(translations, 'AMBÍGUO')}[/yellow]",
        )
        steam.add_row(
            _profile_message(translations, "Propriedade"),
            f"[yellow]{_profile_message(translations, 'Mais de uma correspondência na Steam')}[/yellow]",
        )
        steam.add_row(
            _profile_message(translations, "Candidatos"),
            _profile_display_value(len(steam_provenance.candidates)),
        )
        steam_border = "yellow"
    else:
        steam.add_row(
            _profile_message(translations, "Status"),
            f"[dim]{_profile_message(translations, 'DESCONHECIDO')}[/dim]",
        )
        steam.add_row(
            _profile_message(translations, "Propriedade"),
            f"[dim]{_profile_message(translations, 'Propriedade na Steam não identificada.')}[/dim]",
        )
        steam_border = "cyan"
    _print_game_profile_section(console, "Steam", steam, border_style=steam_border)

    prefix = _game_profile_table()
    consensus = profile.prefix_consensus
    if consensus.resolved:
        prefix.add_row(
            _profile_message(translations, "Status"),
            f"[green]✓ {_profile_message(translations, 'RESOLVIDO')}[/green]",
        )
        prefix.add_row(
            _profile_message(translations, "Prefixo Wine efetivo"),
            _profile_display_value(consensus.effective_wine_prefix),
        )
        prefix.add_row(
            _profile_message(translations, "drive_c efetivo"),
            _profile_display_value(consensus.effective_drive_c),
        )
        sources = ", ".join(
            _profile_display_value(evidence.source.name)
            for evidence in consensus.evidences
        )
        prefix.add_row(
            _profile_message(
                translations,
                "Fontes" if len(consensus.evidences) > 1 else "Fonte",
            ),
            sources,
        )
        prefix_border = "green"
    elif consensus.conflict:
        prefix.add_row(
            _profile_message(translations, "Status"),
            f"[red]✗ {_profile_message(translations, 'CONFLITO')}[/red]",
        )
        prefix.add_row(
            _profile_message(translations, "Resultado"),
            f"[red]{_profile_message(translations, 'Nenhuma fonte foi selecionada.')}[/red]",
        )
        for evidence in consensus.evidences:
            prefix.add_row(
                _profile_display_value(evidence.source.name),
                _profile_display_value(evidence.wine_prefix),
            )
        prefix_border = "red"
    else:
        prefix.add_row(
            _profile_message(translations, "Status"),
            f"[dim]{_profile_message(translations, 'DESCONHECIDO')}[/dim]",
        )
        prefix.add_row(
            _profile_message(translations, "Resultado"),
            f"[dim]{_profile_message(translations, 'Nenhuma evidência estrutural de prefixo via GSE ou Heroic disponível.')}[/dim]",
        )
        prefix_border = "cyan"
    _print_game_profile_section(
        console,
        _profile_message(translations, "Consenso de prefixo (GSE / Heroic)"),
        prefix,
        border_style=prefix_border,
    )
