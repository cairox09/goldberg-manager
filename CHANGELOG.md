# Changelog

All notable changes to Goldberg Manager will be documented in this file.

## [0.3.0] - 2026-08-20

### Added

- Sentinel installation and configuration detection, including JSON/schema validation and GSE watcher coverage.
- Read-only, game-specific GSE save resolution across native Linux and Wine `drive_c` locations, including `local_save_path`, `saves_folder_name`, runtime detection, and explicit effective, possible, and ambiguous locations.
- Achievement runtime progress with unlocked, locked, partial, and completion statistics; metadata-only states, multiple runtime reports, and malformed metadata/runtime diagnostics are represented without inventing progress.
- Immutable, read-only `GameProfile` snapshots combining AppID, architecture, Steam settings, saves, achievements, Sentinel state, Heroic and Steam provenance, and prefix provenance/consensus.
- Read-only Heroic installed-game discovery with runner and `app_name` identity, structural ownership matching, direct and `pfx` Wine layouts, explicit missing/unresolved/ambiguous states, cross-runner protection, duplicate canonicalization, and untrusted metadata hardening.
- Read-only native Steam library discovery with focused Valve KeyValues parsing, appmanifest and `StateFlags` bitmask validation, structural official-install ownership matching, alias/multiple-library protection, and ownership-bound Proton `compatdata` prefix discovery.
- Prefix consensus from GSE runtime-backed and Heroic structural evidence, supporting single-source resolution, agreement, and explicit conflict without an arbitrary winner.
- A read-only **Ver perfil do jogo** CLI view covering identity, settings, GSE saves, achievements, Sentinel, Heroic, Steam, and **Prefix Consensus (GSE / Heroic)** with honest unknown/ambiguous states and escaped external Rich markup.

### Changed

- Sentinel integration now distinguishes runtime recognition from effective GSE save coverage.
- Sentinel repair uses explicit planning and confirmation, verified backups before writes, atomic updates, concurrency/conflict checks, rollback, idempotent writes, and preservation of unknown configuration fields.
- GSE and launcher matching preserve multiple plausible candidates instead of selecting an arbitrary path, game, or prefix.

### Fixed

- Orphan Steam `compatdata` directories no longer imply game ownership or supply prefixes before structural ownership is established.
- Conflicting Heroic identities, cross-runner configuration collisions, Steam library aliases, and conflicting physical-library metadata are handled conservatively.
- Malformed Sentinel, GSE, achievement, Heroic, and Steam metadata is reported without crashing profile resolution or exposing untrusted Rich markup.

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
