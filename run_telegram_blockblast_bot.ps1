if (-not $env:TELEGRAM_BOT_TOKEN) {
    Write-Error "Set TELEGRAM_BOT_TOKEN before running this script."
    exit 1
}

Set-Location 'C:\BlockBlastBOT'
.\.venv\Scripts\python.exe telegram_blockblast_bot.py
