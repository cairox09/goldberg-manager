from __future__ import annotations

import ast
import unittest
from collections.abc import Callable
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
APPLICATION_ROOT = PROJECT_ROOT / "src" / "goldberg_manager" / "application"
CORE_ROOT = PROJECT_ROOT / "src" / "goldberg_manager" / "core"
PRESENTATION_ROOT = PROJECT_ROOT / "src" / "goldberg_manager" / "presentation"
VERSION_MODULE = PROJECT_ROOT / "src" / "goldberg_manager" / "version.py"


def _import_targets(node: ast.Import | ast.ImportFrom) -> tuple[str, ...]:
    if isinstance(node, ast.Import):
        return tuple(alias.name for alias in node.names)

    prefix = "." * node.level
    module = node.module or ""
    base = f"{prefix}{module}"
    targets = [base] if base else []
    targets.extend(
        f"{base}.{alias.name}" if base else alias.name for alias in node.names
    )
    return tuple(targets)


def _is_forbidden_application_import(target: str) -> bool:
    absolute_target = target.lstrip(".")
    parts = absolute_target.split(".")
    forbidden_modules = {"cli", "presentation", "questionary", "rich"}
    return parts[0] in forbidden_modules or (
        len(parts) >= 2
        and parts[0] == "goldberg_manager"
        and parts[1] in forbidden_modules
    )


def _is_forbidden_presentation_import(target: str) -> bool:
    absolute_target = target.lstrip(".")
    parts = absolute_target.split(".")
    return parts[0] in {"cli", "questionary"} or parts[:2] == [
        "goldberg_manager",
        "cli",
    ]


def _is_forbidden_core_import(target: str) -> bool:
    absolute_target = target.lstrip(".")
    parts = absolute_target.split(".")
    forbidden_modules = {
        "application",
        "cli",
        "presentation",
        "questionary",
        "rich",
        "scanner",
    }
    return parts[0] in forbidden_modules or (
        len(parts) >= 2
        and parts[0] == "goldberg_manager"
        and parts[1] in forbidden_modules
    )


def _is_forbidden_version_import(target: str) -> bool:
    absolute_target = target.lstrip(".")
    parts = absolute_target.split(".")
    return target.startswith(".") or parts[0] in {
        "goldberg_manager",
        "questionary",
        "rich",
    }


def _find_import_violations(
    root: Path,
    is_forbidden: Callable[[str], bool],
) -> list[str]:
    violations: list[str] = []

    paths = sorted(root.rglob("*.py")) if root.is_dir() else [root]

    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

        for node in ast.walk(tree):
            if not isinstance(node, (ast.Import, ast.ImportFrom)):
                continue

            for target in _import_targets(node):
                if is_forbidden(target):
                    relative_path = path.relative_to(PROJECT_ROOT)
                    violations.append(f"{relative_path}:{node.lineno}: {target}")

    return violations


class ArchitectureBoundaryTests(unittest.TestCase):
    def test_application_does_not_import_cli_rich_or_questionary(self) -> None:
        self.assertEqual(
            _find_import_violations(
                APPLICATION_ROOT,
                _is_forbidden_application_import,
            ),
            [],
        )

    def test_presentation_does_not_import_cli_or_questionary(self) -> None:
        self.assertEqual(
            _find_import_violations(
                PRESENTATION_ROOT,
                _is_forbidden_presentation_import,
            ),
            [],
        )

    def test_core_does_not_import_outer_layers_or_ui(self) -> None:
        self.assertEqual(
            _find_import_violations(CORE_ROOT, _is_forbidden_core_import),
            [],
        )

    def test_version_does_not_import_project_or_ui_modules(self) -> None:
        self.assertEqual(
            _find_import_violations(VERSION_MODULE, _is_forbidden_version_import),
            [],
        )


if __name__ == "__main__":
    unittest.main()
