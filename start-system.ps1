[CmdletBinding()]
param([switch]$Check, [switch]$Stop, [switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$system = Join-Path $root 'system'
$backend = Join-Path $system 'backend'
$frontend = Join-Path $system 'frontend'
$python = Join-Path $backend '.venv\Scripts\python.exe'
$runtime = Join-Path $system '.codex-artifacts\launcher'
$statePath = Join-Path $runtime 'processes.json'
$mutex = [Threading.Mutex]::new($false, ('Local\ThesisLauncher_' + [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($root)).Replace('\','_').Replace('/','_')))
$locked = $false
$started = @()

function Save-State($items) {
    ConvertTo-Json -InputObject @($items) -Depth 4 | Set-Content -LiteralPath $statePath -Encoding UTF8
}
function Get-OwnedProcess($entry) {
    if ($null -eq $entry -or $null -eq $entry.pid) { return $null }
    $p = Get-Process -Id $entry.pid -ErrorAction SilentlyContinue
    if (-not $p -or $p.HasExited -or $null -eq $p.StartTime) { return $null }
    if ($p -and $p.StartTime.ToUniversalTime().Ticks -eq ([datetime]$entry.started).ToUniversalTime().Ticks) { return $p }
    return $null
}
function Stop-OwnedTree($entry) {
    $p = Get-OwnedProcess $entry
    if (-not $p) { return }
    # Windows venv python.exe is a redirector; its actual Uvicorn is a child.
    $children = @(Get-CimInstance Win32_Process -Filter "ParentProcessId = $($p.Id)" | Where-Object { $_.CreationDate -ge $p.StartTime })
    foreach ($child in $children) {
        $childEntry = [pscustomobject]@{pid=$child.ProcessId; started=$child.CreationDate.ToUniversalTime().ToString('o')}
        # CIM timestamps can be less precise: read the process timestamp before stopping.
        $childProcess = Get-Process -Id $child.ProcessId -ErrorAction SilentlyContinue
        if ($childProcess -and -not $childProcess.HasExited -and $childProcess.StartTime -and $childProcess.StartTime -ge $p.StartTime) {
            $childEntry.started = $childProcess.StartTime.ToUniversalTime().ToString('o')
            Stop-OwnedTree $childEntry
        }
    }
    $p = Get-OwnedProcess $entry
    if ($p) {
        Stop-Process -Id $p.Id
        if (-not $p.WaitForExit(5000)) { throw "Service process $($p.Id) did not exit within five seconds." }
    }
}
function Test-Http([string]$url, [switch]$Health) {
    try {
        $r = Invoke-WebRequest -UseBasicParsing -Uri $url -TimeoutSec 3
        if ($r.StatusCode -ne 200) { return $false }
        if ($Health) {
            $j = $r.Content | ConvertFrom-Json
            return ($j.status -eq 'ok' -and $j.database -eq 'ok' -and $j.pgvector -eq 'ok')
        }
        return $r.Content.Contains('/src/main.ts')
    } catch { return $false }
}
function Start-ServiceProcess([string]$name, [string]$exe, [string]$arguments, [string]$directory) {
    $p = Start-Process -FilePath $exe -ArgumentList $arguments -WorkingDirectory $directory -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $runtime "$name.out.log") -RedirectStandardError (Join-Path $runtime "$name.err.log")
    return [pscustomobject]@{ name=$name; pid=$p.Id; started=$p.StartTime.ToUniversalTime().ToString('o') }
}

try {
    try { $locked = $mutex.WaitOne(0) } catch [Threading.AbandonedMutexException] { $locked = $true }
    if (-not $locked) { throw 'Another launcher is running. Wait for it to finish.' }
    $saved = @()
    if (Test-Path -LiteralPath $statePath) {
        $decoded = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
        $saved = @($decoded | Where-Object { $null -ne $_ -and $null -ne $_.pid })
    }
    if ($Stop) {
        foreach ($entry in $saved) {
            $p = Get-OwnedProcess $entry
            if ($p) { Stop-OwnedTree $entry; Write-Host "Stopped launcher-owned $($entry.name)." }
        }
        if (Test-Path -LiteralPath $statePath) { Save-State @() }
        Write-Host 'Database and stored data are preserved.'
        exit 0
    }
    foreach ($path in @($python, (Join-Path $system '.env'), (Join-Path $frontend 'node_modules\vite\bin\vite.js'))) {
        if (-not (Test-Path -LiteralPath $path)) { throw "Missing prerequisite: $path . See system/README.md for first-time setup." }
    }
    $node = (Get-Command node.exe -ErrorAction Stop).Source
    $null = Get-Command docker.exe -ErrorAction Stop
    & docker info --format '{{.OSType}}' 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Start Docker Desktop (Linux engine), then run this launcher again.' }
    Push-Location $system
    try {
        & docker compose config --quiet
        if ($LASTEXITCODE -ne 0) { throw 'Docker Compose configuration check failed.' }
        if (-not $Check) {
            # Compose writes progress to stderr even on success (Windows PowerShell 5.1).
            $ErrorActionPreference = 'Continue'
            & docker compose up -d --wait --wait-timeout 90 db 2>&1 | ForEach-Object { Write-Output "$_" }
            $ErrorActionPreference = 'Stop'
            if ($LASTEXITCODE -ne 0) { throw 'Database startup failed.' }
        }
    } finally { Pop-Location }
    Push-Location $backend
    try {
        # Read-only schema comparison: never migrate, seed, reset or print secrets.
        $probe = @'
import sys
try:
    import uvicorn
    from app.main import app
    from app.core.database import get_engine
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    from alembic.runtime.migration import MigrationContext
    from sqlalchemy import text
    with get_engine().connect() as c:
        assert set(MigrationContext.configure(c).get_current_heads()) == set(ScriptDirectory.from_config(Config('alembic.ini')).get_heads()), 'SCHEMA_NOT_CURRENT'
        assert c.execute(text("SELECT 1 FROM pg_extension WHERE extname='vector'")).scalar() == 1, 'PGVECTOR_MISSING'
    print('PREFLIGHT_OK: config, application import, database, migration head, pgvector')
except Exception as e:
    print('PREFLIGHT_FAILED: ' + type(e).__name__ + '; see system/README.md (configuration values are hidden)')
    sys.exit(1)
'@
        $probe | & $python -
        if ($LASTEXITCODE -ne 0) { throw 'Backend preflight failed; no migration or seed was performed.' }
    } finally { Pop-Location }
    & $node --version
    if ($LASTEXITCODE -ne 0) { throw 'Node check failed.' }
    if ($Check) { Write-Host 'CHECK_OK: no service was started or stopped. Embedding and external LLM are not exercised.'; exit 0 }
    New-Item -ItemType Directory -Path $runtime -Force | Out-Null
    $alive = @($saved | Where-Object { $null -ne (Get-OwnedProcess $_) })
    foreach ($svc in @(
        @{name='backend'; port=8000; exe=$python; args='-m uvicorn app.main:app --host 127.0.0.1 --port 8000'; dir=$backend; url='http://127.0.0.1:8000/api/health'},
        @{name='frontend'; port=5173; exe=$node; args='"' + (Join-Path $frontend 'node_modules\vite\bin\vite.js') + '" --host 127.0.0.1 --port 5173 --strictPort'; dir=$frontend; url='http://127.0.0.1:5173/login'}
    )) {
        $listeners = @(Get-NetTCPConnection -State Listen -LocalPort $svc.port -ErrorAction SilentlyContinue)
        if ($listeners.Count -gt 0) {
            $listenerProcesses = @($listeners | ForEach-Object { Get-CimInstance Win32_Process -Filter "ProcessId = $($_.OwningProcess)" })
            $ours = @($alive | Where-Object {
                $_.name -eq $svc.name -and (
                    $_.pid -in $listeners.OwningProcess -or
                    $_.pid -in $listenerProcesses.ParentProcessId
                )
            })
            if ($ours.Count -eq 0) { throw "Port $($svc.port) is occupied by a process not started by this launcher. It was left untouched." }
        } else {
            $entry = Start-ServiceProcess $svc.name $svc.exe $svc.args $svc.dir
            $started += $entry
            $alive += $entry
            Save-State $alive
        }
        $ready = $false
        for ($i=0; $i -lt 45; $i++) {
            if (Test-Http $svc.url -Health:($svc.name -eq 'backend')) { $ready=$true; break }
            Start-Sleep -Seconds 1
        }
        if (-not $ready) { throw "$($svc.name) did not become ready. Check $runtime\$($svc.name).err.log" }
        Write-Host "READY: $($svc.name) $($svc.url)"
    }
    Write-Host 'START_OK. Stop only launcher-owned web services: .\start-system.ps1 -Stop'
    if (-not $NoBrowser) { Start-Process 'http://127.0.0.1:5173/login' }
} catch {
    foreach ($entry in $started) { Stop-OwnedTree $entry }
    Write-Verbose $_.ScriptStackTrace
    Write-Error $_ -ErrorAction Continue
    exit 1
} finally {
    if ($locked) { $mutex.ReleaseMutex() }
    $mutex.Dispose()
}
