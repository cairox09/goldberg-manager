from __future__ import annotations

import ast
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
APPLICATION_ROOT = PROJECT_ROOT / "src" / "goldberg_manager" / "application"


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
    return parts[0] in {"cli", "rich", "questionary"} or parts[:2] == [
        "goldberg_manager",
        "cli",
    ]


class ArchitectureBoundaryTests(unittest.TestCase):
    def test_application_does_not_import_cli_rich_or_questionary(self) -> None:
        violations: list[str] = []

        for path in sorted(APPLICATION_ROOT.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

            for node in ast.walk(tree):
                if not isinstance(node, (ast.Import, ast.ImportFrom)):
                    continue

                for target in _import_targets(node):
                    if _is_forbidden_application_import(target):
                        relative_path = path.relative_to(PROJECT_ROOT)
                        violations.append(f"{relative_path}:{node.lineno}: {target}")

        self.assertEqual(violations, [])


if __name__ == "__main__":
    unittest.main()
