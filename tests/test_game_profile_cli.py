from __future__ import annotations

import subprocess
import tempfile
import unittest
from contextlib import ExitStack
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from rich.console import Console

from goldberg_manager.cli import render_game_profile, show_game_profile
from goldberg_manager.scanner import Game


def namespace(**values: object) -> SimpleNamespace:
    return SimpleNamespace(**values)


def make_game(root: Path = Path("/games/Example"), name: str = "Example Game") -> Game:
    return Game(
        name=name,
        root_directory=root,
        executable=root / "Binaries" / "Game.exe",
        steam_api=root / "Binaries" / "steam_api64.dll",
        steam_api_relative_path=Path("Binaries/steam_api64.dll"),
        architecture="64-bit",
        source_directory=root.parent,
    )


def unknown_heroic() -> SimpleNamespace:
    return namespace(
        resolved=False,
        ambiguous=False,
        candidates=(),
        effective=None,
        strongest_evidence=None,
    )


def resolved_heroic(
    layout: str,
    *,
    configured_prefix: Path,
    structural_wine_prefix: Path | None,
    runner: str = "legendary",
    app_name: str = "example",
) -> SimpleNamespace:
    match = namespace(
        installed_game=namespace(id=namespace(runner=runner, app_name=app_name)),
        prefix=namespace(
            configured_prefix=configured_prefix,
            structural_wine_prefix=structural_wine_prefix,
            layout=namespace(name=layout),
        ),
    )
    return namespace(
        resolved=True,
        ambiguous=False,
        candidates=(match,),
        effective=match,
        strongest_evidence=namespace(value="game-root-equals-install-path"),
    )


def unknown_steam() -> SimpleNamespace:
    return namespace(
        resolved=False,
        ambiguous=False,
        candidates=(),
        effective=None,
        prefix=None,
        strongest_evidence=None,
    )


def resolved_steam(
    library_root: Path,
    *,
    app_id: int,
    install_path: Path,
    structural_wine_prefix: Path,
) -> SimpleNamespace:
    match = namespace(
        installed_game=namespace(
            app_id=app_id,
            library_root=library_root,
            install_path=install_path,
        )
    )
    return namespace(
        resolved=True,
        ambiguous=False,
        candidates=(match,),
        effective=match,
        prefix=namespace(
            layout=namespace(name="PFX_SUBDIRECTORY"),
            structural_wine_prefix=structural_wine_prefix,
        ),
        strongest_evidence=namespace(value="game-root-equals-install-path"),
    )


def unknown_consensus() -> SimpleNamespace:
    return namespace(
        resolved=False,
        conflict=False,
        evidences=(),
        effective_wine_prefix=None,
        effective_drive_c=None,
    )


def resolved_consensus(
    wine_prefix: Path,
    sources: tuple[str, ...] = ("HEROIC",),
) -> SimpleNamespace:
    return namespace(
        resolved=True,
        conflict=False,
        evidences=tuple(
            namespace(source=namespace(name=source), wine_prefix=wine_prefix)
            for source in sources
        ),
        effective_wine_prefix=wine_prefix,
        effective_drive_c=wine_prefix / "drive_c",
    )


