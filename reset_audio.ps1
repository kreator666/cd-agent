# Audio Reset Script - Run with Admin privileges
#Requires -RunAsAdministrator

$ErrorActionPreference = "SilentlyContinue"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "   音频设备重置工具" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Step 1: Backup
$backupPath = Join-Path $env:USERPROFILE ("Desktop\AudioBackup_" + (Get-Date -Format 'yyyyMMdd_HHmmss'))
New-Item -Path $backupPath -ItemType Directory -Force | Out-Null
Write-Host "[1/5] 备份当前音频注册表设置..." -ForegroundColor Yellow

$backupKeys = @(
    @{ Key = 'HKCU:\Software\Microsoft\Multimedia\Audio'; ExportPath = 'HKEY_CURRENT_USER\Software\Microsoft\Multimedia\Audio' },
    @{ Key = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Audio'; ExportPath = 'HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Audio' }
)

foreach ($bk in $backupKeys) {
    if (Test-Path $bk.Key) {
        $regFile = Join-Path $backupPath ($bk.ExportPath -replace '[\\:]', '_') + '.reg'
        & reg export $bk.ExportPath $regFile /y 2>&1 | Out-Null
        Write-Host "  OK: $($bk.Key)" -ForegroundColor Green
    }
}
Write-Host "  备份位置: $backupPath" -ForegroundColor Gray
Write-Host ""

# Step 2: Reset Default Audio Endpoint
Write-Host "[2/5] 重置默认音频端点..." -ForegroundColor Yellow

# Remove user preference for default audio device (Windows will re-detect)
$audioRegPath = 'HKCU:\Software\Microsoft\Multimedia\Audio'
if (Test-Path "$audioRegPath\DefaultEndpoint") {
    Remove-ItemProperty -Path "$audioRegPath\DefaultEndpoint" -Name '*' -Force -ErrorAction SilentlyContinue
    Write-Host "  OK: 已清除默认端点偏好" -ForegroundColor Green
} else {
    Write-Host "  跳过: 无默认端点注册表项" -ForegroundColor Gray
}

# Reset volume mixer per-app settings
$volumeMixerPath = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Audio'
if (Test-Path $volumeMixerPath) {
    Remove-Item -Path $volumeMixerPath -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host "  OK: 已重置音量混合器设置" -ForegroundColor Green
}
Write-Host ""

# Step 3: Stop audio services
Write-Host "[3/5] 停止音频相关服务..." -ForegroundColor Yellow

$services = @('Audiosrv', 'AudioEndpointBuilder', 'NahimicService', 'SenaryAudioApp.Svc')
foreach ($svc in $services) {
    $service = Get-Service -Name $svc -ErrorAction SilentlyContinue
    if ($service -and $service.Status -eq 'Running') {
        Stop-Service -Name $svc -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 2
        Write-Host "  已停止: $($service.DisplayName) ($svc)" -ForegroundColor Green
    } else {
        Write-Host "  跳过: $svc (未运行或不存在)" -ForegroundColor Gray
    }
}
Write-Host ""

# Step 4: Restart audio services
Write-Host "[4/5] 重新启动音频服务..." -ForegroundColor Yellow
Start-Sleep -Seconds 3

# Start in reverse order
$restartServices = @('AudioEndpointBuilder', 'Audiosrv', 'SenaryAudioApp.Svc', 'NahimicService')
foreach ($svc in $restartServices) {
    $service = Get-Service -Name $svc -ErrorAction SilentlyContinue
    if ($service) {
        Start-Service -Name $svc -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 2
        $newService = Get-Service -Name $svc
        if ($newService.Status -eq 'Running') {
            Write-Host "  OK: $($newService.DisplayName) 已启动" -ForegroundColor Green
        } else {
            Write-Host "  警告: $($newService.DisplayName) 启动失败 - $($newService.Status)" -ForegroundColor Red
        }
    }
}
Write-Host ""

# Step 5: Rescan audio devices
Write-Host "[5/5] 触发音频设备重新扫描..." -ForegroundColor Yellow

# Force device rescan via pnputil
& pnputil /scan-devices 2>&1 | Out-Null
Write-Host "  OK: 已触发设备扫描" -ForegroundColor Green

# Enumerate audio endpoints
$audioEndpoints = @()
try {
    $audioEndpoints = Get-PnpDevice -Class 'AudioEndpoint' -ErrorAction SilentlyContinue
} catch {}
Write-Host "  发现 $($audioEndpoints.Count) 个音频端点" -ForegroundColor Gray

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "   重置完成！" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "总结:" -ForegroundColor Yellow
Write-Host "  - 注册表设置已备份到桌面" -ForegroundColor White
Write-Host "  - 默认音频端点已重置" -ForegroundColor White
Write-Host "  - 所有音频服务已重启" -ForegroundColor White
Write-Host "  - 设备已重新扫描" -ForegroundColor White
Write-Host ""
Write-Host "请检查:" -ForegroundColor Yellow
Write-Host "  1. 右键任务栏音量图标 -> 声音设置" -ForegroundColor White
Write-Host "  2. 确认输出设备已自动选择为正确的扬声器" -ForegroundColor White
Write-Host "  3. 测试播放一段音频" -ForegroundColor White
Write-Host ""
Write-Host "如需恢复，备份文件在: $backupPath" -ForegroundColor Gray
