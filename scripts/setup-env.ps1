if (Test-Path -LiteralPath ".env") {
    Write-Host ".env already exists. Nothing to copy."
    exit 0
}

if (!(Test-Path -LiteralPath ".env.example")) {
    Write-Error ".env.example was not found."
    exit 1
}

Copy-Item -LiteralPath ".env.example" -Destination ".env"
Write-Host ".env created from .env.example."
