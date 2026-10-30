# Audio Driver Repair Script
$ErrorActionPreference = "SilentlyContinue"

Write-Host "========================================"
Write-Host "  Audio Driver Repair Tool"
Write-Host "========================================"
Write-Host ""

# Step 1: Check for problem devices
Write-Host "[1/5] Checking for audio device errors..."
$problemDevices = @()
Get-CimInstance Win32_PnPEntity | Where-Object {
    $_.ConfigManagerErrorCode -ne 0 -and
    ($_.Name -match "audio|sound|senary|nahimic|realtek")
} | ForEach-Object {
    $problemDevices += $_
    Write-Host "  PROBLEM: $($_.Name) - Error Code: $($_.ConfigManagerErrorCode)" -ForegroundColor Red
}
if ($problemDevices.Count -eq 0) {
    Write-Host "  No audio devices with error codes found."
}
Write-Host ""

# Step 2: Get driver details for main audio devices
Write-Host "[2/5] Driver details for audio devices:"
Get-CimInstance Win32_PnPSignedDriver | Where-Object {
    $_.DeviceClass -eq "MEDIA" -or $_.DeviceName -match "audio|sound|senary"
} | Select-Object DeviceName, DriverVersion, DriverDate, InfName | Format-Table -AutoSize
Write-Host ""

# Step 3: Scan for hardware changes (rescan devices)
Write-Host "[3/5] Scanning for hardware changes..."
& pnputil /scan-devices 2>&1 | Out-Null
Write-Host "  Hardware scan completed."
Write-Host ""

# Step 4: Find the Senary Audio device (main audio) and reinstall its driver
Write-Host "[4/5] Attempting driver reinstall for main audio device..."

$senaryDevice = Get-CimInstance Win32_PnPEntity | Where-Object {
    $_.Name -match "Senary Audio"
} | Select-Object -First 1

if ($senaryDevice) {
    $deviceId = $senaryDevice.PNPDeviceID
    Write-Host "  Found: $($senaryDevice.Name)"
    Write-Host "  Device ID: $deviceId"
    
    # Disable then re-enable the device
    Write-Host "  Disabling device..."
    & pnputil /disable-device "$deviceId" 2>&1
    Start-Sleep -Seconds 3
    
    Write-Host "  Re-enabling device..."
    & pnputil /enable-device "$deviceId" 2>&1
    Start-Sleep -Seconds 3
    
    Write-Host "  Driver reinstall attempted for Senary Audio." -ForegroundColor Green
} else {
    Write-Host "  Senary Audio device not found by name, trying all media devices..." -ForegroundColor Yellow
    
    # Try to find any media class device
    $mediaDevices = Get-CimInstance Win32_PnPEntity | Where-Object {
        $_.PNPClass -eq "MEDIA" -or $_.PNPClass -eq "Audio"
    }
    foreach ($dev in $mediaDevices) {
        Write-Host "  Found media device: $($dev.Name) ($($dev.PNPDeviceID))"
    }
}
Write-Host ""

# Step 5: Reinstall ALL audio devices
Write-Host "[5/5] Reinstalling all audio devices..."

$audioDevices = @(
    "NVIDIA High Definition Audio",
    "AMD Streaming Audio Device",
    "Nahimic mirroring device",
    "AMD High Definition Audio Device",
    "Senary Audio",
    "NVIDIA Virtual Audio Device (Wave Extensible) (WDM)"
)

foreach ($devName in $audioDevices) {
    $dev = Get-CimInstance Win32_PnPEntity | Where-Object {
        $_.Name -eq $devName
    } | Select-Object -First 1
    
    if ($dev) {
        $devId = $dev.PNPDeviceID
        Write-Host "  Processing: $devName"
        
        # Disable
        & pnputil /disable-device "$devId" 2>&1 | Out-Null
        Start-Sleep -Seconds 1
        
        # Enable
        & pnputil /enable-device "$devId" 2>&1 | Out-Null
        Start-Sleep -Seconds 1
        
        Write-Host "    Done." -ForegroundColor Green
    }
}

Write-Host ""
Write-Host "========================================"
Write-Host "  Repair Complete!"
Write-Host "========================================"
Write-Host ""
Write-Host "Verifying device status..."
Get-CimInstance Win32_SoundDevice | Select-Object Name, Status, StatusInfo | Format-Table -AutoSize

Write-Host ""
Write-Host "If sound still doesn't work, please:"
Write-Host "  1. Restart your computer"
Write-Host "  2. Check Device Manager for yellow warning icons"
Write-Host "     (Win+X -> Device Manager -> Sound, video and game controllers)"
Write-Host "  3. Download latest Senary audio driver from manufacturer website"