def make_profile(
    *,
    game: Game | None = None,
    app_id: int | None = 212480,
) -> SimpleNamespace:
    if game is None:
        game = make_game()
    save_location = namespace(root=Path("/saves/GSE Saves"))
    save_resolution = namespace(
        source="default",
        raw_value=None,
        locations=(save_location,),
        effective_locations=(save_location,),
        ambiguous=False,
    )
    report = namespace(
        runtime_path=Path("/saves/GSE Saves/212480/achievements.json"),
        total=20,
        unlocked=8,
        locked=12,
        completion_percentage=40.0,
    )
    status = namespace(
        exists=True,
        valid_json=True,
        schema_valid=True,
        configured=True,
        path=Path("/config/sentinel/config.json"),
        error=None,
    )
    coverage = namespace(
        fully_watched=True,
        partially_watched=False,
        unwatched=False,
        effective_save_resolved=True,
        recognized_by_sentinel=True,
    )
    heroic_prefix = Path("/prefixes/example")
    return namespace(
        game=game,
        architecture=game.architecture,
        app_id=app_id,
        app_id_confidence=100 if app_id is not None else None,
        app_id_source="steam_appid.txt" if app_id is not None else None,
        settings=namespace(
            account_name="Player",
            account_steamid=76561198000000000,
            language="brazilian",
            ip_country="BR",
            local_save_path="./custom-saves",
            saves_folder_name=None,
        ),
        gse=namespace(save_resolution=save_resolution),
        achievements=namespace(
            metadata_path=Path("/games/Example/steam_settings/achievements.json"),
            metadata_exists=True,
            reports=(report,),
            errors=(),
        ),
        sentinel=namespace(
            installation=namespace(
                installed=True,
                executable=Path("/usr/bin/sentinel"),
            ),
            status=status,
            coverage=coverage,
        ),
        heroic=resolved_heroic(
            "DIRECT",
            configured_prefix=heroic_prefix,
            structural_wine_prefix=heroic_prefix,
        ),
        steam=unknown_steam(),
        prefix_consensus=resolved_consensus(
            heroic_prefix,
            sources=("GSE_RUNTIME", "HEROIC"),
        ),
    )


def render(profile: SimpleNamespace) -> str:
    output = StringIO()
    test_console = Console(file=output, width=220, color_system=None)
    with patch("goldberg_manager.cli.console", test_console):
        render_game_profile(profile)
    return output.getvalue()


