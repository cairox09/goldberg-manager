from __future__ import annotations

from pathlib import Path


def detect_generate_interfaces(root: Path) -> tuple[Path | None, Path | None]:
    candidates_x64 = [
        root / "tools" / "generate_interfaces" / "generate_interfacesx64.exe",
        root / "tools" / "generate_interfaces" / "generate_interfaces64.exe",
        root / "tools" / "generate_interfaces" / "generate_interfaces_x64.exe",
    ]

    candidates_x86 = [
        root / "tools" / "generate_interfaces" / "generate_interfacesx86.exe",
        root / "tools" / "generate_interfaces" / "generate_interfaces32.exe",
        root / "tools" / "generate_interfaces" / "generate_interfaces_x86.exe",
    ]

    x64 = next((path for path in candidates_x64 if path.exists()), None)
    x86 = next((path for path in candidates_x86 if path.exists()), None)

    if x64 is None:
        for path in root.rglob("generate_interfacesx64.exe"):
            x64 = path
            break
        if x64 is None:
            for path in root.rglob("generate_interfaces_x64.exe"):
                x64 = path
                break

    if x86 is None:
        for path in root.rglob("generate_interfacesx86.exe"):
            x86 = path
            break
        if x86 is None:
            for path in root.rglob("generate_interfaces_x86.exe"):
                x86 = path
                break

    return x64, x86
