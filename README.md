# Block Blast Helper

Telegram helper bot for Block Blast screenshots. Send a full vertical screenshot of the game, and the bot replies with an annotated image showing where to place the pieces.

## Features

- Detects the 8x8 board from a full screenshot.
- Detects the three tray pieces.
- Searches all piece orders and placements.
- Draws step numbers, placement overlays, and cleared rows/columns.
- Refuses unclear screenshots instead of inventing moves.

## Install

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
```

## Run Locally

```powershell
.\.venv\Scripts\python.exe blockblast_solver.py "C:\path\to\screenshot.png" -o solution.png
```

## Run Telegram Bot

Create a bot with BotFather, then run:

```powershell
$env:TELEGRAM_BOT_TOKEN="YOUR_BOT_TOKEN"
.\run_telegram_blockblast_bot.ps1
```

Send the bot a full screenshot where the board and all three pieces are visible.

## Files

- `blockblast_solver.py` - screenshot recognition, solver, and image annotation.
- `telegram_blockblast_bot.py` - minimal Telegram long-polling bot.
- `run_telegram_blockblast_bot.ps1` - Windows launcher.