class GameProfilePresentationTests(unittest.TestCase):
    def test_dynamic_rich_markup_is_rendered_literally(self) -> None:
        game = make_game(
            Path("/Games/[DODI Repack]"),
            "Example [/bold][red]Game[/red]",
        )
        profile = make_profile(game=game)
        profile.settings.account_name = "[red]Player[/red]"
        profile.settings.language = "[blue]brazilian[/blue]"
        profile.settings.local_save_path = "/Saves/[Backup]"
        save_location = namespace(root=Path("/Saves/[Backup]/GSE Saves"))
        profile.gse.save_resolution = namespace(
            source="[yellow]custom[/yellow]",
            raw_value="/Saves/[Backup]",
            locations=(save_location,),
            effective_locations=(save_location,),
            ambiguous=False,
        )
        profile.sentinel.status.error = "bad [/red] metadata"
        profile.heroic = resolved_heroic(
            "DIRECT",
            configured_prefix=Path("/Heroic/[Prefix]"),
            structural_wine_prefix=Path("/Heroic/[Prefix]"),
            runner="[cyan]legendary[/cyan]",
            app_name="Heroic [/green][DODI]",
        )
        profile.steam = resolved_steam(
            Path("/Steam/[Library]"),
            app_id=291550,
            install_path=Path("/Steam/[Library]/Brawlhalla"),
            structural_wine_prefix=Path("/Steam/[Library]/compatdata/291550/pfx"),
        )
        profile.prefix_consensus = namespace(
            resolved=False,
            conflict=True,
            evidences=(
                namespace(
                    source=namespace(name="GSE_RUNTIME"),
                    wine_prefix=Path("/Prefixes/[GSE]"),
                ),
                namespace(
                    source=namespace(name="HEROIC"),
                    wine_prefix=Path("/Prefixes/[Heroic]"),
                ),
            ),
            effective_wine_prefix=None,
            effective_drive_c=None,
        )

        rendered = render(profile)

        for expected in (
            "Example [/bold][red]Game[/red]",
            "/Games/[DODI Repack]/Binaries/Game.exe",
            "[red]Player[/red]",
            "[blue]brazilian[/blue]",
            "/Saves/[Backup]/GSE Saves",
            "[yellow]custom[/yellow]",
            "bad [/red] metadata",
            "[cyan]legendary[/cyan]",
            "Heroic [/green][DODI]",
            "/Heroic/[Prefix]",
            "/Steam/[Library]",
            "/Prefixes/[GSE]",
            "RESOLVED",
            "CONFLICT",
        ):
            self.assertIn(expected, rendered)
        self.assertNotIn("[green]✓ RESOLVED[/green]", rendered)
        self.assertNotIn("[red]✗ CONFLICT[/red]", rendered)

    def test_known_identity_settings_progress_sentinel_and_multiple_sources(
        self,
    ) -> None:
        rendered = render(make_profile())

        for expected in (
            "Example Game",
            "212480",
            "steam_appid.txt",
            "100%",
            "64-bit",
            "/games/Example/Binaries/Game.exe",
            "Player",
            "76561198000000000",
            "brazilian",
            "BR",
            "./custom-saves",
            "Total",
            "20",
            "Desbloqueadas",
            "8",
            "Bloqueadas",
            "12",
            "40.0%",
            "Cobertura completa",
            "GSE_RUNTIME, HEROIC",
        ):
            self.assertIn(expected, rendered)

    def test_unknown_identity_settings_and_runtime_are_honest(self) -> None:
        profile = make_profile(app_id=None)
        profile.settings = namespace(
            account_name=None,
            account_steamid=None,
            language=None,
            ip_country=None,
            local_save_path=None,
            saves_folder_name=None,
        )
        profile.achievements.reports = (
            namespace(
                runtime_path=None,
                total=12,
                unlocked=0,
                locked=12,
                completion_percentage=0.0,
            ),
        )
        profile.achievements.metadata_exists = True
        profile.heroic = unknown_heroic()
        profile.prefix_consensus = unknown_consensus()

        rendered = render(profile)

        self.assertIn("AppID", rendered)
        self.assertIn("Não identificado", rendered)
        self.assertIn("Nenhuma configuração identificada", rendered)
        self.assertIn("Total", rendered)
        self.assertIn("12", rendered)
        self.assertIn("Runtime indisponível", rendered)
        self.assertNotIn("Desbloqueadas", rendered)
        self.assertIn("Heroic ownership não identificado", rendered)
        self.assertIn("Steam ownership não identificado", rendered)
        self.assertIn("Prefix Consensus (GSE / Heroic)", rendered)
        self.assertIn(
            "Nenhuma evidência estrutural de prefixo via GSE ou Heroic disponível",
            rendered,
        )

        profile.achievements.metadata_exists = False
        profile.achievements.reports = ()
        rendered = render(profile)
        self.assertIn("Metadata", rendered)
        self.assertIn("Não encontrada", rendered)

    def test_invalid_sentinel_and_prefix_conflict_are_explicit(self) -> None:
        profile = make_profile()
        profile.sentinel.status.exists = True
        profile.sentinel.status.valid_json = False
        profile.sentinel.status.schema_valid = False
        profile.sentinel.status.configured = False
        profile.sentinel.status.error = "JSON inválido"
        profile.sentinel.coverage.fully_watched = False
        profile.sentinel.coverage.effective_save_resolved = False
        profile.prefix_consensus = namespace(
            resolved=False,
            conflict=True,
            evidences=(
                namespace(
                    source=namespace(name="GSE_RUNTIME"),
                    wine_prefix=Path("/prefixes/gse"),
                ),
                namespace(
                    source=namespace(name="HEROIC"),
                    wine_prefix=Path("/prefixes/heroic"),
                ),
            ),
            effective_wine_prefix=None,
            effective_drive_c=None,
        )

        rendered = render(profile)

        self.assertIn("Inválida", rendered)
        self.assertIn("JSON inválido", rendered)
        self.assertIn("CONFLICT", rendered)
        self.assertIn("Nenhuma fonte foi selecionada", rendered)
        self.assertIn("/prefixes/gse", rendered)
        self.assertIn("/prefixes/heroic", rendered)

    def test_sonic_like_profile(self) -> None:
        profile = make_profile(game=make_game(name="Sonic Frontiers"))
        location = namespace(root=Path("/custom/sonic/GSE Saves"))
        profile.gse.save_resolution = namespace(
            source="GseSavePath",
            raw_value="/custom/sonic/GSE Saves",
            locations=(location,),
            effective_locations=(location,),
            ambiguous=False,
        )
        profile.heroic = resolved_heroic(
            "DIRECT",
            configured_prefix=Path("/heroic/Prefixes/Sonic"),
            structural_wine_prefix=Path("/heroic/Prefixes/Sonic"),
            app_name="SonicFrontiers",
        )
        profile.steam = unknown_steam()
        profile.prefix_consensus = resolved_consensus(Path("/heroic/Prefixes/Sonic"))

        rendered = render(profile)

        self.assertIn("Sonic Frontiers", rendered)
        self.assertIn("GseSavePath", rendered)
        self.assertIn("/custom/sonic/GSE Saves", rendered)
        self.assertIn("SonicFrontiers", rendered)
        self.assertIn("DIRECT", rendered)
        self.assertIn("Configured prefix", rendered)
        self.assertIn("Structural Wine prefix", rendered)
        self.assertIn("Steam ownership não identificado", rendered)

    def test_tlou_like_profile(self) -> None:
        profile = make_profile(game=make_game(name="The Last of Us Part I"))
        locations = (
            namespace(root=Path("/prefix-a/GSE Saves")),
            namespace(root=Path("/prefix-b/GSE Saves")),
        )
        profile.gse.save_resolution = namespace(
            source="default",
            raw_value=None,
            locations=locations,
            effective_locations=(),
            ambiguous=True,
        )
        profile.heroic = resolved_heroic(
            "PFX_SUBDIRECTORY",
            configured_prefix=Path("/heroic/Prefixes/TLOU"),
            structural_wine_prefix=Path("/heroic/Prefixes/TLOU/pfx"),
            app_name="TLOU",
        )
        profile.prefix_consensus = resolved_consensus(Path("/heroic/Prefixes/TLOU/pfx"))

        rendered = render(profile)

        self.assertIn("The Last of Us Part I", rendered)
        self.assertIn("Ambígua", rendered)
        self.assertIn("Save efetivo", rendered)
        self.assertIn("Não determinado", rendered)
        self.assertIn("Save possível #1", rendered)
        self.assertIn("Save possível #2", rendered)
        self.assertIn("PFX_SUBDIRECTORY", rendered)
        self.assertIn("Fonte", rendered)
        self.assertIn("HEROIC", rendered)

    def test_invincible_like_profile(self) -> None:
        profile = make_profile(game=make_game(name="Invincible Presents: Atom Eve"))
        profile.heroic = resolved_heroic(
            "MISSING",
            configured_prefix=Path("/heroic/Prefixes/Invincible"),
            structural_wine_prefix=None,
            app_name="Invincible",
        )
        profile.prefix_consensus = unknown_consensus()

        rendered = render(profile)

        self.assertIn("Invincible Presents: Atom Eve", rendered)
        self.assertIn("MISSING", rendered)
        self.assertIn("/heroic/Prefixes/Invincible", rendered)
        self.assertIn("Structural Wine prefix", rendered)
        self.assertIn("Não disponível", rendered)
        self.assertIn(
            "Nenhuma evidência estrutural de prefixo via GSE ou Heroic disponível",
            rendered,
        )

    def test_brawlhalla_like_profile(self) -> None:
        game = make_game(Path("/steam/steamapps/common/Brawlhalla"), "Brawlhalla")
        profile = make_profile(game=game, app_id=291550)
        profile.heroic = unknown_heroic()
        profile.steam = resolved_steam(
            Path("/steam"),
            app_id=291550,
            install_path=game.root_directory,
            structural_wine_prefix=Path("/steam/steamapps/compatdata/291550/pfx"),
        )
        profile.prefix_consensus = unknown_consensus()

        rendered = render(profile)

        self.assertIn("Brawlhalla", rendered)
        self.assertIn("Heroic ownership não identificado", rendered)
        self.assertIn("AppID efetivo", rendered)
        self.assertIn("291550", rendered)
        self.assertIn("/steam/steamapps/common/Brawlhalla", rendered)
        self.assertIn("PFX_SUBDIRECTORY", rendered)
        self.assertIn("/steam/steamapps/compatdata/291550/pfx", rendered)
        self.assertIn("Prefix Consensus (GSE / Heroic)", rendered)
        self.assertIn("UNKNOWN", rendered)
        self.assertIn(
            "Nenhuma evidência estrutural de prefixo via GSE ou Heroic disponível",
            rendered,
        )


