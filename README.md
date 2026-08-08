# Goldberg Manager

A Linux-focused manager for automating Goldberg / GBE Fork configuration
for Windows games running through Wine and Proton.

## Status

🚧 Early development — version 0.1.0

The project is currently in its initial development stage.

## Planned features

- Automatic detection of Goldberg / GBE Fork
- Steam interface generation
- Steam settings generation
- Game detection
- Automatic backups and restoration
- Wine and Proton detection
- Steam, Heroic and Lutris integration
- Bannerlator support
- Winlator-related utilities
- Interactive terminal interface

## Requirements

- Python 3.10+
- Linux
- Wine and/or Proton for Windows games

## Development

Create a virtual environment:

```bash
python3 -m venv .venv

Activate it on Fish:

source .venv/bin/activate.fish

Install development dependencies:

python -m pip install rich questionary

Run the application:

python src/main.py
License

See LICENSE.
