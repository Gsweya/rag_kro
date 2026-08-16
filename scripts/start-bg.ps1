# start the rag_kro local-mode services as background (hidden) processes
# with logs under <repo>/logs. Same env rewriting as run.ps1 Load-LocalEnv.
$ErrorActionPreference = 'Stop'

$ROOT = $PSScriptRoot | Split-Path -Parent
$CONDA_ENV = if ($env:RAGKRO_CONDA_ENV) { $env:RAGKRO_CONDA_ENV } else { 'ragkro' }
$CONDA_EXE = $env:CONDA_EXE
if (-not $CONDA_EXE) {
    $candidates = @(
        "$env:USERPROFILE\anaconda3\Scripts\conda.exe",
        "$env:USERPROFILE\miniconda3\Scripts\conda.exe",
        "$env:USERPROFILE\miniforge3\Scripts\conda.exe",
        "$env:LOCALAPPDATA\Continuum\anaconda3\Scripts\conda.exe",
        "$env:ProgramData\Anaconda3\Scripts\conda.exe",
        "$env:ProgramData\miniconda3\Scripts\conda.exe"
    )
    $CONDA_EXE = $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
}
if (-not $CONDA_EXE) { throw "conda not found" }

$map = @{}
foreach ($raw in Get-Content -LiteralPath (Join-Path $ROOT '.env')) {
    $line = $raw.Trim()
    if ($line -eq '' -or $line.StartsWith('#')) { continue }
    $line = ($line -replace '\s+#.*$', '').Trim()
    if ($line -match '^([^=]+)=(.*)$') {
        $k = $matches[1].Trim(); $v = $matches[2].Trim()
        if ($v.Length -ge 2 -and $v[0] -eq '"' -and $v[$v.Length - 1] -eq '"') { $v = $v.Substring(1, $v.Length - 2) }
        if ($k) { $map[$k] = $v }
    }
}
foreach ($k in @($map.Keys)) {
    $map[$k] = [regex]::Replace($map[$k], '\$\{([^}]+)\}', {
        param($m)
        if ($map.ContainsKey($m.Groups[1].Value)) { return $map[$m.Groups[1].Value] }
        return $m.Value
    })
}
$map['POSTGRES_HOST'] = 'localhost'; $map['POSTGRES_PORT'] = '5433'
$map['DATABASE_URL'] = "postgresql+psycopg://$($map['POSTGRES_USER'])`:$($map['POSTGRES_PASSWORD'])@localhost:5433/$($map['POSTGRES_DB'])"
$map['REDIS_HOST'] = 'localhost'; $map['REDIS_PORT'] = '6379'
$map['REDIS_URL'] = 'redis://localhost:6379/0'
$map['CELERY_BROKER_URL'] = 'redis://localhost:6379/1'
$map['CELERY_RESULT_BACKEND'] = 'redis://localhost:6379/2'
$map['QDRANT_HOST'] = 'localhost'; $map['QDRANT_PORT'] = '6333'
$map['QDRANT_URL'] = 'http://localhost:6333'
$map['MINIO_HOST'] = 'localhost'; $map['MINIO_PORT'] = '9000'
$map['MINIO_ENDPOINT'] = 'http://localhost:9000'
$map['INGESTION_API_URL'] = 'http://localhost:8001'
$map['RAG_API_URL'] = 'http://localhost:8002'
$map['WA_API_CALLBACK_URL'] = 'http://localhost:8000/webhook/message'
$map['IG_API_CALLBACK_URL'] = 'http://localhost:8000/webhook/message'
$map['API_INTERNAL_URL'] = 'http://localhost:8000'
$map['WA_GATEWAY_INTERNAL_URL'] = 'http://localhost:8100'
$map['RAG_INTERNAL_URL'] = 'http://localhost:8002'
$map['INGESTION_INTERNAL_URL'] = 'http://localhost:8001'
foreach ($k in $map.Keys) { Set-Item -Path "Env:$k" -Value $map[$k] }

$logs = Join-Path $ROOT 'logs'
New-Item -ItemType Directory -Force -Path $logs | Out-Null

function Start-Bg {
    param([string]$Name, [string]$Dir, [string]$Cmd)
    $running = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -match $Match }
    if ($running) { Write-Host "skip $Name (already running)"; return }
    $out = Join-Path $logs "$Name.out.log"
    $err = Join-Path $logs "$Name.err.log"
    if (Test-Path -LiteralPath $out) { Remove-Item -LiteralPath $out -Force }
    if (Test-Path -LiteralPath $err) { Remove-Item -LiteralPath $err -Force }
    Start-Process -FilePath powershell.exe -ArgumentList @('-NoProfile', '-NoLogo', '-Command', "Set-Location -LiteralPath '$Dir'; $Cmd") -WindowStyle Hidden -RedirectStandardOutput $out -RedirectStandardError $err | Out-Null
    Write-Host "started $Name -> logs/$Name.{out,err}.log"
}

$c = "& `"$CONDA_EXE`" run --no-capture-output -n `"$CONDA_ENV`""
$Match = 'port 8000';                 Start-Bg 'api'        (Join-Path $ROOT 'services/api')        "$c uvicorn app.main:app --host 0.0.0.0 --port 8000"
$Match = 'port 8002';                 Start-Bg 'rag'        (Join-Path $ROOT 'services/rag')        "$c uvicorn app.main:app --host 0.0.0.0 --port 8002"
$Match = 'port 8001';                 Start-Bg 'ingestion'  (Join-Path $ROOT 'services/ingestion')  "$c uvicorn app.main:app --host 0.0.0.0 --port 8001"
$Match = 'worker -l info';            Start-Bg 'worker'     (Join-Path $ROOT 'services/worker')     "$c celery -A app.celery_app.app worker -l info -Q default -P threads"
$Match = 'celery -A app.celery_app.app beat'; Start-Bg 'beat' (Join-Path $ROOT 'services/worker')  "$c celery -A app.celery_app.app beat -l info"
$Match = 'next dev';                  Start-Bg 'web'        (Join-Path $ROOT 'services/web')        'npm run dev'
$Match = 'wa-gateway';                Start-Bg 'wa-gateway' (Join-Path $ROOT 'services/wa-gateway') 'npm run dev'
Write-Host "all services launching (background). tail logs under $logs"
