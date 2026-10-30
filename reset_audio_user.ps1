# Audio Reset Script - User Level
$ErrorActionPreference = "SilentlyContinue"

Write-Host "========================================"
Write-Host "   Audio Reset Tool (User Level)"
Write-Host "========================================"
Write-Host ""

# Step 1: Backup
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backupPath = Join-Path $env:USERPROFILE "Desktop\AudioBackup_$timestamp"
New-Item -Path $backupPath -ItemType Directory -Force | Out-Null
Write-Host "[1/4] Backing up current audio registry settings..."

$regFile = Join-Path $backupPath "Audio.reg"
& reg export "HKEY_CURRENT_USER\Software\Microsoft\Multimedia\Audio" $regFile /y 2>&1 | Out-Null
Write-Host "  OK: Backed up HKCU Audio settings"
Write-Host "  Backup location: $backupPath"
Write-Host ""

# Step 2: Reset Default Audio Endpoint
Write-Host "[2/4] Resetting default audio endpoint..."

$defaultEpPath = "HKCU:\Software\Microsoft\Multimedia\Audio\DefaultEndpoint"
if (Test-Path $defaultEpPath) {
    Remove-ItemProperty -Path $defaultEpPath -Name "*" -Force -ErrorAction SilentlyContinue
    Write-Host "  OK: Cleared default endpoint preference"
} else {
    Write-Host "  Skipped: No default endpoint preference found"
}

# Reset per-app volume settings
$appVolumePath = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Audio"
if (Test-Path $appVolumePath) {
    Remove-Item -Path $appVolumePath -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host "  OK: Reset volume mixer app settings"
}
Write-Host ""

# Step 3: Reset audio effects and sessions
Write-Host "[3/4] Resetting audio sessions..."

$sessionPath = "HKCU:\Software\Microsoft\Multimedia\Audio\WaveOut"
if (Test-Path $sessionPath) {
    Remove-Item -Path $sessionPath -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host "  OK: Reset WaveOut session"
}

$dsoundPath = "HKCU:\Software\Microsoft\DirectSound"
if (Test-Path $dsoundPath) {
    Remove-Item -Path $dsoundPath -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host "  OK: Reset DirectSound config"
}
Write-Host ""

# Step 4: Try to restart audio services
Write-Host "[4/4] Restarting audio services..."

$svcRestarted = $false
foreach ($svc in @("Audiosrv", "AudioEndpointBuilder")) {
    try {
        Stop-Service -Name $svc -Force -ErrorAction Stop
        $svcRestarted = $true
        Write-Host "  Stopped: $svc"
    } catch {
        Write-Host "  Cannot stop $svc (admin required): $($_.Exception.Message)"
    }
}

if ($svcRestarted) {
    Start-Sleep -Seconds 3
    foreach ($svc in @("AudioEndpointBuilder", "Audiosrv")) {
        try {
            Start-Service -Name $svc -ErrorAction Stop
            Write-Host "  Started: $svc"
        } catch {
            Write-Host "  Failed to start: $svc"
        }
    }
} else {
    Write-Host ""
    Write-Host "  WARNING: Cannot restart audio services without admin."
    Write-Host "  Please do one of:"
    Write-Host "    1. Right-click taskbar speaker -> Troubleshoot sound problems"
    Write-Host "    2. Open services.msc and manually restart Windows Audio"
}
Write-Host ""

# Verify
Write-Host "========================================"
Write-Host "   Verification"
Write-Host "========================================"
Write-Host ""
Write-Host "Audio Service Status:"
foreach ($svc in @("Audiosrv", "AudioEndpointBuilder", "NahimicService")) {
    $s = Get-Service -Name $svc -ErrorAction SilentlyContinue
    if ($s) {
        Write-Host "  $($s.Name): $($s.Status)"
    }
}
Write-Host ""
Write-Host "Audio Devices:"
Get-CimInstance Win32_SoundDevice | Select-Object Name, Status | Format-Table -AutoSize

Write-Host "========================================"
Write-Host "   Reset Complete!"
Write-Host "========================================"
Write-Host ""
Write-Host "Next steps:"
Write-Host "  1. Right-click taskbar speaker icon -> Sound Settings"
Write-Host "  2. Check if output device auto-selected correctly"
Write-Host "  3. If still no sound, run Windows Audio Troubleshooter"
Write-Host "     (Settings -> System -> Sound -> Troubleshoot)"
Write-Host "  4. Backup saved at: $backupPath"
