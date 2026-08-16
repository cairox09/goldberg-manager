# Changelog

All notable changes to Goldberg Manager will be documented in this file.

## [0.2.0] - 2026-08-16

### Added

- Advanced game discovery capable of finding games even when no Steam API library is present.
- Detection of games with deeply nested `steam_api.dll` and `steam_api64.dll` layouts.
- Filtering of installers, redistributables, helper tools and standalone launchers during game discovery.
- Steam AppID resolution from existing game configuration and local Steam manifests.
- Steam Store search for unresolved AppIDs.
- Persistent cache for Steam AppID search results.
- Interactive Goldberg/GBE game assistant.
- Guided game configuration workflow.
- Automatic `steam_appid.txt` generation and management.
- Automatic `steam_interfaces` generation using the appropriate 32-bit or 64-bit GBE tool.
- Complete `steam_settings` generation and management.
- Interactive editing of account name, SteamID, language, country and save paths.
- Full `steam_settings` snapshots with SHA-256 integrity verification.
- Safe restoration of previous `steam_settings` snapshots.
- Detection of the GSE `generate_emu_config` tool.
- Interactive execution of `generate_emu_config` directly from the game assistant.
- Authenticated and anonymous GSE generation modes.
- Parsing of generated Steam metadata including:
  - achievements
  - achievement images
  - supported languages
  - DLCs
  - depots
  - branches
  - product information
  - app details
- Safe achievement import from GSE-generated metadata.
- Automatic safety snapshot before achievement imports and reimports.
- Removal of stale achievement images during reimport.
- Detection and display of installed achievement counts.
- Searchable Steam language selector.
- Searchable ISO 3166-1 country selector.
- Validation of Steam language codes.
- Validation of real ISO country codes.
- Automatic prioritization of languages supported by the selected game.
- `pycountry` dependency for ISO country metadata.
- Automated release workflow for tagged versions.

### Changed

- Game detection now supports significantly more real-world directory layouts.
- The game discovery screen distinguishes configurable games from games without a detected Steam API.
- Steam settings editing now uses structured selectors instead of unrestricted text entry for language and country.
- The game assistant now displays GSE and achievement status.
- Achievement reimport replaces the previous image set instead of merging stale files.
- Game configuration operations consistently create verified safety backups before destructive changes.
- Release validation now checks package and application versions against the Git tag.

### Fixed

- Games with Steam API libraries located deep inside engine or Steamworks subdirectories can now be associated with their correct game root.
- Loose Steam API files no longer incorrectly promote an entire library directory into a game.
- Technical directories and redistributables are no longer reported as discovered games.
- Translation installers and standalone launcher directories are filtered from game discovery.
- GSE metadata paths containing Windows-style backslashes are handled correctly on Linux.
- Invalid or unknown country codes are rejected.
- Invalid Steam language codes are rejected.
- Old achievement images are removed safely during metadata reimport.

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
