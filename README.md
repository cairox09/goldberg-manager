# Goldberg Manager

[![CI](https://github.com/cairox09/goldberg-manager/actions/workflows/ci.yml/badge.svg)](https://github.com/cairox09/goldberg-manager/actions/workflows/ci.yml)

**Goldberg Manager** is a Linux command-line application for discovering games and safely managing Goldberg/GBE Fork configuration, Steamworks metadata, backups and achievements.

The project is designed for Linux, Wine and Proton workflows and provides guided tools for Steam AppID resolution, `steam_settings`, `steam_interfaces`, GSE metadata generation and achievement management.
> [!IMPORTANT]
> Goldberg Manager does not provide games or remove DRM.
> Use it only with software you own or are otherwise authorized to modify.

## Current features

### Game discovery

- Discover games inside configurable directories.
- Detect games with or without a Steam API library.
- Detect `steam_api.dll` and `steam_api64.dll`.
- Detect 32-bit and 64-bit games.
- Support nested and non-standard Steam API layouts.
- Filter installers, redistributables, helper tools and standalone launchers.
- Identify the game root, executable and Steam API location.
- Display detailed game information.

### Steam AppID

- Resolve AppIDs from existing configuration.
- Detect AppIDs from local Steam manifests.
- Search the Steam Store for unresolved games.
- Cache Steam AppID search results.
- Configure AppIDs interactively.

### Goldberg / GBE configuration

- Detect Goldberg/GBE Fork tools.
- Detect 32-bit and 64-bit `generate_interfaces` executables.
- Generate `steam_interfaces`.
- Generate and manage `steam_settings`.
- Guided per-game configuration assistant.
- Searchable language and country selectors.
- Detect languages supported by generated game metadata.

### Backups and safety

- Create verified backups of original Steam API libraries.
- Store SHA-256 backup metadata.
- Verify backup integrity before restoration.
- Restore original Steam API libraries.
- Create complete `steam_settings` snapshots.
- Verify and restore `steam_settings` snapshots.
- Automatically create safety snapshots before destructive changes.

### GSE metadata and achievements

- Detect GSE `generate_emu_config`.
- Run `generate_emu_config` from the game assistant.
- Support authenticated and anonymous metadata generation.
- Parse achievements, images, languages, DLCs, depots and branches.
- Import generated achievements and achievement images.
- Safely reimport achievements without leaving stale images.
- Detect and display installed achievement counts.

### Development

- Installable Python package with the `goldberg-manager` command.
- Automated tests.
- GitHub Actions CI for Python 3.11 through 3.14.
- Automated tagged releases with wheel, source archive and SHA-256 checksums.

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
python -m pip install ./goldberg_manager-0.2.0-py3-none-any.whl
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

Version `0.2.0` significantly expands the project with Steam AppID resolution, guided configuration, `steam_settings`, `steam_interfaces`, GSE metadata generation, achievement management, verified settings snapshots and searchable configuration selectors.

Future releases will continue improving integrations, usability, packaging and platform support before the stable `1.0.0` release.
## License

Goldberg Manager is distributed under the MIT License.

See [LICENSE](LICENSE) for details.

## Disclaimer

Goldberg Manager is an independent project and is not affiliated with Valve, Steam, Goldberg Emulator or GBE Fork.

Users are responsible for ensuring that their use of the software complies with applicable licenses and laws.
