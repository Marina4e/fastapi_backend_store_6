& "$PSScriptRoot\setup-env.ps1"
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

docker compose up -d --build
docker compose ps
