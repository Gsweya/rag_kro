#!/usr/bin/env pwsh
# =====================================================================
# rag_kro - local-mode launcher for Windows (port of run.sh --local)
#
#   .\run.ps1                 local up: start infra (docker) + one console
#                             window per service (conda / npm, host-native)
#   .\run.ps1 setup           create the conda env + install deps (once)
#   .\run.ps1 ps              show infra containers + host processes
#   .\run.ps1 down            stop the infra containers only
#   .\run.ps1 restart         down + up
#   .\run.ps1 -Local <action> (optional, accepted for run.sh parity)
#
# Core infra (postgres, redis, qdrant, minio) runs in Docker; the rag_kro
# services run natively on the host:
#   api / rag / ingestion / worker  -> conda env 'ragkro' (uvicorn / celery)
#   web / wa-gateway                -> npm
# Internal docker hostnames are rewritten to localhost host ports.
#
# For the full-Docker mode use docker compose directly, e.g.:
#   docker compose --profile dev --profile wa up -d --build
# =====================================================================
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [string]$Action = "up",
    [switch]$Local
)

$ErrorActionPreference = 'Stop'

$ROOT = $PSScriptRoot
$COMPOSE = "docker compose"
$CONDA_ENV = if ($env:RAGKRO_CONDA_ENV) { $env:RAGKRO_CONDA_ENV } else { 'ragkro' }

# infra ports published to the host (see docker-compose.yml)
$LOCAL_POSTGRES_PORT = 5433
$LOCAL_REDIS_PORT = 6379
$LOCAL_QDRANT_PORT = 6333
$LOCAL_MINIO_PORT = 9000

# ---------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------

function Find-Conda {
    $cmd = Get-Command conda -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $candidates = @(
        "$env:USERPROFILE\anaconda3\Scripts\conda.exe",
        "$env:USERPROFILE\miniconda3\Scripts\conda.exe",
        "$env:USERPROFILE\miniforge3\Scripts\conda.exe",
        "$env:LOCALAPPDATA\Continuum\anaconda3\Scripts\conda.exe",
        "$env:ProgramData\Anaconda3\Scripts\conda.exe",
        "$env:ProgramData\miniconda3\Scripts\conda.exe"
    )
    foreach ($c in $candidates) {
        if (Test-Path -LiteralPath $c) { return $c }
    }
    return $null
}

function Read-EnvFile {
    # bash-`source`-like parse of KEY=VALUE with inline comments and ${VAR} refs
    param([string]$Path)
    $map = @{}
    if (-not (Test-Path -LiteralPath $Path)) { return $map }
    foreach ($raw in Get-Content -LiteralPath $Path) {
        $line = $raw.Trim()
        if ($line -eq '' -or $line.StartsWith('#')) { continue }
        $line = $line -replace '\s+#.*$', ''
        $line = $line.Trim()
        if ($line -match '^([^=]+)=(.*)$') {
            $key = $matches[1].Trim()
            $val = $matches[2].Trim()
            if ($val.Length -ge 2 -and $val[0] -eq '"' -and $val[$val.Length - 1] -eq '"') {
                $val = $val.Substring(1, $val.Length - 2)
            }
            if ($key) { $map[$key] = $val }
        }
    }
    foreach ($k in @($map.Keys)) {
        $map[$k] = [regex]::Replace($map[$k], '\$\{([^}]+)\}', {
            param($m)
            if ($map.ContainsKey($m.Groups[1].Value)) { return $map[$m.Groups[1].Value] }
            return $m.Value
        })
    }
    return $map
}

function Set-EnvMap {
    param([hashtable]$Map)
    foreach ($k in $Map.Keys) { Set-Item -Path "Env:$k" -Value $Map[$k] }
}

function Assert-Docker {
    docker info *> $null
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Docker is not reachable. Start Docker Desktop first."
    }
}

function Test-CondaEnv {
    param([string]$CondaExe)
    if (-not $CondaExe) { return $false }
    $out = & $CondaExe env list 2>$null
    return [bool]($out -match "(?im)^\s*$([regex]::Escape($CONDA_ENV))\s")
}

function Invoke-CondaPip {
    param([string]$CondaExe, [string[]]$Args_)
    & $CondaExe run --no-capture-output -n $CONDA_ENV pip install --retries 10 --default-timeout=120 @Args_
    if ($LASTEXITCODE -ne 0) { throw "pip install failed inside conda env '$CONDA_ENV'" }
}

