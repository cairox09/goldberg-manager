s# Changelog

All notable changes to Goldberg Manager will be documented in this file.

## [0.1.0] - 2026-08-12

### Added

- Interactive terminal interface built with Rich and Questionary.
- Persistent configuration stored in the user's config directory.
- Configuration of game search directories.
- Detection of Goldberg/GBE Fork installation directory.
- Detection of 32-bit and 64-bit `generate_interfaces` executables.
- Automatic game detection through `steam_api.dll` and `steam_api64.dll`.
- Detection of game architecture and installation paths.
- Detailed game information screen.
- Safe backup of original Steam API libraries.
- SHA-256 verification for backup integrity.
- Backup metadata storage.
- Detection of modified Steam API files.
- Safe restoration of original Steam API libraries.
- Ability to open detected game directories.
- Installable Python package with the `goldberg-manager` command.
- Automated tests for backup and restore behavior.
- GitHub Actions CI for Python 3.11, 3.12, 3.13 and 3.14.
- Wheel and source distribution builds.

### In development

- Automatic Goldberg/GBE Fork installation.
- Automatic `steam_interfaces` generation.
- Automatic `steam_settings` generation.
