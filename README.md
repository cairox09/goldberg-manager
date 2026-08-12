# Goldberg Manager

[![CI](https://github.com/cairox09/goldberg-manager/actions/workflows/ci.yml/badge.svg)](https://github.com/cairox09/goldberg-manager/actions/workflows/ci.yml)

**Goldberg Manager** is a Linux command-line application for detecting games that use the Steamworks API and safely managing their original Steam API libraries.

The project is being developed with Linux, Wine and Proton workflows in mind, with planned integration for Goldberg/GBE Fork configuration.

> [!IMPORTANT]
> Goldberg Manager does not provide games or remove DRM.
> Use it only with software you own or are otherwise authorized to modify.

## Current features

- Detect games inside configurable directories.
- Detect `steam_api.dll` and `steam_api64.dll`.
- Detect 32-bit and 64-bit games.
- Identify the game root, executable and Steam API location.
- Display detailed information about detected games.
- Detect Goldberg/GBE Fork tools such as `generate_interfaces`.
- Create safe backups of original Steam API libraries.
- Store backup metadata and SHA-256 hashes.
- Verify backup integrity before restoration.
- Detect whether the current Steam API differs from the original backup.
- Restore original Steam API libraries.
- Open game directories from the CLI.
- Persistent configuration.
- Automated tests and GitHub Actions CI.

## In development

The following features are visible in the interface but are not implemented yet:

- Automatic Goldberg/GBE Fork installation.
- `steam_interfaces` generation.
- `steam_settings` generation.

## Requirements

- Linux
- Python 3.11 or newer

The project is tested automatically on:

- Python 3.11
- Python 3.12
- Python 3.13
- Python 3.14

## Installation

### From a release wheel

Create a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate
```

Install the downloaded wheel:

```bash
python -m pip install ./goldberg_manager-0.1.0-py3-none-any.whl
```

Run:

```bash
goldberg-manager
```

You can also run it as a Python module:

```bash
python -m goldberg_manager
```

## Development installation

Clone the repository:

```bash
git clone https://github.com/cairox09/goldberg-manager.git
cd goldberg-manager
```

Create and activate a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate
```

Install the project with development dependencies:

```bash
python -m pip install -e ".[dev]"
```

Run the application:

```bash
goldberg-manager
```

## Running tests

```bash
python -m unittest discover -s tests -v
```

Run Ruff:

```bash
ruff format --check src/ tests/
ruff check src/ tests/
```

## Building distributions

```bash
python -m build
```

The generated packages will be placed in:

```text
dist/
```

Validate them with:

```bash
python -m twine check dist/*
```

## Project status

Goldberg Manager is currently in **alpha development**.

Version `0.1.0` focuses on game detection, configuration, verified backups and safe restoration.

Automatic emulator installation and configuration are planned for future releases.

## License

Goldberg Manager is distributed under the MIT License.

See [LICENSE](LICENSE) for details.

## Disclaimer

Goldberg Manager is an independent project and is not affiliated with Valve, Steam, Goldberg Emulator or GBE Fork.

Users are responsible for ensuring that their use of the software complies with applicable licenses and laws.