# open a new PowerShell window that inherits the current (env-loaded) session
function Start-ServiceWindow {
    param([string]$Title, [string]$Dir, [string]$Cmd)
    $script = @"
`$Host.UI.RawUI.WindowTitle = '$Title'
Set-Location -LiteralPath '$Dir'
Write-Host ''
Write-Host '=== $Title ===' -ForegroundColor Cyan
$Cmd
"@
    $encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($script))
    Start-Process powershell.exe -ArgumentList @(
        '-NoExit', '-NoLogo', '-ExecutionPolicy', 'Bypass',
        '-EncodedCommand', $encoded
    ) | Out-Null
    Write-Host "    opened '$Title'"
}

# ---------------------------------------------------------------------
# local (no-docker-for-services) mode
# ---------------------------------------------------------------------

function Load-LocalEnv {
    # load .env into the current session, then rewrite internal URLs to
    # localhost host ports (mirrors run.sh LOCAL_ENV_EXPORTS)
    $map = Read-EnvFile (Join-Path $ROOT '.env')
    Set-EnvMap $map

    $pgUser = if ($map.ContainsKey('POSTGRES_USER')) { $map['POSTGRES_USER'] } else { 'rag_kro' }
    $pgPass = if ($map.ContainsKey('POSTGRES_PASSWORD')) { $map['POSTGRES_PASSWORD'] } else { '' }
    $pgDb   = if ($map.ContainsKey('POSTGRES_DB')) { $map['POSTGRES_DB'] } else { 'rag_kro' }

    $local = @{
        POSTGRES_HOST          = 'localhost'
        POSTGRES_PORT          = "$LOCAL_POSTGRES_PORT"
        DATABASE_URL           = "postgresql+psycopg://$pgUser`:$pgPass@localhost:$LOCAL_POSTGRES_PORT/$pgDb"
        REDIS_HOST             = 'localhost'
        REDIS_PORT             = "$LOCAL_REDIS_PORT"
        REDIS_URL              = "redis://localhost:$LOCAL_REDIS_PORT/0"
        CELERY_BROKER_URL      = "redis://localhost:$LOCAL_REDIS_PORT/1"
        CELERY_RESULT_BACKEND  = "redis://localhost:$LOCAL_REDIS_PORT/2"
        QDRANT_HOST            = 'localhost'
        QDRANT_PORT            = "$LOCAL_QDRANT_PORT"
        QDRANT_URL             = "http://localhost:$LOCAL_QDRANT_PORT"
        MINIO_HOST             = 'localhost'
        MINIO_PORT             = "$LOCAL_MINIO_PORT"
        MINIO_ENDPOINT         = "http://localhost:$LOCAL_MINIO_PORT"
        INGESTION_API_URL      = 'http://localhost:8001'
        RAG_API_URL            = 'http://localhost:8002'
        WA_API_CALLBACK_URL    = 'http://localhost:8000/webhook/message'
        IG_API_CALLBACK_URL    = 'http://localhost:8000/webhook/message'
        API_INTERNAL_URL       = 'http://localhost:8000'
        WA_GATEWAY_INTERNAL_URL= 'http://localhost:8100'
        RAG_INTERNAL_URL       = 'http://localhost:8002'
        INGESTION_INTERNAL_URL = 'http://localhost:8001'
    }
    Set-EnvMap $local
}

function Invoke-LocalSetup {
    param([string]$CondaExe)
    Write-Host "==> local mode: setting up conda env '$CONDA_ENV' + node deps ..."
    if (-not (Test-CondaEnv $CondaExe)) {
        Write-Host "==> creating conda env '$CONDA_ENV' (python 3.12) ..."
        & $CondaExe create -y -n $CONDA_ENV python=3.12
        if ($LASTEXITCODE -ne 0) { throw "conda create failed for env '$CONDA_ENV'" }
    }
    Write-Host '==> installing shared package + python deps ...'
    Invoke-CondaPip $CondaExe @('-e', 'packages/python/rag_kro_shared')
    Invoke-CondaPip $CondaExe @(
        '-r', 'services/api/requirements.txt',
        '-r', 'services/rag/requirements.txt',
        '-r', 'services/ingestion/requirements.txt',
        '-r', 'services/worker/requirements.txt'
    )
    Write-Host '==> installing ML stack (torch + sentence-transformers) from python-base ...'
    Invoke-CondaPip $CondaExe @('-r', 'infra/docker/python-base/requirements.txt')
    Write-Host '==> pre-downloaded torch wheels are Linux-only (manylinux);'
    Write-Host '    Windows pip will resolve torch from PyPI instead.'
    $wheels = Get-ChildItem (Join-Path $ROOT 'infra/docker/python-base/wheels/*.whl') -ErrorAction SilentlyContinue
    if ($wheels) {
        Write-Host '==> attempting wheel install ...'
        try {
            Invoke-CondaPip $CondaExe @($wheels.FullName)
        } catch {
            Write-Host "  wheel install skipped: $($_.Exception.Message)"
        }
    }
    Write-Host '==> installing web (next) + wa-gateway (node) deps ...'
    Push-Location (Join-Path $ROOT 'services/web')
    try {
        if (-not (Test-Path -LiteralPath 'node_modules')) {
            npm install --no-audit --no-fund
            if ($LASTEXITCODE -ne 0) { throw 'npm install failed in services/web' }
        }
    } finally { Pop-Location }
    Push-Location (Join-Path $ROOT 'services/wa-gateway')
    try {
        if (-not (Test-Path -LiteralPath 'node_modules')) {
            npm install --no-audit --no-fund
            if ($LASTEXITCODE -ne 0) { throw 'npm install failed in services/wa-gateway' }
        }
    } finally { Pop-Location }
}