class GameProfileActionTests(unittest.TestCase):
    def test_resolution_error_markup_is_escaped_and_pauses(self) -> None:
        game = make_game()
        output = StringIO()
        test_console = Console(file=output, width=220, color_system=None)

        with (
            patch("goldberg_manager.cli.clear_screen"),
            patch("goldberg_manager.cli.render_header"),
            patch("goldberg_manager.cli.console", test_console),
            patch(
                "goldberg_manager.cli.resolve_game_profile",
                side_effect=ValueError("invalid [/red] profile"),
            ) as resolver,
            patch("goldberg_manager.cli.render_game_profile") as renderer,
            patch("goldberg_manager.cli.pause") as pause,
        ):
            show_game_profile(game)

        resolver.assert_called_once_with(game)
        renderer.assert_not_called()
        pause.assert_called_once_with()
        self.assertIn("Não foi possível resolver o perfil do jogo", output.getvalue())
        self.assertIn("invalid [/red] profile", output.getvalue())

    def test_action_resolves_exactly_once_and_renders_same_snapshot(self) -> None:
        game = make_game()
        profile = make_profile(game=game)

        with (
            patch("goldberg_manager.cli.clear_screen"),
            patch("goldberg_manager.cli.render_header"),
            patch(
                "goldberg_manager.cli.resolve_game_profile",
                return_value=profile,
            ) as resolver,
            patch("goldberg_manager.cli.render_game_profile") as renderer,
            patch("goldberg_manager.cli.pause") as pause,
            patch("goldberg_manager.cli.console.print"),
        ):
            show_game_profile(game)

        resolver.assert_called_once_with(game)
        renderer.assert_called_once_with(profile)
        pause.assert_called_once_with()

    def test_action_is_read_only_and_does_not_launch_subprocesses(self) -> None:
        writer_names = (
            "apply_game_sentinel_repair",
            "backup_game",
            "create_steam_settings_backup",
            "generate_game_steam_interfaces",
            "generate_game_steam_settings",
            "import_generated_achievements",
            "restore_game_backup",
            "restore_steam_settings_backup",
            "run_generate_emu_config",
            "save_config",
            "update_game_steam_appid",
            "update_user_setting",
        )
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            game = make_game(root / "Game")
            profile = make_profile(game=game)
            before = {path.relative_to(root) for path in root.rglob("*")}
            output = StringIO()
            test_console = Console(file=output, width=220, color_system=None)

            with ExitStack() as stack:
                stack.enter_context(patch("goldberg_manager.cli.clear_screen"))
                stack.enter_context(patch("goldberg_manager.cli.render_header"))
                stack.enter_context(patch("goldberg_manager.cli.pause"))
                stack.enter_context(patch("goldberg_manager.cli.console", test_console))
                resolver = stack.enter_context(
                    patch(
                        "goldberg_manager.cli.resolve_game_profile",
                        return_value=profile,
                    )
                )
                writers = [
                    stack.enter_context(patch(f"goldberg_manager.cli.{name}"))
                    for name in writer_names
                ]
                run = stack.enter_context(patch.object(subprocess, "run"))
                popen = stack.enter_context(patch.object(subprocess, "Popen"))

                show_game_profile(game)

            after = {path.relative_to(root) for path in root.rglob("*")}

        self.assertEqual(after, before)
        resolver.assert_called_once_with(game)
        for writer in writers:
            writer.assert_not_called()
        run.assert_not_called()
        popen.assert_not_called()
        self.assertIn("Somente leitura", output.getvalue())


if __name__ == "__main__":
    unittest.main()
