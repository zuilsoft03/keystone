# Start Docker Desktop safely on this Windows machine (D-290).
#
# Why: when Docker Desktop does not exit cleanly (a Windows Update restart, a power cut, a crash, a force-stop), it
# leaves its Unix socket files behind (%LOCALAPPDATA%\Docker\run\*, %LOCALAPPDATA%\docker-secrets-engine\engine.sock).
# On the next start Docker Desktop 4.88 tries to remove them, Windows answers "The file cannot be accessed by the
# system" (error 1920), and the backend crashes before the engine starts. Windows itself (del, .NET, fsutil) cannot
# remove those files either; Linux can, through WSL. Measured on 2026-10-16.
#
# What: if the engine already answers, nothing happens. Otherwise this stops a Docker Desktop that is stuck on its
# error dialog, removes the stale socket files (WSL first, renaming the folder aside as a last resort), starts Docker
# Desktop and waits for the engine. It never resets Docker and never touches images, containers or volumes.
#
# Usage:  powershell -NoProfile -ExecutionPolicy Bypass -File dev\docker-preflight.ps1 [-NoStart]
param([switch]$NoStart, [int]$WaitSeconds = 240)

$ErrorActionPreference = 'Continue'
$local = $env:LOCALAPPDATA
$exe = Join-Path $local 'Programs\DockerDesktop\Docker Desktop.exe'
$socketDirs = @((Join-Path $local 'Docker\run'), (Join-Path $local 'docker-secrets-engine'))
$names = @('Docker Desktop', 'com.docker.backend', 'com.docker.build')

function Test-Engine {
	docker info --format '{{.ServerVersion}}' 2>$null | Out-Null
	return $LASTEXITCODE -eq 0
}

function Wait-Engine([int]$seconds) {
	$until = (Get-Date).AddSeconds($seconds)
	while ((Get-Date) -lt $until) {
		if (Test-Engine) { return $true }
		Start-Sleep -Seconds 5
	}
	return $false
}

function Get-StaleSockets {
	Get-ChildItem -Path $socketDirs -Force -File -ErrorAction SilentlyContinue |
		Where-Object { $_.Attributes -match 'ReparsePoint' -and $_.Length -eq 0 }
}

function ConvertTo-WslPath([string]$path) {
	# docker-desktop mounts the Windows drives at /mnt/host/<drive>
	$drive = $path.Substring(0, 1).ToLower()
	return '/mnt/host/' + $drive + ($path.Substring(2) -replace '\\', '/')
}

if (Test-Engine) { 'Docker engine is already running.'; exit 0 }

function Test-SocketCrash([datetime]$since) {
	# Docker Desktop's own record of this failure: "backend cancelling with error ... The file cannot be accessed".
	$log = Join-Path $local 'Docker\log\host\com.docker.backend.exe.log'
	if (-not (Test-Path $log)) { return $false }
	$line = Get-Content $log -Tail 2000 | Select-String 'backend cancelling with error.*cannot be accessed by the system' | Select-Object -Last 1
	if (-not $line) { return $false }
	if ($line.Line -notmatch '^\[(?<at>[0-9T:\-\.]+)Z\]') { return $false }
	return ([datetime]::Parse($Matches.at + 'Z').ToLocalTime() -ge $since)
}

$running = Get-Process -Name $names -ErrorAction SilentlyContinue
if ($running) {
	# A force-stop is itself an unclean exit, so a Docker Desktop that is still starting is never stopped: only one that
	# has crashed on a stale socket since it started.
	$started = ($running | Measure-Object -Property StartTime -Minimum).Minimum
	'Docker Desktop is open but its engine does not answer yet; waiting for it.'
	$until = (Get-Date).AddSeconds($WaitSeconds)
	while ((Get-Date) -lt $until -and -not (Test-SocketCrash $started)) {
		if (Test-Engine) { 'Docker engine is running.'; exit 0 }
		Start-Sleep -Seconds 5
	}
	if (-not (Test-SocketCrash $started)) { "The engine did not answer within $WaitSeconds seconds, and Docker Desktop shows no stale-socket crash; leaving it alone."; exit 1 }
	'Docker Desktop crashed on a stale socket; stopping it so the sockets can be cleared.'
	$running | Stop-Process -Force -ErrorAction SilentlyContinue
	Start-Sleep -Seconds 4
	if (Get-Process -Name $names -ErrorAction SilentlyContinue) { 'Docker Desktop is still running after the stop; not touching its sockets. Quit it from the tray, then run this again.'; exit 1 }
}

$stale = @(Get-StaleSockets)
foreach ($file in $stale) {
	try { [System.IO.File]::Delete($file.FullName) } catch { }
}
$stale = @(Get-StaleSockets)
if ($stale.Count) {
	$targets = ($stale | ForEach-Object { "'" + (ConvertTo-WslPath $_.FullName) + "'" }) -join ' '
	$job = Start-Job -ScriptBlock { param($t) wsl.exe -d docker-desktop -u root -- sh -c "rm -f $t" 2>&1 } -ArgumentList $targets
	if (-not (Wait-Job $job -Timeout 90)) { Stop-Job $job }
	Remove-Job $job -Force -ErrorAction SilentlyContinue
	wsl.exe --terminate docker-desktop 2>&1 | Out-Null
}
$stale = @(Get-StaleSockets)
foreach ($dir in ($stale | ForEach-Object { $_.DirectoryName } | Sort-Object -Unique)) {
	# Last resort: Windows can still rename the folder; Docker Desktop makes a fresh one.
	$aside = (Split-Path $dir -Leaf) + '.stale-' + (Get-Date -Format 'yyyyMMddHHmmss')
	Rename-Item -LiteralPath $dir -NewName $aside -ErrorAction SilentlyContinue
	"Moved $dir aside as $aside."
}
$left = @(Get-StaleSockets).Count
"Stale Docker sockets cleared ($left left)."

if ($NoStart) { exit 0 }
if (-not (Test-Path $exe)) { "Docker Desktop was not found at $exe."; exit 1 }
Start-Process -FilePath $exe
'Docker Desktop started; waiting for the engine.'
if (Wait-Engine $WaitSeconds) { 'Docker engine is running.'; exit 0 }
"The Docker engine did not answer within $WaitSeconds seconds. See %LOCALAPPDATA%\Docker\log\host\com.docker.backend.exe.log."
exit 1