function Start-LocalServices {
    param([string]$CondaExe)
    if (-not (Test-CondaEnv $CondaExe)) {
        Write-Host "==> conda env '$CONDA_ENV' not found - running setup first ..."
        Invoke-LocalSetup $CondaExe
    }

    $c = "& `"$CondaExe`" run --no-capture-output -n `"$CONDA_ENV`""
    $services = @(
        @{ Title = 'ragkro:api';        Dir = 'services/api';        Cmd = "$c uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload" }
        @{ Title = 'ragkro:rag';        Dir = 'services/rag';        Cmd = "$c uvicorn app.main:app --host 0.0.0.0 --port 8002 --reload" }
        @{ Title = 'ragkro:ingestion';  Dir = 'services/ingestion';  Cmd = "$c uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload" }
        @{ Title = 'ragkro:worker';     Dir = 'services/worker';     Cmd = "$c celery -A app.celery_app.app worker -l info -Q default -P threads" }
        @{ Title = 'ragkro:beat';       Dir = 'services/worker';     Cmd = "$c celery -A app.celery_app.app beat -l info" }
        @{ Title = 'ragkro:web';        Dir = 'services/web';        Cmd = 'npm run dev' }
        @{ Title = 'ragkro:wa-gateway'; Dir = 'services/wa-gateway'; Cmd = 'npm run dev' }
    )

    Write-Host '==> starting core infra (postgres, redis, qdrant, minio) in Docker ...'
    & docker compose up -d postgres redis qdrant minio
    if ($LASTEXITCODE -ne 0) { throw 'docker compose up (infra) failed' }

    Write-Host '==> waiting for postgres to be healthy ...'
    $pgUser = if ($env:POSTGRES_USER) { $env:POSTGRES_USER } else { 'rag_kro' }
    $pgDb   = if ($env:POSTGRES_DB) { $env:POSTGRES_DB } else { 'rag_kro' }
    $ready = $false
    for ($i = 0; $i -lt 60; $i++) {
        docker exec rag_kro_postgres pg_isready -U $pgUser -d $pgDb *> $null
        if ($LASTEXITCODE -eq 0) { $ready = $true; break }
        Start-Sleep -Seconds 2
    }
    if ($ready) { Write-Host '==> postgres is up' } else { Write-Warning 'postgres not ready after 120s - continuing anyway' }

    Write-Host '==> opening a console window per service (running natively) ...'
    foreach ($s in $services) {
        $dir = Join-Path $ROOT $s.Dir
        Start-ServiceWindow -Title $s.Title -Dir $dir -Cmd $s.Cmd
    }

    Write-Host ''
    Write-Host '==> everything is running (local mode):'
    Write-Host '    dashboard : http://localhost:3000'
    Write-Host '    api       : http://localhost:8000  (/docs)'
    Write-Host '    ingestion : http://localhost:8001'
    Write-Host '    rag       : http://localhost:8002'
    Write-Host '    minio     : http://localhost:9001'
    Write-Host "    postgres on host port $LOCAL_POSTGRES_PORT"
    Write-Host ''
}

function Show-LocalStatus {
    Write-Host '==> infra (docker):'
    docker compose ps --format "table {{.Name}}`t{{.Status}}`t{{.Ports}}"
    Write-Host ''
    Write-Host '==> local (host) processes:'
    $procs = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -match 'uvicorn|celery|next dev|wa-gateway|src/index' } |
        Select-Object ProcessId, Name, CommandLine
    if ($procs) { $procs | Format-List | Out-String } else { Write-Host '    (none running)' }
}

# ---------------------------------------------------------------------
# dispatch
# ---------------------------------------------------------------------

$condaExe = Find-Conda
if (-not $condaExe) {
    Write-Error "conda not found on PATH or in common install locations. Install Anaconda/Miniconda first."
}
if ($Local) { Write-Host '(--local implied: this script only runs local mode)' }

switch ($Action) {
    'up' {
        Assert-Docker
        Load-LocalEnv
        Start-LocalServices $condaExe
    }
    'setup' {
        Invoke-LocalSetup $condaExe
        Write-Host "==> done. Next: .\run.ps1"
    }
    'ps' {
        Assert-Docker
        Load-LocalEnv
        Show-LocalStatus
    }
    'down' {
        Assert-Docker
        Write-Host '==> stopping infra (postgres, redis, qdrant, minio) ...'
        docker compose down
    }
    'restart' {
        Assert-Docker
        Load-LocalEnv
        Write-Host '==> stopping infra ...'
        docker compose down
        Start-LocalServices $condaExe
    }
    default {
        Write-Host "usage: $PSCommandPath [setup|up|ps|down|restart]" -ForegroundColor Yellow
        Write-Host "  (full-Docker mode: docker compose --profile dev --profile wa up -d --build)" -ForegroundColor Yellow
        exit 1
    }
}
